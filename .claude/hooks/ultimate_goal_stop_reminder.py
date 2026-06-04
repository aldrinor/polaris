#!/usr/bin/env python3
"""POLARIS Stop hook — re-injects the BEAT-BOTH SYSTEM LOOP until the mission is done.

Operator directive 2026-06-04: harden the run -> audit -> beat-both -> fix loop into a durable
reminder so Claude keeps working this way — research-first (NEVER guess), line-by-line review of
BOTH our source code AND the produced output, striving for beat-both on ALL 5 golden DR questions,
not just drb_72. A Stop hook is harness-enforced: it fires every time a turn would end, so the
discipline does not depend on Claude's in-context memory drifting under load.

Canonical loop: docs/beat_both_system_loop.md. Per-question status: state/beat_both_status.json.

Contract (https://code.claude.com/docs/en/hooks, mirrored from stop_hook_v3.py):
  - Reads the Stop event JSON from stdin: {"stop_hook_active": bool, ...}.
  - To KEEP working, emit {"decision": "block", "reason": <loop reminder>} to stdout (the reason is
    fed back to the model). To ALLOW the stop, exit 0 with no JSON.
  - Infinite-loop guard: if `stop_hook_active` is already true (this turn is itself a stop-hook
    continuation), DO NOT block again — allow the stop. So the loop reminder fires at most once per
    real stop attempt, then yields. This is a persistent nudge, not a hard cage.

Lessons baked in:
  - stop_hook_must_be_project_scoped: registered in PROJECT .claude/settings.local.json, never
    ~/.claude; AND a CWD guard in the body so a stray global registration no-ops outside POLARIS.
  - feedback_research_then_empirically_test_candidates: the reminder leads with the no-guess gate.
  - feedback_benchmark_the_tool_not_a_component: whole system, not a component proxy.
  - 8.3.10: self-initiated "natural cadence" stops are illegitimate; only the documented stop
    conditions end the loop.

Exits 0 in all paths (never errors out a turn). Emits the block JSON only when the mission is
unfinished AND we are not legitimately waiting AND no halt fired.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --- CWD / project guard: only act inside the POLARIS tree. ------------------ #
POLARIS_ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = POLARIS_ROOT / "state" / "beat_both_status.json"
STATE_DIR = POLARIS_ROOT / "state"

GOLDEN_QUESTIONS = [
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
    "drb_90_adas_liability",
]


def _allow() -> None:
    """Allow the stop: no stdout, exit 0."""
    sys.exit(0)


def _block(reason: str) -> None:
    """Block the stop and feed `reason` back to the model."""
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _active_halt(status: dict) -> bool:
    """A REAL, active halt is signalled by an explicit `halt` field in the status file (a non-empty
    string reason). We deliberately do NOT glob `state/halt_*` here: stale halt markers from old
    resolved sessions would permanently disable the loop reminder. When a genuine halt fires, the
    loop writes BOTH the `state/halt_*` file (boot-ritual protocol) AND sets status['halt']."""
    if not isinstance(status, dict):
        return False
    halt = status.get("halt")
    return isinstance(halt, str) and bool(halt.strip())


def _read_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_reminder(status: dict) -> str:
    per_q = status.get("questions", {}) if isinstance(status, dict) else {}
    waiting_on = status.get("waiting_on") if isinstance(status, dict) else None
    lines = []
    for q in GOLDEN_QUESTIONS:
        lines.append(f"    - {q}: {per_q.get(q, 'not_started')}")
    status_block = "\n".join(lines)
    waiting_note = (
        f"\n  Currently waiting_on: {waiting_on} (a long external run — fine to yield IF a wakeup is "
        f"scheduled; clear waiting_on when it finishes)." if waiting_on else ""
    )
    return f"""BEAT-BOTH SYSTEM LOOP is unfinished — do not stop on 'natural cadence' (CLAUDE.md
8.3.10). The mission: a RELEASED POLARIS run that BEATS BOTH ChatGPT and Gemini on §-1.1 line-by-line
faithfulness, on ALL 5 golden DR questions. Canonical loop: docs/beat_both_system_loop.md.

Per-question status:
{status_block}{waiting_note}

Before stopping, confirm you are doing the loop, not drifting:
  PHASE 0 (no-guess gate) — for ANY new issue, FIRST research the LATEST/BEST/TOP solutions on GitHub
    + the internet (WebSearch/WebFetch), deeply review those, THEN review OUR source code line-by-line,
    THEN review OUR output content line-by-line (report + claim_audit + fetched spans), THEN design the
    fix. Heavy/safety/release-blocking → empirically bake off candidates on a real labeled set; evidence
    decides. A hand-rolled options list with no research + no line-by-line read is banned.
  PHASE 1 — run the WHOLE SYSTEM (not a component); it must RELEASE (not hold).
  PHASE 2 — §-1.1 line-by-line audit of the WHOLE report vs fetched spans, Claude + Codex independent.
  PHASE 3 — beat-both: score POLARIS + ChatGPT + Gemini claim-by-claim, same scorer, head to head.
  PHASE 4 — if held/lost, diagnose the SYSTEM cause (retrieval/generation/coverage, not just the
    verifier) -> Phase 0 -> fix -> offline smoke -> Codex gate -> fresh whole-system re-run.
  PHASE 5 — repeat for all 5 questions; a fix must not regress the others.
  CROSS-CUTTING (every phase, IN PARALLEL, NOT after) — GitHub: issue FIRST, bot/<issue> branch,
    5-artifact triple, Codex-only gate, PR queued for operator merge, CLOSE the issue on merge, post
    findings as comments. DOCS: update architecture/file_directory/runbook/session_log/
    iteration_trajectory/beat_both_status + memory IN THE SAME CYCLE as the code. HYGIENE: snake_case,
    right dir, explicit `git add` paths + `git show --stat` verify, gitignore artifacts/secrets, one
    heavy job at a time, kill orphan codex/python. (docs/beat_both_system_loop.md "CROSS-CUTTING".)

Legitimate stops ONLY: all 5 beat_both, an active state['halt'], the operator says stop, or you set
state/beat_both_status.json.waiting_on and scheduled a wakeup. Otherwise: keep going — take the next
loop action now."""


def main() -> int:
    # CWD guard: a stray global registration must no-op outside POLARIS.
    try:
        cwd = Path(os.getcwd()).resolve()
        if POLARIS_ROOT not in (cwd, *cwd.parents) and cwd not in (POLARIS_ROOT, *POLARIS_ROOT.parents):
            _allow()
    except Exception:
        pass

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    # Infinite-loop guard: if this turn IS a stop-hook continuation, allow the stop (reminded already).
    if isinstance(event, dict) and event.get("stop_hook_active"):
        _allow()

    status = _read_status()

    # A real, active halt fired (explicit status['halt']) -> allow stop (the loop legitimately ends).
    if _active_halt(status):
        _allow()

    # Mission complete -> allow stop.
    if isinstance(status, dict) and status.get("all_five_beat_both") is True:
        _allow()

    # Otherwise: re-inject the loop. (Even when waiting_on is set, remind once — the model then
    # confirms a wakeup is scheduled and the continuation stop is allowed via stop_hook_active.)
    _block(_build_reminder(status))
    return 0


if __name__ == "__main__":
    main()
