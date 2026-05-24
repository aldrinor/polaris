#!/usr/bin/env python3
"""POLARIS SessionStart hook — re-inject the I-ux-001 standing directive on
startup / resume / compact / clear, so the autonomous S-tier UI/UX initiative
survives context compaction.

Per operator directive 2026-05-24 ("when context windows almost hit 100%, just
update handover, let it auto compact, start a new session, then continue").
SessionStart fires after auto-compaction with source="compact" and its
additionalContext lands in the post-compaction context window — this is the
documented mechanism for surviving compaction (Claude Code hooks docs, verified
2026-05-24 via claude-code-guide).

Output schema: SessionStart uses the hookSpecificOutput wrapper with
additionalContext (≤10,000 chars). The directive file is kept well under that.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path("C:/POLARIS")
DIRECTIVE = ROOT / ".claude" / "hooks" / "stier_directive.txt"
MAX_CHARS = 9500  # SessionStart additionalContext hard limit is 10,000


def _cwd_is_polaris() -> bool:
    try:
        cwd = Path(os.getcwd()).resolve()
        return cwd == ROOT.resolve() or ROOT.resolve() in cwd.parents
    except Exception:
        return False


def main() -> None:
    if not _cwd_is_polaris():
        sys.exit(0)
    try:
        text = DIRECTIVE.read_text(encoding="utf-8")[:MAX_CHARS]
    except Exception:
        sys.exit(0)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
