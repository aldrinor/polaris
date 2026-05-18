# Codex BRIEF review — I-rdy-008 / GH #504 slice 4: migrate the verified-sentences tab + citation hover to AuditIR

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

## 0.1 This is slice 4 of #504, Option A

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI") is sliced
~12 ways per the Codex arch-decision consult (`.codex/I-rdy-008/arch_decision_verdict.txt`,
verdict A: serve the faithful `AuditIR`; do NOT wholesale-mount the legacy
1400-line `polaris_graph/audit_ir/inspector_router.py`).

- **Slices 1-3 shipped**: route `GET /api/inspector/runs/{run_id}` (PR #590);
  `web/lib/api.ts` `AuditIr*` types + `getAuditRun()` (PR #591); inspector
  page **shell + Executive-summary tab** migrated to `getAuditRun()`/
  `AuditIrRun` (PR #592).
- **This is slice 4: migrate the verified-sentences tab** — `SentencesTab`
  + `renderSentenceWithTokens` in `web/app/inspector/[runId]/page.tsx` — off
  `getBundle()`/`EvidenceContract`/`SourceSpan` onto the AuditIR
  `verified_report.sections[].sentences[]` (`AuditIrSentence`) +
  `AuditIrEvidenceSpanToken` + `AuditIrBibliographyEntry`.

**Consult key_risk (binding):** "split by tabs/surfaces, not rewritten in one
PR." Slice 4 touches ONLY `SentencesTab` + `renderSentenceWithTokens` (+ one
1-line type widening — §3.6). `FramesTab` / `ContradictionsTab` / `ChartsTab`
/ `PoolTab` / `EvidencePane` stay on `getBundle()`/`EvidenceContract` —
slices 5-7. Do NOT flag "the other tabs still use getBundle()" — deliberate.

## 1. Grounded state

### 1.1 The file — `web/app/inspector/[runId]/page.tsx` (920 lines, post-slice-3)

- `InspectorPage` dual-fetches `getAuditRun()`→`ir` + `getBundle()`→`bundle`;
  body gates on `ir && bundle`. Slice-4 target call site is line 227-234:
  `<SentencesTab bundle={bundle} evidenceById={evidenceById}
  onSelect={(id) => setSelectedEvidence(evidenceById(id))}
  onJumpToContradictions={() => setActiveTab("contradictions")} />`.
- `SentencesTab` (line 353) — `{ bundle, evidenceById, onSelect,
  onJumpToContradictions }`. Iterates the flat `bundle.verified_sentences`;
  per card: `s.section_id`, `s.verifier_local_pass`/`s.verifier_global_pass`
  ("local✓/✗ · global✓/✗"), `renderSentenceWithTokens(s.sentence_text, …)`,
  `s.drop_reason`; "contradiction in section →" badge from a
  `Set(bundle.contradictions.map(c => c.section_id))`.
- `renderSentenceWithTokens` (line 416) — `(text, onSelect, evidenceById?)`;
  regex `/\[#ev:([^:\]]+):\d+-\d+\]/g` over `text`, per match emits an
  `<EvidenceTooltip>` with `sourceUrl`/`spanText`/`sourceTier` from
  `evidenceById(id): SourceSpan | null`.
- `tabs` array (`InspectorPage`) — the `sentences` tab count is
  `bundle.verified_sentences.length`.

### 1.2 The AuditIR shapes (slice-2 `web/lib/api.ts`, verified vs `loader.py`)

- `AuditIrRun.verified_report` (`AuditIrVerifiedReport`): `sections`
  (`AuditIrSection[]`), `sentences_verified`, `sentences_dropped`,
  `drop_reason_counts`.
- `AuditIrSection`: `title`, `kept_count`, `dropped_count`, `total_in`,
  `dropped_due_to_failure`, `sentences` (`AuditIrSentence[]`).
- `AuditIrSentence`: `claim_id`, `section`, `text`, `tokens`
  (`AuditIrEvidenceSpanToken[]`), `is_verified` (bool), `failure_reasons`
  (`string[]`).
- `AuditIrBibliographyEntry`: `num`, `evidence_id`, `statement`, `tier`
  (raw `string`), `url`.

**Grounding done — confirmed against a real `verification_details.json`
(`outputs/carney_demo_rehearsal_smoke/clinical/clinical_tirzepatide_t2dm/`):**
the per-sentence `text` field STILL CONTAINS inline `[#ev:<id>:<start>-<end>]`
markers (`'[#ev:' in text` → True), so `renderSentenceWithTokens`'s regex
approach carries over unchanged — only the per-token *resolver* changes.
`failure_reasons` is a list of strings (e.g.
`"number_not_in_any_cited_span:ev_005:missing=[…]"`); empty/`None` for kept
sentences (loader: `is_verified=(status=="kept")`).

## 2. The plan — 2 files

### 2.1 `web/app/inspector/[runId]/page.tsx`

**`SentencesTab`** — new props `{ ir: AuditIrRun; bundle: EvidenceContract;
onSelect; onJumpToContradictions }`:
- Flatten `ir.verified_report.sections.flatMap(s => s.sentences)` into the
  rendered list (preserves the current flat-list UX; each card keeps a
  section label, now `sentence.section`). Empty-state check on the flattened
  length.
- Per card: section label `s.section`; verification badge `s.is_verified ?
  "verified✓" : "verified✗"`; body `renderSentenceWithTokens(s.text, …)`;
  when `s.failure_reasons.length > 0`, render them (the AuditIR replacement
  for the single `drop_reason` string — see §3.3).
- "contradiction in section →" badge: keep reading
  `Set(bundle.contradictions.map(c => c.section_id))` — AuditIR contradiction
  clusters carry NO section field (§3.4).
- Build a bibliography resolver `bibById = (id) =>
  ir.bibliography.find(b => b.evidence_id === id) ?? null` and pass it to
  `renderSentenceWithTokens`.

**`renderSentenceWithTokens`** — signature `(text, onSelect, bibById?)`
where `bibById: (id) => AuditIrBibliographyEntry | null`:
- Same regex over `text` (markers confirmed present).
- Per match: `<EvidenceTooltip>` with `sourceUrl={bib?.url}`,
  `spanText={bib?.statement}`, `sourceTier={bib?.tier}`,
  `onClickToInspect={() => onSelect(evidenceId)}` (§3.5).

**`InspectorPage`** — the call site passes `ir={ir} bundle={bundle}` (drop
the `evidenceById` prop — `SentencesTab` builds its own `bibById`); `onSelect`
unchanged (still `setSelectedEvidence(evidenceById(id))` — `EvidencePane`
stays bundle-backed, §3.5). The `sentences` tab count becomes
`ir.verified_report.sentences_verified + ir.verified_report.sentences_dropped`.

### 2.2 `web/components/ui/evidence-tooltip.tsx` — 1-line type widening (§3.6)

Widen `EvidenceTooltipProps.sourceTier` from `"T1" | "T2" | "T3"` to
`string`. `sourceTier` is display-only (line 164: `{sourceTier && \` · tier
${sourceTier}\`}`); both call sites (the inspector page + the
`_demo_evidence_tooltip.tsx` harness passing `"T1"`) remain valid against
`string`. No runtime behavior change.

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — nested → flat.** AuditIR `verified_report` is nested
`sections[].sentences[]`; the legacy `bundle.verified_sentences` is flat.
Plan flattens via `flatMap` and keeps the per-card `section` label (current
UX preserved). Alternative: render section-grouped (bigger change). Recommend
flatten. Rule.

**3.2 — no local/global verifier split.** `AuditIrSentence` has a single
`is_verified` bool, not `verifier_local_pass`/`verifier_global_pass`. Plan:
the card header shows `verified✓`/`verified✗`. The local/global distinction
is dropped (AuditIR does not carry it). Rule: accept?

**3.3 — `drop_reason` (string) → `failure_reasons` (string[]).** The legacy
card showed a single `Dropped: <drop_reason>` line. `AuditIrSentence` has
`failure_reasons: string[]`. Plan: render the list (e.g. each reason on its
own line under the sentence when non-empty). Rule: accept?

**3.4 — contradiction-in-section badge stays bundle-backed.** AuditIR
`AuditIrContradictionCluster` has NO `section`/`section_id` field — the
"contradiction in section →" cross-link cannot be derived from AuditIR.
Plan: `SentencesTab` keeps reading `bundle.contradictions` for the
section-set during the dual-fetch transition (no UX regression). Slice 6
(contradictions migration) decides the permanent linkage (evidence-id-based,
or drop). Alternative: drop the badge now. Recommend keep-via-bundle. Rule.

**3.5 — token click + hover during the transition.** The token CLICK still
calls `onSelect(evidenceId)` → `InspectorPage` resolves via the bundle
`evidenceById` → `EvidencePane` (bundle-backed; migrates with the pool
surface in a later slice). The token HOVER tooltip resolves via
`ir.bibliography`: `sourceUrl` ← `entry.url`, `sourceTier` ← `entry.tier`,
`spanText` ← `entry.statement`. **AuditIR has no flat `evidence_pool` with
the exact ≤500-char cited span** — `bibliography.statement` is the closest
faithful AuditIR field for the hover preview; the exact span text is still
shown on click via the (bundle-backed) `EvidencePane`. Rule: accept
`statement` as the hover preview text, or omit `spanText` until the pool
surface migrates?

**3.6 — one out-of-page-file change: widen `EvidenceTooltip.sourceTier`.**
AuditIR tiers are raw `string` (T1-T7); the prop is typed `"T1"|"T2"|"T3"`.
The 1-line widening to `string` is the minimal faithful fix (display-only
prop, safe for both call sites). Alternative: cast/omit T4-T7 tiers in the
page file only (a faithfulness loss). Recommend the widening. Rule: accept
touching `evidence-tooltip.tsx`?

## 4. Scope boundary

- **IN:** `web/app/inspector/[runId]/page.tsx` (`SentencesTab` +
  `renderSentenceWithTokens` + their call site + the `sentences` tab count);
  `web/components/ui/evidence-tooltip.tsx` (1-line `sourceTier` widening).
- **OUT:** `RunShell` / `ExecutiveSummaryTab` (slice 3, done); `FramesTab` /
  `ContradictionsTab` / `ChartsTab` / `PoolTab` / `EvidencePane` (slices
  5-7); `web/lib/api.ts` (slice 2 shipped the types — no change); any `src/`
  change; the `getBundle()` fetch (removed only when the last tab migrates).

## 5. Smoke test

Frontend change → the `lint + format + typecheck + build` CI job is IN
SCOPE. Offline: `cd web && npx prettier --write` the 2 files
`&& npm run format:check && npm run lint && npm run typecheck && npm run
build` — all green. No new unit test (a data-source swap in a client
component, no new logic branches — consistent with slices 1-3). The 1
pre-existing inspector-page lint warning (`chartTypes` `exhaustive-deps` in
`ExecutiveSummaryTab`) must not increase.

## 6. Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` — `_parse_verification_sentence` /
  `_parse_verified_report`: `ReportSentence.text = raw["sentence"]` (inline
  `[#ev]` markers retained), `is_verified=(status=="kept")`,
  `failure_reasons` from raw. NOT modified.
- `web/lib/api.ts` — `AuditIrVerifiedReport`/`AuditIrSection`/`AuditIrSentence`/
  `AuditIrEvidenceSpanToken`/`AuditIrBibliographyEntry` (slice 2); NOT modified.
- `web/components/ui/evidence-tooltip.tsx` — only `sourceTier` is touched
  (1-line type); `sourceTier` is display-only (line 164).
- `web/app/sentence_hover_test/_demo_evidence_tooltip.tsx` — the other
  `EvidenceTooltip` call site; passes `sourceTier="T1"` (valid vs `string`);
  NOT modified.
- `EvidencePane` / `PoolTab` / `evidenceById` — stay bundle-backed; NOT
  modified.

## 7. Acceptance criteria for THIS PR (slice 4)

1. `SentencesTab` renders `ir.verified_report.sections[].sentences[]`
   (flattened) — section label, `is_verified` badge, `failure_reasons`;
   `renderSentenceWithTokens` resolves token hover data via `ir.bibliography`.
2. The contradiction-in-section badge + `onSelect`→`EvidencePane` click chain
   stay bundle-backed (dual-fetch transition); no UX regression.
3. `EvidenceTooltip.sourceTier` widened to `string`; renders raw AuditIR
   T1-T7 tiers.
4. `format:check` + `lint` + `typecheck` + `build` green; pre-existing
   lint-warning count not increased.
5. No change outside the 2 named files; no `web/lib/api.ts` / `src/` change.

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
