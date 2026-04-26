# Codex review of M-2

## Verdict
PARTIAL

## Specific issues
1. High — [`src/polaris_graph/audit_ir/registry.py`](C:/POLARIS/src/polaris_graph/audit_ir/registry.py:81) breaks the list/detail contract. `list_available_runs()` scans all `outputs/**/manifest.json` and only requires `manifest.json` + `report.md`, while [`load_audit_ir()`](C:/POLARIS/src/polaris_graph/audit_ir/inspector_router.py:78) requires a much stricter artifact set. In this workspace that yields 90 listed runs / 12 unique slugs, and 75 of those listed runs fail `load_audit_ir()`. This is not Phase A scoped.
2. High — [`src/polaris_graph/audit_ir/registry.py`](C:/POLARIS/src/polaris_graph/audit_ir/registry.py:103) uses `slug` as the lookup key even though the scan returns many duplicate slugs. Example: `clinical_tirzepatide_t2dm` appears 49 times; [`find_run_by_slug()`](C:/POLARIS/src/polaris_graph/audit_ir/registry.py:103) returns the first match only. So `/api/inspector/runs` can list a run_id that `/api/inspector/runs/{slug}` cannot actually fetch; it resolves to a different artifact.
3. Medium — the Phase A access-gating comments overstate current protection. [`scripts/live_server.py`](C:/POLARIS/scripts/live_server.py:1432) includes the inspector router unconditionally, and auth in [`src/auth/auth_middleware.py`](C:/POLARIS/src/auth/auth_middleware.py:30) is opt-in per route. In-repo, the inspector is deployment-gated only, not app-gated. A banner / `noindex` is fine, but it is not the security boundary.
4. Low — [`src/polaris_graph/audit_ir/serializer.py`](C:/POLARIS/src/polaris_graph/audit_ir/serializer.py:16) is correct for the current IR surface, but `_coerce()` returns unknown leaf types unchanged at line 31. That is not a current bug; it is future fragility if the IR later gains `datetime`/`Enum`/`Decimal`-like fields.

## Recommended changes
- [`src/polaris_graph/audit_ir/registry.py`](C:/POLARIS/src/polaris_graph/audit_ir/registry.py:81): for Phase A, hard-scope discovery to the canonical demo set you actually intend to expose. If Phase A is really one canonical demo, return that one artifact and stop scanning all of `outputs/`.
- [`src/polaris_graph/audit_ir/registry.py`](C:/POLARIS/src/polaris_graph/audit_ir/registry.py:81) and [`src/polaris_graph/audit_ir/inspector_router.py`](C:/POLARIS/src/polaris_graph/audit_ir/inspector_router.py:67): if you want multiple runs, require full AuditIR loadability at discovery time and route by a unique key (`run_id` or stable artifact key), not `slug`.
- [`tests/polaris_graph/test_audit_ir_registry.py`](C:/POLARIS/tests/polaris_graph/test_audit_ir_registry.py:29) and [`tests/polaris_graph/test_inspector_router.py`](C:/POLARIS/tests/polaris_graph/test_inspector_router.py:22): add tests that every listed run is uniquely addressable and that each listed item round-trips list -> detail without 500 or run_id drift.
- Optional hardening: make [`src/polaris_graph/audit_ir/serializer.py`](C:/POLARIS/src/polaris_graph/audit_ir/serializer.py:31) raise `TypeError` on unsupported leaf types. Circular-ref guarding is not needed for the current acyclic dataclass graph.

## M-3 readiness
The IR -> JSON path is ready for View 1 once discovery/identity is fixed. The serializer preserves `verified_report.sections[].sentences[].tokens[]`, and the current 21 M-2 tests pass locally. I do not see a router-structure, CSP, HTML-shell, cache, or tier-palette blocker for M-3. `APIRouter + include_router` is the right integration pattern, and cache should be deferred until after registry semantics are corrected.

## Final word
PARTIAL with edits. Fix registry scope + unique route identity before locking M-2. After that, GREEN for M-3 consumption.
