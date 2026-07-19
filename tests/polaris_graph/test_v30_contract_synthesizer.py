"""I-arch-001b — v30_contract_synthesizer coverage."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from polaris_graph.v30_contract_synthesizer import build_report_contract
from polaris_v6.templates.registry import load_template

ALL_V6_TEMPLATES = [
    "ai_sovereignty", "canada_us", "clinical", "custom",
    "due_diligence", "policy", "tech", "workforce",
]

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "v30_contracts"


def _load_v6_template(template_id: str) -> dict:
    return load_template(template_id).model_dump()


@pytest.mark.parametrize("template_id", ALL_V6_TEMPLATES)
def test_build_v30_contract_matches_golden_fixture(template_id: str) -> None:
    """build_report_contract output for the fixture slug must equal the golden file."""
    v6_tmpl = _load_v6_template(template_id)
    slug = f"{template_id}_fixture"
    actual = build_report_contract(v6_tmpl, slug, question=None)
    expected = json.loads((FIXTURE_DIR / f"{template_id}.json").read_text(encoding="utf-8"))
    assert actual == expected


@pytest.mark.parametrize("template_id", ALL_V6_TEMPLATES)
def test_fixture_round_trips_via_load_report_contract(template_id: str) -> None:
    """The fixture merged under per_query_report_contract loads cleanly."""
    from polaris_graph.nodes.report_contract import load_report_contract_for_slug

    fixture = json.loads((FIXTURE_DIR / f"{template_id}.json").read_text(encoding="utf-8"))
    slug = next(iter(fixture))
    scope_tmpl = {"per_query_report_contract": dict(fixture)}
    rc = load_report_contract_for_slug(scope_tmpl, slug)
    assert rc is not None
    assert rc.schema_version == "v30.1"
    assert len(rc.required_entities) >= 1
    assert len(rc.rendering_slots) >= 1
    # Referential integrity: every entity's rendering_slot resolves to a declared slot.
    declared_slots = {s.id for s in rc.rendering_slots}
    for e in rc.required_entities:
        assert e.rendering_slot in declared_slots


@pytest.mark.parametrize("template_id", ALL_V6_TEMPLATES)
def test_synthesized_contract_compiles_via_compile_frame(template_id: str) -> None:
    """Synth output compiles through M-55 compile_frame, not just loader."""
    from polaris_graph.nodes.frame_compiler import compile_frame

    v6_tmpl = _load_v6_template(template_id)
    slug = "test_compile_slug"
    contract = build_report_contract(v6_tmpl, slug, question="test question")
    scope_tmpl = {"per_query_report_contract": dict(contract)}
    cf = compile_frame("test question", scope_tmpl, slug)
    assert cf is not None
    assert len(cf.evidence_bindings) >= 1


@pytest.mark.parametrize("template_id", ALL_V6_TEMPLATES)
def test_synthesized_bindings_have_fetchable_url(template_id: str) -> None:
    """Every binding has a resolvable locator: doi OR pmid OR fetchable url_pattern.

    Per Codex iter-4 P1 verification: M-56's `_fetch_url_pattern()` treats the
    value as a literal URL, NOT a regex. A regex locator would fail to fetch.
    """
    from polaris_graph.nodes.frame_compiler import compile_frame

    v6_tmpl = _load_v6_template(template_id)
    slug = "fetchability_slug"
    contract = build_report_contract(v6_tmpl, slug, question="test question")
    scope_tmpl = {"per_query_report_contract": dict(contract)}
    cf = compile_frame("test question", scope_tmpl, slug)
    assert cf is not None
    entities = cf.contract.entities_by_id()
    for binding in cf.evidence_bindings:
        entity = entities[binding.entity_id]
        has_resolvable = bool(entity.doi or entity.pmid or entity.url_pattern)
        assert has_resolvable, (
            f"binding entity_id={binding.entity_id!r} is anchor-only; "
            f"M-56 would treat as FRAME_GAP_UNRECOVERABLE"
        )
        if entity.url_pattern and not (entity.doi or entity.pmid):
            parsed = urlparse(entity.url_pattern)
            assert parsed.scheme in ("http", "https"), (
                f"url_pattern {entity.url_pattern!r} not http(s); M-56 would fail"
            )
            assert parsed.netloc, (
                f"url_pattern {entity.url_pattern!r} missing netloc"
            )


def test_anchor_is_stable_and_collision_safe() -> None:
    """Same (template, frame, slug) → same anchor; different inputs → different anchor."""
    v6 = _load_v6_template("clinical")
    c1 = build_report_contract(v6, "slug_alpha")
    c2 = build_report_contract(v6, "slug_alpha")
    c3 = build_report_contract(v6, "slug_beta")
    anchors_1 = {e["anchor"] for e in c1["slug_alpha"]["required_entities"]}
    anchors_2 = {e["anchor"] for e in c2["slug_alpha"]["required_entities"]}
    anchors_3 = {e["anchor"] for e in c3["slug_beta"]["required_entities"]}
    assert anchors_1 == anchors_2  # determinism
    assert anchors_1.isdisjoint(anchors_3)  # collision-free across slugs


def test_url_pattern_rotates_through_t1_sources() -> None:
    """If T1 has N URLs and contract has M ≥ N entities, entity[i].url_pattern == T1[i % N]."""
    v6 = _load_v6_template("clinical")
    t1 = v6["source_tiers"]["T1"]
    contract = build_report_contract(v6, "rotation_slug")
    entities = contract["rotation_slug"]["required_entities"]
    for i, e in enumerate(entities):
        assert e["url_pattern"] == t1[i % len(t1)], (
            f"entity[{i}] url_pattern={e['url_pattern']!r} != T1[{i % len(t1)}]={t1[i % len(t1)]!r}"
        )


def test_empty_t1_falls_back_to_known_url() -> None:
    """Defensive fallback for templates with empty T1 (none exist today, but ...)."""
    v6 = _load_v6_template("clinical")
    v6["source_tiers"]["T1"] = []
    contract = build_report_contract(v6, "empty_t1_slug")
    for e in contract["empty_t1_slug"]["required_entities"]:
        parsed = urlparse(e["url_pattern"])
        assert parsed.scheme in ("http", "https")
        assert parsed.netloc
