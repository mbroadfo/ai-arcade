"""Copy a cabinet ROM into the lab home. A game adapter decides which bytes are legal.

The bytes themselves are never written inside the repository.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import zipfile
from pathlib import Path

from games.lab.paths import REPO_ROOT, assert_outside_repo, roms_dir

PI_HOST = os.environ.get("LAB_PI", "pi@192.168.10.122")


class RomRejected(Exception):
    """The file is not the ROM this integration was written against."""


def digest(data: bytes) -> tuple[str, str]:
    return hashlib.sha1(data).hexdigest(), hashlib.sha256(data).hexdigest()


def accept_ines(data: bytes) -> None:
    """Raise RomRejected unless data looks like an iNES ROM. Used for bootable NES games."""
    if len(data) < 16 or data[:4] != b"NES\x1a":
        raise RomRejected("not an iNES file")
    prg = data[4] * 16384
    chr_ = data[5] * 8192
    if 16 + prg + chr_ > len(data):
        raise RomRejected("iNES header claims more data than the file holds")


def _identity() -> list[str]:
    candidates = []
    if os.environ.get("LAB_SSH_KEY"):
        candidates.append(Path(os.environ["LAB_SSH_KEY"]))
    candidates.append(Path.home() / ".ssh" / "id_rsa")
    candidates.append(Path("/mnt/c/Users/Mike/.ssh/id_rsa"))
    for path in candidates:
        if path.is_file():
            return ["-i", str(path)]
    return []


def ssh_command(*remote: str) -> list[str]:
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
        *_identity(), PI_HOST, *remote,
    ]


def fetch_bytes(remote_path: str) -> bytes:
    """Read one file from the cabinet over SSH. The caller decides where the bytes may be stored."""
    quoted = shlex.quote(remote_path)
    try:
        return subprocess.check_output(ssh_command(f"cat {quoted}"))
    except subprocess.CalledProcessError as exc:
        raise RomRejected(f"could not read {remote_path} from the cabinet") from exc


def unwrap_rom(blob: bytes) -> bytes:
    """A raw image, or the single playable file inside a zip."""
    if blob[:2] != b"PK":
        return blob
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        preferred = [name for name in names if Path(name).suffix.lower() in {".nes", ".a26", ".bin"}]
        chosen = preferred or names
        if len(chosen) != 1:
            raise RomRejected(f"expected one ROM in the zip, found {chosen}")
        return archive.read(chosen[0])


def accept_a26(data: bytes) -> None:
    if data[:4] == b"NES\x1a" or data[:2] == b"PK" or not 2048 <= len(data) <= 65536:
        raise RomRejected(f"not an Atari 2600 image ({len(data)} bytes)")


def store_rom(remote_path: str, name: str, check) -> Path:
    """Fetch, check, and write a ROM under the lab home. check(data) raises RomRejected."""
    dest_dir = roms_dir()
    assert_outside_repo(dest_dir)
    data = unwrap_rom(fetch_bytes(remote_path))
    check(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    dest.write_bytes(data)
    return dest


def store_game(system: str, remote_path: str, name: str) -> Path:
    """Fetch a bootable image. A scored game uses its adapter's materialize instead."""
    if system == "nes":
        return store_rom(remote_path, name, accept_ines)
    if system == "atari2600":
        return store_rom(remote_path, name, accept_a26)
    raise RomRejected(f"no ROM check for {system}")


def git_tracks_games() -> list[str]:
    """Porcelain lines that would put a game image in the repository."""
    blocked = (".nes", ".a26", ".bin", ".zip", ".7z", ".so")
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    bad = []
    for line in out.splitlines():
        lowered = line.lower()
        if any(lowered.endswith(ext) for ext in blocked):
            bad.append(line)
    return bad
