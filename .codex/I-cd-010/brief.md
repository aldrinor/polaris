HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Generator (active runtime)**: `deepseek/deepseek-v4-pro` (operator-locked).
- **Evaluator (active runtime)**: `google/gemma-4-31b-it` (locked I-cd-005-followup, PR #664).
- **Evaluator vLLM artifact**: `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` (load with `--quantization compressed-tensors`).
- **Engine**: vLLM (locked I-cd-007, PR #663).
- **Two-family**: `check_family_segregation` returns `('deepseek', 'gemma')`.
- **Pipeline-C is FROZEN** per CLAUDE.md §5 (`src/orchestration/`, `scripts/full_cycle.py`, KIMI K2.5 client, Gemini fallback path, agents, COT post-filter classifier).

# Codex brief review — I-cd-010 / GH#625: stale model-ref cleanup

Closes #527 + #529 + folds in iter-4 P2 items deferred from I-cd-009 + iter-1 P1 (docker-compose vLLM) + iter-2 P1 (cot_post_filter llama-v3p3-70b) + iter-2 P2 (Gemini defaults / smoke-cmd typos).

Acceptance per #625: "no stale model identifiers in clients/config."
Per #527: "All stale model references aligned to current state, OR explicitly documented as intentionally-pinned legacy."
Per #529: "graph_v2/v3 default model references reconciled to current state; Pipeline-B behavior verified unaffected."

Deps: **I-B-02 / I-cd-009 (GH#624)** merged (PR #666, squash 30704bdc).

## §0 — Iter trajectory + final fold-in

- **iter 1** RC: 1 P1 (`docker-compose.yml:56`) + 3 P2 (`src/agents/*` kimi-k2p5 brief-accuracy / `OLLAMA_MODEL` / matrix Scout reference).
- **iter 2** RC: 1 NEW P1 (`src/utils/cot_post_filter.py:286` `accounts/fireworks/models/llama-v3p3-70b-instruct` fallback) + 2 P2 (`src/config/core.py` + `src/agents/base_agent.py:216` + `src/agents/analyst_agent.py:602` Gemini fallback executables / smoke-cmd entrypoint names wrong).
- **iter 3** (this iter): all 6 distinct findings folded.

**iter-2 P1 (cot_post_filter)**: file is imported by `src/orchestration/graph.py` (pipeline-C FROZEN per CLAUDE.md §5) + `src/agents/citefirst_synthesizer.py` (pipeline-C). Same intentional-legacy classification as KIMI K2.5 + Gemini fallback — pipeline-C cheap COT classifier path. Resolution: 1-line `# pipeline-C COT classifier legacy; not under Carney demo lock per CLAUDE.md §5` comment.

**iter-2 P2 (Gemini defaults)**: `src/config/core.py:132-159` TierConfig+LLMConfig defaults (gemini-2.5-flash / gemini-3-pro-preview / provider=gemini) + `src/agents/base_agent.py:216` (gemini-2.5-flash fallback) + `src/agents/analyst_agent.py:602-614` (forced gemini-2.5-flash fallback). All pipeline-C Gemini-fallback paths. Resolution: 1 collective `# pipeline-C frozen — KIMI K2.5 primary + Gemini fallback per CLAUDE.md §5` classification comment per call site.

**iter-2 P2 (smoke commands)**: real symbols are `build_v2_graph` / `build_v3_graph` + `build_and_run_v3`. Fixed in §C.

## §A — Final scope: 13 files, ~17 edits

**Active doc/config changes (closes #625 P1 + iter-2 P1):**

| # | File | Lines | Change |
|---|---|---|---|
| 1 | `src/polaris_graph/__init__.py` | 4 | Module docstring "Uses Qwen 3.5 Plus..." → "Uses DeepSeek V4 Pro generator + Gemma 4 31B-it evaluator (Carney demo lock per I-cd-009)" |
| 2 | `src/polaris_graph/llm/__init__.py` | 1 | Module docstring "OpenRouter gateway to Qwen 3.5 Plus" → "OpenRouter gateway; default model = OPENROUTER_DEFAULT_MODEL (default deepseek/deepseek-v4-pro per I-cd-009)" |
| 3 | `src/polaris_graph/llm/openrouter_client.py` | 4 | Module docstring "Single gateway to Qwen 3.5 Plus" → swap as above |
| 4 | `src/polaris_graph/llm/openrouter_client.py` | 930 | Class docstring swap as above |
| 5 | `docker-compose.yml` | 56 | **(iter-1 P1)** `${VLLM_MODEL:-meta-llama/Llama-3.1-70B-Instruct}` → `${VLLM_MODEL:-ebircak/gemma-4-31B-it-4bit-W4A16-AWQ}` + adjacent comment "# Carney demo evaluator artifact; full --quantization compressed-tensors + --tensor-parallel-size 4 wiring at I-cd-038" |
| 6 | `docs/gemma_4_verification.md` | 142-152 | §4.2 fallback Llama 4 Scout 109B-MoE → FP16 `google/gemma-4-31B-it` at TP=4 on the same 4×H100 (same-model variant safety net; matches I-cd-009 lock-pair) |
| 7 | `docs/task_acceptance_matrix.yaml` | ~205 | **(iter-1 P2 #3)** 1-line HISTORICAL note that §4.2 fallback was rewritten post-I-cd-010 |
| 8 | `src/utils/cot_post_filter.py` | 286 | **(iter-2 P1)** Add `# pipeline-C COT classifier legacy; not under Carney demo lock per CLAUDE.md §5` comment on the fallback line |

**Intentional-legacy classifications (closes #527 documented-legacy criterion + iter-1 P2 #1 + iter-2 P2 #1):**

| # | File | Lines | Change |
|---|---|---|---|
| 9 | `src/llm/kimi_client.py` | 3-13 (module docstring) | Add a "**Pipeline-C frozen** — KIMI K2.5 1T hardcoding is intentional legacy per CLAUDE.md §5" note. NO code change. |
| 10a | `src/agents/analyst_agent.py` | 585 | `# pipeline-C frozen — KIMI K2.5 hardcoding intentional per CLAUDE.md §5` |
| 10b | `src/agents/analyst_agent.py` | 602 | `# pipeline-C frozen — Gemini fallback per CLAUDE.md §5` (extending the existing `# Fallback:` comment) |
| 11a | `src/agents/base_agent.py` | 158 | `# pipeline-C frozen — KIMI K2.5 hardcoding intentional per CLAUDE.md §5` |
| 11b | `src/agents/base_agent.py` | 216 | `# pipeline-C frozen — Gemini fallback per CLAUDE.md §5` |
| 12 | `src/agents/citefirst_synthesizer.py` | 4686 | `# pipeline-C frozen — KIMI K2.5 hardcoding intentional per CLAUDE.md §5` |
| 13 | `src/config/core.py` | ~129-160 | Single classification comment block above `# MODEL CONFIGS` header: `# pipeline-C frozen — Gemini TierConfig + LLMConfig defaults per CLAUDE.md §5; Carney demo runtime uses src/polaris_graph/* (OpenRouter V4 Pro + Gemma 4 31B-it)` |
| 14 | `src/providers/llm_provider.py` | 55 | **(iter-1 P2 #2)** `# Ollama legacy fallback; not active under vLLM lock` comment on OLLAMA_MODEL |

**openrouter_client.py legacy-support comment (already known per I-cd-009 deferral):**

| # | File | Lines | Change |
|---|---|---|---|
| 15a | `src/polaris_graph/llm/openrouter_client.py` | 254, 257 | 1 collective `# INTENTIONAL: pricing-table coverage for env-overridden models` comment above the entries |
| 15b | `src/polaris_graph/llm/openrouter_client.py` | 505, 511 | 1 collective `# INTENTIONAL: reasoning-first registry for response-shape-centric recovery (do not remove)` comment above _REASONING_FIRST_MODELS |

## §B — What this PR does NOT change (scope discipline)

- **`src/llm/kimi_client.py` MODEL_ID = "accounts/fireworks/models/kimi-k2p5"**: intentional pipeline-C; documented (file #9).
- **`src/polaris_graph/graph_v2.py` + `graph_v3.py`**: 6 `OpenRouterClient()` no-arg sites. With I-cd-009's openrouter_client.py:46 env default change, these auto-resolve to V4 Pro. Per #529 acceptance: reconciled by inheritance + verified by smoke. NO code change.
- **`docs/task_acceptance_matrix.yaml` historical V4 Flash + Scout entries** at lines 65, 74, 138, 147, 157, 183, 968: HISTORICAL acceptance criteria from green tasks. Updating retroactively would falsify the audit trail. Only line ~205 (Scout-fallback green criterion describing the gemma_4_verification.md content) gets a HISTORICAL note pointer.
- **Standalone test/smoke/preflight scripts** (`scripts/audit_dashboard_visual.py:240`, `scripts/build_walkthrough_pdf.py:100`, `scripts/inject_test_trace.py:110/133/635/844`, `scripts/pg_empirical_e1_e4.py:27/279`, `scripts/pg_mesh_preflight.py:57-58`, `scripts/pg_mesh_scale_test.py:83`, `scripts/pg_smoke_glm5_structured.py:47`, `scripts/pg_preflight_032.py:836`): file-name-pinned test purposes. Explicitly out of #527+#529 scope.
- **docker-compose `command:` wiring** for vLLM (`--quantization compressed-tensors`, `--tensor-parallel-size 4`, GPU resource block): deferred to I-cd-038 per Codex iter-3 of I-cd-009. This iter's P1 fix is the MODEL fallback string ONLY.

## §C — Smoke (real symbol names per iter-2 P2)

- `pytest tests/polaris_graph/llm/` — verify module-docstring + comment additions don't break imports.
- `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` — verify family-segregation invariant.
- `python -c "from src.polaris_graph.graph_v2 import build_v2_graph; print('graph_v2 OK')"` — graph_v2 imports clean.
- `python -c "from src.polaris_graph.graph_v3 import build_v3_graph, build_and_run_v3; print('graph_v3 OK')"` — graph_v3 imports clean.
- `python -c "from src.polaris_graph.llm.openrouter_client import OpenRouterClient, OPENROUTER_MODEL; print('default:', OPENROUTER_MODEL)"` — verify module-level default = V4 Pro.
- `python -m py_compile` on every edited Python file.
- `docker compose config 2>&1 | grep MODEL` (offline; unset VLLM_MODEL first) — verify vLLM service's MODEL env-var resolves to the AWQ artifact.

## §D — Risk surface

- **Module docstring + comment changes (15 of 17 edits)**: ZERO runtime risk. Pure docstrings/comments.
- **§4.2 fallback rewrite in gemma_4_verification.md**: doc-only.
- **docker-compose.yml:56 fallback swap**: optional `vllm` service (profile-gated). Active deployments set VLLM_MODEL explicitly; this is a docs/UX fix.

## §E — Residual question for Codex iter-3

Is the 13-file (~17-edit) scope NOW exhaustive for #625's "no stale model identifiers in clients/config" + #527's "intentionally-pinned legacy documented" + #529's "graph_v2/v3 reconciled" — with the 11-script + historical-matrix-entries (beyond ~205) genuinely out of scope?

Or is there another clients/config stale identifier my expanded grep still missed?

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
