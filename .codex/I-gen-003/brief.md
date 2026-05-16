# I-gen-003 brief — DeepSeek V4 Pro as the multi_section generator

**GH:** #495
**Branch:** `bot/I-gen-003-v4pro-cot-handler`
**Status:** smoke #3 complete — result below. **This is a SHIP-vs-REVERT decision for Codex, not a clean APPROVE.**

## Operator directive (the constraint)

2026-05-14, repeated emphatically 6×: **"I want V4 Pro." "Then fucking fix it." "Not obsolete V3.2." "Is it fucking clear to you?"** The operator wants DeepSeek V4 Pro as THE generator; V3.2-Exp is to be treated as obsolete. This brief must be read against that directive — see the **user-directive conflict** section before issuing a verdict.

## Background

I-bug-091 (2026-05-09) reverted `PG_GENERATOR_MODEL` to V3.2-Exp because V4 Pro is reasoning-first and crashed the multi_section pipeline: it exhausts `max_tokens` mid-planning → I-bug-089 SF-15 fail-loud `RuntimeError` → pipeline abort. I-gen-003 set out to fix that.

## The diff — 5 changes, ~115 src LOC (3 committed, 2 new this iter)

1. **`_call_section` HARD OUTPUT CONTRACT** *(committed `0c55a4bc`)* — on `tighter_retry=True` for reasoning-first models, append an explicit anti-CoT block.
2. **`_run_section` bounded multi-retry + budget escalation** *(committed `0c55a4bc`, escalation new this iter)* — single retry `if` → bounded `while`; `_regen_needed()` fires at `total_in == 0` too; `_max_regens = 3` for reasoning-first; retry budget escalates `base*(1+0.5*N)` → 30k/40k/50k.
3. **`PG_GENERATOR_MODEL` default → `deepseek/deepseek-v4-pro`** *(committed `0c55a4bc`)*. Also: `PG_MAX_COST_PER_RUN` default `0.10 → 10.00` *(committed `9a62ac1b`)* — the `0.10` cap was V3.2-era and false-fired on V4 Pro (smoke #1 died on it).
4. **`ReasoningFirstTruncationError(RuntimeError)` + reasoning-first floor `6000 → 20000`** *(NEW this iter)* — the I-bug-089 SF-15 check raises the typed exception instead of bare `RuntimeError`; the floor is raised because smoke #2 proved V4 Pro emits ~5300+ reasoning tokens (the old I-bug-090 "~2500" estimate was wrong).
5. **`_call_section` catches `ReasoningFirstTruncationError`** *(NEW this iter)* — logs a loud WARNING, returns `("", 0, 0)` so a truncation degrades to an honest `abort_no_verified_sections` rather than a hard `error_unexpected` crash.

## Smoke #3 result — HONEST

`run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm`, `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro`, 2026-05-14.

**Result: `status=abort_evaluator_critical`, cost $0.0746, wall 2231s (~37 min).**

**This did NOT meet the brief's stated PASS criterion** (`status=ok*`/`partial*`). State that plainly. But the breakdown matters:

### What the fix DID achieve (load-bearing — changes 4+5)
- **V4 Pro no longer crashes the pipeline.** Zero `ReasoningFirstTruncationError` raised — the 20000 floor held; V4 Pro completed all 6 sections without a truncation crash. The I-bug-091 revert reason is genuinely fixed.
- Generator produced a **complete 6-section report**: `sections_kept=6`, `sentences_verified=21`, `sentences_dropped=52`, `verified_words=437`, total `words=1835`, plus a **1398-word Analyst Synthesis** (coherent, well-hedged, clinically appropriate — see `report.md`).
- **V4 Pro verified MORE sentences than V3.2-Exp**: 21 vs the V3.2-Exp baseline's 13 (same question, 2026-05-13 smoke). Both dropped 52.

### What the fix did NOT achieve
- **`abort_evaluator_critical`** — the evaluator gate (Gemma 4 31B) blocked release. These ARE generator output failures, not "downstream" noise:
  - **PT11 FAIL**: "3 numeric claims without adjacent citation marker (out of 24 decimals in prose)" — V4 Pro citation discipline.
  - **Qwen `needs_revision` × 3**: `citation_tightness` ("claims in Safety/Mechanism/Regulatory lack adjacent citations"), `flow` ("Efficacy section is a single sentence ... reads as disjointed notes"), `completeness` ("fails to cover Contraindications / warnings" — this one is a corpus gap, 1/7 topics uncovered, not a generator fault).
  - Qwen verdicts: 2 good (`hedging_appropriateness`, `tone_consistency`) / 3 needs_revision.
  - V3.2-Exp on the same question got `ok_qwen_advisory` — V4 Pro trips the gate **one threshold worse** than V3.2 despite verifying more sentences.
- **Changes 1+2 (HARD OUTPUT CONTRACT + bounded regen loop) were EMPIRICALLY INERT.** 12 regen attempts (3 each × Efficacy/Safety/Regulatory/Comparative) lifted **zero** verified sentences — kept_fraction was byte-identical across all 3 regens per section (Efficacy 0.10→0.10→0.10, Safety 0.25→0.25→0.25, Regulatory 0.36→0.36→0.36, Comparative 0.18→0.18→0.18). The escalated budget + anti-CoT prompt did not change V4 Pro's output style. ~20 min of the 37-min wall time was spent on regens that produced nothing. **This is dead code on V4 Pro as it stands.**

## The decision for Codex (this is the real ask)

Not "is the generator fix done." The honest question:

**(a) APPROVE — ship V4 Pro at this quality.** V4 Pro completes the pipeline, verifies more sentences than V3.2, produces a strong Analyst Synthesis. `abort_evaluator_critical` on PT11 + citation_tightness is a real but bounded quality gap; treat the citation-discipline fix + the inert regen loop as follow-up Issues. Honors the operator directive.

**(b) REQUEST_CHANGES — revert `PG_GENERATOR_MODEL` to V3.2-Exp, keep changes 4+5.** Changes 4+5 (typed exception + 20000 floor + catch) are load-bearing future-model insurance and stay. Change 3's model flip reverts until V4 Pro's citation discipline matches V3.2's `ok_advisory`. **This directly contradicts the operator's repeated "I want V4 Pro" directive — if Codex picks (b), it likely needs operator escalation.**

**(c) REQUEST_CHANGES — specific harder intervention.** If Codex sees a concrete generator-side fix for V4 Pro's citation discipline that's in I-gen-003's scope (e.g. a different prompt structure, a post-generation citation-binding pass, a different `reasoning.effort` setting), name it.

## Direct questions for Codex

1. **(a)/(b)/(c)** — which, and if (b), do you escalate the operator-directive conflict or do I?
2. **The inert regen loop (changes 1+2):** 12 retries, zero lift, ~20 min wasted/run. Strip it (revert `_call_section`/`_run_section` to pre-`0c55a4bc`), or keep as scaffold for a future reasoning-first model? It is currently shipped *labelled-honest, not pretending-to-work* — but it is dead weight on V4 Pro.
3. **PT11 / citation_tightness** — is a post-generation citation-binding pass the right scope for I-gen-003, or a separate Issue?
4. `20000` floor + escalation — kept even if (b) is chosen (future-model insurance)?
5. Anything else.

## Files I have ALSO checked and they're clean

- `_REASONING_FIRST_MODELS` (openrouter_client.py:388) — contains v4-pro + v4-flash; GLM is in the *separate* `_ALWAYS_REASON_MODELS` set — the floor raise + escalation do not touch GLM.
- I-bug-088 response-shape recovery — unchanged, complementary.
- I-bug-108 sentence-repair loop — first-pass only; in smoke #3 it ran (`Mechanism 5/5`, `Long-term Outcomes 4/5`) and is the main reason `sentences_verified=21` not lower.
- Two-family invariant — untouched; `PG_EVALUATOR_MODEL` (Gemma 4 31B) unchanged.
- Non-reasoning-first regression surface — `_max_regens=1`, `total_in>0` gate half, `if model in _REASONING_FIRST_MODELS` guards — V3.2-Exp / qwen / GLM-non-members get byte-identical behavior.
- `_call_section` `finally` (client close) runs on the new `except` path — verified.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
decision: a | b | c
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
operator_escalation_needed: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
