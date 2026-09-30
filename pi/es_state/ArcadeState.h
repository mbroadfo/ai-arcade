// AI Arcade read-only state exporter for RetroPie ES c9d905c.
#pragma once
#include "views/ViewController.h"
#include "views/SystemView.h"
#include "views/gamelist/IGameListView.h"
#include "SystemData.h"
#include "Window.h"
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <chrono>
#include <fstream>
#include <cstdio>
#include <unistd.h>

inline int arcadeEventTimeout(int timeout)
{
    return timeout >= 0 && timeout < 250 ? timeout : 250;
}

inline void publishArcadeState(Window& window)
{
    using namespace std::chrono;
    static steady_clock::time_point last;
    const auto now = steady_clock::now();
    if (duration_cast<milliseconds>(now - last).count() < 250) return;
    last = now;
    static unsigned long sequence = 0;
    static std::string boot;
    if (boot.empty()) {
        std::ifstream input("/proc/sys/kernel/random/boot_id");
        std::getline(input, boot);
    }
    auto vc = ViewController::get();
    const auto mode = vc->getState().viewing;
    SystemData* system = nullptr;
    FileData* item = nullptr;
    const char* view = "unknown";
    if (mode == ViewController::SYSTEM_SELECT) {
        view = "system_select";
        auto list = vc->getSystemListView();
        if (list->size()) system = list->getSelected();
    } else if (mode == ViewController::GAME_LIST) {
        view = "game_list";
        system = vc->getState().getSystem();
        if (system) item = vc->getGameListView(system)->getCursor();
    }
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> out(buffer);
    out.StartObject();
    out.Key("schema_version"); out.Int(1);
    out.Key("source"); out.String("emulationstation");
    out.Key("pid"); out.Int(getpid());
    out.Key("boot_id"); out.String(boot.c_str());
    out.Key("sequence"); out.Uint64(++sequence);
    out.Key("monotonic_ms"); out.Int64(duration_cast<milliseconds>(now.time_since_epoch()).count());
    out.Key("view"); out.String(view);
    out.Key("overlay_open"); out.Bool(window.peekGui() != vc);
    out.Key("screensaver_active"); out.Bool(window.arcadeScreenSaverActive());
    out.Key("sleeping"); out.Bool(window.isSleeping());
    out.Key("system");
    if (system) {
        out.StartObject();
        out.Key("name"); out.String(system->getName().c_str());
        out.Key("full_name"); out.String(system->getFullName().c_str());
        out.EndObject();
    } else out.Null();
    out.Key("selection");
    if (item) {
        out.StartObject();
        out.Key("name"); out.String(item->getName().c_str());
        out.Key("path"); out.String(item->getPath().c_str());
        out.Key("type"); out.String(item->getType() == GAME ? "game" :
                                    item->getType() == FOLDER ? "folder" : "placeholder");
        out.Key("metadata"); out.StartObject();
        for (const auto& field : item->metadata.getMDD()) {
            out.Key(field.key.c_str()); out.String(item->metadata.get(field.key).c_str());
        }
        out.EndObject(); out.EndObject();
    } else out.Null();
    out.EndObject();
    const std::string target = "/run/ai-arcade/es-state.json";
    const std::string temp = target + "." + std::to_string(getpid()) + ".tmp";
    std::ofstream file(temp, std::ios::binary | std::ios::trunc);
    file << buffer.GetString() << '\n';
    file.close();
    if (file) std::rename(temp.c_str(), target.c_str());
}
