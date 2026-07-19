"""Thin call-through shim for the v23 full-scale launcher.

Q6 consolidation: the v23 launcher's env profile, default --out-root, log
prefix, and banner now live in scripts/run_full_scale.py (VARIANT_ENV["v23"]).
This shim preserves the historical filename (some code/tests reference it)
and behaves BYTE-FOR-BYTE like the pre-consolidation script.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is importable when run by-path (python scripts/run_full_scale_v23.py).
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from run_full_scale import run  # noqa: E402


def main() -> int:
    return run("v23", sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
