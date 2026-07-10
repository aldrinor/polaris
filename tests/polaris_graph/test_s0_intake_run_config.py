"""S0 INTAKE offline unit battery (Design 3 Level-0 + master §1 RunConfig contract).

Pure logic, no network/GPU: every extractor runs regex-only (llm_fn=None) and the
resolver runs against an empty env, so these assertions are deterministic. Covers the
deliverable-spec extractor, the breadth-directive parser, the scope companions, and the
RunConfig precedence resolver + cp0 writer.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.retrieval.breadth_directive_parser import (
    BREADTH_NARROW,
    BREADTH_WIDE,
    parse_breadth_directive,
)
from src.polaris_graph.retrieval.deliverable_spec_extractor import (
    extract_deliverable_spec,
)
from src.polaris_graph.run_config import (
    SOURCE_DEFAULT,
    SOURCE_PANEL,
    SOURCE_PARSED,
    assemble_run_config,
    load_cp0_run_config,
    load_knob_registry,
    write_cp0_run_config,
)


# ── deliverable extractor ─────────────────────────────────────────────────────
def test_deliverable_empty_prompt_is_empty_spec():
    spec = extract_deliverable_spec("", llm_fn=None)
    assert spec.is_empty()
    assert spec.to_dict()["source"] == "regex"


def test_deliverable_no_ask_is_empty():
    spec = extract_deliverable_spec(
        "What are the cardiovascular outcomes of tirzepatide?", llm_fn=None)
    assert spec.is_empty()


def test_deliverable_mechanical_fields_with_spans():
    spec = extract_deliverable_spec(
        "Write a two-page policy memo with Harvard references, about 1500 words.",
        llm_fn=None)
    assert spec.reference_style == "harvard"
    assert spec.length_target_words == 1500
    assert spec.length_target_pages == 2
    assert spec.deliverable_type in {"memo", "brief"}
    # anti-invention: every populated field carries an in-prompt span
    for name, span in spec.trigger_spans.items():
        assert span.lower() in "write a two-page policy memo with harvard references, about 1500 words."


def test_deliverable_hard_length_strictness():
    spec = extract_deliverable_spec("Give me a brief of no more than 800 words.", llm_fn=None)
    assert spec.length_target_words == 800
    assert spec.length_strictness == "hard"


def test_deliverable_structure_slots_wired():
    spec = extract_deliverable_spec(
        "Include a section on safety signals and organize by region.", llm_fn=None)
    assert spec.structure_slots  # O2 instruction slots consumed


def test_deliverable_from_dict_roundtrip():
    spec = extract_deliverable_spec(
        "Plain-language FAQ for parents with APA references.", llm_fn=None)
    from src.polaris_graph.retrieval.deliverable_spec_extractor import DeliverableSpec
    assert DeliverableSpec.from_dict(spec.to_dict()).to_dict() == spec.to_dict()


# ── breadth directive parser ─────────────────────────────────────────────────
def test_breadth_empty_is_empty():
    assert parse_breadth_directive("", llm_fn=None).is_empty()


def test_breadth_explicit_count_over_35():
    bd = parse_breadth_directive("Run at least 60 queries on this topic.", llm_fn=None)
    assert bd.query_count == 60
    assert bd.query_count >= 35
    assert bd.trigger_spans["query_count"].lower() in "run at least 60 queries on this topic."


def test_breadth_searches_per_query():
    bd = parse_breadth_directive("Use 15 searches per query.", llm_fn=None)
    assert bd.searches_per_query == 15


def test_breadth_class_wide_and_narrow():
    assert parse_breadth_directive("Do an exhaustive review.", llm_fn=None).breadth_class == BREADTH_WIDE
    assert parse_breadth_directive("Just a quick overview please.", llm_fn=None).breadth_class == BREADTH_NARROW


def test_breadth_bare_brief_is_not_narrow():
    # "policy brief" is a deliverable type, not a breadth NARROW ask.
    bd = parse_breadth_directive("Write a policy brief on the topic.", llm_fn=None)
    assert bd.breadth_class is None


# ── RunConfig resolver + precedence + cp0 ─────────────────────────────────────
def test_empty_prompt_all_default_or_env():
    rc = assemble_run_config("", env={})
    # No ask ⇒ nothing parsed ⇒ every knob is default (empty env).
    for kid, p in rc.provenance.items():
        assert p.source == SOURCE_DEFAULT, f"{kid} unexpectedly {p.source}"
    assert rc.breadth.query_budget == 35  # registry code_default


def test_env_beats_default_parsed_beats_env():
    q = "Run at least 50 queries."
    rc_env = assemble_run_config("no ask here", env={"PG_QGEN_FS_RESEARCHER_MAX_QUERIES": "80"})
    assert rc_env.breadth.query_budget == 80
    assert rc_env.source_of("query_budget") == "env"
    rc_parsed = assemble_run_config(q, env={"PG_QGEN_FS_RESEARCHER_MAX_QUERIES": "80"})
    assert rc_parsed.breadth.query_budget == 50  # parsed beats a merely-default env
    assert rc_parsed.source_of("query_budget") == SOURCE_PARSED


def test_panel_beats_prompt():
    q = "Run at least 50 queries."
    rc = assemble_run_config(q, env={}, panel_overrides={"query_budget": 99})
    assert rc.breadth.query_budget == 99
    assert rc.source_of("query_budget") == SOURCE_PANEL


def test_scope_axes_land_parsed():
    q = ("Studies since 2019 and before June 2023, peer-reviewed journal articles only, "
         "focused on European sources, in English, research by Anthony Fauci.")
    rc = assemble_run_config(q, env={})
    assert rc.scope.date_end == "2023-06"
    assert "peer_reviewed_journal" in rc.scope.source_types
    assert rc.scope.geography
    assert rc.scope.language == "en"
    assert rc.scope.authors == ["Anthony Fauci"]
    assert rc.scope.peer_reviewed_only is True


def test_cp0_carries_every_knob_no_hardcode(tmp_path):
    registry = load_knob_registry()
    rc = assemble_run_config("Run at least 45 queries; Harvard references.", env={}, registry=registry)
    path = write_cp0_run_config(rc, tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    registry_ids = {str(r["id"]) for r in registry}
    default_map = {str(r["id"]): r.get("code_default") for r in registry}
    assert set(raw["provenance"].keys()) == registry_ids
    for kid, pv in raw["provenance"].items():
        assert pv["source"] in {"default", "env", "parsed", "panel"}
        if pv["source"] == "default":
            assert pv["value"] == default_map[kid], f"{kid} default != registry (hardcoded?)"
    # round-trip
    reloaded = load_cp0_run_config(path)
    assert reloaded.question_sha == rc.question_sha
    assert reloaded.get("query_budget") == 45


def test_non_default_knobs_disclosure():
    rc = assemble_run_config("Run at least 45 queries.", env={})
    nd = {p["knob_id"] for p in rc.non_default_knobs()}
    assert "query_budget" in nd
    # a knob nobody set must NOT appear in the disclosure
    assert "fetch_cap" not in nd


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
