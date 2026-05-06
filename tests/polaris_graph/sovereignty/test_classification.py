"""Unit tests for I-f3-002 — DataClassification + sovereignty policy."""

from __future__ import annotations

import json

import pytest

from polaris_graph.sovereignty.classification import (
    ALL_CLASSIFICATIONS,
    EXTERNAL_LEAK_FORBIDDEN,
    DataClassification,
    is_external_leak_forbidden,
    parse_classification,
)


def test_all_five_values_present():
    expected = {"PUBLIC_SYNTHETIC", "CAN_REAL", "PRIVATE", "CLIENT", "UNKNOWN"}
    assert {c.value for c in ALL_CLASSIFICATIONS} == expected
    assert len(ALL_CLASSIFICATIONS) == 5


def test_str_inheritance_makes_json_serializable():
    payload = {"c": DataClassification.CLIENT}
    assert json.dumps(payload) == '{"c": "CLIENT"}'


def test_parse_classification_accepts_enum():
    assert parse_classification(DataClassification.CAN_REAL) is DataClassification.CAN_REAL


def test_parse_classification_accepts_string():
    assert parse_classification("CAN_REAL") is DataClassification.CAN_REAL


def test_parse_classification_none_returns_unknown():
    assert parse_classification(None) is DataClassification.UNKNOWN


def test_parse_classification_invalid_raises():
    with pytest.raises(ValueError):
        parse_classification("NOT_A_REAL_CLASSIFICATION")


def test_is_external_leak_forbidden():
    """Per Carney v6.2 §332: only PUBLIC_SYNTHETIC is allowed external."""
    assert is_external_leak_forbidden(DataClassification.PUBLIC_SYNTHETIC) is False
    for c in (
        DataClassification.CAN_REAL,
        DataClassification.PRIVATE,
        DataClassification.CLIENT,
        DataClassification.UNKNOWN,
    ):
        assert is_external_leak_forbidden(c) is True
    assert EXTERNAL_LEAK_FORBIDDEN == frozenset(
        {
            DataClassification.CAN_REAL,
            DataClassification.PRIVATE,
            DataClassification.CLIENT,
            DataClassification.UNKNOWN,
        }
    )
