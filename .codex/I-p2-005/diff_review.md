# Codex DESIGN+DIFF review — I-p2-005 (#744): per-claim verdict chip

HARD ITERATION CAP: 5. iter 2 (iter-1 P1: UNSUPPORTED/UNREACHABLE text-foreground AA). APPROVE iff zero P0/P1 (code + design rubric). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `061480583db01b9fd68c498e4c333be920ffafbe185a4cddbaedbd2c5d5e0ccb`. web/ only.

## Design-audit note (component, no standalone page)
Display-only chip; visual renders in-context on the report/audit pages (#756/#759) where it gets the full screenshot audit. Here audit code + the rubric a11y/honesty dims from the code + token math.

## Diff
- NEW web/components/verdict/verdict_chip.tsx: VerdictKind union (7 verdicts) → {label, lucide Icon, #742-token className}. Renders pill: tint bg + icon (aria-hidden) + label text = THREE signals (never color-only).
- Mapping: VERIFIED→verified(green,BadgeCheck); PARTIAL→contradiction-tint(CircleSlash); UNSUPPORTED→muted(Minus); FABRICATED→destructive(X); UNREACHABLE→muted dashed(CircleHelp); contradiction→contradiction(TriangleAlert); refusal→refusal(Ban).

## Review focus (rubric: provability/honesty, a11y, visual)
1. WCAG 1.4.1: every verdict distinguished by MORE than color (icon + label present)? PARTIAL vs contradiction (both amber tint) distinct by icon(CircleSlash vs TriangleAlert) + label?
2. AA contrast: each label text on its tint (text-verified / text-destructive / text-refusal on /10 of themselves ≈ white; text-contradiction-foreground on amber/15; text-muted-foreground on muted). Any pair under 4.5:1?
3. Honesty: labels accurate, no euphemism (Fabricated, Unreachable distinct + serious)?
4. Token classes resolve (bg-verified/10 etc. from @theme)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
