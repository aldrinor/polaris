"""Sovereignty router: enforces EXTERNAL_LEAK_FORBIDDEN policy at call sites (I-f3-003).

Per Carney v6.2 §332. The router is a policy library — callers invoke
`assert_safe_for_external` (strict gate) or `filter_for_external_egress`
(split mode) before any outbound payload leaves Canadian-sovereign infra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from polaris_graph.sovereignty.classification import (
    is_external_leak_forbidden,
    parse_classification,
)


@dataclass(frozen=True)
class SovereigntyDecision:
    """Result of `filter_for_external_egress(strict=False)`.

    Note: while the dataclass is frozen, the contained `tuple` fields
    are themselves immutable.
    """

    allowed: tuple
    blocked: tuple
    reasons: tuple[str, ...]


class SovereigntyViolationError(RuntimeError):
    """Raised in strict mode when any item is forbidden external-egress."""


def _classification_of(item: Any) -> str | None:
    raw = getattr(item, "classification", None)
    if raw is None and isinstance(item, dict):
        raw = item.get("classification")
    return raw


def filter_for_external_egress(
    items: Iterable, *, strict: bool = True,
) -> SovereigntyDecision:
    """Filter items against EXTERNAL_LEAK_FORBIDDEN per Carney v6.2 §332.

    strict=True (default): raises SovereigntyViolationError on first forbidden item.
    strict=False: returns SovereigntyDecision split.

    Items lacking `classification` default to UNKNOWN (forbidden).
    """
    allowed: list = []
    blocked: list = []
    reasons: list[str] = []
    for item in items:
        cls = parse_classification(_classification_of(item))
        if is_external_leak_forbidden(cls):
            reason = f"classification={cls.value} forbidden external-egress"
            if strict:
                raise SovereigntyViolationError(reason)
            blocked.append(item)
            reasons.append(reason)
        else:
            allowed.append(item)
    return SovereigntyDecision(
        allowed=tuple(allowed), blocked=tuple(blocked), reasons=tuple(reasons),
    )


def assert_safe_for_external(items: Iterable) -> None:
    """Strict gate; raises SovereigntyViolationError on any forbidden item."""
    filter_for_external_egress(items, strict=True)
