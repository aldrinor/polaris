"""Tests for section_blueprint — clinical scope_class -> ordered sections."""

from __future__ import annotations

import pytest

from polaris_graph.generator2.section_blueprint import (
    CLINICAL_DIAGNOSIS,
    CLINICAL_EFFICACY,
    CLINICAL_PROGNOSIS,
    CLINICAL_SAFETY,
    DEFAULT_BLUEPRINT,
    Blueprint,
    SectionPlan,
    blueprint_for_scope_class,
    known_scope_classes,
    register_blueprint,
)


# ---------- Built-in blueprints ----------

def test_efficacy_blueprint_has_4_sections():
    assert len(CLINICAL_EFFICACY.sections) == 4


def test_safety_blueprint_has_4_sections():
    assert len(CLINICAL_SAFETY.sections) == 4


def test_diagnosis_blueprint_has_4_sections():
    assert len(CLINICAL_DIAGNOSIS.sections) == 4


def test_prognosis_blueprint_has_4_sections():
    assert len(CLINICAL_PROGNOSIS.sections) == 4


def test_efficacy_section_ids_unique():
    ids = [s.section_id for s in CLINICAL_EFFICACY.sections]
    assert len(ids) == len(set(ids))


def test_each_section_has_brief():
    for bp in (
        CLINICAL_EFFICACY,
        CLINICAL_SAFETY,
        CLINICAL_DIAGNOSIS,
        CLINICAL_PROGNOSIS,
    ):
        for plan in bp.sections:
            assert plan.section_brief.strip()
            assert plan.section_title.strip()
            assert plan.section_id.startswith("sec_")


# ---------- Resolution ----------

def test_blueprint_for_efficacy():
    bp = blueprint_for_scope_class("clinical_efficacy")
    assert bp is CLINICAL_EFFICACY


def test_blueprint_for_safety():
    bp = blueprint_for_scope_class("clinical_safety")
    assert bp is CLINICAL_SAFETY


def test_blueprint_for_diagnosis():
    bp = blueprint_for_scope_class("clinical_diagnosis")
    assert bp is CLINICAL_DIAGNOSIS


def test_blueprint_for_prognosis():
    bp = blueprint_for_scope_class("clinical_prognosis")
    assert bp is CLINICAL_PROGNOSIS


def test_blueprint_for_unknown_falls_back():
    bp = blueprint_for_scope_class("nonexistent")
    assert bp is DEFAULT_BLUEPRINT


def test_blueprint_for_none_falls_back():
    bp = blueprint_for_scope_class(None)
    assert bp is DEFAULT_BLUEPRINT


def test_default_blueprint_is_efficacy():
    """Conservative default per architecture proposal."""
    assert DEFAULT_BLUEPRINT is CLINICAL_EFFICACY


# ---------- Introspection ----------

def test_known_scope_classes_includes_all_four():
    classes = known_scope_classes()
    for expected in (
        "clinical_efficacy",
        "clinical_safety",
        "clinical_diagnosis",
        "clinical_prognosis",
    ):
        assert expected in classes


def test_known_scope_classes_returns_sorted():
    classes = known_scope_classes()
    assert list(classes) == sorted(classes)


# ---------- Custom registration ----------

def test_register_custom_blueprint():
    custom = Blueprint(
        scope_class="experimental_test_only",
        sections=(
            SectionPlan(
                "sec_one", "One", "single-section experimental layout"
            ),
        ),
    )
    register_blueprint(custom)
    bp = blueprint_for_scope_class("experimental_test_only")
    assert bp is custom


# ---------- Frozen dataclass ----------

def test_blueprint_is_frozen():
    with pytest.raises(Exception):
        CLINICAL_EFFICACY.scope_class = "tampered"  # type: ignore[misc]


def test_section_plan_is_frozen():
    plan = CLINICAL_EFFICACY.sections[0]
    with pytest.raises(Exception):
        plan.section_id = "tampered"  # type: ignore[misc]
