HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-013b / GH#669

Brief APPROVE iter 2/5. 11 files / +141 / -313 / **-172 net LOC**. The diff is mechanical migration (more deletes than adds).

## §A — Diff summary

- 2 production component patches (WCAG 2.5.8 button sizing).
- 5 .spec.ts file edits (inspector / accessibility / visual / performance / inspector_route).
- 1 .spec.ts file DELETED (performance_hover).
- 3 visual baseline PNGs DELETED.
- 1 playwright.config.ts edit (Linux testIgnore).

## §B — Acceptance verification

| Criterion | Status |
|---|---|
| Legacy `/inspector/golden_*` Playwright assertions all migrated/replaced/deleted | YES |
| `accessibility.spec.ts` covers new Inspector route a11y | YES |
| `/runs/<bad-runid>` axe test PRESERVED (Codex iter-1 P2 #2) | YES — in new "WCAG-AA — Run-detail error states" describe |
| Legacy visual baselines deleted | YES — 3 PNGs |
| `performance_hover.spec.ts` deletion justified | YES — UX surface no longer exists |
| Buttons meet WCAG 2.5.8 ≥24×24 | YES — min-h-6 + px-2 py-1 |

## §C — Smoke

- `cd web && npm run typecheck`: clean (0 errors)
- `cd web && npm run lint`: 2 pre-existing warnings (unrelated)
- `prettier --check` on changed files: clean

## §D — Codex Red-Team checklist

1. Are the 2 button patches sufficient to make the target-size sweep pass on `/inspector/v1-canonical-success` Reasoning tab? (24×24 minimum with min-h-6 + py-1 + px-2 = 24+8+8 px = 40×40 minimum visible).
2. Did I preserve the `/runs/<bad-runid>` axe test correctly in a new describe (Codex iter-1 P2 #2)?
3. Are the deleted legacy describes' test intents either MIGRATED or DOCUMENTED-as-deferred (drop_reason)?
4. Does the playwright.config.ts Linux testIgnore now correctly cover both `visual.spec.ts` and `inspector_route.spec.ts`?
5. Is the deletion of `performance_hover.spec.ts` justified given the new Inspector has no hover tooltip UX?
6. No accidental file additions / deletions beyond the 11-file scope?

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
