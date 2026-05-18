# Codex BRIEF review — I-rdy-008 / GH #504 slice 3: migrate inspector shell + summary to the AuditIR client

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

## 0.1 This is slice 3 of #504, Option A

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI") is sliced ~12
ways per the Codex arch-decision consult (`.codex/I-rdy-008/arch_decision_verdict.txt`,
verdict A: serve the faithful `AuditIR`, do NOT wholesale-mount the legacy
1400-line `polaris_graph/audit_ir/inspector_router.py`).

- **Slice 1 shipped** (PR #590): the v6 backend route
  `GET /api/inspector/runs/{run_id}` → `to_json_dict(load_audit_ir(artifact_dir))`,
  i.e. faithful `AuditIR` JSON. 404 unknown / 409 not-completed / 422 abort-or-error
  run or unloadable `artifact_dir`.
- **Slice 2 shipped** (PR #591): `web/lib/api.ts` gained 17 `AuditIr*` interfaces
  + `getAuditRun(runId): Promise<AuditIrRun>`.
- **This is slice 3: migrate the inspector page SHELL + SUMMARY tab** off
  `getBundle()`/`EvidenceContract` onto `getAuditRun()`/`AuditIrRun`.

**The consult's key_risk is binding:** "the inspector page should be split by
tabs/surfaces, not rewritten in one PR." Slice 3 migrates ONLY the shell
(status cards + run-header) and the Executive-summary tab. The other 5 tabs
(`SentencesTab`/`FramesTab`/`ContradictionsTab`/`PoolTab`/`ChartsTab`),
`EvidencePane`, `renderSentenceWithTokens`, and `evidenceById` stay on
`getBundle()`/`EvidenceContract` — those migrate in slices 4-7. #504 closes
when the last slice lands. Do NOT flag "the other 5 tabs still use getBundle()"
— that is intentional, deferred to later slices.

## 1. Grounded state

### 1.1 The file being changed — `web/app/inspector/[runId]/page.tsx` (805 lines)

- `InspectorPage` (lines 30-262): `getBundle(runId)` → `bundle: EvidenceContract`;
  6-tab nav (`summary`/`sentences`/`frames`/`contradictions`/`pool`/`charts`);
  `evidenceById` resolves `bundle.evidence_pool`; whole body gated on `bundle &&`.
- **Shell pieces** (the slice-3 target):
  - 3 status cards (lines 134-179): `bundle.pipeline_status`,
    `bundle.family_segregation_passed` + `bundle.generator_model` +
    `bundle.verifier_model`, `bundle.cost_usd`.
  - run-header section (lines 181-191): `bundle.question`, `bundle.template`,
    `bundle.queued_at`, `bundle.finished_at`.
  - "Export bundle JSON" button (lines 106-113): `downloadBundleAsJson(bundle)`.
- **`ExecutiveSummaryTab`** (lines 459-609, the slice-3 target): renders
  `bundle.template`/`bundle.question`; counts `verifiedCount` /`droppedCount`
  (from `bundle.verified_sentences`), `contradictionCount` (from
  `bundle.contradictions`), `tierCounts` (reduced over `bundle.evidence_pool`,
  shows T1/T2/T3 only); 3 `getChart()` charts (`forest_plot`/`comparison_table`/
  `timeline`).
- **NOT touched by slice 3:** `SentencesTab` (264), `renderSentenceWithTokens`
  (327), `FramesTab` (358), `ContradictionsTab` (392), `ChartsTab` (611),
  `PoolTab` (721), `EvidencePane` (751). All keep `EvidenceContract`/`SourceSpan`.

### 1.2 The data shapes

- `getAuditRun()` → `AuditIrRun` (api.ts:1381) — `manifest` (`AuditIrManifest`:
  `run_id`, `slug`, `status`, `question`, `cost_usd`, `budget_cap_usd`,
  `word_count`, `sentences_verified`, `sentences_dropped`,
  `contradictions_found`, `completeness_percent`, `release_allowed`, …);
  `model_provenance` (`AuditIrModelProvenance | null`: `generator_family`,
  `generator_model`, `evaluator_family`, `evaluator_model`, …); `protocol`
  (`AuditIrProtocolMetadata | null`: `created_at_iso`, `scope_decision`, …);
  `bibliography` (`AuditIrBibliographyEntry[]`, each with raw `tier: string`);
  `tier_mix` (`AuditIrTierMix`: `fractions: Record<string,number>`,
  `corpus_count`); `report_md: string`; etc.
- `getBundle()` → `EvidenceContract` (api.ts:266) — carries `template`,
  `queued_at`, `finished_at`, `pipeline_status`, `cost_usd`,
  `family_segregation_passed`, `generator_model`, `verifier_model`,
  `evidence_pool`, `verified_sentences`, `frame_coverage`, `contradictions`.

### 1.3 Field-availability gap (drives the §3 scope calls)

`AuditIR` is the **artifact** IR — it does NOT carry run-lifecycle fields.
`EvidenceContract.template`, `.queued_at`, `.finished_at` have **no AuditIR
equivalent** (they are `run_store` lifecycle columns, surfaced by the separate
`getRun()` → `RunStatusResponse` helper, api.ts:122). `AuditIR` carries
`manifest.slug`, `protocol.created_at_iso`, `protocol.scope_decision` instead.
There is also **no `family_segregation_passed` boolean** in `AuditIR` — the
two-family invariant must be derived.

## 2. The plan — `web/app/inspector/[runId]/page.tsx` only (1 file)

### 2.1 Dual-fetch during the staged migration

`InspectorPage` fetches **both** `getAuditRun()` → `ir: AuditIrRun | null`
**and** `getBundle()` → `bundle: EvidenceContract | null` (two independent
`useEffect` promises, each with the existing `cancelled` guard). The shell +
`ExecutiveSummaryTab` read `ir`; the 5 un-migrated tabs + `EvidencePane` +
`downloadBundleAsJson` + `evidenceById` keep reading `bundle`. The full
inspector body renders gated on `ir && bundle`. When slices 4-7 migrate the
last tab off `bundle`, the `getBundle()` call is removed.

### 2.2 Shell migration mapping

| UI element | was (`bundle`) | becomes (`ir`) |
|---|---|---|
| Pipeline status card | `bundle.pipeline_status` | `ir.manifest.status` |
| Two-family card PASS/FAIL | `bundle.family_segregation_passed` | derived: `ir.model_provenance != null && ir.model_provenance.generator_family !== ir.model_provenance.evaluator_family` |
| Two-family card models | `generator_model → verifier_model` | `ir.model_provenance.generator_model → ir.model_provenance.evaluator_model` |
| Cost card | `bundle.cost_usd` | `ir.manifest.cost_usd` |
| Run-header question | `bundle.question` | `ir.manifest.question` |
| Run-header sub-line | `Template: {template} · Queued {queued_at} · Finished {finished_at}` | `Run {ir.manifest.slug} · Scope {ir.protocol?.scope_decision} · Created {ir.protocol?.created_at_iso}` (see §3.1) |

If `ir.model_provenance` is `null` (loader returns `None` for legacy/abort
artifacts), the two-family card shows a neutral "model provenance not recorded"
state rather than a fabricated PASS/FAIL.

### 2.3 `ExecutiveSummaryTab` migration mapping

| UI element | was | becomes |
|---|---|---|
| heading | `bundle.template` | `ir.manifest.slug` |
| question | `bundle.question` | `ir.manifest.question` |
| Verified count | `bundle.verified_sentences.length` | `ir.manifest.sentences_verified` |
| Dropped count | `verified_sentences.filter(drop_reason)` | `ir.manifest.sentences_dropped` |
| Contradictions count | `bundle.contradictions.length` | `ir.manifest.contradictions_found` |
| Sources + tier mix | reduce `bundle.evidence_pool` (T1/T2/T3 only) | reduce `ir.bibliography` by raw `tier` → exact T1-T7 counts; total = `ir.bibliography.length` |
| 3 charts | `getChart(runId, t)` | UNCHANGED — `getChart` is a separate route |

The chart-click `onSelect(evidenceId)` still resolves through the
`bundle`-based `evidenceById` → `EvidencePane` — that chain migrates with the
pool tab in a later slice; it stays functional in the dual-fetch state.

### 2.4 Error / non-completed handling

`getAuditRun()` throws `ApiError` on 404 (unknown) / 409 (not completed) /
422 (abort/error run or unloadable artifact). The `.catch` sets `error` to the
thrown message; the existing error `<section role="alert">` renders it. This
means an **abort/error run shows an explicit failure panel** instead of the
old empty-tabs inspector — see §3.4.

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — drop `template`/`finished_at` from the run-header.** `AuditIR` has no
`template` name and no `finished_at`. The plan renders `slug` +
`scope_decision` + `created_at_iso` from `AuditIR` instead. Alternative: also
fetch `getRun()` for the lifecycle fields (a 3rd fetch). Recommend the
AuditIR-only path (single migration target, faithful — `slug`/`scope_decision`
are richer provenance than a bare template label; no UX element is silently
blanked, the line is replaced with named AuditIR fields). Rule: accept, or
require the `getRun()` compose?

**3.2 — `report_md` rendering.** The consult listed "render report_md" for
slice 3. There is **no markdown renderer in `web/`** (no `react-markdown`/
`marked`/`remark` dependency; verified against `web/package.json`). Plan:
render `ir.report_md` as raw monospace text inside a collapsible
`<details>`/`<pre>` block in the summary tab — zero new dependency, faithful
(shows the actual report bytes). Proper markdown rendering (adding
`react-markdown`) is deferred to a later polish slice. Rule: accept the raw
`<pre>` for slice 3, or defer `report_md` entirely to the markdown-renderer
slice?

**3.3 — two-family PASS/FAIL is derived, not stored.** `AuditIR` has no
`family_segregation_passed` boolean. Plan derives it from
`generator_family !== evaluator_family` (CLAUDE.md §9.1.1 — the invariant *is*
"generator and evaluator from different lineages"). Rule: is deriving from the
family strings acceptable, or is a stored boolean required?

**3.4 — abort/error runs lose the inspector page.** Slice-1's route 422s on
`pipeline_status` starting `abort_`/`error_`. Post-slice-3, an abort run hits
the `error` panel ("Bundle load failed" → will be relabeled "Run inspector
unavailable" + the 422 detail) instead of the old `getBundle()` empty-tabs
view. Recommend accepting this — an abort run showing an honest "run aborted:
<status>" message is more correct than empty tabs, and matches slice-1's
deliberate 422 design. Rule: accept, or require a `bundle`-fallback path?

**3.5 — dual-fetch is the intended transition state.** The page issues two
fetches and the body gates on `ir && bundle`. This is the consult's
"split by surface" pattern, not an oversight. Confirm acceptable.

## 4. Scope boundary

- **IN:** `web/app/inspector/[runId]/page.tsx` — `InspectorPage` shell
  (3 status cards + run-header) + `ExecutiveSummaryTab` migrate to
  `getAuditRun()`/`AuditIrRun`; add the `getAuditRun()` fetch; relabel the
  error panel.
- **OUT:** `SentencesTab`/`FramesTab`/`ContradictionsTab`/`ChartsTab`/`PoolTab`/
  `EvidencePane`/`renderSentenceWithTokens`/`evidenceById` (slices 4-7);
  `web/lib/api.ts` (slice 2 already shipped the client — no change); any `src/`
  change; `web/app/runs/[runId]/page.tsx` (separate page, also uses
  `getBundle()` — not in #504 slice 3 scope).

## 5. Smoke test

Frontend-only change → the `lint + format + typecheck + build` CI job is IN
SCOPE and must pass. Offline: `cd web && npm run format:check && npm run lint
&& npm run typecheck && npm run build` — all green. No new unit test (a
data-source swap in a client component with no new logic branches; consistent
with how the inspector page itself was added). If `npm run typecheck` flags
the `AuditIrRun` field access, fix before commit. The 3 pre-existing
`inspector/[runId]/page.tsx` lint warnings noted in slice 2 — verify the count
does not increase.

## 6. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `getAuditRun()` + the 17 `AuditIr*` interfaces (slice 2,
  PR #591); `getBundle()`/`EvidenceContract`/`getChart()` all still present;
  NOT modified by slice 3.
- `src/polaris_v6/api/inspector.py` (slice 1) — the route `getAuditRun()`
  targets; NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — the dataclass tree the `AuditIr*`
  types mirror (cross-checked: `AuditIrManifest`/`ModelProvenance`/
  `ProtocolMetadata`/`BibliographyEntry`/`TierMix` field names + types match);
  NOT modified.
- `web/app/runs/[runId]/page.tsx` — also calls `getBundle()`; a separate page,
  NOT in #504 slice 3 scope; NOT modified.
- `web/components/ui/evidence-tooltip.tsx`, `vega-chart.tsx` — consumed by the
  un-migrated tabs; NOT modified.

## 7. Acceptance criteria for THIS PR (slice 3)

1. `InspectorPage` fetches `getAuditRun()`; the 3 status cards + run-header +
   `ExecutiveSummaryTab` render from `AuditIrRun` per the §2.2/§2.3 mappings.
2. The 5 un-migrated tabs + `EvidencePane` continue to render from
   `getBundle()`/`EvidenceContract` unchanged (dual-fetch transition state).
3. `ir.model_provenance == null` is handled (neutral two-family state, no
   fabricated PASS/FAIL).
4. `npm run format:check` + `lint` + `typecheck` + `build` all green; no
   increase in pre-existing lint-warning count.
5. No `web/lib/api.ts` / `src/` change; no other `web/app/**` file changed.

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
