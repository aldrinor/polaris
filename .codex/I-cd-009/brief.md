HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Generator**: `deepseek/deepseek-v4-pro` (operator-locked).
- **Evaluator**: `google/gemma-4-31b-it` (locked I-cd-005-followup, PR #664).
- **Evaluator 4×H100 vLLM runtime artifact**:
  `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` (load with
  `--quantization compressed-tensors` server-side; not client config).
- **Engine**: vLLM (locked I-cd-007, PR #663).
- **Two-family**: `check_family_segregation` returns `('deepseek', 'gemma')`.

# Codex brief review — I-cd-009 / GH#624: align model/config to V4 Pro + Gemma 4 31B-it

Acceptance per breakdown: "config points at DeepSeek V4 Pro 1.6T + the
licensed ~400B evaluator." Deps `I-B-01` + `I-C-06` both merged.

## §0 — 4-iter consolidation (final scope)

The brief went through 4 Codex iterations, each adding stale defaults Codex
caught via web/repo-search:
- **iter 1**: initial 9-line scope (`.env.example`, `llm_provider.py`,
  generator function defaults, `regate_v23.py`). RC.
- **iter 2**: +4 P1 + 3 P2 — `openrouter_client.py:46` Qwen default,
  `real_completion.py:80` GLM fallback, `disambiguation_route.py:68` GLM
  fallback, `deploy.sh:662` Kimi template, `transparency.py:218` Qwen
  default disclosure, `transparency.md:29` + `runbook.md:153-168` Qwen
  documentation. RC.
- **iter 3**: +1 NOVEL P1 + 4 P2 — `docker-compose.yml:56` sovereign vLLM
  (dropped iter-4 per Codex alternative; deferred to I-cd-038),
  `regate_v23.py:116` evaluator fallback, `helm/values.yaml:69`,
  `docs/models/serving_engine_pick.md` Maverick refs,
  `architecture.md:175-176,337-339`, my comprehensive grep added
  `audit_ir/model_pin.py:25-26` + `real_completion.py:7` docstrings. RC.
- **iter 4**: +1 NOVEL P1 + 3 P2 — **`tests/polaris_graph/clinical_generator/test_real_completion.py:46-51` asserts the OLD GLM fallback and will FAIL after the `real_completion.py:80` change** (must include the test update); `docs/gemma_4_verification.md` + `docs/task_acceptance_matrix.yaml:959` still describe NVFP4 artifact (P2; lock-consistency); `docs/carney_handover/runbook.md:17,48` + `5min_video_script.md:41` describe V4 Flash as the demo generator (P2; handover-doc consistency); module docstrings `__init__.py` + `openrouter_client.py:4/930` still say Qwen 3.5 Plus (Codex explicitly accepted "I-cd-010 boundary"). RC.

Final scope: **24 changes across 14 files** (23 from iters 1-3 + 1 test
update from iter 4 + 3 handover/lock-consistency doc updates). The iter-4
module-docstring + script log-string P2s are EXPLICITLY DEFERRED to
I-cd-010 per Codex's own framing.

## §A — Final scope: 24 changes across 14 files

**Code defaults (active runtime):**

| # | File | Lines | Change |
|---|---|---|---|
| 1-5 | `.env.example` | 61, 62, 68, 70, 145 | `PG_GENERATOR_MODEL=v3.2-exp` → `=v4-pro`; family override comment `qwen` → `gemma`; `OPENROUTER_DEFAULT_MODEL=v3.2-exp` → `=v4-pro`; `VLLM_MODEL=Llama-3.1-70B-Instruct` → `=ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` with `# Load with --quantization compressed-tensors`; preamble comment refresh |
| 6 | `src/providers/llm_provider.py` | 46 | `OPENROUTER_MODEL` default `moonshotai/kimi-k2-0711` → `"deepseek/deepseek-v4-pro"` |
| 7 | `src/providers/llm_provider.py` | 50 | `VLLM_MODEL` default `meta-llama/Llama-3.1-70B-Instruct` → `"ebircak/gemma-4-31B-it-4bit-W4A16-AWQ"` |
| 8 | `src/polaris_graph/llm/openrouter_client.py` | 46 | `OPENROUTER_DEFAULT_MODEL` env-default `"qwen/qwen3.5-plus-02-15"` → `"deepseek/deepseek-v4-pro"` |
| 9 | `src/polaris_graph/generator/analyst_synthesis.py` | 310 | function default `"deepseek/deepseek-v3.2-exp"` → `"deepseek/deepseek-v4-pro"` |
| 10-11 | `src/polaris_graph/generator/sentence_repair.py` | 148, 259 | two function defaults — same swap |
| 12 | `src/polaris_graph/clinical_generator/real_completion.py` | 80 | fallback `"z-ai/glm-5.1"` → `"deepseek/deepseek-v4-pro"` |
| 13 | `src/polaris_graph/api/disambiguation_route.py` | 68 | fallback `"z-ai/glm-5.1"` → `"deepseek/deepseek-v4-pro"` |
| 14 | `scripts/regate_v23.py` | 113 | generator fallback v3.2-exp → v4-pro |
| 15 | `scripts/regate_v23.py` | 116 | evaluator fallback `qwen/qwen3-8b` → `google/gemma-4-31b-it` |
| 16 | `scripts/deploy.sh` | 662 | generated-env template `OPENROUTER_DEFAULT_MODEL=moonshotai/kimi-k2.5` → `=deepseek/deepseek-v4-pro` |
| 17 | `src/polaris_v6/api/transparency.py` | 218 | evaluator env default `"qwen/qwen-2.5-72b-instruct"` → `"google/gemma-4-31b-it"` |
| 18 | `helm/polaris/values.yaml` | 69 | `vllm.model` Llama-3.1-70B → `ebircak/...-AWQ` + `# Not wired into active templates; full launch wiring at I-cd-038` |

**Tests (iter-4 P1):**

| # | File | Lines | Change |
|---|---|---|---|
| 19 | `tests/polaris_graph/clinical_generator/test_real_completion.py` | 46-51 | Update default-fallback expectation `"z-ai/glm-5.1"` → `"deepseek/deepseek-v4-pro"` to match the updated `real_completion.py:80` |

**Doc + locked-pair consistency:**

| # | File | Lines | Change |
|---|---|---|---|
| 20 | `docs/transparency.md` | 29 | evaluator default disclosure → `"google/gemma-4-31b-it"` |
| 21 | `docs/runbook.md` | 153-168 | Default pair → V4 Pro + Gemma 4 31B-it; same-family-invalid example → `(v4-pro, v4-flash)` |
| 22 | `docs/models/serving_engine_pick.md` | Maverick refs throughout | Evaluator → Gemma 4 31B-it + AWQ artifact + `--quantization compressed-tensors`; drop Maverick contingency (lock is now Gemma 4 31B-it) |
| 23 | `architecture.md` | 175-176, 337-339 | Default pair → V4 Pro + Gemma 4 31B-it |
| 24 | `src/polaris_graph/audit_ir/model_pin.py` | 25-26 | Docstring example pair → V4 Pro + Gemma 4 31B-it |
| 25 | `src/polaris_graph/clinical_generator/real_completion.py` | 7 | Module docstring default → `'deepseek/deepseek-v4-pro'` |
| 26 | `docs/gemma_4_verification.md` | 63, 74-91, 165, 180 | NVFP4 / V4 Flash refs → AWQ + V4 Pro lock-consistency (iter-4 P2) |
| 27 | `docs/task_acceptance_matrix.yaml` | 959 | Same NVFP4 / V4 Flash → AWQ + V4 Pro (iter-4 P2) |
| 28 | `docs/carney_handover/runbook.md` | 17, 48 | V4 Flash demo-generator references → V4 Pro (iter-4 P2) |
| 29 | `docs/carney_handover/5min_video_script.md` | 41 | Same V4 Flash → V4 Pro (iter-4 P2) |

**state/polaris_restart/iteration_trajectory.md** — §8.3.5 log.

(File-count = 14 unique files; line-count = ~29 lines. Some files have
multiple lines edited — see right-hand "Lines" column above.)

## §B — What this PR does NOT change

- **Two-family enforcement code**: unchanged. Map already supports the
  locked pair (Codex iter-2 P2 of I-cd-005-followup).
- **`tests/crown_jewels/test_cj_001_two_family_segregation.py`**: tests
  the family-mapping function contract using `deepseek-v3.2-exp` as
  illustration; the contract holds. Not updated.
- **`tests/fixtures/m_live_4_baseline/.../model_pin.json`**: historic
  baseline snapshot from 2026-04. Not updated.
- **`docker-compose.yml:56`**: dropped per Codex iter-3 P1 (compose
  vLLM service needs full `command:` wiring with
  `--quantization compressed-tensors` + `--tensor-parallel-size 4`, not
  just MODEL env-var swap; deferred to I-cd-038 deployment).
- **Two-box runtime architecture in `llm_provider.py`** (separate URLs
  for Box 1 generator vs Box 2 evaluator): deferred to I-cd-038.
- **iter-4 P2 module docstrings** (`src/polaris_graph/__init__.py:4`,
  `llm/__init__.py:1`, `openrouter_client.py:4/930`, `architecture.md:49/83`,
  `README.md:116` still say Qwen 3.5 Plus): Codex explicitly accepted
  "I-cd-010 boundary." DEFERRED to I-cd-010.
- **iter-3 P2 standalone test/smoke/preflight scripts** that pin
  specific models for THEIR OWN test purposes
  (`scripts/audit_dashboard_visual.py:240`, `build_walkthrough_pdf.py:100`,
  `inject_test_trace.py:*`, `pg_empirical_e1_e4.py:27,279`,
  `pg_mesh_preflight.py:57-58`, `pg_mesh_scale_test.py:83`,
  `pg_smoke_glm5_structured.py:47`, `pg_preflight_032.py:836`): DEFERRED
  to I-cd-010 per the breakdown's task split.

## §C — Smoke

- `pytest tests/polaris_graph/clinical_generator/test_real_completion.py`
  — MUST pass with the updated default expectation (iter-4 P1).
- `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` —
  passes (family-mapping contract unchanged).
- `python -m py_compile` on every edited Python file.

## §D — Residual question for Codex iter-5

The iter-1 through iter-4 findings are all folded above. Iter 5's question:
is the 24-change × 14-file scope NOW exhaustive on active-default +
locked-pair-documentation, with everything else genuinely belonging in
I-cd-010 per the breakdown's task split?

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
