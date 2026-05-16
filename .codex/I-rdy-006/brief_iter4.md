HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-rdy-006 brief iter 4 (#502) — SCOPE-BOUNDARY ruling (not another inventory)

Iter 1/2/3 = REQUEST_CHANGES. **Trajectory:** each pass added another stratum
of stale refs — `.env.example` → `openrouter_client.py:46` →
`real_completion.py` + `disambiguation_route.py` → `deploy.sh` →
`carney_delivery_plan_v6_2.md:439` → `polaris_graph/__init__.py` — and the
iter-3 exhaustive grep then uncovered THREE more model subsystems:
`src/agents/` (`base_agent.py` / `analyst_agent.py` / `citefirst_synthesizer.py`
all hardcode Kimi K2.5 via Fireworks), `src/providers/llm_provider.py:46`
(`OPENROUTER_MODEL` default `moonshotai/kimi-k2-0711`), `src/llm/kimi_client.py`
(a whole Kimi client module) — plus `config/settings/models.yaml` (Gemini
agent-tier config) and `graph_v2/v3` (pipeline-B no-arg clients).

**The inventory is unbounded because #502 as literally worded ("everything
points at V4 Pro + Gemma") is repo-wide across ≥4 model-using subsystems. The
brief will not converge by adding files. iter 4 is a SCOPE-BOUNDARY decision.**

## The precedent risk

Codex iter-2 ruled `change_v4pro` on `analyst_synthesis.py` — a default Claude
flagged as possibly-deliberate. The `src/agents/` Kimi framework is the SAME
risk class: it looks like a deliberate, architecturally-separate subsystem (an
agent framework distinct from the pipeline-A generator/evaluator), not a
stale-and-purgeable string. Blind-purging Kimi from `src/agents/` could break a
working subsystem; it needs its own architecture pass, not a string-purge
inside #502.

## PROPOSED #502 boundary — the pipeline-A locked-pair surface

**IN #502** (the pipeline-A generator/evaluator surface + the issue's explicit
acceptance criteria):
- `transparency.py:~218` + `docs/transparency.md:29` — evaluator →
  `google/gemma-4-31b-it`.
- `openrouter_client.py:46` `OPENROUTER_DEFAULT_MODEL` → `deepseek/deepseek-v4-pro`
  + the two v6 `/api` fallbacks that read it: `real_completion.py:80` &
  `disambiguation_route.py:68` (`z-ai/glm-5.1` → `deepseek/deepseek-v4-pro`) +
  `tests/polaris_graph/generator2/test_real_completion.py`.
- operator config templates: `.env.example` (62/70), `scripts/deploy.sh:662`.
- executable `v3.2-exp` defaults: `analyst_synthesis.py:310`,
  `sentence_repair.py:148/254` → `deepseek/deepseek-v4-pro` (Codex iter-2 ruling).
- pipeline-A current-state docs: `architecture.md` (49/53/83/92/175/176/320/
  325/337/339), `README.md` (116/127), `ground_rules.md` (173/316),
  `docs/runbook.md` (154/160/274).
- pipeline-A stale docstrings: `live_qwen_judge.py` (5/10-11/126),
  `live_deepseek_generator.py` (2/4/390), `openrouter_client.py` (4/820),
  `evaluator_gate.py` header (5/17/21), `hallucination_detector.py:24`,
  `src/polaris_graph/__init__.py:4`, `src/polaris_graph/llm/__init__.py:1`.
- sweep-script log strings: `run_honest_sweep_r3.py` (319/1944),
  `run_live_honest_cycle.py` (9/10/217/328/346),
  `run_honest_on_prerebuild_corpus.py` (18/385).
- `model_pin.py:26` docstring example; `carney_delivery_plan_v6_2.md:439`
  (Codex iter-3 ruled IN).
- new `tests/v6/` transparency fallback regression test.

**CARVED to separate follow-up issues** (Claude `gh issue create` at #502 close):
- `src/agents/` Kimi-K2.5 framework + `src/providers/llm_provider.py` +
  `src/llm/kimi_client.py` — agent-subsystem model alignment (needs an
  architecture pass: is Kimi deliberate? is the subsystem demo-live?).
- `config/settings/models.yaml` Gemini agent-tier config reconciliation.
- `graph_v2.py`/`graph_v3.py` pipeline-B no-arg client cleanup.
- Class B (already carved iter-1): `evaluator_gate.py` `qwen_*` identifiers,
  `live_qwen_judge.py` module rename, `qwen_judge_output.json` artifact.

**NOT changed anywhere — behavior/registry data, not stale claims:**
- `openrouter_client.py` cost table (146-158), family-prefix registry
  (308-314 — `check_family_segregation` NEEDS the glm/kimi prefixes),
  `_ALWAYS_REASON_MODELS` / `_REASONING_FIRST_MODELS` (404-417).
- `openrouter_client.py:236/253` — accurate "predecessor retained on
  OpenRouter, switch back via env" rationale comments.
- dev/test scripts (`inject_test_trace`, `build_walkthrough_pdf`, `pg_mesh_*`,
  `audit_dashboard_visual`, `pg_empirical_e1_e4`, `pg_smoke_glm5_structured`,
  `regate_v23`, `pg_preflight_032`) — legacy/dev tooling (your iter-2 P3).
- explicitly-historical docs (`experiments/`, `pipeline_audit_context/`,
  `carney_delivery_plan_v5_*`, `hardware_decision.md`, `file_directory.md:252`,
  `polaris_locked_scope.md:27`).

## The ask

**Codex: ratify this #502 boundary, or adjust it.** If a carved subsystem must
be IN #502, name it and accept the LOC implication. iter-4 is the boundary
decision; iter-5 if needed is force-APPROVE on the ratified boundary so #502
ships and the loop proceeds to #503.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
boundary_ruling: ratified | adjusted
boundary_adjustments: [...]
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
