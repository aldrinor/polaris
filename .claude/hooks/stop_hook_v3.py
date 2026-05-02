#!/usr/bin/env python3
"""POLARIS Stop hook v3 — plan-aware, reads from git HEAD (not working tree).

Per Plan v13 §B (user-approved 2026-05-02). Replaces polaris_keep_going.py
which read derived todo_list.md and was vulnerable to Claude self-editing
the file the hook reads (sister-project Failure S1).

Inputs (READ-ONLY, all from `git show HEAD:` — Claude cannot tamper with
HEAD without a precommit-gated commit):
  1. docs/canonical_pin.txt — verifies canonical files haven't drifted vs working tree
  2. docs/carney_delivery_plan_v6_2.md — the canonical plan
  3. docs/task_acceptance_matrix.yaml — per-task GREEN criteria + user_action_blocked + substrate_prep
  4. docs/blockers.md — canonical user-action gates
  5. outputs/audits/verdicts/<task_id>/iter_<N>.json — Codex APPROVE/REQUEST_CHANGES (Claude has zero write per §C)

Decision logic (per Plan v13 §B):
  - Verify canonical pin SHA matches working tree SHA → mismatch = HARD STOP (canonical drifted)
  - For each task in plan-canonical sequence:
      if verdict APPROVE → skip
      if user_action_blocked AND has_substrate_prep_pending → block stop, point to prep
      if user_action_blocked AND no_substrate_prep_pending → next task
      if next_in_sequence AND no_verdict → block stop, point to task
  - Allow stop ONLY when every task APPROVE'd OR every remaining is fully user-action with no prep

Per https://code.claude.com/docs/en/hooks the script:
  - Reads JSON from stdin
  - Honours stop_hook_active to prevent infinite loops
  - Exits 0 in all paths; emits decision JSON to stdout when blocking
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

POLARIS_ROOT = Path("C:/POLARIS").resolve()
KILL_SWITCH = POLARIS_ROOT / "state" / "autoloop_active"
BLOCK_COUNT_FILE = POLARIS_ROOT / "state" / "autoloop_block_count_v3"
MAX_CONSECUTIVE_BLOCKS = 50

# Canonical files pinned in canonical_pin.txt
CANONICAL_FILES = [
    "docs/carney_delivery_plan_v6_2.md",
    "architecture.md",
    "docs/blockers.md",
    "docs/task_acceptance_matrix.yaml",
    "docs/agent_architecture.md",
    "docs/substrate_audit_2026-05-01.md",
    ".codex/codex_red_team_checklist.md",
    ".codex/REVIEW_BRIEF_FORMAT_v2.md",
    ".codex/AUDIT_CYCLE_PROTOCOL_v2.md",
    "CLAUDE.md",
]


def _is_polaris_session() -> bool:
    """Defense-in-depth CWD guard — only fire when CWD is POLARIS or subdir."""
    try:
        cwd = Path(os.getcwd()).resolve()
        cwd.relative_to(POLARIS_ROOT)
        return True
    except (ValueError, OSError):
        return False


def _read_count() -> int:
    try:
        return int(BLOCK_COUNT_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _write_count(n: int) -> None:
    try:
        BLOCK_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
        BLOCK_COUNT_FILE.write_text(str(n), encoding="utf-8")
    except Exception:
        pass


def _git_show_head(path: str) -> str | None:
    """Read file content as committed at HEAD. Returns None if not in HEAD."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=str(POLARIS_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


def _file_sha256(path: str) -> str | None:
    """SHA256 of working-tree file (used to detect canonical drift vs HEAD)."""
    try:
        with open(POLARIS_ROOT / path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _git_show_head_sha256(path: str) -> str | None:
    """SHA256 of file as committed at HEAD."""
    content = _git_show_head(path)
    if content is None:
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _verify_canonical_pin() -> tuple[bool, str]:
    """Verify each canonical file's working-tree SHA matches HEAD SHA matches pin file.

    Returns (ok, message). On mismatch, message names the offending file.
    """
    pin_text = _git_show_head("docs/canonical_pin.txt")
    if pin_text is None:
        return False, "docs/canonical_pin.txt missing from HEAD"

    expected = {}
    for line in pin_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        expected[parts[1].strip()] = parts[0].strip()

    for f in CANONICAL_FILES:
        exp = expected.get(f)
        if not exp:
            return False, f"canonical_pin.txt missing entry for {f}"
        actual_head = _git_show_head_sha256(f)
        if actual_head != exp:
            return False, f"HEAD SHA mismatch for {f}: pin says {exp[:12]}, HEAD has {(actual_head or 'MISSING')[:12]}"
        # Also verify working tree matches HEAD (so working-tree edits between
        # commits don't cause a stale read of canonical content during execution)
        actual_wt = _file_sha256(f)
        if actual_wt != actual_head:
            return False, f"working-tree drift for {f}: HEAD has {actual_head[:12]}, working-tree has {(actual_wt or 'MISSING')[:12]}"

    return True, "canonical pin verified"


def _parse_matrix_tasks_from_head() -> list[dict]:
    """Parse task_acceptance_matrix.yaml from HEAD into ordered task list.

    Lightweight YAML parser — good enough for our matrix structure (no
    external dep). Returns list of dicts with: task_id, user_action,
    substrate_prep (list), green_criteria, blocking_consequence.
    """
    text = _git_show_head("docs/task_acceptance_matrix.yaml")
    if text is None:
        return []

    # Use PyYAML if available, else minimal fallback
    try:
        import yaml
        try:
            parsed = yaml.safe_load(text)
        except Exception:
            return []
    except ImportError:
        # Minimal parser fallback: just extract task IDs in order
        # Lines like "  task_0_5:" → task_id "0.5"
        tasks = []
        import re
        for m in re.finditer(r"^\s{2,4}(task_[\w_]+):\s*$", text, re.MULTILINE):
            task_id = m.group(1).removeprefix("task_").replace("_", ".")
            tasks.append({"task_id": task_id, "user_action": False, "substrate_prep": []})
        return tasks

    # Walk parsed structure
    tasks = []
    if not isinstance(parsed, dict):
        return tasks

    for phase_key in sorted(parsed.keys()):
        if not phase_key.startswith("phase_"):
            continue
        phase_val = parsed[phase_key]
        if not isinstance(phase_val, dict):
            continue
        for task_key, task_val in phase_val.items():
            if not isinstance(task_val, dict):
                continue
            task_id = task_key.removeprefix("task_").replace("_", ".")
            tasks.append({
                "task_id": task_id,
                "user_action": bool(task_val.get("user_action", False)),
                "substrate_prep": task_val.get("substrate_prep", []) or [],
                "blocking_consequence": task_val.get("blocking_consequence", ""),
            })
    return tasks


def _verdict_state(task_id: str) -> str:
    """Return 'APPROVE', 'REQUEST_CHANGES', 'BLOCKED', or 'NONE' for a task."""
    verdict_dir = POLARIS_ROOT / "outputs" / "audits" / "verdicts" / task_id
    if not verdict_dir.is_dir():
        return "NONE"
    iters = sorted(verdict_dir.glob("iter_*.json"))
    if not iters:
        return "NONE"
    try:
        latest = json.loads(iters[-1].read_text(encoding="utf-8"))
        return latest.get("verdict", "NONE")
    except Exception:
        return "NONE"


def _has_pending_prep(task: dict) -> bool:
    """Check if a user-blocked task has any substrate_prep sub-task without APPROVE."""
    for prep in task.get("substrate_prep", []) or []:
        prep_id = prep.get("id") if isinstance(prep, dict) else None
        if not prep_id:
            continue
        if _verdict_state(prep_id) != "APPROVE":
            return True
    return False


def _next_actionable_task(tasks: list[dict]) -> tuple[dict | None, str | None]:
    """Walk tasks in canonical sequence; return (next_task, prep_id_if_any)."""
    for task in tasks:
        verdict = _verdict_state(task["task_id"])
        if verdict == "APPROVE":
            continue
        if task["user_action"]:
            if _has_pending_prep(task):
                # find first non-APPROVE prep
                for prep in task["substrate_prep"]:
                    prep_id = prep.get("id") if isinstance(prep, dict) else None
                    if prep_id and _verdict_state(prep_id) != "APPROVE":
                        return task, prep_id
            continue  # user-blocked, no prep → skip
        # not user-action, not APPROVE'd → this is the next task
        return task, None
    return None, None


def main() -> None:
    if not _is_polaris_session():
        sys.exit(0)

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)

    # Guard 1: prevent infinite loop with ourselves
    if payload.get("stop_hook_active"):
        sys.exit(0)

    # Guard 2: kill switch off → loop disabled
    if not KILL_SWITCH.exists():
        _write_count(0)
        sys.exit(0)

    # Guard 3: max consecutive blocks safety net
    count = _read_count()
    if count >= MAX_CONSECUTIVE_BLOCKS:
        _write_count(0)
        sys.exit(0)

    # Step A: verify canonical pin (HARD STOP if drift)
    pin_ok, pin_msg = _verify_canonical_pin()
    if not pin_ok:
        _write_count(count + 1)
        reason = (
            f"POLARIS HARD STOP — canonical pin drift detected: {pin_msg}. "
            f"Per Plan v13 §A: any pinned-file change requires user-signed "
            f"reconciliation commit + new pin. Halt loop, investigate before resume."
        )
        sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
        sys.stdout.flush()
        sys.exit(0)

    # Step B: parse matrix from HEAD, find next actionable
    tasks = _parse_matrix_tasks_from_head()
    if not tasks:
        # Matrix unparseable (likely Phase 1-5 not yet filled out per §K Step 0b).
        # Don't block stop — let user know via heartbeat.
        _write_count(0)
        sys.exit(0)

    next_task, prep_id = _next_actionable_task(tasks)
    if next_task is None:
        # All tasks APPROVE'd, nothing left
        _write_count(0)
        sys.exit(0)

    # Block stop, point at next actionable
    _write_count(count + 1)
    target = prep_id or next_task["task_id"]
    if prep_id:
        msg = f"prep sub-task {prep_id} (parent {next_task['task_id']} is user-action-blocked)"
    else:
        msg = f"task {next_task['task_id']}"

    reason = (
        f"POLARIS autoloop active — next actionable: {msg}. "
        f"Per Plan v13 §E strict canonical-plan sequence (no jumping). "
        f"Read docs/task_acceptance_matrix.yaml for green-criteria; "
        f"build manifest at outputs/audits/manifests/{target}.json; "
        f"orchestrator will invoke `codex exec` for verdict gate. "
        f"(Block {count + 1}/{MAX_CONSECUTIVE_BLOCKS}. To stop loop: "
        f"delete state/autoloop_active.)"
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
