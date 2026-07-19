"""I-deepfix-003 (#1374) STEP 5 — SPAN-LEVEL off-topic screen on the FINDINGS-BODY compose path.

The per-basket body writers in ``verified_compose`` — ``build_short_member_sentence``,
``build_multi_member_sentences`` and the K-span fallback ``build_verified_span_draft_multi`` — emit
VERBATIM span sentences after only the chrome-FORM screen (``_compose_boilerplate_screen``) + the downstream
strict_verify. NEITHER is TOPICAL, so a CONFIDENTLY-foreign span of an otherwise-on-topic source (a
"TranScriptorium manuscript digitisation project" sentence inside an AI-labor source) composed into the
findings body. STEP 5 wires the EXISTING high-precision, FAIL-OPEN span screen
``weighted_enrichment._withhold_offtopic_spans`` onto these writers, gated by a NEW kill-switch
``PG_COMPOSE_SPAN_TOPICALITY`` (default ON).

Faithfulness-neutral BY CONSTRUCTION: the screen only chooses WHICH already-grounded verbatim span of a
source is surfaced. The source stays in the evidence pool + bibliography; the frozen faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance / span-grounding) is NEVER touched. Pure Python — no GPU,
no LLM, no network.

Asserts (per the STEP-5 spec):
  (1) flag ON (default) + a real research question => the OFF-topic span is WITHHELD, the ON-topic span
      is EMITTED — for all three writers AND through the ``_compose_section_per_basket`` K-span fallback.
  (2) empty research_question => BOTH spans emitted (byte-identical to the legacy keep-all writers).
  (3) PG_COMPOSE_SPAN_TOPICALITY=0 => BOTH spans emitted even with a real research question.
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

vc = importlib.import_module("src.polaris_graph.generator.verified_compose")

_TOPICALITY_ENV = "PG_COMPOSE_SPAN_TOPICALITY"

_QUESTION = "What is the impact of generative artificial intelligence on the labor market?"

# ON-topic span: shares the question vocabulary (generative / artificial / intelligence / labor /
# market) so ``_span_is_confidently_offtopic`` fails OPEN on it (shares a question term => KEEP).
_ON_TOPIC = (
    "Generative artificial intelligence is reshaping the labor market for clerical workers "
    "across advanced economies."
)
# OFF-topic span: >= 6 content words, shares NO question term AND NO term with the source's own
# ON-topic sibling span (or its title) => CONFIDENTLY foreign => WITHHELD.
_OFF_TOPIC = (
    "The TranScriptorium manuscript digitisation project received substantial grant funding "
    "from Brussels cultural heritage institutions."
)

# Distinctive substrings used for presence/absence assertions.
_ON_MARK = "clerical workers"
_OFF_MARK = "TranScriptorium"


def _member(eid: str, quote: str):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict="SUPPORTS",
        credibility_weight=0.9,
        origin_cluster_id=eid,
    )


def _basket(*members):
    return SimpleNamespace(
        supporting_members=list(members),
        subject="generative AI labor market",
        claim_text="generative AI reshapes the labor market",
    )


def _pool(eid: str, quote: str):
    # The pool row carries the FULL member quote (so ``_member_global_span`` locates it) plus a rich
    # on-topic TITLE (one of ``_SOURCE_TOPIC_TITLE_FIELDS``) that anchors the source's local topic.
    return {
        eid: {
            "direct_quote": quote,
            "title": "Generative AI and the clerical labor market workforce",
        }
    }


# The member quote carries BOTH spans as two sentences. ON-topic first for the multi/K-span writers;
# a separate OFF-topic-first quote is used for the single-headline short writer (which emits unit[0]).
_QUOTE_ON_FIRST = f"{_ON_TOPIC} {_OFF_TOPIC}"
_QUOTE_OFF_FIRST = f"{_OFF_TOPIC} {_ON_TOPIC}"


# ── build_multi_member_sentences (the primary deterministic body writer) ─────────────────────────


def test_multi_writer_withholds_offtopic_keeps_ontopic(monkeypatch):
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)  # default ON
    eid = "ev1"
    out = vc.build_multi_member_sentences(_basket(_member(eid, _QUOTE_ON_FIRST)), _pool(eid, _QUOTE_ON_FIRST),
                                          research_question=_QUESTION)
    assert _ON_MARK in out, "on-topic span must be emitted"
    assert _OFF_MARK not in out, "confidently-off-topic span must be withheld from citation"
    # A real cited span (with its provenance token) is still emitted — never a blank section.
    assert "[#ev:ev1:" in out


def test_multi_writer_empty_question_emits_both(monkeypatch):
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)  # default ON
    eid = "ev1"
    out = vc.build_multi_member_sentences(_basket(_member(eid, _QUOTE_ON_FIRST)), _pool(eid, _QUOTE_ON_FIRST),
                                          research_question="")
    assert _ON_MARK in out and _OFF_MARK in out, "empty question => byte-identical keep-all"


def test_multi_writer_killswitch_off_emits_both(monkeypatch):
    monkeypatch.setenv(_TOPICALITY_ENV, "0")
    eid = "ev1"
    out = vc.build_multi_member_sentences(_basket(_member(eid, _QUOTE_ON_FIRST)), _pool(eid, _QUOTE_ON_FIRST),
                                          research_question=_QUESTION)
    assert _ON_MARK in out and _OFF_MARK in out, "PG_COMPOSE_SPAN_TOPICALITY=0 => keep-all"


# ── build_short_member_sentence (single-headline writer; emits unit[0]) ──────────────────────────


def test_short_writer_withholds_offtopic_headline(monkeypatch):
    # OFF-topic is the FIRST sentence: without the screen the headline would be the off-topic span;
    # with the screen it is withheld and the writer emits the next (ON-topic) unit instead.
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)  # default ON
    eid = "ev1"
    out = vc.build_short_member_sentence(_basket(_member(eid, _QUOTE_OFF_FIRST)), _pool(eid, _QUOTE_OFF_FIRST),
                                         research_question=_QUESTION)
    assert _ON_MARK in out and _OFF_MARK not in out


def test_short_writer_empty_question_emits_offtopic_headline(monkeypatch):
    # Empty question => no screen => the FIRST (off-topic) unit is the headline (byte-identical legacy).
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)
    eid = "ev1"
    out = vc.build_short_member_sentence(_basket(_member(eid, _QUOTE_OFF_FIRST)), _pool(eid, _QUOTE_OFF_FIRST),
                                         research_question="")
    assert _OFF_MARK in out


def test_short_writer_killswitch_off_emits_offtopic_headline(monkeypatch):
    monkeypatch.setenv(_TOPICALITY_ENV, "0")
    eid = "ev1"
    out = vc.build_short_member_sentence(_basket(_member(eid, _QUOTE_OFF_FIRST)), _pool(eid, _QUOTE_OFF_FIRST),
                                         research_question=_QUESTION)
    assert _OFF_MARK in out


# ── build_verified_span_draft_multi (K-span FALLBACK writer) ─────────────────────────────────────


def test_kspan_fallback_withholds_offtopic_keeps_ontopic(monkeypatch):
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)  # default ON
    eid = "ev1"
    out = vc.build_verified_span_draft_multi(_basket(_member(eid, _QUOTE_ON_FIRST)), _pool(eid, _QUOTE_ON_FIRST),
                                             research_question=_QUESTION)
    assert out is not None
    assert _ON_MARK in out and _OFF_MARK not in out


def test_kspan_fallback_empty_question_emits_both(monkeypatch):
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)
    eid = "ev1"
    out = vc.build_verified_span_draft_multi(_basket(_member(eid, _QUOTE_ON_FIRST)), _pool(eid, _QUOTE_ON_FIRST),
                                             research_question="")
    assert out is not None
    assert _ON_MARK in out and _OFF_MARK in out


# ── threading through _compose_section_per_basket -> _compose_one_basket -> K-span fallback ───────


def test_section_producer_threads_research_question_to_fallback(monkeypatch):
    """Force the K-span FALLBACK (writer_fn returns "" so _compose_one_basket falls to
    build_verified_span_draft_multi) and prove research_question threads through
    _compose_section_per_basket -> _compose_one_basket -> the fallback, withholding the off-topic span.
    This is the path that fires on BOTH the abstractive and deterministic production branches."""
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)  # default ON
    monkeypatch.delenv("PG_VERIFIED_COMPOSE_MULTICITED", raising=False)  # default OFF => single-basket path
    eid = "ev1"
    composed = vc._compose_section_per_basket(
        [_basket(_member(eid, _QUOTE_ON_FIRST))],
        _pool(eid, _QUOTE_ON_FIRST),
        writer_fn=lambda _b, _p: "",  # empty draft => no kept sentences => K-span fallback fires
        verify_fn=lambda *_a, **_k: SimpleNamespace(is_verified=False, sentence=""),
        research_question=_QUESTION,
    )
    body = "\n".join(composed)
    assert _ON_MARK in body, "on-topic span must survive to the section body"
    assert _OFF_MARK not in body, "off-topic span must be withheld through the section producer"


def test_section_producer_empty_question_emits_both(monkeypatch):
    monkeypatch.delenv(_TOPICALITY_ENV, raising=False)
    monkeypatch.delenv("PG_VERIFIED_COMPOSE_MULTICITED", raising=False)
    eid = "ev1"
    composed = vc._compose_section_per_basket(
        [_basket(_member(eid, _QUOTE_ON_FIRST))],
        _pool(eid, _QUOTE_ON_FIRST),
        writer_fn=lambda _b, _p: "",
        verify_fn=lambda *_a, **_k: SimpleNamespace(is_verified=False, sentence=""),
        research_question="",
    )
    body = "\n".join(composed)
    assert _ON_MARK in body and _OFF_MARK in body, "empty question => keep-all through the producer"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
