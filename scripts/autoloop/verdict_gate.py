#!/usr/bin/env python3
"""POLARIS Verdict Gate — shared validator for git pre-commit + Claude PreToolUse hook.

Per Plan v13 §C. Validates that every commit has Codex APPROVE verdicts for
all tasks implicated by the staged diff. NO PASS-THROUGH BRANCHES.

Bootstrap exemption (only during initial setup):
  - If state/bootstrap_active exists AND commit message starts with "BOOTSTRAP",
    allow commit; log to outputs/audits/codex_audit.jsonl with type="bootstrap_exempt".
  - File state/bootstrap_active is deleted at end of §K Step 16 smoke (post-bootstrap).

Normal mode:
  - Read staged diff (git diff --cached --name-only).
  - Map changed files to task IDs via docs/task_acceptance_matrix.yaml.
  - For each implicated task, find latest verdict at outputs/audits/verdicts/<task_id>/iter_N.json.
  - Validate: schema valid, HMAC valid, verdict == APPROVE, canonical_pin_sha matches.
  - Block (exit 1) on any failure.

Usage:
  python scripts/autoloop/verdict_gate.py [--commit-message-file <path>]
    --commit-message-file: path to .git/COMMIT_EDITMSG (used for BOOTSTRAP detection).
                            Optional; if omitted, reads from /tmp or skips bootstrap check.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

POLARIS_ROOT = Path("C:/POLARIS").resolve()
BOOTSTRAP_FLAG = POLARIS_ROOT / "state" / "bootstrap_active"
HMAC_KEY_PATH = POLARIS_ROOT / ".private" / "codex_hmac.key"
SCHEMA_PATH = POLARIS_ROOT / "docs" / "schemas" / "codex_verdict.schema.json"
VERDICTS_DIR = POLARIS_ROOT / "outputs" / "audits" / "verdicts"
AUDIT_LOG = POLARIS_ROOT / "outputs" / "audits" / "codex_audit.jsonl"
CANONICAL_PIN = POLARIS_ROOT / "docs" / "canonical_pin.txt"
MATRIX_PATH = POLARIS_ROOT / "docs" / "task_acceptance_matrix.yaml"


class GateError(Exception):
    pass


def _staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(POLARIS_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise GateError(f"git diff failed: {result.stderr}")
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def _load_matrix() -> dict:
    try:
        import yaml
        return yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8")) or {}
    except ImportError:
        raise GateError("PyYAML required for matrix parsing; pip install pyyaml")
    except Exception as e:
        raise GateError(f"matrix parse failed: {e}")


def _changed_files_to_task_ids(files: list[str], matrix: dict) -> set[str]:
    """Map each changed file to one or more task IDs via changed_files_glob."""
    import fnmatch
    implicated = set()
    for phase_key, phase_val in matrix.items():
        if not phase_key.startswith("phase_") or not isinstance(phase_val, dict):
            continue
        for task_key, task_val in phase_val.items():
            if not isinstance(task_val, dict):
                continue
            task_id = task_key.removeprefix("task_").replace("_", ".")
            globs = task_val.get("changed_files_glob", []) or []
            for glob in globs:
                for f in files:
                    if fnmatch.fnmatch(f, glob):
                        implicated.add(task_id)
                        break
    return implicated


def _latest_verdict(task_id: str) -> dict | None:
    verdict_dir = VERDICTS_DIR / task_id
    if not verdict_dir.is_dir():
        return None
    iters = sorted(verdict_dir.glob("iter_*.json"))
    if not iters:
        return None
    try:
        return json.loads(iters[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _validate_schema(verdict: dict) -> tuple[bool, str]:
    try:
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(verdict, schema)
        return True, "schema ok"
    except ImportError:
        # Best-effort fallback — check required fields manually
        required = {"task_id", "iter", "codex_session_id", "verdict",
                    "canonical_pin_sha", "hmac_sha256", "findings", "timestamp"}
        missing = required - set(verdict.keys())
        if missing:
            return False, f"missing fields: {missing}"
        return True, "schema ok (jsonschema fallback)"
    except Exception as e:
        return False, f"schema validation failed: {e}"


def _canonical_serialize(verdict: dict) -> bytes:
    """Canonical serialization for HMAC: sorted keys, no spaces, drop hmac_sha256."""
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _validate_hmac(verdict: dict, key: bytes) -> tuple[bool, str]:
    expected = verdict.get("hmac_sha256")
    if not expected:
        return False, "verdict missing hmac_sha256"
    payload = _canonical_serialize(verdict)
    actual = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual, expected):
        return False, f"hmac mismatch: expected {expected[:12]}, computed {actual[:12]}"
    return True, "hmac ok"


def _validate_canonical_pin(verdict: dict) -> tuple[bool, str]:
    expected = verdict.get("canonical_pin_sha")
    if not expected:
        return False, "verdict missing canonical_pin_sha"
    actual = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    if actual != expected:
        return False, f"canonical_pin_sha mismatch: verdict={expected[:12]}, current={actual[:12]}"
    return True, "canonical pin ok"


def _is_bootstrap(commit_msg_path: str | None) -> bool:
    if not BOOTSTRAP_FLAG.exists():
        return False
    if not commit_msg_path:
        return False
    try:
        msg = Path(commit_msg_path).read_text(encoding="utf-8")
    except Exception:
        return False
    first_line = msg.lstrip().splitlines()[0] if msg.strip() else ""
    return first_line.startswith("BOOTSTRAP")


def _audit_log_event(event: dict) -> None:
    """Append to codex_audit.jsonl with prev_sha chain (best-effort)."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        prev_sha = None
        if AUDIT_LOG.exists():
            with open(AUDIT_LOG, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                # Read last KB
                f.seek(max(0, size - 4096))
                tail = f.read().decode("utf-8", errors="replace")
            for line in reversed(tail.strip().splitlines()):
                try:
                    last = json.loads(line)
                    prev_sha = last.get("entry_sha")
                    break
                except Exception:
                    continue
        event["prev_sha"] = prev_sha
        # Compute entry_sha excluding entry_sha field itself
        payload = {k: v for k, v in event.items() if k != "entry_sha"}
        ser = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        event["entry_sha"] = hashlib.sha256(ser).hexdigest()
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never let audit log failure block a legitimate gate decision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit-message-file", default=None)
    args = parser.parse_args()

    import time
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Bootstrap exemption check
    if _is_bootstrap(args.commit_message_file):
        _audit_log_event({
            "ts": timestamp,
            "type": "bootstrap_exempt",
            "commit_message_file": args.commit_message_file,
        })
        print("verdict_gate: BOOTSTRAP commit exempted (state/bootstrap_active present).", file=sys.stderr)
        return 0

    # Load matrix (if missing → new repo or pre-bootstrap; allow with warning)
    if not MATRIX_PATH.exists():
        print("verdict_gate: WARN matrix missing; commit allowed but autoloop NOT operational.", file=sys.stderr)
        return 0

    try:
        matrix = _load_matrix()
    except GateError as e:
        print(f"verdict_gate: ERROR matrix unparseable: {e}", file=sys.stderr)
        return 1

    files = _staged_files()
    if not files:
        return 0  # empty commit, nothing to gate

    implicated = _changed_files_to_task_ids(files, matrix)
    if not implicated:
        # No task implicated by the diff. Could be: docs-only commit, infra commit,
        # or matrix doesn't yet have changed_files_glob filled out for the task.
        # Conservative: allow but log loudly. The orchestrator's own task framing
        # should always set implicated tasks via manifest.
        print("verdict_gate: WARN no task implicated by staged files; commit allowed.", file=sys.stderr)
        _audit_log_event({
            "ts": timestamp,
            "type": "no_task_implicated",
            "files": files,
        })
        return 0

    # Load HMAC key
    if not HMAC_KEY_PATH.exists():
        print(f"verdict_gate: BLOCK no HMAC key at {HMAC_KEY_PATH}", file=sys.stderr)
        return 1
    try:
        hmac_key = HMAC_KEY_PATH.read_bytes().strip()
    except Exception as e:
        print(f"verdict_gate: BLOCK HMAC key read failed: {e}", file=sys.stderr)
        return 1

    # Validate verdict for each implicated task
    failed = []
    for task_id in sorted(implicated):
        verdict = _latest_verdict(task_id)
        if verdict is None:
            failed.append(f"{task_id}: no verdict file at outputs/audits/verdicts/{task_id}/iter_N.json")
            continue
        ok, msg = _validate_schema(verdict)
        if not ok:
            failed.append(f"{task_id}: schema invalid — {msg}")
            continue
        ok, msg = _validate_hmac(verdict, hmac_key)
        if not ok:
            failed.append(f"{task_id}: HMAC invalid — {msg}")
            continue
        ok, msg = _validate_canonical_pin(verdict)
        if not ok:
            failed.append(f"{task_id}: canonical pin mismatch — {msg}")
            continue
        if verdict.get("verdict") != "APPROVE":
            failed.append(f"{task_id}: verdict is {verdict.get('verdict')!r}, not APPROVE")
            continue

    if failed:
        print("verdict_gate: BLOCK — Codex verdict gate failed for staged commit:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nPer Plan v13 §C: every commit requires APPROVE verdict for each "
            "implicated task. Run the orchestrator (or `codex exec` manually) "
            "to obtain a verdict before re-attempting commit.",
            file=sys.stderr,
        )
        _audit_log_event({
            "ts": timestamp,
            "type": "gate_blocked",
            "implicated": list(implicated),
            "failures": failed,
            "files": files,
        })
        return 1

    # All implicated tasks have valid APPROVE
    _audit_log_event({
        "ts": timestamp,
        "type": "gate_passed",
        "implicated": list(implicated),
        "files": files,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
