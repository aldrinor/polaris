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
    """Detect git commit invocations including common variants.

    Per Codex round-1 P0-3 fix: correctly skip option VALUES that follow flags
    expecting an argument (e.g., `git -c key=val commit`, `git --git-dir DIR commit`).
    Without this, `git -c core.hooksPath=/tmp/empty commit` was parsed as non-commit
    AND simultaneously disabled .git/hooks/pre-commit — full Claude-side bypass.
    """
    if not command:
        return False
    cmd_lower = command.strip().lower()
    parts = cmd_lower.split()

    # Flags that take a value as the NEXT token (must skip both the flag and its value)
    FLAGS_WITH_SEPARATE_ARG = {
        "-c", "-c=",  # config override (rare separate form)
        "--git-dir", "--work-tree", "--namespace", "--super-prefix",
        "--exec-path", "--config-env",
        "-c=",  # noop dup
    }

    for i, p in enumerate(parts):
        # Locate the git invocation
        if not (p == "git" or p.endswith("/git") or p.endswith("\\git") or p.endswith(".exe")):
            continue
        if p.endswith(".exe") and "git" not in p:
            continue

        # Now scan tokens after the git binary, skipping flags and their values
        j = i + 1
        while j < len(parts):
            tok = parts[j]
            if tok.startswith("-"):
                # Inline form (--key=value or -c=value): skip just this token
                if "=" in tok:
                    j += 1
                    continue
                # Separate-arg form (-c VALUE): skip this AND the next token
                if tok in FLAGS_WITH_SEPARATE_ARG:
                    j += 2
                    continue
                # Plain flag (no value): skip just this token
                j += 1
                continue
            # First non-flag token is the subcommand
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
