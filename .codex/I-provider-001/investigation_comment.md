## Investigation complete (I-provider-001)

**resolution_path: ENV-ORDER (not Path-B).** The production beat-both launcher `python -m scripts.dr_benchmark.run_gate_b` calls `run_one_query` DIRECTLY and NEVER calls `gate_around_question()` / `set_role_providers()` (only the legacy `run_honest_sweep_r3 --pathB-gate` CLI does — and even that runs the single-evaluator path, not what we run). So `_ROLE_PROVIDER` stays None → `current_role_provider()` returns None → the Path-B singleton-override branch in `openrouter_client.py:1718-1723` is DEAD on the real run. Generation provider routing is therefore governed by the plain env path.

Precedence in `OpenRouterClient._build_body` (lines 1717-1738):
1. Path-B singleton (`current_role_provider()`) — None here.
2. `OPENROUTER_PROVIDER_ORDER` env (if set) → `order=<list>`, `allow_fallbacks=<OPENROUTER_ALLOW_FALLBACKS>`.
3. else config YAML `roles.generator.order` fallback (`config/settings/openrouter_provider_routing.yaml`).

**Current state (the bug):** `.env` has `OPENROUTER_PROVIDER_ORDER=` (empty) + `OPENROUTER_ALLOW_FALLBACKS=true`, so generation falls to branch 3 → config YAML `roles.generator.order: [streamlake, siliconflow, baidu, novita, gmicloud, deepseek]`. It lands on **streamlake first**, NOT Novita; and the reasoning-first caps clamp to 16384 (DeepInfra's cap), truncating V4 Pro's ~18k reasoning.

**Fix = ENV-ONLY (no code/config change).** Set on the VM run env (`.env` / run script):

```
OPENROUTER_PROVIDER_ORDER=Novita
OPENROUTER_ALLOW_FALLBACKS=false
PG_REASONING_FIRST_HARD_CAP=32000
PG_REASONING_FIRST_MIN_MAX_TOKENS=32000
PG_SECTION_MAX_TOKENS=32000
```

`OPENROUTER_ALLOW_FALLBACKS=false` is REQUIRED: with env order set, branch 2 leaves `allow_fallbacks` at the env value; `order=[Novita]` + `fallbacks=true` would let OpenRouter drift off Novita. The slate (`apply_full_capability_benchmark_slate`) does NOT touch any of these 5 keys, so they are pure operator env knobs.

**Blast-radius check (why the GLOBAL env order is safe):** `OPENROUTER_PROVIDER_ORDER` is model-agnostic in `_build_body` (no per-model eligibility intersect, unlike Path-B's `resolve_role_provider`). I verified EVERY model that flows through `OpenRouterClient._build_body` on the run_gate_b path is deepseek-v4-pro:
- generator / STORM (`PG_GENERATOR_MODEL as _STORM_MODEL`) / agentic (`as _AG_MODEL`) / deepener (`PG_SWEEP_DEEPENER_MODEL` default) / clinical+scope classifier (`OPENROUTER_DEFAULT_MODEL` default) → all `deepseek/deepseek-v4-pro`, which Novita serves (API-verified).
- The gemma-family verifiers are NOT affected: the entailment judge (`llm/entailment_judge.py`), NLI semantic-conflict detector, and credibility judge are direct-httpx / role-scoped and add a provider block ONLY from `get_role_provider("evaluator")` (Path-B mapping = None here) — they never read `OPENROUTER_PROVIDER_ORDER`.
- The 4-role verifiers (mirror/sentinel/judge) route through `openrouter_role_transport` using the per-role config YAML (`apply_provider_routing`), insulated from the global env.
- The legacy single gemma judge (`live_judge.judge_report` via OpenRouterClient global env) is SKIPPED when the 4-role seam runs (`_seam_will_run`, `run_honest_sweep_r3.py:6546-6552`); `run_external_evaluation` runs with `enable_llm_judge=False` (rule checks only, no LLM call).

So pinning the global env to Novita pins ONLY deepseek-v4-pro callers, all of which Novita serves. No 404 risk with fallbacks off.

**One cost side-effect to note:** `PG_REASONING_FIRST_MIN_MAX_TOKENS=32000` is a FLOOR on EVERY reasoning-first call, so it inflates small structured/subsection calls (e.g. m50 subsection budget 400, trial-table). The section truncation is fixed by `PG_SECTION_MAX_TOKENS=32000` + `PG_REASONING_FIRST_HARD_CAP=32000` alone; the MIN floor only matters for callers that pass <32000 and could be left lower (e.g. 16384) to avoid inflating small calls. Recommend HARD_CAP=32000 + SECTION_MAX_TOKENS=32000 as the load-bearing pair; treat MIN as optional/lower.

**Alternative (generator-scoped, if you prefer not to touch the global env):** edit `config/settings/openrouter_provider_routing.yaml` `roles.generator.order` to `[novita]` (or novita-first). That leaves verifier/evaluator chains untouched and is consumed by branch 3 when env order is empty. This makes the provider pin `env_only=false`; the token knobs remain env. Not needed for the current run_gate_b path (env order wins), but it is the surgical option.
