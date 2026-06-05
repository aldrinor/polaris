"""
Codex round 1 B-3 regression tests: refuse to ship report.md when
ZERO sections survived strict_verify.

Pre-fix behavior: if all sections failed Phase-4 verification, the
orchestrator would still concatenate Methods + Bibliography and write
an empty-findings report.md, then set status=fail_no_verified_prose
as a post-hoc flag.

Post-fix: the predicate `filter_verified_sections()` and the artifact
builder `build_no_verified_sections_abort_body()` are extracted as
pure functions so behavior tests can exercise them directly, without
mocking the whole async orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _FakeSection:
    """Minimal stand-in for multi_section_generator.SectionResult."""
    title: str
    verified_text: str
    dropped_due_to_failure: bool
    sentences_verified: int = 0
    sentences_dropped: int = 0
    regen_attempted: bool = False
    error: str | None = None


def test_b3_predicate_rejects_all_dropped() -> None:
    """If every section was dropped, the filter returns an empty list."""
    from scripts.run_honest_sweep_r3 import filter_verified_sections
    sections = [
        _FakeSection(title="Intro", verified_text="", dropped_due_to_failure=True),
        _FakeSection(title="Findings", verified_text="", dropped_due_to_failure=True),
    ]
    assert filter_verified_sections(sections) == []


def test_b3_predicate_rejects_empty_text_even_if_not_dropped() -> None:
    """A section that's not dropped but has empty verified_text is NOT
    a pass — otherwise a silent-degraded section would slip through."""
    from scripts.run_honest_sweep_r3 import filter_verified_sections
    sections = [
        _FakeSection(title="Hollow", verified_text="", dropped_due_to_failure=False),
    ]
    assert filter_verified_sections(sections) == []


def test_b3_predicate_keeps_real_section() -> None:
    from scripts.run_honest_sweep_r3 import filter_verified_sections
    sections = [
        _FakeSection(title="Intro", verified_text="", dropped_due_to_failure=True),
        _FakeSection(
            title="Findings",
            verified_text="## Findings\n\nReal content.",
            dropped_due_to_failure=False,
            sentences_verified=3,
        ),
    ]
    kept = filter_verified_sections(sections)
    assert len(kept) == 1
    assert kept[0].title == "Findings"


def test_b3_abort_body_is_pipeline_verdict_not_content() -> None:
    """The emitted markdown body must begin with 'Pipeline verdict' and
    NOT contain any of the normal sectioned-report headings."""
    from scripts.run_honest_sweep_r3 import build_no_verified_sections_abort_body
    sections = [
        _FakeSection(
            title="Dosing", verified_text="", dropped_due_to_failure=True,
            sentences_verified=0, sentences_dropped=12, regen_attempted=True,
            error="all_tokens_invalid",
        ),
        _FakeSection(
            title="Safety", verified_text="", dropped_due_to_failure=True,
            sentences_verified=0, sentences_dropped=9, regen_attempted=True,
            error="no_content_word_overlap",
        ),
    ]
    body = build_no_verified_sections_abort_body(
        "What is the efficacy of drug X?", sections,
    )
    assert "Pipeline verdict" in body
    assert "EVERY section failed Phase-4 strict_verify" in body
    # Per-section verdicts must expose the dropped counts
    assert "Dosing" in body
    assert "Safety" in body
    assert "dropped=12" in body
    assert "dropped=9" in body
    # Error reason must surface so operators can triage
    assert "all_tokens_invalid" in body or "'all_tokens_invalid'" in body
    # Must NOT look like a content report
    assert "## Findings" not in body
    assert "## Methods" not in body
    assert "## Bibliography" not in body


def test_b3_abort_body_handles_zero_sections() -> None:
    """Defensive: if the generator returned zero sections at all, the
    body must still render without error."""
    from scripts.run_honest_sweep_r3 import build_no_verified_sections_abort_body
    body = build_no_verified_sections_abort_body("Q?", [])
    assert "Pipeline verdict" in body
    assert "0 section(s)" in body


def test_b3_orchestrator_uses_extracted_helpers() -> None:
    """Source check: confirm the orchestrator branch delegates to the
    pure helpers, not an inline predicate / inline body string. This
    prevents the next refactor from silently re-introducing the old
    behavior."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    src = inspect.getsource(sweep.run_one_query)
    assert "filter_verified_sections(multi.sections)" in src
    assert "build_no_verified_sections_abort_body(" in src
    # The abort branch must still return BEFORE Methods assembly
    abort_idx = src.find("if not verified_sections:")
    # I-ready-016 (#1086): re-anchor the "abort returns BEFORE generation/Methods assembly" marker.
    # PG_GENERATOR_MODEL is now referenced EARLY (STORM/agentic/quantified blocks) — before the abort —
    # so it no longer marks the post-abort generation step. PG_EVALUATOR_MODEL first appears only in the
    # success-path generation/manifest block (after the abort), so it is the stable post-abort anchor.
    methods_idx = src.find("PG_EVALUATOR_MODEL")
    assert 0 < abort_idx < methods_idx


def test_b3_manifest_records_zero_verified() -> None:
    """Source check: the abort manifest still records sentences_verified=0
    and sections_dropped == sections_total, so downstream telemetry is honest."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    src = inspect.getsource(sweep.run_one_query)
    abort_idx = src.find("if not verified_sections:")
    # I-ready-016 (#1086): re-anchor the "abort returns BEFORE generation/Methods assembly" marker.
    # PG_GENERATOR_MODEL is now referenced EARLY (STORM/agentic/quantified blocks) — before the abort —
    # so it no longer marks the post-abort generation step. PG_EVALUATOR_MODEL first appears only in the
    # success-path generation/manifest block (after the abort), so it is the stable post-abort anchor.
    methods_idx = src.find("PG_EVALUATOR_MODEL")
    branch = src[abort_idx:methods_idx]
    assert '"sentences_verified": 0' in branch
    assert "sections_dropped" in branch
