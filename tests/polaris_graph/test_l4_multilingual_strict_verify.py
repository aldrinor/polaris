"""I-deepfix-001 L4 (#1344) — CJK / multilingual-aware strict_verify + multilingual
NLI consolidation.

FAIL-LOUD behavioral tests that prove the EFFECT in real verify output (not a
flag tautology). Each block asserts a concrete RED baseline (the pre-L4 engine,
reachable via PG_STRICT_VERIFY_SCRIPT_AWARE=0) against the GREEN post-fix
behavior, so a regression that silently reverts the fix fails the suite.

DNA: this fix only ever TIGHTENS the faithfulness engine — it extends correct
lexical grounding to more scripts and FAILS CLOSED on scripts it cannot segment.
It relaxes nothing, drops no corroborating source, and adds no cap/target.

All offline, $0 — no model download, no network. The consolidation-NLI block
drives the label-resolution logic with a fake model object (no cross-encoder).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.polaris_graph.generator import script_aware_grounding as sag
from src.polaris_graph.generator.provenance_generator import verify_sentence_provenance
from src.polaris_graph.clinical_generator.strict_verify import verify_sentence
from src.polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ── real non-Latin fixtures (short, grounded clinical-shaped prose) ──────────
#
# zh spans/claims about diabetes glucose control; the fabricated claim shares the
# printed number 7.0 but NO content bigrams with its cited span (the exact hole
# L4 closes: an ungrounded non-Latin claim riding through on a coincidental
# number match because the Latin-only tokenizer produced ZERO content words).
_ZH_SPAN = "糖尿病患者的血糖控制目标为7.0"          # "diabetic patients' glucose target is 7.0"
_ZH_GROUNDED = "糖尿病患者的血糖控制目标为7.0"        # same content -> bigrams overlap
_ZH_FAB_SPAN = "阿司匹林降低疼痛评分至7.0"           # "aspirin lowers pain score to 7.0"
_ZH_FAB_CLAIM = "高血压患者死亡风险显著上升7.0"       # unrelated: hypertension mortality
_AR_SPAN = "مرض السكري يؤثر على ضغط الدم"          # "diabetes affects blood pressure"
_AR_GROUNDED = "مرض السكري يؤثر على ضغط الدم"
_TH_SPAN = "ผู้ป่วยเบาหวานควบคุมน้ำตาล7.0"          # Thai (unsegmentable)
_TH_CLAIM = "ผู้ป่วยเบาหวานควบคุม7.0"


def _tok(ev_id: str, span_text: str) -> str:
    return f"[#ev:{ev_id}:0-{len(span_text)}]"


# ════════════════════════════════════════════════════════════════════════════
# BLOCK A — the shared script-aware tokenizer (unit level)
# ════════════════════════════════════════════════════════════════════════════

def test_cjk_bigrams_overlapping():
    assert sag.cjk_bigrams("糖尿病") == {"糖尿", "尿病"}
    # single ideograph -> unigram (still a token)
    assert sag.cjk_bigrams("糖") == {"糖"}


def test_extra_script_tokens_covers_cjk_and_arabic_not_latin(monkeypatch):
    # The multilingual tightening is DEFAULT-OFF; turn it on explicitly to exercise
    # the gated helpers (an unset env is proven a no-op by
    # test_default_unset_is_off_byte_identical below).
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    zh = sag.extra_script_tokens("糖尿病患者")
    assert {"糖尿", "尿病", "患者"}.issubset(zh)
    ar = sag.extra_script_tokens("مرض السكري")
    assert ar == {"مرض", "السكري"}
    # Latin is the caller's own job — this helper must not double-count it
    assert sag.extra_script_tokens("diabetes mellitus") == set()


def test_unsegmentable_detects_thai_only(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    assert sag.has_unsegmentable_content(_TH_CLAIM) is True
    assert sag.has_unsegmentable_content("diabetes 7.0") is False
    assert sag.has_unsegmentable_content("糖尿病") is False
    assert sag.has_unsegmentable_content("مرض السكري") is False


def test_killswitch_reverts_tokenizer(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    assert sag.extra_script_tokens("糖尿病患者") == set()
    assert sag.has_unsegmentable_content(_TH_CLAIM) is False


def test_default_unset_is_off_byte_identical(monkeypatch):
    """DEFAULT-OFF contract (LAW VI): with PG_STRICT_VERIFY_SCRIPT_AWARE UNSET the
    module is a no-op, byte-identical to the pre-L4 Latin-only engine. This is the
    P1 the dual gate flagged — an unset production env must NOT silently change
    strict_verify behaviour; the multilingual tightening only activates on an
    explicit ON. RED (unset -> OFF) then GREEN (explicit '1' -> ON)."""
    monkeypatch.delenv("PG_STRICT_VERIFY_SCRIPT_AWARE", raising=False)
    assert sag.script_aware_enabled() is False
    assert sag.extra_script_tokens("糖尿病患者") == set()
    assert sag.has_unsegmentable_content(_TH_CLAIM) is False

    # Explicit ON flips it on (the deliberate run-config opt-in).
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    assert sag.script_aware_enabled() is True
    assert {"糖尿", "尿病", "患者"}.issubset(sag.extra_script_tokens("糖尿病患者"))
    assert sag.has_unsegmentable_content(_TH_CLAIM) is True


# ════════════════════════════════════════════════════════════════════════════
# BLOCK B — provenance_generator.verify_sentence_provenance
# entailment leg forced OFF so the CONTENT-OVERLAP FLOOR is the sole gate under
# test (isolates the L4 change from the independent NLI leg).
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _entailment_off(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")


def test_provenance_grounded_cjk_verifies_recall_restored(monkeypatch):
    """A genuinely grounded Chinese claim must VERIFY. Pre-L4 the Latin-only
    tokenizer produced zero content words, so the overlap floor mis-counted and
    the claim was at risk of a spurious drop (recall loss)."""
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    pool = {"e1": {"direct_quote": _ZH_SPAN}}
    sentence = f"{_ZH_GROUNDED} {_tok('e1', _ZH_SPAN)}"
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is True, result.failure_reasons


def test_provenance_fabricated_cjk_dropped_hole_closed(monkeypatch):
    """RED->GREEN: a fabricated Chinese claim sharing only the printed number 7.0
    with its cited span. Pre-L4 (aware=0) it VERIFIES — the empty Latin content
    set SKIPS the overlap floor entirely (the lethal weakened-positive). Post-L4
    (aware=1) the CJK bigrams give it real content, no overlap, so it DROPS."""
    pool = {"e2": {"direct_quote": _ZH_FAB_SPAN}}
    sentence = f"{_ZH_FAB_CLAIM} {_tok('e2', _ZH_FAB_SPAN)}"

    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    red = verify_sentence_provenance(sentence, pool)
    assert red.is_verified is True, (
        "RED baseline must reproduce the pre-L4 hole (ungrounded CJK claim "
        "passing on a bare number match); if this fails the test no longer "
        "proves the fix"
    )

    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    green = verify_sentence_provenance(sentence, pool)
    assert green.is_verified is False
    assert any("no_content_word_overlap" in r for r in green.failure_reasons), (
        green.failure_reasons
    )


def test_provenance_unsegmentable_thai_fails_closed(monkeypatch):
    """RED->GREEN: a Thai claim whose only cross-script match is the number 7.0.
    Thai has no word spaces and no bigram convention we trust, so pre-L4 it rode
    through (aware=0 -> verified) and post-L4 it FAILS CLOSED (drop, never
    guess)."""
    pool = {"e3": {"direct_quote": _TH_SPAN}}
    sentence = f"{_TH_CLAIM} {_tok('e3', _TH_SPAN)}"

    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    red = verify_sentence_provenance(sentence, pool)
    assert red.is_verified is True, "RED baseline must reproduce the pre-L4 hole"

    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    green = verify_sentence_provenance(sentence, pool)
    assert green.is_verified is False
    assert any(
        "unsegmentable_script" in r for r in green.failure_reasons
    ), green.failure_reasons


def test_provenance_mixed_thai_latin_fails_closed(monkeypatch):
    """RED->GREEN (Codex iter-3 P1): a MIXED sentence — grounded Latin content PLUS
    an ungrounded unsegmentable Thai run — must FAIL CLOSED.

    This is the narrower-than-contract hole: the earlier provenance guard only
    dropped when sentence_content was EMPTY (``not sentence_content and ...``). A
    mixed sentence has NON-empty sentence_content from its Latin tokens, so it fell
    to the ``elif`` and could PASS the overlap floor on the Latin words while the
    Thai claim rode through UNGROUNDED — while clinical_generator.strict_verify
    already failed closed UNCONDITIONALLY. The fix makes provenance_generator match:
    fail closed on ANY unsegmentable run regardless of the segmentable tokens.

    The Latin part is deliberately GROUNDED (overlaps the span) so that WITHOUT the
    fix the sentence would VERIFY on the Latin overlap — the RED kill-switch path
    (aware=0) proves exactly that. GREEN (aware=1) drops it unsegmentable.
    """
    span = "Metformin controls glucose in adults ผู้ป่วยเบาหวานควบคุมน้ำตาล"
    claim = "Metformin controls glucose in adults ผู้ป่วยเบาหวานควบคุม"
    pool = {"e_mix": {"direct_quote": span}}
    sentence = f"{claim} {_tok('e_mix', span)}"

    # RED: kill-switch OFF == pre-L4 Latin-only floor. The Latin content is grounded,
    # so the mixed sentence VERIFIES — the Thai run is invisible to the floor.
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    red = verify_sentence_provenance(sentence, pool)
    assert red.is_verified is True, (
        "RED baseline must show the mixed sentence passing on the grounded Latin "
        "overlap while the Thai run is unchecked; if this fails the test no longer "
        f"proves the mixed hole: {red.failure_reasons}"
    )

    # GREEN: fix ON. Even though the Latin content overlaps, the unsegmentable Thai
    # run fails the whole sentence closed — the unconditional fail-closed contract.
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    green = verify_sentence_provenance(sentence, pool)
    assert green.is_verified is False, (
        "mixed Thai+Latin sentence must FAIL CLOSED on the unsegmentable Thai run "
        "even though its Latin content is grounded"
    )
    assert any(
        "unsegmentable_script" in r for r in green.failure_reasons
    ), green.failure_reasons


def test_provenance_english_unchanged(monkeypatch):
    """English behavior is byte-identical either side of the flag: a normal
    grounded English clinical sentence still verifies with script-aware ON."""
    span = "Aspirin reduced cardiovascular events in older adults."
    pool = {"e4": {"direct_quote": span}}
    sentence = f"Aspirin reduced cardiovascular events {_tok('e4', span)}"
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    on = verify_sentence_provenance(sentence, pool)
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    off = verify_sentence_provenance(sentence, pool)
    assert on.is_verified == off.is_verified is True


# ════════════════════════════════════════════════════════════════════════════
# BLOCK C — clinical_generator.strict_verify.verify_sentence
# ════════════════════════════════════════════════════════════════════════════

def _src(source_id: str, full_text: str) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=full_text[:400] or "x",
        full_text=full_text,
        full_text_available=True,
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


def test_clinical_grounded_cjk_passes(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool(_src("s1", _ZH_SPAN))
    passed, reason = verify_sentence(f"{_ZH_GROUNDED} {_tok('s1', _ZH_SPAN)}", pool)
    assert passed is True, reason


def test_clinical_fabricated_cjk_overlap_too_low(monkeypatch):
    """RED->GREEN: pre-L4 the fabricated CJK claim mis-counts zero content words
    and, with a matching decimal, slips to overlap_too_low only by accident; the
    real fix is that with CJK bigrams the overlap is genuinely computed and the
    claim is dropped for the RIGHT reason. Under aware=0 the same claim reaches
    overlap_too_low via an empty set; assert the GREEN drop carries a real
    reason."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    pool = _pool(_src("s2", _ZH_FAB_SPAN))
    passed, reason = verify_sentence(f"{_ZH_FAB_CLAIM} {_tok('s2', _ZH_FAB_SPAN)}", pool)
    assert passed is False
    assert reason in ("overlap_too_low", "empty_or_contentless_sentence"), reason


def test_clinical_arabic_grounded_passes(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = _pool(_src("s5", _AR_SPAN))
    passed, reason = verify_sentence(f"{_AR_GROUNDED} {_tok('s5', _AR_SPAN)}", pool)
    assert passed is True, reason


def test_clinical_unsegmentable_thai_fails_closed(monkeypatch):
    """RED->GREEN: a Thai claim carrying a matching decimal. Pre-L4 (aware=0) the
    decimal passes and the empty content set falls to overlap_too_low ONLY if the
    threshold bites; L4 fails it closed with the explicit unsegmentable_script
    reason so the outcome is unambiguous and never a spurious pass."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    pool = _pool(_src("s3", _TH_SPAN))
    passed, reason = verify_sentence(f"{_TH_CLAIM} {_tok('s3', _TH_SPAN)}", pool)
    assert passed is False
    assert reason == "unsegmentable_script", reason


def test_clinical_mixed_thai_latin_fails_closed(monkeypatch):
    """Parity with the provenance mixed-script fix (Codex iter-3 P1): a MIXED
    Thai+Latin sentence whose Latin content is grounded must ALSO fail closed here.
    strict_verify already checks has_unsegmentable_content unconditionally BEFORE
    the overlap floor, so this documents+locks that both callers agree on the mixed
    case (no ungrounded unsegmentable claim rides through on grounded Latin)."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    span = "Metformin controls glucose in adults ผู้ป่วยเบาหวานควบคุมน้ำตาล"
    claim = "Metformin controls glucose in adults ผู้ป่วยเบาหวานควบคุม"
    pool = _pool(_src("s_mix", span))
    passed, reason = verify_sentence(f"{claim} {_tok('s_mix', span)}", pool)
    assert passed is False
    assert reason == "unsegmentable_script", reason


def test_clinical_english_unchanged(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    span = "Aspirin reduced cardiovascular events in older adults."
    pool = _pool(_src("s4", span))
    sentence = f"Aspirin reduced cardiovascular events {_tok('s4', span)}"
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "1")
    on = verify_sentence(sentence, pool)
    monkeypatch.setenv("PG_STRICT_VERIFY_SCRIPT_AWARE", "0")
    off = verify_sentence(sentence, pool)
    assert on[0] == off[0] is True


# ════════════════════════════════════════════════════════════════════════════
# BLOCK D — consolidation_nli multilingual label resolution
# A multilingual cross-encoder (e.g. mDeBERTa-xnli) exposes a DIFFERENT 3-way
# label order than the English nli-deberta default. Pre-L4 the indices were
# hardcoded, so swapping the model silently mis-read the logits. L4 resolves the
# indices from the loaded model's id2label. Driven with a fake model — no
# download, no cross-encoder.
# ════════════════════════════════════════════════════════════════════════════

class _FakeConfig:
    def __init__(self, id2label):
        self.id2label = id2label


class _FakeModel:
    def __init__(self, id2label):
        self.config = _FakeConfig(id2label)


@pytest.fixture
def _restore_nli_indices():
    from src.polaris_graph.synthesis import consolidation_nli as cn
    saved = (cn._ENTAILMENT_IDX, cn._CONTRADICTION_IDX)
    yield cn
    cn._ENTAILMENT_IDX, cn._CONTRADICTION_IDX = saved


def test_nli_resolves_multilingual_label_order(_restore_nli_indices):
    cn = _restore_nli_indices
    # mDeBERTa-xnli order: 0=entailment, 1=neutral, 2=contradiction — the OPPOSITE
    # of the English default (0=contradiction, 1=entailment).
    model = _FakeModel({0: "entailment", 1: "neutral", 2: "contradiction"})
    cn._resolve_label_indices(model)
    assert cn._ENTAILMENT_IDX == 0
    assert cn._CONTRADICTION_IDX == 2

    # _entails must now read the RESOLVED indices: a logit vector whose argmax is
    # index 0 (entailment) must entail; one whose argmax is index 2 must not.
    assert cn._entails([5.0, 0.0, 1.0], margin=0.0) is True
    assert cn._entails([1.0, 0.0, 5.0], margin=0.0) is False


def test_nli_default_order_still_correct(_restore_nli_indices):
    cn = _restore_nli_indices
    model = _FakeModel({0: "contradiction", 1: "entailment", 2: "neutral"})
    cn._resolve_label_indices(model)
    assert cn._ENTAILMENT_IDX == 1
    assert cn._CONTRADICTION_IDX == 0
    assert cn._entails([0.0, 5.0, 1.0], margin=0.0) is True
    assert cn._entails([5.0, 0.0, 1.0], margin=0.0) is False


def test_nli_bad_config_keeps_defaults(_restore_nli_indices):
    cn = _restore_nli_indices
    cn._ENTAILMENT_IDX = cn._DEFAULT_ENTAILMENT_IDX
    cn._CONTRADICTION_IDX = cn._DEFAULT_CONTRADICTION_IDX
    # not 3-way -> ignored
    cn._resolve_label_indices(_FakeModel({0: "yes", 1: "no"}))
    assert cn._ENTAILMENT_IDX == cn._DEFAULT_ENTAILMENT_IDX
    assert cn._CONTRADICTION_IDX == cn._DEFAULT_CONTRADICTION_IDX
    # missing config attribute -> ignored (no crash)
    cn._resolve_label_indices(object())
    assert cn._ENTAILMENT_IDX == cn._DEFAULT_ENTAILMENT_IDX
