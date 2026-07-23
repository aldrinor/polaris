"""Batch 3 behavioral tests for pre-generation relation and scope levers."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from src.polaris_graph.generator.contradiction_hedging import (
    filter_section_contradictions,
    render_section_hedging_block,
)
from src.polaris_graph.generator.contradiction_mining import (
    contradiction_mining_enabled,
    find_contradictions,
)
from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block
from src.polaris_graph.generator.relation_evidence_packs import (
    build_relation_evidence_packs,
    relation_context_for_plan,
    relation_evidence_packs_enabled,
)
from src.polaris_graph.retrieval.scope_contract import (
    ScopeContractResult,
    deepen_scope_contract,
    scope_deepening_enabled,
)


def _conflict_rows() -> list[dict]:
    return [
        {
            "evidence_id": "row_a",
            "title": "Employment response",
            "statement": "The employment rate increased after adoption.",
            "measure": "employment rate",
        },
        {
            "evidence_id": "row_b",
            "title": "Employment response",
            "statement": "The employment rate decreased after adoption.",
            "measure": "employment rate",
        },
    ]


def test_generator_judge_keeps_only_confident_comparable_conflict():
    calls: list[str] = []

    def judge(prompt: str) -> str:
        calls.append(prompt)
        return (
            '{"classification":"conflict","confident":true,'
            '"reason":"The reported direction differs for the same rate.",'
            '"subject":"employment","predicate":"rate change",'
            '"measure":"employment rate"}'
        )

    conflicts = find_contradictions(_conflict_rows(), "How does adoption affect work?", judge)

    assert len(calls) == 1
    assert conflicts == [{
        "evidence_ids": ["row_a", "row_b"],
        "subject": "employment",
        "predicate": "rate change",
        "measure": "employment rate",
        "reason": "The reported direction differs for the same rate.",
        "comparison_status": "conflict",
        "confidence": "confirmed",
    }]
    source = inspect.getsource(
        __import__(
            "src.polaris_graph.generator.contradiction_mining",
            fromlist=["find_contradictions"],
        )
    ).casefold()
    assert "semantic_conflict_detector" not in source
    assert "pg_entailment_model" not in source


def test_generator_judge_drops_compatible_and_non_comparable_pairs():
    rows = _conflict_rows()
    for classification in ("compatible", "non_comparable"):
        result = find_contradictions(
            rows,
            "How does adoption affect work?",
            lambda _prompt, value=classification: (
                f'{{"classification":"{value}","confident":true,'
                '"reason":"The bases differ.","subject":"employment",'
                '"predicate":"rate change","measure":"employment rate"}'
            ),
        )
        assert result == []


def test_conflict_routes_to_owner_hint_and_limitations_telemetry():
    conflict = {
        "evidence_ids": ["row_a", "row_b"],
        "subject": "employment",
        "predicate": "rate change",
        "measure": "employment rate",
        "reason": "The reported direction differs for the same rate.",
        "comparison_status": "conflict",
        "confidence": "confirmed",
        "section_title": "Employment effects",
    }

    owner_hints = filter_section_contradictions("Employment effects", [conflict])
    other_hints = filter_section_contradictions("Methods", [conflict])
    block = render_section_hedging_block(owner_hints)
    telemetry = _format_telemetry_block(None, [conflict])

    assert len(owner_hints) == 1
    assert other_hints == []
    assert "Rows row_a and row_b report incompatible findings" in block
    assert "population, method, period, or measure" in block
    assert "contradictions_detected: 1" in telemetry


def test_deepening_reapplies_topic_type_and_work_dedup_then_stops_on_novelty(monkeypatch):
    monkeypatch.setenv("PG_COMPOSITION_SCOPE_CONTRACT", "1")
    prompt = "Cite only English-language journal articles about employment."
    result = ScopeContractResult(
        evidence=[{
            "evidence_id": "seed",
            "source_url": "https://example.org/seed",
            "statement": "Employment increased.",
            "document_type": "JOURNAL_ARTICLE",
            "language": "en",
        }],
        constraints={
            "source_types": ["journal_article"],
            "languages": ["en"],
            "source_types_exclusive": True,
            "languages_exclusive": True,
        },
    )
    rounds = [
        [
            {
                "evidence_id": "novel",
                "source_url": "https://example.org/novel",
                "statement": "Employment decreased for a rural population.",
                "population": "rural workers",
                "document_type": "JOURNAL_ARTICLE",
                "language": "en",
            },
            {
                "evidence_id": "wrong_type",
                "source_url": "https://example.org/report",
                "statement": "Employment decreased.",
                "document_type": "REPORT",
                "language": "en",
            },
            {
                "evidence_id": "off_topic",
                "source_url": "https://example.org/clinical",
                "statement": "A surgical outcome changed.",
                "document_type": "JOURNAL_ARTICLE",
                "language": "en",
            },
            {
                "evidence_id": "same_work",
                "source_url": "https://example.org/seed",
                "statement": "Employment increased.",
                "document_type": "JOURNAL_ARTICLE",
                "language": "en",
            },
        ],
        [{
            "evidence_id": "corroborator",
            "source_url": "https://example.org/corroborator",
            "statement": "Rural workers experienced a reduction in employment.",
            "population": "rural workers",
            "document_type": "JOURNAL_ARTICLE",
            "language": "en",
        }],
    ]
    retrieval_calls = 0
    judge_calls = 0
    novelty_calls = 0

    def retrieve(_queries, _filters):
        nonlocal retrieval_calls
        value = rounds[retrieval_calls]
        retrieval_calls += 1
        return value

    def judge(_prompt):
        nonlocal judge_calls
        judge_calls += 1
        if judge_calls == 1:
            return "0: ON\n1: ON\n2: OFF_SUBJECT\n3: ON"
        return "0: ON"

    def novelty_judge(_prompt):
        nonlocal novelty_calls
        novelty_calls += 1
        return "NOVEL" if novelty_calls == 1 else "EXHAUSTED"

    deepened = deepen_scope_contract(
        result,
        prompt,
        retrieve,
        lambda _rq, _constraints, _rows: ["employment evidence"],
        judge,
        wall_seconds=60,
        novelty_judge=novelty_judge,
    )

    assert [row["evidence_id"] for row in deepened.evidence] == [
        "seed", "novel", "corroborator",
    ]
    assert {item["evidence_id"] for item in deepened.wrong_type_excluded} == {
        "wrong_type",
    }
    assert {item["evidence_id"] for item in deepened.off_topic_excluded} == {
        "off_topic",
    }
    assert deepened.deepening["rounds"] == 2
    assert deepened.deepening["stop_reason"] == "novelty_exhausted"
    assert retrieval_calls == 2
    assert novelty_calls == 2


def test_default_off_flags_are_no_ops(monkeypatch):
    for key in (
        "PG_CONTRADICTION_MINING",
        "PG_SCOPE_DEEPENING",
        "PG_RELATION_EVIDENCE_PACKS",
    ):
        monkeypatch.delenv(key, raising=False)

    assert contradiction_mining_enabled() is False
    assert scope_deepening_enabled() is False
    assert relation_evidence_packs_enabled() is False


def test_relation_packs_preserve_membership_and_synthesis_gets_global_map():
    plans = [
        SimpleNamespace(
            title="Employment effects",
            focus="Compare employment outcomes.",
            ev_ids=["row_a", "row_c"],
        ),
        SimpleNamespace(
            title="Cross-study synthesis",
            focus="Integrate convergence and disagreement.",
            ev_ids=["row_b"],
        ),
    ]
    original_membership = [list(plan.ev_ids) for plan in plans]
    pool = {
        "row_a": {
            "evidence_id": "row_a",
            "proposition_id": "employment_direction",
            "statement": "Employment increased.",
            "design": "panel",
            "population": "workers",
            "measure": "employment rate",
            "observed_or_modeled": "observed",
        },
        "row_b": {
            "evidence_id": "row_b",
            "proposition_id": "employment_direction",
            "statement": "Employment decreased.",
            "design": "simulation",
            "population": "workers",
            "measure": "employment rate",
            "observed_or_modeled": "modeled",
        },
        "row_c": {
            "evidence_id": "row_c",
            "proposition_id": "employment_direction",
            "statement": "Employment increased in another panel.",
            "design": "panel",
        },
    }
    conflict = {
        "evidence_ids": ["row_a", "row_b"],
        "subject": "employment",
        "predicate": "direction",
        "measure": "employment rate",
        "reason": "The direction differs.",
        "comparison_status": "conflict",
        "confidence": "confirmed",
    }

    packs, global_map, owned = build_relation_evidence_packs(plans, pool, [conflict])
    body_local, body_global = relation_context_for_plan(plans[0], packs, global_map)
    synthesis_local, synthesis_global = relation_context_for_plan(plans[1], packs, global_map)

    assert [list(plan.ev_ids) for plan in plans] == original_membership
    assert '"supporting_evidence_ids": ["row_a", "row_c"]' in packs["Employment effects"]
    assert '"design": "panel"' in body_local
    assert body_global == ""
    assert synthesis_local
    assert synthesis_global == global_map
    assert '"section": "Employment effects"' in synthesis_global
    assert '"section": "Cross-study synthesis"' in synthesis_global
    assert owned[0]["section_title"] == "Employment effects"
