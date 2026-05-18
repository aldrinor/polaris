# Claude architect audit — I-rdy-008 (#504) slice 4

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 4 of ~12** (Codex arch-decision consult, verdict A). Slices 1-3 merged
(PR #590/#591/#592). #504 closes when the last slice lands.
**Branch:** `bot/I-rdy-008-slice4` off `polaris` HEAD `99801be2`.
**Commit 1:** `ae11b9c0` — `web/app/inspector/[runId]/page.tsx` +
`web/components/ui/evidence-tooltip.tsx`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; all 6 scope calls accepted; 2 P2 baked into commit 1).

## 1. What shipped

The inspector page **verified-sentences tab** (`SentencesTab` +
`renderSentenceWithTokens`) migrates off `getBundle()`/`EvidenceContract`/
`SourceSpan` onto the faithful AuditIR `verified_report.sections[].sentences[]`
(`AuditIrSentence`) + `AuditIrBibliographyEntry`.

- `SentencesTab` takes `ir`: flattens `ir.verified_report.sections.flatMap(
  sec => sec.sentences)`; per card renders `s.section` (title),
  `s.is_verified` (`verified✓`/`verified✗`), `s.failure_reasons[]` (list);
  body via `renderSentenceWithTokens`.
- `renderSentenceWithTokens` resolver migrated to `ir.bibliography`
  (`url` / `tier` / `statement`); the `[#ev:...]` regex unchanged.
- New `slugifySection` mirrors the backend `_slugify` for the bundle-backed
  contradiction-in-section cross-link.
- `EvidenceTooltip.sourceTier` widened `"T1"|"T2"|"T3"` → `string`.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — nested→flat (§3.1).** `ir.verified_report.sections.flatMap(
  (sec) => sec.sentences)`; the empty-state check is on the flattened
  length; each card carries `s.section`. Key is `s.claim_id` (loader:
  `f"{section}:{status}:{idx}"` — unique).
- **VERIFIED — single `is_verified` (§3.2).** Card header shows
  `verified✓`/`verified✗`; the legacy local/global split is gone (AuditIR
  does not carry it).
- **VERIFIED — `failure_reasons[]` (§3.3).** Rendered as a `<ul>` of
  `Dropped: <reason>` lines when `s.failure_reasons.length > 0` (the AuditIR
  list replaces the single `drop_reason` string).
- **VERIFIED — P2-1 (tab-count guard).** The `tabs` initializer guard is
  now `ir && bundle ?` (was `bundle ?`); the `sentences` count
  `ir.verified_report.sentences_verified + ir.verified_report.sentences_dropped`
  is only evaluated when `ir` is non-null. No null-deref.
- **VERIFIED — P2-2 (section-id identifier match).** `slugifySection`
  replicates the backend `_slugify`
  (`re.sub(r"[^a-z0-9_]+","_",text.lower()).strip("_")[:60]` →
  `.toLowerCase().replace(/[^a-z0-9_]+/g,"_").replace(/^_+|_+$/g,"").slice(0,60)`).
  The contradiction badge matches `slugifySection(s.section)` against
  `bundle.contradictions[].section_id` — verified the bundle assigns
  `section_id=_slugify(air_sent.section)` (`artifact_to_slice_chain.py:348`),
  the same identifier space.
- **VERIFIED — contradiction badge bundle-backed (§3.4).** AuditIR
  `AuditIrContradictionCluster` has no `section` field; the badge keeps
  reading `bundle.contradictions` during the dual-fetch transition. No UX
  regression. Slice 6 decides the permanent linkage.
- **VERIFIED — token resolver (§3.5).** Confirmed against a real
  `verification_details.json` that `AuditIrSentence.text` retains inline
  `[#ev:<id>:<start>-<end>]` markers — the regex carries over; only the
  per-token resolver changed from the bundle `SourceSpan` pool to
  `ir.bibliography` (`bib?.url` / `bib?.statement` / `bib?.tier`). Token
  CLICK still flows through `onSelect` → the bundle-backed `EvidencePane`
  (migrates with the pool surface).
- **VERIFIED — `sourceTier` widening (§3.6).** `EvidenceTooltip.sourceTier`
  is display-only (`{sourceTier && \` · tier ${sourceTier}\`}`); widening
  to `string` is safe for both call sites (the inspector page + the
  `_demo_evidence_tooltip.tsx` harness passing `"T1"`).
- **VERIFIED — scope.** Only `web/app/inspector/[runId]/page.tsx` +
  `web/components/ui/evidence-tooltip.tsx` changed; no `web/lib/api.ts`, no
  `src/`. The 4 un-migrated tabs + `EvidencePane` are untouched.

## 3. Smoke

`web/`: `prettier --write` the 2 files → applied; `npm run lint` → 0 errors
(3 repo-wide warnings, all pre-existing — `chartTypes` `exhaustive-deps` in
the inspector page's `ExecutiveSummaryTab`, + `benchmark_board.tsx` +
`frame_coverage_panel.spec.ts` — count NOT increased); `npm run typecheck`
→ clean; `npm run build` → OK.

## 4. Codex iteration trail

- **Brief iter 1 APPROVE** — 0 P0/P1; all 6 §3 scope calls ruled accept;
  2 P2 (tab-count guard, section-id slug normalization) — both implemented.

## 5. Scope + residuals

Slice 4 = the verified-sentences tab. Remaining per the consult: slice 5
frame coverage, slice 6 contradictions, slice 7 pool + `EvidencePane`,
slices 8-12 charts / compare / follow-up / pin replay / memory / bundle UX.
The `getBundle()` call is removed when the last tab migrates. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief; the verified-sentences tab reads the
AuditIR `verified_report` 1:1; both Codex P2s implemented; the contradiction
cross-link's identifier match is verified against the backend `_slugify`;
the 4 un-migrated tabs + `EvidencePane` untouched (the consult's
split-by-surface discipline); web smoke (prettier/lint/typecheck/build) all
green. Ready for Codex diff review.
