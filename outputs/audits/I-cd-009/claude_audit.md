# I-cd-009 — Claude architect audit

**Issue:** GH#624 — align model/config to DeepSeek V4 Pro + Gemma 4 31B-it
evaluator (Carney demo lock).
**Deliverable:** 22 files / 119 insertions / 82 deletions across active
runtime defaults, tests, and locked-pair documentation. iter-4 P1 test fix
included; iter-4 P2 module docstrings + standalone-script log-strings
explicitly deferred to I-cd-010 per the breakdown's task split.
**Deps:** I-B-01 (#622 canonical-pin reconciliation, MERGED) + I-C-06
(#638 evaluator license sign-off, MERGED).

## What this PR ships

### Active runtime defaults (10 files)

| File | Change |
|---|---|
| `.env.example` | `PG_GENERATOR_MODEL=v3.2-exp` → `=v4-pro`; family-override comment `qwen` → `gemma`; `OPENROUTER_DEFAULT_MODEL` swap; `VLLM_MODEL=Llama-3.1-70B-Instruct` → `=ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` with `# Load with --quantization compressed-tensors` note; preamble re-pinned to 2026-05-19 |
| `src/providers/llm_provider.py` | `OPENROUTER_MODEL` default `moonshotai/kimi-k2-0711` → V4 Pro; `VLLM_MODEL` default Llama-70B → ebircak AWQ |
| `src/polaris_graph/llm/openrouter_client.py` | `OPENROUTER_DEFAULT_MODEL` env-default `qwen/qwen3.5-plus-02-15` → V4 Pro |
| `src/polaris_graph/generator/analyst_synthesis.py` | `model: str = "deepseek/deepseek-v3.2-exp"` → `="deepseek/deepseek-v4-pro"` (+ docstring re-anchored to I-cd-009 lock) |
| `src/polaris_graph/generator/sentence_repair.py` | Two function defaults swapped |
| `src/polaris_graph/clinical_generator/real_completion.py` | Module docstring example + `load_config_from_env` fallback `z-ai/glm-5.1` → V4 Pro |
| `src/polaris_graph/api/disambiguation_route.py` | Label-client fallback `z-ai/glm-5.1` → V4 Pro |
| `scripts/regate_v23.py` | Generator fallback v3.2-exp → V4 Pro; evaluator fallback `qwen/qwen3-8b` → `google/gemma-4-31b-it` |
| `scripts/deploy.sh` | Generated-env template `OPENROUTER_DEFAULT_MODEL=moonshotai/kimi-k2.5` → V4 Pro |
| `src/polaris_v6/api/transparency.py` | Evaluator env default `qwen/qwen-2.5-72b-instruct` → `google/gemma-4-31b-it` |

### iter-4 P1 test fix (1 file)

`tests/polaris_graph/clinical_generator/test_real_completion.py:46-51` —
`test_load_config_default_model` updated to assert `deepseek/deepseek-v4-pro`
instead of the now-stale `z-ai/glm-5.1`. Without this fold-in the
`real_completion.py:80` source change would land a failing unit test.

### Doc + locked-pair consistency (10 files)

| File | Change |
|---|---|
| `docs/transparency.md` | Evaluator default disclosure → Gemma 4 31B-it |
| `docs/runbook.md` | Default pair + invalid-pair example (same-family) updated to V4 Pro + Gemma 4 31B-it + V4 Pro/V4 Flash for the family-collision example |
| `docs/models/serving_engine_pick.md` | All Maverick refs → Gemma 4 31B-it AWQ W4A16 artifact + `--quantization compressed-tensors`; lock-history note added |
| `architecture.md` | Default pair docs + env-var table updated |
| `src/polaris_graph/audit_ir/model_pin.py` | Docstring example pair updated |
| `docs/gemma_4_verification.md` | §3.2 NVFP4 recipe → §3.2 Carney demo evaluator AWQ W4A16 recipe; §2 row + sources updated to ebircak weights |
| `docs/task_acceptance_matrix.yaml` | task_0_8 green criteria description: NVFP4 + V4 Flash → AWQ + V4 Pro |
| `docs/carney_handover/runbook.md` | LLM serving row + active-pairing line: V4 Flash → V4 Pro |
| `docs/carney_handover/5min_video_script.md` | Demo narration: V4 Flash → V4 Pro |
| `helm/polaris/values.yaml` | `vllm.model` Llama-3.1-70B → ebircak AWQ + comment "Not wired into active templates; full launch wiring at I-cd-038" |

### Trajectory log

`state/polaris_restart/iteration_trajectory.md` — appended per §8.3.5 with
brief iter-5 APPROVE record + final scope + dropped/deferred items.

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | initial 9-line scope (.env.example, llm_provider.py, generator function defaults, regate_v23.py) |
| 2 | RC | +4 P1 +3 P2 — openrouter_client.py:46, real_completion.py:80, disambiguation_route.py:68, deploy.sh:662, transparency.py:218, transparency.md:29, runbook.md:153-168 |
| 3 | RC | +1 NOVEL P1 +4 P2 — docker-compose.yml:56 surfaced then dropped (deferred to I-cd-038), regate_v23.py:116, helm/values.yaml:69, docs/models/serving_engine_pick.md, architecture.md:175-176/337-339, audit_ir/model_pin.py:25-26, real_completion.py:7 |
| 4 | RC | +1 NOVEL P1 +3 P2 — **test_real_completion.py:46-51 test breakage** (real iter-4 catch — would have shipped a broken test), gemma_4_verification.md, task_acceptance_matrix.yaml:959, carney_handover/runbook.md:17/48, 5min_video_script.md:41 |
| 5 | **APPROVE** | novel_p0=0 / continuing_p0=0 / p1=0; 2 P2 deferred to I-cd-010 (module docstrings + standalone-script log-strings) per breakdown task split |

## Why the iter-4 P1 was the binding catch

iter-3 brief was clean on every active-runtime default, but
`real_completion.py:80` swap from `z-ai/glm-5.1` to V4 Pro would have broken
`test_real_completion.py:test_load_config_default_model` — a pure unit test
asserting the documented default. The test would have failed CI immediately
on the diff Codex review's smoke (or worse, on `pytest_v6` post-merge).
iter-4 Codex caught this with a verbatim line-number cite; iter-5 brief
incorporates the test update as scope item #19, and the local smoke run
confirms 26/26 tests pass with the new assertion.

## Risk surface + side findings

- **Two-family enforcement code unchanged.** `check_family_segregation`
  already returns `('deepseek', 'gemma')` for the locked pair — the map
  was updated in I-cd-005-followup (PR #664). No code change needed here.
- **Docker compose vLLM service deferred.** `docker-compose.yml:56`
  surfaced in iter 3 but full wiring (`--quantization compressed-tensors`
  + `--tensor-parallel-size 4` + GPU resource block) belongs with
  I-cd-038 deployment, not a config-default swap.
- **Two-box runtime split deferred.** `llm_provider.py` still has a single
  `VLLM_BASE_URL` / `VLLM_MODEL`; the locked topology has separate Box 1
  (8×H200, V4 Pro generator) and Box 2 (4×H100, Gemma 4 31B-it AWQ
  evaluator). The two-URL refactor belongs with I-cd-038.
- **Llama 4 Scout §4.2 fallback** in `docs/gemma_4_verification.md` is now
  stale (was Gemma 4 31B's fallback under the old NVFP4 design). The
  correct demo safety net is FP16 `google/gemma-4-31B-it` at TP=4 on the
  same 4×H100. Codex iter-5 accepted leaving Scout untouched as I-cd-010
  scope (broader stale-ref cleanup).
- **Pricing tables + reasoning-model registry** in `openrouter_client.py`
  still list `qwen/qwen3-8b` + `z-ai/glm-5.1` etc. as cost/registry
  entries. These are NOT defaults; they exist to price/route legacy or
  multi-model runs. Defer to I-cd-010 per the breakdown.

## Smoke

| Check | Result |
|---|---|
| `pytest tests/polaris_graph/clinical_generator/test_real_completion.py` | **26 passed** |
| `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` | **5 passed** |
| `py_compile` on each of the 10 edited Python files | **all OK** |
| `bash -n scripts/deploy.sh` | **OK** |
| `yaml.safe_load` on helm/polaris/values.yaml | **OK** |
| `yaml.safe_load` on docs/task_acceptance_matrix.yaml | **OK** |

## Scope discipline

This is a config-default + locked-pair-doc-consistency PR. It does NOT:
- Order GPUs (I-cd-038, [GL gate]).
- Run the FP4 readiness spike (I-cd-011).
- Final-hold OVH capacity (I-cd-037).
- Cleanup stale model refs in docstrings + standalone scripts (I-cd-010).
- Wire the two-box runtime architecture in `llm_provider.py` (I-cd-038).
- Update docker-compose vLLM service (I-cd-038).
