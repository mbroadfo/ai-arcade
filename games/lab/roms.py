"""Copy a cabinet ROM into the lab home and accept it only when the bytes match.

The pinned digest is the World ROM already on the cabinet
(Super Mario Bros. (Japan, USA), 40,976 bytes). The bytes themselves are never
written inside the repository. LEGAL.md allows a checksum; it does not allow the ROM.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import zipfile
from pathlib import Path

from games.lab.paths import REPO_ROOT, assert_outside_repo, roms_dir

# No-Intro / GoodTools "Super Mario Bros. (World)". Header 4E 45 53 1A 02 01 01 00.
SMB_REMOTE = "/home/pi/RetroPie/roms/nes/Super Mario Bros. (Japan, USA).zip"
SMB_SHA1 = "ea343f4e445a9050d4b4fbac2c77d0693b1d0922"
SMB_SHA256 = "f61548fdf1670cffefcc4f0b7bdcdd9eaba0c226e3b74f8666071496988248de"
SMB_SIZE = 40976
SMB_HEADER = bytes.fromhex("4e45531a02010100")
PI_HOST = os.environ.get("LAB_PI", "pi@192.168.10.122")


class RomRejected(Exception):
    """The file is not the ROM this integration was written against."""


def digest(data: bytes) -> tuple[str, str]:
    return hashlib.sha1(data).hexdigest(), hashlib.sha256(data).hexdigest()


def accept_smb(data: bytes) -> None:
    """Raise RomRejected unless data is the pinned World ROM."""
    sha1, sha256 = digest(data)
    if len(data) != SMB_SIZE or data[:8] != SMB_HEADER or sha1 != SMB_SHA1 or sha256 != SMB_SHA256:
        raise RomRejected(
            "not the cabinet Super Mario Bros. (Japan, USA) ROM "
            f"(size {len(data)}, sha1 {sha1})"
        )


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


def store_smb() -> Path:
    # A short local name. The cabinet path has spaces and parentheses, which some cores mishandle.
    return store_rom(SMB_REMOTE, "smb.nes", accept_smb)


def store_game(system: str, remote_path: str, name: str) -> Path:
    if system == "nes":
        return store_rom(remote_path, name, accept_smb if name.startswith("Super Mario Bros. (Japan") else accept_ines)
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
