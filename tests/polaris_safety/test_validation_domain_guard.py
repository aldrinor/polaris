"""Tests for the validation-domain fail-closed checklist guard (D1)."""

from __future__ import annotations

import pytest

from src.polaris_safety.validation_domain_guard import (
    VALIDATION_DOMAINS,
    ValidationDomainChecklistError,
    assert_validation_checklists_present,
    missing_validation_checklists,
)


def test_all_six_validation_domains_have_checklists():
    # After D1 authored ai_sovereignty.yaml + canada_us.yaml, none should be missing.
    assert missing_validation_checklists() == []


def test_assert_passes_with_all_present():
    assert_validation_checklists_present()  # must not raise


def test_validation_domains_are_the_locked_six():
    assert set(VALIDATION_DOMAINS) == {
        "clinical",
        "due_diligence",
        "policy",
        "tech",
        "ai_sovereignty",
        "canada_us",
    }
    # workforce + custom are explicitly NOT validation domains (D1a §3 exclusions)
    assert "workforce" not in VALIDATION_DOMAINS
    assert "custom" not in VALIDATION_DOMAINS


def test_fail_closed_raises_on_missing_domain():
    # A bogus domain has no checklist file -> guard must fail closed.
    with pytest.raises(ValidationDomainChecklistError):
        assert_validation_checklists_present(domains=("clinical", "definitely_no_such_domain"))


def test_missing_list_names_the_offender():
    missing = missing_validation_checklists(domains=("clinical", "definitely_no_such_domain"))
    assert missing == ["definitely_no_such_domain"]


def test_each_validation_domain_loads_topics():
    # Every validation domain checklist must parse to >=1 topic individually.
    from src.polaris_graph.nodes.completeness_checker import load_checklist

    for domain in VALIDATION_DOMAINS:
        topics = load_checklist(domain)
        assert topics, f"{domain} checklist loaded zero topics"
