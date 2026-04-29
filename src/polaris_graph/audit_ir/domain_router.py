"""M-D6 phase 1 v1 (Phase D): Cross-domain template routing substrate.

M-D5 phase 2 (`scope_classifier_llm.py`) produces a
`ScopeClassification` with a `domain` tag. M-D6 phase 1 ships
the **cross-domain routing substrate**: given a domain tag,
look up the matching `DomainTemplate` and route to the
right `DomainAdapter` (HTTP client / retrieval backend).

Phase 1 v1 ships substrate ONLY:
  - `DomainTemplate` dataclass — ID + display name + tier
    expectations + scope-template path
  - `DomainTemplateRegistry` — workspace-scoped lookup
  - `DomainAdapter` Protocol — pluggable retrieval seam
  - `route_to_domain(classification, registry, adapters)` —
    pure orchestrator

Phase 2 (deferred) ships concrete `DomainAdapter` impls:
  - NIST / MITRE for cybersec
  - FAERS / EudraVigilance for pharmacovigilance
  - ASTM / NIST for materials

This separation keeps the routing logic testable without API
costs and lets adapter impls land independently as their HTTP
contracts firm up.

## Substrate boundary

Imports `scope_classifier` (phase 1 contracts) +
`scope_classifier_llm` (phase 2 verdict shape) + stdlib only.
No HTTP, no DB, no LLM clients.

See `docs/md6_phase1_threat_model.md` for boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol

from src.polaris_graph.audit_ir.scope_classifier import (
    ScopeClassification,
    ScopeClassifierError,
    ScopeVerdict,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DomainRouterError(ScopeClassifierError):
    """Raised on contract violations — unknown domain, missing
    adapter, malformed registry."""


# ---------------------------------------------------------------------------
# Domain template + registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainTemplate:
    """One domain's routing manifest.

    `domain_id`: stable string ID (e.g. "clinical", "policy").
    Matches the `domain` field on a `ScopeClassification`.

    `display_name`: human-readable label for UI / dashboards.

    `scope_template_path`: relative path to the YAML scope
    template (e.g. `config/scope_templates/clinical.yaml`).
    Substrate doesn't load the YAML — that's caller territory.

    `expected_adapter_ids`: tuple of `DomainAdapter` IDs that
    this domain requires for retrieval. Routing fails if any
    expected adapter is missing from the supplied adapters
    dict at `route_to_domain` time.
    """

    domain_id: str
    display_name: str
    scope_template_path: str
    expected_adapter_ids: tuple[str, ...] = field(default_factory=tuple)


class DomainTemplateRegistry:
    """Workspace-scoped registry of domain templates.

    Substrate-only — no DB persistence. Caller constructs with
    a tuple of templates; routing reads from this registry.

    Workspace scoping is achieved by callers maintaining one
    registry per workspace; the substrate doesn't enforce
    workspace_id directly (consistent with how M-D5 phase 1
    composes with phase 1 store via per-call workspace_id).
    """

    def __init__(self, templates: tuple[DomainTemplate, ...]) -> None:
        if not isinstance(templates, tuple):
            raise DomainRouterError(
                f"templates must be a tuple of DomainTemplate, got "
                f"{type(templates).__name__}"
            )
        ids: dict[str, DomainTemplate] = {}
        for i, tpl in enumerate(templates):
            if not isinstance(tpl, DomainTemplate):
                raise DomainRouterError(
                    f"templates[{i}] must be DomainTemplate, got "
                    f"{type(tpl).__name__}"
                )
            if not tpl.domain_id:
                raise DomainRouterError(
                    f"templates[{i}].domain_id must be non-empty"
                )
            if tpl.domain_id in ids:
                raise DomainRouterError(
                    f"duplicate domain_id {tpl.domain_id!r} in templates"
                )
            ids[tpl.domain_id] = tpl
        self._by_id = ids

    @property
    def domain_ids(self) -> tuple[str, ...]:
        """Stable-sorted tuple of registered domain IDs."""
        return tuple(sorted(self._by_id.keys()))

    def get(self, domain_id: str) -> DomainTemplate:
        """Lookup by domain_id. Raises if missing."""
        if not isinstance(domain_id, str):
            raise DomainRouterError(
                f"domain_id must be str, got {type(domain_id).__name__}"
            )
        try:
            return self._by_id[domain_id]
        except KeyError:
            raise DomainRouterError(
                f"unknown domain_id {domain_id!r}; "
                f"registered: {self.domain_ids}"
            )

    def has(self, domain_id: str) -> bool:
        return isinstance(domain_id, str) and domain_id in self._by_id


# ---------------------------------------------------------------------------
# Adapter Protocol
# ---------------------------------------------------------------------------


class DomainAdapter(Protocol):
    """Pluggable retrieval seam for one adapter source.

    Each adapter has a stable `adapter_id` (e.g.
    "nist_cve", "faers", "crossref"). The
    `expected_adapter_ids` tuple on a `DomainTemplate` lists
    which adapters that domain needs; routing matches them up.

    Substrate doesn't dictate the adapter's retrieval shape —
    callers who need different return types per adapter
    (CVEs vs adverse events vs trial records) should narrow
    via runtime isinstance checks or wrap with a typed
    facade. v2 may ship a structured `AdapterFetchResult`
    contract once the concrete adapters firm up.
    """

    @property
    def adapter_id(self) -> str:
        ...


# ---------------------------------------------------------------------------
# Routing result + orchestrator
# ---------------------------------------------------------------------------


class RoutingOutcome(str, Enum):
    """Per-route outcome.

    ROUTED: classifier returned IN_SCOPE with a known domain;
       all expected adapters present.
    REJECTED_OUT_OF_SCOPE: classifier returned OUT_OF_SCOPE.
    REJECTED_UNCERTAIN: classifier returned UNCERTAIN.
    UNKNOWN_DOMAIN: classifier returned IN_SCOPE but the
       domain is not in the registry.
    MISSING_ADAPTERS: domain template lists adapters that
       aren't in the supplied adapter dict.
    """

    ROUTED = "routed"
    REJECTED_OUT_OF_SCOPE = "rejected_out_of_scope"
    REJECTED_UNCERTAIN = "rejected_uncertain"
    UNKNOWN_DOMAIN = "unknown_domain"
    MISSING_ADAPTERS = "missing_adapters"


@dataclass(frozen=True)
class RoutingResult:
    """Pure-derivation orchestrator output.

    `outcome`: closed enum.
    `template`: the matched DomainTemplate (only when
    outcome == ROUTED).
    `adapters`: tuple of resolved adapters in the order listed
    by `template.expected_adapter_ids` (only when ROUTED).
    `rationale`: human-readable explanation for any non-ROUTED
    outcome.
    """

    outcome: RoutingOutcome
    template: DomainTemplate | None
    adapters: tuple[DomainAdapter, ...]
    rationale: str


def route_to_domain(
    classification: ScopeClassification,
    registry: DomainTemplateRegistry,
    adapters: Mapping[str, DomainAdapter],
) -> RoutingResult:
    """Pure orchestrator — given a classifier verdict + a
    registry + an adapter pool, return a RoutingResult.

    Decision tree:
      1. classification.verdict == OUT_OF_SCOPE →
         REJECTED_OUT_OF_SCOPE
      2. classification.verdict == UNCERTAIN →
         REJECTED_UNCERTAIN
      3. classification.verdict == IN_SCOPE:
         a. domain not in registry → UNKNOWN_DOMAIN
         b. expected adapters missing → MISSING_ADAPTERS
         c. otherwise → ROUTED with the matched template +
            resolved adapters in expected order

    No I/O, no LLM, no HTTP. Caller invokes the adapters'
    retrieval methods downstream; this function just resolves
    the routing decision.
    """
    if not isinstance(classification, ScopeClassification):
        raise DomainRouterError(
            f"classification must be ScopeClassification, got "
            f"{type(classification).__name__}"
        )
    if not isinstance(registry, DomainTemplateRegistry):
        raise DomainRouterError(
            f"registry must be DomainTemplateRegistry, got "
            f"{type(registry).__name__}"
        )
    if not isinstance(adapters, Mapping):
        raise DomainRouterError(
            f"adapters must be a Mapping[str, DomainAdapter], got "
            f"{type(adapters).__name__}"
        )

    if classification.verdict == ScopeVerdict.OUT_OF_SCOPE:
        return RoutingResult(
            outcome=RoutingOutcome.REJECTED_OUT_OF_SCOPE,
            template=None,
            adapters=(),
            rationale=(
                f"classifier returned OUT_OF_SCOPE: "
                f"{classification.rationale}"
            ),
        )

    if classification.verdict == ScopeVerdict.UNCERTAIN:
        return RoutingResult(
            outcome=RoutingOutcome.REJECTED_UNCERTAIN,
            template=None,
            adapters=(),
            rationale=(
                f"classifier returned UNCERTAIN: "
                f"{classification.rationale}"
            ),
        )

    # IN_SCOPE path.
    domain_id = classification.domain
    if domain_id is None:
        # Phase 2 classifier guarantees domain != None for
        # IN_SCOPE; defensive check for non-LLM classifiers.
        return RoutingResult(
            outcome=RoutingOutcome.UNKNOWN_DOMAIN,
            template=None,
            adapters=(),
            rationale="IN_SCOPE classification missing domain tag",
        )
    if not registry.has(domain_id):
        return RoutingResult(
            outcome=RoutingOutcome.UNKNOWN_DOMAIN,
            template=None,
            adapters=(),
            rationale=(
                f"domain {domain_id!r} not in registry; "
                f"registered: {registry.domain_ids}"
            ),
        )

    template = registry.get(domain_id)
    missing = [
        adapter_id
        for adapter_id in template.expected_adapter_ids
        if adapter_id not in adapters
    ]
    if missing:
        return RoutingResult(
            outcome=RoutingOutcome.MISSING_ADAPTERS,
            template=None,
            adapters=(),
            rationale=(
                f"domain {domain_id!r} requires adapters "
                f"{template.expected_adapter_ids} but missing: "
                f"{missing}"
            ),
        )

    resolved: list[DomainAdapter] = []
    for adapter_id in template.expected_adapter_ids:
        adapter = adapters[adapter_id]
        if not hasattr(adapter, "adapter_id"):
            raise DomainRouterError(
                f"adapter {adapter_id!r} does not implement the "
                "DomainAdapter Protocol (must expose adapter_id)"
            )
        # Defense: caller-supplied adapter_id key must match
        # the adapter's own adapter_id property. Catches
        # caller-side dict-construction bugs.
        if adapter.adapter_id != adapter_id:
            raise DomainRouterError(
                f"adapter dict key {adapter_id!r} does not match "
                f"adapter.adapter_id {adapter.adapter_id!r}"
            )
        resolved.append(adapter)

    return RoutingResult(
        outcome=RoutingOutcome.ROUTED,
        template=template,
        adapters=tuple(resolved),
        rationale=(
            f"routed to {domain_id!r} with adapters "
            f"{template.expected_adapter_ids}"
        ),
    )
