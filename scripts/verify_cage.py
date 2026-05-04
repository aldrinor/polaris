#!/usr/bin/env python3
"""POLARIS cage verification — runs at session start and on demand.

Verifies the cage established 2026-05-04 per polaris-controls/PLAN.md is
intact:

  1. POLARIS branch protection on `polaris` and `main` matches expected
     baseline (signed commits, no force push, no deletions).
  2. polaris-controls branch protection on `main` matches expected
     baseline (signed commits, code-owner review, 1 approval).
  3. session_pin.txt SHAs match live blob SHAs of pinned files in
     polaris-controls HEAD.
  4. CODEOWNERS file present and covers expected control-plane paths.

Output: structured pass/fail with per-check detail. Exits 0 on full pass,
1 on any failure.

Usage:
    python scripts/verify_cage.py
    python scripts/verify_cage.py --json             # machine-readable
    python scripts/verify_cage.py --polaris-only     # skip cross-repo

Dependencies: gh CLI authenticated as aldrinor with metadata read on both
repos. No third-party Python packages required.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_OWNER = "aldrinor"
POLARIS_REPO = "polaris"
CONTROLS_REPO = "polaris-controls"
POLARIS_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_PROTECTION_POLARIS = {
    "required_signatures.enabled": True,
    "allow_force_pushes.enabled": False,
    "allow_deletions.enabled": False,
}

EXPECTED_PROTECTION_CONTROLS = {
    "required_signatures.enabled": True,
    "enforce_admins.enabled": True,
    "allow_force_pushes.enabled": False,
    "allow_deletions.enabled": False,
    "required_pull_request_reviews.require_code_owner_reviews": True,
    "required_pull_request_reviews.required_approving_review_count": 1,
}

EXPECTED_CODEOWNERS_PATHS = [
    "docs/session_pin.txt",
    "docs/canonical_pin.txt",
    "docs/blockers.md",
    "docs/task_acceptance_matrix.yaml",
    ".github/",
    ".codex/",
    ".claude/",
    "scripts/autoloop/",
    ".legacy/",
]

PIN_KEY_TO_PATH = {
    "charter_blob_sha": "CHARTER.md",
    "plan_blob_sha": "PLAN.md",
    "slice_blob_sha": "slices/slice_001_clinical_scope_discovery.md",
    "golden_blob_sha": "golden/slice_001/manifest.md",
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    passed: bool = True
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name, passed, detail))
        if not passed:
            self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }


def gh(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, check=False
    )
    return result.returncode, result.stdout, result.stderr


def get_protection(owner: str, repo: str, branch: str) -> dict[str, Any] | None:
    rc, out, _ = gh(["api", f"repos/{owner}/{repo}/branches/{branch}/protection"])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def get_blob_sha(owner: str, repo: str, path: str) -> str | None:
    rc, out, _ = gh(
        ["api", f"repos/{owner}/{repo}/contents/{path}", "--jq", ".sha"]
    )
    if rc != 0:
        return None
    return out.strip() or None


def nested_get(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def check_protection(
    report: Report,
    owner: str,
    repo: str,
    branch: str,
    expected: dict[str, Any],
) -> None:
    label = f"{repo}/{branch}"
    bp = get_protection(owner, repo, branch)
    if bp is None:
        report.add(
            f"protection.{label}.exists",
            False,
            f"no branch protection found (or unauthorized to fetch)",
        )
        return
    report.add(f"protection.{label}.exists", True)
    for key, want in expected.items():
        actual = nested_get(bp, key)
        ok = actual == want
        report.add(
            f"protection.{label}.{key}",
            ok,
            f"expected {want!r}, got {actual!r}" if not ok else "",
        )


def check_session_pin(report: Report) -> None:
    pin_path = POLARIS_ROOT / "docs" / "session_pin.txt"
    if not pin_path.is_file():
        report.add(
            "session_pin.exists", False,
            f"file not found at {pin_path}",
        )
        return
    report.add("session_pin.exists", True)

    pin_text = pin_path.read_text(encoding="utf-8")
    pinned: dict[str, str] = {}
    for line in pin_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([\w_]+):\s*([\w-]+)\s*$", line)
        if m:
            pinned[m.group(1)] = m.group(2)

    for key, controls_path in PIN_KEY_TO_PATH.items():
        recorded = pinned.get(key)
        if not recorded:
            report.add(
                f"session_pin.{key}.recorded", False,
                f"key '{key}' missing from session_pin.txt",
            )
            continue
        if recorded.startswith("TBD"):
            report.add(
                f"session_pin.{key}.recorded", False,
                f"placeholder TBD value: {recorded!r}",
            )
            continue
        report.add(f"session_pin.{key}.recorded", True)

        live = get_blob_sha(REPO_OWNER, CONTROLS_REPO, controls_path)
        if live is None:
            report.add(
                f"session_pin.{key}.live_fetch", False,
                f"could not fetch live blob SHA for {controls_path}",
            )
            continue
        ok = recorded == live
        report.add(
            f"session_pin.{key}.matches",
            ok,
            f"recorded {recorded[:12]}..., live {live[:12]}..." if not ok else "",
        )


def check_codeowners(report: Report) -> None:
    co_path = POLARIS_ROOT / ".github" / "CODEOWNERS"
    if not co_path.is_file():
        report.add("codeowners.exists", False, f"not found at {co_path}")
        return
    report.add("codeowners.exists", True)

    raw = co_path.read_text(encoding="utf-8")
    for path in EXPECTED_CODEOWNERS_PATHS:
        present = path in raw
        report.add(
            f"codeowners.covers[{path}]",
            present,
            f"path '{path}' not found in CODEOWNERS" if not present else "",
        )


def emit(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"\n{'=' * 60}")
    print(f"POLARIS Cage Verification")
    print(f"{'=' * 60}\n")

    for c in report.checks:
        mark = "OK   " if c.passed else "FAIL "
        print(f"  [{mark}] {c.name}")
        if c.detail:
            print(f"          {c.detail}")

    overall = "PASSED" if report.passed else "FAILED"
    print(f"\n{'=' * 60}")
    print(f"OVERALL: {overall}")
    print(f"{'=' * 60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify POLARIS cage state")
    parser.add_argument(
        "--polaris-only", action="store_true",
        help="Skip cross-repo checks against polaris-controls",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON report instead of human-readable",
    )
    args = parser.parse_args()

    report = Report()

    # POLARIS branch protections
    check_protection(
        report, REPO_OWNER, POLARIS_REPO, "polaris", EXPECTED_PROTECTION_POLARIS
    )
    check_protection(
        report, REPO_OWNER, POLARIS_REPO, "main", EXPECTED_PROTECTION_POLARIS
    )

    # polaris-controls protections + session pin (cross-repo)
    if not args.polaris_only:
        check_protection(
            report, REPO_OWNER, CONTROLS_REPO, "main", EXPECTED_PROTECTION_CONTROLS
        )
        check_session_pin(report)

    # CODEOWNERS file
    check_codeowners(report)

    emit(report, args.json)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
