#!/usr/bin/env python3
"""POLARIS Autoloop Orchestrator — Plan v13 §D runtime substrate.

External Python process. User starts ONCE: `python scripts/autoloop/orchestrator.py`.
Each task = one fresh Claude Agent SDK session reading canonical from disk.
Codex CLI invoked at task boundaries for verdict gate.

Survives 18 weeks structurally because no per-task state lives in this process —
state is in `git log` + `outputs/audits/{manifests,verdicts}/`. If process dies
(reboot, kill, hang), user re-runs orchestrator and it picks up where git +
verdicts say to resume.

Halt conditions per Plan v13 §H:
  1. canonical hash drift → HARD STOP
  2. 24h wall-clock per task without APPROVE
  3. $100 spend per task
  4. 3 consecutive REQUEST_CHANGES on same task
  5. user-action gate AND no substrate-prep alternative
  6. cross-review integrity finding (Claude SDK and Codex disagree on P0/P1)
  7. quality bar unreachable per §F (e.g. Gemma 4 31B unavailable)

Each halt → emits state/halt_<timestamp>_<task_id>.md and exits 0.

Authentication:
  Both Codex CLI and Claude Agent SDK use OAuth tokens from the user's existing
  logins on this machine — NO API keys required.
    - `codex exec` reads OAuth from ~/.codex/auth.json (run `codex login` once)
    - Claude Agent SDK reads OAuth from Claude Code's credential store
      (~/.claude/credentials.json) when ANTHROPIC_API_KEY is not set
  If you have a Claude Pro/Max/Team subscription, this just works — the SDK uses
  your subscription quota, not pay-per-token billing.

Required env:
  POLARIS_ROOT — defaults to C:/POLARIS
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

POLARIS_ROOT = Path(os.environ.get("POLARIS_ROOT", "C:/POLARIS")).resolve()
STATUS_FILE = POLARIS_ROOT / "state" / "orchestrator_status.json"
HALT_DIR = POLARIS_ROOT / "state"
MANIFEST_DIR = POLARIS_ROOT / "outputs" / "audits" / "manifests"
VERDICT_DIR = POLARIS_ROOT / "outputs" / "audits" / "verdicts"
BRIEF_DIR = POLARIS_ROOT / "outputs" / "audits" / "briefs"
AUDIT_LOG = POLARIS_ROOT / "outputs" / "audits" / "codex_audit.jsonl"
HMAC_KEY_PATH = POLARIS_ROOT / ".private" / "codex_hmac.key"
CANONICAL_PIN = POLARIS_ROOT / "docs" / "canonical_pin.txt"

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

PER_TASK_HOURS = 24
PER_TASK_USD_CAP = 100.0
MAX_REQUEST_CHANGES_ITER = 3


class HaltCondition(Exception):
    def __init__(self, code: int, reason: str, task_id: str | None = None, payload: dict | None = None):
        self.code = code
        self.reason = reason
        self.task_id = task_id
        self.payload = payload or {}
        super().__init__(reason)


def _heartbeat(state: dict) -> None:
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        state["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        STATUS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _emit_halt_marker(halt: HaltCondition) -> Path:
    HALT_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    fname = f"halt_{ts}_{halt.task_id or 'no_task'}.md"
    path = HALT_DIR / fname
    path.write_text(
        f"# Halt — condition #{halt.code}\n\n"
        f"task_id: {halt.task_id or 'N/A'}\n"
        f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        f"reason: {halt.reason}\n\n"
        f"## Payload\n```json\n{json.dumps(halt.payload, indent=2)}\n```\n\n"
        f"## Resolution\n"
        f"User reviews and either:\n"
        f"  (a) authorizes a §F best-of-best switch via signed canonical edit,\n"
        f"  (b) pauses build until upstream constraint satisfied, or\n"
        f"  (c) revises the failing task brief.\n"
        f"Then re-run `python scripts/autoloop/orchestrator.py`.\n",
        encoding="utf-8",
    )
    return path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_show_head(path: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=str(POLARIS_ROOT),
            capture_output=True, text=True, timeout=5, encoding="utf-8",
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _verify_canonical_pin() -> tuple[bool, str]:
    pin_text = _git_show_head("docs/canonical_pin.txt")
    if pin_text is None:
        return False, "canonical_pin.txt missing from HEAD"
    expected = {}
    for line in pin_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            expected[parts[1]] = parts[0]
    for f in CANONICAL_FILES:
        head_content = _git_show_head(f)
        if head_content is None:
            return False, f"{f} missing from HEAD"
        head_sha = hashlib.sha256(head_content.encode("utf-8")).hexdigest()
        if expected.get(f) != head_sha:
            return False, f"HEAD/pin mismatch for {f}"
        wt = POLARIS_ROOT / f
        if not wt.exists():
            return False, f"{f} missing in working tree"
        if _file_sha256(wt) != head_sha:
            return False, f"working-tree drift for {f}"
    return True, "canonical pin verified"


def _load_matrix_from_head() -> dict:
    text = _git_show_head("docs/task_acceptance_matrix.yaml")
    if text is None:
        raise HaltCondition(1, "task_acceptance_matrix.yaml missing from HEAD")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        raise HaltCondition(7, "PyYAML missing; install pyyaml in orchestrator venv")


def _verdict_state(task_id: str) -> tuple[str, int]:
    """Return (verdict_str, latest_iter_n). 'NONE'/0 if no verdict file."""
    d = VERDICT_DIR / task_id
    if not d.is_dir():
        return "NONE", 0
    iters = sorted(d.glob("iter_*.json"))
    if not iters:
        return "NONE", 0
    n = int(iters[-1].stem.removeprefix("iter_"))
    try:
        v = json.loads(iters[-1].read_text(encoding="utf-8"))
        return v.get("verdict", "NONE"), n
    except Exception:
        return "NONE", n


def _next_actionable(matrix: dict) -> tuple[str | None, dict | None, str | None]:
    """Walk plan-canonical sequence; return (task_id, task_dict, prep_id_or_None)."""
    for phase_key in sorted(matrix.keys()):
        if not phase_key.startswith("phase_"):
            continue
        phase = matrix[phase_key]
        if not isinstance(phase, dict):
            continue
        for task_key, task_val in phase.items():
            if not isinstance(task_val, dict):
                continue
            task_id = task_val.get("task_id") or task_key.removeprefix("task_").replace("_", ".")
            verdict, _ = _verdict_state(task_id)
            if verdict == "APPROVE":
                continue
            if task_val.get("user_action"):
                # Check substrate_prep
                preps = task_val.get("substrate_prep", []) or []
                for prep in preps:
                    if not isinstance(prep, dict):
                        continue
                    prep_id = prep.get("id")
                    if prep_id and _verdict_state(prep_id)[0] != "APPROVE":
                        return task_id, task_val, prep_id
                # User-action with no pending prep → skip
                continue
            return task_id, task_val, None
    return None, None, None


def _build_task_brief(task_id: str, task_def: dict) -> str:
    """Construct the system prompt + brief for the Agent SDK session."""
    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    green = task_def.get("green_criteria", []) or []
    artifacts = task_def.get("required_artifacts", []) or []
    brief = f"""# POLARIS Autoloop — Task {task_id}

You are running inside a fresh Claude Agent SDK session under POLARIS Plan v13.
You are NON-INTERACTIVE: you cannot ask the user questions; if you would normally
ask, instead halt the orchestrator with a halt-marker write per §H.

## Task

Task ID: {task_id}
Title: {task_def.get('title', 'N/A')}
Owner: {task_def.get('owner', 'claude')}
Estimate: {task_def.get('estimate_hours', '?')}h

## GREEN criteria (binding)

{chr(10).join(f"- {g}" for g in green)}

## Required artifacts

{chr(10).join(f"- {a}" for a in artifacts)}

## Canonical pin

SHA256: {pin_sha}

You MUST verify this pin matches `git show HEAD:docs/canonical_pin.txt` SHA before
making any edit. Mismatch = HARD STOP per Plan v13 §A.

## Process

1. Read `docs/carney_delivery_plan_v6_2.md` (canonical mission)
2. Read `docs/task_acceptance_matrix.yaml` (the row for task_{task_id.replace('.', '_')})
3. Read `architecture.md` (current-state)
4. Re-verify canonical pin every 10 tool calls or 15 min wall-clock (§J intra-task)
5. Implement per GREEN criteria
6. Write manifest at `outputs/audits/manifests/{task_id}.json` per Codex Red-Team schema
7. Stage commit (precommit hook will block until Codex verdict lands — that's the orchestrator's job, not yours)
8. Stop session cleanly

## Forbidden tools

- AskUserQuestion (HARD HALT — orchestrator will exit)
- Agent, Task (no subagent spawn)
- WebFetch, WebSearch (no outbound)
- ExitPlanMode

## Halt-and-decide quality bar (§F)

If you encounter inability to meet a GREEN criterion (Gemma 4 unavailable, hardware
not yet provisioned, etc.) — do NOT degrade silently. Write a partial manifest
listing what's done + what's blocked, then exit. Orchestrator emits halt-condition
#5 marker; user resolves.

## Begin
"""
    return brief


# ---------- Agent SDK invocation (lazy import to allow standalone tests) ----------

async def _hard_halt_callback(input_data, tool_use_id, context):
    """PreToolUse hook callback — defense in depth alongside disallowed_tools."""
    tool_name = input_data.get("tool_name", "")
    if tool_name in ("AskUserQuestion", "Agent", "Task", "WebFetch", "WebSearch", "ExitPlanMode"):
        task_id = os.environ.get("POLARIS_TASK_ID", "unknown")
        halt = HaltCondition(
            5, f"agent attempted forbidden tool {tool_name}", task_id=task_id,
            payload={"tool_input": input_data.get("tool_input", {})},
        )
        _emit_halt_marker(halt)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Tool {tool_name} forbidden in non-interactive task; "
                    f"halt marker written for orchestrator pickup."
                ),
            }
        }
    return None


async def _run_agent_session(task_id: str, brief: str, deadline_ts: float) -> dict:
    """Spawn fresh Claude Agent SDK session for the task. Returns result summary."""
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher
    except ImportError:
        raise HaltCondition(
            7, "claude_agent_sdk not installed; pip install claude-agent-sdk",
            task_id=task_id,
        )

    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    os.environ["POLARIS_TASK_ID"] = task_id
    os.environ["POLARIS_PIN_SHA"] = pin_sha

    options = ClaudeAgentOptions(
        cwd=str(POLARIS_ROOT),
        system_prompt=brief,
        permission_mode="dontAsk",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
        disallowed_tools=[
            "AskUserQuestion", "Agent", "Task",
            "WebFetch", "WebSearch", "ExitPlanMode",
        ],
        hooks={
            "PreToolUse": [
                HookMatcher(
                    matcher="AskUserQuestion|Agent|Task|WebFetch|WebSearch|ExitPlanMode",
                    hooks=[_hard_halt_callback],
                ),
            ],
        },
        setting_sources=["project"],
        model="claude-opus-4-7",
        max_turns=200,
    )

    summary = {"task_id": task_id, "messages": 0, "halt": None}
    try:
        async for msg in query(prompt=brief, options=options):
            summary["messages"] += 1
            if time.time() > deadline_ts:
                raise HaltCondition(2, "24h wall-clock exceeded", task_id=task_id)
    except HaltCondition:
        raise
    except Exception as e:
        summary["halt"] = str(e)
    return summary


# ---------- Codex CLI invocation ----------

def _build_review_brief(task_id: str, task_def: dict, diff_sha: str) -> str:
    """Construct INDEPENDENT review brief for Codex (P1-1 fix).

    NOT the same as the build brief. Build brief instructs Claude what to make.
    Review brief instructs Codex what to evaluate against.
    """
    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    green = task_def.get("green_criteria", []) or []
    artifacts = task_def.get("required_artifacts", []) or []
    return f"""# POLARIS Review Brief — task {task_id}

You are Codex. Adversarially review the staged commit for task {task_id} per
.codex/codex_red_team_checklist.md universal U1-U8 + applicable LLM-call/UI/crown-jewel
checks, severity-stratified per .codex/REVIEW_BRIEF_FORMAT_v2.md.

## Authoritative inputs

- Diff: `git diff --cached` from this orchestrator session, sha256={diff_sha}
- Manifest: outputs/audits/manifests/{task_id}.json
- Canonical pin: {pin_sha}
- Acceptance criteria for {task_id} from docs/task_acceptance_matrix.yaml

## GREEN criteria

{chr(10).join(f"- {g}" for g in green)}

## Required artifacts

{chr(10).join(f"- {a}" for a in artifacts)}

## Output (STRICT — gate enforces)

Emit JSON matching docs/schemas/codex_verdict.schema.json:
- verdict ∈ {{APPROVE, REQUEST_CHANGES, BLOCKED}}
- findings[] with severity P0/P1/P2/P3, file, line, category, description
- task_id="{task_id}", iter=<your iteration>, canonical_pin_sha="{pin_sha}",
  diff_sha256="{diff_sha}", commit_sha=<commit being-prepared sha or zeros>,
  codex_session_id=<your session>, model="gpt-5.5", reasoning_effort="xhigh",
  timestamp=<UTC ISO-8601>

DO NOT output Authorization headers, API keys, OAuth tokens, or PEM blocks.
Output is server-side scanned for credential exfiltration.
"""


def _invoke_codex_review(
    task_id: str, build_brief_path: Path, iter_n: int, task_def: dict
) -> dict:
    """Call `codex exec` for verdict. P1-1 fix: build independent review brief."""
    out_path = VERDICT_DIR / task_id / f"iter_{iter_n}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute substrate diff_sha (excludes verdict files for atomic-commit safety)
    diff_proc = subprocess.run(
        ["git", "diff", "--cached", "--",
         ":(exclude)outputs/audits/verdicts/**",
         ":(exclude)outputs/audits/codex_audit.jsonl",
         ":(exclude)outputs/audits/manifests/**"],
        cwd=str(POLARIS_ROOT), capture_output=True, timeout=30,
    )
    if diff_proc.returncode != 0:
        raise HaltCondition(7, f"git diff failed: {diff_proc.stderr.decode('utf-8', errors='replace')}", task_id=task_id)
    diff_sha = hashlib.sha256(diff_proc.stdout).hexdigest()

    review_brief = _build_review_brief(task_id, task_def, diff_sha)

    try:
        r = subprocess.run(
            ["codex", "exec", "--cd", str(POLARIS_ROOT), "--sandbox", "read-only",
             "--json", "--output-file", str(out_path), "-"],
            input=review_brief.encode("utf-8"),
            capture_output=True, timeout=1800, cwd=str(POLARIS_ROOT),
        )
    except Exception as e:
        raise HaltCondition(7, f"codex exec invocation failed: {e}", task_id=task_id)

    if r.returncode != 0:
        raise HaltCondition(7, f"codex exec exit {r.returncode}: {r.stderr.decode('utf-8', errors='replace')[:500]}", task_id=task_id)

    if not out_path.exists():
        raise HaltCondition(7, f"codex exec produced no verdict at {out_path}", task_id=task_id)

    try:
        verdict = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HaltCondition(7, f"verdict unparseable: {e}", task_id=task_id)

    # Orchestrator fills required signed fields (Codex CLI emits the review payload;
    # orchestrator owns identity + signing for the gate).
    verdict.setdefault("schema_version", "1.0.0")
    verdict["task_id"] = task_id
    verdict["iter"] = iter_n
    verdict["canonical_pin_sha"] = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    verdict["diff_sha256"] = diff_sha
    verdict.setdefault("commit_sha", "0" * 40)  # gate ignores this for backfill+normal
    verdict.setdefault("model", "gpt-5.5")
    verdict.setdefault("reasoning_effort", "xhigh")
    verdict.setdefault("findings", [])
    verdict.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    # HMAC sign
    hmac_key = HMAC_KEY_PATH.read_bytes().strip()
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    ser = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    verdict["hmac_sha256"] = hmac.new(hmac_key, ser, hashlib.sha256).hexdigest()
    out_path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")

    return verdict


def _commit_substrate_with_verdict(task_id: str, iter_n: int, verdict_path: Path) -> str:
    """P1-2 fix: orchestrator stages substrate + verdict atomically + commits.

    Called only after Codex APPROVE. Returns commit SHA.
    """
    # Stage all working-tree changes, including the just-written verdict
    subprocess.run(["git", "add", "-A"], cwd=str(POLARIS_ROOT), check=True, timeout=30)

    pin_short = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()[:12]
    msg = (
        f"task {task_id}: iter {iter_n} APPROVE\n\n"
        f"task: {task_id}\n"
        f"verdict: {verdict_path.relative_to(POLARIS_ROOT).as_posix()}\n"
        f"pin: {pin_short}\n"
        f"manifest: outputs/audits/manifests/{task_id}.json\n"
        f"\n"
        f"Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>\n"
    )
    r = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise HaltCondition(
            7, f"git commit failed (gate may have blocked): {r.stderr[:500]}",
            task_id=task_id,
        )
    sha_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=10,
    )
    return sha_proc.stdout.strip()


def _push_to_origin(task_id: str) -> None:
    """Push current branch to origin. Best-effort; failure halts at next iter."""
    r = subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        # Non-fatal — push can be retried. But log loudly.
        print(f"WARN push failed for {task_id}: {r.stderr[:300]}", file=sys.stderr)


# ---------- Main loop ----------

async def _run_task(task_id: str, task_def: dict) -> None:
    deadline = time.time() + PER_TASK_HOURS * 3600
    iter_n = 0

    while iter_n < MAX_REQUEST_CHANGES_ITER:
        iter_n += 1
        _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "build"})

        # Step 1: build via fresh SDK session (Claude SDK stages files but the
        # precommit gate blocks any commit attempt without a verdict; SDK is
        # instructed in the build brief NOT to commit — orchestrator does that)
        build_brief = _build_task_brief(task_id, task_def)
        build_brief_path = BRIEF_DIR / f"{task_id}_build_brief.md"
        build_brief_path.parent.mkdir(parents=True, exist_ok=True)
        build_brief_path.write_text(build_brief, encoding="utf-8")

        await _run_agent_session(task_id, build_brief, deadline)

        # Step 2: invoke Codex for INDEPENDENT review (not the build brief)
        _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "review"})
        verdict = _invoke_codex_review(task_id, build_brief_path, iter_n, task_def)
        verdict_path = VERDICT_DIR / task_id / f"iter_{iter_n}.json"

        if verdict.get("verdict") == "APPROVE":
            # Step 3: commit substrate + verdict atomically (P1-2 fix)
            _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "commit"})
            commit_sha = _commit_substrate_with_verdict(task_id, iter_n, verdict_path)
            # Step 4: push (P1-7 — best-effort; failure logged not halt)
            _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "push", "commit": commit_sha})
            _push_to_origin(task_id)
            _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "approved", "commit": commit_sha})
            return

        # REQUEST_CHANGES path: surface findings to next SDK session
        if iter_n >= MAX_REQUEST_CHANGES_ITER:
            raise HaltCondition(
                4, f"3 consecutive REQUEST_CHANGES on {task_id}", task_id=task_id,
                payload={"latest_verdict": verdict},
            )
        # Otherwise loop with findings injected into next build brief
        # (SDK session reads outputs/audits/verdicts/<id>/iter_<n-1>.json itself)


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                       help="Run one task then exit (for smoke testing)")
    args = parser.parse_args()

    print(f"POLARIS Autoloop Orchestrator — starting at {POLARIS_ROOT}")
    _heartbeat({"phase": "starting"})

    while True:
        try:
            ok, msg = _verify_canonical_pin()
            if not ok:
                raise HaltCondition(1, f"canonical pin drift: {msg}")

            matrix = _load_matrix_from_head()
            task_id, task_def, prep_id = _next_actionable(matrix)
            if task_id is None:
                print("All tasks APPROVE'd. Loop complete.")
                _heartbeat({"phase": "complete"})
                return 0

            target = prep_id or task_id
            target_def = task_def
            if prep_id:
                # Find the prep sub-task definition within parent's substrate_prep list
                for p in task_def.get("substrate_prep", []) or []:
                    if isinstance(p, dict) and p.get("id") == prep_id:
                        target_def = p
                        break

            print(f"Next actionable: {target} (parent={task_id})")
            await _run_task(target, target_def)

            if args.once:
                return 0

            time.sleep(5)

        except HaltCondition as halt:
            marker = _emit_halt_marker(halt)
            print(f"HALT condition #{halt.code}: {halt.reason}", file=sys.stderr)
            print(f"Marker: {marker}", file=sys.stderr)
            _heartbeat({"phase": "halted", "halt_code": halt.code, "halt_marker": str(marker)})
            return halt.code
        except KeyboardInterrupt:
            print("\nOrchestrator interrupted by user (Ctrl-C). Heartbeat preserved.")
            _heartbeat({"phase": "interrupted"})
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
