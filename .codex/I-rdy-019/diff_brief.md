# Codex DIFF review — I-rdy-019 / GH #515: the 24-type test matrix doc

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

The **diff** for GH #515 (Carney readiness Phase 5a — author the 24-type
test matrix against the real product journey).

- **Diff to review:** `.codex/I-rdy-019/codex_diff.patch`
  — canonical-diff-sha256 `17dd8d744c0b83a14adccd0c8e39dda63d82ac63514eaa3fbd273bf3672818e9`
  (trailer line; sha is over the patch body above it).
- **Claude architect audit:** `outputs/audits/I-rdy-019/claude_audit.md`
- **Scope:** 1 file, +374 — `docs/carney_handover/test_matrix.md` (doc-only;
  no code, no test files, no production-path change).
- The brief for this issue was Codex-APPROVE'd at iter 2
  (`.codex/I-rdy-019/codex_brief_verdict.txt`); iter-2 P2 (deployed URL
  spelling of the excluded harness route) was applied in the doc.

## 0.1 Iter-1 diff-review findings — addressed (verify the fixes)

Diff iter 1 returned 2 P1 + 4 P2 — all journey-content inaccuracies (the
matrix had been authored from route names; each was verified against
`web/app/` component code and corrected in commit `efa77204`):

- **P1-001** (Security): `/retrieval` + `/generation` expose their own
  research-question forms (`data-testid="retrieval-form"` /
  `"generation-form"`); `/dashboard` exposes a question form + upload +
  `createRun`. Security row now applies to J4, J5, J10 (was wrongly N/A).
- **P1-002** (SSE): `/runs/<runId>` subscribes to the run EventSource
  (`subscribeToRun` → `/stream/<runId>`). SSE row now applies to J7.
- **P2-001** (J10): `/dashboard` is "Start a research run" (template +
  question + upload → `createRun` → `/runs/<id>`), not an aggregates
  dashboard. J10 re-described; unit/integration/tenant cells re-pointed.
- **P2-002** (Artifact contract): `/generation` builds/downloads audit
  bundles, `/runs/<runId>` exports them. Row 3 now applies to J5, J7.
- **P2-003** (Unit): a concrete J2 unit check added (`/` template-catalog
  component logic).
- **P2-004** (Performance): Core Web Vitals apply to every rendered page;
  row 13 now ✓ for all J1-J11 (J8 keeps the long-report hover budget).

The §4 coverage grid was updated to match (rows 3, 6, 11, 13, 14).

## 0.2 Iter-2 diff-review finding — addressed (verify the fix)

Diff iter 2 returned 1 P1 (P1-003), verified against `web/app/` and fixed
in commit `b02ff164`:

- **P1-003** (`/audit_live` is not a production surface): `/audit_live`
  (`web/app/audit_live/_panels.tsx`) defaults its stream to
  `/api/audit/stream`, which `web/next.config.ts` does NOT rewrite to the
  backend; `.codex/I-f4-005/brief.md:29` already states `/audit_live` is "a
  test-route surface, not a production live-run UI". The real production
  live-run surface is `/runs/<runId>` (`subscribeToRun` → `/stream/<runId>`).
  Fix: `/audit_live` moved to the §2 excluded harness list (now 19; real
  routes 14); J6 reworked to `/runs/<runId>` in-progress streaming phase,
  J7 to `/runs/<runId>` completed-view phase; SSE row → J6 only;
  Integration J6 endpoint corrected to `/stream/<runId>`; Cancellation row
  states resume-from-checkpoint as an honest gap (forward-ref #507/#539);
  §4 grid row 11 updated.

## 0.3 Iter-3 diff-review findings — addressed (verify the fixes)

Diff iter 3 returned 1 P1 + 1 P2, verified against the codebase and fixed
in commit `56830c8b`:

- **P1-004** (tenant isolation missing J6): `/stream/<runId>` (the
  in-progress SSE endpoint, query-token auth via `streamUrl`,
  `web/lib/api.ts`; served by `src/polaris_v6/api/stream.py`) streams
  org-scoped run events. Fix: test type 15 now applies to J6 with a
  concrete cross-org `/stream/<runId>` denial check; J6 removed from the
  N/A "transitively covered" clause; §4 grid row 15 J6 → ✓.
- **P2-005** (cancellation overclaimed): the `/runs/<runId>` Cancel button
  is `disabled` (`web/app/runs/[runId]/page.tsx`) and no cancel endpoint
  exists in `src/polaris_v6/api/runs.py`. Fix: the Cancellation row now
  states BOTH cancellation AND resume are unimplemented gaps (forward-ref
  #507/#539); #516 records the whole row as expected-fail.

## 1. What #515 delivers

`docs/carney_handover/test_matrix.md` instantiates the carney-plan testing
matrix (`docs/carney_delivery_plan_v6_2.md:314-339`, 24 test types) against
the real deployed product journey (the 15 non-harness `web/app/` routes,
journey stages J1-J11), 18 harness/diagnostic routes explicitly excluded.
Per test type: plan Tool + pass-criteria, concrete check per applicable
journey stage, reasoned N/A elsewhere, plus a 24×11 coverage grid. #516
(I-rdy-020) executes this matrix.

## 2. Verification done

- All 11 journey routes cited in §1 verified to exist as
  `web/app/.../page.tsx` files.
- `/sse` reclassified to harness — confirmed: `web/app/sse/page.tsx` exports
  `SSETestHarnessPage`; `web/app/sse/_harness.tsx` renders
  `data-testid="sse-harness"`.
- 15 real + 18 harness = 33 = the full `web/app/**/page.tsx` inventory.
- All 24 test types in §3 cross-checked against plan rows v6_2:316-339.

## 3. Red-Team checklist — please verify

1. **Test-type fidelity** — do all 24 §3 rows carry the plan's (v6_2:314-339)
   Tool + Pass-criteria faithfully? Any row dropped, merged, or with an
   invented/altered pass criterion?
2. **Journey accuracy** — are J1-J11 mapped to real product routes, and are
   all 18 §2 routes genuinely harness/diagnostic (not real product surfaces
   wrongly excluded)? Any real route missing from the journey?
3. **No blank cells** — does every test-type × journey-stage pairing resolve
   to a concrete check or a *reasoned* N/A (§3 blocks + §4 grid)? Any N/A
   whose reason is wrong (i.e. the type really does apply there)?
4. **Grid consistency** — does the §4 coverage grid agree with the §3
   per-type "Applies to" / "N/A" prose for all 264 cells? Any contradiction?
5. **I-rdy-007 (#503) honesty** — is the test type 3 `forward-ref` handling
   correct (contract-level checks, field-level schema deferred to #503),
   not an overclaim or a faked schema?
6. **LAW II honesty** — does the doc anywhere imply a test has been *run*?
   It must read as an authored matrix only (#516 runs it).
7. **Scope** — doc-only, within #515 (author the matrix); no "while we're
   at it" code/test change.

## 4. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
