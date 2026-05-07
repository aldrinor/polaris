"""Unit tests for I-f3-003 — sovereignty router."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from polaris_graph.sovereignty.classification import DataClassification
from polaris_graph.sovereignty.router import (
    SovereigntyDecision,
    SovereigntyViolationError,
    assert_safe_for_external,
    filter_for_external_egress,
)


@dataclass
class Item:
    text: str
    classification: str


def test_strict_blocks_client_doc():
    items = [Item("ok", "PUBLIC_SYNTHETIC"), Item("leak", "CLIENT")]
    with pytest.raises(SovereigntyViolationError, match="CLIENT"):
        filter_for_external_egress(items, strict=True)


def test_strict_blocks_can_real():
    with pytest.raises(SovereigntyViolationError, match="CAN_REAL"):
        filter_for_external_egress([Item("x", "CAN_REAL")], strict=True)


def test_strict_blocks_private():
    with pytest.raises(SovereigntyViolationError, match="PRIVATE"):
        filter_for_external_egress([Item("x", "PRIVATE")], strict=True)


def test_strict_blocks_unknown_default_deny():
    # UNKNOWN-classified item:
    with pytest.raises(SovereigntyViolationError, match="UNKNOWN"):
        filter_for_external_egress([Item("x", "UNKNOWN")], strict=True)
    # missing classification entirely:
    with pytest.raises(SovereigntyViolationError, match="UNKNOWN"):
        filter_for_external_egress([{"text": "no_class"}], strict=True)


def test_strict_allows_only_public_synthetic():
    items = [Item(f"ps{i}", "PUBLIC_SYNTHETIC") for i in range(3)]
    decision = filter_for_external_egress(items, strict=True)
    assert isinstance(decision, SovereigntyDecision)
    assert len(decision.allowed) == 3
    assert decision.blocked == ()


def test_lax_returns_split():
    items = [Item("ok", "PUBLIC_SYNTHETIC"), Item("leak", "CLIENT"), Item("ok2", "PUBLIC_SYNTHETIC")]
    decision = filter_for_external_egress(items, strict=False)
    assert len(decision.allowed) == 2
    assert len(decision.blocked) == 1
    assert decision.blocked[0].text == "leak"
    assert decision.reasons[0].endswith("forbidden external-egress")


def test_dict_items_classification_field():
    items = [{"text": "ok", "classification": "PUBLIC_SYNTHETIC"}]
    decision = filter_for_external_egress(items, strict=True)
    assert len(decision.allowed) == 1


def test_assert_safe_for_external_passthrough():
    assert_safe_for_external([Item("ok", "PUBLIC_SYNTHETIC")])  # no raise
    with pytest.raises(SovereigntyViolationError):
        assert_safe_for_external([Item("leak", "CLIENT")])


def test_enum_classification_value_works():
    """Items can carry DataClassification enum directly, not just strings."""
    items = [Item("ok", DataClassification.PUBLIC_SYNTHETIC)]
    decision = filter_for_external_egress(items, strict=True)
    assert len(decision.allowed) == 1
