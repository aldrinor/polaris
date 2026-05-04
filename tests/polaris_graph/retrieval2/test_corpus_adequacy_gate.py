"""Tests for corpus_adequacy_gate — min-sources-per-tier check."""

from __future__ import annotations

import pytest

from polaris_graph.retrieval2.corpus_adequacy_gate import (
    CLINICAL_DEFAULT,
    CLINICAL_DIAGNOSIS,
    CLINICAL_EFFICACY,
    CLINICAL_PROGNOSIS,
    CLINICAL_SAFETY,
    ClinicalTemplate,
    assess,
    get_template,
    register_template,
    template_for_scope_class,
)
from polaris_graph.retrieval2.evidence_pool import (
    Source,
    SourceTier,
)


def _src(tier: SourceTier, host: str = "nejm.org") -> Source:
    return Source(
        url=f"https://{host}/doi/abc",
        domain=host,
        tier=tier,
        title="example",
        snippet="example",
    )


def _mk(t1: int = 0, t2: int = 0, t3: int = 0) -> list[Source]:
    return (
        [_src(SourceTier.T1, "fda.gov") for _ in range(t1)]
        + [_src(SourceTier.T2, "nejm.org") for _ in range(t2)]
        + [_src(SourceTier.T3, "clinicaltrials.gov") for _ in range(t3)]
    )


# ---------- clinical_default thresholds ----------

def test_default_pass_at_threshold():
    sources = _mk(t1=2, t2=4, t3=2)
    v = assess(sources, CLINICAL_DEFAULT)
    assert v.is_adequate
    assert v.failure_reason is None


def test_default_pass_above_threshold():
    sources = _mk(t1=5, t2=10, t3=4)
    v = assess(sources, CLINICAL_DEFAULT)
    assert v.is_adequate


def test_default_fail_t1_short():
    sources = _mk(t1=1, t2=4, t3=2)
    v = assess(sources, CLINICAL_DEFAULT)
    assert not v.is_adequate
    assert "T1" in v.failure_reason
    assert "got 1, need 2" in v.failure_reason


def test_default_fail_t2_short():
    sources = _mk(t1=2, t2=2, t3=2)
    v = assess(sources, CLINICAL_DEFAULT)
    assert not v.is_adequate
    assert "T2" in v.failure_reason


def test_default_fail_t3_short():
    sources = _mk(t1=2, t2=4, t3=1)
    v = assess(sources, CLINICAL_DEFAULT)
    assert not v.is_adequate
    assert "T3" in v.failure_reason


def test_default_fail_lists_all_deficient_tiers():
    """When multiple tiers are short, all must appear in failure_reason."""
    sources = _mk(t1=0, t2=0, t3=0)
    v = assess(sources, CLINICAL_DEFAULT)
    assert not v.is_adequate
    for label in ("T1", "T2", "T3"):
        assert label in v.failure_reason


def test_empty_pool_fails():
    v = assess([], CLINICAL_DEFAULT)
    assert not v.is_adequate
    assert v.sources_per_tier == {SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0}


# ---------- counts populated ----------

def test_verdict_counts_populated():
    sources = _mk(t1=3, t2=5, t3=4)
    v = assess(sources, CLINICAL_DEFAULT)
    assert v.sources_per_tier[SourceTier.T1] == 3
    assert v.sources_per_tier[SourceTier.T2] == 5
    assert v.sources_per_tier[SourceTier.T3] == 4


def test_verdict_min_required_populated():
    v = assess(_mk(t1=2, t2=4, t3=2), CLINICAL_DEFAULT)
    assert v.min_required_per_tier == {
        SourceTier.T1: 2,
        SourceTier.T2: 4,
        SourceTier.T3: 2,
    }


# ---------- per-template thresholds ----------

def test_safety_template_requires_3_t1():
    """Safety template needs T1>=3 (regulatory weight). 2 should fail."""
    v = assess(_mk(t1=2, t2=3, t3=1), CLINICAL_SAFETY)
    assert not v.is_adequate
    assert "T1" in v.failure_reason


def test_safety_template_passes_at_3_t1():
    v = assess(_mk(t1=3, t2=3, t3=1), CLINICAL_SAFETY)
    assert v.is_adequate


def test_diagnosis_template_relaxed_t1():
    """Diagnosis only needs 1 T1 source."""
    v = assess(_mk(t1=1, t2=5, t3=1), CLINICAL_DIAGNOSIS)
    assert v.is_adequate


def test_efficacy_template_thresholds():
    """Demo-stage thresholds: T1>=1, T2>=3, T3>=1."""
    v = assess(_mk(t1=1, t2=3, t3=1), CLINICAL_EFFICACY)
    assert v.is_adequate

    v_short = assess(_mk(t1=1, t2=2, t3=1), CLINICAL_EFFICACY)
    assert not v_short.is_adequate
    assert "T2" in v_short.failure_reason


def test_prognosis_template_thresholds():
    v = assess(_mk(t1=1, t2=4, t3=2), CLINICAL_PROGNOSIS)
    assert v.is_adequate


# ---------- template registry ----------

def test_get_template_known():
    assert get_template("clinical_default").template_id == "clinical_default"
    assert get_template("clinical_safety").template_id == "clinical_safety"


def test_get_template_unknown_falls_back():
    assert get_template("nonexistent_template").template_id == "clinical_default"


def test_register_custom_template():
    custom = ClinicalTemplate(
        template_id="strict_test_only",
        min_t1=10,
        min_t2=10,
        min_t3=10,
    )
    register_template(custom)
    assert get_template("strict_test_only").min_t1 == 10
    # And it actually applies to assessment
    v = assess(_mk(t1=5, t2=5, t3=5), custom)
    assert not v.is_adequate


def test_template_for_scope_class_routes():
    assert template_for_scope_class("clinical_efficacy").template_id == "clinical_efficacy"
    assert template_for_scope_class("clinical_safety").template_id == "clinical_safety"
    assert template_for_scope_class("clinical_diagnosis").template_id == "clinical_diagnosis"
    assert template_for_scope_class("clinical_prognosis").template_id == "clinical_prognosis"


def test_template_for_scope_class_none_falls_back():
    assert template_for_scope_class(None).template_id == "clinical_default"


def test_template_for_scope_class_unknown_falls_back():
    assert template_for_scope_class("out_of_scope").template_id == "clinical_default"


# ---------- failure_reason structure ----------

def test_failure_reason_has_template_id_marker():
    v = assess(_mk(t1=0), CLINICAL_DEFAULT)
    assert "[clinical_default]" in v.failure_reason


def test_failure_reason_machine_parseable_marker():
    """failure_reason starts with corpus_adequacy_failed[<template_id>]:
    so downstream UI/log code can match without full-string parsing."""
    v = assess(_mk(t1=0), CLINICAL_SAFETY)
    assert v.failure_reason.startswith("corpus_adequacy_failed[clinical_safety]:")


# ---------- ClinicalTemplate dataclass ----------

def test_clinical_template_as_dict():
    t = ClinicalTemplate(template_id="x", min_t1=1, min_t2=2, min_t3=3)
    d = t.as_dict()
    assert d == {SourceTier.T1: 1, SourceTier.T2: 2, SourceTier.T3: 3}


def test_clinical_template_frozen():
    """Templates should be immutable so accidentally mutating one
    in-place doesn't poison the registry."""
    t = ClinicalTemplate(template_id="x", min_t1=1, min_t2=2, min_t3=3)
    with pytest.raises(Exception):  # FrozenInstanceError
        t.min_t1 = 99  # type: ignore[misc]
