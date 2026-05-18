# Codex DIFF review — I-rdy-008 / GH #504 slice 7b: migrate the inspector page off getBundle() onto the live evidence route

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 7b** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1,
0 P0/P1, 3 P2). **3 files: `web/app/inspector/[runId]/page.tsx` +
`web/lib/api.ts` + `logs/bug_log.md`.**

Slice 7b is the frontend half of the slice-7 split your architecture consult
decided (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`). Slice 7a
(merged, PR #596) shipped `GET /api/inspector/runs/{run_id}/evidence`. Slice
7b migrates the inspector page off the golden-fixture-only `getBundle()`
onto that route. Frontend only — the backend route is unchanged.

## 2. The problem this fixes

The inspector page (`web/app/inspector/[runId]/page.tsx`) dual-fetched
`getAuditRun()` + `getBundle()` and gated its whole body on
`{ir && bundle && (...)}`. `getBundle()` hits `/runs/{id}/bundle`, whose
route is a hardcoded 7-run golden-fixture index → **404 for every live
run** → `bundle` stays null → the body never renders. The inspector was
golden-fixture-only; #504's "wire live runs into the rich UI" goal was
unmet for the inspector surface.

## 3. The change

- **`web/lib/api.ts`** — add `getInspectorEvidence(runId)` →
  `authFetch(GET /api/inspector/runs/{runId}/evidence)` → `asJsonOrThrow`;
  add `AuditIrEvidenceSpan` (`evidence_id`, `span_start`, `span_end`,
  `span_text`, `tier`, `source_url`, `claim_ids`) + `AuditIrEvidenceResponse`
  (`run_id`, `spans[]`) — shapes mirror the slice-7a route's JSON.
  `getBundle` / `EvidenceContract` / `SourceSpan` / `downloadBundleAsJson`
  are **kept** (still imported by `web/app/runs/[runId]/page.tsx`).
- **`web/app/inspector/[runId]/page.tsx`**:
  - imports: drop `getBundle` / `EvidenceContract` / `SourceSpan` /
    `downloadBundleAsJson`; add `getInspectorEvidence` /
    `AuditIrEvidenceResponse` / `AuditIrEvidenceSpan`.
  - state: `bundle: EvidenceContract | null` → `evidence:
    AuditIrEvidenceResponse | null` + `evidenceError: string | null`;
    `selectedEvidence: SourceSpan | null` → `selectedEvidenceId: string |
    null`.
  - the load `useEffect` fetches `getInspectorEvidence(runId)` independently
    of `getAuditRun()` — its failure sets `evidenceError`, never blocks `ir`.
  - `evidenceById` → `spansForEvidenceId(id)` = `evidence?.spans.filter(s =>
    s.evidence_id === id) ?? []`.
  - the tabs-initializer gate + the body gate drop `&& bundle` (now `ir`
    only); the bundle Export button is removed.
  - the Pool-tab count = `new Set((evidence?.spans ?? []).map(s =>
    s.evidence_id)).size`.
  - `PoolTab({evidence, evidenceError, onSelect})` — `evidenceError` → error
    panel; `evidence === null` → "Loading evidence…"; empty `spans` → empty
    state; else group `spans` by `evidence_id` into a `Map`, one row per id.
  - `EvidencePane({evidenceId, spans, evidenceError, onClose})` — null id →
    placeholder; `evidenceError` → "Evidence unavailable" card; empty
    `spans` → "No verified span recorded"; else render every span of that
    id (`spans[0]` for the shared tier/source_url, all spans for the char
    ranges + `<pre>` bodies).
  - the dead `slugifySection` helper + the `SentencesTab` contradiction
    badge are deleted (`SentencesTab` no longer takes `bundle`).
- **`logs/bug_log.md`** — the slice-7 §6.2 Degradation Proposal marked
  RESOLVED (routed to your arch consult).

## 4. Verify

1. **No `getBundle()` in the inspector page.** `getBundle` /
   `EvidenceContract` / `SourceSpan` / `downloadBundleAsJson` are gone from
   `web/app/inspector/[runId]/page.tsx` code. A live completed run now
   renders (its body no longer gates on a 404'ing fetch).
2. **`getBundle()` retained for the runs page.** It is still exported from
   `web/lib/api.ts` and still imported by `web/app/runs/[runId]/page.tsx` —
   confirm slice 7b did not break that page.
3. **Independent failure isolation.** A failed evidence fetch sets
   `evidenceError` only; `ir` is unaffected; Summary / Sentences / Frames /
   Contradictions tabs still render. PoolTab + EvidencePane surface the
   error (fail loud) — no silent fallback, no zero-fill.
4. **PoolTab guards `evidence === null`.** Because the body gates on `ir`
   only, PoolTab renders before the evidence fetch resolves — confirm no
   unguarded `evidence.spans` dereference.
5. **Span grouping.** The 7a route returns one span per `(evidence_id,
   start, end)`. PoolTab groups by `evidence_id`; EvidencePane shows all
   ranges of the clicked id. Confirm `spans[0]` for shared tier/source_url
   is sound (same id → same source).
6. **No backend / no test change.** Only the 3 named files. The inspector
   e2e + demo fixtures are rebaselined in slice 7c (per the brief; you ruled
   3.5 accept). Confirm no `src/**`, no `tests/**`.

## 5. Files I have ALSO checked and they're clean

- `web/app/runs/[runId]/page.tsx` — the other `getBundle()` /
  `downloadBundleAsJson` consumer; NOT modified, still imports them from
  `web/lib/api.ts`.
- `src/polaris_v6/api/inspector.py` — the slice-7a evidence route the new
  client calls; NOT modified (7a shipped it).
- `web/components/ui/evidence-tooltip.tsx` — `sourceTier` widened in slice
  4; NOT touched by 7b.
- `tests/e2e/sentence_inspector*.spec.ts` — the inspector e2e specs; NOT
  modified — slice 7c rebaselines them against the new data path.

## 6. Smoke state

`npx prettier --write` both files. `npm run format:check` — 188 files
flagged, all pre-existing repo-wide debt (the 2 slice-7b files are clean).
`npm run lint` — **0 errors**, 3 warnings all pre-existing (incl.
`page.tsx` `chartTypes` `exhaustive-deps`, verified identical on
`origin/polaris` — the line number shifted only because slice 7b removed
dead code). `npm run typecheck` — `tsc --noEmit` clean. `npm run build` —
succeeded, `/inspector/[runId]` present as a dynamic route.

## 7. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
