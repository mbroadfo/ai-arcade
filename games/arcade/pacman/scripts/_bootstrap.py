"""Import first in a script here: makes `games.*` and the general `tools/` modules importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for path in (ROOT, ROOT / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
