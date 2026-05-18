# Claude architect audit — I-rdy-008 (#504) slice 3

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 3 of ~12** (Codex arch-decision consult, verdict A). Slices 1 (v6
backend route, PR #590) + 2 (frontend AuditIR client, PR #591) merged. #504
closes when the last slice lands.
**Branch:** `bot/I-rdy-008-slice3` off `polaris` HEAD `85bd4bdb`.
**Commit 1:** `f402d29e` — canonical diff `1 file changed, +192 / -77`
(`web/app/inspector/[runId]/page.tsx`, 805 → 920 lines).
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; 3 P2 refinements baked into the diff).

## 1. What shipped

`web/app/inspector/[runId]/page.tsx` — the inspector page **shell** and
**Executive-summary tab** migrate off `getBundle()`/`EvidenceContract` onto
`getAuditRun()`/`AuditIrRun` (the faithful AuditIR). The 5 other tabs +
`EvidencePane` are byte-unchanged — they migrate in slices 4-7.

- **`InspectorPage`** dual-fetches `getAuditRun()` → `ir` and `getBundle()` →
  `bundle` in one `useEffect` (single `cancelled` guard). The full body gates
  on `ir && bundle`.
- **`RunShell`** (new) — 3 status cards + run-header from `ir`:
  pipeline-status `ir.manifest.status`; two-family invariant derived from
  `ir.model_provenance`; cost `ir.manifest.cost_usd`; run-header `question` +
  AuditIR-native `slug`/`scope_decision`/`created_at_iso`.
- **`ExecutiveSummaryTab`** — counts from `ir.manifest`
  (`sentences_verified`/`sentences_dropped`/`contradictions_found`); tier mix
  reduces `ir.bibliography` by raw `tier`; new collapsible `report_md` block;
  the 3 `getChart()` charts unchanged.
- **`apiErrorMessage`** (new helper) — extracts the FastAPI `detail` from
  `ApiError.body`.
- **`twoFamilyState`** (new helper) — recomputes the §9.1.1 invariant.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — shell migrated, no fabrication.** `RunShell` reads only
  `ir.manifest.{status,cost_usd,question,slug,word_count}`,
  `ir.model_provenance`, `ir.protocol` — all fields confirmed present in the
  slice-2 `AuditIrRun` interface (api.ts:1309-1396) and the loader dataclass
  tree (`loader.py`). No `bundle` field is read by the shell.
- **VERIFIED — P2-1 (§3.4) addressed.** `apiErrorMessage` reads
  `(err as ApiError).body.detail` — the FastAPI 404/409/422 reason that
  `asJsonOrThrow` stores on `ApiError.body` — with a typed guard chain
  (`"body" in err` → object → `"detail" in body` → `typeof detail ===
  "string"`). Falls back to `err.message` only when no `detail`. The error
  panel heading is relabelled "Run inspector unavailable".
- **VERIFIED — P2-2 (§2.2) addressed.** `ir.protocol` is nullable; the
  run-header renders `slug` unconditionally and gates the
  `scope_decision`/`created_at_iso` fragment on `ir.protocol &&` — no
  rendering of `undefined`.
- **VERIFIED — P2-3 (§3.3) addressed.** `twoFamilyState` returns
  `known: false` when `model_provenance == null` OR either family string is
  `""`; PASS/FAIL (`generator_family !== evaluator_family`) is only computed
  and shown in the `known` branch. The card shows a neutral "Model provenance
  not recorded" title + no border tint when `!known` — no fabricated verdict.
- **VERIFIED — faithful T1-T7 tier mix.** `tierCounts` reduces
  `ir.bibliography` by the raw `tier` string; `tierSummary` sorts and joins
  all present tiers. The old hard-coded `T1:/T2:/T3:` (which silently dropped
  T4-T7) is gone — this is the Option-A faithfulness point.
- **VERIFIED — `report_md` as raw `<pre>`.** Rendered inside a collapsible
  `<details>` (brief §3.2, Codex raised no P2 against the raw-`<pre>` plan).
  Zero new dependency — `web/package.json` has no markdown renderer; proper
  markdown rendering is a later slice.
- **VERIFIED — abort/error runs (§3.4).** `getAuditRun()` throws on
  abort/error runs (slice-1 route 422); the `.catch` sets `error`; the body
  gate `ir && bundle` stays false → the honest error panel renders the 422
  detail instead of empty tabs. Accepted per brief §3.4.
- **VERIFIED — 5 tabs untouched.** `SentencesTab`, `renderSentenceWithTokens`,
  `FramesTab`, `ContradictionsTab`, `ChartsTab`, `PoolTab`, `EvidencePane` are
  byte-identical to `polaris` HEAD — still `EvidenceContract`/`SourceSpan`.
  `evidenceById` + the `tabs` array stay `bundle`-based.
- **VERIFIED — scope.** Only `web/app/inspector/[runId]/page.tsx` changed; no
  `web/lib/api.ts`, no `src/`, no other `web/app/**`.

## 3. Smoke

Frontend change → `lint + format + typecheck + build` CI job in scope.
Offline: `npx prettier --write app/inspector/[runId]/page.tsx` → unchanged
(already compliant); `npm run lint` → 0 errors (3 repo-wide warnings: 1 in
the inspector page — `chartTypes` `react-hooks/exhaustive-deps`, **pre-existing**,
preserved verbatim from the original `ExecutiveSummaryTab`; 2 unrelated —
`benchmark_board.tsx`, `frame_coverage_panel.spec.ts`); `npm run typecheck`
→ clean; `npm run build` → OK. The repo-wide `format:check` 189-file debt is
pre-existing (THIRD_PARTY_LICENSES.md, tsconfig.json, test fixtures — none
touched by slice 3).

## 4. Codex iteration trail

- **Brief iter 1 APPROVE** — 0 P0/P1; 3 P2 (error-detail extraction, nullable
  `protocol` fallback, two-family known-state guard) — all baked into commit 1.

## 5. Scope + residuals

Slice 3 = shell + summary. Remaining per the consult: slice 4 citation hover,
slice 5 frame coverage / tier mix / two-family detail, slice 6 contradictions,
slices 7-12 charts / compare / follow-up / pin replay / memory / bundle UX.
The `getBundle()` call is removed when the last tab migrates. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief; the shell + summary read the AuditIR shape
1:1; the 3 Codex P2 refinements are implemented; the 5 un-migrated tabs are
untouched (the consult's "split by surface" discipline); web smoke
(prettier/lint/typecheck/build) all green. Ready for Codex diff review.
