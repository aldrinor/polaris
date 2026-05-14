# I-sov-001 Claude architect audit

**Issue:** GH#199 — Replace OpenRouter with sovereign vLLM
**Branch:** `bot/I-sov-001-vllm-base-url`
**Head commit:** `8ebcc9a5`
**Codex diff verdict:** APPROVE iter 1 of 5 (zero P0/P1/P2/P3, convergence_call: accept_remaining)

## Surface

| File | Change | LOC |
|---|---|---|
| `src/polaris_graph/generator2/real_completion.py` | endpoint from `OPENROUTER_BASE_URL`; `_extract_text` checks `reasoning_content` ∨ `reasoning`; empty-content error reports endpoint | +24/-? |
| `src/polaris_graph/llm/entailment_judge.py` | `__init__` reads `OPENROUTER_BASE_URL` → `self._endpoint`; `judge()` POSTs to it | +10/-1 |
| `tests/polaris_graph/generator2/test_real_completion.py` | +4 tests (reasoning_content fallback, content precedence, endpoint default + vLLM override) | +62 |
| `tests/polaris_graph/llm/test_entailment_judge_cost.py` | +3 tests (endpoint default, vLLM override, POST-targets-configured-endpoint) | +41 |

Total source change: 27 insertions / 7 deletions — well under the ≤200-LOC CHARTER §3 cap.

## Investigation that scoped this (G2)

`.codex/I-sov-001/dual_backend_test.py` + `g2_dual_backend_findings.md`:
ran an identical chat-completion request through real OpenRouter (DeepSeek
V4 Pro) AND a self-hosted OpenAI-compatible endpoint (Ollama, vLLM-equivalent
plain-OpenAI contract). Both raw responses run through POLARIS's actual
parsers. Key findings:

- Both POLARIS parsers passed against both backends.
- OpenRouter's `system_fingerprint` for DeepSeek V4 Pro is literally
  `vllm-0.20.1rc1...` — OpenRouter already serves it via vLLM. The OVH
  cutover is a hosting change, not an engine change.
- `openrouter_client.py` (2469 LOC, 56 importers) was already vLLM-ready.
- Only 2 peripheral files hardcoded the endpoint — the exact cutover surface.

This is the "be skeptical of Codex" application: Codex's 7-day-prep
consultation estimated G2 at "2 days, audit every callsite, build a backend
abstraction." The dual-backend test measured the real surface at ~27 src
LOC. Codex's iter-1 diff review then APPROVE'd the narrowed scope.

## Codex iteration trail

| Doc | Iter | Outcome |
|---|---|---|
| diff (+ brief, co-authored) | 1 | **APPROVE** — zero P0/P1/P2/P3; all 3 brief questions answered APPROVE; Codex verified the 5 new tests locally (5 passed) |

## Tests

`PYTHONPATH=src pytest tests/polaris_graph/generator2/ tests/polaris_graph/llm/`
→ 238 passed, 4 skipped. The 4 skips are `test_strict_verify_entailment_live.py`
(needs a live API key — expected offline skip). The 5 new tests pass.

## Verdict

READY TO MERGE. All Codex-required artifacts present:
- `.codex/I-sov-001/brief.md`
- `.codex/I-sov-001/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-sov-001/codex_diff.patch` (canonical-diff-sha256 trailer)
- `.codex/I-sov-001/codex_diff_audit.txt` (iter-1 APPROVE)
- `outputs/audits/I-sov-001/claude_audit.md` (this file)
- Investigation artifacts: `dual_backend_test.py`, `dual_backend_raw_responses.json`, `g2_dual_backend_findings.md`

## What ships

After merge, one env var — `OPENROUTER_BASE_URL=http://<ovh-h200-priv-ip>:8000/v1`
— flips the entire POLARIS LLM call path (generator + entailment judge +
central client) to the sovereign vLLM endpoint. No further code change needed
for the cutover.

## What's still gated (NOT this PR)

- **G1 dress rehearsal** — verify on the real OVH H200: vLLM launched with
  `--reasoning-parser deepseek_r1` (reasoning split) + guided-decoding
  (for `entailment_judge`'s `response_format: json_object`). These are vLLM
  server launch flags, not code.
- **GH#200 I-sov-002** — quality-unchanged validation on the sovereign topology.
- **GH#202 I-sov-004** — two-family segregation re-verification on vLLM.
