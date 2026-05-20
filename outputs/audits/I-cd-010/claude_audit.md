# I-cd-010 — Claude architect audit

**Issue:** GH#625 — stale model-ref cleanup. Closes #527 + #529 + I-cd-009 deferrals.
**Deliverable:** 13 files / +78 / -20 / +58 net LOC. 8 active doc/config edits + 9 intentional-legacy classification comments.
**Deps:** I-B-02 / I-cd-009 (PR #666, squash 30704bdc) — active runtime defaults are V4 Pro + Gemma 4 31B-it.

## What this PR ships

### Active doc/config (closes #625 P1 + iter-2 P1)

| File | Change |
|---|---|
| `src/polaris_graph/__init__.py:4` | "Uses Qwen 3.5 Plus" → "Uses DeepSeek V4 Pro generator + Gemma 4 31B-it evaluator (Carney demo lock per I-cd-009)" |
| `src/polaris_graph/llm/__init__.py:1` | "OpenRouter gateway to Qwen 3.5 Plus" → docstring with V4 Pro default per env |
| `src/polaris_graph/llm/openrouter_client.py:4` | Module docstring — same swap |
| `src/polaris_graph/llm/openrouter_client.py:930` | OpenRouterClient class docstring — same swap |
| `docker-compose.yml:56` | **(iter-1 P1)** `${VLLM_MODEL:-meta-llama/Llama-3.1-70B-Instruct}` → `${VLLM_MODEL:-ebircak/gemma-4-31B-it-4bit-W4A16-AWQ}` + comment about deferred I-cd-038 launch wiring |
| `docs/gemma_4_verification.md` §4.2 | Llama 4 Scout 109B-MoE fallback rewritten to FP16 `google/gemma-4-31B-it` at TP=4 on the same 4×H100 (same-model variant, different quantization — closes the safety net loop without forcing family-segregation + license sign-off re-run) |
| `docs/task_acceptance_matrix.yaml:205` | **(iter-1 P2 #3)** 1-line HISTORICAL note pointing at the §4.2 rewrite; original criterion preserved verbatim |
| `src/utils/cot_post_filter.py:286` | **(iter-2 P1)** `# pipeline-C COT classifier legacy` comment on `accounts/fireworks/models/llama-v3p3-70b-instruct` fallback |

### Intentional-legacy classification (closes #527 documented-legacy criterion)

| File | Change |
|---|---|
| `src/llm/kimi_client.py` | Module docstring augmented with "**Pipeline-C frozen** — KIMI K2.5 1T hardcoding is intentional legacy per CLAUDE.md §5" note |
| `src/agents/analyst_agent.py:585` | KIMI K2.5 primary — `# pipeline-C frozen` comment |
| `src/agents/analyst_agent.py:602` | Gemini fallback — `# pipeline-C frozen` comment |
| `src/agents/base_agent.py:158` | KIMI K2.5 primary — `# pipeline-C frozen` comment |
| `src/agents/base_agent.py:216` | Gemini fallback — `# pipeline-C frozen` comment |
| `src/agents/citefirst_synthesizer.py:4686` | KIMI K2.5 per-call — `# pipeline-C frozen` comment |
| `src/config/core.py` MODEL CONFIGS section | Banner classifying Gemini TierConfig + LLMConfig defaults as pipeline-C frozen per CLAUDE.md §5 |
| `src/providers/llm_provider.py:55` | **(iter-1 P2 #2)** OLLAMA_MODEL default classified as legacy Ollama fallback (not active under vLLM lock) |
| `src/polaris_graph/llm/openrouter_client.py` pricing table @ :254-258 | INTENTIONAL retention comment for env-overridden cost routing (qwen/qwen3-8b + z-ai/glm-5.1) |
| `src/polaris_graph/llm/openrouter_client.py` reasoning-first registry @ :510-512 | INTENTIONAL retention comment per `architectural_response_shape_centric_recovery` memory (GLM-5.1 + GLM-4.7 + GLM-5-turbo + GLM-5 needed for reasoning-first response shape recovery; do not remove) |

## #529 graph_v2/v3 reconciliation (verified by inheritance, no code change)

Acceptance criterion: "graph_v2/v3 default model references reconciled to current state; Pipeline-B behavior verified unaffected."

After I-cd-009's `openrouter_client.py:46` env-default change, the 6 `OpenRouterClient()` no-arg sites in `graph_v2.py` (lines 154, 216, 369, 469, 520) + `graph_v3.py` (line 723) auto-resolve to `OPENROUTER_DEFAULT_MODEL=deepseek/deepseek-v4-pro`. No code edit needed. Smoke verifies:

- `from src.polaris_graph.graph_v2 import build_v2_graph` → clean import
- `from src.polaris_graph.graph_v3 import build_v3_graph, build_and_run_v3` → clean import
- `OPENROUTER_MODEL` module-level constant = `deepseek/deepseek-v4-pro` (verified by literal print)

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | 1 P1 (docker-compose:56 missed stale Llama-3.1-70B vLLM fallback) + 3 P2 (agents kimi-k2p5 brief-inventory inaccuracy / OLLAMA_MODEL missed by grep / matrix Scout reference) |
| 2 | RC | 1 NEW P1 (`src/utils/cot_post_filter.py:286` ChatFireworks llama-v3p3-70b classifier fallback — pipeline-C COT path) + 2 P2 (`src/config/core.py` + `src/agents/base_agent.py:216` + `src/agents/analyst_agent.py:602` Gemini fallback executables needing pipeline-C-frozen classification / smoke command entrypoint names wrong: `build_v2_graph` not `build_v2_app`) |
| 3 | **APPROVE** | novel_p0=0 / continuing_p0=0 / p1=0; 2 P2 explicitly `accept_remaining` (gemini_client.py + live_deepseek_generator.py docstrings — non-blocking pipeline-C / no client-config default stale) |

## Why the iter-1 P1 was THE catch worth +1 iter

Codex live grep caught a vLLM service fallback string my iter-1 grep missed (pattern `Llama-3.1-70B` vs `Llama-3.1-70B-Instruct`). A docker-compose default of Llama-3.1-70B fallback means an unset VLLM_MODEL launches the sovereign profile on the WRONG model — even though I-cd-009 already updated the active runtime defaults. Codex's framing "this can start the sovereign vLLM profile on the wrong model" reframed the deferral logic: 1-line MODEL fallback swap is sufficient to close the "stale identifier" criterion; the full `--quantization compressed-tensors` + `--tensor-parallel-size 4` + GPU resource block wiring stays at I-cd-038. iter-2 brief made that split explicit; iter-3 APPROVE'd.

## Why the iter-2 P1 was THE catch worth +1 iter

`src/utils/cot_post_filter.py:286` builds a REAL `ChatFireworks` client with `accounts/fireworks/models/llama-v3p3-70b-instruct` as fallback when `POLARIS_COT_FILTER_MODEL` is unset. My iter-2 grep enumerated 3 src/agents files for kimi-k2p5 (good) but missed cot_post_filter (it imports langchain_fireworks directly, not via kimi_client). Codex caught this; iter-3 brief added the classification comment.

## Risk surface

- **Module docstring + comment changes (15 of 17 edits)**: ZERO runtime risk. Pure docstrings/comments.
- **§4.2 fallback rewrite in gemma_4_verification.md**: doc-only; no code path uses Llama 4 Scout. Rewrite preserves the safety net concept with a same-model variant.
- **docker-compose.yml:56 fallback swap**: optional `vllm` service (profile-gated). Active deployments set VLLM_MODEL explicitly. Behavior change is the IF-VLLM_MODEL-UNSET path picks up the locked AWQ artifact rather than Llama-3.1-70B — a docs/UX fix matching the Carney demo lock.

## Smoke

| Check | Result |
|---|---|
| `py_compile` on all 10 edited Python files | **all OK** |
| `yaml.safe_load` on `docker-compose.yml` + `docs/task_acceptance_matrix.yaml` | **OK** |
| `from src.polaris_graph.graph_v2 import build_v2_graph` | **OK** |
| `from src.polaris_graph.graph_v3 import build_v3_graph, build_and_run_v3` | **OK** |
| `OPENROUTER_MODEL` module-level default | `deepseek/deepseek-v4-pro` |
| `pytest tests/polaris_graph/llm/` | **11 passed** |
| `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` | **5 passed** |
| docker-compose offline render — vllm MODEL env | `${VLLM_MODEL:-ebircak/gemma-4-31B-it-4bit-W4A16-AWQ}` |

## Scope discipline

Out of scope per breakdown task split + Codex iter-3 explicit accept_remaining:
- Standalone test/smoke/preflight scripts that pin specific models for THEIR OWN test purposes (file names like `pg_smoke_glm5_structured.py`, `pg_preflight_032.py` literally name the pinned model).
- Historical `task_acceptance_matrix.yaml` V4 Flash + Scout entries beyond line 205 (updating retroactively would falsify the audit trail).
- docker-compose `command:` wiring for vLLM (full `--quantization compressed-tensors` + `--tensor-parallel-size 4` + GPU resource block) deferred to I-cd-038.
- `src/llm/gemini_client.py` + `src/llm/__init__.py` Gemini-package docstrings — Codex iter-3 P2 non-blocking (pipeline-C legacy).
- `src/polaris_graph/generator/live_deepseek_generator.py:2,4,390` V3.2-Exp comments — Codex iter-3 P2 non-blocking (no client/config default is stale; comments mention the variant the generator was built against).
