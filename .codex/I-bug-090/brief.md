# Codex Brief — I-bug-090: reasoning-first min_max_tokens floor

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- DO NOT call exec / rg. Brief contains all data.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What just happened

I-bug-088 (PR #339) + I-bug-089 (PR #340) merged. Live BEAT-BOTH validation on V4 Pro showed:

```
02:52:44 generate completed: 1705 in/2500 out/2500 reasoning tokens
[FATAL] I-bug-089: reasoning-first model deepseek/deepseek-v4-pro truncated mid-planning.
        content empty, reasoning has 10202 chars but no [#ev:] markers and ends mid-sentence.
```

Section 1 of multi-section generation: V4 Pro hit the 2400 max_tokens cap, emitted 2500 tokens (provider over-shoot) entirely to reasoning_content, content empty. I-bug-089 fail-loud raised correctly. Pipeline aborted (no caller-side retry).

**Two distinct empirical findings:**

1. **OpenRouter does NOT honor `reasoning.max_tokens` for V4 Pro** — we set it to `0.4 * 2400 = 960` per I-bug-089, but the model still emitted 2500 reasoning tokens. The provider-side cap is ineffective for this model.
2. **2400 total budget is insufficient for V4 Pro** to do CoT-style reasoning AND emit answer. Need a larger total budget so the 40/60 split actually leaves room for content even if the cap is ignored.

## Implementation plan (5 src LOC + 17 test LOC)

Mirror the existing `PG_GLM5_MIN_MAX_TOKENS` pattern at `openrouter_client.py:1152`. Inside the I-bug-089 elif branch, after setting the reasoning cap, floor `body["max_tokens"]` to 6000:

```python
# I-bug-090: OpenRouter does NOT enforce reasoning.max_tokens for V4 Pro
# on the provider side — the model still emits ~2500 reasoning tokens
# regardless. Floor max_tokens to a value large enough that 40/60 split
# leaves room for both reasoning AND content. Empirically observed at
# 2400 max: reasoning eats the whole budget, content empty, I-bug-089
# fail-loud raises. 6000 floor → ~2500 reasoning + ~3500 content, both fit.
_min_tokens = int(os.getenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", "6000"))
if body.get("max_tokens", 0) < _min_tokens:
    body["max_tokens"] = _min_tokens
```

## Test surface

1. `test_v4_pro_min_max_tokens_floor_default_is_6000` — env-var default check.
2. Existing 7 I-bug-088/089 unit tests + 6 I-bug-088 normalize tests = 13 total regression. Run locally:
   ```
   13 passed in 6.83s
   ```

## Constraints

1. No regression to I-bug-088 promote path (test 4: GLM-5 legacy regression continues to pass).
2. GLM-5 already has `PG_GLM5_MIN_MAX_TOKENS=4096` floor; the new V4 Pro floor at 6000 doesn't override (GLM-5 path fires first in if/elif chain).
3. Caller-passed `max_tokens=N` from caller can EXCEED the floor (good — caller wants high) but cannot be less than it (good — V4 Pro needs 6000).
4. Two-family invariant unchanged. Budget-guard invariant unchanged.
5. CHARTER §3 LOC: 5 src + 17 test = 22 LOC, well under 200.
6. Env-var override `PG_REASONING_FIRST_MIN_MAX_TOKENS` available for tuning.

## Why 6000 specifically

Empirical: V4 Pro emits 2500 reasoning tokens (provider hard floor on its CoT). For section_max_tokens=2400, content gets 0. For 6000, reasoning still ~2500 + content gets ~3500 = full SURPASS-trial section comfortably. Tested via the live BEAT-BOTH run that just produced the I-bug-089 fatal.

If V4 Pro ever bumps its reasoning floor (e.g. to 5000 in a future model release), this needs adjustment — env var enables that without code change.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: []
```
