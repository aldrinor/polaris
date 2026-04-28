"""M-D1 validation-set loader.

The validation set is a YAML/JSON document in
`config/auto_induction/validation_set.yaml` containing three
groups of cases:

  in_scope:
    - case_id: cli-01
      query: "..."
      curator_contract_slug: clinical_tirzepatide_t2dm
      domain: clinical
    ...

  ambiguous:
    - case_id: amb-01
      query: "..."
      expected_action: abstain  # the inductor SHOULD abstain
      reason: "intent unclear between supported clinical and policy"
    ...

  out_of_scope:
    - case_id: oos-01
      query: "..."
      expected_action: abstain  # not in supported template space
      reason: "industrial materials — no current Phase D adapter"
    ...

The harness loads this, validates schema, and exposes ValidationCase
objects for `run_benchmark()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


CaseGroup = Literal["in_scope", "ambiguous", "out_of_scope"]


@dataclass(frozen=True)
class ValidationCase:
    """One row in the M-D1 validation set."""

    case_id: str
    group: CaseGroup
    query: str
    # Only set for in_scope cases — points at a curator-reviewed
    # contract slug (loadable via M-54 ReportContract loader).
    curator_contract_slug: str | None = None
    domain: str | None = None
    # Only set for ambiguous / out_of_scope cases.
    expected_action: Literal["accept", "abstain"] = "accept"
    reason: str | None = None


@dataclass(frozen=True)
class ValidationSet:
    """Complete validation set."""

    in_scope: tuple[ValidationCase, ...] = field(default_factory=tuple)
    ambiguous: tuple[ValidationCase, ...] = field(default_factory=tuple)
    out_of_scope: tuple[ValidationCase, ...] = field(default_factory=tuple)

    @property
    def all_cases(self) -> tuple[ValidationCase, ...]:
        return self.in_scope + self.ambiguous + self.out_of_scope

    @property
    def total(self) -> int:
        return len(self.all_cases)


class ValidationSetError(ValueError):
    """Raised when the validation-set YAML is malformed."""


def _coerce_case(
    raw: dict[str, Any], *, group: CaseGroup,
) -> ValidationCase:
    if not isinstance(raw, dict):
        raise ValidationSetError(
            f"validation case in group {group!r} is not a dict: {raw!r}"
        )
    case_id = raw.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValidationSetError(
            f"validation case in group {group!r} missing or empty "
            f"case_id: {raw!r}"
        )
    query = raw.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValidationSetError(
            f"validation case {case_id!r} missing or empty query"
        )
    if group == "in_scope":
        slug = raw.get("curator_contract_slug")
        if not isinstance(slug, str) or not slug.strip():
            raise ValidationSetError(
                f"in_scope case {case_id!r} requires "
                f"curator_contract_slug"
            )
        return ValidationCase(
            case_id=case_id.strip(),
            group=group,
            query=query.strip(),
            curator_contract_slug=slug.strip(),
            domain=raw.get("domain"),
            expected_action="accept",
        )
    # ambiguous / out_of_scope: MUST declare expected_action='abstain'
    # Codex round-1 (M-D1 harness review): allowing 'accept' for
    # negative-set groups weakens the round-2 negative-set contract
    # — by definition an ambiguous or out-of-scope case is one the
    # inductor must abstain on.
    expected = raw.get("expected_action", "abstain")
    if expected != "abstain":
        raise ValidationSetError(
            f"case {case_id!r} (group {group!r}) must have "
            f"expected_action='abstain'; got {expected!r}. "
            f"Negative-set cases by definition require abstention."
        )
    return ValidationCase(
        case_id=case_id.strip(),
        group=group,
        query=query.strip(),
        expected_action=expected,
        reason=raw.get("reason"),
    )


def load_validation_set(path: Path | str) -> ValidationSet:
    """Load + validate an M-D1 validation set.

    Raises ValidationSetError on schema violations.
    Returns ValidationSet on success.
    """
    p = Path(path)
    if not p.exists():
        raise ValidationSetError(
            f"validation set not found: {p}"
        )
    with p.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    if not isinstance(data, dict):
        raise ValidationSetError(
            f"validation set root must be a mapping; got {type(data).__name__}"
        )

    def _load_group(key: CaseGroup) -> tuple[ValidationCase, ...]:
        items = data.get(key, [])
        if items is None:
            return ()
        if not isinstance(items, list):
            raise ValidationSetError(
                f"validation set group {key!r} must be a list; "
                f"got {type(items).__name__}"
            )
        return tuple(_coerce_case(it, group=key) for it in items)

    s = ValidationSet(
        in_scope=_load_group("in_scope"),
        ambiguous=_load_group("ambiguous"),
        out_of_scope=_load_group("out_of_scope"),
    )

    # Sanity: case_ids must be globally unique.
    seen: set[str] = set()
    for c in s.all_cases:
        if c.case_id in seen:
            raise ValidationSetError(
                f"duplicate case_id: {c.case_id!r}"
            )
        seen.add(c.case_id)

    return s
