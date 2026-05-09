"""Make src/ importable for crown-jewel tests so deep modules in
src.polaris_graph.* can resolve their own `from polaris_graph...` imports."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
