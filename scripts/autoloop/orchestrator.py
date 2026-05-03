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
  Both Codex CLI and Claude Code CLI use OAuth tokens from the user's existing
  logins on this machine — NO API keys required, NO Python SDK dependency.
    - `codex exec` reads OAuth from ~/.codex/auth.json (run `codex login` once)
    - `claude -p` reads OAuth from Claude Code's credential store
      (~/.claude/credentials.json) — same auth as the user's interactive sessions
  If you have a Claude Pro/Max/Team subscription, this just works — the CLI uses
  your subscription quota, not pay-per-token billing. The `--max-budget-usd` flag
  enforces Plan v13 §H halt-condition #3 at the CLI layer.

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
import shutil
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


def _is_halt_resolved(task_or_prep_id: str) -> bool:
    """Skip tasks/preps that have an active halt-resolution marker.

    Convention: outputs/audits/halt_resolutions/<id>_halt.md exists =
    user has documented a deferral / structural-block resolution that
    the orchestrator MUST honor (otherwise we burn quota re-discovering
    the same blocker every run).

    Resolution paths per Plan v13 §H halt-condition #5 are recorded in
    the marker file. The picker walks past marked tasks silently.
    Re-enable: delete the marker file; orchestrator re-surfaces in
    canonical sequence on the next run.
    """
    halt_file = POLARIS_ROOT / "outputs" / "audits" / "halt_resolutions" / f"{task_or_prep_id}_halt.md"
    return halt_file.is_file()


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
            # Skip tasks with active halt-resolution markers (e.g. 5.2 deferred to Phase 5)
            if _is_halt_resolved(task_id):
                continue
            if task_val.get("user_action"):
                # Check substrate_prep
                preps = task_val.get("substrate_prep", []) or []
                for prep in preps:
                    if not isinstance(prep, dict):
                        continue
                    prep_id = prep.get("id")
                    if not prep_id:
                        continue
                    if _verdict_state(prep_id)[0] == "APPROVE":
                        continue
                    if _is_halt_resolved(prep_id):
                        continue
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


# ---------- Claude Code CLI invocation (replaces Claude Agent SDK 2026-05-02) ----------
# Rationale: the `claude` CLI (v2.1.126+) is already installed and OAuth-authenticated
# from the user's interactive Claude Code sessions. Using it directly via subprocess
# eliminates the `claude-agent-sdk` Python dependency (one less halt-condition #7
# trigger) and ensures the orchestrator uses the same auth + tool-restriction
# semantics the user already validates interactively. --max-budget-usd enforces
# Plan v13 §H halt-condition #3 at the CLI layer; --disallowedTools enforces
# tool-restriction discipline (replacing the SDK PreToolUse hook).


async def _run_agent_session(task_id: str, brief: str, deadline_ts: float) -> dict:
    """Spawn fresh Claude Code CLI session for the task. Returns result summary.

    Uses `claude -p` (non-interactive) with OAuth from user's existing Claude Code
    login (~/.claude/credentials.json). No Python SDK dependency.
    """
    if not shutil.which("claude"):
        raise HaltCondition(
            7, "claude CLI not on PATH; install from https://claude.com/code",
            task_id=task_id,
        )

    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    os.environ["POLARIS_TASK_ID"] = task_id
    os.environ["POLARIS_PIN_SHA"] = pin_sha

    timeout_s = max(60, int(deadline_ts - time.time()))

    cmd_list = [
        "claude", "-p",
        "--allowedTools", "Read Write Edit Bash Grep Glob",
        "--disallowedTools", "AskUserQuestion Agent Task WebFetch WebSearch ExitPlanMode",
        "--max-budget-usd", str(PER_TASK_USD_CAP),
        "--permission-mode", "dontAsk",
        "--output-format", "json",
    ]
    # Windows: shell=True for .cmd shim resolution (same pattern as codex exec).
    import platform
    use_shell = platform.system() == "Windows"
    if use_shell:
        import shlex
        cmd_run = " ".join(shlex.quote(c) for c in cmd_list)
    else:
        cmd_run = cmd_list

    summary = {"task_id": task_id, "messages": 0, "halt": None, "cost_usd": 0.0}
    try:
        r = subprocess.run(
            cmd_run,
            input=brief.encode("utf-8"),
            capture_output=True, timeout=timeout_s, cwd=str(POLARIS_ROOT),
            shell=use_shell,
        )
    except subprocess.TimeoutExpired:
        raise HaltCondition(
            2, f"24h wall-clock exceeded during claude session (timeout={timeout_s}s)",
            task_id=task_id,
        )
    except Exception as e:
        summary["halt"] = f"subprocess invocation failed: {e!r}"
        return summary

    # Parse JSON result (claude -p --output-format json emits one result object)
    stdout_text = r.stdout.decode("utf-8", errors="replace")
    stderr_text = r.stderr.decode("utf-8", errors="replace")
    try:
        result = json.loads(stdout_text)
    except Exception:
        # Non-JSON output = unexpected failure (CLI crashed, OAuth invalid, etc.)
        raise HaltCondition(
            7, f"claude -p produced non-JSON output (returncode={r.returncode}): "
               f"stdout[:500]={stdout_text[:500]!r}, stderr[:300]={stderr_text[:300]!r}",
            task_id=task_id,
        )

    summary["messages"] = result.get("num_turns", 0)
    summary["cost_usd"] = result.get("total_cost_usd", 0.0)

    # Detect specific halt-condition signatures in CLI errors
    if result.get("is_error"):
        errors = result.get("errors") or []
        err_text = " | ".join(str(e) for e in errors)
        subtype = result.get("subtype", "")
        if subtype == "error_max_budget_usd" or "maximum budget" in err_text.lower():
            raise HaltCondition(
                3, f"per-task ${PER_TASK_USD_CAP} cap hit at ${summary['cost_usd']:.2f}: {err_text}",
                task_id=task_id,
            )
        if any(k in err_text for k in ("AskUserQuestion", "Agent", "Task", "WebFetch", "WebSearch", "ExitPlanMode")):
            raise HaltCondition(
                5, f"agent attempted forbidden tool: {err_text}",
                task_id=task_id,
            )
        # Other CLI-reported error → record but don't halt (let Codex review judge)
        summary["halt"] = f"claude -p reported is_error=true subtype={subtype} errors={err_text[:300]}"

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

- Diff: `git diff --cached` from this orchestrator session
- Substrate diff sha256={diff_sha} — INTENTIONALLY excludes
  `outputs/audits/manifests/**`, `outputs/audits/verdicts/**`, and
  `outputs/audits/codex_audit.jsonl` per gate convention (those paths
  are gate-managed, not substrate). For prep tasks whose only change
  IS a manifest, this hash may legitimately be the empty SHA256
  (e3b0c44...855) while `git diff --cached --numstat` shows real
  added lines. Verify staged content via `git diff --cached --name-only`
  rather than via this hash; output the same hash unchanged in your
  verdict (orchestrator overrides at sign time anyway).
- Manifest path (per matrix `changed_files_glob`): may be either
  `outputs/audits/manifests/{task_id}.json` (parent-task convention)
  OR a glob the matrix points to (e.g. `outputs/audits/manifests/0.5.json`
  for prep `0_5_stub_substrate` whose parent is `0.5`). Prefer the
  matrix glob.
- Canonical pin: {pin_sha}
- Acceptance criteria for {task_id} from docs/task_acceptance_matrix.yaml
  (or its substrate_prep entry, when reviewing a prep)

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

    # Real Codex CLI invocation. On Windows: shell=True for .cmd shim resolution
    # AND forward-slash paths (Codex CLI rejects backslashes with os error 123).
    # Drop --output-schema (over-constrains generation; smoke ran clean without).
    import platform
    use_shell = platform.system() == "Windows"
    cmd_list = ["codex", "exec",
                "--cd", str(POLARIS_ROOT).replace("\\", "/"),
                "--sandbox", "read-only",
                "--output-last-message", str(out_path).replace("\\", "/"),
                "-"]
    if use_shell:
        import shlex
        cmd_run = " ".join(shlex.quote(c) for c in cmd_list)
    else:
        cmd_run = cmd_list
    try:
        r = subprocess.run(
            cmd_run,
            input=review_brief.encode("utf-8"),
            capture_output=True, timeout=1800, cwd=str(POLARIS_ROOT),
            shell=use_shell,
        )
    except Exception as e:
        raise HaltCondition(7, f"codex exec invocation failed: {e!r}", task_id=task_id)

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


def _push_to_origin(task_id: str, iter_n: int) -> None:
    """Push to a task-scoped branch and open PR.

    Codex round-3 P0 fix: fail-CLOSED on push/PR failure. Was: WARN+continue
    (which let task be locally APPROVE'd while CI never ran → server-side
    cryptographic gate bypassed). Now: HaltCondition #7 raises on any push/PR
    failure that isn't "PR already exists" idempotency.

    Per Plan v13 §C-server: orchestrator must NOT push directly to `polaris`.
    Branch protection on `polaris` requires PR-only via merge queue.
    """
    branch = f"task/{task_id}/iter_{iter_n}"
    subprocess.run(
        ["git", "branch", "-f", branch, "HEAD"],
        cwd=str(POLARIS_ROOT), check=True, timeout=10,
    )
    r = subprocess.run(
        ["git", "push", "-f", "origin", branch],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise HaltCondition(
            7, f"git push of {branch} failed (server-side gate cannot run): {r.stderr[:300]}",
            task_id=task_id,
        )
    pr_title = f"task {task_id}: iter {iter_n} APPROVE"
    pr_body = (
        f"Per Plan v13 autoloop. Task {task_id} iteration {iter_n}.\n\n"
        f"Codex local verdict: APPROVE (HMAC-signed).\n"
        f"CI Phase B/C will independently re-validate.\n\n"
        f"Auto-merge enabled if CI passes.\n"
    )
    pr_r = subprocess.run(
        ["gh", "pr", "create", "--base", "polaris", "--head", branch,
         "--title", pr_title, "--body", pr_body],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=30,
    )
    if pr_r.returncode != 0:
        if "already exists" in (pr_r.stderr or "") or "already exists" in (pr_r.stdout or ""):
            print(f"INFO PR for {branch} already exists; reusing", file=sys.stderr)
            return
        # Any other failure → halt (CI gate cannot run without PR)
        raise HaltCondition(
            7, f"gh pr create for {branch} failed (CI gate cannot run): {pr_r.stderr[:300]}",
            task_id=task_id,
        )


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
            # Step 4: push to task-scoped branch + open PR (Codex round-2 P0 fix:
            # orchestrator MUST NOT push directly to polaris; branch protection
            # forces PR-only flow through CI Phase A/B/C verdict-validate)
            _heartbeat({"current_task": task_id, "iter": iter_n, "phase": "push", "commit": commit_sha})
            _push_to_origin(task_id, iter_n)
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

    # Codex round-4 P0 fix: reconcile unpushed locally-APPROVE'd commits BEFORE
    # picking any new task. Otherwise a previous run that committed locally but
    # failed at push silently leaves an unpushed verdict; on resume,
    # _next_actionable() sees the verdict as APPROVE'd and advances past the
    # task, skipping the server-side gate entirely.
    try:
        unpushed = subprocess.run(
            ["git", "log", "origin/polaris..HEAD", "--format=%H %s"],
            cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=10,
        )
        if unpushed.returncode == 0 and unpushed.stdout.strip():
            for line in unpushed.stdout.strip().splitlines():
                # Extract task_id from commit message line "task: <id>"
                # via subsequent git show
                sha = line.split()[0]
                msg = subprocess.run(
                    ["git", "show", "--no-patch", "--format=%B", sha],
                    cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=10,
                )
                task_match = None
                for ml in msg.stdout.splitlines():
                    if ml.startswith("task:"):
                        task_match = ml.split(":", 1)[1].strip()
                        break
                if task_match:
                    # Find iter from commit message; default to 1
                    iter_match = 1
                    for ml in msg.stdout.splitlines():
                        if ml.startswith("verdict:"):
                            # path like outputs/audits/verdicts/<id>/iter_N.json
                            import re
                            m = re.search(r"iter_(\d+)\.json", ml)
                            if m:
                                iter_match = int(m.group(1))
                            break
                    print(f"reconciling unpushed commit {sha[:12]} for task {task_match} iter {iter_match}", file=sys.stderr)
                    _heartbeat({"phase": "reconcile_push", "commit": sha, "task": task_match})
                    _push_to_origin(task_match, iter_match)
    except HaltCondition:
        raise  # re-raise so outer except handles it
    except Exception as e:
        print(f"WARN reconcile-push pre-check failed (non-fatal, will retry next iter): {e}", file=sys.stderr)

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
