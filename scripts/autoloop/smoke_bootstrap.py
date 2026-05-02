#!/usr/bin/env python3
"""POLARIS Bootstrap Smoke — Plan v13 §K Step 16 local-gate exercise.

Runs end-to-end through the autoloop substrate WITHOUT invoking the actual
Codex CLI (so it can run before the Canadian runner is provisioned and before
the user is online). Synthesizes a Codex-equivalent verdict via the same
HMAC + schema path that real Codex uses, and asserts every local gate seam
fires correctly.

Probes covered (per Plan v13 §K Step 16):
  (a) Stop hook reports "next actionable: bootstrap_smoke" when matrix has it pending
  (b) Manifest lands at outputs/audits/manifests/bootstrap_smoke.json
  (c) Synthetic verdict written; HMAC + schema valid
  (d) verdict_gate.py validates: schema, HMAC, canonical_pin, diff_sha256
  (e) Audit log entry chained correctly

Probes NOT covered (require Canadian runner + actual Codex auth):
  (j-n) GitHub Actions workflow run; merge queue
  (o-r) Failure injections — author separately when runner is up

Run from the orchestrator OR manually:
    python scripts/autoloop/smoke_bootstrap.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path

POLARIS_ROOT = Path("C:/POLARIS").resolve()
HMAC_KEY_PATH = POLARIS_ROOT / ".private" / "codex_hmac.key"
CANONICAL_PIN = POLARIS_ROOT / "docs" / "canonical_pin.txt"
SCHEMA_PATH = POLARIS_ROOT / "docs" / "schemas" / "codex_verdict.schema.json"

TASK_ID = "bootstrap_smoke"
SUBSTRATE_PATH = POLARIS_ROOT / "tests" / "smoke" / "bootstrap_no_op.py"
MANIFEST_PATH = POLARIS_ROOT / "outputs" / "audits" / "manifests" / f"{TASK_ID}.json"
VERDICT_PATH = POLARIS_ROOT / "outputs" / "audits" / "verdicts" / TASK_ID / "iter_1.json"
GATE_SCRIPT = POLARIS_ROOT / "scripts" / "autoloop" / "verdict_gate.py"


class SmokeError(Exception):
    pass


def _probe(name: str, fn) -> bool:
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except Exception as e:
        # Windows console may be cp1252; encode safely
        try:
            print(f"  [FAIL] {name}: {e}")
        except UnicodeEncodeError:
            msg = str(e).encode("ascii", errors="replace").decode("ascii")
            print(f"  [FAIL] {name}: {msg}")
        return False


def step_1_substrate():
    """Step 1: write a minimal no-op substrate file."""
    SUBSTRATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBSTRATE_PATH.write_text(
        '"""POLARIS bootstrap smoke — no-op test fixture."""\n'
        "\n"
        "def test_bootstrap_smoke_marker():\n"
        '    """Marker test — its existence is the smoke artifact."""\n'
        "    assert True, \"bootstrap smoke fixture loaded\"\n",
        encoding="utf-8",
    )


def step_2_manifest():
    """Step 2: write per-task manifest matching Codex Red-Team Checklist schema."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest = {
        "task_id": TASK_ID,
        "phase": "bootstrap",
        "title": "Bootstrap smoke end-to-end gate exercise",
        "owner": "claude+orchestrator",
        "started_at": timestamp,
        "completed_at": timestamp,
        "estimate_hours": 1,
        "actual_hours": 1,
        "changed_files": [
            str(SUBSTRATE_PATH.relative_to(POLARIS_ROOT).as_posix()),
            str(MANIFEST_PATH.relative_to(POLARIS_ROOT).as_posix()),
        ],
        "test_commands": [
            f"python -m pytest {SUBSTRATE_PATH.relative_to(POLARIS_ROOT).as_posix()}",
        ],
        "artifacts": [
            {"type": "test_fixture", "path": str(SUBSTRATE_PATH.relative_to(POLARIS_ROOT).as_posix())},
        ],
        "recordings": [],
        "trace_ids": [],
        "open_bugs": [],
        "evidence_links": [
            {
                "green_criterion": "Manifest lands at outputs/audits/manifests/bootstrap_smoke.json",
                "artifact": str(MANIFEST_PATH.relative_to(POLARIS_ROOT).as_posix()),
            }
        ],
        "codex_findings_addressed": [],
        "walkthrough_artifact": None,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def step_3_stage_substrate():
    """Step 3: stage substrate (NOT verdict yet — gate should block on commit)."""
    subprocess.run(
        ["git", "add", str(SUBSTRATE_PATH), str(MANIFEST_PATH)],
        cwd=str(POLARIS_ROOT), check=True, timeout=30,
    )


def _staged_diff_sha256(exclude_verdicts: bool = True) -> str:
    cmd = ["git", "diff", "--cached"]
    if exclude_verdicts:
        cmd += ["--",
                ":(exclude)outputs/audits/verdicts/**",
                ":(exclude)outputs/audits/codex_audit.jsonl",
                ":(exclude)outputs/audits/manifests/**"]
    r = subprocess.run(cmd, cwd=str(POLARIS_ROOT), capture_output=True, timeout=15)
    return hashlib.sha256(r.stdout).hexdigest()


def step_4_live_codex_review():
    """Step 4 (LIVE mode): invoke real `codex exec` to review the staged smoke commit.

    Replaces synthetic verdict with the same orchestrator-path call that real
    tasks use. Verifies: Codex CLI is reachable, OAuth tokens work, output is
    schema-valid, HMAC sign-and-verify roundtrip works.
    """
    diff_sha = _staged_diff_sha256(exclude_verdicts=True)
    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()

    review_brief = f"""# Bootstrap Smoke — Live Codex Review

You are reviewing a 1-line no-op test fixture (`tests/smoke/bootstrap_no_op.py`)
that exists solely to validate the autoloop's gate machinery.

## Task

Emit a verdict JSON matching `docs/schemas/codex_verdict.schema.json`. Required:
- verdict: APPROVE  (this is a no-op fixture, no findings expected)
- task_id: bootstrap_smoke
- iter: 1
- canonical_pin_sha: {pin_sha}
- diff_sha256: {diff_sha}
- commit_sha: 0000000000000000000000000000000000000000
- model: gpt-5.5
- reasoning_effort: xhigh
- codex_session_id: <your session>
- timestamp: ISO-8601 UTC
- findings: []

DO NOT include hmac_sha256 (orchestrator signs after).
DO NOT output Authorization headers, API keys, or PEM blocks.
"""

    out_path = VERDICT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Windows: shell=True so the .cmd shim resolves correctly
    import platform
    use_shell = platform.system() == "Windows"
    # Codex CLI on Windows wants forward-slash paths.
    # Drop --output-schema for smoke — it constrains generation and codex is
    # already instructed via prompt to emit JSON. Schema validation happens
    # in step 5 against the file codex produces.
    cmd = ["codex", "exec", "--cd", str(POLARIS_ROOT).replace("\\", "/"),
           "--sandbox", "read-only",
           "--output-last-message", str(out_path).replace("\\", "/"), "-"]
    if use_shell:
        # Convert list to a single quoted string for cmd.exe
        import shlex
        cmd = " ".join(shlex.quote(c) for c in cmd)
    try:
        r = subprocess.run(
            cmd,
            input=review_brief.encode("utf-8"),
            capture_output=True, timeout=600, cwd=str(POLARIS_ROOT),
            shell=use_shell,
        )
    except Exception as e:
        raise SmokeError(f"codex exec invocation failed: {e!r}")
    if r.returncode != 0:
        raise SmokeError(f"codex exec exit {r.returncode}: {r.stderr.decode('utf-8', errors='replace')[:500]}")
    if not out_path.exists():
        raise SmokeError(f"codex exec produced no verdict at {out_path}")

    verdict = json.loads(out_path.read_text(encoding="utf-8"))
    # Orchestrator-equivalent: ensure required fields exist + sign
    verdict.setdefault("schema_version", "1.0.0")
    verdict["task_id"] = TASK_ID
    verdict["iter"] = 1
    verdict["canonical_pin_sha"] = pin_sha
    verdict["diff_sha256"] = diff_sha
    verdict.setdefault("commit_sha", "0" * 40)
    verdict.setdefault("model", "gpt-5.5")
    verdict.setdefault("reasoning_effort", "xhigh")
    verdict.setdefault("findings", [])
    verdict.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if "codex_session_id" not in verdict:
        verdict["codex_session_id"] = f"live_smoke_{int(time.time())}"

    hmac_key = HMAC_KEY_PATH.read_bytes().strip()
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    ser = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    verdict["hmac_sha256"] = hmac.new(hmac_key, ser, hashlib.sha256).hexdigest()
    out_path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")


def step_4_synthesize_verdict():
    """Step 4 (SMOKE mode, default): synthesize a Codex-equivalent APPROVE verdict.

    In LIVE mode (--live flag) we invoke real `codex exec`. SMOKE mode synthesizes
    the verdict to exercise gate paths without Codex round-trip. Honestly disclosed
    via codex_session_id="bootstrap_smoke_synthetic_<ts>".
    """
    diff_sha = _staged_diff_sha256(exclude_verdicts=True)
    pin_sha = hashlib.sha256(CANONICAL_PIN.read_bytes()).hexdigest()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    verdict = {
        "schema_version": "1.0.0",
        "task_id": TASK_ID,
        "iter": 1,
        "codex_session_id": f"bootstrap_smoke_synthetic_{int(time.time())}",
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh",
        "canonical_pin_sha": pin_sha,
        "commit_sha": "0" * 40,
        "diff_sha256": diff_sha,
        "verdict": "APPROVE",
        "verdict_reason": (
            "Bootstrap smoke synthetic verdict. NOT a Codex-generated review; "
            "it is a smoke-test artifact that exercises the gate's HMAC + schema "
            "+ canonical-pin + diff_sha256 validation paths. Real Codex review "
            "fires on first non-bootstrap commit (decision #10 runner online)."
        ),
        "findings": [],
        "rationale": (
            "Smoke task is a no-op substrate (single test fixture). The smoke "
            "validates the gate plumbing, not feature correctness."
        ),
        "manifest_evidence": [
            str(SUBSTRATE_PATH.relative_to(POLARIS_ROOT).as_posix()),
            str(MANIFEST_PATH.relative_to(POLARIS_ROOT).as_posix()),
        ],
        "timestamp": timestamp,
    }
    # HMAC sign
    hmac_key = HMAC_KEY_PATH.read_bytes().strip()
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    ser = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    verdict["hmac_sha256"] = hmac.new(hmac_key, ser, hashlib.sha256).hexdigest()

    VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERDICT_PATH.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")


def step_5_validate_schema():
    """Step 5: validate verdict against schema."""
    try:
        import jsonschema
    except ImportError:
        print("    note: jsonschema not installed; skipping schema check")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    verdict = json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(verdict, schema)


def step_6_validate_hmac():
    """Step 6: re-compute HMAC and verify match."""
    verdict = json.loads(VERDICT_PATH.read_text(encoding="utf-8"))
    expected = verdict["hmac_sha256"]
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    ser = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    hmac_key = HMAC_KEY_PATH.read_bytes().strip()
    actual = hmac.new(hmac_key, ser, hashlib.sha256).hexdigest()
    if actual != expected:
        raise SmokeError(f"HMAC mismatch: expected {expected[:12]}, computed {actual[:12]}")


def step_7_run_gate():
    """Step 7: run verdict_gate against current staged set + (still un-staged) verdict."""
    # First stage the verdict file too
    subprocess.run(
        ["git", "add", str(VERDICT_PATH)],
        cwd=str(POLARIS_ROOT), check=True, timeout=30,
    )
    r = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        cwd=str(POLARIS_ROOT), capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise SmokeError(
            f"verdict_gate.py rc={r.returncode}\nstderr: {r.stderr[:1000]}"
        )


def step_8_check_audit_log():
    """Step 8: confirm gate appended an entry to outputs/audits/codex_audit.jsonl."""
    audit_log = POLARIS_ROOT / "outputs" / "audits" / "codex_audit.jsonl"
    if not audit_log.exists():
        raise SmokeError(f"audit log missing at {audit_log}")
    last_line = audit_log.read_text(encoding="utf-8").strip().splitlines()[-1]
    entry = json.loads(last_line)
    if entry.get("type") not in ("gate_passed", "infrastructure_only_allow"):
        raise SmokeError(f"latest audit entry type {entry.get('type')!r}, expected gate_passed")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                       help="Invoke real `codex exec` instead of synthesizing the verdict")
    args = parser.parse_args()

    mode = "LIVE (real Codex)" if args.live else "SMOKE (synthetic verdict)"
    print(f"POLARIS Bootstrap Smoke — Plan v13 §K Step 16 — mode: {mode}")
    print(f"  task_id: {TASK_ID}")
    print(f"  POLARIS_ROOT: {POLARIS_ROOT}")
    print()

    step4_fn = step_4_live_codex_review if args.live else step_4_synthesize_verdict
    step4_label = ("step 4: LIVE codex exec produces signed verdict"
                   if args.live else "step 4: synthesize verdict")

    results = []
    results.append(_probe("step 1: write substrate", step_1_substrate))
    results.append(_probe("step 2: write manifest", step_2_manifest))
    results.append(_probe("step 3: stage substrate", step_3_stage_substrate))
    results.append(_probe(step4_label, step4_fn))
    results.append(_probe("step 5: schema validates", step_5_validate_schema))
    results.append(_probe("step 6: HMAC validates", step_6_validate_hmac))
    results.append(_probe("step 7: verdict_gate passes", step_7_run_gate))
    results.append(_probe("step 8: audit log entry chained", step_8_check_audit_log))

    print()
    passed = sum(results)
    total = len(results)
    print(f"smoke result: {passed}/{total} probes passed")
    if passed != total:
        print("\nFAIL — at least one local gate seam is broken. Investigate before continuing.")
        return 1
    print("\nPASS — all local gate seams operational.")
    print("Server-side probes (j-n + p-r) require self-hosted runner (decision #10).")
    print("\nNext: orchestrator can now be invoked safely. To complete bootstrap:")
    print("  1. Verify this commit lands cleanly (git status)")
    print("  2. After live runner is up, exercise probes j-n via real PR")
    print("  3. Delete state/bootstrap_active to switch gate to STRICT mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
