# Codex DIFF review — I-rdy-008 / GH #504 slice 6: migrate the contradictions tab to AuditIR

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 6** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical diff
in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 1, all
6 scope calls accepted). **1 file: `web/app/inspector/[runId]/page.tsx`.**

Slice 6 of ~12 for #504 (Option A). Migrates the inspector page
**contradictions tab** (`ContradictionsTab`) off `getBundle()`/
`EvidenceContract` onto the AuditIR `contradictions`. `SentencesTab` (s4) /
`FramesTab` (s5) / `ChartsTab` / `PoolTab` / `EvidencePane` stay on
`getBundle()` — slices 7+. Do NOT flag "the other tabs still use
getBundle()" — deliberate.

## 2. The change

- `ContradictionsTab` — new props `{ ir, onSelect }` (was `{ bundle,
  onSelect }`); maps `ir.contradictions` (`AuditIrContradictionCluster[]`):
  per cluster a Card (key `cluster_id`) with a `severity` badge + diff
  (`absolute_difference`/`relative_difference`), `subject` — `predicate`
  title, `recommended_action` line, and an N-row `claims[]` list (per claim:
  `value`/`unit`, `endpoint_phrase`, `arm`/`dose`/`source_tier`,
  `context_snippet`, clickable `evidence_id`, `source_url` link).
- New `contradictionSeverityClass(severity)` — heuristic color.
- `contradictions` tab count `bundle.contradictions.length` →
  `ir.contradictions.length`.
- Call site `<ContradictionsTab bundle={bundle} … />` → `ir={ir}`.

## 3. Verify

1. **AuditIR field access faithful.** `AuditIrContradictionCluster`
   (`cluster_id`, `subject`, `predicate`, `severity`, `absolute_difference`,
   `relative_difference`, `recommended_action`, `claims`);
   `AuditIrContradictionClaim` (`evidence_id`, `subject`, `predicate`,
   `arm`, `dose`, `value`, `unit`, `source_tier`, `source_url`,
   `context_snippet`, `endpoint_phrase`). Cross-check `web/lib/api.ts`
   (slice 2) + `src/polaris_graph/audit_ir/loader.py` `_parse_contradictions`.
2. **`source_url` guarded.** The `source` link renders only when
   `claim.source_url` is non-empty (the loader defaults missing to `""`).
3. **No fabrication.** `recommended_action` / `context_snippet` /
   `endpoint_phrase` / `arm` / `dose` rendered only when non-empty;
   `cluster_id` is the React key only (the loader assigns it from the list
   index — stable per load).
4. **`onSelect`** still routes a claim `evidence_id` to the bundle-backed
   `EvidencePane` (dual-fetch transition); the `InspectorPage` closure +
   `evidenceById` are untouched.
5. **The other tabs + `EvidencePane`** byte-identical to `polaris` HEAD;
   `SentencesTab`'s `bundle.contradictions[].section_id` badge is
   independent of this change and untouched.
6. **Scope** — only `web/app/inspector/[runId]/page.tsx`; no `web/lib/api.ts`,
   no `web/components/ui/**`, no `src/`.

## 4. Files I have ALSO checked and they're clean

- `web/lib/api.ts` — `AuditIrContradictionCluster`/`AuditIrContradictionClaim`
  (slice 2); NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `_parse_contradictions`
  (`cluster_id=idx`; `claims` ≥2; `severity` default `"unknown"`); NOT
  modified.
- `SentencesTab` / `FramesTab` / `ChartsTab` / `PoolTab` / `EvidencePane` —
  untouched.

## 5. Smoke state

`web/`: `prettier --write app/inspector/[runId]/page.tsx` → applied;
`npm run lint` → 0 errors (3 pre-existing warnings, count unchanged —
`chartTypes` `exhaustive-deps` in `ExecutiveSummaryTab` is pre-existing);
`npm run typecheck` → clean; `npm run build` → OK. The `lint + format +
typecheck + build` CI job is in scope for this web/ PR.

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
