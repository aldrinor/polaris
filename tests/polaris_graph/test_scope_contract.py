"""Behavioral tests for the pre-generation retrieval/scope contract."""
from __future__ import annotations

import copy

from src.polaris_graph.retrieval.scope_contract import (
    apply_scope_contract,
    build_scope_deepening_queries,
)


RQ = "Review how artificial intelligence restructures labor markets."


def _rows() -> list[dict]:
    return [
        {
            "evidence_id": "labor",
            "title": "Artificial intelligence exposure and employment",
            "snippet": "Automation changes occupations, wages, tasks, and employment.",
            "document_type": "JOURNAL_ARTICLE",
            "language": "en",
        },
        {
            "evidence_id": "knee",
            "title": "Patient outcomes after total knee replacement",
            "snippet": "A clinical review of postoperative pain and rehabilitation.",
            "document_type": "JOURNAL_ARTICLE",
            "language": "en",
        },
    ]


def test_off_topic_excluded_disclosed_on_topic_kept_and_input_not_mutated(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1")
    rows = _rows()
    original = copy.deepcopy(rows)

    result = apply_scope_contract(
        rows,
        RQ,
        lambda _prompt: "0: ON\n1: OFF_SUBJECT",
    )

    assert [row["evidence_id"] for row in result.evidence] == ["labor"]
    assert result.off_topic_excluded == [{
        "evidence_id": "knee",
        "title": "Patient outcomes after total knee replacement",
        "url": "",
        "reason": "semantic_topic_judge: off-topic to research question",
        "category": "off_topic",
        "excluded_from_composition": True,
        "retained_in_source_corpus": True,
    }]
    assert rows == original
    assert result.evidence[0] is not rows[0]


def test_no_exclusive_type_constraint_does_not_filter_type(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    rows = [{
        "evidence_id": "report",
        "title": "AI and jobs policy report",
        "snippet": "Labor-market evidence about occupations and automation.",
        "document_type": "REPORT",
    }]
    result = apply_scope_contract(
        rows,
        RQ,
        lambda _prompt: "0: ON",
        constraints={"source_types": ["journal_article"]},
    )
    assert [row["evidence_id"] for row in result.evidence] == ["report"]
    assert result.wrong_type_excluded == []


def test_hard_exclusive_type_and_language_exclude_only_proven_mismatch(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    prompt = "Review AI and labor. Cite only English-language journal articles."
    rows = [
        {"evidence_id": "journal", "title": "AI and work", "snippet": "Labor market study",
         "document_type": "JOURNAL_ARTICLE", "language": "en"},
        {"evidence_id": "report", "title": "AI and work policy", "snippet": "Labor market report",
         "document_type": "REPORT", "language": "en"},
        {"evidence_id": "spanish", "title": "IA y trabajo", "snippet": "Mercado laboral",
         "document_type": "JOURNAL_ARTICLE", "language": "es"},
        {"evidence_id": "unknown", "title": "AI labor evidence", "snippet": "Employment analysis",
         "document_type": "UNKNOWN"},
    ]
    result = apply_scope_contract(
        rows,
        prompt,
        lambda _prompt: "0: ON\n1: ON\n2: ON\n3: ON",
        constraints={"source_types": ["journal_article"], "languages": ["en"]},
    )
    assert [row["evidence_id"] for row in result.evidence] == ["journal"]
    assert {item["evidence_id"] for item in result.wrong_type_excluded} == {
        "report", "spanish", "unknown",
    }
    assert all(item["retained_in_source_corpus"] for item in result.wrong_type_excluded)


def test_topic_judge_error_fails_open(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")

    def _raise(_prompt: str) -> str:
        raise TimeoutError("judge timed out")

    rows = _rows()
    result = apply_scope_contract(rows, RQ, _raise)
    assert [row["evidence_id"] for row in result.evidence] == ["labor", "knee"]
    assert result.off_topic_excluded == []
    assert result.judge_failed_open is True


def test_same_subject_wrong_aspect_is_kept_not_thinned(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1")
    rows = [{
        "evidence_id": "adjacent",
        "title": "Artificial intelligence and organizational strategy",
        "snippet": "A study of AI adoption in firms.",
    }]
    result = apply_scope_contract(
        rows,
        RQ,
        lambda _prompt: "0: OFF_ASPECT",
    )
    assert [row["evidence_id"] for row in result.evidence] == ["adjacent"]
    assert result.off_topic_excluded == []


def test_deepening_queries_are_prompt_and_wanted_type_derived():
    queries = build_scope_deepening_queries(
        "Compare AI labor displacement; assess wage effects and worker transitions.",
        {"source_types": ["journal_article"]},
    )
    assert queries[0].startswith("Compare AI labor displacement")
    assert any(query.endswith("journal article") for query in queries)


def test_quality_descriptor_cannot_disable_exclusive_document_type_gate(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    prompt = "Cite only high-quality journal articles."
    rows = [
        {"evidence_id": "journal", "title": "Study", "document_type": "JOURNAL_ARTICLE"},
        {"evidence_id": "news", "title": "Newsroom item", "document_type": "NEWS"},
        {"evidence_id": "unknown", "title": "Unresolved source", "document_type": "UNKNOWN"},
    ]
    result = apply_scope_contract(
        rows,
        prompt,
        lambda _prompt: "0: ON\n1: ON\n2: ON",
        constraints={"source_types": ["journal_article", "high-quality"]},
    )
    assert [row["evidence_id"] for row in result.evidence] == ["journal"]
    assert {item["evidence_id"] for item in result.wrong_type_excluded} == {
        "news", "unknown",
    }


def test_exclusive_language_detection_uses_extracted_value_not_language_list(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    result = apply_scope_contract(
        [
            {
                "evidence_id": "it",
                "title": "Studio",
                "document_type": "JOURNAL_ARTICLE",
                "language": "it",
            },
            {
                "evidence_id": "en",
                "title": "Study",
                "document_type": "JOURNAL_ARTICLE",
                "language": "en",
            },
        ],
        "Cite only Italian-language journal articles.",
        lambda _prompt: "0: ON\n1: ON",
        constraints={"source_types": ["journal_article"], "languages": ["it"]},
    )
    assert [row["evidence_id"] for row in result.evidence] == ["it"]
