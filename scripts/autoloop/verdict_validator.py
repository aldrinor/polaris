#!/usr/bin/env python3
"""POLARIS verdict validator — runs in GitHub Actions Phase C (verdict-validate).

Per Plan v13 §C severity-aware structural-equivalence rule:
  PASS iff ALL:
    committed.verdict == "APPROVE"
    AND rerun.verdict == "APPROVE"
    AND jsonschema_valid(committed) AND jsonschema_valid(rerun)
    AND hmac_valid(committed, CODEX_HMAC_KEY)
    AND committed.canonical_pin_sha == sha256(canonical_pin.txt @ commit)
    AND committed.diff_sha256 matches the actual diff at commit
    AND count_findings(rerun, severity in {"P0", "P1"}) == 0
    AND no_severity_upgrade(committed.findings, rerun.findings)
       # for every (file, line) finding in committed, rerun cannot have higher severity at same location
  P2/P3 count drift → audit only, NOT merge-blocking.

Loaded from refs/heads/main (trusted ref) — PR cannot tamper with this code.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path


SEVERITY_RANK = {"P3": 0, "P2": 1, "P1": 2, "P0": 3}


def _validate_schema(verdict: dict, schema_path: Path) -> tuple[bool, str]:
    try:
        import jsonschema
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(verdict, schema)
        return True, "schema ok"
    except ImportError:
        return False, "jsonschema package required in CI runner"
    except Exception as e:
        return False, f"schema invalid: {e}"


def _canonical_serialize(verdict: dict) -> bytes:
    payload = {k: v for k, v in verdict.items() if k != "hmac_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _validate_hmac(verdict: dict, key: bytes) -> tuple[bool, str]:
    expected = verdict.get("hmac_sha256", "")
    actual = hmac.new(key, _canonical_serialize(verdict), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(actual, expected):
        return False, f"hmac mismatch: expected {expected[:12]}, computed {actual[:12]}"
    return True, "hmac ok"


def _validate_canonical_pin(verdict: dict, pin_path: Path) -> tuple[bool, str]:
    expected = verdict.get("canonical_pin_sha", "")
    actual = hashlib.sha256(pin_path.read_bytes()).hexdigest()
    if actual != expected:
        return False, f"canonical_pin mismatch: verdict={expected[:12]}, file={actual[:12]}"
    return True, "canonical_pin ok"


def _validate_diff_sha(verdict: dict, expected_diff_sha: str) -> tuple[bool, str]:
    if expected_diff_sha and verdict.get("diff_sha256") != expected_diff_sha:
        return False, (
            f"diff_sha256 mismatch: verdict={verdict.get('diff_sha256','')[:12]}, "
            f"actual={expected_diff_sha[:12]}"
        )
    return True, "diff_sha ok"


def _no_p0_p1(findings: list[dict]) -> tuple[bool, str]:
    blockers = [f for f in findings if f.get("severity") in ("P0", "P1")]
    if blockers:
        return False, f"rerun has {len(blockers)} P0/P1 finding(s)"
    return True, "no P0/P1"


def _no_severity_upgrade(committed_findings: list[dict], rerun_findings: list[dict]) -> tuple[bool, str]:
    """For each (file, line) PRESENT in committed, rerun cannot have HIGHER severity at same location.

    Per Codex round-1 P1-5 fix: only check locations that exist in committed.
    New findings at NEW locations are NOT severity upgrades — they're audit-only
    drift (Plan v13 §C structural-equivalence rule: "P2/P3 count drift → audit only,
    not merge-blocking"). New P0/P1 findings at new locations are caught separately
    by `_no_p0_p1` rule.
    """
    committed_by_loc: dict[tuple[str, int], int] = {}
    for f in committed_findings:
        key = (f.get("file", ""), f.get("line", 0))
        sev = SEVERITY_RANK.get(f.get("severity", "P3"), 0)
        if key in committed_by_loc:
            committed_by_loc[key] = max(committed_by_loc[key], sev)
        else:
            committed_by_loc[key] = sev

    upgrades = []
    for f in rerun_findings:
        key = (f.get("file", ""), f.get("line", 0))
        if key not in committed_by_loc:
            continue  # new location → not an upgrade (drift; audit-only)
        rerun_sev = SEVERITY_RANK.get(f.get("severity", "P3"), 0)
        committed_sev = committed_by_loc[key]
        if rerun_sev > committed_sev:
            upgrades.append({
                "file": key[0],
                "line": key[1],
                "committed_severity": [s for s, r in SEVERITY_RANK.items() if r == committed_sev][0],
                "rerun_severity": f.get("severity"),
                "description": f.get("description", "")[:200],
            })

    if upgrades:
        return False, f"severity upgrade at {len(upgrades)} location(s); first: {upgrades[0]}"
    return True, "no severity upgrades"


def _latest_committed_verdict(committed_dir: Path) -> dict | None:
    if not committed_dir.is_dir():
        return None
    iters = sorted(committed_dir.glob("iter_*.json"))
    if not iters:
        return None
    return json.loads(iters[-1].read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--committed-verdict-dir", required=True, type=Path)
    parser.add_argument("--rerun-verdict", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--gpg-public-key", required=True, type=Path)
    parser.add_argument("--canonical-pin", required=True, type=Path)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--diff-sha256", default="")
    args = parser.parse_args()

    hmac_key_str = os.environ.get("CODEX_HMAC_KEY", "")
    if not hmac_key_str:
        print("verdict_validator: BLOCK CODEX_HMAC_KEY env not set", file=sys.stderr)
        return 1
    hmac_key = hmac_key_str.encode() if isinstance(hmac_key_str, str) else hmac_key_str

    committed = _latest_committed_verdict(args.committed_verdict_dir)
    if committed is None:
        print(f"verdict_validator: BLOCK no committed verdict in {args.committed_verdict_dir}", file=sys.stderr)
        return 1

    try:
        rerun = json.loads(args.rerun_verdict.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"verdict_validator: BLOCK rerun verdict unreadable: {e}", file=sys.stderr)
        return 1

    failures = []

    # Codex round-3 P0 fix: verdict.task_id MUST match --task-id arg from workflow.
    # Was: only verdict_gate.py local-side checked this; CI side wasn't.
    # A bypassed local hook could land an HMAC-valid verdict under the wrong
    # task directory + wrong task scope.
    if committed.get("task_id") != args.task_id:
        failures.append(
            f"committed.task_id={committed.get('task_id')!r} does not match --task-id={args.task_id!r} "
            f"(directory placement vs verdict-content mismatch — replay/aliasing detected)"
        )
    if rerun.get("task_id") != args.task_id and rerun.get("task_id") is not None:
        failures.append(
            f"rerun.task_id={rerun.get('task_id')!r} does not match --task-id={args.task_id!r}"
        )

    # 1. Schema validity (committed); rerun is unsigned (Codex direct output) so we
    # validate it against a relaxed view that doesn't require hmac_sha256.
    # Codex round-2 P1 fix.
    ok, msg = _validate_schema(committed, args.schema)
    if not ok:
        failures.append(f"committed: {msg}")
    # For rerun: synthesize an hmac_sha256 placeholder so schema validates structurally.
    rerun_for_schema = dict(rerun)
    rerun_for_schema.setdefault("hmac_sha256", "0" * 64)
    rerun_for_schema.setdefault("schema_version", "1.0.0")
    rerun_for_schema.setdefault("canonical_pin_sha", committed.get("canonical_pin_sha", "0" * 64))
    rerun_for_schema.setdefault("commit_sha", committed.get("commit_sha", "0" * 40))
    rerun_for_schema.setdefault("diff_sha256", committed.get("diff_sha256", "0" * 64))
    rerun_for_schema.setdefault("task_id", committed.get("task_id", "unknown"))
    rerun_for_schema.setdefault("iter", committed.get("iter", 1))
    rerun_for_schema.setdefault("codex_session_id", "rerun_unsigned")
    rerun_for_schema.setdefault("model", "gpt-5.5")
    rerun_for_schema.setdefault("reasoning_effort", "xhigh")
    rerun_for_schema.setdefault("findings", [])
    rerun_for_schema.setdefault("timestamp", "1970-01-01T00:00:00Z")
    ok, msg = _validate_schema(rerun_for_schema, args.schema)
    if not ok:
        failures.append(f"rerun (after defaults): {msg}")

    # 2. HMAC (committed only — rerun is unsigned by design, since it's a fresh
    #    Codex run on the diff, not a separate commit)
    ok, msg = _validate_hmac(committed, hmac_key)
    if not ok:
        failures.append(f"committed: {msg}")

    # 3. Canonical pin
    ok, msg = _validate_canonical_pin(committed, args.canonical_pin)
    if not ok:
        failures.append(f"committed: {msg}")

    # 4. Diff SHA cross-check
    ok, msg = _validate_diff_sha(committed, args.diff_sha256)
    if not ok:
        failures.append(f"committed: {msg}")

    # 5. Verdict equality
    if committed.get("verdict") != "APPROVE":
        failures.append(f"committed.verdict={committed.get('verdict')!r}, expected APPROVE")
    if rerun.get("verdict") != "APPROVE":
        failures.append(f"rerun.verdict={rerun.get('verdict')!r}, expected APPROVE")

    # 6. No P0/P1 in rerun
    ok, msg = _no_p0_p1(rerun.get("findings", []))
    if not ok:
        failures.append(f"rerun: {msg}")

    # 7. No severity upgrade (rerun cannot escalate findings beyond committed)
    ok, msg = _no_severity_upgrade(committed.get("findings", []), rerun.get("findings", []))
    if not ok:
        failures.append(msg)

    if failures:
        print("verdict_validator: ❌ BLOCK", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"verdict_validator: ✅ PASS task={args.task_id} commit={args.commit_sha[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
