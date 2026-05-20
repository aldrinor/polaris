HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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
- **Pipeline-C is FROZEN** per CLAUDE.md §5 (`src/orchestration/`, `scripts/full_cycle.py`, KIMI K2.5 + Gemini fallback + agents + COT post-filter classifier).

# Codex diff review — I-cd-010 / GH#625

## §0 — Context

Brief APPROVE'd at iter 3/5 (`novel_p0=0, continuing_p0=0, p1=0, convergence_call: accept_remaining`). 2 P2 non-blocking (gemini_client.py docstrings + live_deepseek_generator.py V3.2 comments). Iter trajectory: 1 RC (1 P1 + 3 P2) → 2 RC (1 NEW P1 + 2 P2) → 3 APPROVE.

This diff implements the 13-file scope from the iter-3 brief.

## §A — Diff summary

**13 files / +78 / -20 / +58 net LOC.** Well under the 200-LOC PR cap.

- **8 active doc/config edits**: 4 module docstrings (Qwen 3.5 Plus → V4 Pro per env default), docker-compose:56 vLLM MODEL fallback (Llama-3.1-70B → ebircak AWQ), gemma_4_verification.md §4.2 (Llama 4 Scout → FP16 Gemma 4 31B-it TP=4), task_acceptance_matrix.yaml:205 HISTORICAL note, cot_post_filter.py:286 pipeline-C classifier comment.
- **9 intentional-legacy classification comments** across 6 files: kimi_client.py docstring augment, agents (analyst:585/602, base:158/216, citefirst:4686), config/core.py MODEL CONFIGS banner, llm_provider.py:55 OLLAMA_MODEL, openrouter_client.py pricing table + reasoning-first registry.

## §B — Acceptance criteria check

| Criterion | Status |
|---|---|
| #625: "no stale model identifiers in clients/config" | YES — docker-compose:56 fixed (Llama-3.1-70B → AWQ); cot_post_filter:286 documented; module docstrings updated; pricing/registry retentions documented as INTENTIONAL |
| #527: "All stale model references aligned... OR explicitly documented as intentionally-pinned legacy" | YES — 9 pipeline-C-frozen classification comments + 2 INTENTIONAL retention comments cover every flagged legacy entry |
| #529: "graph_v2/v3 default model references reconciled to current state" | YES — reconciled by inheritance from I-cd-009's openrouter_client.py:46 env default; smoke verifies imports clean + module-level default = V4 Pro |
| #529: "Pipeline-B behavior verified unaffected" | YES — graph_v2 + graph_v3 import smoke clean |

## §C — Smoke evidence

- `py_compile` on all 10 edited Python files → **all OK**
- `yaml.safe_load` on `docker-compose.yml` + `docs/task_acceptance_matrix.yaml` → **OK**
- `from src.polaris_graph.graph_v2 import build_v2_graph` → **OK**
- `from src.polaris_graph.graph_v3 import build_v3_graph, build_and_run_v3` → **OK**
- `OPENROUTER_MODEL` module-level default → `deepseek/deepseek-v4-pro`
- `pytest tests/polaris_graph/llm/` → **11 passed**
- `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` → **5 passed**
- docker-compose offline render — vllm MODEL env → `${VLLM_MODEL:-ebircak/gemma-4-31B-it-4bit-W4A16-AWQ}`

## §D — What this diff does NOT do (per scope discipline)

- **Standalone test/smoke/preflight scripts** that pin specific models for THEIR OWN test purposes — file-name-pinned scripts like `pg_smoke_glm5_structured.py` / `pg_preflight_032.py` literally name the pinned model. Out of #527+#529 scope.
- **Historical task_acceptance_matrix.yaml V4 Flash + Scout entries** at lines 65, 74, 138, 147, 157, 183, 968 — historical task-acceptance criteria from already-green tasks; updating retroactively falsifies the audit trail. Only line 205 (which describes the gemma_4_verification.md §4.2 content) got a HISTORICAL note pointer.
- **docker-compose `command:` wiring for vLLM** (full `--quantization compressed-tensors` + `--tensor-parallel-size 4` + GPU resource block) — deferred to I-cd-038 deployment.
- **iter-3 P2 (gemini_client.py + live_deepseek_generator.py docstrings)** — Codex explicitly `accept_remaining` (non-blocking pipeline-C / no client-config default stale).

## §E — Codex Red-Team checklist for THIS diff

Reviewer please verify:
1. No NEW stale identifier introduced anywhere in the 13 changed files.
2. The docker-compose.yml:56 MODEL fallback string EXACTLY matches `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` (the locked vLLM artifact per I-cd-009).
3. The §4.2 fallback rewrite preserves the two-family invariant (FP16 google/gemma-4-31B-it is same-model variant of locked evaluator — same lineage as the AWQ version, NOT a cross-lineage swap).
4. Every "pipeline-C frozen" / "INTENTIONAL" / HISTORICAL comment is a true classification (no incorrect-legacy labeling that would mask a real stale active-runtime default).
5. `graph_v2.py` + `graph_v3.py` `OpenRouterClient()` no-arg construction is the right reconciliation path for #529 (vs an explicit `model=` argument).
6. No accidental file additions beyond the brief's 13-file scope.

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
