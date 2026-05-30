"""Validation-domain fail-closed checklist guard (D1, contract carry-forward #7).

Production completeness checking is intentionally PERMISSIVE: a missing checklist
yields `no_checklist_loaded`, not a failure (see
`src/polaris_graph/nodes/completeness_checker.py`). That is correct for arbitrary
production domains.

For the Statistical Safety Contract VALIDATION SCOPE, that permissiveness is
unsafe: a gold set must not be constructed for a validation domain whose
completeness checklist is missing or empty. This guard FAILS CLOSED — it raises
if any of the six locked validation domains (D1a) lacks a present, non-empty
checklist. It is a pre-construction gate for the safety program, NOT a change to
production completeness behaviour.
"""

from __future__ import annotations

from src.polaris_graph.nodes.completeness_checker import load_checklist

# The six locked validation domains (D1a_validation_domain_set.md). This list is
# the single authority for which domains the guard fails closed on.
VALIDATION_DOMAINS = (
    "clinical",
    "due_diligence",
    "policy",
    "tech",
    "ai_sovereignty",
    "canada_us",
)


class ValidationDomainChecklistError(RuntimeError):
    """Raised when a validation domain lacks a present, non-empty checklist."""


def missing_validation_checklists(domains: tuple[str, ...] = VALIDATION_DOMAINS) -> list[str]:
    """Return the validation domains whose checklist is missing or empty.

    A checklist is "present + non-empty" iff `load_checklist(domain)` returns at
    least one topic (the loader returns [] for a missing/empty/unparseable file).
    """
    return [domain for domain in domains if not load_checklist(domain)]


def assert_validation_checklists_present(
    domains: tuple[str, ...] = VALIDATION_DOMAINS,
) -> None:
    """Fail closed: raise if any validation domain lacks a non-empty checklist.

    Called as a pre-construction gate before any gold-set claim is built. Unlike
    production completeness checking, a missing checklist here is a HARD STOP.
    """
    missing = missing_validation_checklists(domains)
    if missing:
        raise ValidationDomainChecklistError(
            "validation domains missing a present, non-empty completeness "
            f"checklist (fail-closed per D1): {missing}. "
            "Author config/completeness_checklists/<domain>.yaml before gold-set "
            "construction."
        )
