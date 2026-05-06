# Codex round 1 — M-INT-0a v1 (commit 76eff76)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_m_int_0a_decision_telemetry_integration.py`
- DO NOT run rg/find — read directly:
  - `src/polaris_graph/audit_ir/inspector_router.py` (the M-INT-0a block + route_query)
  - `src/polaris_graph/audit_ir/auth_middleware.py` (new `optional_caller` dep)
  - `tests/polaris_graph/test_m_int_0a_decision_telemetry_integration.py`
- DO NOT run Python verification scripts that print Unicode

## Scope
First integration milestone of `docs/full_online_plan_FINAL.md`
(Claude+Codex GREEN-signed roadmap). Wires
`decision_telemetry.record_decision(...)` into production
scope-gate at `/api/inspector/templates/route`.

## Acceptance bar (the "production import" check from FINAL_PLAN.md §G)

Per the canonical roadmap, Codex MUST grep-verify all 4:

1. **Imported.** `DecisionRecordStore` + `DecisionKind` are
   imported by `inspector_router.py`. Catches accidental
   de-integration regression.
2. **Invoked.** `_record_scope_gate_decision()` is called
   inside `route_query()` after `classify_query(...)`.
   "Imported but unused" doesn't pass.
3. **Run-log evidence.** Real test run shows DecisionRecordStore
   has rows after an authenticated route_query call.
4. **Rollback flag works.** `PG_RECORD_DECISIONS=0` actually
   disables the write path; endpoint still returns 200.

All 4 pinned by 9/9 passing tests.

## Public API change (small)

`route_query` endpoint signature added: `caller: Caller |
None = Depends(optional_caller)`. The new dep is non-raising
(returns None if no auth). Backward compat: anonymous callers
still get 200 (no telemetry). Authenticated callers (existing
test fixture uses `X-Polaris-Caller: org_default:usr_test:owner`)
get telemetry tied to `caller.org_id` as the workspace_id.

Regression: 9/9 existing template-router tests pass, 28/28
authz endpoint tests pass.

## Diff-against-baseline (what changed vs old behavior)

OLD: `route_query` was anonymous, took only `req`, returned
classification dict. No telemetry.

NEW (additive only):
- Endpoint accepts an optional `caller` dep
- After classify_query, calls `_record_scope_gate_decision(...)`
  with `workspace_id=caller.org_id if caller else None`
- Telemetry skipped when caller is None or PG_RECORD_DECISIONS=0
- Telemetry failure logged but does NOT raise (decision returned
  unchanged)
- Response shape UNCHANGED (verdict/template_id/confidence/
  candidates/rationale)

## What might Codex probe

- Workspace_id ↔ org_id mapping: M-D3 docs say "workspace_id"
  but caller has `org_id`. v1 simplification: org_id IS
  the workspace_id for this telemetry surface. Documented in
  inline comment.
- PII risk in `proposed_payload`: only verdict + template_id
  written, NOT the user's question text. (The question goes
  into the `query` column, which is part of M-D3 phase 1
  schema.)
- Singleton thread-safety: `_DECISION_STORE_LOCK` guards init.
- `_reset_decision_store_for_test()` — production code MUST
  NOT call this (docstring says so); tests use it via fixture.
- `optional_caller` fall-through on bad API key: doesn't raise,
  just returns None (silent fallback). Could mask
  misconfiguration but matches the "best-effort telemetry"
  semantic.

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Acceptance bar
- [x/ ] Imported (DecisionRecordStore + DecisionKind in inspector_router)
- [x/ ] Invoked (_record_scope_gate_decision called in route_query)
- [x/ ] Run-log evidence (test_authed_route_query_writes_decision_record passes)
- [x/ ] Rollback flag PG_RECORD_DECISIONS=0 actually disables

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```

Tool hints repeated:
- `python -m pytest -q tests\polaris_graph\test_m_int_0a_decision_telemetry_integration.py`
- Read source files directly; no rg/find
- 9/9 tests + 45/45 regression on dependent surfaces
