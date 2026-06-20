#!/usr/bin/env python3
"""I-arch-011 PR-e — CONSOLIDATED composition behavioral replay gate (§-1.4, FAIL LOUD).

This is the single pre-spend gate for the composition rebuild: it runs EVERY locally-replayable
component behavioral harness on a REAL banked ``corpus_snapshot.json`` (with ``PG_PRD_REQUIRE_REAL=1``
so a missing corpus FAILS rather than silently falling back to a synthetic fixture), and exits non-zero
naming the first failure. It does NOT relax faithfulness or add production code — it orchestrates the
already-Codex-approved per-component harnesses so the whole composition back-half can be gated with one
command before any VM spend.

Components run here (each internally exercises enforce + hermetic ``PG_STRICT_VERIFY_ENTAILMENT``):
  - I-arch-010 TAIL          -> scripts/iarch010_replay_breadth_faithfulness_harness.py
  - I-arch-011 PR-b BASKETS  -> scripts/iarch011_prb_corroboration_replay_harness.py
  - I-arch-011 PR-c COMPOSE  -> scripts/iarch011_prc_verified_compose_replay_harness.py
  - I-arch-011 PR-d ABS/CONC -> scripts/iarch011_prd_abstract_conclusion_replay_harness.py

NOT locally replayable (explicitly disclosed — never silently omitted; covered by the FINAL fresh VM
run + its §-1.1 line-by-line audit, per state/iarch_wiring_acceptance_checklist.md):
  - I-arch-009 QUALITY GATE (Qwen3-Embedding-8B relevance embedder) — needs the 8B model on a GPU; its
    behavioral proof is the GPU bake-off (scripts/relevance_scorer_bakeoff.py) + the VM run's
    fail-closed loaded-identity == Qwen3-Embedding-8B check (no silent MiniLM).
  - I-arch-011 PR-a STORM-OUTLINE adapter — structure-only (asserts no facts); its section-scaffold
    wiring fires end-to-end only in a full run, verified on the VM (sections == STORM outline).

Run: ``python scripts/iarch011_composition_replay_harness.py`` -> exit 0 iff EVERY component harness
passes on real corpus; non-zero + the failing component otherwise.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Load C:/POLARIS/.env so the live entailment judge is reachable for the enforce legs.
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(_REPO_ROOT / ".env")
except Exception:  # noqa: BLE001 — dotenv optional; env may already be exported
    pass

# Per-harness wall-clock cap (s). Each child has its OWN internal bounded deadline + fail-loud, so this
# is a backstop; a child that exceeds it is a HANG and FAILS the gate (never silently passes).
_PER_HARNESS_TIMEOUT_S = 420

_COMPONENTS = [
    ("I-arch-010 TAIL (breadth + faithfulness)", "scripts/iarch010_replay_breadth_faithfulness_harness.py"),
    ("I-arch-011 PR-b BASKETS (keep-all corroboration)", "scripts/iarch011_prb_corroboration_replay_harness.py"),
    ("I-arch-011 PR-c COMPOSE (per-basket verified-compose)", "scripts/iarch011_prc_verified_compose_replay_harness.py"),
    ("I-arch-011 PR-d ABSTRACT/CONCLUSION (verbatim synthesis)", "scripts/iarch011_prd_abstract_conclusion_replay_harness.py"),
]

# Components that CANNOT be replayed on this box — disclosed in the output, NEVER silently dropped.
_NOT_LOCALLY_REPLAYABLE = [
    "I-arch-009 QUALITY GATE (Qwen3-Embedding-8B) — GPU bake-off + VM loaded-identity fail-closed check",
    "I-arch-011 PR-a STORM-OUTLINE adapter — structure-only; section-scaffold verified on the VM run",
]


def _run_component(label: str, rel_path: str, env: dict) -> dict:
    script = _REPO_ROOT / rel_path
    if not script.is_file():
        return {"label": label, "script": rel_path, "ok": False,
                "reason": "harness script MISSING from the stack"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=_PER_HARNESS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"label": label, "script": rel_path, "ok": False,
                "reason": f"HANG: exceeded {_PER_HARNESS_TIMEOUT_S}s (a child harness must fail loud, never hang)"}
    ok = proc.returncode == 0
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    last = tail[-1] if tail else ""
    return {"label": label, "script": rel_path, "ok": ok, "returncode": proc.returncode,
            "last_line": last[:300]}


def main() -> int:
    # Enforce REAL corpus across the children (a missing banked snapshot FAILS, never silently synthetic).
    env = dict(os.environ)
    env["PG_PRD_REQUIRE_REAL"] = "1"

    results = [_run_component(label, path, env) for label, path in _COMPONENTS]
    failed = [r for r in results if not r["ok"]]

    print(json.dumps({
        "harness": "iarch011_composition_replay_harness (PR-e consolidated gate)",
        "status": "PASS" if not failed else "FAIL",
        "components_run": results,
        "not_locally_replayable_disclosed": _NOT_LOCALLY_REPLAYABLE,
        "require_real_corpus": True,
        "faithfulness": "untouched — orchestrates the per-component harnesses; no production code, no relaxation",
    }, indent=2))

    if failed:
        for r in failed:
            print(f"FAIL [{r['label']}]: {r.get('reason') or r.get('last_line')!r} "
                  f"(rc={r.get('returncode')})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
