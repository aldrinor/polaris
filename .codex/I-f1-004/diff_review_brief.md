# Codex Diff Review Brief — I-f1-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates. Brief APPROVE'd iter 3.

- **Brief:** `.codex/I-f1-004/brief.md` (Codex APPROVE iter 3)
- **Diff:** `.codex/I-f1-004/codex_diff.patch` (canonical sha256 `75f12bb2b2eca1bc76f7184bcb9f797d89e6e37cb304ff2f688fc5c40d92bc3d`)
- **Audit:** `outputs/audits/I-f1-004/claude_audit.md`

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint tests/e2e/command_palette_adversarial.spec.ts` → clean.
- Codex iter-1 + iter-2 of brief empirically ran each corpus input through `score_template` → confirmed zero false-positives in zero_match set + correct sole match in exact_one_match set (after iter-2 `the` → `weather forecast` fix).

## Files (1, +82 net)

```
web/tests/e2e/command_palette_adversarial.spec.ts   NEW +82
```

CHARTER §1 200-LOC cap: +82 net. Well under cap.

## Specific risks for Codex Red-Team

1. **22-input corpus spec compliance.** Carney plan §F1 calls for "22-input adversarial corpus." The diff has `ZERO_MATCH_INPUTS.length === 15` + `EXACT_ONE_MATCH_INPUTS.length === 7` = 22. Verify count exactly.

2. **`exact_one_match` asserts BOTH count AND template-id** (P1-iter2 fix). For each positive input, `await expect(items).toHaveCount(1)` AND `await expect(page.getByTestId(\`palette-item-${expected_id}\`)).toBeVisible()`. Wrong sole-suggestion fails the visible-by-id check.

3. **No regression to existing palette specs.** New file is independent; doesn't touch `command_palette.tsx` or any other test.

4. **Test-only scope (no scoring change).** Verify no `command_palette.tsx` modifications in the diff.

5. **Hydration race.** Each test starts with `await expect(page.getByTestId("header-sign-in-link")).toBeVisible()` after `goto('/', { waitUntil: 'networkidle' })`.

6. **Whitespace-only input `"   "`.** `score_template("   ")` is truthy but yields zero substring matches across all 8 templates → `s > 0` filter empties → expected count 0. Aligns with zero_match.

7. **Unicode RTL probe `"‮لا"`.** No template contains Arabic or RTL override; score=0; count=0.

8. **`canonical-diff-sha256` trailer correctness.** `75f12bb2b2eca1bc76f7184bcb9f797d89e6e37cb304ff2f688fc5c40d92bc3d` produced via `git diff --cached -- :(exclude).codex/I-f1-004/ :(exclude)outputs/audits/I-f1-004/`.

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
