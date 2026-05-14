HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-sov-001 diff iter 1 — env-configurable LLM endpoint for vLLM cutover

This is both the brief review AND the diff review (the brief was authored
alongside the diff; the G2 investigation in `g2_dual_backend_findings.md`
is the comprehensive pre-work). Review the diff against the brief.

## Brief

See `.codex/I-sov-001/brief.md` in this same diff. GH#199. Make the POLARIS
LLM call path point at the sovereign OVH H200 vLLM endpoint via one env var
(`OPENROUTER_BASE_URL`) instead of hardcoded OpenRouter URLs.

## Diff

`.codex/I-sov-001/codex_diff.patch` — 27 source insertions / 7 deletions
across 2 files + 103 test LOC. Canonical-diff-sha256 trailer included.

- `src/polaris_graph/generator2/real_completion.py` — endpoint derived from
  `OPENROUTER_BASE_URL`; `_extract_text` reasoning fallback checks
  `reasoning_content` (vLLM) OR `reasoning` (OpenRouter); empty-content
  error reports the endpoint.
- `src/polaris_graph/llm/entailment_judge.py` — `__init__` reads
  `OPENROUTER_BASE_URL` → `self._endpoint`; `judge()` POSTs to it.
- `tests/polaris_graph/generator2/test_real_completion.py` — +4 tests
- `tests/polaris_graph/llm/test_entailment_judge_cost.py` — +3 tests

## Evidence the cutover surface is exactly these 2 files

Verified via grep: only 3 files in `src/` make direct httpx/requests calls
to an `openrouter.ai` URL — `openrouter_client.py` (already env-configurable
via `OPENROUTER_BASE_URL`, line 44, no change needed), and the 2 files
changed here. The other 56 files matching `openrouter` import the client.
No code depends on the OpenRouter-specific `provider` top-level field.

## Test result

`PYTHONPATH=src pytest tests/polaris_graph/generator2/ tests/polaris_graph/llm/`
→ 238 passed, 4 skipped. The 4 skips are `test_strict_verify_entailment_live.py`
(needs a live API key — expected offline skip). The 5 new tests pass.

## Direct questions (also in brief.md §"Direct questions for Codex")

1. Reuse of `OPENROUTER_BASE_URL` vs a new `POLARIS_LLM_BASE_URL` — I reused
   it because `openrouter_client.py` + `llm_provider.py` already use it; one
   env var flips the whole stack with zero LOC in those 2 files. APPROVE?
2. `_extract_text` precedence: content-str → content-list → reasoning_content
   → reasoning. Correct order?
3. `entailment_judge.py` keeps the `Authorization: Bearer` header even when
   pointed at vLLM (harmless; and needed if OVH H200 vLLM is launched with
   `--api-key`). Leave unconditional?
4. Anything else blocking APPROVE?

## Out of scope (do not flag as missing — these are G1 dress-rehearsal checks)

- vLLM `--reasoning-parser deepseek_r1` launch flag (server config, not code)
- vLLM guided-decoding launch flag for `entailment_judge.py`'s
  `response_format: json_object` (server config, not code)
- The actual integration test on the real OVH H200 — that is GH#200 I-sov-002
  + the G1 dress rehearsal, gated on the hardware landing.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
