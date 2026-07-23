"""Primary-source routing and named-study citation tests."""

from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _m44_detect_primary_ev_ids,
    _m44_find_study_mentions,
    _m44_inject_primaries_into_outline,
    _m44_section_is_primary_eligible,
    _m44_sentence_spans,
    _m44_validate_primary_same_sentence,
)


def _primary_row(
    evidence_id: str,
    anchor: str,
    *,
    metric: str,
    section: str = "",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "title": f"{anchor} primary publication about {metric}",
        "direct_quote": f"{anchor} reported {metric}.",
        "metric": metric,
        "section": section,
        "is_primary_source": True,
        "source_url": f"https://example.test/{evidence_id}",
    }


def test_any_named_evidence_section_is_eligible_on_compatibility_path() -> None:
    for title in ("Performance", "Energy", "Methods", "Limitations"):
        assert _m44_section_is_primary_eligible(title)
    assert not _m44_section_is_primary_eligible("")


def test_primary_detection_uses_anchor_and_source_role_metadata() -> None:
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
        "ev_review": {
            "evidence_id": "ev_review",
            "title": "ORION-4 systematic review",
            "is_primary_source": True,
        },
    }
    assert _m44_detect_primary_ev_ids(
        pool,
        ["ORION-4", "NOVA-2"],
    ) == {"ORION-4": ["ev_orion"]}


def test_primary_is_preferred_ahead_of_derivative_sources() -> None:
    plans = [
        SectionPlan(
            title="Performance",
            focus="Compare median latency.",
            ev_ids=["ev_post_analysis", "ev_review"],
        ),
    ]
    pool = {
        "ev_primary": _primary_row(
            "ev_primary",
            "ORION-4",
            metric="median latency",
        ),
    }
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_primary"]},
        evidence_pool=pool,
    )
    assert updated[0].ev_ids == [
        "ev_primary",
        "ev_post_analysis",
        "ev_review",
    ]
    assert log[0]["action"] == "injected"


def test_routing_vocabulary_is_derived_from_evidence_rows() -> None:
    plans = [
        SectionPlan(
            title="Performance",
            focus="Compare median latency.",
            ev_ids=["ev_perf"],
        ),
        SectionPlan(
            title="Energy",
            focus="Compare energy consumption.",
            ev_ids=["ev_energy_existing"],
        ),
    ]
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
        "ev_nova": _primary_row(
            "ev_nova",
            "NOVA-2",
            metric="energy consumption",
        ),
    }
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {
            "ORION-4": ["ev_orion"],
            "NOVA-2": ["ev_nova"],
        },
        evidence_pool=pool,
    )
    assert updated[0].ev_ids[0] == "ev_orion"
    assert "ev_nova" not in updated[0].ev_ids
    assert updated[1].ev_ids[0] == "ev_nova"
    assert "ev_orion" not in updated[1].ev_ids
    assert any(entry["action"] == "skipped_evidence_affinity" for entry in log)


def test_evidence_metadata_path_does_not_route_to_unrelated_section() -> None:
    plans = [
        SectionPlan(
            title="Legal history",
            focus="Summarize enacted provisions.",
            ev_ids=["ev_law"],
        ),
    ]
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
    }
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_orion"]},
        evidence_pool=pool,
    )
    assert updated[0].ev_ids == ["ev_law"]
    assert log[0]["action"] == "skipped_evidence_affinity"


def test_legacy_call_without_rows_keeps_primary_custody_fallback() -> None:
    plans = [
        SectionPlan(title="Evidence", focus="Synthesize findings.", ev_ids=[]),
    ]
    updated, _ = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_orion"]},
    )
    assert updated[0].ev_ids == ["ev_orion"]


def test_already_present_primary_is_not_duplicated() -> None:
    plans = [
        SectionPlan(
            title="Performance",
            focus="Median latency.",
            ev_ids=["ev_orion", "ev_other"],
        ),
    ]
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
    }
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_orion"]},
        evidence_pool=pool,
    )
    assert updated[0].ev_ids == ["ev_orion", "ev_other"]
    assert log[0]["action"] == "already_present"


def test_default_path_does_not_count_evict_existing_evidence() -> None:
    plans = [
        SectionPlan(
            title="Performance",
            focus="Median latency.",
            ev_ids=["ev_a", "ev_b"],
        ),
    ]
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
    }
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_orion"]},
        max_ev_per_section=1,
        evidence_pool=pool,
    )
    assert updated[0].ev_ids == ["ev_orion", "ev_a", "ev_b"]
    assert log[0]["action"] == "injected"


def test_archetype_mode_preserves_field_neutral_routing() -> None:
    plans = [
        SectionPlan(
            title="Latency under sustained load",
            focus="Compare median latency.",
            ev_ids=["ev_existing"],
            archetype="Quantitative-Comparison",
        ),
        SectionPlan(
            title="Historical context",
            focus="Describe the project.",
            ev_ids=["ev_history"],
            archetype="Background",
        ),
    ]
    pool = {
        "ev_orion": _primary_row(
            "ev_orion",
            "ORION-4",
            metric="median latency",
        ),
    }
    updated, _ = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_orion"]},
        use_archetype=True,
        evidence_pool=pool,
    )
    assert updated[0].ev_ids[0] == "ev_orion"
    assert updated[0].archetype == "Quantitative-Comparison"
    assert updated[1].ev_ids == ["ev_history"]


def test_named_study_mentions_use_exact_boundaries() -> None:
    text = "ORION-4 and NOVA-2 reported results; ORION-40 did not."
    assert [item[0] for item in _m44_find_study_mentions(
        text,
        ["ORION-4", "NOVA-2"],
    )] == ["ORION-4", "NOVA-2"]
    assert _m44_find_study_mentions("ORION-40", ["ORION-4"]) == []


def test_sentence_span_parser_handles_terminal_and_unterminated_text() -> None:
    text = "First sentence. Second sentence! Third?"
    assert len(_m44_sentence_spans(text)) == 3
    unterminated = "Sentence without terminal punctuation"
    assert _m44_sentence_spans(unterminated) == [(0, len(unterminated))]
    assert _m44_sentence_spans("") == []


def test_primary_cited_in_same_sentence_passes() -> None:
    assert _m44_validate_primary_same_sentence(
        "ORION-4 reported median latency of 18.4 ms [1].",
        {"ORION-4": ["ev_orion"]},
        [{"num": 1, "evidence_id": "ev_orion"}],
    ) == []


def test_primary_cited_in_previous_or_next_sentence_passes() -> None:
    bibliography = [{"num": 1, "evidence_id": "ev_orion"}]
    primary = {"ORION-4": ["ev_orion"]}
    assert _m44_validate_primary_same_sentence(
        "The primary publication reports the result [1]. "
        "ORION-4 is the named study.",
        primary,
        bibliography,
    ) == []
    assert _m44_validate_primary_same_sentence(
        "ORION-4 is the named study. "
        "The primary publication reports the result [1].",
        primary,
        bibliography,
    ) == []


def test_primary_citation_two_sentences_away_fails() -> None:
    violations = _m44_validate_primary_same_sentence(
        "ORION-4 reported the result. "
        "A second statement adds context. "
        "The primary publication is cited here [1].",
        {"ORION-4": ["ev_orion"]},
        [{"num": 1, "evidence_id": "ev_orion"}],
    )
    assert len(violations) == 1
    assert violations[0]["anchor"] == "ORION-4"


def test_derivative_citation_does_not_satisfy_primary_validator() -> None:
    violations = _m44_validate_primary_same_sentence(
        "ORION-4 reported the result [2].",
        {"ORION-4": ["ev_orion"]},
        [
            {"num": 1, "evidence_id": "ev_orion"},
            {"num": 2, "evidence_id": "ev_review"},
        ],
    )
    assert len(violations) == 1
    assert violations[0]["citations_found"] == ["ev_review"]


def test_unmentioned_source_identifier_creates_no_violation() -> None:
    assert _m44_validate_primary_same_sentence(
        "The scheduler reduced latency [1].",
        {"ORION-4": ["ev_orion"]},
        [{"num": 1, "evidence_id": "ev_other"}],
    ) == []
