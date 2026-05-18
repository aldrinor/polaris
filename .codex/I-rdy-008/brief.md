# Codex BRIEF review — I-rdy-008 / GH #504 slice 6: migrate the contradictions tab to AuditIR

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

## 0.1 This is slice 6 of #504, Option A

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI") is sliced
~12 ways per the Codex arch-decision consult (verdict A: serve the faithful
`AuditIR`; do NOT wholesale-mount the legacy 1400-line `inspector_router.py`).

- **Slices 1-5 shipped**: v6 route (PR #590); `AuditIr*` types +
  `getAuditRun()` (PR #591); shell + Executive-summary tab (PR #592);
  verified-sentences tab (PR #593); frame-coverage tab (PR #594).
- **This is slice 6: migrate the contradictions tab** — `ContradictionsTab`
  in `web/app/inspector/[runId]/page.tsx` — off `getBundle()`/
  `EvidenceContract` onto the AuditIR `contradictions`
  (`AuditIrContradictionCluster` → `AuditIrContradictionClaim`).

**Consult key_risk (binding):** "split by tabs/surfaces, not rewritten in one
PR." Slice 6 touches ONLY `ContradictionsTab` (+ its call site + the
`contradictions` tab count). `ChartsTab` / `PoolTab` / `EvidencePane` stay on
`getBundle()` — slices 7+. Do NOT flag "the other tabs still use
getBundle()" — deliberate.

## 1. Grounded state

### 1.1 The current `ContradictionsTab` (`web/app/inspector/[runId]/page.tsx:617`)

`ContradictionsTab({ bundle, onSelect })` — iterates `bundle.contradictions`
(`{ contradiction_id, section_id, claim_a, claim_b, evidence_a[],
evidence_b[], resolution }[]` — a **2-sided A/B** shape); per item a Card with
a `contradiction_id · section_id · resolution` header and a 2-column grid
(column A = `claim_a` + `evidence_a[]` clickable id buttons; column B =
`claim_b` + `evidence_b[]`). Each id button → `onSelect(id)`. Call site
`page.tsx:242-247` — `<ContradictionsTab bundle={bundle} onSelect={(id) =>
setSelectedEvidence(evidenceById(id))} />`. The `contradictions` tab count
(`page.tsx:147`) is `bundle.contradictions.length`.

### 1.2 The AuditIR shape (slice-2 `web/lib/api.ts`, verified vs `loader.py`
+ a real `contradictions.json`)

`AuditIrRun.contradictions` is `AuditIrContradictionCluster[]` — **an N-claim
cluster, NOT a 2-sided A/B**:
- `AuditIrContradictionCluster`: `cluster_id` (loader-assigned enumerate
  index — `_parse_contradictions` line 569), `subject`, `predicate`,
  `severity` (string, loader default `"unknown"`), `absolute_difference`
  (number), `relative_difference` (number), `recommended_action` (string),
  `claims` (`AuditIrContradictionClaim[]`, loader requires ≥2).
- `AuditIrContradictionClaim`: `evidence_id`, `subject`, `predicate`, `arm`,
  `dose`, `value` (number), `unit`, `source_tier`, `source_url`,
  `context_snippet`, `endpoint_phrase`.

**Grounding done** — a real `contradictions.json`
(`outputs/carney_demo_rehearsal_smoke/clinical/clinical_tirzepatide_t2dm/`):
the file is a list of 4 clusters; cluster keys `subject`/`predicate`/
`severity`/`absolute_difference`/`relative_difference`/`recommended_action`/
`claims` (NO `cluster_id` in the raw JSON — the loader assigns it from the
list index); claim keys `evidence_id`/`subject`/`predicate`/`arm`/`dose`/
`value`/`unit`/`source_tier`/`source_url`/`context_snippet`/`endpoint_phrase`;
`severity` value seen: `"high"`.

## 2. The plan — `web/app/inspector/[runId]/page.tsx` only (1 file)

`ContradictionsTab` — new props `{ ir: AuditIrRun; onSelect: (id: string) =>
void }` (drop `bundle`):
- Empty-state: `ir.contradictions.length === 0` → "No contradictions
  detected."
- Per **cluster** Card (`key = cluster.cluster_id`):
  - Header: `subject` — `predicate` (CardTitle); a `severity` badge
    (color-coded high→red / moderate→amber / else→neutral) + the diff
    (`absolute_difference` / `relative_difference`) in the CardDescription.
  - `recommended_action` line under the header.
  - **Claims list** — each `AuditIrContradictionClaim` a row: `arm`/`dose`
    label, the numeric disagreement `value` `unit`, `endpoint_phrase`,
    `source_tier`, `context_snippet`, an `evidence_id` clickable button →
    `onSelect(evidence_id)`, and a `source_url` link.
- New `contradictionSeverityClass(severity)` — heuristic color.
- Call site `page.tsx:243` → `<ContradictionsTab ir={ir} onSelect={...} />`.
- `contradictions` tab count → `ir.contradictions.length`.

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — 2-sided A/B → N-claim cluster.** The legacy `claim_a`/`claim_b`
two-column grid is a 2-sided shape; an AuditIR cluster has `claims[]` (N≥2).
Plan renders the cluster as a header + an N-row claims list (one row per
`AuditIrContradictionClaim`). Rule: accept the N-claim list re-design?

**3.2 — no `section_id` / `contradiction_id` / `resolution` on the AuditIR
cluster.** The legacy per-card header `contradiction_id · section_id ·
resolution` has no AuditIR equivalent. Plan: the header becomes `subject` —
`predicate` + `severity`; `cluster_id` (the loader-assigned index) is the
React key only (not displayed as a label). Rule: accept?

**3.3 — `resolution` → `recommended_action`.** The legacy `resolution`
string maps to the AuditIR cluster's `recommended_action` (the closest
faithful field). Rule: accept?

**3.4 — `onSelect` token-click stays bundle-backed.** Each claim's
`evidence_id` is a clickable button → `onSelect(evidence_id)` → the
`InspectorPage` closure resolves it via the bundle `evidenceById` →
`EvidencePane` (bundle-backed; migrates with the pool surface in a later
slice). The click chain stays functional in the dual-fetch state. Confirm
acceptable.

**3.5 — new affordances.** AuditIR adds `severity`, `absolute_difference`,
`relative_difference`, `recommended_action`, and per-claim `value`/`unit`/
`arm`/`dose`/`endpoint_phrase`/`context_snippet`/`source_tier`/`source_url`.
Plan renders all of them (the numeric disagreement is the core audit value).
Rule: accept rendering the full claim detail, or trim any field?

**3.6 — the SentencesTab contradiction-in-section badge is unaffected.**
Slice 4's `SentencesTab` reads `bundle.contradictions[].section_id` for the
"contradiction in section →" badge. That cross-link stays bundle-backed and
is NOT touched by slice 6 (only `ContradictionsTab`'s own rendering
migrates). Confirm this is correct / no action needed.

## 4. Scope boundary

- **IN:** `web/app/inspector/[runId]/page.tsx` — `ContradictionsTab`
  migrates to `getAuditRun()`/`AuditIrRun`; its call site; the
  `contradictions` tab count.
- **OUT:** `SentencesTab` (slice 4) / `FramesTab` (slice 5) / `ChartsTab` /
  `PoolTab` / `EvidencePane` (slices 7+); `web/lib/api.ts` (slice 2 shipped
  the types — no change); `web/components/ui/**`; any `src/` change; the
  `getBundle()` fetch (removed when the last tab migrates); the SentencesTab
  contradiction badge (§3.6 — stays bundle-backed).

## 5. Smoke test

Frontend change → the `lint + format + typecheck + build` CI job is IN
SCOPE. Offline: `cd web && npx prettier --write app/inspector/[runId]/page.tsx
&& npm run format:check && npm run lint && npm run typecheck && npm run
build` — all green. No new unit test (a data-source swap in a client
component, no new logic branches — consistent with slices 1-5). The 1
pre-existing inspector-page lint warning (`chartTypes` `exhaustive-deps` in
`ExecutiveSummaryTab`) must not increase.

## 6. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `AuditIrContradictionCluster`/`AuditIrContradictionClaim`
  (slice 2); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `_parse_contradictions` /
  `_parse_contradiction_claim` (`cluster_id=idx`; `claims` requires ≥2;
  `severity` default `"unknown"`); NOT modified.
- `SentencesTab` — its `bundle.contradictions[].section_id` badge is
  independent of `ContradictionsTab`'s data source; NOT modified.
- `FramesTab` (slice 5) / `ChartsTab` / `PoolTab` / `EvidencePane` —
  untouched.

## 7. Acceptance criteria for THIS PR (slice 6)

1. `ContradictionsTab` renders `ir.contradictions` — per-cluster header
   (`subject`/`predicate`/`severity` badge/diff/`recommended_action`) + an
   N-row claims list (`arm`/`dose`, `value` `unit`, `endpoint_phrase`,
   `source_tier`, `context_snippet`, `evidence_id` click button, `source_url`).
2. The call site passes `ir`; the `contradictions` tab count reads
   `ir.contradictions.length`.
3. `onSelect`→`EvidencePane` click chain stays bundle-backed (dual-fetch).
4. `format:check` + `lint` + `typecheck` + `build` green; pre-existing
   lint-warning count not increased.
5. Only `web/app/inspector/[runId]/page.tsx` changed; no `web/lib/api.ts` /
   `src/` change; `SentencesTab`/`FramesTab`/`ChartsTab`/`PoolTab`/
   `EvidencePane` untouched.

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
