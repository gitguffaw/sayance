"""Internal benchmark package.

The public compatibility surface remains in run_benchmark.py.
"""
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
try:
    __version__ = _VERSION_FILE.read_text().strip()
except OSError:
    __version__ = "unknown"
