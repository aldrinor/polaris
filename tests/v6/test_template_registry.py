"""Tests for the v6 template content registry (Phase 2A.6 substrate)."""

from __future__ import annotations

import pytest

from polaris_v6.templates.registry import (
    TemplateContent,
    list_template_ids,
    load_template,
)


def test_defense_and_climate_load():
    ids = list_template_ids()
    assert "defense" in ids
    assert "climate" in ids


@pytest.mark.parametrize("template_id", ["defense", "climate"])
def test_template_validates_against_schema(template_id):
    content = load_template(template_id)
    assert isinstance(content, TemplateContent)
    assert content.template_id == template_id
    assert "T1" in content.source_tiers
    assert content.min_sources_per_tier["T1"] >= 1
    assert len(content.frame_manifest) >= 2


def test_defense_has_norad_frame():
    defense = load_template("defense")
    frame_ids = [f.frame_id for f in defense.frame_manifest]
    assert "norad_modernization" in frame_ids
    assert "arctic_sovereignty" in frame_ids


def test_climate_has_emissions_intensity_frame():
    climate = load_template("climate")
    frame_ids = [f.frame_id for f in climate.frame_manifest]
    assert "emissions_intensity" in frame_ids
    assert "critical_minerals" in frame_ids


def test_load_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        load_template("does_not_exist")


def test_sample_questions_non_empty():
    for tid in ("defense", "climate"):
        content = load_template(tid)
        assert len(content.sample_questions) >= 2
        assert all(len(q) > 20 for q in content.sample_questions)
