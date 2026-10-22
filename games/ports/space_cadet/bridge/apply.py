"""Add the agent bridge to a copy of the SpaceCadetPinball source (run on the Pi):

    python3 apply.py <source folder> <this folder>

Copies AgentBridge.cpp/.h in, lists it in CMakeLists.txt, starts it in winmain and polls it in the main loop; in step mode the
game's own real-time frame is skipped, so time moves only by the bridge's "step" command. Safe to run twice."""
import pathlib
import shutil
import sys

src, here = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
code = src / "SpaceCadetPinball"
for name in ("AgentBridge.cpp", "AgentBridge.h"):
    shutil.copy(here / name, code / name)


def edit(path, old, new):
    text = path.read_text()
    if new in text:
        return
    assert old in text, f"{path.name}: {old[:50]!r} not found"
    path.write_text(text.replace(old, new, 1))


edit(src / "CMakeLists.txt", "        SpaceCadetPinball/control.cpp\n",
     "        SpaceCadetPinball/AgentBridge.cpp\n        SpaceCadetPinball/AgentBridge.h\n        SpaceCadetPinball/control.cpp\n")
w = code / "winmain.cpp"
edit(w, '#include "control.h"\n', '#include "control.h"\n#include "AgentBridge.h"\n')
edit(w, "\t\t\tif (!single_step && !no_time_loss)\n\t\t\t{\n\t\t\t\tauto dt = static_cast<float>(frameDuration.count());",
     "\t\t\tAgentBridge::Poll();\n\t\t\tif (!single_step && !no_time_loss && !AgentBridge::StepMode())\n\t\t\t{\n\t\t\t\tauto dt = static_cast<float>(frameDuration.count());")
edit(w, "\t\tMainLoop();", "\t\tAgentBridge::Init();\n\t\tMainLoop();")
print("bridge applied")
