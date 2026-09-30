"""Apply the minimal state exporter to the pinned ES source, exactly once."""
from pathlib import Path
import shutil


def patch(source, header):
    source = Path(source)
    changes = {
        'es-app/src/main.cpp': [
            ('#include "EmulationStation.h"', '#include "EmulationStation.h"\n#include "ArcadeState.h"'),
            ('\t\tif(window.isSleeping())', '\t\tpublishArcadeState(window);\n\n\t\tif(window.isSleeping())'),
            ('SDL_WaitEventTimeout(&event, PowerSaver::getTimeout())',
             'SDL_WaitEventTimeout(&event, arcadeEventTimeout(PowerSaver::getTimeout()))'),
        ],
        'es-core/src/Window.h': [
            ('\tbool getAllowSleep();', '\tbool arcadeScreenSaverActive() const { return mRenderScreenSaver; }\n\tbool getAllowSleep();'),
        ],
    }
    outputs = {}
    for relative, replacements in changes.items():
        path = source / relative
        text = path.read_text()
        # Upgrade the first patch revision while preserving PowerSaver's side effects.
        text = text.replace('SDL_WaitEventTimeout(&event, 250 /* AI Arcade heartbeat */)',
                            'SDL_WaitEventTimeout(&event, PowerSaver::getTimeout())')
        for before, after in replacements:
            if after in text:
                continue
            if text.count(before) != 1:
                raise RuntimeError('Unsupported ES source: ' + relative)
            text = text.replace(before, after)
        outputs[path] = text
    for path, text in outputs.items():
        if path.read_text() != text:
            path.write_text(text)
    shutil.copy2(str(header), str(source / 'es-app/src/ArcadeState.h'))
