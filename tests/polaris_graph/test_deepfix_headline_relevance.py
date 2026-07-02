"""I-deepfix-001 (#1344) headline_relevance — offline RED->GREEN tests.

Relevance-weighted headline / Key-Findings selection: WEIGHT and RE-ORDER only, never drop (§-1.3
Principle 1). The optional ``sentence_relevance`` ranker re-orders sentences that ALREADY passed the
frozen faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) — those run
upstream in the generator and are neither imported nor modified here. ``None`` (every existing caller)
is byte-identical document order.

Offline: no GPU, no network, no paid LLM. The ranker is an injected pure callable.
"""
from __future__ import annotations

from src.polaris_graph.generator.abstract_conclusion import build_abstract
from src.polaris_graph.generator.key_findings import (
    _MAX_BULLETS,
    _first_verified_sentences,
    build_key_findings,
    make_question_relevance_ranker,
)


class _Sec:
    def __init__(self, verified_text: str, title: str = "Section") -> None:
        self.verified_text = verified_text
        self.title = title
        self.dropped_due_to_failure = False
        self.is_gap_stub = False
        self.sentences_verified = 2


# A ranker that scores a sentence high iff it is on-topic for the (fixed) test question.
def _aspirin_ranker(sentence: str) -> float:
    return 1.0 if "aspirin" in sentence.lower() else 0.0


_TWO_SENTENCE = "Off topic remark about the weather today. [1] On topic aspirin lowers cardiac risk. [2]"


def test_default_none_is_document_order():
    """No ranker => the first verified sentence in DOCUMENT order leads (byte-identical)."""
    got = _first_verified_sentences(_TWO_SENTENCE, 1)
    assert got == ["Off topic remark about the weather today. [1]"]


def test_ranker_puts_most_on_topic_sentence_first():
    """With a ranker, the most on-topic verified sentence leads its section (RED pre-fix:
    the function had no ``sentence_relevance`` param -> TypeError)."""
    got = _first_verified_sentences(_TWO_SENTENCE, 1, sentence_relevance=_aspirin_ranker)
    assert got == ["On topic aspirin lowers cardiac risk. [2]"]


def test_ranking_drops_no_sentence():
    """Re-ordering NEVER drops a sentence: the full candidate SET is identical with and without
    the ranker (weight, don't filter)."""
    with_ranker = _first_verified_sentences(
        _TWO_SENTENCE, 10_000, sentence_relevance=_aspirin_ranker
    )
    without = _first_verified_sentences(_TWO_SENTENCE, 10_000)
    assert set(with_ranker) == set(without)
    assert len(with_ranker) == 2


def test_build_key_findings_globally_orders_by_relevance():
    """build_key_findings orders bullets by descending relevance across sections when a ranker is
    wired; None keeps document order."""
    sections = [
        _Sec("Weather remark leads here. [1]", title="Weather"),
        _Sec("Aspirin lowers cardiac risk sharply. [2]", title="Cardio"),
    ]
    ranked = build_key_findings(sections, sentence_relevance=_aspirin_ranker)
    default = build_key_findings(sections)
    ranked_bullets = [ln for ln in ranked.splitlines() if ln.startswith("- ")]
    default_bullets = [ln for ln in default.splitlines() if ln.startswith("- ")]
    assert "aspirin" in ranked_bullets[0].lower()      # on-topic leads with the ranker
    assert "weather" in default_bullets[0].lower()      # document order without it


def test_on_topic_finding_buried_past_max_bullets_is_surfaced():
    """An on-topic finding beyond the _MAX_BULLETS document-order cutoff is SURFACED by the ranker
    (RED pre-fix: dropped by the head-slice; no global re-order existed)."""
    sections = [
        _Sec(f"Generic finding number {i} here. [{i + 1}]", title=f"S{i}")
        for i in range(_MAX_BULLETS)
    ]
    sections.append(_Sec("SURFACEME critical on-topic finding here. [99]", title="Buried"))

    def _surface_ranker(sentence: str) -> float:
        return 1.0 if "SURFACEME" in sentence else 0.0

    ranked = build_key_findings(sections, sentence_relevance=_surface_ranker)
    default = build_key_findings(sections)
    ranked_bullets = [ln for ln in ranked.splitlines() if ln.startswith("- ")]
    assert "SURFACEME" in ranked_bullets[0]          # surfaced AND leads with the ranker
    assert "SURFACEME" not in default                # dropped by the summary cap without it
    assert len(ranked_bullets) == _MAX_BULLETS       # cap still holds (still a summary)


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCTION-PATH wiring (Codex P1 #1): the ranker is actually applied by the two
# functions run_honest_sweep_r3.py calls — build_key_findings AND build_abstract —
# using the REAL production ranker factory (make_question_relevance_ranker), not a
# hand-rolled test stub. RED before wiring: build_abstract had no sentence_relevance
# param (TypeError) and make_question_relevance_ranker did not exist (ImportError).
# ─────────────────────────────────────────────────────────────────────────────
_KF_SECTIONS = [
    _Sec("Weather remark leads this section here. [1]", title="Weather"),
    _Sec("Aspirin lowers cardiac risk sharply overall. [2]", title="Cardio"),
]


def test_production_ranker_is_content_word_overlap_weight():
    """The production ranker is a WEIGHT (content-word overlap with the question), higher for the
    on-topic sentence. It returns None only when the question has no content words (=> caller
    threads None => document order)."""
    ranker = make_question_relevance_ranker("aspirin cardiac risk")
    assert ranker is not None
    assert ranker("Aspirin lowers cardiac risk sharply overall. [2]") > ranker(
        "Weather remark leads this section here. [1]"
    )
    # No content words in the question => None => byte-identical document order at the call site.
    assert make_question_relevance_ranker("") is None
    assert make_question_relevance_ranker("of to in on") is None


def test_production_build_key_findings_applies_the_real_ranker():
    """build_key_findings (run_honest_sweep_r3.py:13746) promotes the on-topic verified sentence
    when wired with the REAL production ranker; None keeps document order."""
    ranker = make_question_relevance_ranker("aspirin cardiac risk")
    ranked = build_key_findings(_KF_SECTIONS, sentence_relevance=ranker)
    default = build_key_findings(_KF_SECTIONS)
    ranked_bullets = [ln for ln in ranked.splitlines() if ln.startswith("- ")]
    default_bullets = [ln for ln in default.splitlines() if ln.startswith("- ")]
    assert "aspirin" in ranked_bullets[0].lower()     # on-topic leads with the ranker
    assert "weather" in default_bullets[0].lower()     # document order without it (byte-identical)


def test_production_build_abstract_applies_the_real_ranker(monkeypatch):
    """build_abstract (run_honest_sweep_r3.py:13937) — the Abstract front-sandwich — orders its
    verbatim headline findings by relevance when wired with the ranker; None keeps document order
    (the Codex-flagged "Abstract still harvests via _first_verified_sentences with no ranker" gap)."""
    monkeypatch.setenv("PG_SYNTHESIS_ABSTRACT_CONCLUSION", "1")
    ranker = make_question_relevance_ranker("aspirin cardiac risk")
    ranked = build_abstract(_KF_SECTIONS, sentence_relevance=ranker)
    default = build_abstract(_KF_SECTIONS)
    # With the ranker the on-topic sentence leads the abstract body (comes before the off-topic one).
    assert ranked.lower().index("aspirin") < ranked.lower().index("weather")
    # Default (None) is document order: the first section's sentence leads (byte-identical harvest).
    assert default.lower().index("weather") < default.lower().index("aspirin")


def test_build_abstract_default_none_is_byte_identical(monkeypatch):
    """Passing no ranker (or sentence_relevance=None) is byte-identical to the pre-wiring behavior."""
    monkeypatch.setenv("PG_SYNTHESIS_ABSTRACT_CONCLUSION", "1")
    assert build_abstract(_KF_SECTIONS) == build_abstract(_KF_SECTIONS, sentence_relevance=None)
