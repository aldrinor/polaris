"""Thin call-through shim for the V30 Phase-2 full-scale launcher.

Q6 consolidation: the v30_phase2 env profile (V30 phase gating + V29 baseline
knobs), default --out-root, log prefix, and banner now live in
scripts/run_full_scale.py (VARIANT_ENV["v30_phase2"]). This behaves
BYTE-FOR-BYTE like the pre-consolidation script.

IMPORTANT — this filename is a KNOWN dynamic reference:
  * src/polaris_graph/audit_ir/honest_sweep_job_runner.py launches it BY PATH
    as a subprocess: `python scripts/run_full_scale_v30_phase2.py --only <slug>
    --out-root <dir>`. Because run() injects --only/--out-root only when absent,
    the runner-supplied args are forwarded verbatim.
  * tests/polaris_graph/test_honest_sweep_job_runner.py asserts
    `sweep_script.name == "run_full_scale_v30_phase2.py"`, so this filename
    MUST NOT change.
The shim keeps the file byte-runnable and path-loadable; do not delete it.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is importable when run by-path as a subprocess.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from run_full_scale import run  # noqa: E402


def main() -> int:
    return run("v30_phase2", sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
