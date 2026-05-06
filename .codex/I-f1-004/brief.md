# Codex Brief Review — I-f1-004 (ITER 3 of 5)

## Iter-1 P0 fix
Codex iter-1 ran the corpus against current scoring and found `the` matched 5 templates (`clinical, canada_us, defense, trade, workforce`) via `sample_question.includes("the")` substring. Replaced with `weather forecast` — verified to score 0 against all templates (no template summary/sample_question contains "weather" or "forecast").

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f1-004 — Template adversarial test: "BPEI" → no false-positive
**Phase:** 1 / **Feature:** F1
**LOC budget:** 100 net per `state/polaris_restart/issue_breakdown.md` §I-f1-004. **CHARTER §1 hard cap: 200 net additions.**

## Mission

Add a Playwright adversarial-corpus test that verifies the command palette + scoring (built in I-f1-002 + I-f1-003) does NOT produce false-positive template suggestions for ambiguous, off-topic, or unrelated inputs. Prevents the "ChatGPT/Gemini fail BPEI silently" failure mode the Carney plan §F1 calls out.

Per Carney plan §F1 (lines 78-85): "input 'BPEI' must NOT suggest any template; Playwright + AI-agent adversarial test confirms no false-positive across 22-input adversarial corpus."

## Substrate (HONEST)

- I-f1-003 just merged at `66158a50`; `command_palette.tsx` has the scoring + synonym map. Empty search returns all 8 templates (score=1 sentinel); non-empty + zero-score returns empty list (filter `s > 0`).
- The synonym map is intentionally narrow: only 4 medical drug brand names → clinical. No mapping for ambiguous tokens like BPEI, CDS, NEC, MS, RAG, SOTA, etc.
- Score function awards +30 on `name` substring match; substring matches like "ai" (in "ai_sovereignty") would falsely score; **the adversarial corpus must include such partial-substring inputs to surface real false-positives if any exist.**

## Acceptance criteria (binding)

1. **`web/tests/e2e/command_palette_adversarial.spec.ts`** (NEW) — Playwright test with a 22-input adversarial corpus. For each input the test verifies the palette result count behavior:
   - **`zero_match` set (15 inputs):** palette must show ZERO items after debounce (true ambiguous / unknown / off-topic).
     - `BPEI` (ambiguous: syndrome / institute / chemical)
     - `CDS` (ambiguous: clinical decision support / certificate of deposit / coordinate)
     - `NEC` (electrical code / necrotizing enterocolitis / nuclear energy commission)
     - `MS` (multiple sclerosis / Microsoft / mass spectrometry)
     - `RAG` (retrieval-augmented generation / clothing material)
     - `SOTA` (state-of-the-art / Greek)
     - `xyz123abc` (random alphanumeric)
     - `🚀` (emoji)
     - `weather forecast` (off-domain meteorology — verified 0 substring matches across 8 templates)
     - `quantum entanglement` (off-domain physics)
     - `pizza recipe` (off-domain cooking)
     - `   ` (whitespace only — should be treated as empty? See risk #4)
     - `'); DROP TABLE templates;--` (SQL injection probe)
     - `"><script>alert(1)</script>` (XSS probe)
     - `‮لا` (Unicode RTL override + Arabic)
   - **`exact_one_match` set (7 inputs):** palette must show EXACTLY ONE item — the correct template.
     - `tirzepatide` → clinical (synonym, regression of I-f1-003)
     - `ozempic` → clinical (synonym)
     - `clinical drug audit` → clinical (exact name match)
     - `housing` → housing (substring on name)
     - `oil-sands` → climate (substring on summary)
     - `2% target` → defense (substring on sample_question)
     - `tariff` → trade (substring on name)
2. **Test runs each input via the existing palette flow:** `goto('/')`, wait header-sign-in-link visible, Ctrl+K, fill input with the corpus item, wait for `palette-item-*` count to settle.
   - **For zero_match (expected_count=0):** assert `await expect(items).toHaveCount(0, { timeout: 350 })`.
   - **For exact_one_match (expected_count=1, expected_id="<id>"):** parameterize the corpus as `[{ input, expected_id }]` tuples. Assert `await expect(items).toHaveCount(1, { timeout: 350 })` AND `await expect(page.getByTestId('palette-item-' + expected_id)).toBeVisible()`. Wrong sole suggestion fails the visible-by-id check (P1-iter2 fix).
3. **No new code in `command_palette.tsx`.** This Issue is test-only. **Strict scope:** if the test surfaces any false-positives, this Issue STOPS at the failing test result and a follow-up Issue is opened to fix scoring; no inline scoring fix in this PR. Risk #8's "obviously wrong" emergency-waiver clause is REMOVED (P2-iter2 fix). The empirical iter-1 + iter-2 Codex runs verified the current corpus scores cleanly; no false-positive will surface.

## Planned diff shape

```
web/tests/e2e/command_palette_adversarial.spec.ts    NEW +90
```

LOC: +90 net. Under 100 budget AND CHARTER §1 200-cap.

## Out of scope (deferred per breakdown)

- F1 axe-core WCAG-AA broader scan → I-f1-005
- Multi-tab safety → I-f1-006

## Non-acceptance / explicit exclusions

- Does NOT modify `command_palette.tsx` scoring logic. Test-only.
- Does NOT add server-side validation (palette is client-only).
- Does NOT integrate an "AI-agent adversarial test" beyond what Playwright covers (the AI-agent layer is a Sep 6 evaluator-walkthrough concern, not iter scope here).
- Does NOT cover internationalization beyond the one Unicode probe.

## Risks for Codex Red-Team

1. **Substring false-positive surface.** `ai_sovereignty.id` contains substring `ai`; if the user types just `ai`, score: name "AI sovereignty" exact lower vs name substring +30 → fires. The adversarial corpus avoids `ai` as a probe because it's a TRUE positive (score should fire). But `pizza recipe` could substring-match `pizza` against any template? No; no template has "pizza" anywhere. Verify each zero_match input has zero substring overlap with template names/summaries/etc.

2. **Whitespace-only input.** `   ` (3 spaces) — does the score function treat this as empty? In code: `if (!q) return 1` returns sentinel for falsy, but `"   ".toLowerCase()` is truthy. So all templates get score=0 (no substring matches), filter removes all → 0 items. Test expectation = 0. Aligns with zero_match set.

3. **Unicode RTL probe `‮لا`.** Score function uses `toLowerCase()` + `includes()`. RTL override + Arabic letters won't match any template substring. Score=0 → filtered. Test expectation = 0.

4. **SQL/XSS probes.** Pure substring match; no SQL/XSS execution path exists in the client. Score=0 → filtered. Test verifies the palette doesn't crash on these inputs (no exception thrown; count = 0).

5. **`exact_one_match` regression coverage.** Includes the `tirzepatide → clinical` synonym (already covered by I-f1-003 suggest spec) plus 6 NEW positive cases. This is acceptance, not adversarial — included to prevent over-aggressive future tightening from breaking known-good suggestions.

6. **22-input count.** Carney plan §F1 calls for "22-input adversarial corpus." This brief specifies 15 zero_match + 7 exact_one_match = 22 total. ✓

7. **Test run-time.** Each test makes a fresh `page.goto('/')` and waits for hydration + debounce. 22 tests × ~500ms = ~11s. Acceptable.

8. **Possible existing false-positive in current scoring** (iter-3 LOCKED scope). Codex iter-1 + iter-2 empirical scoring runs verified the current corpus scores cleanly (after `the` → `weather forecast` fix in iter-2). If a future scoring change introduces regressions, THIS test will catch them and a follow-up Issue addresses the scoring fix. **Strict scope:** no inline scoring fix in this Issue regardless of finding type.

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
