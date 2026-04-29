"""M-D6 phase 1 v1 — cross-domain routing substrate tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.polaris_graph.audit_ir.domain_router import (
    DomainAdapter,
    DomainRouterError,
    DomainTemplate,
    DomainTemplateRegistry,
    RoutingOutcome,
    RoutingResult,
    route_to_domain,
)
from src.polaris_graph.audit_ir.scope_classifier import (
    ScopeClassification,
    ScopeVerdict,
)


# ---------------------------------------------------------------------------
# Stub adapter
# ---------------------------------------------------------------------------


@dataclass
class _StubAdapter:
    adapter_id: str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _classification(
    *,
    verdict: ScopeVerdict,
    domain: str | None = None,
    rationale: str = "test",
) -> ScopeClassification:
    return ScopeClassification(
        verdict=verdict,
        confidence=0.9,
        domain=domain,
        rationale=rationale,
    )


@pytest.fixture()
def registry() -> DomainTemplateRegistry:
    return DomainTemplateRegistry((
        DomainTemplate(
            domain_id="clinical",
            display_name="Clinical research",
            scope_template_path="config/scope_templates/clinical.yaml",
            expected_adapter_ids=("crossref", "pubmed"),
        ),
        DomainTemplate(
            domain_id="cybersec",
            display_name="Cybersecurity",
            scope_template_path="config/scope_templates/cybersec.yaml",
            expected_adapter_ids=("nist_cve", "mitre_attack"),
        ),
    ))


@pytest.fixture()
def adapters() -> dict[str, DomainAdapter]:
    return {
        "crossref": _StubAdapter("crossref"),
        "pubmed": _StubAdapter("pubmed"),
        "nist_cve": _StubAdapter("nist_cve"),
        "mitre_attack": _StubAdapter("mitre_attack"),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_indexes_by_domain_id(
    registry: DomainTemplateRegistry,
) -> None:
    assert registry.has("clinical")
    assert registry.has("cybersec")
    assert not registry.has("unknown")
    assert registry.domain_ids == ("clinical", "cybersec")


def test_registry_get_returns_template(
    registry: DomainTemplateRegistry,
) -> None:
    tpl = registry.get("clinical")
    assert tpl.domain_id == "clinical"
    assert tpl.expected_adapter_ids == ("crossref", "pubmed")


def test_registry_get_unknown_raises(
    registry: DomainTemplateRegistry,
) -> None:
    with pytest.raises(DomainRouterError, match="unknown domain_id"):
        registry.get("nope")


def test_registry_get_non_string_raises(
    registry: DomainTemplateRegistry,
) -> None:
    with pytest.raises(DomainRouterError, match="must be str"):
        registry.get(123)  # type: ignore[arg-type]


def test_registry_rejects_non_tuple_input() -> None:
    with pytest.raises(DomainRouterError, match="must be a tuple"):
        DomainTemplateRegistry([  # type: ignore[arg-type]
            DomainTemplate("a", "A", "p", ()),
        ])


def test_registry_rejects_non_template_element() -> None:
    with pytest.raises(DomainRouterError, match="must be DomainTemplate"):
        DomainTemplateRegistry((
            DomainTemplate("a", "A", "p", ()),
            "not a template",  # type: ignore[arg-type]
        ))


def test_registry_rejects_empty_domain_id() -> None:
    with pytest.raises(DomainRouterError, match="domain_id must be non-empty"):
        DomainTemplateRegistry((
            DomainTemplate("", "A", "p", ()),
        ))


def test_registry_rejects_duplicate_domain_id() -> None:
    with pytest.raises(DomainRouterError, match="duplicate"):
        DomainTemplateRegistry((
            DomainTemplate("clinical", "A", "p1", ()),
            DomainTemplate("clinical", "B", "p2", ()),
        ))


# ---------------------------------------------------------------------------
# Routing — verdict-based dispatch
# ---------------------------------------------------------------------------


def test_route_out_of_scope_rejects(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.OUT_OF_SCOPE,
        rationale="cooking recipe",
    )
    result = route_to_domain(cls, registry, adapters)
    assert result.outcome == RoutingOutcome.REJECTED_OUT_OF_SCOPE
    assert result.template is None
    assert result.adapters == ()
    assert "cooking" in result.rationale


def test_route_uncertain_rejects(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.UNCERTAIN,
        rationale="ambiguous",
    )
    result = route_to_domain(cls, registry, adapters)
    assert result.outcome == RoutingOutcome.REJECTED_UNCERTAIN
    assert result.template is None
    assert result.adapters == ()


def test_route_in_scope_with_known_domain(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE,
        domain="clinical",
    )
    result = route_to_domain(cls, registry, adapters)
    assert result.outcome == RoutingOutcome.ROUTED
    assert result.template is not None
    assert result.template.domain_id == "clinical"
    assert tuple(a.adapter_id for a in result.adapters) == ("crossref", "pubmed")


def test_route_in_scope_unknown_domain(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE,
        domain="materials",
    )
    result = route_to_domain(cls, registry, adapters)
    assert result.outcome == RoutingOutcome.UNKNOWN_DOMAIN
    assert "materials" in result.rationale


def test_route_in_scope_missing_domain_tag(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    """Defensive: an IN_SCOPE classification with domain=None
    (non-LLM classifier) is treated as UNKNOWN_DOMAIN, not
    silently routed."""
    cls = _classification(verdict=ScopeVerdict.IN_SCOPE, domain=None)
    result = route_to_domain(cls, registry, adapters)
    assert result.outcome == RoutingOutcome.UNKNOWN_DOMAIN


def test_route_in_scope_missing_adapters(
    registry: DomainTemplateRegistry,
) -> None:
    """Adapter pool missing one of the expected adapters."""
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE,
        domain="cybersec",
    )
    partial_adapters: dict[str, DomainAdapter] = {
        "nist_cve": _StubAdapter("nist_cve"),
        # mitre_attack missing
    }
    result = route_to_domain(cls, registry, partial_adapters)
    assert result.outcome == RoutingOutcome.MISSING_ADAPTERS
    assert "mitre_attack" in result.rationale


def test_route_resolves_adapters_in_template_order(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE,
        domain="cybersec",
    )
    result = route_to_domain(cls, registry, adapters)
    assert tuple(a.adapter_id for a in result.adapters) == (
        "nist_cve", "mitre_attack",
    )


# ---------------------------------------------------------------------------
# Adapter validation
# ---------------------------------------------------------------------------


def test_route_raises_when_adapter_missing_adapter_id_attr(
    registry: DomainTemplateRegistry,
) -> None:
    @dataclass
    class _BadAdapter:
        # No adapter_id attribute
        pass

    bad_adapters = {
        "crossref": _BadAdapter(),
        "pubmed": _StubAdapter("pubmed"),
    }
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE, domain="clinical",
    )
    with pytest.raises(DomainRouterError, match="DomainAdapter Protocol"):
        route_to_domain(cls, registry, bad_adapters)  # type: ignore[arg-type]


def test_route_raises_on_adapter_id_mismatch(
    registry: DomainTemplateRegistry,
) -> None:
    """Caller dict key 'crossref' but adapter.adapter_id = 'wrong'.
    Catches caller-side construction bugs."""
    mismatched = {
        "crossref": _StubAdapter("wrong_id"),
        "pubmed": _StubAdapter("pubmed"),
    }
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE, domain="clinical",
    )
    with pytest.raises(DomainRouterError, match="does not match"):
        route_to_domain(cls, registry, mismatched)


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------


def test_route_classification_must_be_scopeclassification(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    with pytest.raises(DomainRouterError, match="classification"):
        route_to_domain("not a classification", registry, adapters)  # type: ignore[arg-type]


def test_route_registry_must_be_registry(
    adapters: dict[str, DomainAdapter],
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE, domain="clinical",
    )
    with pytest.raises(DomainRouterError, match="registry"):
        route_to_domain(cls, "not a registry", adapters)  # type: ignore[arg-type]


def test_route_adapters_must_be_mapping(
    registry: DomainTemplateRegistry,
) -> None:
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE, domain="clinical",
    )
    with pytest.raises(DomainRouterError, match="Mapping"):
        route_to_domain(cls, registry, ["not a mapping"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Empty adapter list (template with no expected adapters)
# ---------------------------------------------------------------------------


def test_registry_rejects_non_string_domain_id() -> None:
    """Codex round-1 MEDIUM fix (v2): domain_id must be str.
    v1 only checked truthiness — DomainTemplate(domain_id=123)
    was accepted but get()/has() only handle str."""
    with pytest.raises(DomainRouterError, match="domain_id must be str"):
        DomainTemplateRegistry((
            DomainTemplate(123, "X", "p", ()),  # type: ignore[arg-type]
        ))


def test_route_rejects_malformed_verdict_value(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    """Codex round-1 HIGH fix (v2): verdict MUST be a
    ScopeVerdict enum. v1 fell through to IN_SCOPE path on any
    non-OUT_OF_SCOPE / non-UNCERTAIN value, so a malformed
    `ScopeClassification(verdict="bogus", ...)` could route
    incorrectly."""
    @dataclass(frozen=True)
    class _BogusClassification:
        verdict: str
        confidence: float
        domain: str | None
        rationale: str

    # Bypass dataclass type checks via a separate dataclass
    # mimic — ScopeClassification's frozen dataclass would
    # accept this too if Python doesn't enforce types at
    # runtime.
    cls = _BogusClassification(
        verdict="bogus", confidence=0.9,
        domain="clinical", rationale="",
    )
    with pytest.raises(DomainRouterError, match="classification must be"):
        route_to_domain(cls, registry, adapters)  # type: ignore[arg-type]

    # Also test a real ScopeClassification with a non-enum
    # verdict (achievable via direct construction since
    # ScopeClassification dataclass doesn't enforce enum at
    # runtime).
    bogus_real = ScopeClassification(
        verdict="bogus",  # type: ignore[arg-type]
        confidence=0.9,
        domain="clinical",
        rationale="",
    )
    with pytest.raises(DomainRouterError, match="verdict must be ScopeVerdict"):
        route_to_domain(bogus_real, registry, adapters)


def test_registry_rejects_non_tuple_expected_adapter_ids() -> None:
    """Codex round-2 MEDIUM fix (v3): expected_adapter_ids
    must be a tuple. v2 trusted annotations; a list would
    construct fine then degrade into MISSING_ADAPTERS at
    route time."""
    with pytest.raises(DomainRouterError, match="expected_adapter_ids must be tuple"):
        DomainTemplateRegistry((
            DomainTemplate(
                "x", "X", "p",
                ["crossref", "pubmed"],  # type: ignore[arg-type]
            ),
        ))


def test_registry_rejects_non_string_adapter_id() -> None:
    """Codex round-2 MEDIUM fix (v3): each adapter_id in
    expected_adapter_ids must be str."""
    with pytest.raises(DomainRouterError, match="must be str"):
        DomainTemplateRegistry((
            DomainTemplate(
                "x", "X", "p",
                (123,),  # type: ignore[arg-type]
            ),
        ))


def test_registry_rejects_empty_adapter_id() -> None:
    """Empty-string adapter_id rejected at construction."""
    with pytest.raises(DomainRouterError, match="must be non-empty"):
        DomainTemplateRegistry((
            DomainTemplate("x", "X", "p", ("",)),
        ))


def test_route_rejects_non_string_domain(
    registry: DomainTemplateRegistry,
    adapters: dict[str, DomainAdapter],
) -> None:
    """Codex round-2 MEDIUM fix (v3): IN_SCOPE classification
    with non-str domain raises DomainRouterError. v2 returned
    UNKNOWN_DOMAIN, masking schema drift as a routing miss."""
    cls = ScopeClassification(
        verdict=ScopeVerdict.IN_SCOPE,
        confidence=0.9,
        domain=123,  # type: ignore[arg-type]
        rationale="",
    )
    with pytest.raises(DomainRouterError, match="domain must be str"):
        route_to_domain(cls, registry, adapters)


def test_route_template_with_no_expected_adapters() -> None:
    """A template with empty expected_adapter_ids routes
    successfully even with empty adapter pool."""
    registry = DomainTemplateRegistry((
        DomainTemplate(
            domain_id="meta",
            display_name="Meta",
            scope_template_path="config/scope_templates/meta.yaml",
            expected_adapter_ids=(),
        ),
    ))
    cls = _classification(
        verdict=ScopeVerdict.IN_SCOPE, domain="meta",
    )
    result = route_to_domain(cls, registry, {})
    assert result.outcome == RoutingOutcome.ROUTED
    assert result.adapters == ()
