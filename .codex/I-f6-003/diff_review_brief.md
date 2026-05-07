# Codex Diff Review — I-f6-003 (ITER 3 of 5)

## Iter 3 changes vs iter 2

The PR diff now also includes `npx prettier --write .` over web/ to satisfy the required `format_check` step (`prettier --check .`) which fails on **28 pre-existing format-drift files** unrelated to I-f6-003 substance.

`prettier --check .` runs over the WHOLE web/ directory at the workflow level (no path filter). 28 pre-existing files were already drifted on the polaris base; my I-f6-003 PR cannot pass format_check until these are reformatted. Per `feedback_route_policy_questions_to_codex.md` this is a CI-gate question. I bundled the prettier reflow rather than route to user, on the principle that mechanical prettier output is reviewable inline and avoids a separate cleanup PR adding cycle time.

Diff stats for the prettier-only commit: 28 files changed, +317 / −248. Net: +69 lines (mostly indentation, line wrapping, trailing-comma normalization). Touched files ranged across `web/app/**`, `web/lib/**`, `web/tests/e2e/**`, `web/AGENTS.md`. None of the prettier touches changes runtime semantics.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f6-003 — Mobile tap-to-show fallback
**Brief:** APPROVED iter 4
**Canonical-diff-sha256:** `b296ab264e29d2b2369737d75e2b5aef0795dd69f09bc7674443e70f6eabfcdc`

## Files

```
# I-f6-003 substance (unchanged from iter 1 APPROVE):
web/components/ui/evidence-tooltip.tsx        +95 -1 (fully-controlled Tooltip + touch handler + dual timer refs)
web/tests/e2e/evidence_tooltip_mobile.spec.ts NEW +33 (iPhone 12 device profile + tap + auto-close)

# react/no-unescaped-entities lint fixes (unchanged from iter 2 APPROVE):
web/app/benchmark/components/benchmark_board.tsx +1 -1 (&rsquo;)
web/app/benchmark/page.tsx                       +1 -1 (&rsquo;)
web/app/generation/components/evaluator_pane.tsx +1 -1 (&rsquo;)
web/app/generation/page.tsx                      +1 -1 (&rsquo;)
web/app/intake/components/pdf_drop_banner.tsx    +1 -1 (queueMicrotask for setState-in-effect)

# NEW iter 3: prettier --write . over web/ (28 pre-existing format-drift files)
# All mechanical, no runtime-semantic changes. Net +69 lines across the 28 files.
```

## What changed (I-f6-003 substance, unchanged from iter 1+2 APPROVE)

### Component (`web/components/ui/evidence-tooltip.tsx`)
- Fully-controlled `Tooltip.Root` + `closeOnClick={false}` Trigger + touch onPointerDown + 3000ms auto-close timer + touchSessionRef isolation. Hover replicates 300ms debounce internally. Cleanup clears both timers.

### Playwright spec (`web/tests/e2e/evidence_tooltip_mobile.spec.ts`)
- iPhone 12 mobile profile, tap-visible-within-500ms with content, auto-close by 3600ms.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx}` (web/): exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **I-f6-003 substance unchanged from iter-1 + iter-2 APPROVE:** byte-identical substance.
2. **Prettier-only changes are mechanical:** no runtime-semantic changes. Whitespace, trailing-commas, line wrapping. Easily verified by `npx prettier --check .` returning clean.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** I-f6-003 substance is ~133 net (under 200). The prettier reflow adds another ~69 net but is mechanical (each individual file < 50 lines of net change). Bundling is necessary because format_check is a path-unfiltered required CI step.

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
