"""scripts/restart/open_github_issues.py

PR-E: parse state/polaris_restart/issue_breakdown.md and open GitHub Issues
on aldrinor/polaris in the linear DAG order encoded by `Blocked by` /
`Blocks` fields.

Per cleanup_audit.md PR-E scope + plan §6 canonical 10-PR table. Each
Issue body uses the §3 issue body template:

    ## Scope
    ## Foundation refs
    ## Acceptance criteria
    ## Out of scope
    ## Adversarial inputs
    ## LOC estimate
    ## Per-Issue artifacts required at PR open
    ## Blocks

Modes:
- --dry-run: parse + render bodies + print to stdout. NO gh API calls.
  Output captured to state/polaris_restart/pr_e_issues_dryrun.txt for
  Codex review.
- --apply: parse + render + call `gh issue create` for each Issue.
  Records {issue_id: github_issue_number} to
  state/polaris_restart/issue_github_map.json.

Hard preconditions (Apply mode):
- gh CLI authenticated as aldrinor (verified by `gh auth status`).
- PR-D codex-required.yml workflow committed (verified by file existence).
- branch protection on aldrinor/polaris configured (USER ACTION 2 done).

Usage:
    python scripts/restart/open_github_issues.py --dry-run
    python scripts/restart/open_github_issues.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUE_BREAKDOWN = REPO_ROOT / "state" / "polaris_restart" / "issue_breakdown.md"
ISSUE_MAP = REPO_ROOT / "state" / "polaris_restart" / "issue_github_map.json"
DRYRUN_TRANSCRIPT = REPO_ROOT / "state" / "polaris_restart" / "pr_e_issues_dryrun.txt"
GH_REPO = "aldrinor/polaris"

# PR-E iter 1 PRE-002 fix: implement §3a default Phase/Feature inheritance
# from issue prefix. Most Issues in issue_breakdown.md don't repeat
# Phase/Feature fields; they inherit from §3a defaults. Without this,
# 122 of 133 Issues would render as "(unspecified)".
#
# Mapping per state/polaris_restart/issue_breakdown.md §3a lines 114-125:
PHASE_BY_PREFIX: dict[str, str] = {
    "phase0": "0",
    "f1": "1",
    "f2": "1",
    "f3": "1",
    "f15": "1",
    "ecg": "1",
    "bug-079": "1",
    "bug-082": "1",
    "f4": "2A",
    "f5": "2A",
    "f7": "2A",
    "f8": "2A",
    "f9": "2A",
    "f6": "2B",
    "f10": "2B",
    "f13": "2B",
    "f14": "2B",
    "p2c": "2C polish",
    "f11": "3",
    "f12": "3",
    "bench": "3",
    "tpl": "3",
    "bug-084": "3",
    "sov": "4",
    "buf": "4.5",
    "hand": "5",
    "cj": "side-track",       # parallel — no phase number
    "anti": "side-track",
}

FEATURE_BY_PREFIX: dict[str, str] = {
    "phase0": "infra",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
    "f13": "F13",
    "f14": "F14",
    "f15": "F15",
    "ecg": "evidence-contract-gate",
    "p2c": "phase-2c-polish",
    "bench": "benchmark-templates",
    "tpl": "benchmark-templates",
    "sov": "sovereign-migration",
    "buf": "buffer",
    "hand": "handover",
    "cj": "crown-jewel-preservation",
    "anti": "anti-sycophancy-CI",
    "bug-079": "F1",            # 079 is intake/clinical_classifier
    "bug-082": "F15",           # 082 is audit-bundle health endpoint
    "bug-084": "F12-benchmark", # 084 is benchmark coverage scorer
}


def issue_id_prefix(issue_id: str) -> str:
    """Extract the prefix used for §3a defaults lookup.

    Examples:
        I-phase0-003 -> "phase0"
        I-f1-001     -> "f1"
        I-bug-079    -> "bug-079" (the bug number IS the disambiguator)
        I-cj-001     -> "cj"
        I-anti-002   -> "anti"
    """
    # Strip "I-" prefix and trailing "-NNN" issue number
    m = re.match(r"^I-(.+?)-([0-9]{3})$", issue_id)
    if not m:
        return ""
    prefix = m.group(1)
    if prefix == "bug":
        return f"bug-{m.group(2)}"  # disambiguate by bug number
    return prefix


def default_phase(issue_id: str) -> str:
    return PHASE_BY_PREFIX.get(issue_id_prefix(issue_id), "")


def default_feature(issue_id: str) -> str:
    return FEATURE_BY_PREFIX.get(issue_id_prefix(issue_id), "")

# PR-E iter 1 PRE-001 fix: bug-issue headers use `## §N I-bug-NNN — title`
# (not `### I-bug-NNN —`). Match BOTH ### (most issues) and ## §N (bug
# reissues) so we capture all 133 source Issues. Issue-id group 1 plus
# title group 2 unchanged.
ISSUE_HEADER_RE = re.compile(
    r"^(?:###|##\s+§[0-9]+)\s+(I-[a-z0-9]{2,8}-[0-9]{3})\s+[—-]\s+(.+?)(?:\s+\(reissued\))?$",
    re.M,
)
# Field pattern: matches `- **Name:** value` at line start; non-greedy on key
# so the same line with multiple `**Key:** value` pairs (e.g.
# `- **Phase:** 0 / **Feature:** infra`) splits correctly via repeated finditer.
FIELD_RE = re.compile(r"\*\*([A-Za-z][A-Za-z\s\-]*?):\*\*\s*([^\*\n]+?)(?=\s*\*\*[A-Za-z]|\s*$)")


def parse_issues(md_text: str) -> list[dict]:
    """Parse the issue_breakdown.md into a list of issue dicts.

    Each issue dict contains: id, title, body_fields (Phase, Scope, etc.).
    Body composition is done separately in render_body().

    Handles compound field lines like `- **Phase:** 0 / **Feature:** infra`
    by running FIELD_RE.finditer line-by-line so each `**Key:**` segment
    is treated as a separate field.
    """
    issues = []
    matches = list(ISSUE_HEADER_RE.finditer(md_text))
    # PR-E iter 3 PRE3-P2-002 fix: bound the LAST issue's block at the next
    # `## §N` section header (e.g. §31 doc-decommission, §32+ etc.) so any
    # tail bullets don't leak into the last Issue's parsed fields.
    SECTION_END_RE = re.compile(r"^##\s+§[0-9]+\s+", re.M)
    for i, match in enumerate(matches):
        issue_id = match.group(1)
        title_short = match.group(2).strip()
        start = match.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            # Last issue — search for the next ## §N header AFTER start
            tail = md_text[start:]
            section_match = SECTION_END_RE.search(tail)
            end = start + section_match.start() if section_match else len(md_text)
        block = md_text[start:end].strip()
        fields = {}
        # Walk line-by-line so multi-field lines are split correctly.
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            # Strip leading "- " (bullet)
            content = line[1:].strip()
            for fm in FIELD_RE.finditer(content):
                key = fm.group(1).strip()
                value = fm.group(2).strip().rstrip("/").strip()
                if key and value:
                    fields[key] = value
        issues.append({
            "id": issue_id,
            "title_short": title_short,
            "fields": fields,
            "raw_block": block,
        })
    return issues


def render_body(issue: dict, issue_total: int = 133) -> str:
    """Render an Issue body using the §3 template.

    Fills in §3 sections from parsed fields. Missing fields get explicit
    "(not specified in issue_breakdown.md)" markers so CI catches gaps.

    issue_total is the count of all parsed Issues, used in the trailing
    footer line "one of N opened by PR-E" (PR-E iter 2 PRE2-P2-001 fix
    making the count dynamic instead of a stale literal).
    """
    ISSUE_TOTAL = issue_total  # noqa: N806 — local alias used inside f-string template
    f = issue["fields"]
    # PR-E iter 1 PRE-002 fix: §3a Phase/Feature inheritance — explicit
    # field wins, otherwise default by issue-id prefix.
    # PR-E iter 2 PRE2-P1-001 fix: when explicit Feature has parenthetical
    # annotation like `F1 (intake)` for bug Issues, prefer the canonical
    # default-by-prefix value to keep label consistent with `feature-f1`
    # not `feature-f1-intake`.
    explicit_feature = f.get("Feature", "").strip()
    default_ft = default_feature(issue["id"])
    if explicit_feature and "(" in explicit_feature and default_ft:
        # Parenthetical annotation present + a canonical default exists -> default wins
        feature = default_ft
    else:
        feature = explicit_feature or default_ft or "(unspecified)"
    phase = f.get("Phase", "").strip() or default_phase(issue["id"]) or "(unspecified)"
    scope = f.get("Scope", "(unspecified)")
    acceptance = f.get("Acceptance", "(unspecified)")
    # PR-E iter 2 PRE2-P1-002 fix: source-of-truth uses both `Foundation refs`
    # AND `Foundation` (4 Issues). Read both keys and prefer the longer.
    foundation = f.get("Foundation refs", "") or f.get("Foundation", "")
    out_of_scope = f.get("Out of scope", "(none specified)")
    adversarial = f.get("Adversarial inputs", "(none specified)")
    loc = f.get("LOC estimate", "(unspecified)")
    user_blocked = f.get("User-blocked", "NO")
    blocked_by = f.get("Blocked by", "(none)")
    blocks = f.get("Blocks", "(none)")

    foundation_default_lines = [
        "- `state/polaris_restart/plan.md` §4 (master breakdown)",
        "- `polaris-controls/CHARTER.md` §1 + §3 + §4 + §7 (roles, LOC cap, immutable tests, visibility)",
        "- `polaris-controls/PLAN.md` (slice progression context)",
        f"- `docs/carney_delivery_plan_v6_2.md` Phase {phase} / Feature {feature}",
    ]
    if foundation:
        foundation_default_lines.append(f"- {foundation}  (Issue-specific)")
    foundation_block = "\n".join(foundation_default_lines)

    body = f"""## Phase / Feature

- **Phase:** {phase}
- **Feature:** {feature}

## Scope

{scope}

## Foundation refs

{foundation_block}

## Acceptance criteria

{acceptance}

## Out of scope

{out_of_scope}

## Adversarial inputs

{adversarial}

## LOC estimate

{loc} (≤200 per CHARTER §3)

## Per-Issue artifacts required at PR open (CHARTER §7)

- `.codex/{issue["id"]}/brief.md` (Claude-authored)
- `.codex/{issue["id"]}/codex_brief_verdict.txt` (Codex APPROVE)
- `.codex/{issue["id"]}/codex_diff.patch` (Claude-written diff with `# canonical-diff-sha256: <64-hex>` trailer)
- `.codex/{issue["id"]}/codex_diff_audit.txt` (Codex APPROVE on Red-Team checklist)
- `outputs/audits/{issue["id"]}/claude_audit.md` (Claude architect review)

## Blocks

- **Blocked by:** {blocked_by}
- **Blocks:** {blocks}
- **User-blocked:** {user_blocked}

---

_This Issue is one of {ISSUE_TOTAL} opened by PR-E from `state/polaris_restart/issue_breakdown.md` (Codex APPROVE iter 4). Branch convention: `bot/{issue["id"]}`. The codex-required.yml workflow (PR-D Codex APPROVE iter 7) gates merge on §3.0 5-artifact triple._
"""
    return body


def issue_label(issue: dict) -> list[str]:
    """Return GitHub labels for the Issue based on phase + feature.

    Labels normalized to lowercase + hyphenated; rejects any label with
    invalid GH characters (slash, asterisk, etc. — defense against bad
    parses leaking into labels).
    """
    f = issue["fields"]
    labels = []

    def safe_label(prefix: str, raw: str) -> str | None:
        v = raw.strip().lower().replace(" ", "-")
        # PR-E iter 3 PRE3-P2-003 fix: preserve `.` as `-` so Phase 4.5 -> phase-4-5
        # (was previously phase-45 because the dot was stripped by the alnum/hyphen
        # filter below, joining 4 and 5 with no separator).
        v = v.replace(".", "-")
        # Strip remaining non-alnum/hyphen chars
        v = re.sub(r"[^a-z0-9_-]+", "", v)
        # Collapse repeated hyphens
        v = re.sub(r"-+", "-", v).strip("-")
        if not v:
            return None
        return f"{prefix}-{v}"

    # PR-E iter 1 PRE-002 fix: same Phase/Feature inheritance as render_body
    # PR-E iter 2 PRE2-P1-001 fix: same parenthetical-annotation handling as
    # render_body so labels stay canonical (`feature-f1`, not `feature-f1-intake`).
    phase = f.get("Phase", "").strip() or default_phase(issue["id"])
    explicit_feature = f.get("Feature", "").strip()
    default_ft = default_feature(issue["id"])
    if explicit_feature and "(" in explicit_feature and default_ft:
        feature = default_ft
    else:
        feature = explicit_feature or default_ft
    if phase:
        lbl = safe_label("phase", phase)
        if lbl:
            labels.append(lbl)
    if feature:
        lbl = safe_label("feature", feature)
        if lbl:
            labels.append(lbl)
    # PR-E iter 1 PRE-003 fix: source values are `YES (account, billing, payment)`
    # etc. — the explanatory parenthetical follows YES. Match `YES` as a
    # whole-word prefix instead of exact equality.
    user_blocked_val = f.get("User-blocked", "").strip().upper()
    if user_blocked_val.startswith("YES"):
        labels.append("user-blocked")
    return labels


def gh_existing_labels() -> set[str]:
    """Return the set of label names that already exist on the repo.

    PR-E iter 3 PRE3-P2-001 fix: FAIL CLOSED on list error. Earlier
    version returned an empty set on error, which combined with
    `gh label create --force` would treat existing labels as missing
    and overwrite their metadata. Now: any error raises RuntimeError
    so the apply-mode caller aborts before Issue creation.
    """
    try:
        result = subprocess.run(
            ["gh", "label", "list", "--repo", GH_REPO, "--limit", "200", "--json", "name"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        return {entry["name"] for entry in data}
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"`gh label list` failed: {exc.stderr.strip()}") from exc
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"`gh label list` returned malformed JSON: {exc}") from exc


def gh_label_create(name: str, description: str = "Auto-created by PR-E") -> bool:
    """Create a single GH label, return True on success.

    PR-E iter 3 PRE3-P2-001 fix: drop `--force` flag. We only call this
    function for labels NOT in the existing-set (preflight has confirmed
    they don't exist), so create-not-update is the right semantic. If
    the label somehow exists (race condition), the create returns
    "already exists" which is treated as success.
    """
    try:
        subprocess.run(
            ["gh", "label", "create", name, "--repo", GH_REPO, "--description", description],
            capture_output=True, text=True, check=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        # If error is "already exists" -> ok (idempotent). Else fail.
        if "already exists" in (exc.stderr or "").lower():
            return True
        print(f"ERROR: gh label create '{name}' failed: {exc.stderr}", file=sys.stderr)
        return False


def ensure_labels_exist(needed_labels: set[str]) -> int:
    """PR-E iter 2 PRE2-P1-003 fix: label preflight.

    Compute the union of labels needed by all 133 Issues, list existing
    labels via `gh label list`, create the missing ones via `gh label
    create`. Return count of labels created. If any creation fails,
    abort before any Issue is created (Apply mode).
    """
    existing = gh_existing_labels()
    missing = needed_labels - existing
    if not missing:
        print(f"Label preflight: all {len(needed_labels)} required labels already exist")
        return 0
    print(f"Label preflight: {len(missing)} missing labels to create: {sorted(missing)}")
    created = 0
    for name in sorted(missing):
        if gh_label_create(name):
            created += 1
        else:
            raise RuntimeError(f"Label preflight failed: could not create '{name}'")
    print(f"Label preflight: created {created} labels")
    return created


def gh_issue_create(issue: dict, body: str, labels: list[str]) -> int | None:
    """Call `gh issue create` and return the new issue number, or None on error."""
    title = f'{issue["id"]} — {issue["title_short"]}'
    cmd = [
        "gh", "issue", "create",
        "--repo", GH_REPO,
        "--title", title,
        "--body", body,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # `gh issue create` returns the URL; extract the number.
        url = result.stdout.strip()
        m = re.search(r"/issues/(\d+)$", url)
        if m:
            return int(m.group(1))
        return None
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: gh issue create failed for {issue['id']}: {exc.stderr}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print rendered bodies without creating Issues")
    parser.add_argument("--apply", action="store_true", help="Actually create GitHub Issues via gh CLI")
    args = parser.parse_args()
    if not (args.dry_run or args.apply):
        parser.error("must specify --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply are mutually exclusive")

    md_text = ISSUE_BREAKDOWN.read_text(encoding="utf-8")
    issues = parse_issues(md_text)
    print(f"Parsed {len(issues)} Issues from {ISSUE_BREAKDOWN.name}")

    if args.dry_run:
        with DRYRUN_TRANSCRIPT.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"# PR-E dry-run transcript\n\nParsed {len(issues)} Issues.\n\n")
            for issue in issues:
                body = render_body(issue, issue_total=len(issues))
                labels = issue_label(issue)
                fh.write(f"\n---\n\n## WOULD CREATE Issue {issue['id']}\n\n")  # dry-run mode
                fh.write(f"**Title:** `{issue['id']} — {issue['title_short']}`\n\n")
                fh.write(f"**Labels:** {labels}\n\n")
                fh.write(f"### Body\n\n{body}\n")
        print(f"DRY RUN — wrote transcript to {DRYRUN_TRANSCRIPT}")
        print(f"Re-run with --apply after Codex APPROVE on the transcript.")
        return 0

    if args.apply:
        # Pre-flight gh auth check
        try:
            subprocess.run(["gh", "auth", "status", "--hostname", "github.com"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("ERROR: gh CLI not authenticated. Run `gh auth login`.", file=sys.stderr)
            return 1

        # PR-E iter 2 PRE2-P1-003 fix: label preflight. Compute the union of
        # all labels needed by all 133 Issues and ensure each exists on the
        # repo BEFORE attempting any `gh issue create`. Without this, the
        # first Issue with a missing label fails the create call.
        all_labels = set()
        for issue in issues:
            for lbl in issue_label(issue):
                all_labels.add(lbl)
        try:
            ensure_labels_exist(all_labels)
        except RuntimeError as exc:
            print(f"ERROR: label preflight failed — {exc}", file=sys.stderr)
            return 2

        existing_map = {}
        if ISSUE_MAP.exists():
            existing_map = json.loads(ISSUE_MAP.read_text(encoding="utf-8"))
        created = 0
        skipped = 0
        failed = 0
        for issue in issues:
            if issue["id"] in existing_map:
                print(f"SKIP {issue['id']} (already created as #{existing_map[issue['id']]})")
                skipped += 1
                continue
            # PR-E iter 3 PRE2-P2-001-PARTIAL fix: pass dynamic count to
            # apply path too (was previously falling back to hard-coded 133).
            body = render_body(issue, issue_total=len(issues))
            labels = issue_label(issue)
            print(f"CREATE {issue['id']}: {issue['title_short']}")
            number = gh_issue_create(issue, body, labels)
            if number is None:
                failed += 1
                continue
            existing_map[issue["id"]] = number
            # Persist after each successful create so we can resume on failure
            ISSUE_MAP.write_text(json.dumps(existing_map, indent=2, sort_keys=True), encoding="utf-8")
            created += 1
            print(f"  -> #{number}")

        print(f"\nDone: created={created}, skipped={skipped}, failed={failed}")
        if failed > 0:
            return 3
        return 0


if __name__ == "__main__":
    sys.exit(main())
