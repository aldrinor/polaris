"""Migrate BPEI → ambiguity_detector references per I-naming-001 plan iter 3.

Per Codex iter-3 APPROVE:
- Test fixtures with literal 'BPEI' as adversarial probe input → PRESERVE.
- Feature-name references → renamed per the convention below.
- Memory filename 'bpei_phantom_completion_lessons.md' → PRESERVE (commemorative).
- Module path 'polaris_v6.bpei' → 'polaris_v6.ambiguity_detector' (rename).
- 'src/polaris_v6/bpei/' path → 'src/polaris_v6/ambiguity_detector/' (rename).
"""
import re
import sys
from pathlib import Path

ROOT = Path("C:/POLARIS")

# Files to migrate (per Codex iter-3 APPROVE'd plan). Test-input fixtures excluded.
FILES = [
    # src/ comment/docstring updates (Python)
    "src/polaris_v6/ambiguity_detector/ambiguity_detector.py",
    "src/polaris_v6/memory/__init__.py",
    "src/polaris_v6/api/ambiguity.py",
    "src/polaris_graph/api/audit_bundle_route.py",
    "src/polaris_graph/api/intake.py",
    "src/polaris_graph/api/intake_route.py",
    "src/polaris_graph/api/__init__.py",
    "src/polaris_graph/audit_bundle/bundle_schema.py",
    "src/polaris_graph/audit_bundle/manifest_builder.py",
    "src/polaris_graph/intake/cluster_labeler.py",
    "src/polaris_graph/intake/disambiguation_clusterer.py",
    "src/polaris_graph/intake/__init__.py",
    "src/polaris_graph/scope/scope_decision.py",
    # tests/ comment updates (preserve test-data literals)
    "tests/e2e/frontend_replay_smoke.py",
    "tests/polaris_graph/audit_bundle/test_bundle_builder.py",
    "tests/polaris_graph/followup/test_agent.py",
    "tests/polaris_graph/golden/test_slice_004_goldens.py",
    "tests/v6/test_api_ambiguity.py",
    "tests/v6/test_run_benchmark_script.py",
    # Scripts
    "scripts/autoloop/backfill_pre_bootstrap_verdicts.py",
    "scripts/screenshot_walkthrough.js",
    # Frontend (web/)
    "web/app/dashboard/page.tsx",
    "web/app/generation/page.tsx",
    "web/app/intake/page.tsx",
    "web/app/retrieval/page.tsx",
    "web/lib/api.ts",
    # Frontend tests (feature-name only; preserve typed-in-search-box probes)
    "web/tests/e2e/command_palette_adversarial.spec.ts",
    "web/tests/e2e/command_palette_suggest.spec.ts",
    "web/tests/e2e/f2_walkthrough.spec.ts",
    "web/tests/e2e/intake_disambiguation.spec.ts",
    # Docs (CURRENT)
    "docs/carney_delivery_plan_v6_2.md",
    "docs/carney_handover/5min_video_script.md",
    "docs/blockers.md",
    "docs/blocked/blocked_on_user_action_tracker.md",
    "docs/substrate_audit_2026-05-01.md",
    "docs/v6_substrate_audit_2026-05-01.md",
    "docs/task_acceptance_matrix.yaml",
    "docs/benchmark/scoring_rubric.md",
    "docs/walkthroughs/1.8/briefing.md",
    "docs/walkthroughs/1.8/recording_template.md",
    "docs/walkthroughs/2B.7/test_inputs.md",  # name-refs only; literal probes preserved
    "docs/walkthroughs/2C.6/briefing.md",
    "docs/walkthroughs/2C.6/test_inputs.md",
    "docs/walkthroughs/1.8/test_inputs.md",
    "docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md",
    # walkthroughs/5.1/full_corpus_test_inputs.md — line 22 comment only, line 20 literal preserved
    "docs/walkthroughs/5.1/full_corpus_test_inputs.md",
]

# Phrase-level replacements (longest first to avoid partial overlaps).
# These intentionally do NOT include bare 'BPEI' (that would catch test-input literals).
PHRASE_REPLACEMENTS = [
    # User-facing UI copy
    ("BPEI ambiguity detector substrate", "ambiguity detector substrate"),
    ("BPEI ambiguity detector", "ambiguity detector"),
    ("F2 BPEI ambiguity detector", "F2 ambiguity detector"),
    ("F2 BPEI ambiguity", "F2 ambiguity"),
    ("BPEI ambiguity expected", "ambiguity expected"),
    ("BPEI ambiguity should fire", "ambiguity detector should fire"),
    ("BPEI ambiguity", "ambiguity"),
    ("BPEI spine substrate", "research-pipeline substrate"),
    ("BPEI spine", "research pipeline"),
    ("full BPEI spine", "full research pipeline"),
    ("BPEI front half", "scope + intake"),
    ("BPEI front-half", "scope + intake"),
    ("BPEI front-half pipeline", "scope + intake pipeline"),
    ("BPEI retrieval half", "retrieval"),
    ("BPEI retrieval-half", "retrieval"),
    ("BPEI generator", "generator"),
    ("BPEI chain", "research chain"),
    ("BPEI guard", "ambiguity guard"),
    ("BPEI question", "ambiguity-checked question"),
    ("BPEI fix substrate", "ambiguity detector substrate"),
    ("BPEI failure pattern", "ambiguity-failure pattern (memory: bpei_phantom_completion_lessons.md)"),
    # Module path
    ("polaris_v6.bpei.ambiguity_detector", "polaris_v6.ambiguity_detector.ambiguity_detector"),
    ("polaris_v6.bpei", "polaris_v6.ambiguity_detector"),
    # Filesystem path
    ("src/polaris_v6/bpei/ambiguity_detector.py", "src/polaris_v6/ambiguity_detector/ambiguity_detector.py"),
    ("src/polaris_v6/bpei/", "src/polaris_v6/ambiguity_detector/"),
    ("src/polaris_v6/bpei", "src/polaris_v6/ambiguity_detector"),
]

# Per-file SKIP regexes — these lines/patterns are preserved verbatim
# even if they contain replaceable phrases.
# Format: {file_relpath: [regex, ...]}
SKIP_LINES = {
    # docs/walkthroughs/5.1/full_corpus_test_inputs.md line 20:
    # `**Query:** "What is the BPEI methodology…"` is a literal adversarial probe.
    "docs/walkthroughs/5.1/full_corpus_test_inputs.md": [
        re.compile(r'^\*\*Query:\*\*.*"What is the BPEI'),
    ],
    # web/tests/e2e specs: any line that types `"BPEI"` into a search box is preserved.
    # Pattern: lines containing `.fill(.*BPEI` or `.type(.*BPEI`.
    "web/tests/e2e/command_palette_adversarial.spec.ts": [
        re.compile(r"\.fill\([^)]*BPEI"),
        re.compile(r"\.type\([^)]*BPEI"),
    ],
    "web/tests/e2e/command_palette_suggest.spec.ts": [
        re.compile(r"\.fill\([^)]*BPEI"),
        re.compile(r"\.type\([^)]*BPEI"),
    ],
    "web/tests/e2e/f2_walkthrough.spec.ts": [
        re.compile(r"\.fill\([^)]*BPEI"),
        re.compile(r"\.type\([^)]*BPEI"),
    ],
    "web/tests/e2e/intake_disambiguation.spec.ts": [
        re.compile(r"\.fill\([^)]*BPEI"),
        re.compile(r"\.type\([^)]*BPEI"),
    ],
    # tests/v6/test_api_ambiguity.py: function name `test_check_ambiguity_bpei_pattern`
    # is preserved (commemorates the test pattern, not production code).
    "tests/v6/test_api_ambiguity.py": [
        re.compile(r"^def test_check_ambiguity_bpei_pattern"),
        re.compile(r'""".*BPEI pattern'),
    ],
    # tests/v6/test_run_benchmark_script.py line 80: literal probe input
    "tests/v6/test_run_benchmark_script.py": [
        re.compile(r'"What is BPEI\?"'),
    ],
}


def migrate_file(path: Path) -> tuple[int, list[int]]:
    """Returns (replacements_made, skipped_line_numbers)."""
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    skip_patterns = SKIP_LINES.get(rel, [])
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    skipped_lines = []
    replacements = 0
    for i, line in enumerate(lines):
        if any(p.search(line) for p in skip_patterns):
            skipped_lines.append(i + 1)
            continue
        new_line = line
        for old, new in PHRASE_REPLACEMENTS:
            if old in new_line:
                new_line = new_line.replace(old, new)
                replacements += 1
        lines[i] = new_line
    new_text = "\n".join(lines)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return replacements, skipped_lines


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total_replacements = 0
    total_files_changed = 0
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            print(f"SKIP (missing): {rel}")
            continue
        n, skipped = migrate_file(p)
        if n > 0:
            total_replacements += n
            total_files_changed += 1
            note = f" (preserved lines: {skipped})" if skipped else ""
            print(f"{rel}: {n} replacements{note}")
        elif skipped:
            print(f"{rel}: 0 replacements, preserved lines: {skipped}")
    print(f"\nTotal: {total_replacements} replacements across {total_files_changed} files")


if __name__ == "__main__":
    main()
