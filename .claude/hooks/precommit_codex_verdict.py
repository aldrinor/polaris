#!/usr/bin/env python3
"""POLARIS PreToolUse hook — intercepts Bash `git commit` invocations from Claude.

Per Plan v13 §C (user-approved 2026-05-02). Wired in .claude/settings.local.json
as a PreToolUse matcher on Bash with command pattern `git commit *`.

Defense-in-depth alongside .git/hooks/pre-commit (which fires on every git
commit regardless of caller). This hook fires ONLY for Claude-initiated
Bash commits in this project; the git-side hook fires for ALL commits.

NO PASS-THROUGH BRANCHES per Plan v13 §C ("the current 'fall through if not
in autoloop' branch is the bypass I exploited 153 times today" — sister project).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

POLARIS_ROOT = Path("C:/POLARIS").resolve()
VERDICT_GATE = POLARIS_ROOT / "scripts" / "autoloop" / "verdict_gate.py"


def _is_polaris_session() -> bool:
    try:
        cwd = Path(os.getcwd()).resolve()
        cwd.relative_to(POLARIS_ROOT)
        return True
    except (ValueError, OSError):
        return False


def _is_git_commit(command: str) -> bool:
    """Detect git commit invocations including common variants."""
    if not command:
        return False
    cmd_lower = command.strip().lower()
    # Match "git commit", "git -c ... commit", "/usr/bin/git commit", etc.
    # But NOT "git status" or "git commit-tree" (plumbing)
    parts = cmd_lower.split()
    for i, p in enumerate(parts):
        if p.endswith("git") or p == "git":
            # next non-flag token should be "commit"
            for j in range(i + 1, len(parts)):
                tok = parts[j]
                if tok.startswith("-"):
                    # skip flags like "-c" "key=value"
                    if tok in ("-c", "--git-dir", "--work-tree"):
                        # next token is the value, also skip
                        continue
                    if "=" in tok:
                        continue
                    continue
                return tok == "commit"
            return False
    return False


def main() -> None:
    if not _is_polaris_session():
        sys.exit(0)

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)  # malformed input → never block

    tool_input = payload.get("tool_input", {}) or {}
    command = tool_input.get("command", "") or ""

    if not _is_git_commit(command):
        sys.exit(0)  # not a git commit, allow

    # Run shared verdict gate
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, str(VERDICT_GATE)],
            cwd=str(POLARIS_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
    except Exception as e:
        # Gate script unavailable → BLOCK (fail-loud, never fail-open per Plan v13 §C)
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"verdict_gate.py invocation failed: {e}. Per Plan v13 §C, "
                    f"NO PASS-THROUGH BRANCHES — gate must run successfully or commit blocks."
                ),
            }
        }
        sys.stdout.write(json.dumps(out))
        sys.exit(0)

    if result.returncode == 0:
        sys.exit(0)  # gate passed, allow

    # Gate blocked
    reason_parts = []
    if result.stderr:
        reason_parts.append(result.stderr.strip())
    if result.stdout:
        reason_parts.append(result.stdout.strip())
    reason = "\n".join(reason_parts) or "verdict_gate.py exited non-zero with no output"

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason[:2000],  # cap to avoid runaway
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
