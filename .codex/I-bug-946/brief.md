## Codex review brief — I-bug-946 (GH#932) Path-B gate per-role provider pin

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (bound)

```yaml
verdict: APPROVE | REQUEST_CHANGES
choice: A | B | C | other
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context (LOCKED — do not relitigate)

- Clinical-grade DR benchmark POLARIS vs ChatGPT 5.5 Pro vs Gemini 3.1 Pro on 5 frozen DRB-EN questions (#925).
- §-1.1 binding: claim-by-claim audit; gate must catch real drift, not false-fail on identity-equivalent surface.
- Generator pinned to `deepseek/deepseek-v4-pro` (LOCKED, do not propose alternative).
- Evaluator pinned to `google/gemma-4-31b-it` (LOCKED, two-family segregation).
- I-bug-944 fixed (provider case insensitive), I-bug-945 fixed (alias↔canonical_slug). The gate's RolePin already supports per-role `provider_name` — only the env-resolution path is wrong.

## The decision

OpenRouter's per-model endpoints endpoint (verified 2026-05-28):

```
GET /api/v1/models/deepseek/deepseek-v4-pro/endpoints
  providers: DeepSeek, DeepInfra, GMICloud, Baidu, Novita, SiliconFlow, Alibaba,
             StreamLake, AtlasCloud, Venice, Parasail, Fireworks, Together

GET /api/v1/models/google/gemma-4-31b-it/endpoints
  providers: DeepInfra, SiliconFlow, Novita, Parasail, Chutes, Phala, Venice,
             Ambient, Together  (Fireworks NOT in list)
```

The pinned models have **disjoint provider sets**. A single global `OPENROUTER_PROVIDER_ORDER=fireworks` pin cannot satisfy both. Empirically OpenRouter silently routed the evaluator to Novita despite `allow_fallbacks=false`. The gate caught it (correct §-1.1 behavior); the env model is the bug.

Current code path:
- `src/polaris_graph/llm/openrouter_client.py:1400-1409` reads `OPENROUTER_PROVIDER_ORDER` globally per call
- `src/polaris_graph/benchmark/pathB_runner.py:_role_pins()` uses the same global env for both roles
- `scripts/dr_benchmark/pathB_run_gate.py:194-196` preflight enforces singleton, not per-role

### Three honest paths

**A — Per-role env vars** `OPENROUTER_PROVIDER_ORDER_GENERATOR` / `_EVALUATOR`, global as fallback.
- Implementation: `_role_pins` reads per-role env (~5 LOC); openrouter_client accepts per-call provider_order override (~10 LOC); thread through call sites.
- Pros: Explicit operator config; minimal new HTTP calls.
- Cons: (i) Operator burden — maintain two envs. (ii) Operator can still typo into a model-incompatible provider; only catches mismatch at full LLM call. (iii) openrouter_client signature surgery needed to plumb per-call provider_order through call sites.

**B — Live preflight ping per role**. Send a 1-token request per role; pin = served provider from response.
- Implementation: ~20 LOC in preflight; uses openrouter client at preflight.
- Pros: Pin reflects empirical reality.
- Cons: (i) Burns API credit per preflight. (ii) 1-token ping might route differently from real-load call. (iii) Non-deterministic across re-runs (pin drift even with same env). (iv) Pre-registration anchor becomes "what was served on this specific preflight ping," not "what will be served on the run" — weaker semantics than C.

**C (Claude's recommendation) — Static endpoint-list lookup at preflight**.
- Implementation: `preflight` calls `GET /api/v1/models/<id>/endpoints` for each role's model. Parses returned endpoints into a provider list. Intersects with env's `OPENROUTER_PROVIDER_ORDER` (case-insensitive). Pin's `provider_name` = first match in env order. Fails closed with diagnostic if no match: `"role evaluator: model 'google/gemma-4-31b-it' has no endpoint in OPENROUTER_PROVIDER_ORDER=[fireworks]; available: [DeepInfra, SiliconFlow, Novita, ...]"`. ~30 LOC + small change to relax the strict singleton check (now: per-role disjoint sets OK as long as each role intersects).
- Pros: (i) Deterministic — same env + same OpenRouter catalog = same pin. (ii) No live LLM call at preflight. (iii) Auto-resolves disjoint provider sets when operator sets e.g. `OPENROUTER_PROVIDER_ORDER=fireworks,novita` (first match per role). (iv) Pre-registration anchor is the resolved per-role provider, recorded in `pathB_gate_pin.json`. (v) Fails closed with actionable diagnostic if env can't satisfy a role.
- Cons: (i) One extra HTTPS call per role at preflight (~100-200ms). (ii) Adds API dependency (already there for I-bug-945 canonical_slug resolution — same `/api/v1/models` family). (iii) Requires relaxing the "singleton routing" preflight check (currently fails if provider_order has >1 entry — needed to allow `fireworks,novita`). Replace with: "each role's order must be non-empty AND have ≥1 intersection with that role's endpoints AND fail closed if no intersection."

## Claude's choice

**C**. Same engineering philosophy as I-bug-945: capture the actual routing fact at preflight, record it in the audit anchor, fail closed on real drift. C resolves the disjoint-provider-set issue without operator-doubling-env burden or per-ping cost. The "singleton routing" preflight rule was the right intent (one provider per role per run) but wrong implementation (one provider for both roles).

## Files to be touched (under C)

- `scripts/dr_benchmark/pathB_run_gate.py`:
  - Add `resolve_role_provider(model_slug, provider_order: list[str]) -> str` function that calls `/api/v1/models/<id>/endpoints`, intersects with provider_order (case-insensitive), returns first match. Raises GateError with diagnostic if no match.
  - In `preflight()`: replace the global singleton check with per-role resolution loop. Each role's `provider_name` is populated from the resolved match (env override accepted if non-empty; otherwise resolved value wins).
  - The `OPENROUTER_PROVIDER_ORDER` env is now interpreted as a candidate list (comma-separated), not a forced singleton.
- `src/polaris_graph/benchmark/pathB_runner.py`:
  - `_role_pins()` no longer needs to take a single `provider` value — the preflight resolves per-role provider. RolePin's `provider_name` is set to "" pre-preflight and populated by preflight.
  - Alternative: keep _role_pins setting `provider_name=""` and rely on preflight to fill.
- `src/polaris_graph/llm/openrouter_client.py`:
  - Either (a) accept per-call `provider_order_override: list[str] | None` argument, OR (b) read role-specific env (`PG_ROLE_GENERATOR_PROVIDER_ORDER` / `_EVALUATOR_PROVIDER_ORDER`) set by the runner before each call.
  - Recommended: (a) per-call override threaded through `generate()` / entailment_judge call paths. Falls back to global env when override absent.
- `tests/dr_benchmark/test_pathB_run_gate.py`:
  - `test_resolve_role_provider_returns_first_in_order_match` — happy path
  - `test_resolve_role_provider_fails_closed_on_no_intersection` — diagnostic
  - `test_preflight_pins_per_role_from_endpoint_resolution` — integration
  - `test_preflight_accepts_multi_provider_order_when_disjoint_roles` — fireworks for generator, novita for evaluator from order=fireworks,novita

## Files I have ALSO checked and they're clean

- `scripts/dr_benchmark/score_run.py:51` — consumes pin's provider_name from RolePin; additive.
- `scripts/dr_benchmark/aggregate_systems.py:149,153` — final-report rendering; additive.
- `src/polaris_graph/benchmark/pathB_capture.py` — captures served metadata; no compare.
- `src/polaris_graph/llm/entailment_judge.py` — wraps openrouter_client; if (a) chosen, must thread the per-call override; if (b) chosen, no change.

## Required from Codex

1. Verdict APPROVE/REQUEST_CHANGES on Claude's choice C (or counter-propose A or B with rationale tied to §-1.1).
2. If APPROVE on C: implementation guidance — particularly the openrouter_client per-call override vs role-specific env approach (Claude leans toward per-call override for thread-safety in async).
3. Edge cases to test: (a) endpoint status field (e.g., status=-5 from OpenRouter — is that a degraded provider that should be excluded?). (b) multi-key OPENROUTER_PROVIDER_ORDER with case mix (`Fireworks,novita`). (c) endpoint list returns empty for a model (fail closed).

Question: A, B, or C?
