# Codex BRIEF review — I-p2-005 (#744): per-claim verdict chip

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **per-claim verdict chip** (TIER 2; report/audit pages reuse it) showing a claim's verification verdict with a state color + icon + label (NOT color-only).

## Verified current state (grounded)
- NO per-claim verdict enum exists in the frontend yet (grep: only ScopeVerdict = accepted|needs_clarification|rejected, which is the SCOPE gate, NOT per-claim). So #744 INTRODUCES the canonical verdict vocabulary as a presentation primitive; the data layer feeds it (report page #756 / audit #759 wire real values).
- #742 state tokens exist + @theme-exported: --verified (green), --contradiction (amber), --refusal (neutral), --destructive (maroon), each with -foreground; plus --muted for neutral.
- Canonical §-1.1 audit vocabulary: VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE (+ contradiction, refusal as run states).

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/verdict/verdict_chip.tsx`: prop `verdict: VerdictKind` (typed union of the 7 values). Renders a small pill: state-color tint + an icon/glyph + the label text (THREE signals — never color alone, per rubric a11y).
2. Token mapping (distinct + AA): VERIFIED→--verified(green,✓); PARTIAL→amber(~, caution); UNSUPPORTED→--muted/neutral(—, no evidence); FABRICATED→--destructive(maroon,✕, serious); UNREACHABLE→muted dashed(?, not fetched); contradiction→--contradiction(amber,⚠ conflict); refusal→--refusal(neutral, shield). PARTIAL vs contradiction both amber-family MUST be disambiguated by icon+label (color not sole signal).
3. Honest semantics: each label is accurate (FABRICATED is a real, serious verdict; UNREACHABLE ≠ UNSUPPORTED). No euphemism.
4. Frontier-Minimal; WCAG 2.2 (AA contrast on each tint, icon has aria-hidden + the label is the accessible name, target sizing if interactive — chip is non-interactive display).

## Files I have ALSO checked and they're clean
- web/app/globals.css (#742 state tokens + @theme exports the chip consumes), web/components/inspector/family_segregation_badge.tsx (existing badge pattern), web/components/ui/badge.tsx (shadcn badge if present).

## Review focus
1. Is the 7-verdict vocabulary correct + complete vs §-1.1 (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE) + contradiction/refusal? Any verdict missing/wrong?
2. Are PARTIAL vs contradiction (both amber) disambiguated by icon+label so they're not color-only-distinguished?
3. AA contrast of each label on its tint; icon a11y (aria-hidden + accessible label).
4. Any euphemism that softens a serious verdict (FABRICATED). Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
