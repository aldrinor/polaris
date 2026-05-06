# Codex round 1 — M-D6 phase 1 v1

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md6_phase1_domain_router.py`
- DO NOT run rg/find — read directly:
  - `src/polaris_graph/audit_ir/domain_router.py` (~280 lines)
  - `tests/polaris_graph/test_md6_phase1_domain_router.py` (~280 lines)
  - `docs/md6_phase1_threat_model.md` (~190 lines)

## Scope
Cross-domain routing substrate. Builds on M-D5 phase 2's
classifier domain tag. Substrate ONLY — concrete HTTP adapter
impls deferred to phase 2.

## Public API

```python
@dataclass(frozen=True)
class DomainTemplate:
    domain_id: str
    display_name: str
    scope_template_path: str
    expected_adapter_ids: tuple[str, ...] = ()

class DomainTemplateRegistry:
    def __init__(self, templates: tuple[DomainTemplate, ...]): ...
    @property
    def domain_ids(self) -> tuple[str, ...]: ...
    def get(self, domain_id: str) -> DomainTemplate: ...
    def has(self, domain_id: str) -> bool: ...

class DomainAdapter(Protocol):
    @property
    def adapter_id(self) -> str: ...

class RoutingOutcome(str, Enum):
    ROUTED = "routed"
    REJECTED_OUT_OF_SCOPE = "rejected_out_of_scope"
    REJECTED_UNCERTAIN = "rejected_uncertain"
    UNKNOWN_DOMAIN = "unknown_domain"
    MISSING_ADAPTERS = "missing_adapters"

def route_to_domain(
    classification: ScopeClassification,
    registry: DomainTemplateRegistry,
    adapters: Mapping[str, DomainAdapter],
) -> RoutingResult: ...
```

## Boundaries (7 documented)

1. Pure stdlib substrate (no HTTP, no YAML loading)
2. Closed RoutingOutcome taxonomy (5 values)
3. Adapter dict-key / adapter_id consistency required
4. Adapters resolved in template-declared order
5. IN_SCOPE without domain → UNKNOWN_DOMAIN (defensive)
6. Registry rejects malformed input at construction
7. Empty expected_adapter_ids tuple is valid

## Tests (21/21 passing)

- Registry indexing + lookup + has + domain_ids ordering
- Registry construction validation (4 negative cases)
- Routing dispatch on each verdict (3 cases)
- IN_SCOPE with known + unknown + missing-domain
- Missing adapters detection
- Adapters resolved in template order
- Adapter validation (no adapter_id attr, mismatch)
- Contract validation (3 negative cases)
- Empty expected_adapter_ids edge case

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate
- [x/ ] RoutingOutcome taxonomy closed
- [x/ ] Adapter id consistency
- [x/ ] Defensive UNKNOWN_DOMAIN

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
