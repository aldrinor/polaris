#!/usr/bin/env python3
"""POLARIS UserPromptSubmit hook — injects the polaris_task_cycle reminder.

Operator decision #6 (2026-05-28 ultracode session): a RELIABLE mechanism
that reminds Claude to follow the standing task-execution loop EVERY time the
operator asks for a task. The failure mode this prevents is the 4-role drift
("16 smokes ran on a 2-LLM stub, not POLARIS") — Claude drifting from the loop
under context pressure. A hook is harness-enforced (the harness runs it on every
prompt), so it does not depend on Claude's in-context memory the way a CLAUDE.md
line or a SessionStart-only hook does.

Contract (https://code.claude.com/docs/en/hooks):
  - Reads the UserPromptSubmit event JSON from stdin.
  - Emits hookSpecificOutput.additionalContext to inject the reminder into the
    model's context for THIS prompt. (Documented in stop_hook_v3.py:304 — the
    additionalContext field is the UserPromptSubmit injection channel.)
  - Exits 0 in all paths. Never blocks the prompt; this is a nudge, not a gate.

Lessons baked in:
  - stop_hook_must_be_project_scoped: this hook is registered in the PROJECT
    .claude/settings.json (committed, repo-local), NEVER ~/.claude/settings.json,
    AND carries a CWD guard in the body so a stray global registration still
    no-ops outside POLARIS.
  - Codex iter-1 fix (f): Gate-A uses verify_lock CONSISTENCY mode
    (verify_lock_against_code, i.e. does the lock match the code?), NOT the full
    report() propagation gate — report() hardcodes tests_pass=False and so can
    never exit 0 today. The reminder text says "verify_lock --consistency",
    not "verify_lock exit 0".
  - Codex iter-1 fix (c): the verdict is parsed from the WRITTEN verdict FILE,
    deterministically; never trust an agent-reported verdict. The reminder says so.
  - Codex iter-1 fix (g): Gate-A is the PRE-RENTAL gate (proves wiring +
    connectivity), not full functionality.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

POLARIS_ROOT = Path("C:/POLARIS").resolve()
ACTIVE_ISSUE = POLARIS_ROOT / "state" / "active_issue.json"

# The reminder is intentionally short (one screen) so it costs few tokens per
# prompt and stays salient. It points to the canonical loop + the two hard
# pre-spend invariants. Detail lives in CLAUDE.md §3.0.1 + the workflow file;
# this is the per-prompt re-injection of the SPEC that falls out of the window.
REMINDER = """\
[polaris_task_cycle — STANDING WORKFLOW, re-injected per prompt by hook]
Every task = a GitHub-Issue cycle. Follow this loop, in order, EVERY time:

  BOOT -> BRIEF -> codex-gate(brief) -> BUILD -> SMOKE -> codex-gate(diff) -> CLOSE -> NEXT

Non-negotiable invariants (these are what the 4-role drift violated):
  1. BOOT first: verify_lock --consistency (does lock match code?) + read
     state/active_issue.json. Resume the in_progress issue ONLY; no scope jump.
  2. GATE-A (pre-rental gate: wiring + connectivity, NOT full functionality)
     MUST pass BEFORE any GPU/Cohere/full-sweep spend. Gate-A = pytest
     (serialized, no parallel runs — §8.4) + verify_lock consistency +
     preflight(offline=True) + per-role contract fixtures (Sentinel polarity
     yes=UNGROUNDED is LETHAL; Judge 5-enum; Mirror two-pass) + 3 cheap real
     probes (Serper/S2/DeepSeek). Gate-B (live per-role) only after GPU rented.
  3. Codex is the ONLY review gate (§3.0). Two gates per issue: brief + diff,
     each 5-cap (§8.3.1). Parse the verdict from the WRITTEN verdict file's last
     'verdict:' line — NEVER trust an agent-reported verdict. Schema §8.3.9.
  4. Visual review (web/** changes) via scripts/visual_review_gate.py against
     .codex/visual_audit_rubric.md — NOT ad-hoc codex -i.
  5. Claude does NOT merge. Codex merges after its own APPROVE (D1 auto-admin
     merger). Live testing / auto-merge enabled ONLY after everything is fixed.
  6. Between merge and next branch: ZERO prose (§8.2). Stop is Codex's call,
     not Claude's (§8.3.10).
  7. ONE name: "Claude Codex Workflow" (no sub-labels). ALWAYS run it via the
     Anthropic Workflow FUNCTION, NEVER inline (operator reaffirmed 2026-06-09).
  8. Prove-first (the standard content of every run): write the Claims Ledger
     (every claim -> file:line -> live/staged/roadmap/removed) BEFORE building;
     build from the ledger not memory; batch-fix the whole class (sibling-grep);
     self-run the rubric; hand Codex an EVIDENCE PACK (changes + ledger + smoke
     command/output/artifact) to VERIFY not hunt; answer each finding
     id -> fixed line -> sibling-grep proof.

Full spec: CLAUDE.md §3.0.1 + .claude/workflows/polaris_task_cycle.md.

NAMED TRIGGER (operator, 2026-05-29): "Claude Codex Workflow" (or "with Claude Codex
Workflow") is the operator's ONE invocation phrase for THIS loop (no sub-labels). When the
operator says it — and equivalently the keywords 'exec:' / 'task:' — ALWAYS RUN this loop
via the Anthropic Workflow FUNCTION, NEVER inline (operator reaffirmed 2026-06-09) — the
background workflow engine that spawns the BRIEF / BUILD / SMOKE / Codex-gate agents in
phases, with Codex as the ONLY gate. Prove-first is the standard content of every run:
Claims Ledger (every claim -> file:line -> live/staged) BEFORE building; self-run the
rubric; hand Codex an EVIDENCE PACK to VERIFY not hunt; batch-fix the whole class; answer
findings id -> line -> sibling-grep. Operator is BLIND: ANNOUNCE each workflow launch in one
plain spoken line as it fires, and read the key result inline — do NOT rely on the
/workflows panel (a screen reader cannot see it)."""


# Case-insensitive trigger phrases that mean "run the loop via the Workflow function".
_TRIGGER_PHRASES = ("claude codex workflow", "exec:", "task:")


def _is_polaris_session() -> bool:
    """CWD guard (stop_hook_must_be_project_scoped lesson): only fire inside
    POLARIS, even if this hook is ever mis-registered globally."""
    try:
        Path(os.getcwd()).resolve().relative_to(POLARIS_ROOT)
        return True
    except (ValueError, OSError):
        return False


def _active_issue_line() -> str:
    """Append the current in_progress issue so the reminder is grounded, not
    generic. Fail-soft: a missing/garbled file must never break the prompt."""
    try:
        data = json.loads(ACTIVE_ISSUE.read_text(encoding="utf-8"))
        iid = data.get("active_issue_id")
        step = data.get("current_step", "")
        if iid:
            step_short = (step[:160] + "…") if len(step) > 160 else step
            return f"\nACTIVE ISSUE: {iid} — current_step: {step_short}"
    except Exception:
        pass
    return ""


def _trigger_line(raw_event: str) -> str:
    """If the operator's prompt contains a named trigger ('Claude Codex Workflow' /
    'exec:' / 'task:'), emit an emphatic activation line so the binding is harness-enforced,
    not just remembered. Fail-soft: any parse problem yields no line."""
    try:
        prompt = ""
        try:
            prompt = (json.loads(raw_event) or {}).get("prompt", "") or ""
        except Exception:
            prompt = raw_event or ""
        low = prompt.lower()
        if any(phrase in low for phrase in _TRIGGER_PHRASES):
            return (
                "\n\n>>> NAMED TRIGGER DETECTED in this prompt ('Claude Codex Workflow' / "
                "'exec:' / 'task:'): run the polaris_task_cycle loop via the Anthropic Workflow "
                "FUNCTION (Codex the only gate), and ANNOUNCE the launch + result in plain spoken "
                "lines (operator is blind; the /workflows panel is not accessible)."
            )
    except Exception:
        pass
    return ""


def main() -> int:
    # Read the UserPromptSubmit event (we use the prompt text for trigger detection).
    try:
        raw_event = sys.stdin.read()
    except Exception:
        raw_event = ""

    if not _is_polaris_session():
        # Outside POLARIS: emit nothing, do not inject. No-op.
        return 0

    context = REMINDER + _active_issue_line() + _trigger_line(raw_event)
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    # Always exit 0 — a reminder hook must never block the operator's prompt.
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
