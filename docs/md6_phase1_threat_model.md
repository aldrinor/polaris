# M-D6 phase 1 v1 — cross-domain routing substrate boundary

**Status:** v2 / 2026-04-29
**Module:** `src/polaris_graph/audit_ir/domain_router.py`
**Tests:** `tests/polaris_graph/test_md6_phase1_domain_router.py` (23 passing)
**Pairs with:** M-D5 phase 1 (gate orchestrator), M-D5 phase 2
(LLM classifier producing the domain tag).
**Substrate:** stdlib + `scope_classifier` + `scope_classifier_llm`.

---

## Scope

M-D5 phase 2's classifier returns a `ScopeClassification` with
a `domain` tag. Routing that tag to the right
domain-specific retrieval pipeline is M-D6's job.

Phase 1 v1 ships **routing substrate ONLY** — concrete
adapter implementations (NIST/MITRE for cybersec, FAERS/EV
for pharmacovigilance, ASTM for materials) are deferred to
phase 2.

What v1 ships:
  - `DomainTemplate` dataclass (domain_id + display_name +
    scope_template_path + expected_adapter_ids)
  - `DomainTemplateRegistry` — workspace-scoped lookup
  - `DomainAdapter` Protocol — pluggable retrieval seam
  - `RoutingOutcome` enum (5 outcomes)
  - `RoutingResult` dataclass
  - `route_to_domain(classification, registry, adapters)` —
    pure orchestrator

What phase 2 (deferred) will ship:
  - Concrete `DomainAdapter` impls per domain
  - YAML-loading layer for `scope_template_path`
  - HTTP wiring (Crossref, PubMed, NIST, MITRE, FAERS, etc.)
  - Adapter response shape (typed `AdapterFetchResult`)

---

## v1 boundaries

### 1. Pure substrate — no HTTP, no YAML loading

`domain_router.py` imports stdlib + `scope_classifier` (phase
1 contracts) + `scope_classifier_llm` (phase 2 verdict shape)
only. No PyYAML, no HTTP clients, no DB.

The substrate stores `scope_template_path` as a string;
loading the YAML is caller territory. This keeps the routing
layer testable without filesystem dependencies and lets the
YAML-loader live wherever it makes sense (probably with
`scope_query_validator.py`).

### 2. Closed RoutingOutcome taxonomy (5 values)

`RoutingOutcome` enumerates exactly:
  - `ROUTED` — IN_SCOPE + known domain + adapters present
  - `REJECTED_OUT_OF_SCOPE` — classifier verdict
  - `REJECTED_UNCERTAIN` — classifier verdict
  - `UNKNOWN_DOMAIN` — IN_SCOPE but domain not in registry
  - `MISSING_ADAPTERS` — domain template lists adapters not
    in the supplied adapter dict

Distinct enum values for the rejection reasons let callers
emit different UI / telemetry on each. v2 may add more
outcomes (e.g. "ADAPTER_HEALTH_DEGRADED" once health checks
ship); the substrate's taxonomy is closed at v1.

**Mitigation**: tests pin all 5 outcomes explicitly.

### 3. Adapter dict-key / adapter_id consistency required

`route_to_domain` validates that for each
`adapters[adapter_id]`, the resolved adapter's
`adapter_id` property MATCHES the dict key. A mismatch
raises `DomainRouterError` — catches caller-side dict-
construction bugs (e.g. `{"crossref": pubmed_adapter}`)
before the wrong adapter gets dispatched.

**Mitigation**: `test_route_raises_on_adapter_id_mismatch`.

### 4. Adapters resolved in template-declared order

`RoutingResult.adapters` is a tuple in the order listed by
`template.expected_adapter_ids`, NOT the dict insertion
order of `adapters`. This makes downstream invocation
ordering deterministic regardless of how the caller built
the adapter dict.

**Mitigation**: `test_route_resolves_adapters_in_template_order`.

### 5. IN_SCOPE without domain tag → UNKNOWN_DOMAIN

Phase 2 LLM classifier guarantees `domain != None` for
IN_SCOPE verdicts. But non-LLM `ScopeEligibilityClassifier`
implementations (e.g. a future regex-anchor fallback) might
not. Defensive substrate path: IN_SCOPE + domain=None →
UNKNOWN_DOMAIN with rationale "IN_SCOPE classification
missing domain tag" rather than a silent route attempt.

**Mitigation**:
`test_route_in_scope_missing_domain_tag`.

### 6. Registry rejects malformed input at construction time

`DomainTemplateRegistry.__init__` validates:
  - `templates` MUST be a tuple (not list/iter)
  - Each element MUST be `DomainTemplate`
  - `domain_id` MUST be non-empty
  - No duplicate `domain_id` values

All raise `DomainRouterError` at construction — caller-side
bugs surface immediately, not at first lookup.

**Mitigation**: 4 negative-case tests pin each.

### 7. Empty expected_adapter_ids tuple is valid

A `DomainTemplate` with `expected_adapter_ids=()` is valid —
some domains might be metadata-only (e.g. "meta" domain that
just routes to a static knowledge base, no live adapter
needed). Routing succeeds with `adapters=()` in the result.

**Mitigation**:
`test_route_template_with_no_expected_adapters`.

---

## v1 NON-goals (defer to phase 2)

  - **No HTTP-backed adapter impls**: substrate ships
    `DomainAdapter` Protocol + `_StubAdapter` test fixture.
    Production wiring is phase 2.
  - **No YAML loader**: substrate stores
    `scope_template_path` as a string. Loader lives elsewhere.
  - **No adapter health checks**: callers wire their own
    health probing. Routing trusts adapter presence in dict.
  - **No adapter response typing**: `DomainAdapter` Protocol
    only requires `adapter_id`. Caller knows how to invoke
    each adapter and what shape comes back.
  - **No M-D7 cache integration**: callers wire the cache
    around their adapter invocations.
  - **No M-D8 parallel-fetch integration**: callers compose
    parallel_fetch + adapters as needed.
  - **No LLM-assisted ambiguous-domain handling**: if the
    classifier returns UNCERTAIN, routing rejects. v2 may
    add a "tier-down to a meta-domain" fallback.

---

## Codex review trail

Round-1 brief incoming. Tool hints:
- `python -m pytest -q tests\polaris_graph\test_md6_phase1_domain_router.py`
- DO NOT run rg/find — read source/tests/threat-model directly
- DO NOT run Python verification scripts that print Unicode
- 21 tests pin all 7 boundaries

Targeted at 1-2 round convergence per the M-D5 phase 2 +
M-D11 phase 2 v2 patterns (substrate orchestration with
v1-shipped threat-model docs).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (concrete
adapters, YAML loader, M-D7/M-D8 integration) tracked
separately.
