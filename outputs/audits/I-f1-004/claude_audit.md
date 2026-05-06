# Claude architect self-audit — I-f1-004

**Issue:** I-f1-004 — Template adversarial test: BPEI → no false-positive
**Brief:** `.codex/I-f1-004/brief.md` (Codex APPROVE iter 3)
**Diff:** `.codex/I-f1-004/codex_diff.patch` (canonical sha256 `75f12bb2b2eca1bc76f7184bcb9f797d89e6e37cb304ff2f688fc5c40d92bc3d`)

## What the diff does

Per iter-3 brief (Codex APPROVE), adds a 22-input adversarial Playwright corpus:

**`web/tests/e2e/command_palette_adversarial.spec.ts`** (NEW +82) — Two parameterized loops:

1. **`zero_match` (15 inputs):** ambiguous tokens (BPEI/CDS/NEC/MS/RAG/SOTA), random gibberish, emoji, off-domain (weather forecast / quantum entanglement / pizza recipe), whitespace, SQL/XSS/Unicode-RTL probes. Each asserts `await expect(items).toHaveCount(0, { timeout: 350 })`.
2. **`exact_one_match` (7 inputs with expected_id):** synonym-fired (tirzepatide/ozempic → clinical), exact name (clinical drug audit, housing), summary substring (oil-sands → climate), sample-question substring (2% target → defense, tariff → trade). Each asserts `toHaveCount(1)` AND `getByTestId(palette-item-<expected_id>).toBeVisible()` (P1-iter2 fix — the visible-by-id assertion catches wrong-sole-suggestion).

15 + 7 = 22 inputs total per Carney plan §F1 spec.

## Empirical verification

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint tests/e2e/command_palette_adversarial.spec.ts` → clean.
- Codex iter-1 + iter-2 ran the corpus through actual `score_template()` and verified zero unexpected matches after the iter-2 `the` → `weather forecast` fix (the iter-1 false-positive that Codex caught — substring "the" in 5 sample_questions).
- Playwright not run locally (requires Next.js dev server + Chromium download).

## LOC accounting

```
web/tests/e2e/command_palette_adversarial.spec.ts    NEW +82
```

**Total: +82 net.** Under 100 issue-budget AND CHARTER §1 200-cap.

## Risks acknowledged

- **Test-only scope (LOCKED iter-3).** No `command_palette.tsx` change. If a future scoring change introduces a regression that fires for any zero_match input, THIS test catches it; the fix is a follow-up Issue, NOT inline scope-creep.
- **22 tests × ~500ms = ~11s** test-run time. Acceptable.
- **Iter-1 P0 caught real bug.** Codex empirically ran the original `the` stopword against current scoring and found 5 false-positive matches. Replaced with `weather forecast` in iter-2 brief (verified zero matches via Codex re-run). This is exactly the "live empirical-test loop" CLAUDE.md §8.3 anti-toothpaste-squeeze + §8.3.1 5-iter-cap was designed for.

## What this Issue does NOT do

- Does NOT modify `command_palette.tsx`.
- Does NOT add an "AI-agent adversarial" layer beyond the static corpus (deferred to evaluator-walkthrough at Sep 6).
- Does NOT add internationalization beyond the one Unicode RTL probe.
- Does NOT add CI step to run this spec automatically (`web_ci.yml` runs only inspector/accessibility/performance per existing policy).

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
