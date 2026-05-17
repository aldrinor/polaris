#!/usr/bin/env python3
"""CI gate — block secret-bearing / non-slim .codex/** artifacts (I-sec-001 #535).

Invoked by ``.github/workflows/codex_artifact_gate.yml``. That workflow uses
``pull_request_target``, so this script runs from the trusted base ref; the
PR's own copy is never executed. PR content is inspected as data only.

For every changed ``.codex/**`` path in the PR (git status A/M/R/C — deletions
are ignored):
  * denylist — raw ``codex exec`` transcript filename patterns are rejected
    (verdict-only commit policy);
  * allowlist — only the slim per-issue artifact filenames are permitted;
  * content  — verdict/audit artifacts must validate as schema-bounded slim
    blocks via ``extract_codex_verdict.py validate``;
  * secret scan — every changed ``.codex/**`` file is scanned with
    ``scan_for_secrets.py --strict``.

Fast-passes (exit 0) when the PR changes no ``.codex/**`` path — so the gate
can be a *required* status check without deadlocking non-.codex PRs.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Raw codex-exec transcripts must never be committed (verdict-only policy).
DENY_RE = re.compile(
    r"(codex_.*review.*\.txt"
    r"|codex_.*audit_iter.*\.txt"
    r"|codex_.*_iter[0-9]+\.txt)$",
    re.I,
)
# Slim per-issue artifacts permitted under .codex/<issue_id>/.
ALLOWED_BASENAMES = {
    "brief.md", "diff_brief.md", "codex_brief_verdict.txt",
    "codex_diff_audit.txt", "codex_diff.patch",
}
FORCE_APPROVE_RE = re.compile(r".*_iter5_force_approve\.txt$")
# Artifacts whose content must be a schema-bounded slim verdict.
VALIDATE_RE = re.compile(
    r"(codex_brief_verdict\.txt|codex_diff_audit\.txt|.*_iter5_force_approve\.txt)$"
)


def changed_codex_paths(pr_dir: Path, base_branch: str) -> list[tuple[str, str]]:
    """[(status, path)] for changed .codex/** paths; deletions dropped."""
    subprocess.run(
        ["git", "-C", str(pr_dir), "fetch", "--no-tags", "--quiet",
         "origin", base_branch],
        check=False, capture_output=True,
    )
    r = subprocess.run(
        ["git", "-C", str(pr_dir), "diff", "--name-status",
         f"origin/{base_branch}...HEAD", "--", ".codex/"],
        capture_output=True, text=True, check=True,
    )
    out: list[tuple[str, str]] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0][0]
        if status == "D":
            continue
        out.append((status, parts[-1]))  # dest path (R/C put dest last)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr-checkout", required=True,
                    help="dir holding the PR head checkout (data only)")
    ap.add_argument("--base-branch", default="polaris")
    ap.add_argument("--scanner", required=True,
                    help="path to the trusted base scan_for_secrets.py")
    ap.add_argument("--validator", required=True,
                    help="path to the trusted base extract_codex_verdict.py")
    args = ap.parse_args()

    pr = Path(args.pr_checkout)
    changed = changed_codex_paths(pr, args.base_branch)
    if not changed:
        print("codex-artifact-gate: no .codex/** changes — PASS (fast)")
        return 0

    failures: list[str] = []
    for status, path in changed:
        base = Path(path).name
        fpath = pr / path
        if not FORCE_APPROVE_RE.match(base):
            if DENY_RE.search(base):
                failures.append(
                    f"{path}: raw codex exec transcript must not be committed "
                    "— commit only the slim verdict (verdict-only policy, "
                    "I-sec-001 #535)")
                continue
            if base not in ALLOWED_BASENAMES:
                failures.append(
                    f"{path}: filename not on the .codex/<id>/ allowlist "
                    f"{sorted(ALLOWED_BASENAMES)} (+ *_iter5_force_approve.txt)")
                continue
        if not fpath.is_file():
            continue  # rename edge with content elsewhere — nothing to scan
        if VALIDATE_RE.search(base):
            v = subprocess.run(
                [sys.executable, args.validator, "validate", str(fpath)],
                capture_output=True, text=True)
            if v.returncode != 0:
                failures.append(
                    f"{path}: not a schema-bounded slim verdict — "
                    f"{(v.stdout + ' ' + v.stderr).strip()}")
        s = subprocess.run(
            [sys.executable, args.scanner, str(fpath), "--strict"],
            capture_output=True, text=True)
        if s.returncode != 0:
            failures.append(
                f"{path}: secret pattern detected by scan_for_secrets")

    if failures:
        print("codex-artifact-gate: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"codex-artifact-gate: PASS — {len(changed)} .codex/** path(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
