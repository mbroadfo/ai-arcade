// AI Arcade read-only state exporter for RetroPie ES c9d905c.
#pragma once
#include "views/ViewController.h"
#include "views/SystemView.h"
#include "views/gamelist/IGameListView.h"
#include "SystemData.h"
#include "Window.h"
#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>
#include <rapidjson/filewritestream.h>
#include <chrono>
#include <fstream>
#include <cstdio>
#include <unistd.h>
#include <set>

inline std::string arcadeEntryId(const std::string& system, const std::string& path)
{
    // Length prefix avoids separator collisions and stays stable across restarts.
    return std::to_string(system.size()) + ":" + system + path;
}

template<typename Writer>
inline void writeArcadeEntries(Writer& out, SystemData* system, FileData* folder, bool visible)
{
    const auto& displayed = folder->getChildrenListToDisplay();
    std::set<FileData*> shown(displayed.begin(), displayed.end());
    for (auto item : folder->getChildren()) {
        if (item->getType() != GAME && item->getType() != FOLDER) continue;
        bool itemVisible = visible && shown.count(item);
        auto source = item->getSourceFileData();
        out.StartObject();
        out.Key("id"); out.String(arcadeEntryId(system->getName(), item->getPath()).c_str());
        out.Key("game_id");
        if (item->getType() == GAME)
            out.String(arcadeEntryId(source->getSystem()->getName(), source->getPath()).c_str());
        else out.Null();
        out.Key("parent_path"); out.String(folder->getPath().c_str());
        out.Key("name"); out.String(item->getName().c_str());
        out.Key("path"); out.String(item->getPath().c_str());
        out.Key("source_system"); out.String(source->getSystem()->getName().c_str());
        out.Key("source_path"); out.String(source->getPath().c_str());
        out.Key("type"); out.String(item->getType() == GAME ? "game" : "folder");
        out.Key("visible"); out.Bool(itemVisible);
        out.Key("playability"); out.String("unknown");
        out.Key("metadata"); out.StartObject();
        for (const auto& field : item->metadata.getMDD()) {
            out.Key(field.key.c_str()); out.String(item->metadata.get(field.key).c_str());
        }
        out.EndObject(); out.EndObject();
        if (item->getType() == FOLDER) writeArcadeEntries(out, system, item, itemVisible);
    }
}

inline void publishArcadeCatalog(const std::string& boot)
{
    using namespace std::chrono;
    static steady_clock::time_point last;
    static unsigned long generation = 0;
    const std::string target = "/run/ai-arcade/es-catalog.json";
    const bool requested = std::remove("/run/ai-arcade/es-catalog.request") == 0;
    auto now = steady_clock::now();
    if (generation && !requested && access(target.c_str(), F_OK) == 0
        && duration_cast<seconds>(now - last).count() < 60) return;
    const std::string temp = target + "." + std::to_string(getpid()) + ".tmp";
    FILE* file = std::fopen(temp.c_str(), "wb");
    if (!file) return;
    char bytes[65536];
    bool written;
    {
        rapidjson::FileWriteStream stream(file, bytes, sizeof(bytes));
        rapidjson::Writer<rapidjson::FileWriteStream> out(stream);
        out.StartObject();
        out.Key("schema_version"); out.Int(1);
        out.Key("source"); out.String("emulationstation");
        out.Key("kind"); out.String("catalog");
        out.Key("pid"); out.Int(getpid());
        out.Key("boot_id"); out.String(boot.c_str());
        out.Key("generation"); out.Uint64(generation + 1);
        out.Key("monotonic_ms"); out.Int64(duration_cast<milliseconds>(now.time_since_epoch()).count());
        out.Key("systems"); out.StartArray();
        for (auto system : SystemData::sSystemVector) {
            bool visible = system->isVisible();
            out.StartObject();
            out.Key("name"); out.String(system->getName().c_str());
            out.Key("full_name"); out.String(system->getFullName().c_str());
            out.Key("is_collection"); out.Bool(system->isCollection());
            out.Key("is_game_system"); out.Bool(system->isGameSystem());
            out.Key("visible"); out.Bool(visible);
            out.Key("root_path"); out.String(system->getRootFolder()->getPath().c_str());
            out.Key("entries"); out.StartArray();
            writeArcadeEntries(out, system, system->getRootFolder(), visible);
            out.EndArray(); out.EndObject();
        }
        out.EndArray(); out.EndObject(); stream.Flush();
        written = !std::ferror(file);
    }
    if (std::fclose(file) != 0) written = false;
    if (written && std::rename(temp.c_str(), target.c_str()) == 0) {
        ++generation;
        last = now;
    }
}

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
    publishArcadeCatalog(boot);
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
