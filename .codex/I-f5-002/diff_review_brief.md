# Codex Diff Review — I-f5-002 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f5-002 — Click → Inspector pane (Sheet, 40% width)
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `0c5913301e7194dbe8f8b1e6651771d27b076fbc3ab1a765e8cfa3cae3d8a2d9`
**LOC:** 137 net (well under CHARTER §1 200-cap)

## Diff iter-1 verdict consumed

- P1 (40% width override fails because side-scoped Sheet classes win): RESOLVED iter 2 — switched to side-scoped overrides `data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none` (same selector specificity as the base SheetContent).
- P2 #1 (description leaked I-f5-003 follow-up reference): RESOLVED iter 2 — replaced with product-facing copy "Provenance and verification details for the selected sentence."
- P2 #2 (non-semantic li with no keyboard activation): RESOLVED iter 2 — added `role="button"`, `tabIndex={0}`, and `onKeyDown` handler for Enter/Space (with preventDefault). Plus `focus:ring-2 focus:ring-blue-400` for visible focus state.

## Files

```
web/app/generation/components/sentence_inspector.tsx     NEW +84
web/app/generation/components/verified_report_view.tsx   EDIT +32
web/tests/e2e/sentence_inspector.spec.ts                 NEW +21
```

## Risks for Codex Red-Team

1. **Side-scoped width override** matches base SheetContent selector specificity per Codex iter-1 P1.
2. **Keyboard accessibility** via role+tabIndex+onKeyDown.
3. **Click vs hover** coexist; click triggers Sheet open, hover triggers highlight.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap.** 137 net.

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
