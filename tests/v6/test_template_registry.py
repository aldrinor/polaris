"""Tests for the v6 template content registry (Phase 2A.6 substrate).

Re-keyed by I-rdy-005 (#501) to the canonical 8 templates.
"""

from __future__ import annotations

import pytest

from polaris_v6.templates.registry import (
    TemplateContent,
    list_template_ids,
    load_template,
)

CANONICAL_8 = [
    "clinical",
    "policy",
    "tech",
    "due_diligence",
    "ai_sovereignty",
    "canada_us",
    "workforce",
    "custom",
]


def test_all_canonical_templates_load():
    ids = list_template_ids()
    for expected in CANONICAL_8:
        assert expected in ids, f"missing template: {expected}"
    assert set(ids) == set(CANONICAL_8)


@pytest.mark.parametrize("template_id", CANONICAL_8)
def test_template_validates_against_schema(template_id):
    content = load_template(template_id)
    assert isinstance(content, TemplateContent)
    assert content.template_id == template_id
    assert "T1" in content.source_tiers
    # `custom` is intentionally permissive on tier minimums (free-form scope);
    # every other template requires at least one T1 source.
    if template_id == "custom":
        assert content.min_sources_per_tier["T1"] >= 0
    else:
        assert content.min_sources_per_tier["T1"] >= 1
    assert len(content.frame_manifest) >= 2


def test_policy_has_regulatory_frame():
    policy = load_template("policy")
    frame_ids = [f.frame_id for f in policy.frame_manifest]
    assert "regulatory_decision" in frame_ids
    assert "hta_assessment" in frame_ids


def test_tech_has_benchmark_frame():
    tech = load_template("tech")
    frame_ids = [f.frame_id for f in tech.frame_manifest]
    assert "novel_contribution" in frame_ids
    assert "benchmark_results" in frame_ids


def test_load_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        load_template("does_not_exist")


def test_sample_questions_non_empty():
    for tid in ("policy", "tech", "due_diligence", "custom"):
        content = load_template(tid)
        assert len(content.sample_questions) >= 2
        assert all(len(q) > 20 for q in content.sample_questions)
