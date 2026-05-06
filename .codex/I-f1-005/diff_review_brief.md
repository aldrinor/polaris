# Codex Diff Review Brief — I-f1-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates. Brief APPROVE'd iter 3.

- **Brief:** `.codex/I-f1-005/brief.md` (Codex APPROVE iter 3)
- **Diff:** `.codex/I-f1-005/codex_diff.patch` (canonical sha256 `e2e629497e74ef0f613a1e3fce140367d5015938fe082d7248d842ada71f6a9a`)
- **Audit:** `outputs/audits/I-f1-005/claude_audit.md`

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint <my files>` → clean.
- Playwright not run locally.

## Files (2, +46 net)

```
web/app/components/command_palette.tsx       MOD +3/-1   (a11y fixes per brief iter-1+iter-2 P1s)
web/tests/e2e/f1_a11y.spec.ts                 NEW +44     (2 axe scans)
```

CHARTER §1 200-LOC cap: +46 net. Well under cap.

## Specific risks for Codex Red-Team

1. **Listbox aria-label string `"Template results"`.** Picked for clarity. Verify it's an accessible name axe `aria-input-field-name` will accept.
2. **`role="option"` + `aria-selected` on each `<li>`.** axe `aria-required-children` requires listbox children with `role=option`. `aria-selected={boolean}` is required on each option per ARIA spec. Verify both attributes set correctly.
3. **Severity filter (`serious`+`critical`).** Per issue spec; non-critical violations don't fail. Verify the filter functor matches issue acceptance.
4. **`/intake?template=clinical` `domcontentloaded` + testid wait.** Avoids networkidle stalls on retried backend fetches. axe runs after React hydration confirmed via `intake-page` testid. Verify this pattern doesn't miss render-late content.
5. **No regression to existing axe specs.** `landing_template_grid.spec.ts` axe at 1024px (palette CLOSED) still passes — the new `aria-label` and `role="option"` are additive; closed-palette doesn't render the Dialog. `accessibility.spec.ts` (dashboard/inspector) untouched.
6. **`canonical-diff-sha256` correctness.** `e2e629497e74ef0f613a1e3fce140367d5015938fe082d7248d842ada71f6a9a`.

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
