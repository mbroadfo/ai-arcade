"""Libretro cores live in the lab home, not the repo. Buildbot builds for this OS."""
from __future__ import annotations

import io
import os
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

from games.lab.paths import assert_outside_repo, cores_dir

_EXT = ".dll" if sys.platform == "win32" else ".so"
_PLATFORM = "windows/x86_64" if sys.platform == "win32" else "linux/x86_64"
CORES = {
    "nes": {
        "file": f"fceumm_libretro{_EXT}",
        "url": f"https://buildbot.libretro.com/nightly/{_PLATFORM}/latest/fceumm_libretro{_EXT}.zip",
    },
    "atari2600": {
        "file": f"stella2014_libretro{_EXT}",
        "url": f"https://buildbot.libretro.com/nightly/{_PLATFORM}/latest/stella2014_libretro{_EXT}.zip",
    },
}


def ensure_core(system: str) -> Path:
    try:
        spec = CORES[system]
    except KeyError:
        raise RuntimeError(f"no core for {system}") from None
    dest_dir = cores_dir()
    assert_outside_repo(dest_dir)
    dest = dest_dir / spec["file"]
    if dest.is_file() and dest.stat().st_size > 100_000:
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "ai-arcade-lab"})
    with urllib.request.urlopen(request, timeout=120) as response:
        blob = response.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = [name for name in archive.namelist() if name.endswith(spec["file"]) and not name.endswith("/")]
        if not names:
            names = [name for name in archive.namelist() if name.endswith(_EXT) and not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(f"{spec['url']} did not contain one {spec['file']} ({names})")
        dest.write_bytes(archive.read(names[0]))
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    return dest
