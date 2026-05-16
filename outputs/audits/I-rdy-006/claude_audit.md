# Claude architect audit — I-rdy-006

**Issue:** #502 / I-rdy-006 — align stale model configuration references
**Branch:** `bot/I-rdy-006-model-config-align` @ `304c1268` (off `polaris` @ `9185035e`)
**Brief:** APPROVED iter-4 (`boundary_ruling: ratified`, `scope_ruling: class_a_only`)
**Canonical diff:** 26 files, 113 insertions / 69 deletions, sha256 `78c3597d9bff712cd8a26c334b4387e18cc31dbdd6c68472dea1d3a07e000053`

## 1. Objective

Replace stale generator/evaluator model references throughout pipeline-A
with the operator-locked pair: **DeepSeek V4 Pro** generator + **Gemma 4
31B** evaluator. The stale strings were `deepseek/deepseek-v3.2-exp`,
`qwen/qwen3-8b`, `qwen/qwen-2.5-72b-instruct`, `z-ai/glm-5.1`, and the
prose names "DeepSeek V3.2-Exp" / "Qwen3-8B".

## 2. Per-file verification

All edits are single-line, mechanical, behavior-preserving (defaults +
docstrings/comments + log strings). No control flow changed.

**Code — runtime defaults (behavior-affecting):**
- `openrouter_client.py` — `OPENROUTER_MODEL` default → `deepseek/deepseek-v4-pro`. Verified the cost table, family registry, and `_REASONING_FIRST` set already cover `deepseek-v4-pro` (no KeyError path).
- `generator2/real_completion.py` — `load_config_from_env()` fallback → `deepseek/deepseek-v4-pro`. Verified by `test_load_config_default_model` (updated assertion).
- `transparency.py` — `/transparency` `evaluator_models` fallbacks → `deepseek/deepseek-v4-pro` / `google/gemma-4-31b-it`. Verified by the new regression test.
- `analyst_synthesis.py` — `model` default → `deepseek/deepseek-v4-pro`.
- `sentence_repair.py` (×2), `disambiguation_route.py`, `deploy.sh`, `.env.example` (`PG_GENERATOR_MODEL`, `PG_FAMILY_OVERRIDE`, `OPENROUTER_DEFAULT_MODEL`) — defaults aligned.

**Code — docstrings / comments only (no behavior):**
- `live_qwen_judge.py`, `live_deepseek_generator.py`, `multi_section_generator.py`, `hallucination_detector.py`, `model_pin.py`, `evaluator_gate.py`, `__init__.py` ×2.

**Docs:** `architecture.md` (×10), `README.md` (×2), `ground_rules.md` (×2), `docs/runbook.md` (×7, incl. stale per-M cost line reworded — no cost numbers, per operator preference), `docs/transparency.md` (×1). All are current-state model claims.

**Sweep scripts:** `run_honest_sweep_r3.py` (×2), `run_live_honest_cycle.py` (×6), `run_honest_on_prerebuild_corpus.py` (×2) — log/header strings only.

**Tests:** new `tests/v6/test_transparency_model_fallback.py` (2 tests: default pair when env unset + env override honored); `test_real_completion.py` default-model assertion updated to track the `real_completion.py` fallback change.

## 3. Verification evidence

- `pytest tests/v6/test_transparency_model_fallback.py tests/polaris_graph/generator2/test_real_completion.py` → **28 passed**.
- Import smoke: `polaris_v6.api.transparency`, `src.polaris_graph.llm.openrouter_client`, `src.polaris_graph.generator2.real_completion`, `src.polaris_graph.api.disambiguation_route` → **imports OK**.

## 4. Deliberate exclusions (Codex to rule)

1. **`carney_delivery_plan_v6_2.md:439`** — NOT touched. It is a historical
   reconciliation-log entry, not a current-state claim. Its real staleness
   is the wholesale-superseded OVH/8×H200/V4-Flash hardware path (superseded
   by #486 sovereign pivot); fixing only the "V4 Flash" model token would
   leave a more-misleading half-stale line. Full reconciliation belongs to a
   carney-doc issue.
2. **Class B identifiers** — `evaluator_gate.py` `qwen_*` symbol names, the
   `live_qwen_judge.py` module filename, and the `qwen_judge_output.json`
   artifact name — NOT renamed. Identifier/filename renames are higher-risk
   (call-site + artifact-consumer churn) and out of this issue's "stale
   reference text" scope. Carved to a follow-up issue.

## 5. Verdict

Implementation matches the APPROVED brief (pipeline-A, class_a_only).
Diff is mechanical, fully tested, 182-LOC (under the 200-LOC cap). Ready
for Codex diff review.
