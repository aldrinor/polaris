"""Enumerate stale `.codex/` files that should be archived under
archive/2026-05-11-root-hygiene/codex_historical/.

KEEP: current Issue subdirs (.codex/I-eval-004..008, I-doc-001..002, I-beat-001..003, etc.),
canonical protocol docs (AUDIT_CYCLE_PROTOCOL.md, REVIEW_BRIEF_FORMAT.md, LOOP_PROTOCOL.md,
codex_red_team_checklist.md), the issue tracking subdir if any.

ARCHIVE: historical review-output files dropped at .codex/ root (m_int_*_review_output.md,
m26_*_brief.md, md1_*, md2_*, g2_*, cleanup_pr_1_dryrun_*, etc.) and obsolete subdirs
(audit_v32_baseline, faithfulness_gap, I-bug-085 if closed) that pre-date the issue-driven
workflow."""
import os
import re
import sys
from pathlib import Path

CODEX = Path("C:/POLARIS/.codex")

# Files explicitly kept at .codex root (canonical protocol + active config)
# Patched post Codex iter-2 adjudication: config.toml is active runtime config.
KEEP_FILES = {
    "AUDIT_CYCLE_PROTOCOL.md",
    "REVIEW_BRIEF_FORMAT.md",
    "REVIEW_BRIEF_FORMAT_v2.md",
    "LOOP_PROTOCOL.md",
    "codex_red_team_checklist.md",
    "config.toml",
}

# Dir-name prefix patterns that are CURRENT (keep)
# slices/ added post Codex iter-2 adjudication — load-bearing per 9
# production references (tests/polaris_graph/golden/test_slice_002..003_goldens.py
# fall back to .codex/slices/slice_NNN/golden_drafts/; src/polaris_graph/
# {api,audit_bundle}/*.py cite slice_002/004/005 architecture proposals).
CURRENT_DIR_PATTERNS = [
    re.compile(r"^I-"),
    re.compile(r"^GH\d+$"),
    re.compile(r"^slices$"),
]

# Patterns for clearly archivable files at .codex/ root
ARCHIVE_FILE_PATTERNS = [
    re.compile(r"^m_int_.*_review_output\.md$"),
    re.compile(r"^m26_.*_brief\.md$"),
    re.compile(r"^m26_.*_round\d+_brief\.md$"),
    re.compile(r"^md1_.*_brief\.md$"),
    re.compile(r"^md2_.*_brief\.md$"),
    re.compile(r"^g2_.*\.md$"),
    re.compile(r"^g2_.*\.txt$"),
    re.compile(r"^cleanup_pr_\d+_.*\.md$"),
    re.compile(r"^cleanup_pr_\d+_.*\.txt$"),
    # Post Codex iter-2 adjudication (decommissioning of tracked historical workflow artifacts):
    re.compile(r"^REVIEW_BRIEF\.md$"),
    re.compile(r"^ROUND_N_BRIEF_TEMPLATE\.md$"),
    re.compile(r"^autoloop_v2_protocol_review_brief\.md$"),
    re.compile(r"^carney_delivery_plan_FINAL_review_brief\.md$"),
    re.compile(r"^loop_state\.json$"),
    re.compile(r"^m\d+_code_audit.*\.md$"),
    re.compile(r"^m\d+[a-z]?_(?:code_audit|verdict_only|bundle_code_audit|fix_plan_review|m\d+_code_audit).*\.md$"),
    re.compile(r"^md3_verdict_brief\.md$"),
    re.compile(r"^md5_.*verdict_brief\.md$"),
    re.compile(r"^md5_verdict_brief\.md$"),
    re.compile(r"^m\d+[a-z]+_code_audit.*\.md$"),
    re.compile(r"^phase_c_plan\.md$"),
    re.compile(r"^phase_d_milestones_.*\.md$"),
    re.compile(r"^plan_amendment_skip_road_b_reset_verdict_iter_\d+\.txt$"),
    re.compile(r"^pr_b_dna_doc_updates_review.*\.(?:md|txt)$"),
    re.compile(r"^pr_b2_relocate_polaris_controls_review.*\.(?:md|txt)$"),
    re.compile(r"^pr_d_mechanical_gates_review.*\.(?:md|txt)$"),
    re.compile(r"^pr_e_open_issues_review.*\.(?:md|txt)$"),
    re.compile(r"^shippable_plan.*_review_brief\.md$"),
    re.compile(r"^test_failure_triage.*_brief\.md$"),
    re.compile(r"^triage_executed.*_brief\.md$"),
    re.compile(r"^v(?:17|23|27|28|29|30)_.*_brief\.md$"),
    re.compile(r"^walkthrough_2026_05_04\.md$"),
]

# Dirs at .codex/ root that pre-date issue-driven workflow
# Expanded post Codex iter-2 adjudication.
ARCHIVE_DIR_PATTERNS = [
    re.compile(r"^audit_v32_baseline$"),
    re.compile(r"^faithfulness_gap$"),
    re.compile(r"^continuous$"),
    re.compile(r"^deep_dive_round_\d+_.*$"),
    re.compile(r"^next_issue_pick.*$"),
    re.compile(r"^next_pick_post_cj$"),
    re.compile(r"^round_[2-5]$"),
    re.compile(r"^runs$"),
    re.compile(r"^strategic_review_high_quality$"),
    re.compile(r"^task_briefs$"),
    re.compile(r"^walkthrough_screenshots.*$"),
]


def categorize_codex_root(name: str, is_dir: bool) -> tuple[str, str]:
    if is_dir:
        for pat in CURRENT_DIR_PATTERNS:
            if pat.match(name):
                return "KEEP", "current issue-driven dir"
        for pat in ARCHIVE_DIR_PATTERNS:
            if pat.match(name):
                return "ARCHIVE", f"pre-issue-driven dir: {pat.pattern}"
        return "INSPECT", "unrecognized dir at .codex/ root"
    else:
        if name in KEEP_FILES:
            return "KEEP", "canonical protocol doc"
        for pat in ARCHIVE_FILE_PATTERNS:
            if pat.match(name):
                return "ARCHIVE", f"historical review output: {pat.pattern}"
        return "INSPECT", "unrecognized file at .codex/ root"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    entries = sorted(os.listdir(CODEX))
    keep, archive, inspect = [], [], []
    for name in entries:
        full = CODEX / name
        is_dir = full.is_dir()
        cat, reason = categorize_codex_root(name, is_dir)
        marker = "[D]" if is_dir else "[F]"
        line = f"{marker} {name} — {reason}"
        if cat == "KEEP":
            keep.append(line)
        elif cat == "ARCHIVE":
            archive.append(line)
        else:
            inspect.append(line)

    out_path = Path("state/polaris_restart/i_hygiene_001_codex_inventory.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "# I-hygiene-001 .codex/ inventory",
        "",
        f"Source: `{CODEX}` enumerated 2026-05-11.",
        f"Total entries: {len(entries)} | KEEP: {len(keep)} | ARCHIVE: {len(archive)} | INSPECT: {len(inspect)}",
        "",
        "## KEEP (current issue-driven dirs + canonical protocol docs)",
        "",
        *keep,
        "",
        "## ARCHIVE (historical review outputs / pre-issue-driven dirs → archive/2026-05-11-root-hygiene/codex_historical/)",
        "",
        *archive,
        "",
        "## INSPECT (needs Codex adjudication)",
        "",
        *inspect,
    ]
    out_path.write_text("\n".join(body), encoding="utf-8")
    print(f"saved {out_path}")
    print(f"KEEP={len(keep)} ARCHIVE={len(archive)} INSPECT={len(inspect)}")


if __name__ == "__main__":
    main()
