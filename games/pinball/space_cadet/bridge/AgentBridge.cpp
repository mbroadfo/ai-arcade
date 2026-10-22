#include "pch.h"
#include "AgentBridge.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <string>

#include "options.h"
#include "pb.h"
#include "score.h"
#include "TBall.h"
#include "TFlipper.h"
#include "TFlipperEdge.h"
#include "TPinballTable.h"
#include "TTextBox.h"
#include "nudge.h"

namespace
{
	int listenFd = -1, clientFd = -1;
	bool stepMode = false;
	std::string inbuf;
	const float StepMs = 10.0f; // one step is 10 ms of game time, whatever the machine's speed

	void Send(const std::string& s)
	{
		if (clientFd < 0)
			return;
		std::string line = s + "\n";
		if (send(clientFd, line.data(), line.size(), MSG_NOSIGNAL) < 0)
		{
			close(clientFd);
			clientFd = -1;
		}
	}

	std::string Quote(const char* s)
	{
		std::string o = "\"";
		for (; s && *s; s++)
		{
			if (*s == '"' || *s == '\\')
			{
				o += '\\';
				o += *s;
			}
			else if (static_cast<unsigned char>(*s) < 32)
				o += ' ';
			else
				o += *s;
		}
		return o + "\"";
	}

	std::string State()
	{
		auto* t = pb::MainTable;
		char b[320];
		std::string o = "{";
		snprintf(b, sizeof b, "\"game_mode\":\"%s\",\"ticks\":%d,\"time\":%.3f,",
		         pb::game_mode == GameModes::InGame ? "in_game" : "game_over", pb::time_ticks, pb::time_now);
		o += b;
		if (!t)
			return o + "\"table\":false}";
		snprintf(b, sizeof b, "\"score\":%d,\"score_e9\":%d,\"ball_number\":%d,\"balls_max\":%d,\"extra_balls\":%d,"
		         "\"tilt_lock\":%s,\"multiball\":%s,\"multiplier\":%d,",
		         t->CurScore, t->CurScoreE9, t->BallCount, t->MaxBallCount, t->ExtraBalls,
		         t->TiltLockFlag ? "true" : "false", t->MultiballFlag ? "true" : "false", t->ScoreMultiplier);
		o += b;
		o += "\"balls\":[";
		bool first = true;
		for (auto* ball : t->BallList)
		{
			if (ball->CollisionDisabledFlag)
				continue;
			snprintf(b, sizeof b, "%s{\"x\":%.4f,\"y\":%.4f,\"z\":%.4f,\"dx\":%.4f,\"dy\":%.4f,\"speed\":%.4f}",
			         first ? "" : ",", ball->Position.X, ball->Position.Y, ball->Position.Z,
			         ball->Direction.X, ball->Direction.Y, ball->Speed);
			o += b;
			first = false;
		}
		o += "],\"flippers\":{";
		auto flipper = [&](const char* name, TFlipper* f, bool comma)
		{
			snprintf(b, sizeof b, "%s\"%s\":{\"angle\":%.4f,\"max\":%.4f}", comma ? "," : "", name,
			         f && f->FlipperEdge ? f->FlipperEdge->CurrentAngle : 0.0f,
			         f && f->FlipperEdge ? f->FlipperEdge->AngleMax : 0.0f);
			o += b;
		};
		flipper("left", t->FlipperL, false);
		flipper("right", t->FlipperR, true);
		o += "},\"message\":";
		auto* m = pb::InfoTextBox ? pb::InfoTextBox->CurrentMessage : nullptr;
		o += Quote(m ? m->Text : "");
		o += ",\"miss_message\":";
		auto* mm = pb::MissTextBox ? pb::MissTextBox->CurrentMessage : nullptr;
		o += Quote(mm ? mm->Text : "");
		return o + "}";
	}

	// The keys the game's default bindings use, so that the game's own input path (and its tilt, nudge and launch rules) runs.
	bool KeyFor(const std::string& name, int* key)
	{
		if (name == "left") *key = SDLK_z;
		else if (name == "right") *key = SDLK_SLASH;
		else if (name == "plunger") *key = SDLK_SPACE;
		else if (name == "nudge_left") *key = SDLK_x;
		else if (name == "nudge_right") *key = SDLK_PERIOD;
		else if (name == "nudge_up") *key = SDLK_UP;
		else if (name == "new_game") *key = SDLK_F2;
		else return false;
		return true;
	}

	// The text after "key": up to the next , or }
	std::string Field(const std::string& line, const char* key)
	{
		auto p = line.find(std::string("\"") + key + "\"");
		if (p == std::string::npos) return "";
		p = line.find(':', p);
		if (p == std::string::npos) return "";
		auto e = line.find_first_of(",}", p + 1);
		std::string v = line.substr(p + 1, e - p - 1);
		while (!v.empty() && (v.front() == ' ' || v.front() == '"')) v.erase(v.begin());
		while (!v.empty() && (v.back() == ' ' || v.back() == '"')) v.pop_back();
		return v;
	}

	void Handle(const std::string& line)
	{
		const auto cmd = Field(line, "cmd");
		if (cmd == "state")
			Send(State());
		else if (cmd == "mode")
		{
			stepMode = Field(line, "step") == "true";
			Send(State());
		}
		else if (cmd == "step")
		{
			int n = atoi(Field(line, "frames").c_str());
			for (int i = 0; i < n && i < 100000; i++)
				pb::frame(StepMs);
			Send(State());
		}
		else if (cmd == "input")
		{
			int key;
			if (!KeyFor(Field(line, "name"), &key))
			{
				Send("{\"error\":\"unknown input\"}");
				return;
			}
			GameInput in{InputTypes::Keyboard, key};
			if (Field(line, "down") == "true")
				pb::InputDown(in);
			else
				pb::InputUp(in);
			Send("{\"ok\":true}");
		}
		else
			Send("{\"error\":\"unknown cmd\"}");
	}
}

namespace AgentBridge
{
	void Init()
	{
		const char* port = getenv("SCP_AGENT_PORT");
		if (!port || !*port)
			return;
		listenFd = socket(AF_INET, SOCK_STREAM, 0);
		int one = 1;
		setsockopt(listenFd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
		sockaddr_in a{};
		a.sin_family = AF_INET;
		a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
		a.sin_port = htons(static_cast<uint16_t>(atoi(port)));
		if (bind(listenFd, reinterpret_cast<sockaddr*>(&a), sizeof a) < 0 || listen(listenFd, 1) < 0)
		{
			close(listenFd);
			listenFd = -1;
			return;
		}
		fcntl(listenFd, F_SETFL, O_NONBLOCK);
		if (getenv("SCP_AGENT_STEP"))
			stepMode = true;
	}

	bool Active() { return listenFd >= 0; }
	bool StepMode() { return listenFd >= 0 && stepMode; }

	void Poll()
	{
		if (listenFd < 0)
			return;
		if (clientFd < 0)
		{
			clientFd = accept(listenFd, nullptr, nullptr);
			if (clientFd >= 0)
				fcntl(clientFd, F_SETFL, O_NONBLOCK);
			inbuf.clear();
		}
		if (clientFd < 0)
			return;
		char buf[1024];
		for (;;)
		{
			auto n = recv(clientFd, buf, sizeof buf, 0);
			if (n > 0)
				inbuf.append(buf, n);
			else if (n == 0)
			{
				close(clientFd);
				clientFd = -1;
				return;
			}
			else
				break;
		}
		size_t nl;
		while ((nl = inbuf.find('\n')) != std::string::npos)
		{
			auto line = inbuf.substr(0, nl);
			inbuf.erase(0, nl + 1);
			Handle(line);
		}
	}
}
