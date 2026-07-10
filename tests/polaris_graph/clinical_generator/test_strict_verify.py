"""Tests for strict_verify — CLAUDE.md sec 9.1 invariant 3 enforcement."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.clinical_generator.strict_verify import (
    DEFAULT_MIN_CONTENT_OVERLAP,
    section_pass_rate,
    verify_sentence,
    verify_sentence_to_record,
)
from polaris_graph.clinical_generator.verified_report import VerifiedSentence
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Pool builders ----------

def _src(
    source_id: str = "src-1",
    full_text: str | None = None,
    snippet: str = "snippet text",
) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=snippet,
        full_text=full_text,
        full_text_available=full_text is not None,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


# ---------- no_provenance_token ----------

def test_sentence_without_token_fails():
    pool = _pool(_src(full_text="Aspirin reduced cardiovascular events in adults."))
    passed, reason = verify_sentence(
        "Aspirin works in adults.", pool
    )
    assert passed is False
    assert reason == "no_provenance_token"


def test_sentence_with_only_malformed_token_fails():
    pool = _pool(_src(full_text="x" * 200))
    passed, reason = verify_sentence(
        "Aspirin works [#ev::0-100].", pool
    )
    assert passed is False
    assert reason == "no_provenance_token"


def test_synthesis_claim_without_token_passes():
    pool = _pool(_src(full_text="Aspirin reduced cardiovascular events."))
    passed, reason = verify_sentence(
        "These trials together suggest moderate effect.",
        pool,
        is_synthesis_claim=True,
    )
    assert passed is True
    assert reason is None


def test_synthesis_claim_record_constructed_with_flag():
    pool = _pool(_src(full_text="Aspirin reduced cardiovascular events."))
    record = verify_sentence_to_record(
        "These trials together suggest moderate effect.",
        section_id="sec_x",
        pool=pool,
        is_synthesis_claim=True,
    )
    assert record.is_synthesis_claim is True
    assert record.verifier_pass is True
    assert record.provenance_tokens == []
    assert record.evaluator_agrees is True


# ---------- invalid_token ----------

def test_unknown_source_id_fails():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    passed, reason = verify_sentence(
        "Aspirin works [#ev:bogus:0-100].", pool
    )
    assert passed is False
    assert reason == "invalid_token"


# ---------- span_out_of_range ----------

def test_span_end_beyond_text_fails():
    pool = _pool(_src(source_id="src-1", full_text="short text"))
    passed, reason = verify_sentence(
        "Claim [#ev:src-1:0-9999].", pool
    )
    assert passed is False
    assert reason == "span_out_of_range"


def test_span_start_greater_than_end_fails():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    passed, reason = verify_sentence(
        "Claim [#ev:src-1:100-50].", pool
    )
    assert passed is False
    assert reason == "span_out_of_range"


# ---------- numeric_mismatch ----------

def test_numeric_decimal_in_sentence_not_in_span_fails():
    """Sentence claims '23.5%' but span only contains '18%'."""
    full_text = (
        "The trial enrolled adults with chronic pain and showed "
        "an event rate of 18% in the treatment arm."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"The trial showed event rate of 23.5% [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is False
    assert reason == "numeric_mismatch"


def test_numeric_match_passes_when_decimal_in_span():
    full_text = (
        "The trial enrolled 1247 adults with chronic pain. "
        "The event rate was 18.5% in treatment vs 24% control."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"The trial enrolled 1247 adults and showed event rate 18.5% in treatment [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"expected pass, got reason={reason}"


def test_sentence_with_no_decimals_skips_numeric_check():
    """No decimals in sentence -> numeric check trivially passes."""
    full_text = (
        "Adults with chronic pain showed clinical benefit "
        "from regular treatment."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults with chronic pain showed clinical benefit from treatment [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"expected pass, got reason={reason}"


# ---------- content-word-overlap gate REMOVED (2026-07-10 UNFREEZE, Fix 1) ----------

def test_low_content_overlap_no_longer_dropped():
    """2026-07-10 UNFREEZE (Fix 1): the lexical content-word-overlap gate was DELETED
    (it forced near-verbatim copying). A non-numeric sentence sharing no content words
    with its span is NO LONGER dropped by a lexical floor — the NLI entailment judge
    (off in these offline unit pools) is the semantic bar, so it now passes.
    """
    full_text = "Tomato basil mozzarella pizza dough recipe pasta"
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults with chronic pain experienced relief [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"overlap gate removed; expected pass, got reason={reason}"


def test_one_shared_word_no_longer_dropped():
    """Fix 1: with the overlap threshold gone, one (or zero) shared content word no
    longer fails — the sentence carries content, so only the numeric/percent/qualifier
    gates + the NLI judge remain."""
    full_text = "Adults entered the cafeteria for lunch."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults reported severe migraines after taking aspirin [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"overlap gate removed; expected pass, got reason={reason}"


def test_two_shared_words_pass_default_threshold():
    full_text = (
        "The randomized trial enrolled adults with chronic migraines "
        "and demonstrated significant aspirin benefit."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults experienced aspirin benefit for migraines [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"expected pass, got reason={reason}"


def test_explicit_min_overlap_zero_relaxes_check():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    passed, reason = verify_sentence(
        "Adults benefited [#ev:src-1:0-50].", pool, min_content_overlap=0
    )
    assert passed is True


def test_env_override_min_overlap_no_longer_gates(monkeypatch: pytest.MonkeyPatch):
    # Fix 1: PG_PROVENANCE_MIN_CONTENT_OVERLAP no longer gates strict_verify — the
    # content-word-overlap floor was DELETED, so raising the threshold has no effect
    # and a content-bearing sentence passes (the numeric/percent/qualifier/NLI bar
    # is what remains).
    monkeypatch.setenv("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "5")
    full_text = "Adults benefited from aspirin therapy in the trial."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults benefited from aspirin [#ev:src-1:0-{len(full_text)}].", pool
    )
    assert passed is True, f"overlap threshold no longer gates; got reason={reason}"


# ---------- multi-token sentences ----------

def test_two_tokens_combined_spans_satisfy_check():
    full_a = "Trial enrolled adults with chronic migraines."
    full_b = "Aspirin demonstrated significant benefit in efficacy."
    pool = _pool(
        _src(source_id="src-A", full_text=full_a),
        _src(source_id="src-B", full_text=full_b),
    )
    passed, reason = verify_sentence(
        f"Adults with chronic migraines showed aspirin benefit "
        f"[#ev:src-A:0-{len(full_a)}] [#ev:src-B:0-{len(full_b)}].",
        pool,
    )
    assert passed is True, f"expected pass, got reason={reason}"


def test_one_invalid_token_fails_even_when_other_valid():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    passed, reason = verify_sentence(
        "Claim [#ev:src-1:0-50] another [#ev:bogus:0-50].", pool
    )
    assert passed is False
    assert reason == "invalid_token"


# ---------- snippet fallback ----------

def test_snippet_used_when_full_text_none():
    pool = _pool(
        _src(
            source_id="src-1",
            full_text=None,
            snippet="Adults benefited from aspirin therapy clearly",
        )
    )
    passed, reason = verify_sentence(
        "Adults benefited from aspirin [#ev:src-1:0-30].", pool
    )
    # Snippet has the relevant content; should pass
    assert passed is True, f"expected pass, got reason={reason}"


# ---------- verify_sentence_to_record ----------

def test_to_record_passes_returns_kept():
    full_text = "Adults benefited from aspirin therapy in the trial."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    token = f"[#ev:src-1:0-{len(full_text)}]"
    rec = verify_sentence_to_record(
        f"Adults benefited from aspirin therapy {token}.",
        section_id="sec_x",
        pool=pool,
    )
    assert isinstance(rec, VerifiedSentence)
    assert rec.verifier_pass is True
    assert rec.drop_reason is None
    assert token in rec.provenance_tokens


def test_to_record_fail_returns_dropped():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    rec = verify_sentence_to_record(
        "Sentence with bogus claim [#ev:bogus:0-50].",
        section_id="sec_x",
        pool=pool,
    )
    assert rec.verifier_pass is False
    assert rec.drop_reason == "invalid_token"


def test_to_record_no_token_drops_with_reason():
    pool = _pool(_src(source_id="src-1", full_text="x" * 200))
    rec = verify_sentence_to_record(
        "Sentence with no token at all.",
        section_id="sec_x",
        pool=pool,
    )
    assert rec.verifier_pass is False
    assert rec.drop_reason == "no_provenance_token"


# ---------- section_pass_rate ----------

def test_section_pass_rate_all_pass():
    sentences = [
        VerifiedSentence(
            section_id="x",
            sentence_text="a",
            provenance_tokens=["[#ev:s:0-10]"],
            verifier_pass=True,
        )
        for _ in range(3)
    ]
    assert section_pass_rate(sentences) == 1.0


def test_section_pass_rate_all_fail():
    sentences = [
        VerifiedSentence(
            section_id="x",
            sentence_text="a",
            verifier_pass=False,
            drop_reason="numeric_mismatch",
        )
        for _ in range(3)
    ]
    assert section_pass_rate(sentences) == 0.0


def test_section_pass_rate_mixed():
    sentences = [
        VerifiedSentence(
            section_id="x",
            sentence_text="a",
            provenance_tokens=["[#ev:s:0-10]"],
            verifier_pass=True,
        ),
        VerifiedSentence(
            section_id="x",
            sentence_text="b",
            provenance_tokens=["[#ev:s:0-10]"],
            verifier_pass=True,
        ),
        VerifiedSentence(
            section_id="x",
            sentence_text="c",
            verifier_pass=False,
            drop_reason="overlap_too_low",
        ),
    ]
    assert abs(section_pass_rate(sentences) - 2 / 3) < 1e-9


def test_section_pass_rate_empty_is_zero():
    assert section_pass_rate([]) == 0.0


# ---------- DEFAULT_MIN_CONTENT_OVERLAP constant ----------

def test_default_threshold_is_two():
    assert DEFAULT_MIN_CONTENT_OVERLAP == 2
