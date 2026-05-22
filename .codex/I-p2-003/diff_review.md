# Codex DESIGN-AUDIT + DIFF review — I-p2-003 (#742) design system → white + Canada-red

HARD ITERATION CAP: 5. iter 3 (iter-2: all ring-ring/50 fixed repo-wide + hash refreshed). APPROVE iff zero P0/P1 across code-correctness AND the design rubric. Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `1d493807ee5f227c8a9e2cfc2792477d984de3ae0c448a38046a60286171e34f`. web/ only.

## Claude's VISUAL design audit (I rendered via the production standalone harness + viewed the home screenshot; Codex can't view PNGs — audit the DIFF + cross-check these findings):
- White background; --primary/--ring = #C8102E renders as a confident dark red — the "Verify" + "Open Clinical drug audit" buttons + active nav pill are clearly Canada-red on white. PASS visual/accent.
- Accent reads as a real accent (not the faint old cyan/blue). Hairlines + whitespace intact.
- (Note: screenshot is the CURRENT home layout — the new home is #752. This issue = design-system TOKENS only.)

## Diff (.codex/I-p2-003/codex_diff.patch) — review for the rubric + correctness:
- globals.css :root: --primary/--ring #C8102E (AA 5.88:1 on white); --accent red tint; --destructive = deep maroon oklch(0.42 0.13 18) DISTINCT from national red; state tokens --verified(green)/--contradiction(amber)/--refusal(neutral) + foregrounds; evidence tokens --tier-1/2/3, --proof-token, --verified-bundle; all @theme-exported.
- .dark: cyan → Canada-red (was violating the lock); light is demo target.
- focus ring ring-ring/50 → /70 (button.tsx, input.tsx) + outline-ring opaque (globals.css) — clears the 3:1 WCAG 2.2 focus bar.

## Review focus (16-dim rubric, dims 1/7/8/12 most relevant + code correctness)
1. Contrast: #C8102E/white ≥4.5:1? --destructive maroon distinguishable from #C8102E? state-token foregrounds AA? focus ring /70 ≥3:1?
2. @theme exports correct + consumable? No broken var refs?
3. Any token the rubric requires that's still missing/red-only?
4. typecheck/build green (confirmed locally). Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
