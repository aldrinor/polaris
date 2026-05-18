# Codex DIFF review — I-rdy-008 / GH #504 slice 4: migrate the verified-sentences tab to AuditIR

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 4** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1, 2 P2
baked in). **2 files: `web/app/inspector/[runId]/page.tsx` +
`web/components/ui/evidence-tooltip.tsx`.**

Slice 4 of ~12 for #504 (Option A). Migrates the inspector page
**verified-sentences tab** (`SentencesTab` + `renderSentenceWithTokens`) off
`getBundle()`/`EvidenceContract`/`SourceSpan` onto the AuditIR
`verified_report.sections[].sentences[]` + `AuditIrBibliographyEntry`. The 4
other tabs (`FramesTab`/`ContradictionsTab`/`ChartsTab`/`PoolTab`) +
`EvidencePane` stay on `getBundle()` — slices 5-7. Do NOT flag "the other
tabs still use getBundle()" — deliberate, per the consult's split-by-surface
plan.

## 2. The change

- `SentencesTab` — new props `{ ir, bundle, onSelect, onJumpToContradictions }`;
  flattens `ir.verified_report.sections.flatMap(sec => sec.sentences)`; per
  card: `s.section`, `s.is_verified` badge, `s.failure_reasons[]` list, body
  via `renderSentenceWithTokens`; bibliography resolver `bibById` from
  `ir.bibliography`.
- `renderSentenceWithTokens` — 3rd param now `bibById: (id) =>
  AuditIrBibliographyEntry | null`; `EvidenceTooltip` gets `sourceUrl` ←
  `bib?.url`, `spanText` ← `bib?.statement`, `sourceTier` ← `bib?.tier`. The
  `[#ev:...]` regex is unchanged.
- New `slugifySection` — mirrors the backend `_slugify`
  (`artifact_to_slice_chain.py`).
- `tabs` initializer guard `bundle ?` → `ir && bundle ?`; `sentences` count
  from `ir.verified_report`.
- `evidence-tooltip.tsx` — `sourceTier` type `"T1"|"T2"|"T3"` → `string`.

## 3. Verify

1. **AuditIR field access faithful.** `ir.verified_report.sections[].sentences[]`
   (`AuditIrSentence`: `claim_id`, `section`, `text`, `tokens`, `is_verified`,
   `failure_reasons`), `ir.bibliography` (`AuditIrBibliographyEntry`:
   `evidence_id`, `url`, `tier`, `statement`), `ir.verified_report.sentences_
   verified/_dropped`, `ir.manifest.status` — cross-check against
   `web/lib/api.ts` (slice 2) + `src/polaris_graph/audit_ir/loader.py`.
2. **The 2 brief P2s.** (P2-1) the `tabs` initializer is gated `ir && bundle`
   so the `ir.verified_report.*` count never null-derefs. (P2-2)
   `slugifySection` exactly mirrors `_slugify`
   (`re.sub(r"[^a-z0-9_]+","_",lower).strip("_")[:60]`) — the contradiction
   badge compares `slugifySection(s.section)` against the bundle's
   already-slugified `contradictions[].section_id`.
3. **Regex still correct.** `renderSentenceWithTokens` runs the unchanged
   `/\[#ev:([^:\]]+):\d+-\d+\]/g` over `AuditIrSentence.text` (inline markers
   confirmed present in `verification_details.json`).
4. **No fabrication.** `failure_reasons` rendered only when non-empty;
   `bibById` returns `null` when an `evidence_id` is absent → tooltip
   `sourceUrl`/`spanText`/`sourceTier` become `undefined` (all optional props).
5. **The 4 un-migrated tabs + `EvidencePane`** are byte-identical to
   `polaris` HEAD; `evidenceById` + the `onSelect`→`EvidencePane` click chain
   stay bundle-backed.
6. **`sourceTier` widening** — `string` is a safe supertype; display-only
   prop; both `EvidenceTooltip` call sites still valid.
7. **Scope** — only the 2 named files; no `web/lib/api.ts`, no `src/`.

## 4. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `AuditIrSentence`/`AuditIrSection`/`AuditIrVerifiedReport`/
  `AuditIrBibliographyEntry` (slice 2); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `_parse_verification_sentence`
  (`text=raw["sentence"]` retains `[#ev]` markers; `is_verified=
  (status=="kept")`); NOT modified.
- `src/polaris_v6/api/artifact_to_slice_chain.py` — `_slugify` (the function
  `slugifySection` mirrors); NOT modified.
- `web/app/sentence_hover_test/_demo_evidence_tooltip.tsx` — the other
  `EvidenceTooltip` call site (`sourceTier="T1"`, valid vs `string`); NOT
  modified.

## 5. Smoke state

`web/`: `prettier --write` the 2 files → applied; `npm run lint` → 0 errors
(3 pre-existing warnings, count unchanged — `chartTypes` `exhaustive-deps` in
the inspector page is pre-existing in `ExecutiveSummaryTab`); `npm run
typecheck` → clean; `npm run build` → OK. The `lint + format + typecheck +
build` CI job is in scope for this web/ PR.

## 6. Required output schema (§8.3.9)

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
