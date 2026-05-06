# Codex round 1 — M-LIVE-3 v1 (Operator dashboard aggregates)

## Pre-flight
- Branch: `polaris`
- Commit: `3e50977`
- Brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md` (autoloop V3)

## Scope
Phase F third milestone per FINAL_PLAN. Wires 3 M-D substrate
APIs into authenticated, org-scoped Inspector endpoints.

## Tool hints
- Read: `src/polaris_graph/audit_ir/inspector_router.py:2614-end`
  (M-LIVE-3 endpoint block)
- Read: `src/polaris_graph/audit_ir/decision_aggregates.py:121-219`
  (compute_aggregates contract)
- Read: `src/polaris_graph/audit_ir/freshness_aggregates.py:214-`
  (compute_freshness_aggregates contract)
- Read: `src/polaris_graph/audit_ir/pin_trends.py:254-`
  (analyze_pin_trends contract)
- Smoke (manual TestClient probes — work):
  - GET /api/inspector/dashboard/decision-aggregates → 200
  - GET /api/inspector/dashboard/freshness-aggregates → 200
  - GET /api/inspector/dashboard/pin-trends → 200

## Acceptance bar
1. **Endpoints exist.** 3 GET routes registered:
   - /api/inspector/dashboard/decision-aggregates
   - /api/inspector/dashboard/freshness-aggregates
   - /api/inspector/dashboard/pin-trends
2. **Substrate wiring.** Each endpoint wraps the named M-D
   substrate function (compute_aggregates,
   compute_freshness_aggregates, analyze_pin_trends).
3. **Org-scoped.** Decision + freshness use `caller.org_id` as
   workspace_id (M-LIVE-3 spec). Pin trends has best-effort
   org-scoping via auth gate (pin files do not currently
   carry org_id; deferred to M-INT-0b v2).
4. **Time-windowed.** since/until UNIX-epoch float params on
   decision + freshness.
5. **Rollback flag.** `PG_USE_OPERATOR_DASHBOARD=0` returns 404
   (default ON).
6. **Auth required.** `require_authenticated_caller` dep on all
   three endpoints.
7. **Path traversal guard.** Pin-trends `out_root` param
   constrained to repo root.

## Severity rubric
- **P0** — production-breaker: endpoint crashes, wrong
  workspace, auth bypass, path traversal escape, flag broken
- **P1** — phase-rework: acceptance criterion not met
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly — do not manufacture findings.
- Verify each substrate wiring by reading the FastAPI handler
  AND the substrate function it calls.
- Test cross-org isolation: org_a → only sees org_a aggregates.
- Test path-traversal guard on pin-trends `out_root` param.
- Test rollback flag (`PG_USE_OPERATOR_DASHBOARD=0`).

## Skepticism gate
Before declaring a verdict, list:
- which files you read + line ranges
- which acceptance criteria you confirmed evidence for
- whether you actually invoked the endpoints (TestClient or
  similar) or only read code

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- Speculative concerns about code that does not exist
- Pin trends org-scoping (documented as deferred to M-INT-0b v2)

## Verdict format
```
## Files scanned
## Acceptance bar verification
## Findings
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict
APPROVE | REQUEST_CHANGES
```

## Round metadata
This is round 1 — comprehensive pass. Hard iter cap: 5.
