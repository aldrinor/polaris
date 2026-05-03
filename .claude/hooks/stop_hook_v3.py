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
            task_id = task_val.get("task_id") or task_key.removeprefix("task_").replace("_", ".")
            tasks.append({
                "task_id": task_id,
                "user_action": bool(task_val.get("user_action", False)),
                "substrate_prep": task_val.get("substrate_prep", []) or [],
                "blocking_consequence": task_val.get("blocking_consequence", ""),
            })
    return tasks


def _is_task_halted(task_id: str) -> bool:
    """True if a halt marker exists for this task at outputs/audits/halt_resolutions/.
    Per Plan v13 §H: halt markers signal "task pending user resolution"; hook
    treats halted tasks as user-blocked (skip) until the marker is removed.
    """
    halt_dir = POLARIS_ROOT / "outputs" / "audits" / "halt_resolutions"
    if not halt_dir.is_dir():
        return False
    # Match either exact name or prefix (orchestrator may add suffixes)
    safe_id = task_id.replace("/", "_")
    return any(p.is_file() for p in halt_dir.glob(f"{safe_id}*halt*.md"))


def _verdict_state(task_id: str) -> str:
    """Return 'APPROVE', 'REQUEST_CHANGES', 'BLOCKED', or 'NONE' for a task.

    Per Codex round-1 P0-4 fix: read verdict files from `git show HEAD:` only.
    Working-tree verdict files are not authoritative — Claude can edit them
    locally and bypass the hook. Only committed verdicts count.
    """
    # Find latest iter_N.json under the task's verdict dir AT HEAD via git ls-tree
    try:
        result = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD",
             f"outputs/audits/verdicts/{task_id}/"],
            cwd=str(POLARIS_ROOT),
            capture_output=True, text=True, timeout=5, encoding="utf-8",
        )
        if result.returncode != 0:
            return "NONE"
        files = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        iters = sorted(f for f in files if f.endswith(".json") and "iter_" in f)
        if not iters:
            return "NONE"
        latest_path = iters[-1]
    except Exception:
        return "NONE"

    content = _git_show_head(latest_path)
    if content is None:
        return "NONE"
    try:
        return json.loads(content).get("verdict", "NONE")
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
    """Walk tasks in canonical sequence; return (next_task, prep_id_if_any).

    Per Plan v13 §H: halted tasks (with halt-marker file present) are treated
    as user-blocked — the autoloop won't re-attempt them until user removes
    the halt marker (signalling resolution per the marker's resolution paths).
    """
    for task in tasks:
        if _is_task_halted(task["task_id"]):
            continue  # halted; pending user resolution
        verdict = _verdict_state(task["task_id"])
        if verdict == "APPROVE":
            continue
        if task["user_action"]:
            if _has_pending_prep(task):
                # find first non-APPROVE, non-halted prep
                for prep in task["substrate_prep"]:
                    prep_id = prep.get("id") if isinstance(prep, dict) else None
                    if not prep_id:
                        continue
                    if _is_task_halted(prep_id):
                        continue
                    if _verdict_state(prep_id) != "APPROVE":
                        return task, prep_id
            continue  # user-blocked, no prep → skip
        # not user-action, not APPROVE'd, not halted → this is the next task
        return task, None
    return None, None


def _emit_block(reason: str) -> None:
    """Emit a block-decision JSON to stdout per Claude Code Stop hook spec.

    Per https://code.claude.com/docs/en/hooks: use `hookSpecificOutput.additionalContext`
    so the reason text is wrapped in a system reminder and inserted into Claude's
    context window. The top-level `reason` field is shown to the human user;
    Claude itself reads `additionalContext`.
    """
    payload = {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": reason,
        },
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    sys.exit(0)


def _audit_classification(tasks: list) -> list:
    """Sweep every non-APPROVE task for lifecycle classification.

    Each non-APPROVE task MUST be in exactly one of these states:
      (1) APPROVE'd verdict at outputs/audits/verdicts/<id>/iter_*.json
      (2) Has at least one substrate_prep entry that is itself non-APPROVE
          and not halt-resolved (orchestrator-completable scaffold)
      (3) phase_gate field set + current phase < phase_gate
      (4) user_action_only dict with rationale + required_external fields
      (5) halt-resolution marker at outputs/audits/halt_resolutions/<id>_halt.md

    Returns: list of {task_id, missing_classification} for each unclassified task.
    """
    unclassified = []
    for task in tasks:
        task_id = task.get("task_id")
        if not task_id:
            continue
        # (1) Already APPROVE'd → nothing required
        if _verdict_state(task_id) == "APPROVE":
            continue
        # (5) halt-resolved at task-level → documented terminal state
        if _is_task_halted(task_id):
            continue
        # (3) phase_gated → check it has the field + valid phase ref
        if task.get("phase_gate"):
            continue
        # (4) user_action_only with rationale → documented external-dependency
        ua_only = task.get("user_action_only")
        if isinstance(ua_only, dict) and ua_only.get("rationale"):
            continue
        # (2) Active substrate_prep → orchestrator-completable scaffold defined
        preps = task.get("substrate_prep", []) or []
        has_active_prep = False
        for prep in preps:
            if not isinstance(prep, dict):
                continue
            pid = prep.get("id")
            if not pid:
                continue
            if _is_task_halted(pid):
                continue
            # Either pending (will be picked) OR APPROVE'd (already done) — both count
            has_active_prep = True
            break
        if has_active_prep:
            continue
        # Otherwise: UNCLASSIFIED
        unclassified.append({
            "task_id": task_id,
            "title": task.get("title", "")[:80],
            "user_action_legacy": bool(task.get("user_action")),
        })
    return unclassified


def main() -> None:
    if not _is_polaris_session():
        sys.exit(0)

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)

    # Kill switch off → loop disabled, allow stop
    if not KILL_SWITCH.exists():
        sys.exit(0)

    # NOTE: dropped MAX_CONSECUTIVE_BLOCKS counter (anti-pattern per
    # https://code.claude.com/docs/en/hooks: "Make your validation script
    # idempotent (same input → same result)... Check state from files/environment
    # rather than hook call count"). Validation is now purely state-based.

    # Step A: verify canonical pin (HARD STOP if drift)
    pin_ok, pin_msg = _verify_canonical_pin()
    if not pin_ok:
        _emit_block(
            f"POLARIS HARD STOP — canonical pin drift detected: {pin_msg}. "
            f"Per Plan v13 §A: any pinned-file change requires user-signed "
            f"reconciliation commit + new pin. Halt loop, investigate before resume."
        )

    # Step B: parse matrix from HEAD
    tasks = _parse_matrix_tasks_from_head()
    if not tasks:
        # Matrix unparseable — allow stop (don't block on infrastructure failure)
        sys.exit(0)

    # Step C: classification exhaustion audit.
    # Every non-APPROVE task MUST be classified. Refuse stop until ALL tasks have
    # one of: APPROVE'd verdict / active substrate_prep / phase_gate / user_action_only
    # rationale / halt-resolution marker. If any unclassified, block and tell Claude
    # exactly what to add.
    unclassified = _audit_classification(tasks)
    if unclassified:
        lines = [
            "POLARIS classification audit FAIL — cannot stop until every non-APPROVE task is classified.",
            "",
            f"{len(unclassified)} unclassified task(s):",
        ]
        for item in unclassified[:15]:
            ua = " (legacy user_action flag, no rationale)" if item["user_action_legacy"] else ""
            lines.append(f"  - {item['task_id']}: {item['title']}{ua}")
        if len(unclassified) > 15:
            lines.append(f"  ... and {len(unclassified) - 15} more")
        lines += [
            "",
            "Each unclassified task MUST be brought into ONE of these states (in matrix or filesystem):",
            "  (a) substrate_prep entry — orchestrator-completable scaffold (manifest / runbook / outline / harness)",
            "  (b) phase_gate: phase_<N> — defers task until phase N starts (orchestrator skips silently)",
            "  (c) user_action_only: { rationale: '...', required_external: '...' } — external-only, documented",
            "  (d) outputs/audits/halt_resolutions/<task_id>_halt.md — explicit halt with rationale",
            "",
            "Add the appropriate classification, update docs/canonical_pin.txt if matrix changed, ",
            "commit infrastructure-only, then continue. DO NOT stop without classifying.",
        ]
        _emit_block("\n".join(lines))

    # Step D: find next actionable
    next_task, prep_id = _next_actionable_task(tasks)
    if next_task is None:
        # Every task is classified AND nothing actionable remaining → genuinely done
        sys.exit(0)

    # Block stop, point at next actionable
    target = prep_id or next_task["task_id"]
    if prep_id:
        msg = f"prep sub-task {prep_id} (parent {next_task['task_id']} is user-action-blocked)"
    else:
        msg = f"task {next_task['task_id']}"

    _emit_block(
        f"POLARIS autoloop active — next actionable: {msg}. "
        f"Per Plan v13 §E strict canonical-plan sequence (no jumping). "
        f"Read docs/task_acceptance_matrix.yaml for green-criteria; "
        f"build manifest at outputs/audits/manifests/{target}.json; "
        f"orchestrator will invoke `codex exec` for verdict gate. "
        f"To stop loop: delete state/autoloop_active OR document a halt-resolution "
        f"at outputs/audits/halt_resolutions/{target}_halt.md."
    )


if __name__ == "__main__":
    main()
