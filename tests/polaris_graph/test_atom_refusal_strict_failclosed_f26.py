"""F26 (I-arch-004 A3, P2): atom-refusal strict-mode fail-CLOSED.

Regression for the fail-OPEN bug in generate_multi_section_report's post-hoc
atom-refusal validation hook:

  - strict mode + EMPTY atom_catalog was silently SKIPPED
    (mode="skipped_empty_catalog") — the section shipped UN-VALIDATED as if it
    had passed.
  - a validator exception was swallowed for the WHOLE loop — one section's
    failure aborted validation for every section, all shipping un-validated.
  - only total_words was recomputed after strict refusal replacement, so the
    verified tally (total_sentences_verified) over-counted: a refused sentence
    replaced by a refusal block was still counted as verified prose.

The fix (_apply_atom_refusal_validation):
  - strict + empty catalog OR strict + validator-raise -> that section is marked
    atom_validation_degraded=True (distinct, testable signal; no
    atom_validation_result so it stays out of the "validated" tally), loop
    continues (per-section isolation).
  - strict + refusal -> sr.sentences_verified decremented by refusal_count
    (clamped at 0) so the verified tally is HONEST.
  - log_only keeps its original advisory fail-soft semantics.
  - off mode is a no-op (byte-identical).

These assert behavior on the extracted helper directly (it mutates the passed
SectionResult list in place), which is the exact code path the async entrypoint
calls.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.claim_atom_extractor import ClaimAtom
from src.polaris_graph.generator.multi_section_generator import (
    SectionResult,
    _apply_atom_refusal_validation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_atom(aid: str, value: str, endpoint: str = "HbA1c") -> ClaimAtom:
    return ClaimAtom(
        atom_id=aid,
        evidence_id="ev_001",
        span_start=0,
        span_end=100,
        literal_text=f"placeholder for {aid}",
        entity="tirzepatide",
        endpoint=endpoint,
        comparator="",
        timepoint="40 weeks",
        value=value,
        unit="percentage points",
        primary_section="Efficacy",
        section_tags=("Efficacy",),
        tier="T1",
        value_signed=value.startswith("-"),
        confidence="high",
        provenance_class="open_access",
        source_paper_title="placeholder",
    )


def _section(
    title: str,
    *,
    verified_text: str,
    sentences_verified: int,
    atom_catalog: dict | None = None,
    dropped: bool = False,
) -> SectionResult:
    return SectionResult(
        title=title,
        focus="focus",
        ev_ids_assigned=["ev_001"],
        raw_draft="draft",
        rewritten_draft="draft",
        verified_text=verified_text,
        biblio_slice=[],
        sentences_verified=sentences_verified,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=dropped,
        atom_catalog=atom_catalog if atom_catalog is not None else {},
    )


# ---------------------------------------------------------------------------
# ACCEPT criterion: strict + empty catalog -> flagged/degraded (not silent ok)
# ---------------------------------------------------------------------------

def test_strict_empty_catalog_is_degraded_not_silent_ok():
    sr = _section(
        "Mechanism",
        verified_text="A claim sentence [#ev:ev_001:0-10].",
        sentences_verified=3,
        atom_catalog={},  # empty -> un-validatable
    )
    replacements, degraded = _apply_atom_refusal_validation([sr], "strict")

    # The section is explicitly DEGRADED — not the prior silent
    # "skipped_empty_catalog" benign pass.
    assert sr.atom_validation_degraded is True
    assert sr.atom_validation_mode == "strict_degraded_empty_catalog"
    # No validation result -> stays OUT of any "validated" tally.
    assert sr.atom_validation_result is None
    assert degraded == 1
    assert replacements == 0


def test_log_only_empty_catalog_stays_benign_skip():
    """log_only is advisory: empty catalog is a benign skip, NOT degraded."""
    sr = _section(
        "Mechanism",
        verified_text="A claim sentence [#ev:ev_001:0-10].",
        sentences_verified=3,
        atom_catalog={},
    )
    replacements, degraded = _apply_atom_refusal_validation([sr], "log_only")

    assert sr.atom_validation_degraded is False
    assert sr.atom_validation_mode == "skipped_empty_catalog"
    assert degraded == 0
    assert replacements == 0


# ---------------------------------------------------------------------------
# Per-section isolation: a validator raise degrades ONLY that section
# ---------------------------------------------------------------------------

def test_strict_validator_raise_isolated_to_failing_section(monkeypatch):
    good_atoms = {"atom_001": _make_atom("atom_001", "-2.01")}
    bad = _section(
        "Boom",
        verified_text="The HbA1c reduction was 2.0 percentage points [atom_001].",
        sentences_verified=2,
        atom_catalog=good_atoms,
    )
    good = _section(
        "Fine",
        verified_text="Narrative prose with no quantitative claim here.",
        sentences_verified=2,
        atom_catalog=good_atoms,
    )

    import src.polaris_graph.generator.atom_refusal_validator as _arv

    real_validate = _arv.validate_section

    def _flaky(section_text, *, section_id, section_title, catalog):
        if section_title == "Boom":
            raise RuntimeError("validator exploded")
        return real_validate(
            section_text,
            section_id=section_id,
            section_title=section_title,
            catalog=catalog,
        )

    monkeypatch.setattr(_arv, "validate_section", _flaky)

    replacements, degraded = _apply_atom_refusal_validation([bad, good], "strict")

    # The failing section is degraded (fail-closed).
    assert bad.atom_validation_degraded is True
    assert bad.atom_validation_mode == "strict_degraded_validator_error"
    assert bad.atom_validation_result is None
    # The healthy section was STILL validated (loop did not abort).
    assert good.atom_validation_degraded is False
    assert good.atom_validation_result is not None
    assert good.atom_validation_mode == "strict"
    assert degraded == 1


def test_log_only_validator_raise_is_fail_soft_not_degraded(monkeypatch):
    atoms = {"atom_001": _make_atom("atom_001", "-2.01")}
    sr = _section(
        "Boom",
        verified_text="The HbA1c reduction was 2.0 percentage points [atom_001].",
        sentences_verified=2,
        atom_catalog=atoms,
    )
    import src.polaris_graph.generator.atom_refusal_validator as _arv

    def _boom(*a, **k):
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(_arv, "validate_section", _boom)

    replacements, degraded = _apply_atom_refusal_validation([sr], "log_only")

    # log_only is advisory -> NOT degraded on a validator error.
    assert sr.atom_validation_degraded is False
    assert degraded == 0


# ---------------------------------------------------------------------------
# Honest count recompute: strict refusal decrements sentences_verified
# ---------------------------------------------------------------------------

def test_strict_refusal_decrements_verified_count_honestly(monkeypatch):
    sr = _section(
        "Efficacy",
        verified_text="Two claims here that will be refused.",
        sentences_verified=5,
        atom_catalog={"atom_001": _make_atom("atom_001", "-2.01")},
    )

    import src.polaris_graph.generator.atom_refusal_validator as _arv
    from src.polaris_graph.generator.atom_refusal_validator import (
        GapRecord,
        RefusalAction,
        RefusalReason,
        SectionValidationResult,
    )

    # Two refused sentences -> refusal_count == 2.
    refused_records = [
        GapRecord(
            section_id="efficacy",
            section_title="Efficacy",
            sentence_index=0,
            original_sentence="claim one",
            rendered_text="[REFUSED]",
            action=RefusalAction.REFUSED,
            reason=RefusalReason.MISSING_ATOM_CITATION,
        ),
        GapRecord(
            section_id="efficacy",
            section_title="Efficacy",
            sentence_index=1,
            original_sentence="claim two",
            rendered_text="[REFUSED]",
            action=RefusalAction.REFUSED,
            reason=RefusalReason.MISSING_ATOM_CITATION,
        ),
    ]
    fake = SectionValidationResult(
        section_id="efficacy",
        section_title="Efficacy",
        original_text=sr.verified_text,
        rendered_text="[REFUSED]\n\n[REFUSED]",
        gap_records=refused_records,
    )
    assert fake.refusal_count == 2

    monkeypatch.setattr(
        _arv, "validate_section", lambda *a, **k: fake
    )

    replacements, degraded = _apply_atom_refusal_validation([sr], "strict")

    assert replacements == 2
    assert degraded == 0
    # 5 verified - 2 refused = 3 honest verified sentences.
    assert sr.sentences_verified == 3
    assert sr.refusal_count == 2
    assert sr.verified_text == "[REFUSED]\n\n[REFUSED]"
    # The aggregate the entrypoint re-sums after the hook is now honest.
    total_verified = sum(s.sentences_verified for s in [sr])
    assert total_verified == 3


def test_strict_refusal_decrement_clamped_at_zero(monkeypatch):
    sr = _section(
        "Efficacy",
        verified_text="One verified sentence.",
        sentences_verified=1,
        atom_catalog={"atom_001": _make_atom("atom_001", "-2.01")},
    )
    import src.polaris_graph.generator.atom_refusal_validator as _arv
    from src.polaris_graph.generator.atom_refusal_validator import (
        GapRecord,
        RefusalAction,
        RefusalReason,
        SectionValidationResult,
    )

    records = [
        GapRecord(
            section_id="efficacy",
            section_title="Efficacy",
            sentence_index=i,
            original_sentence="claim",
            rendered_text="[REFUSED]",
            action=RefusalAction.REFUSED,
            reason=RefusalReason.MISSING_ATOM_CITATION,
        )
        for i in range(3)  # refusal_count 3 > sentences_verified 1
    ]
    fake = SectionValidationResult(
        section_id="efficacy",
        section_title="Efficacy",
        original_text=sr.verified_text,
        rendered_text="[REFUSED]",
        gap_records=records,
    )
    monkeypatch.setattr(_arv, "validate_section", lambda *a, **k: fake)

    _apply_atom_refusal_validation([sr], "strict")

    # Clamp: never negative.
    assert sr.sentences_verified == 0


# ---------------------------------------------------------------------------
# OFF mode is a no-op (byte-identical)
# ---------------------------------------------------------------------------

def test_off_mode_is_noop():
    sr = _section(
        "Efficacy",
        verified_text="Some prose [#ev:ev_001:0-10].",
        sentences_verified=4,
        atom_catalog={"atom_001": _make_atom("atom_001", "-2.01")},
    )
    before_text = sr.verified_text
    replacements, degraded = _apply_atom_refusal_validation([sr], "off")

    assert replacements == 0
    assert degraded == 0
    assert sr.atom_validation_degraded is False
    assert sr.atom_validation_mode == "off"  # untouched default
    assert sr.atom_validation_result is None
    assert sr.sentences_verified == 4
    assert sr.verified_text == before_text


def test_dropped_and_empty_text_sections_skipped():
    """Dropped / empty-text sections are skipped in every mode (no degrade)."""
    dropped = _section(
        "Dropped",
        verified_text="text",
        sentences_verified=0,
        atom_catalog={},
        dropped=True,
    )
    empty = _section(
        "Empty",
        verified_text="",
        sentences_verified=0,
        atom_catalog={},
    )
    replacements, degraded = _apply_atom_refusal_validation(
        [dropped, empty], "strict"
    )
    assert degraded == 0
    assert dropped.atom_validation_degraded is False
    assert empty.atom_validation_degraded is False
