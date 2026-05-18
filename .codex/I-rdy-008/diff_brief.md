# Codex DIFF review — I-rdy-008 / GH #504 slice 3: migrate inspector shell + summary to the AuditIR client

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 3** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1, 3 P2).
**1 file, +192 / -77 — `web/app/inspector/[runId]/page.tsx`** (805 → 920 lines).

Slice 3 of ~12 for #504 (Option A). Migrates the inspector page **shell**
(3 status cards + run-header) + **Executive-summary tab** off
`getBundle()`/`EvidenceContract` onto `getAuditRun()`/`AuditIrRun`. The 5 other
tabs (`SentencesTab`/`FramesTab`/`ContradictionsTab`/`ChartsTab`/`PoolTab`),
`EvidencePane`, `renderSentenceWithTokens`, `evidenceById` are intentionally
**unchanged** — they migrate in slices 4-7. Do NOT flag "the other tabs still
use getBundle()" — that is the consult's deliberate split-by-surface plan.

## 2. The change

- `InspectorPage` dual-fetches `getAuditRun()` → `ir` + `getBundle()` →
  `bundle` (one `useEffect`, single `cancelled` guard); body gates on
  `ir && bundle`.
- New `RunShell` renders pipeline-status / two-family / cost from
  `ir.manifest` + `ir.model_provenance`; run-header from
  `ir.manifest.{question,slug}` + `ir.protocol?.{scope_decision,created_at_iso}`.
- New `twoFamilyState(ir)` derives the §9.1.1 invariant from the family
  strings (`known` false when `model_provenance` null or a family string is
  empty).
- New `apiErrorMessage(err, fallback)` extracts the FastAPI `detail` from
  `ApiError.body`.
- `ExecutiveSummaryTab` takes `ir` instead of `bundle`; counts from
  `ir.manifest`; tier mix from `ir.bibliography` (raw `tier`); new collapsible
  `report_md` block; 3 `getChart()` charts unchanged.

## 3. Verify

1. **AuditIR field access is faithful.** Cross-check every `ir.*` access in
   `RunShell` / `twoFamilyState` / `ExecutiveSummaryTab` against the
   `AuditIrRun` interface (`web/lib/api.ts:1309-1396`, slice 2) — field names
   + nullability. `model_provenance`/`protocol` are `| null`.
2. **The 3 brief P2s are implemented.** (P2-1) `apiErrorMessage` reads
   `body.detail` not just `err.message`; (P2-2) `protocol` null → run-header
   omits scope/created, no `undefined` render; (P2-3) two-family PASS/FAIL
   only in the `known` branch (both families non-empty + unequal).
3. **No fabricated state.** `model_provenance == null` → "Model provenance
   not recorded", no PASS/FAIL, no border tint.
4. **The 5 un-migrated tabs are byte-identical** to `polaris` HEAD —
   `SentencesTab`/`renderSentenceWithTokens`/`FramesTab`/`ContradictionsTab`/
   `ChartsTab`/`PoolTab`/`EvidencePane`. `evidenceById` + `tabs` stay
   `bundle`-based.
4b. **`cancelled` guard** covers both promises; both `.catch` set `error`.
5. **Scope** — only `web/app/inspector/[runId]/page.tsx`; no `web/lib/api.ts`,
   no `src/`, no other `web/app/**`.

## 4. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `getAuditRun()` + `AuditIrRun` (slice 2); `getBundle()`/
  `EvidenceContract`/`getChart()`/`ApiError`/`downloadBundleAsJson` all still
  present; NOT modified.
- `src/polaris_v6/api/inspector.py` (slice 1) — the route `getAuditRun`
  targets; NOT modified.
- `web/app/runs/[runId]/page.tsx` — also uses `getBundle()`; a separate page,
  not in #504 slice 3 scope; NOT modified.

## 5. Smoke state

`web/`: `prettier --write app/inspector/[runId]/page.tsx` → unchanged;
`npm run lint` → 0 errors (1 pre-existing inspector-page warning preserved
verbatim — `chartTypes` `exhaustive-deps` in `ExecutiveSummaryTab`, present in
the original code; 2 unrelated pre-existing warnings); `npm run typecheck`
→ clean; `npm run build` → OK. Repo-wide `format:check` 189-file debt is
pre-existing (untouched files). The `lint + format + typecheck + build` CI job
is in scope for this web/ PR.

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
