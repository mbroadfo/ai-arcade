"""Pinned Super Mario Bros. World ROM. The bytes stay outside the repository.

LEGAL.md allows this checksum. It does not allow the ROM image in git.
"""
from __future__ import annotations

from pathlib import Path

from games.lab.paths import roms_dir
from games.lab.roms import RomRejected, digest, store_rom

# No-Intro / GoodTools "Super Mario Bros. (World)". Header 4E 45 53 1A 02 01 01 00.
SMB_REMOTE = "/home/pi/RetroPie/roms/nes/Super Mario Bros. (Japan, USA).zip"
SMB_SHA1 = "ea343f4e445a9050d4b4fbac2c77d0693b1d0922"
SMB_SHA256 = "f61548fdf1670cffefcc4f0b7bdcdd9eaba0c226e3b74f8666071496988248de"
SMB_SIZE = 40976
SMB_HEADER = bytes.fromhex("4e45531a02010100")


def accept_smb(data: bytes) -> None:
    """Raise RomRejected unless data is the pinned World ROM."""
    sha1, sha256 = digest(data)
    if len(data) != SMB_SIZE or data[:8] != SMB_HEADER or sha1 != SMB_SHA1 or sha256 != SMB_SHA256:
        raise RomRejected(
            "not the cabinet Super Mario Bros. (Japan, USA) ROM "
            f"(size {len(data)}, sha1 {sha1})"
        )


def pinned_smb() -> Path | None:
    """The lab-home ROM when it is already the pinned World image."""
    path = roms_dir() / "smb.nes"
    if not path.is_file():
        return None
    try:
        accept_smb(path.read_bytes())
    except (OSError, RomRejected):
        return None
    return path


def store_smb() -> Path:
    """A short local name. The cabinet path has spaces and parentheses."""
    found = pinned_smb()
    if found is not None:
        return found
    return store_rom(SMB_REMOTE, "smb.nes", accept_smb)
