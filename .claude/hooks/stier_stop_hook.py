#!/usr/bin/env python3
"""POLARIS S-tier-experience Stop hook (I-ux-001 / GitHub #872).

Blocks premature stop while the S-tier UI/UX initiative is open, re-injecting
the operator's 2026-05-24 standing directive. Gates on OBJECTIVE state
(GitHub issue #872 OPEN), never Claude's self-report.

Per operator directive 2026-05-24 ("Codex decides, don't ask me, don't
checkpoint/report/pause, keep executing until Codex (uncapped) approves and the
S-tier experience is built; on context-fill update handover + auto-compact +
continue").

Best practice (Claude Code hooks docs, verified 2026-05-24 via claude-code-guide):
- Stop hook blocks with TOP-LEVEL {"decision":"block","reason":...}. Do NOT wrap
  in hookSpecificOutput — Claude Code drops a Stop emission with that wrapper as
  schema-invalid, so the block silently fails to fire.
- exit 0 in all paths.
- honour stop_hook_active (infinite-loop guard).
- progress-based stuck counter (reset on a NEW HEAD commit), not call-count
  (idempotency best practice: derive from state, not from invocation count).
- escape valves: halt marker / gh failure / issue closed / stuck-cap → ALLOW
  stop so the operator is never structurally trapped.
- project-scoped + CWD guard (never global — prior global-hook incident).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("C:/POLARIS")
REPO = "aldrinor/polaris"
UMBRELLA_ISSUE = 872
STATE = ROOT / "state" / "stier_stop_state.json"
DIRECTIVE = ROOT / ".claude" / "hooks" / "stier_directive.txt"
MAX_STUCK = 60  # consecutive turn-ends with NO new commit → allow stop (investigate)


def _allow() -> None:
    print(json.dumps({}))
    sys.exit(0)


def _cwd_is_polaris() -> bool:
    try:
        cwd = Path.cwd().resolve()
        return cwd == ROOT.resolve() or ROOT.resolve() in cwd.parents
    except Exception:
        return False


def _head_sha() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _issue_open(n: int):
    """True/False if issue n is OPEN; None on gh failure (→ don't trap)."""
    try:
        r = subprocess.run(
            ["gh", "issue", "view", str(n), "--repo", REPO,
             "--json", "state", "-q", ".state"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return None
        return r.stdout.strip().upper() == "OPEN"
    except Exception:
        return None


def _halt_present() -> bool:
    try:
        return any(ROOT.glob("state/stier_halt_*.md"))
    except Exception:
        return False


def _read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"blocks": 0, "last_sha": ""}


def _write_state(blocks: int, last_sha: str) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps({"blocks": blocks, "last_sha": last_sha}),
            encoding="utf-8",
        )
    except Exception:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    if data.get("stop_hook_active"):  # already forced-continue → never re-block
        sys.exit(0)
    if not _cwd_is_polaris():
        _allow()
    if _halt_present():               # documented genuine blocker → allow
        _write_state(0, _head_sha())
        _allow()

    open_state = _issue_open(UMBRELLA_ISSUE)
    if open_state is None:            # gh failed → don't trap on infra
        _allow()
    if not open_state:                # initiative complete → allow
        _write_state(0, _head_sha())
        _allow()

    # progress-based stuck counter: a new HEAD commit since last block = progress
    st = _read_state()
    sha = _head_sha()
    blocks = 0 if (sha and sha != st.get("last_sha", "")) else st.get("blocks", 0) + 1
    _write_state(blocks, sha or st.get("last_sha", ""))
    if blocks >= MAX_STUCK:           # no commit in N turn-ends → allow (investigate)
        _write_state(0, sha)
        _allow()

    try:
        reason = DIRECTIVE.read_text(encoding="utf-8")
    except Exception:
        reason = (
            "I-ux-001 (#872) NOT complete — DO NOT STOP. Continue the S-tier "
            "UI/UX initiative: Codex decides (uncapped), don't ask the operator, "
            "don't checkpoint. To stop for a genuine blocker write "
            "state/stier_halt_<reason>.md first."
        )
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
