---
status: research_artifact
locked_decision: none (advisory research, no architecture lock here)
related_lock: docs/polaris_step_b_full_set_audit_2026_05_27.md
---

# V4 Pro root-cause analysis — 2026-05-25 night

**Trigger:** Operator picked Option B1 ("debug deeply"). Live smoke on
`clinical_tirzepatide_t2dm` showed 87% sentence drop, 68 sentences with no
provenance token, 12 with fabricated numbers — despite `manifest.generator
= deepseek/deepseek-v4-pro` confirming V4 Pro really ran.

## Smoking gun — the I-gen-003 fix was REVERTED 1.5 hours after merge

- `0c55a4bc` (2026-05-14 09:09) — I-gen-003 adds HARD OUTPUT CONTRACT
  prompt + bounded 3-retry for reasoning-first models.
- `cb7feaa3` (2026-05-14 10:47) — **STRIPS the HARD OUTPUT CONTRACT** in
  I-gen-003 iter 2. Commit body verbatim:
  > "Smoke #3 proved the blind regen loop (changes 1+2) lifted zero
  > verified sentences across 12 retries on V4 Pro, and Codex caught that
  > _REASONING_FIRST_MODELS is a superset of _ALWAYS_REASON_MODELS — so
  > the escalation mistreated GLM. Strip changes 1+2: revert
  > _call_section's HARD OUTPUT CONTRACT and _run_section's bounded
  > regen loop + budget escalation to pre-0c55a4bc."

So the fix that was supposed to land never actually shipped. What ships
today (verified at `multi_section_generator.py:880-887`):

```python
if tighter_retry:
    system += (
        "\n\nREGEN NOTE: the previous draft had multiple sentences "
        "without verifiable provenance. Every sentence MUST cite a "
        "specific [ev_XXX] and the claimed numbers must appear in "
        "that evidence's direct_quote. When in doubt, cite multiple "
        "sources or drop the claim."
    )
```

This is a weak suggestion, not the HARD OUTPUT CONTRACT. No anti-CoT
prohibition. No `reasoning_enabled=False`. No temperature change. No
stop sequences. V4 Pro happily ignores it.

## Root causes ranked

### RC-1 — Reasoning-first token starvation (VERY HIGH confidence)
- `openrouter_client.py` defaults: `reasoning_enabled=True`, `effort="high"`.
- I-bug-089 caps reasoning at 40% of max_tokens. With max_tokens=16384,
  reasoning gets ~6500 tokens, content gets ~10000.
- V4 Pro's reasoning channel fills 6500 tokens with planning text ("Let
  me check the triggers. First, look for mechanism-of-action
  vocabulary..." — verified in `reasoning_trace.jsonl`), then content
  begins WITH CoT mode still active.
- The 19,843-char CoT leak in I-bug-091 evidence (`Run 3 PR#341+6000`)
  is the same phenomenon.

### RC-2 — System vs user prompt weighting (HIGH confidence)
- The HARD OUTPUT CONTRACT (when it existed) was appended to the SYSTEM
  prompt. V4 Pro may down-weight system messages on the retry path.
- The `cb7feaa3` smoke result ("12 retries → 0 verified gain") is
  consistent with system-message-ignored behavior.

### RC-3 — `reasoning_effort="high"` default triggers think-max (MEDIUM-HIGH)
- DeepSeek docs (https://api-docs.deepseek.com/guides/thinking_mode):
  > "think-max mode utilizes the full context window for reasoning
  > before providing the final answer."
- POLARIS doesn't pass `reasoning_effort` to `_call_section`, so it
  inherits openrouter_client's default. Confirmed at
  `multi_section_generator.py:906-911`:
  ```python
  response = await client.generate(
      prompt=prompt, system=system,
      max_tokens=max_tokens, temperature=temperature,
  )
  ```
  No `reasoning_effort`. No `reasoning_enabled=False` override.

### RC-4 — No stop sequences (MEDIUM)
- Model free to emit `"Let me"`, `"First, I"`, `"Looking at"` tokens.
- Both DeepSeek API and OpenRouter support `stop` parameter; POLARIS
  doesn't use it.

### RC-5 — Temperature 0.3 (LOW)
- `section_temperature: float = 0.3` (multi_section_generator.py:3331).
- Cold but not maximally cold. 0.1 would force more determinism.

## Recommended fix (combine RC-1 + RC-2 + RC-3 fixes)

On the retry path (`tighter_retry=True`) for reasoning-first models:

1. **Set `reasoning_enabled=False`** — turn off V4 Pro's thinking
   channel entirely. Force direct content-only output.
2. **Drop temperature to 0.1** — maximum determinism.
3. **Re-add HARD OUTPUT CONTRACT** — paired with #1, the contract has
   a fighting chance because there's no reasoning channel to
   compete with.
4. **Add stop sequences:** `["Let me", "First, I will", "Looking at",
   "I need to", "The evidence shows", "Sentence 1:", "Sentence 2:"]`.
5. **Add ONE few-shot example** of `[#ev:ev_XXX:Y-Z]` citation format in
   the system prompt (V4 Pro's training distribution may not include
   the POLARIS-specific token shape; one worked example helps land it).

Why combined fix (not single lever): Smoke #3 already proved the HARD
CONTRACT ALONE fails. The combination addresses the actual mechanism —
disable the channel that was ignoring the contract, force cold sampling,
forbid the leak tokens.

## Fallback plan if combined fix doesn't converge

- FIX #4 from the research: JSON-schema-bound output. Convert per-sentence
  cited prose into JSON array `[{sentence, citations[]}]` then render to
  markdown. Higher implementation cost. Use only if combined fix fails.

## Test plan

1. Apply combined fix locally.
2. Re-smoke `clinical_tirzepatide_t2dm`.
3. Pass criteria:
   - `sentences_verified / total >= 0.60` (currently 0.13)
   - `number_not_in_any_cited_span == 0` (currently 12) — non-negotiable per §-1.1
   - CoT leakage instances in rendered report == 0 (currently 2)
   - `evaluator_gate.release_allowed == true` (currently false)
4. If pass: run on 2-3 more clinical questions to confirm not a one-off.
5. If fail: investigate which lever didn't fire, escalate to fallback.

## Sources

- https://api-docs.deepseek.com/guides/thinking_mode
- https://openrouter.ai/deepseek/deepseek-v4-pro/api
- Commit `cb7feaa3` — local git, body documents the strip rationale
- Commit `0c55a4bc` — original HARD CONTRACT add
- Commit `7089bfe6` — I-bug-091 19,843-char CoT leak evidence
- `reasoning_trace.jsonl` from this smoke — V4 Pro's planning text
  verbatim
- BerriAI/litellm #26395 — V4 Pro multi-turn reasoning_content (not
  relevant to POLARIS single-turn-per-section path)
