# Codex Diff Gate — I-provider-001 (#1183): route deepseek-v4-pro generation to Novita + raise reasoning-first cap to 32000

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Required output schema (machine-parsed; the LAST `verdict:` line is read by CI)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

End your review with a final standalone line: `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.

## Summary (operator-authorized provider switch)

The operator authorized switching deepseek-v4-pro generation off DeepInfra and onto Novita.
ROOT CAUSE of the dominant completeness gap vs ChatGPT/Gemini: DeepInfra's deepseek-v4-pro
endpoint caps `max_completion_tokens` at 16384. deepseek-v4-pro is reasoning-first and emits
~17-18k reasoning tokens BEFORE content on some sections, so reasoning alone exhausts the 16384
budget -> `finish_reason=length` -> the FX-01 guard correctly refuses to ship truncated
scratchpad -> core sections dropped. This is NOT fixable by raising PG_SECTION_MAX_TOKENS alone,
because the runner budget is clamped back down by the 16384 hard cap in `_build_body`.

Novita = Singapore (non-US / non-China, satisfies the LLM-inference sovereignty threat model),
serves deepseek-v4-pro at `max_completion_tokens=393216`, and was behaviorally smoked live:
`provider=Novita, content=true, finish_reason=stop, truncated=false`. So 32000 is well within
Novita's ceiling and NEVER 404s on Novita; the truncation source (DeepInfra 16384) is removed by
pinning the provider.

The change is **env-only routing + one documentation-only code edit** (a comment block; NO default
value changed). Provider routing is governed by the plain env path in `_build_body`:
`OPENROUTER_PROVIDER_ORDER=novita` selects branch 2 (`provider_block["order"]=[novita]`,
`allow_fallbacks` left at the `OPENROUTER_ALLOW_FALLBACKS` env value). The production beat-both
launcher `run_gate_b` calls `run_one_query` directly and never calls `set_role_providers()`, so the
Path-B singleton override is dead on the real run; the env path is the live one.

## PLEASE VERIFY (4 explicit checks the operator wants confirmed)

1. **The cap raise to 32000 is SAFE — it must NOT cause 404s if a call falls back to a
   provider that caps lower (e.g. DeepInfra 16384).** Confirm the 404 risk is fully coupled to the
   Novita pin: the code DEFAULT stays 16384 (so un-pinned runs never request >16384), and 32000 is
   only requested in a run env that pins `OPENROUTER_PROVIDER_ORDER=novita` AND
   `OPENROUTER_ALLOW_FALLBACKS=false` (so OpenRouter cannot drift off Novita onto a 16384-cap
   provider and re-truncate or 404). Trace `_build_body` branch 2: with env order=[novita] and
   `allow_fallbacks=false`, can a call still land on a lower-cap provider? If yes, that is a P0.
2. **No faithfulness impact.** This only gives content MORE room (raises the token ceiling) and
   pins the provider; it does not touch `strict_verify`, the 4-role verifier, the redactor, or any
   provenance/NLI gate. Confirm nothing in the diff or env slate weakens a faithfulness gate.
3. **Env-overridable, no magic numbers.** Confirm the cap is the named env knob
   `PG_REASONING_FIRST_HARD_CAP` (not a hardcoded literal), `PG_SECTION_MAX_TOKENS` is the named
   runner-budget knob, and the provider pin is `OPENROUTER_PROVIDER_ORDER` / `OPENROUTER_ALLOW_FALLBACKS`.
4. **Jurisdiction rationale documented.** Confirm Novita=Singapore (non-US/non-China) sovereignty
   rationale is recorded at the code site AND the brief.

## The diff (code change — documentation-only)

```diff
diff --git a/src/polaris_graph/llm/openrouter_client.py b/src/polaris_graph/llm/openrouter_client.py
index 6e072be3..085d7d7e 100644
--- a/src/polaris_graph/llm/openrouter_client.py
+++ b/src/polaris_graph/llm/openrouter_client.py
@@ -1690,6 +1690,26 @@ class OpenRouterClient:
             # Hard ceiling at DeepInfra's verified cap for deepseek-v4-pro. The runner's
             # per-section/outline max_tokens kwargs can legally request higher (e.g. 24000
             # for V30 Phase-2 long-form sections); without this clamp those requests 404.
+            #
+            # I-provider-001 (#1183): the default STAYS 16384 — it is the safe cap for the
+            # DEFAULT provider configuration (empty OPENROUTER_PROVIDER_ORDER -> the health-
+            # ranked generator chain in config/settings/openrouter_provider_routing.yaml,
+            # which can land on DeepInfra whose deepseek-v4-pro endpoint caps at exactly
+            # 16384; 16385 -> 404 "No endpoints found"). deepseek-v4-pro is reasoning-first
+            # and emits ~17-18k reasoning tokens before content on some sections, so a 16384
+            # ceiling starves content -> finish_reason=length -> the FX-01 guard drops the
+            # truncated section. The fix is COUPLED, env-only, and provider-gated: raise this
+            # cap to 32000 ONLY in a run env that also pins OPENROUTER_PROVIDER_ORDER=novita
+            # (+ OPENROUTER_ALLOW_FALLBACKS=false so OpenRouter cannot drift off Novita) AND
+            # PG_SECTION_MAX_TOKENS=32000 (the runner budget that this cap would otherwise
+            # clamp back down). Novita serves deepseek-v4-pro at max_completion_tokens=393216
+            # (verified live via GET /api/v1/models/deepseek/deepseek-v4-pro/endpoints,
+            # 2026-06-09: Novita status=0, max_completion=393216; DeepInfra max_completion=
+            # 16384), so 32000 NEVER 404s there. Raising the DEFAULT here (instead of via the
+            # coupled run env) would re-introduce the DeepInfra 404 on un-pinned runs and would
+            # change behavior for EVERY reasoning-first model — both forbidden. Jurisdiction
+            # rationale: Novita = Singapore (non-US / non-China), operator-chosen for the
+            # sovereign generation provider. Exact run-env slate is in the I-provider-001 brief.
             _hard_cap = int(os.getenv("PG_REASONING_FIRST_HARD_CAP", "16384"))
             if body.get("max_tokens", 0) > _hard_cap:
                 body["max_tokens"] = _hard_cap
```

### Diff LOC

```
 src/polaris_graph/llm/openrouter_client.py | 20 ++++++++++++++++++++
 1 file changed, 20 insertions(+)
```

## env_to_set (run-script env slate — the live routing; NO code default changed)

```
OPENROUTER_PROVIDER_ORDER=novita
OPENROUTER_ALLOW_FALLBACKS=false
PG_REASONING_FIRST_HARD_CAP=32000
PG_SECTION_MAX_TOKENS=32000
```

- `OPENROUTER_PROVIDER_ORDER=novita` (lowercase routing slug, verified against
  `config/settings/openrouter_provider_routing.yaml` `roles.generator.order` which already uses
  lowercase `novita`) -> `_build_body` branch 2 pins generation to Novita.
- `OPENROUTER_ALLOW_FALLBACKS=false` -> with env order set, branch 2 leaves `allow_fallbacks` at the
  env value; `order=[novita] + fallbacks=true` would let OpenRouter drift onto a 16384-cap provider
  and re-truncate / 404. REQUIRED.
- `PG_SECTION_MAX_TOKENS=32000` + `PG_REASONING_FIRST_HARD_CAP=32000` are the LOAD-BEARING PAIR:
  the runner passes `section_max_tokens=PG_SECTION_MAX_TOKENS` (run_honest_sweep_r3.py:5567, default
  16384) into the generator, and `_build_body` clamps it to `PG_REASONING_FIRST_HARD_CAP`. Both must
  be 32000 or the cap wins and content still starves.
- `PG_REASONING_FIRST_MIN_MAX_TOKENS` is deliberately LEFT UNSET (default 16384). Setting it to
  32000 would floor EVERY reasoning-first call to 32000, inflating small structured/subsection calls.

These env vars are set ONLY in the VM run scripts (`~/p1.sh ~/p2.sh ~/p3.sh`) at the deploy step.
With env UNSET, behavior is byte-for-byte identical (default 16384 cap, health-ranked chain).

## Full brief (acceptance criteria + adjacent-file scan + smoke evidence)

# I-provider-001 (#1183) — Wire deepseek-v4-pro generation to Novita with a 32000 reasoning-first cap

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema bound

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Problem

`deepseek/deepseek-v4-pro` (PG_GENERATOR_MODEL) is reasoning-first: it emits ~17-18k reasoning
tokens BEFORE content on some sections. `openrouter_client.py` clamps reasoning-first calls to
`PG_REASONING_FIRST_HARD_CAP` (default 16384, matching DeepInfra's deepseek-v4-pro endpoint cap;
16385 -> 404). So reasoning alone exhausts the budget -> `finish_reason=length` -> the FX-01 guard
correctly refuses to ship truncated scratchpad -> core sections dropped. This is the dominant
completeness gap vs ChatGPT/Gemini and is NOT fixable by raising `PG_SECTION_MAX_TOKENS` alone,
because that runner budget is clamped back down by the 16384 hard cap.

## Resolution: ENV-ORDER (env-only) + one documentation-only code edit

Per the investigation (`.codex/I-provider-001/investigation_comment.md`): the production beat-both
launcher `python -m scripts.dr_benchmark.run_gate_b` calls `run_one_query` directly and NEVER calls
`gate_around_question()` / `set_role_providers()`, so the Path-B singleton override is DEAD on the
real run. Generation provider routing is governed by the plain env path in
`OpenRouterClient._build_body` (openrouter_client.py:1704-1739):

1. Path-B singleton (`current_role_provider()`) — None on the run_gate_b path.
2. `OPENROUTER_PROVIDER_ORDER` env (if set) -> `order=<list>`, `allow_fallbacks=<OPENROUTER_ALLOW_FALLBACKS>`.
3. else config YAML `roles.generator.order` -> health-ranked chain (can land on DeepInfra/streamlake).

Setting branch 2 pins generation to Novita. No code change is required for the routing.

### Exact run-env slate (env_to_set)

```
OPENROUTER_PROVIDER_ORDER=novita
OPENROUTER_ALLOW_FALLBACKS=false
PG_REASONING_FIRST_HARD_CAP=32000
PG_SECTION_MAX_TOKENS=32000
```

- `OPENROUTER_ALLOW_FALLBACKS=false` is REQUIRED: with env order set, branch 2 leaves
  `allow_fallbacks` at the env value; `order=[novita]` + `fallbacks=true` would let OpenRouter drift
  off Novita onto a 16384-cap provider and re-truncate.
- `PG_SECTION_MAX_TOKENS=32000` + `PG_REASONING_FIRST_HARD_CAP=32000` are the LOAD-BEARING PAIR:
  the runner passes `section_max_tokens=PG_SECTION_MAX_TOKENS` (run_honest_sweep_r3.py:5567,
  default 16384) into the generator, and `_build_body` then clamps it to `PG_REASONING_FIRST_HARD_CAP`
  (openrouter_client.py:1693-1695). Both must be 32000 or the cap wins and content still starves.
- `PG_REASONING_FIRST_MIN_MAX_TOKENS` is deliberately LEFT UNSET (default 16384). Setting it to
  32000 floors EVERY reasoning-first call to 32000, inflating small structured/subsection calls
  (e.g. the m50 subsection budget of 400). Not needed: HARD_CAP + SECTION_MAX_TOKENS close the gap.

### Provider-slug casing (verified)

OpenRouter's `provider.order` field takes the routing SLUG, lowercase `novita` — NOT the display
name "Novita". In-codebase proof: `config/settings/openrouter_provider_routing.yaml`
`roles.generator.order` uses lowercase `novita` and `role_provider_routing("generator")` feeds those
lowercase slugs straight into `provider_block["order"]` (openrouter_client.py:1735) on the working
verifier/generator paths. The `provider_aliases` map normalizes display name `"Novita" -> novita`.
The issue/investigation text wrote `Novita` (capital N) loosely; the wire value is lowercase
`novita`.

## Smoke evidence (live, no spend)

`GET https://openrouter.ai/api/v1/models/deepseek/deepseek-v4-pro/endpoints` (2026-06-09):

| Provider  | max_completion_tokens | status | tag         |
|-----------|-----------------------|--------|-------------|
| Novita    | 393216                | 0      | novita/fp8  |
| DeepInfra | 16384                 | 0      | (default chain member — source of the 16384 truncation) |
| Venice    | 32768                 | 0      | (also >32000, not pinned) |

So 32000 is well within Novita's 393216 ceiling -> NEVER 404s on Novita. DeepInfra's 16384 cap is
exactly the truncation source. Coupling proven: the 32000 cap is safe iff the provider is pinned to
Novita.

## Code change (documentation-only — the coupling)

`src/polaris_graph/llm/openrouter_client.py:1690-1695`: added a comment block at the
`PG_REASONING_FIRST_HARD_CAP` default explaining WHY the default STAYS 16384 (safe on the default
DeepInfra-capable chain) and WHEN 32000 is safe (coupled to `OPENROUTER_PROVIDER_ORDER=novita` +
`OPENROUTER_ALLOW_FALLBACKS=false` + `PG_SECTION_MAX_TOKENS=32000`), with the live smoke evidence
and the jurisdiction rationale. NO default value changed. NO magic number introduced (the cap is the
named env knob `PG_REASONING_FIRST_HARD_CAP`).

## Safety / blast radius

- The code default is UNCHANGED (16384), so an un-pinned run (empty `OPENROUTER_PROVIDER_ORDER` ->
  health-ranked chain -> possibly DeepInfra) NEVER sees a cap it can't serve. The 404 risk is fully
  coupled to the Novita pin via the run env, not the code default.
- Behavior for OTHER models is unchanged: `OPENROUTER_PROVIDER_ORDER` is only set in the run env, and
  the cap knobs only apply to `_REASONING_FIRST_MODELS` (deepseek-v4-pro / deepseek-v4-flash). With
  env unset, byte-for-byte identical behavior.
- `OPENROUTER_PROVIDER_ORDER` is model-agnostic in `_build_body` (no per-model eligibility
  intersect), and the investigation verified EVERY model on the run_gate_b path through
  `_build_body` is deepseek-v4-pro (generator / STORM / agentic / deepener / clinical+scope
  classifier), all of which Novita serves. The gemma/4-role verifiers route through separate
  direct-httpx / role-scoped / config-YAML paths and never read `OPENROUTER_PROVIDER_ORDER`.

## Jurisdiction rationale

Novita = Singapore (non-US / non-China), operator-chosen as the sovereign generation provider. The
sovereignty threat model is the LLM-inference path: no runtime US LLM vendor calls, no data in US
jurisdiction. Novita-Singapore satisfies this for generation.

## Files I have ALSO checked and they're clean

- `config/settings/openrouter_provider_routing.yaml` — `roles.generator.order` left UNCHANGED
  (health-ranked chain). NOT reordered to novita-first: that would change routing globally even when
  env is empty AND would not carry the cap. Provider pin stays env-only.
- `src/polaris_graph/generator/multi_section_generator.py:78` + `analyst_synthesis.py:59` —
  `PG_SECTION_MAX_TOKENS` default 24000 (module-level); the binding default for the sweep is the
  runner's 16384 at `run_honest_sweep_r3.py:5567`. Both read the env knob; no edit needed.
- `scripts/dr_benchmark/run_gate_b.py` — the production beat-both launcher; reads env, no hardcoded
  provider order or cap. No edit needed.
- `src/polaris_graph/roles/provider_routing.py` — `slug_for_provider` / `role_provider_routing`
  confirm lowercase slug usage and the alias map. No edit needed.
- VM run scripts `~/p1.sh ~/p2.sh ~/p3.sh` — get the env slate in the SMOKE/deploy step (env_to_set
  below).

## Acceptance criteria

1. With the env slate set, a deepseek-v4-pro generation call requests max_tokens=32000 and is routed
   to Novita (200, not 404), giving ~14k content headroom after ~18k reasoning -> sections no longer
   truncate.
2. With the env slate UNSET, behavior is byte-for-byte identical to before (default 16384 cap,
   health-ranked chain).
3. No magic number; the cap is the named `PG_REASONING_FIRST_HARD_CAP` env knob.
4. The coupling (32000 only safe when Novita-pinned) is documented at the code site + this brief.
