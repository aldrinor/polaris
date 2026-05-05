#!/usr/bin/env python3
"""scripts/hooks/session_start_check.py

Per polaris-restart Plan §9.6a — Persisted session-start hook (CRITICAL).
Cross-platform (Python) sibling to session_start_check.sh.

Fires BEFORE any Bash/Edit/Write/MultiEdit tool call. Behavior (iter 7 PRB6-P1-001 fix):
- ALWAYS verifies BOTH `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md` SHAs against `state/polaris_restart/charter_sha_pin.txt` on EVERY tool call. No stamp-based bypass.
- If both SHAs match pins: refresh stamp and allow tool calls.
- If either-file mismatch / pin missing / file missing: deny tool call with explicit user-side reconciliation reason.
- The stamp is informational only — records last successful check time + observed SHAs. NOT a bypass token.
- Future requirement: §10 boot ritual (read CHARTER+PLAN, state active issue) is NOT enforced by this hook directly — it relies on the assistant reading CLAUDE.md §10 and the `state/active_issue.json` file, both of which are reachable via Read tool. This hook is the SHA-pin gate, not the full-ritual gate.

Created 2026-05-05 night (PR-B iter 2 fix for CLEAN-PR-B-P1-004 Windows compat).

The bash variant fails on Windows native bash with `signal pipe Win32 error 5`.
This Python variant runs cross-platform (Windows Python, Linux Python, macOS Python).

CODEOWNERS-protected per §10.0. Claude cannot edit this file post-PR-D.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import sys


def _utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_pins(pin_file: pathlib.Path) -> dict[str, str]:
    """Parse pin file → {<basename>: <sha>}. Empty if file missing/malformed."""
    pins: dict[str, str] = {}
    if not pin_file.exists():
        return pins
    for raw_line in pin_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 40:
            pins[parts[1].split("/")[-1]] = parts[0]
    return pins


def _live_sha(file_path: pathlib.Path) -> str:
    if not file_path.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(file_path.parent), "hash-object", file_path.name],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _emit_deny(reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(payload))


def main() -> int:
    repo_root = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    today = datetime.date.today().strftime("%Y%m%d")
    stamp = repo_root / "state" / "polaris_restart" / f"session_started_{today}.stamp"

    # iter 7 PRB6-P1-001 fix: ALWAYS verify SHAs on every tool call.
    # Earlier the hook auto-skipped if stamp existed → if CHARTER/PLAN changed
    # mid-day, the cage would not detect drift. Now verify every call; stamp is
    # informational only (records last successful check time + observed SHAs).
    pin_file = repo_root / "state" / "polaris_restart" / "charter_sha_pin.txt"
    pins = _read_pins(pin_file)

    # Sister repo at C:\polaris-controls\ (Windows) or sibling on Unix
    sister_candidates = [
        pathlib.Path("C:/polaris-controls"),
        repo_root.parent / "polaris-controls",
    ]
    sister_root = next((p for p in sister_candidates if p.exists()), sister_candidates[0])

    drift = []
    live_shas = {}
    for fname in ("CHARTER.md", "PLAN.md"):
        live = _live_sha(sister_root / fname)
        live_shas[fname] = live
        pin = pins.get(fname, "")
        if not live or not pin or live != pin:
            drift.append(f"{fname} pin={pin or 'MISSING'} live={live or 'UNREADABLE'}")

    if drift:
        _emit_deny(
            "SHA pin drift detected: " + "; ".join(drift) + ". "
            "Halt per Plan §10. Resolution requires user-side reconciliation: "
            "user reads polaris-controls/CHARTER.md + PLAN.md, decides whether "
            "the live SHAs are the new canonical, then signs a commit updating "
            "state/polaris_restart/charter_sha_pin.txt. Hook will allow tool calls "
            "again on next invocation after reconciliation. Claude must NOT write "
            "the stamp file directly."
        )
        return 0

    active_file = repo_root / "state" / "active_issue.json"
    active = active_file.read_text(encoding="utf-8") if active_file.exists() else "{}"

    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        f"session_started: {_utc_iso()}\n"
        f"active_issue: {active}\n"
        f"charter_sha: {live_shas.get('CHARTER.md', '')}\n"
        f"plan_sha: {live_shas.get('PLAN.md', '')}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
