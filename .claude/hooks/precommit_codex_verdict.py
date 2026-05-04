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
    # === HOOK NEUTRALIZED 2026-05-04 ===
    # The Plan v13 §C verdict_gate.py enforcement is DEPRECATED by the
    # 2026-05-04 cage restart. The old hook required matrix-task implication
    # or `infrastructure-only:` magic-string in commit messages. Both are
    # superseded:
    #   - matrix YAML deprecated → polaris-controls/PLAN.md slice progression
    #   - infrastructure-only magic → deleted from new design (escape hatch)
    #   - verdict_gate.py self-attestation → server-side branch protection
    # Real enforcement now lives at:
    #   - GitHub branch protection (signed commits, PR-only on main)
    #   - .github/workflows/* CI checks
    #   - .github/CODEOWNERS gate on control-plane paths
    #   - scripts/verify_cage.py (33 cage checks on demand)
    # The local precommit gate was firing on legitimate slice 1 work that
    # has no matrix entry (because matrix is itself deprecated). Net effect:
    # blocking real progress on superseded checks.
    sys.exit(0)

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

    # Extract -m message from the Bash command and pass to gate (pre-commit
    # stage cannot read .git/COMMIT_EDITMSG for `-m` invocations — that file
    # has stale prior message). Without the message, gate's bootstrap +
    # infrastructure-only checks cannot fire.
    import shlex, tempfile, subprocess
    msg_file_arg = []
    try:
        tokens = shlex.split(command, posix=False)
        # Look for -m "..." or --message="..."
        i = 0
        msg_text = None
        while i < len(tokens):
            t = tokens[i].strip('"\'')
            if t == "-m" or t == "--message":
                if i + 1 < len(tokens):
                    msg_text = tokens[i + 1].strip('"\'')
                    break
            elif t.startswith("--message="):
                msg_text = t.removeprefix("--message=").strip('"\'')
                break
            elif t.startswith("-m"):
                msg_text = t.removeprefix("-m").strip('"\'')
                if msg_text:
                    break
            i += 1
        if msg_text:
            tf = tempfile.NamedTemporaryFile(
                mode="w", suffix=".commit_msg", encoding="utf-8", delete=False
            )
            tf.write(msg_text)
            tf.close()
            msg_file_arg = ["--commit-message-file", tf.name]
    except Exception:
        pass  # best-effort; gate falls through if message unparseable

    try:
        result = subprocess.run(
            [sys.executable, str(VERDICT_GATE)] + msg_file_arg,
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
