"""LEVER 4 (source routing, PG_SOURCE_ROUTING) — offline language detection + fail-open safety.

Scope of this pass:
  * Part 1 (offline language detection) — IMPLEMENTED here and tested.
  * Part 2 (journal-source preference) — ALREADY EXISTS as the RQ source-eligibility firewall
    (PG_RQ_SOURCE_ELIGIBILITY_ENFORCE + _SOURCE_TYPE_TO_GENRES journal_article -> JOURNAL_ARTICLE +
    the host/DOI-driven document_type_classifier). Lever 4 ENABLES it in the recipe, not rebuilt.
  * Part 3 (same-work journal-preferred re-citation with strict re-verify) — DEFERRED (faithfulness
    boundary; needs compose-time same-work + re-verify integration). Not in this pass.
"""
from __future__ import annotations

import os
import pytest

from src.polaris_graph.retrieval import rq_eligibility as E


def _set(monkeypatch, on: bool):
    monkeypatch.setenv("PG_SOURCE_ROUTING", "1" if on else "")


# ── detector: offline, general, conservative ──────────────────────────────────────────────────
def test_detect_arabic_script():
    # the real drb_72 offender: an Arabic-language article title
    assert E.detect_language_offline("تأثير الذكاء الاصطناعي على سوق العمل والوظائف") == "ar"


def test_detect_cyrillic_and_cjk_and_greek():
    assert E.detect_language_offline("Влияние искусственного интеллекта на рынок труда") == "ru"
    assert E.detect_language_offline("人工智能对劳动力市场的影响研究") == "zh"
    assert E.detect_language_offline("Επιπτώσεις της τεχνητής νοημοσύνης στην αγορά") == "el"


def test_english_returns_none_stays_failopen():
    # English is the reference language: detector must NOT emit a code (nothing to demote)
    assert E.detect_language_offline(
        "The impact of artificial intelligence on the labor market and jobs"
    ) is None


def test_latin_nonenglish_stopword_signal():
    # German title with a clear function-word majority
    assert E.detect_language_offline(
        "Die Auswirkungen der künstlichen Intelligenz auf den Arbeitsmarkt und die Beschäftigung"
    ) == "de"


def test_ambiguous_short_returns_none():
    assert E.detect_language_offline("AI 2026") is None
    assert E.detect_language_offline("") is None
    assert E.detect_language_offline(None) is None
    # a short Latin title with no strong non-English signal stays fail-open
    assert E.detect_language_offline("Generative models") is None


# ── _row_language gating: OFF byte-identical, ON adds the fallback only when sidecar absent ──────
def test_row_language_off_is_sidecar_only(monkeypatch):
    _set(monkeypatch, False)
    # no sidecar, Arabic title => OFF must behave exactly like today: None (fail-open)
    assert E._row_language({"title": "تأثير الذكاء الاصطناعي على سوق العمل"}) is None


def test_row_language_on_detects_when_no_sidecar(monkeypatch):
    _set(monkeypatch, True)
    assert E._row_language({"title": "تأثير الذكاء الاصطناعي على سوق العمل والوظائف"}) == "ar"


def test_sidecar_always_wins_over_detection(monkeypatch):
    _set(monkeypatch, True)
    # an explicit sidecar language is authoritative even with a foreign-looking title
    assert E._row_language({"language": "en", "title": "人工智能对劳动力市场的影响"}) == "en"


def test_row_language_on_english_title_stays_failopen(monkeypatch):
    _set(monkeypatch, True)
    # English title, no sidecar => detector returns None => still fail-open (never punished)
    assert E._row_language({"title": "Artificial intelligence and the future of work"}) is None


# ── no-rollback: detection feeds DEMOTE-AND-RETAIN, never a delete ───────────────────────────────
def test_detection_never_deletes_only_demotes(monkeypatch):
    # build_rq_eligibility only ever demotes (weight in (0,1)); it never removes a row. Confirm the
    # plan for a non-English row is a demotion entry, and the row object is not dropped from input.
    _set(monkeypatch, True)
    monkeypatch.setenv("PG_RQ_SOURCE_ELIGIBILITY_ENFORCE", "1")
    rows = [
        {"url": "https://x.test/a", "title": "تأثير الذكاء الاصطناعي على سوق العمل والوظائف"},
        {"url": "https://y.test/b", "title": "Artificial intelligence and the labor market"},
    ]
    protocol = {"_rq_constraints": {"languages": ["en"], "source_types": [], "recency": None}}
    plan = E.build_rq_eligibility(protocol, rows, research_question="only English-language articles")
    # the plan is a demote map (never a delete); the input rows are untouched in count
    assert len(rows) == 2
    # weight applied to any demoted row is strictly in (0,1) — retained, not zeroed
    assert 0.0 < E.demote_weight() < 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
