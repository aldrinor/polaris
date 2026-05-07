# Codex Diff Review — I-f5-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-003 — Inspector source span + URL + tier + retrieval trace
**Brief:** APPROVED iter 2 (after pool-threading + snippet-fallback fixes)
**Canonical-diff-sha256:** `1a04802055fbe0410c6e17554a6fe3afb0423395536b5b896d15e110b338380a`
**LOC:** 245 net (45 over CHARTER §1 200-cap; LOC exemption requested below)

## Files

```
web/lib/provenance_tokens.ts                          NEW +27
web/app/generation/components/sentence_inspector.tsx  EDIT +128/-13
web/app/generation/components/verified_report_view.tsx EDIT +4
web/app/generation/components/generation_runner.tsx   EDIT +1
web/app/sentence_hover_test/_demo.tsx                 EDIT +63/-13
web/tests/e2e/sentence_inspector_source.spec.ts       NEW +42
```

## What changed

**`provenance_tokens.ts`:** `parseProvenanceToken` regex `/^\[#ev:([a-zA-Z0-9_\-]+):(\d+)-(\d+)\]$/` + `parseAllTokens` filter.

**`sentence_inspector.tsx`:** SourceCard renders for each parsed token: source URL anchor + tier badge with rationale tooltip + highlighted span (full_text ?? snippet ?? "") with out-of-range guard + retrieval trace (title/date/authors). Missing-source path shows `inspector-source-missing-{i}` badge.

**`verified_report_view.tsx`:** Accepts optional `pool` prop; threads to SentenceInspector.

**`generation_runner.tsx`:** Passes `pool={state.pool}` to VerifiedReportView (production wiring).

**`_demo.tsx`:** Synthetic EvidencePool with 10 T1 Cochrane sources; sentence 9 references `src-ghost` for missing-source path.

**`sentence_inspector_source.spec.ts`:** 2 Playwright tests covering tier+URL+span+trace + missing-source path.

## LOC exemption requested

CHARTER §1 200-cap exceeded by 45. Drivers: SourceCard renders 6 distinct fields (URL, tier, span, trace title, trace date, trace authors), each requiring its own data-testid for Playwright assertions. Splitting into a separate component file would only relocate LOC. Demo fixture extension (synthetic 10-source pool) drives ~50 LOC; needed for both happy + missing-source test paths. Exemption analogous to I-f15-003 (381 LOC, granted) — binding multi-substrate coverage in a single coherent UI feature.

## Risks for Codex Red-Team

1. **Snippet fallback** uses `full_text ?? snippet ?? ""` per Codex iter-1 P1; out-of-range guard prevents crash on `text.slice(end > length)`.
2. **Tier rationale** rendered via `title=` attribute (HTML tooltip) on the badge.
3. **Missing-source path** uses `inspector-source-missing-{i}` testid (per Codex iter-1 P2).
4. **`pool` defaults to null** in VerifiedReportView; missing-pool case renders SourceCard with `source=undefined` → missing-source badge fires correctly.
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 245 net. Exemption requested.
7. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
