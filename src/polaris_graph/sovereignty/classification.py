"""Canonical data classification taxonomy + sovereignty policy (I-f3-002).

Codifies `docs/carney_delivery_plan_v6_2.md:332` "All non-PUBLIC_SYNTHETIC
classifications blocked from external API". The `EXTERNAL_LEAK_FORBIDDEN`
set is the authoritative external-egress policy consumed by the
sovereignty router (I-f3-003).
"""

from __future__ import annotations

from enum import Enum
from typing import Union


class DataClassification(str, Enum):
    PUBLIC_SYNTHETIC = "PUBLIC_SYNTHETIC"
    CAN_REAL = "CAN_REAL"
    PRIVATE = "PRIVATE"
    CLIENT = "CLIENT"
    UNKNOWN = "UNKNOWN"


ALL_CLASSIFICATIONS: tuple[DataClassification, ...] = tuple(DataClassification)

EXTERNAL_LEAK_FORBIDDEN: frozenset[DataClassification] = frozenset(
    {
        DataClassification.CAN_REAL,
        DataClassification.PRIVATE,
        DataClassification.CLIENT,
        DataClassification.UNKNOWN,
    }
)


def parse_classification(
    value: Union[str, DataClassification, None],
) -> DataClassification:
    """Normalize input to DataClassification. None → UNKNOWN. Invalid → ValueError."""
    if value is None:
        return DataClassification.UNKNOWN
    if isinstance(value, DataClassification):
        return value
    return DataClassification(value)


def is_external_leak_forbidden(classification: DataClassification) -> bool:
    """True iff the given classification is forbidden from external-API egress."""
    return classification in EXTERNAL_LEAK_FORBIDDEN
