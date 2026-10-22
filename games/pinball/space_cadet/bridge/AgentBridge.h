#pragma once

// A line-based JSON socket on 127.0.0.1 that lets a program watch and play the table. Off unless SCP_AGENT_PORT is set.
// Commands (one JSON object per line, one JSON reply per line):
//   {"cmd":"state"}                              what is on the table now
//   {"cmd":"input","name":"left","down":true}    left, right, plunger, nudge_left, nudge_right, nudge_up, new_game
//   {"cmd":"mode","step":true}                   step: time moves only when told to; false: real time again
//   {"cmd":"step","frames":N}                    advance N fixed frames (10 ms each), reply with the state
namespace AgentBridge
{
	void Init();
	bool Active();
	bool StepMode();
	// Called once per main-loop pass, before the game's own frame. Handles any waiting commands.
	void Poll();
}
