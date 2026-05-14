# G2 — vLLM ↔ OpenRouter dual-backend test findings

**GH#199 I-sov-001.** Test run 2026-05-13. Codex flagged G2 as P0: "vLLM cutover
is larger than a client swap... multiple direct OpenRouter-shaped paths...
estimated 2 days." This test measures the actual blast radius.

## Method

`.codex/I-sov-001/dual_backend_test.py` sent an identical chat-completion
request to:
- **OpenRouter** (real, US) — model `deepseek/deepseek-v4-pro` via the live key
- **Self-hosted OpenAI-compatible endpoint** — Ollama `qwen2.5:7b` at
  `localhost:11434/v1`. Ollama and vLLM both implement the plain OpenAI
  `/v1/chat/completions` contract; Ollama is the *minimal-fields* case, vLLM
  sits between Ollama and OpenRouter.

Both raw responses were then run through POLARIS's actual parsers:
`generator2/real_completion.py::_extract_text` and the
`openrouter_client.py` content/reasoning/usage parse path.

Raw responses saved at `.codex/I-sov-001/dual_backend_raw_responses.json`.

## Result — response-shape diff

| Field | OpenRouter (DeepSeek V4 Pro) | Self-hosted (Ollama, vLLM-equivalent) |
|---|---|---|
| top-level `provider` | `"Parasail"` | **absent** |
| `message.reasoning` | present + populated | **absent** |
| `message.reasoning_details` | present | **absent** |
| `message.refusal` | present | **absent** |
| `usage.cost` / `cost_details` | present | **absent** |
| `usage.*_tokens_details` | present | **absent** |
| `message.content` (str) | populated | populated |
| `usage.{prompt,completion,total}_tokens` | present | present |

**Both parsers passed against BOTH backends:**
- `_extract_text` → OK on both (correct content extracted)
- `openrouter_client` path → `content_ok=True` on both; `api_cost=0.0` on
  self-host is absorbed by `_impute_cost_from_tokens` (the §9.1 invariant-6
  backstop, built for exactly this token-only case)

## Critical observation

OpenRouter's `system_fingerprint` for DeepSeek V4 Pro was literally
`vllm-0.20.1rc1.dev1005+gcbf8428d0-tp4-ep-66a5fbd4`. **OpenRouter already
serves DeepSeek V4 Pro via vLLM** (through the Parasail provider). The OVH
H200 cutover is NOT an inference-engine change — it's the same vLLM engine,
different host. The only deltas are OpenRouter's *wrapper* fields
(`provider`, `usage.cost`, `reasoning` vs vLLM-native `reasoning_content`).

## Actual cutover surface — NARROWER than Codex's estimate

Codex estimated "2 days, audit every callsite, build a backend abstraction."
Evidence says the surface is **2 peripheral files, ~20 LOC**:

### Already vLLM-ready (no change needed)
- **`openrouter_client.py`** (2469 LOC, imported by 56 files) — already
  reads `OPENROUTER_BASE_URL` env var (line 44). Already checks BOTH
  `reasoning_content` (vLLM's key) AND `reasoning` (OpenRouter's key) at
  lines 931-932, 1044-1050, 1384-1393. The I-bug-088/089 reasoning-shape
  work already hardened it. No `provider`-field dependency anywhere.
- **`providers/llm_provider.py`** — already reads `OPENROUTER_BASE_URL`.
- `usage.cost` absence — handled by `_impute_cost_from_tokens` everywhere.

### Needs the cutover fix (~20 LOC, 2 files)
1. **`real_completion.py:40`** — `OPENROUTER_ENDPOINT` is hardcoded.
   Make it read `OPENROUTER_BASE_URL` (consistent with the central client).
   ALSO: its `_extract_text` reasoning fallback (line 249) only checks
   `message.reasoning`; add `message.reasoning_content` so an empty-content
   vLLM response with reasoning is recovered. ~8 LOC.
2. **`entailment_judge.py:155`** — endpoint hardcoded inline. Make it read
   `OPENROUTER_BASE_URL`. ~4 LOC. (Its `usage.cost` path already has the
   impute backstop.)

### Dress-rehearsal verification items (G1, not code — needs real vLLM)
- vLLM on the OVH H200 must be launched with `--reasoning-parser deepseek_r1`
  if we want DeepSeek V4 Pro's reasoning split into `reasoning_content`
  (otherwise reasoning merges into `content`, which is also fine for POLARIS).
- `entailment_judge.py` sends `response_format: {"type": "json_object"}`.
  vLLM supports this but the server must be started with guided-decoding
  enabled. Verify in the dress rehearsal.

## Verdict

Codex's G2 was directionally correct (hardcoded endpoints exist; reasoning
shape differs) but **overstated the blast radius**. The central client was
already hardened. The cutover is a ~20-LOC, 2-file change plus 2 vLLM
launch-flag checks at dress-rehearsal time. This fits comfortably in the
≤200-LOC CHARTER §3 cap for I-sov-001 and does not need a "backend
abstraction" rewrite.

Recommended I-sov-001 scope: env-configurable base URL in the 2 peripheral
files + `reasoning_content` fallback in `real_completion.py` + a unit test
that runs both response fixtures (OpenRouter-shape + plain-OpenAI-shape,
captured in `dual_backend_raw_responses.json`) through the parsers.
