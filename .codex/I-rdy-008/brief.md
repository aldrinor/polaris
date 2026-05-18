# Codex BRIEF review — I-rdy-008 / GH #504 slice 7b: migrate the inspector page off getBundle() onto the live evidence route

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 7b of #504 — the architecture is settled

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI"). Slices 1-6
+ 7a merged (PR #590-#596). Slice 7 was split by a Codex architecture
consult (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`) into 7a backend
/ 7b frontend / 7c tests. **7a shipped** the v6 route
`GET /api/inspector/runs/{run_id}/evidence`. **This is slice 7b — the
frontend migration; a normal implementation brief, architecture settled.**

**Why 7b matters:** the inspector page currently dual-fetches `getAuditRun()`
+ `getBundle()` and gates its body on `{ir && bundle}`. `getBundle()` hits a
**golden-fixture-only** route — it 404s for every live run. So the inspector
page works ONLY for the 7 golden fixtures today; slices 3-6 migrated
rendering but kept the `bundle` dependency. **7b removes that dependency so
the page works for live runs.**

## 1. Grounded state (`polaris` HEAD `2e4ef83f`)

### 1.1 `web/app/inspector/[runId]/page.tsx` (1095 lines)

- `InspectorPage` — `useEffect` dual-fetches `getAuditRun()→ir` +
  `getBundle()→bundle`; both `.catch`→`setError`. Body gated `{ir && bundle &&
  …}`. State: `ir`, `bundle`, `error`, `selectedEvidence: SourceSpan|null`,
  `activeTab`.
- `evidenceById(id) = bundle?.evidence_pool.find(s => s.evidence_id===id)`
  → `SourceSpan|null`. Every tab's `onSelect={(id) =>
  setSelectedEvidence(evidenceById(id))}` (summary/sentences/contradictions/
  pool/charts).
- `tabs` array gated `ir && bundle`; the `pool` count is
  `bundle.evidence_pool.length` (every other count already `ir.*`).
- Header "Export bundle JSON" button → `downloadBundleAsJson(bundle)`.
- `PoolTab({bundle, onSelect})` — maps `bundle.evidence_pool` (`SourceSpan[]`)
  → buttons (`evidence_id · tier · span_text[:120]`).
- `EvidencePane({span: SourceSpan|null, onClose})` — renders one `SourceSpan`
  (`evidence_id · tier`, `source_url` link, `chars start–end`, `span_text`).
- `SentencesTab` takes `bundle` ONLY for the contradiction-in-section badge
  (`new Set(bundle.contradictions.map(c => c.section_id))`).
- `ChartsTab` uses the separate `getChart()` route — NOT `getBundle()` —
  unaffected.

### 1.2 `web/lib/api.ts`

- `getBundle()` → `GET ${BACKEND_URL}/runs/{runId}/bundle` →
  `EvidenceContract` (golden-fixture-only). `SourceSpan` =
  `{evidence_id, source_url, source_tier: "T1"|"T2"|"T3", span_start,
  span_end, span_text}`. `downloadBundleAsJson(bundle)`.
- The slice-7a route `GET /api/inspector/runs/{run_id}/evidence` returns
  `{run_id, spans: [{evidence_id, span_start, span_end, span_text,
  tier (raw string), source_url, claim_ids}]}` — **range-keyed**: one
  `evidence_id` can have multiple spans.

## 2. The plan — `web/lib/api.ts` + `web/app/inspector/[runId]/page.tsx`

### 2.1 `web/lib/api.ts`

Add (alongside the slice-2 `AuditIr*` block):
- `AuditIrEvidenceSpan` = `{evidence_id, span_start, span_end, span_text,
  tier: string, source_url, claim_ids: string[]}`.
- `AuditIrEvidenceResponse` = `{run_id, spans: AuditIrEvidenceSpan[]}`.
- `getInspectorEvidence(runId): Promise<AuditIrEvidenceResponse>` →
  `authFetch(\`${BACKEND_URL}/api/inspector/runs/${encodeURIComponent(runId)}
  /evidence\`)` → `asJsonOrThrow`.

### 2.2 `web/app/inspector/[runId]/page.tsx`

**The `onSelect(id: string)` signature is UNCHANGED** — the key
simplification. `EvidencePane` is keyed by `evidence_id` but renders **every
range** of that evidence (Codex consult risk: "do not key by evidence_id
alone; live runs cite multiple ranges" — satisfied by showing all ranges,
not by changing the click signature across 4 call sites).

- **Fetch:** `useEffect` fetches `getAuditRun()→ir` + `getInspectorEvidence()
  →evidence`. `getBundle()` is removed.
- **State:** `bundle` → `evidence: AuditIrEvidenceResponse | null`;
  `evidenceError: string | null` (separate from the page `error`);
  `selectedEvidenceId: string | null` (was `selectedEvidence: SourceSpan`).
- **Gate:** the body gate `{ir && bundle}` → `{ir &&}`. `ir` failing
  (404/409/422) still shows the error panel. The **evidence fetch is
  independent** — if it 422s (e.g. a run with no `evidence_pool.json`), the
  page still renders shell + summary + sentences + frames + contradictions;
  only `PoolTab`/`EvidencePane` show `evidenceError`. This is why the page
  now works for live runs: the shell no longer hard-requires the
  golden-fixture bundle.
- **`evidenceById` → `spansForEvidenceId(id)`** = `evidence?.spans.filter(s
  => s.evidence_id === id) ?? []`.
- **`PoolTab({evidence, evidenceError, onSelect})`** — if `evidenceError`,
  render it; else group `evidence.spans` by `evidence_id` and render one row
  per evidence id (id · tier · span count · first span_text excerpt);
  `onClick → onSelect(evidence_id)`.
- **`EvidencePane({spans, evidenceId, onClose})`** — `spans` = the selected
  id's spans; renders `evidence_id · tier`, `source_url` link, then EACH span
  (`chars start–end` + `span_text` `<pre>`). Empty/no-selection → the "Click
  a token to inspect" placeholder.
- **`tabs`:** gate `ir &&` (drop `&& bundle`); `pool` count = the count of
  distinct `evidence_id`s in `evidence.spans` (0 when evidence unloaded).
- **`SentencesTab`:** drop the `bundle` prop and the contradiction-in-section
  badge + `onJumpToContradictions` (Codex consult: AuditIR contradiction
  clusters carry no section — remove the badge; §3.3).
- **Export button:** removed (Codex consult: do not export `EvidenceContract`
  as the live audit artifact; §3.4).
- **Imports:** drop `getBundle`, `downloadBundleAsJson`, `EvidenceContract`,
  `SourceSpan`; add `getInspectorEvidence`, `AuditIrEvidenceResponse`,
  `AuditIrEvidenceSpan`.

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — `onSelect(id)` unchanged; EvidencePane shows ALL ranges of the
clicked `evidence_id`.** The 7a route is range-keyed but the 4 click sources
(`renderSentenceWithTokens`, `ContradictionsTab`, `ExecutiveSummaryTab`/
`ChartsTab` chart data) pass only an `evidence_id`. Rather than thread
`(id,start,end)` through all of them, `EvidencePane` is keyed by
`evidence_id` and renders every cited range. Rule: accept (no lossy
single-range pick; no 4-call-site signature churn), or require threading the
exact range?

**3.2 — evidence fetch is independent of the page gate.** The body gates on
`ir` only; the evidence fetch's failure (422 for a run without
`evidence_pool.json`) degrades ONLY `PoolTab`/`EvidencePane` (they show
`evidenceError`), not the whole page. This is deliberate — it is what makes
the page work for live runs whose evidence is fetched separately. Rule:
accept?

**3.3 — drop the SentencesTab contradiction-in-section badge.** It read
`bundle.contradictions[].section_id`; AuditIR contradiction clusters carry no
section. The Codex arch consult said "replace with an AuditIR-derived signal
or remove it." Plan: remove the badge + the now-unused `onJumpToContradictions`
prop. Rule: accept removal (no faithful AuditIR section linkage exists), or
require a derived signal?

**3.4 — remove the "Export bundle JSON" button.** It exported the
golden-fixture `EvidenceContract`. The Codex consult said do not export
`EvidenceContract` as the live audit artifact. Plan: remove the button (a
later slice may add an AuditIR/audit-bundle export). Rule: accept removal?

**3.5 — one PR vs split.** This is one cohesive `web/lib/api.ts` +
`web/app/inspector/[runId]/page.tsx` change (the `onSelect`-unchanged design
in §3.1 bounds it — no signature churn). Estimated ~200-250 line churn.
Rule: accept as one slice 7b PR, or split (e.g. 7b-1 evidence client +
PoolTab/EvidencePane; 7b-2 gate-flip + getBundle removal + badge/Export)?

**3.6 — `ChartsTab` stays.** It uses `getChart()` (a separate route), not
`getBundle()` — unaffected by 7b; its `onSelect` chart-click still resolves
through the (now evidence-backed) `spansForEvidenceId`. Confirm no action.

## 4. Scope boundary

- **IN:** `web/lib/api.ts` (the evidence client + 2 types);
  `web/app/inspector/[runId]/page.tsx` (fetch, gate, `PoolTab`,
  `EvidencePane`, `SentencesTab` badge removal, Export removal, imports).
- **OUT:** `web/app/runs/[runId]/page.tsx` (also uses `getBundle()` — a
  separate page, not #504-inspector scope); `src/**` (7a shipped the route);
  `src/polaris_v6/api/bundle.py` (the golden-fixture route stays for
  legacy/F15); slice 7c (inspector e2e/demo fixture rebaseline).

## 5. Smoke test

Frontend change → the `lint + format + typecheck + build` CI job is IN
SCOPE. Offline: `cd web && npx prettier --write` the 2 files
`&& npm run format:check && npm run lint && npm run typecheck && npm run
build` — all green. The 1 pre-existing inspector-page lint warning
(`chartTypes` `exhaustive-deps`) must not increase. No new unit test (a
data-source swap; consistent with slices 3-6 — slice 7c handles e2e/demo
fixtures).

## 6. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/inspector.py` — the 7a `/evidence` route the client
  targets; NOT modified.
- `web/lib/api.ts` — `getAuditRun` + `AuditIr*` (slice 2); `getChart` (used
  by `ChartsTab`, kept); `getBundle`/`EvidenceContract`/`SourceSpan`/
  `downloadBundleAsJson` become unreferenced by the inspector page after 7b
  but are NOT deleted from api.ts (`web/app/runs/[runId]/page.tsx` still
  imports `getBundle`) — only the inspector page's imports drop them.
- `web/app/runs/[runId]/page.tsx` — separate page; still uses `getBundle()`;
  out of #504-inspector scope; NOT modified.
- `ChartsTab` — `getChart()`-backed; NOT modified.

## 7. Acceptance criteria for THIS PR (slice 7b)

1. `web/lib/api.ts` gains `getInspectorEvidence()` + `AuditIrEvidenceSpan`/
   `AuditIrEvidenceResponse`.
2. The inspector page fetches `getAuditRun()` + `getInspectorEvidence()`,
   gates the body on `ir` only, and no longer calls `getBundle()`.
3. `PoolTab` + `EvidencePane` render the AuditIR evidence spans; a clicked
   `evidence_id` shows all its ranges; an evidence-fetch failure degrades
   only those two surfaces.
4. The SentencesTab contradiction badge + the Export button are removed; the
   `getBundle`/`EvidenceContract`/`SourceSpan`/`downloadBundleAsJson` imports
   are dropped from the inspector page.
5. `format:check` + `lint` + `typecheck` + `build` green; pre-existing
   lint-warning count not increased; only the 2 named files changed.

## 8. Required output schema (§8.3.9)

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
