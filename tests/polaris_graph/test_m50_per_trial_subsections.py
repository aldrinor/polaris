"""Named-study subsection selection without a domain-specific study catalog."""

from __future__ import annotations

import asyncio

from src.polaris_graph.generator.multi_section_generator import (
    _M50_SUBSECTION_SYSTEM_PROMPT,
    _call_m50_per_study_subsection,
    _m50_select_candidate_studies,
)


def _source(
    evidence_id: str,
    marker: str,
    *,
    direct_quote: str | None = None,
    refetched_quote: str = "",
) -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "title": f"{marker} primary publication",
        "direct_quote": (
            direct_quote
            if direct_quote is not None
            else f"{marker} source frame. " + ("source-derived detail " * 10)
        ),
        "_m42b_refetched_quote": refetched_quote,
    }


def _bibliography(*evidence_ids: str) -> list[dict[str, object]]:
    return [
        {"num": index, "evidence_id": evidence_id}
        for index, evidence_id in enumerate(evidence_ids, start=1)
    ]


def test_every_qualifying_primary_source_can_be_selected() -> None:
    pool = {
        "ev_orion": _source("ev_orion", "ORION-4"),
        "ev_nova": _source("ev_nova", "NOVA-2"),
    }
    candidates = _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_orion"], "NOVA-2": ["ev_nova"]},
        _bibliography("ev_orion", "ev_nova"),
        {"ORION-4", "NOVA-2"},
    )
    assert [candidate[0] for candidate in candidates] == ["ORION-4", "NOVA-2"]
    assert all(len(candidate) == 4 for candidate in candidates)


def test_single_qualifying_source_preserves_general_capability() -> None:
    pool = {"ev_orion": _source("ev_orion", "ORION-4")}
    candidates = _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_orion"]},
        _bibliography("ev_orion"),
        {"ORION-4"},
    )
    assert len(candidates) == 1
    assert candidates[0][0] == "ORION-4"


def test_scope_metadata_excludes_indirect_anchor() -> None:
    pool = {
        "ev_direct": _source("ev_direct", "ORION-4"),
        "ev_indirect": _source("ev_indirect", "NOVA-2"),
    }
    candidates = _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_direct"], "NOVA-2": ["ev_indirect"]},
        _bibliography("ev_direct", "ev_indirect"),
        {"ORION-4"},
    )
    assert [candidate[0] for candidate in candidates] == ["ORION-4"]


def test_thin_source_quote_is_not_sent_to_writer() -> None:
    pool = {
        "ev_thin": _source(
            "ev_thin",
            "ORION-4",
            direct_quote="short source fragment",
        ),
    }
    assert _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_thin"]},
        _bibliography("ev_thin"),
        {"ORION-4"},
    ) == []


def test_richer_refetched_quote_is_carried_to_writer() -> None:
    refetched = "REFETCHED SOURCE FRAME " + ("verified detail " * 12)
    pool = {
        "ev_orion": _source(
            "ev_orion",
            "ORION-4",
            direct_quote="thin",
            refetched_quote=refetched,
        ),
    }
    candidates = _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_orion"]},
        _bibliography("ev_orion"),
        {"ORION-4"},
    )
    assert candidates[0][3] == refetched


def test_equal_length_quotes_prefer_direct_source_text() -> None:
    direct = "DIRECT_" + ("a" * 120)
    refetched = "REFETCH" + ("b" * 120)
    pool = {
        "ev_orion": _source(
            "ev_orion",
            "ORION-4",
            direct_quote=direct,
            refetched_quote=refetched,
        ),
    }
    candidates = _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_orion"]},
        _bibliography("ev_orion"),
        {"ORION-4"},
    )
    assert candidates[0][3] == direct


def test_missing_bibliography_marker_excludes_source() -> None:
    pool = {"ev_orion": _source("ev_orion", "ORION-4")}
    assert _m50_select_candidate_studies(
        pool,
        {"ORION-4": ["ev_orion"]},
        [],
        {"ORION-4"},
    ) == []


def test_prompt_requests_source_frame_without_domain_vocabulary() -> None:
    prompt = _M50_SUBSECTION_SYSTEM_PROMPT.casefold()
    for phrase in (
        "sample size",
        "comparator or reference condition",
        "primary measure",
        "effect estimate and uncertainty",
        "copy the source's own vocabulary",
    ):
        assert phrase in prompt


def test_canonical_call_uses_study_name(monkeypatch) -> None:
    received: dict[str, object] = {}

    class _Response:
        content = "Source-bound paragraph [3]."
        input_tokens = 11
        output_tokens = 7

    class _Client:
        def __init__(self, *, model: str) -> None:
            received["model"] = model

        async def generate(self, **kwargs):
            received.update(kwargs)
            return _Response()

        async def close(self) -> None:
            received["closed"] = True

    monkeypatch.setattr(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        _Client,
    )
    text, input_tokens, output_tokens = asyncio.run(
        _call_m50_per_study_subsection(
            study_name="ORION-4",
            direct_quote="A source-derived frame with a measured value of 18.4 ms.",
            biblio_num=3,
            model="test-model",
        )
    )
    assert text == "Source-bound paragraph [3]."
    assert (input_tokens, output_tokens) == (11, 7)
    assert "Study/source identifier: ORION-4" in str(received["prompt"])
    assert received["closed"] is True
