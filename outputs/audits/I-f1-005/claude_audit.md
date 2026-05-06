# Claude architect self-audit — I-f1-005

**Issue:** I-f1-005 — F1 axe-core WCAG-AA compliance test
**Brief:** `.codex/I-f1-005/brief.md` (Codex APPROVE iter 3)
**Diff:** `.codex/I-f1-005/codex_diff.patch` (canonical sha256 `e2e629497e74ef0f613a1e3fce140367d5015938fe082d7248d842ada71f6a9a`)

## What the diff does

1. **`web/app/components/command_palette.tsx`** (MOD +3/-1): adds `aria-label="Template results"` to `<ul role="listbox">` (closes axe `aria-input-field-name`); adds `role="option"` + `aria-selected={i === clamped}` to each `<li>` (closes axe `aria-required-children`). Both fixes were caught by Codex iter-1 + iter-2 of the brief by inspecting the existing palette markup.
2. **`web/tests/e2e/f1_a11y.spec.ts`** (NEW +44): two scans at 1024×768:
   - `/` with palette OPEN (Ctrl+K + `command-palette` testid visible) → axe scan; assert serious+critical violations empty.
   - `/intake?template=clinical` initial render → axe scan; same assertion.
   Severity filter (`v.impact === "serious" || "critical"`) per issue acceptance criterion "zero serious/critical violations."

## Empirical verification

- `npx tsc --noEmit -p .` clean.
- `npx eslint <my files>` clean.
- Playwright not run locally.

## LOC

```
web/app/components/command_palette.tsx       MOD +3 / -1
web/tests/e2e/f1_a11y.spec.ts                 NEW +44
```

**Total: +47/-1 = +46 net.** Under 60 issue-budget AND CHARTER §1 200-cap.

## Iter trajectory

- iter 1: 1 P1 (palette listbox `<li>` not `role="option"`) + 1 P2 (WCAG_TAGS drift)
- iter 2: 1 P1 (listbox needs aria-label) + 1 P2 (exclusion contradiction)
- iter 3: APPROVE (zero P0/P1/P2)

Codex caught two real a11y bugs by reading actual `command_palette.tsx` markup against axe rule definitions. Empirical inspection-driven review.

## Risks acknowledged

- Severity filter only blocks `serious`+`critical`. `moderate`/`minor` violations are non-blocking per issue spec. If future audits demand zero-of-any, tighten the filter in a follow-up.
- `/intake?template=clinical` uses `domcontentloaded` rather than `networkidle` to avoid stalling on retried fetches when backend is unavailable; `intake-page` testid visible signals React rendered.
- No CI integration in this Issue; `web_ci.yml` runs only inspector/accessibility/performance per existing policy.

## Output schema for Codex review

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
