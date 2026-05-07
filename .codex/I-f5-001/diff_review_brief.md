# Codex Diff Review — I-f5-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-001 — Hover-highlight every claim sentence
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `5b626980146e7458e6cfd9f888ab1cb98e0f74c0f0ae769e5fc9b2a74f1586ac`
**LOC:** 153 net (47 under CHARTER §1 200-cap)

## Files

```
web/lib/sentence_highlight.ts                          NEW +50
web/app/generation/components/verified_report_view.tsx EDIT +37/-13
web/app/sentence_hover_test/page.tsx                   NEW +5
web/app/sentence_hover_test/_demo.tsx                  NEW +43
web/tests/e2e/sentence_hover.spec.ts                   NEW +18
```

## What changed

**`sentence_highlight.ts`:** `useSentenceHover` hook with debounced mouseover/mouseout listeners on a ref-attached root + `[data-sentence-id]` selector. Returns `{ hovered_id, root_ref }`.

**`verified_report_view.tsx`:** WIRED into production component (per Codex iter-1 P1). Each `<li>` gets `data-sentence-id="${section_id}:${idx}"` + conditional `bg-yellow-100` className when hovered. Root `<div>` carries the ref.

**`/sentence_hover_test`:** Test harness route mounting VerifiedReportView with synthetic 10-sentence report. Avoids needing a real generation run for the test.

**`sentence_hover.spec.ts`:** Single Playwright test (per Codex iter-1 P2 deterministic indices) hovers s7 then s3, asserts highlight transitions correctly.

## Risks for Codex Red-Team

1. **Production wiring done.** `verified_report_view.tsx` (consumed by `generation_runner.tsx`) now applies hover-highlight to every sentence.
2. **Debounce cleanup** in effect cleanup via clearTimeout.
3. **`set-state-in-effect` lint** avoided — setState only in event handlers (mouseover/mouseout via debounced setTimeout).
4. **Test harness** at `/sentence_hover_test` (Codex iter-1 production-wiring fix uses real component, not demo-only).
5. **§9.4 N/A frontend.**
6. **CHARTER §1 LOC cap.** 153 net.
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
