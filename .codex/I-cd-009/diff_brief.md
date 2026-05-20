HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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
  `--quantization compressed-tensors` server-side).
- **Engine**: vLLM (locked I-cd-007, PR #663).
- **Two-family**: `check_family_segregation` returns `('deepseek', 'gemma')`.

# Codex diff review — I-cd-009 / GH#624

## §0 — Context

Brief APPROVE'd at iter 5/5 (novel_p0=0, continuing_p0=0, p1=0,
convergence_call: accept_remaining). 2 P2 deferred to I-cd-010 (module
docstrings + standalone-script log-strings) per breakdown task split.

This diff implements the 22-file scope from the iter-5 brief. The
deliverable is the diff itself; the question is whether the implementation
faithfully matches the brief + introduces no execution risk.

## §A — Diff summary

**22 files / 119 insertions / 82 deletions / +37 net LOC.** Well under the
200-LOC PR cap.

- **10 active-runtime default files** — config-default swaps to V4 Pro
  generator + Gemma 4 31B-it evaluator + ebircak AWQ W4A16 vLLM artifact.
- **1 test file** — `test_real_completion.py:46-51` updated to assert
  V4 Pro instead of GLM-5.1 (iter-4 P1 fold-in).
- **10 doc + locked-pair-consistency files** — `docs/transparency.md`,
  `docs/runbook.md`, `architecture.md`, `audit_ir/model_pin.py` docstring,
  `docs/gemma_4_verification.md` (NVFP4 → AWQ W4A16), `docs/task_acceptance_
  matrix.yaml` line 959, `docs/carney_handover/runbook.md` + `5min_video_
  script.md` (V4 Flash → V4 Pro), `helm/polaris/values.yaml` vllm.model.
- **1 docs/models/serving_engine_pick.md** — Maverick refs throughout
  rewritten to Gemma 4 31B-it AWQ artifact + lock-history note.
- **1 trajectory file** — `state/polaris_restart/iteration_trajectory.md`
  appended per §8.3.5.

## §B — Acceptance criteria check (per GH#624)

| Criterion | Status |
|---|---|
| config points at DeepSeek V4 Pro 1.6T | YES — `PG_GENERATOR_MODEL`, `OPENROUTER_DEFAULT_MODEL`, `OPENROUTER_MODEL`, all function defaults, all script fallbacks, deploy.sh template |
| config points at the licensed Gemma 4 31B-it evaluator | YES — `PG_EVALUATOR_MODEL`, `VLLM_MODEL`, `transparency.py:218`, `regate_v23.py:116` |
| `openrouter_client.check_family_segregation` returns `('deepseek', 'gemma')` | YES — already enforced by I-cd-005-followup PR #664; no change needed; `test_cj_001_two_family_segregation` passes |
| no fail-loud regressions | YES — `pytest tests/polaris_graph/clinical_generator/test_real_completion.py` 26 passed |

## §C — Smoke evidence

- `pytest tests/polaris_graph/clinical_generator/test_real_completion.py`
  → **26 passed in 4.88s**
- `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py`
  → **5 passed in 0.79s**
- `py_compile` on all 10 edited Python files → **all OK**
- `bash -n scripts/deploy.sh` → **OK**
- `yaml.safe_load` on `helm/polaris/values.yaml` → **OK**
- `yaml.safe_load` on `docs/task_acceptance_matrix.yaml` → **OK**

## §D — What this diff does NOT do (per scope discipline + breakdown)

- **`docker-compose.yml:56`** — sovereign vLLM service NOT updated. Needs
  full `command:` wiring with `--quantization compressed-tensors` +
  `--tensor-parallel-size 4` + GPU resource block; just MODEL env-var swap
  would leave a broken service. Deferred to **I-cd-038** deployment.
- **Two-box runtime split in `llm_provider.py`** — still single
  `VLLM_BASE_URL`/`VLLM_MODEL`. Locked topology needs separate Box 1
  (V4 Pro generator) and Box 2 (Gemma 4 31B-it evaluator) URLs.
  Deferred to **I-cd-038**.
- **Module docstrings** in `src/polaris_graph/__init__.py:4`,
  `llm/__init__.py:1`, `openrouter_client.py:4/930`, `architecture.md:49/83`,
  `README.md:116` (still say Qwen 3.5 Plus). Codex brief iter-4 explicitly
  accepted "I-cd-010 boundary." Deferred to **I-cd-010**.
- **Standalone test/smoke/preflight scripts** that pin specific models for
  THEIR OWN test purposes (audit_dashboard_visual.py:240,
  build_walkthrough_pdf.py:100, inject_test_trace.py, pg_empirical_e1_e4.py,
  pg_mesh_preflight.py, pg_mesh_scale_test.py, pg_smoke_glm5_structured.py,
  pg_preflight_032.py). Deferred to **I-cd-010**.
- **`docs/gemma_4_verification.md` §4.2 Llama 4 Scout fallback** —
  stale fallback name. Demo safety net is now FP16 Gemma 4 31B-it at TP=4.
  Deferred to **I-cd-010** broader stale-ref cleanup.
- **Pricing tables + reasoning-model registry** in
  `openrouter_client.py:254/257/342/359/505-511` — these are NOT defaults;
  they exist to price/route legacy or multi-model runs. Deferred to
  **I-cd-010**.

## §E — Codex Red-Team checklist for THIS diff

Reviewer please verify:
1. No active runtime default still pins V3.2-exp / GLM-5.1 / Qwen / Maverick /
   Llama 3.1-70B in the 22 changed files (line-by-line cite if found).
2. The test `test_load_config_default_model` correctly asserts V4 Pro and
   matches the new `real_completion.py:80` fallback.
3. `check_family_segregation` correctness is preserved — the brief did NOT
   change the family-mapping code (it was correct as of I-cd-005-followup).
4. `--quantization compressed-tensors` is documented everywhere the AWQ
   artifact appears (NOT `--quantization awq`, which would mis-route).
5. No accidental file additions beyond the brief's 22-file scope.
6. The trajectory log accurately reflects the brief iter 5 APPROVE state.

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
