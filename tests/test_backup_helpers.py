import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from backup_common import excluded, s3_key


def test_s3_key_with_prefix():
    assert s3_key("pi-library", "mame/pacman.zip") == "pi-library/mame/pacman.zip"


def test_s3_key_without_prefix():
    assert s3_key("", "mame/pacman.zip") == "mame/pacman.zip"


def test_excluded_glob():
    assert excluded("foo/Thumbs.db", ["**/Thumbs.db"])
    assert not excluded("mame/pacman.zip", ["**/Thumbs.db"])
