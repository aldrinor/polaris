# Brief — I-p2-042 (#831): S-tier foundation tokens (motion + brand-tinted shadow) + design-system doc

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Same quality bar each iter.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
S-tier redesign (#829), build-order step 1, per YOUR vision-authored direction
(.codex/ui_visual_audit/s_tier_direction_verdict.txt). Token system + brand red already
exist; brand #c8102e is OPERATOR-LOCKED (do not change). This adds the genuinely-missing
foundation primitives + the canonical doc.

## Change (3 files, additive/low-risk)
- `app/globals.css` @theme: `--ease-standard: cubic-bezier(0.2,0.8,0.2,1)` (one motion
  primitive) + `--shadow-card` / `--shadow-card-hover` (brand-temperature elevation using
  the locked #c8102e=rgb(200,16,46) — neutral hairline + faint red wash, NOT a palette
  change). Purely additive (new utilities `shadow-card`, `ease-standard`).
- `components/ui/card.tsx`: add `shadow-card` + `transition-shadow duration-150 ease-standard`
  → restrained premium elevation on every Card product-wide (was ring-only/flat).
- `docs/web/s_tier_design_system.md`: canonical S-tier reference.

## Acceptance
- AC1: additive tokens; no existing utility/token value changed; brand red untouched.
- AC2: Card gains brand-tinted elevation + smooth shadow transition; no layout shift.
- AC3: build + eslint + prettier green.

## Visual verification (the operator-required gate — run after this)
Claude viewed + Codex `-i` will confirm the every-page card elevation is a restrained S-tier
LIFT (expensive temperature) not a regression. NOTE: visual_60 baselines will need refresh
(intentional global shadow change).

## Files I have ALSO checked and they're clean
- card.tsx is the single Card primitive (used product-wide); the new tokens are namespace-safe
  (`--shadow-*`→`shadow-*`, `--ease-*`→`ease-*` Tailwind v4 utilities); no component currently
  uses `shadow-card`/`ease-standard` except the Card I edited.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
