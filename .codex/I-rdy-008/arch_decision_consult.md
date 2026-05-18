# Codex architecture-decision consult — I-rdy-008 / GH #504: how to wire live runs into the rich UI

This is a **decision consult**, not a brief/diff gate review. The operator has
delegated this architecture choice to you and asked specifically: **which
option yields the biggest quality improvement** for #504 and the surfaces that
build on it. Return a clear verdict (A or B) + reasoning + the resulting #504
decomposition. Filter freely — correct anything stale below.

## The issue

GH #504 (I-rdy-008, Phase 3.5 of the Carney readiness chain): "Inspector,
charts, follow-up, compare, pin replay, memory, and bundle all accept a real
completed run ID, not only golden fixtures." Acceptance: a live run is fully
inspectable end-to-end through every rich surface. #506 (document grounding),
#508 (durable memory), #510 (demo journey) depend on the data path chosen here.

## Grounded substrate findings (verified in current `polaris` HEAD)

1. **A faithful AuditIR backend already exists but is unmounted.**
   `src/polaris_graph/audit_ir/inspector_router.py` — ~1400 lines, 18 routes,
   incl. `GET /api/inspector/runs/{slug}` → `find_run_by_slug` →
   `load_audit_ir(artifact_dir)` → `to_json_dict(ir)` (full faithful AuditIR
   JSON), plus `/report.md`, `/audit-bundle.zip`, run-diff, regression,
   slide-deck, health, and ~10 more. `src/polaris_v6/api/app.py` mounts 21
   routers; **this one is not among them.**
2. **The frontend is on a different, narrower path.**
   `web/app/inspector/[runId]/page.tsx` (805 lines) calls `getBundle(runId)` →
   `GET /runs/{id}/bundle` (`src/polaris_v6/api/bundle.py`), which is
   **golden-fixture-only**: it serves an `EvidenceContract` for 7 hard-coded
   golden run-ids and 404s otherwise. `compare.py` `_load()` is the same.
3. **`EvidenceContract` is structurally too narrow for a live run.**
   `src/polaris_v6/schemas/evidence_contract.py` `SourceSpan.source_tier` is
   constrained to `T1|T2|T3`; evidence is keyed by `evidence_id` only. Real
   V30 artifact dirs carry T4-T7 sources (T4 used by kept sentences), and the
   `AuditIR` verified-report cites one `evidence_id` at multiple
   `[#ev:id:start-end]` span ranges. A faithful adapter into `EvidenceContract`
   either fails validation or loses span/tier fidelity.
4. **The #503 contract (just merged) names `AuditIR` as canonical.**
   `docs/live_run_artifact_contract.md` (I-rdy-007): `load_audit_ir()` →
   `AuditIR` is "the single source of truth ... all derivative renderers
   project from it." `EvidenceContract` is the older golden-fixture shape.
5. Identity mismatch: `inspector_router` resolves by `slug`; v6 runs are UUID
   `run_id`; `run_store` carries the UUID ↔ `query_slug` ↔ `manifest_run_id`
   mapping (I-arch-001a).

## Fixed context (operator-locked — do not reopen)

- Generator DeepSeek V4 Pro, evaluator Gemma 4 31B. Single-venue June Carney
  demo. v6 stack, no rewrites (`docs/polaris_locked_scope.md`).
- §-1.1 audit-fidelity standard: an inspector that shows a wrong evidence span
  or a coerced source tier is a fidelity failure — unacceptable in clinical
  context. "Approximately right" is not acceptable for the audit surface.

## The two options

**Option A — mount `inspector_router.py` (demo-scoped routes) + migrate the
frontend surfaces to `/api/inspector/*`.**
- Serves the faithful raw `AuditIR` (all tiers, range-keyed spans). Matches the
  #503 contract.
- The backend is largely already built; the work is: mount it (auditing which
  of the 18 routes are demo-scoped per `polaris_locked_scope.md`), bridge
  run-id ↔ slug, and migrate the 805-line inspector frontend + the other
  surfaces off `getBundle`/`EvidenceContract`.

**Option B — keep `getBundle`/`EvidenceContract`, expand that schema.**
- Grow `EvidenceContract` to T1-T7 + range-keyed spans; keep the frontend
  largely as-is.
- Leaves two parallel post-run shapes (`EvidenceContract` and `AuditIR`) — a
  drift surface; and it grows the shape the #503 contract calls non-canonical.
  The schema change touches the 7 golden fixtures, the I-ecg contract editor,
  and `compare.py`.

## What to return

```yaml
verdict: A | B
quality_reasoning: <why the chosen option yields the bigger quality improvement
  for #504 + #506/#508/#510, judged on audit fidelity + the demo>
decomposition: <how #504 re-slices into <=200-LOC per-surface PRs under the
  chosen option; what slice 1 is>
key_risks: [...]
```
