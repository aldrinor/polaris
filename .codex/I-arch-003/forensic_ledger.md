# I-arch-003 forensic ledger (synthesis)

Decisive: the benchmark slate sets `PG_SWEEP_EVIDENCE_DEEPENER=1` (run_gate_b.py:454), and it is in BOTH `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (line 742) AND `_BENCHMARK_FORCE_ON_FLAGS` (line 810) — meaning the deepener is FORCE-ON for the real benchmark run; it cannot be disabled. This flips the two deepener mines from "latent/conditional" to **fires on the live run → P0/P1**, exactly as the advisor predicted. STORM is also force-on (`PG_STORM_ENABLED_IN_BENCHMARK=1`, line 453), so the STORM-outline mine fires too. And `PG_FOUR_ROLE_MODE=1` is set unconditionally (line 1231), confirming the legacy live_judge is dead on the benchmark path (PASS 1 correct).

I now have everything verified. The two deepener mines are P0 (forced-on, smallest budgets 2000/500 against a model emitting 17-18k reasoning tokens). The STORM-outline mine is P1 (forced-on but 4096 with JSON-recovery fallback, lower confidence). Writing the final synthesis ledger.

---

# I-arch-003 Land-Mine Ledger — Synthesis (token-starvation / model-conformance forensic)

Scope: DR-benchmark live run path (`scripts/run_honest_sweep_r3.py` + `scripts/dr_benchmark/run_gate_b.py` closure). Read-only audit, three forensic passes reconciled, every claim re-verified against source this session.

## 0. The load-bearing mechanism (re-verified, resolves the PASS 1 vs PASS 3 split)

`openrouter_client.py:1640-1736` is a 3-way **`elif` chain**, not independent guards:

- **Branch 1** `if self.model in _ALWAYS_REASON_MODELS` (the GLM ids) → 4096 floor (`PG_GLM5_MIN_MAX_TOKENS`, line 1656-1658). Never 32768.
- **Branch 2** `elif reasoning_enabled` → **NO floor at all** (lines 1659-1666).
- **Branch 3** `elif self.model in _REASONING_FIRST_MODELS` → 32768 floor (`PG_REASONING_FIRST_MIN_MAX_TOKENS`, line 1703) + 384000 cap (line 1734).

Because it is an `elif`, a reasoning-first model (deepseek-v4-pro) reaches the 32768 floor **only when `reasoning_enabled` is falsy**. Verified call-path facts:
- `generate()` → `_generate_impl` hardcodes `reasoning_enabled=False` (`openrouter_client.py:2743`) → branch 3 → **floored to 32768** (PROTECTED). `generate()` has no `reasoning_enabled` parameter (signature 2676-2686).
- `generate_structured()` defaults `reasoning_enabled=False` (line 3045) and forwards it raw to `_call` (line 3135). Callers that omit it → branch 3 → **floored** (PROTECTED). Callers that pass `reasoning_enabled=True` → branch 2 → **NO floor** (EXPOSED).
- `reason()` always passes `reasoning_enabled=True` to `_call` (line 2412) → branch 2 → **NO floor** (EXPOSED).

**Conclusion:** PASS 3 is correct; PASS 1's blanket "all six reasoning-first models are auto-protected" premise is false — protection holds only on the reasoning-OFF (`generate`/default-`generate_structured`) path.

## 1. CONFIRMED land mines

| # | Site (file:line) | Model | Current cap | Starvation mechanism | Recommended fix | Priority |
|---|---|---|---|---|---|---|
| 1 | `src/polaris_graph/agents/evidence_deepener.py:294-298` (`_extract_named_studies`) | deepseek/deepseek-v4-pro (`DEEPENER_LLM_MODEL`, default) | `max_tokens=2000`, `reason(effort="high")` | `reason()`→`reasoning_enabled=True`→branch 2→NO floor (32768 skipped). V4-Pro emits ~17-18k reasoning tokens (in-code evidence lines 1685-1702) before content → `finish_reason=length`, content empty. "operator 2026-06-13: reasoning MAX" comment shows effort was raised to high THIS session while max_tokens stayed 2000 — the #1251/#1252 class freshly re-introduced. | Raise to ≥32768: `max_tokens=int(os.getenv("PG_DEEPENER_EXTRACT_MAX_TOKENS","32768"))`. Root-cause fix preferred (see §6). | **P0** |
| 2 | `src/polaris_graph/agents/evidence_deepener.py:815-819` (`_mechanism_search`) | deepseek/deepseek-v4-pro (same client) | `max_tokens=500`, `reason(effort="high")` | Same branch-2/no-floor path; 500 total tokens vs 17-18k reasoning footprint → guaranteed empty content. Even more starved than #1. Same "reasoning MAX" comment (line 817). | Raise to ≥32768: `max_tokens=int(os.getenv("PG_DEEPENER_MECHANISM_MAX_TOKENS","32768"))`. | **P0** |
| 3 | `src/polaris_graph/agents/storm_interviews.py:1108-1114` (`_generate_outline_from_conversations`) | deepseek/deepseek-v4-pro (`_STORM_MODEL`=`PG_GENERATOR_MODEL`) | `PG_STORM_OUTLINE_MAX_TOKENS=4096` (default, line 43); `generate_structured(reasoning_enabled=True)` | `reasoning_enabled=True` passed explicitly (line 1113)→branch 2→NO floor. 4096 < documented ~17-18k V4-Pro reasoning footprint → outline JSON can truncate. This is the ONE STORM call with reasoning on; the other 3 STORM calls pass `reasoning_enabled=False`→floored→safe. | Raise default `PG_STORM_OUTLINE_MAX_TOKENS` 4096→32768 (line 43). Or root-cause fix (§6). | **P1** |

**Firing status (verified):** `run_gate_b.py` sets `PG_SWEEP_EVIDENCE_DEEPENER="1"` (line 454) AND lists it in both `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (742) and `_BENCHMARK_FORCE_ON_FLAGS` (810) — the deepener is **force-on and cannot be disabled** on the real benchmark run, so #1/#2 fire every paid run (→ P0). STORM is force-on too (`PG_STORM_ENABLED_IN_BENCHMARK="1"`, line 453), so #3 fires. #3 stays P1, not P0: it has a robust `_extract_json_from_text(result.reasoning)` recovery (`openrouter_client.py:3170-3185`) and an outline's reasoning footprint may be shorter than a full report section, so truncation is plausible-but-not-guaranteed — §-1.1 posture flags the uncertainty rather than clearing it.

**Failure character:** all three degrade *silently*, not loud — empty LLM output falls back to a deterministic path (#1→regex "Author et al. (YYYY)" at line 326; #2→`_fallback_mechanism_queries` at line 824; #3→outline recovery). So the symptom is silent capability loss (the citation-snowball / mechanism-search / multi-perspective-outline value the operator paid for never materializes), which is exactly the class §-1.1 says pattern checks miss.

## 2. FALSE POSITIVES — do NOT touch (each safe by a named mechanism)

**Clamp-protected `generate()` / default-`generate_structured()` sites (branch 3, deepseek-v4-pro → 32768 floor; verified `_generate_impl` hardcodes `reasoning_enabled=False` at line 2743):**
- `multi_section_generator.py:1457,1466,1553` section draft+retry; `:5070,5076,5091,5098,5110` outline=2500/limitations=400/table=800/subsection=400 budgets; `:5607` fact_dedup=2048; `:2793` inline 400 — small literals all floored to 32768.
- `generator/analyst_synthesis.py:446,497,506` — `generate()`, floored.
- `generator/sentence_repair.py:144,187,191,254,323` — `generate()` max_tokens=400, floored.
- `agents/storm_interviews.py:472,719,817` persona/questions/answer — `generate_structured(reasoning_enabled=False default)` → branch 3 → floored. (Only the outline sibling at 1108 is exposed.)
- `agents/searcher.py:1251,1563,2057` refiner — `generate_structured` without `reasoning_enabled` → default False → floored.
- `run_honest_sweep_r3.py:3140` planner=2000; `:4965` scope-topic=1200; `:6491` quantified=4000 — `generate()`, floored.
- `scope/clinical_classifier.py:239-241` max_tokens=200; `audit_ir/scope_classifier_llm.py:532+`; `auto_induction/llm_inductor.py:324+` — `generate()`, floored if reached (latter two default-OFF).

**Self-managed direct-httpx sites (bypass the `_call` clamp entirely; safe by hardcoded ample budget, all GLM-5.1, all un-starved this session):**
- `llm/entailment_judge.py:80,191,241` — 2000 tok, effort high (measured finish=stop, valid JSON ~11.7s). Was 100→empty; FIXED.
- `authority/credibility_judge_caller.py:27,94,117` — 8000 tok, effort high (measured finish=stop ~24s). Was 512→truncation; FIXED.
- `retrieval/semantic_conflict_detector.py:68,345,365` — 2000 tok, effort high. Was 60→empty; FIXED.

**4-role role-transport sites (KNOWN-GOOD baseline; own budgets, no `_call` clamp, reconciled vs provider caps — see §4):**
- `roles/openrouter_role_transport.py:153-163,693` Mirror 131072; `:162,669` Sentinel decomp 131072; `:710` Sentinel classifier 4096; `:163,704` Judge 262140.

**Off-live-path (not in the `run_honest_sweep_r3` import closure — pipeline B / UI / dead code):**
- `evaluator/live_judge.py:121-160` legacy single-judge — REACHABLE-BUT-DEAD: `run_gate_b:1231` forces `PG_FOUR_ROLE_MODE=1` and the runner's `_seam_will_run` guard (`run_honest_sweep_r3.py:7149-7155`) SKIPS it. (Floor here would be 4096 via GLM `_ALWAYS_REASON` branch, not 32768 — moot since it never executes.)
- `agents/analyzer.py:581,673,1059,2063,2226` (GRADE + extraction) — imported only by graph*.py/pipeline_definition (pipeline B); not by the sweep.
- `generator/live_deepseek_generator.py:406-444` `generate_live_draft` — ZERO call sites; multi_section imports only its non-LLM helpers.
- `clinical_generator/real_completion.py`, `tools/react_agent.py`, `intake/cluster_labeler.py:28,76` (max_tokens=50), `api/disambiguation_route.py`, `audit_ir/corpus_brief.py:329`, `nodes/scope.py`, `nodes/outline.py`, `synthesis/*`, `tools/{data_analyzer,code_executor,evidence_database}.py`, `agents/{planner,synthesizer,verifier,citation_agent}.py`, `retrieval/verify_schemas.py` — all pipeline B / UI / agent-tooling, none reachable from the DR sweep closure.
- Deliberate probe: `openrouter_client.py:3415` max_tokens=50 — liveness/`validate_reasoning`, not a content call.

**Conditional caveat (not a current mine):** if `PG_SWEEP_DEEPENER_MODEL` / `PG_SCOPE_TOPIC_MODEL` were overridden to a NON-reasoning-first model, their small budgets would pass raw and starve. Defaults are deepseek-v4-pro (protected on the `generate` sites; the `reason()` sites are already mines #1/#2 regardless of model). Note only.

## 3. Model-lock conformance (live inference path)

The four locked roles all resolve correctly on the live path and all are open-weight/non-US-vendor — **CONFORMANT**:
- generator → deepseek/deepseek-v4-pro (`openrouter_client.py:53,547`; lock `polaris_runtime_lock.yaml:50`).
- mirror + 3 side-judges (credibility/entailment/semantic-conflict, which map to mirror per lock `legacy_compat`) → z-ai/glm-5.1 (`openrouter_client.py:579`; judge defaults `entailment_judge.py:80`, `credibility_judge_caller.py:27`, `semantic_conflict_detector.py:68`). The stale gemma defaults on these three were retired this session — **verified none remain on a live default**.
- sentinel → minimax/minimax-m2 (`openrouter_client.py:580`); judge → qwen/qwen3.6-35b-a3b (`openrouter_client.py:581`). Used only via role transport.

**Decisive negative proof (re-verified):** every `OpenRouterClient(model=...)` site on the live closure resolves to deepseek-v4-pro or glm-5.1; minimax/qwen are consumed ONLY through `roles/openrouter_role_transport.py`. So no non-reasoning-first model is ever handed a tiny raw `max_tokens` through `openrouter_client.generate/reason` — the #1251/#1252 starvation class via the client does not exist on the live path (the three confirmed mines are all reasoning-first deepseek via the un-floored branch-2 path, a distinct mechanism).

**No live gemma / closed-source violation.** Every gemma/gemini/gpt/claude occurrence in `openrouter_client.py` (pricing-dict keys, `_FAMILY_PREFIXES` detection tuples 608-618, the error-message recommendation f-string 689, comments/docstrings) is **inert or part of the family-segregation guardrail** — no live default selects any of them.

**One non-conformant config string, OFF the live path:** `config/settings/models.yaml:40,52,58,67` pins closed-source `gemini-2.5-flash / gemini-3-pro-preview / gemini-2.5-pro` for the **legacy Gemini agent stack** (consumers per the file's own SCOPE header: `src/config/core.py`, `src/llm/gemini_client.py`, `src/utils/atomic_decomposer.py`). Verified NO module under `src/polaris_graph` imports `src.llm`/`gemini_client`/`src.config.core`/`google.generativeai`, and `run_honest_sweep_r3` imports only `src.polaris_graph.*` + `src.polaris_v6.queue`. **Cannot leak onto the live path as wired today.** Recommend retiring with pipeline-C/legacy cleanup (not in I-arch-003 scope). The `sota_baselines.json` / `sota_parameters.yaml` gemini/gpt/claude strings are comparison BASELINE DATA, not runtime selections — no client is constructed from them.

**Stale-doc debt (cosmetic, not a runtime mine):** gemma in docstrings/comments at `evaluator/external_evaluator.py:29`, `clinical_generator/strict_verify.py:38,166`, `llm/entailment_judge.py:186`, `retrieval/nli_benchmark_annotator.py:109`, `audit_ir/model_pin.py:26`, and the recommendation f-string `openrouter_client.py:689`. Recommend scrubbing; no priority.

## 4. Provider-cap mismatches

**None found on the live path.** The 4-role transport budgets are each reconciled to the *minimum* `max_completion_tokens` across the role's routed provider chain:
- Mirror/Sentinel-decomp 131072 (z-ai/baidu/novita/minimax all serve 131072; 196608 would 400).
- Judge 262140 (wandb 262144 / io-net 262140 → 262140 safe; atlas-cloud 65536 dropped from routing).
- Generator reasoning-first hard cap 384000 (`PG_REASONING_FIRST_HARD_CAP`, line 1734) matches the fp8 full-cap generator chain (WandB/Parasail 1,048,576; StreamLake/SiliconFlow/Baidu/Novita ≥384,000; DeepInfra fp4/16384 EXCLUDED via `require_parameters:true`).

The recommended fixes for mines #1/#2/#3 (raise to 32768) sit far under every generator-chain provider cap (≥384,000), so they introduce no new cap-overrun risk.

## 5. Bottom line

**Three real land mines remain on the live run path, all the same un-floored reasoning-first mechanism: a `reason()` or `generate_structured(reasoning_enabled=True)` call on deepseek-v4-pro takes the `elif reasoning_enabled` branch (`openrouter_client.py:1659`) which applies NO `max_tokens` floor, so a small budget (2000, 500, 4096) is consumed entirely by V4-Pro's ~17-18k reasoning tokens and content returns empty.** Mines #1 and #2 (evidence-deepener study-extraction and mechanism-search) are **P0** — the deepener is force-on and un-disableable on the benchmark slate (`run_gate_b.py:454,810`) and both were freshly re-starved this session when effort was raised to "high" while max_tokens stayed at 2000/500. Mine #3 (STORM outline) is **P1** — force-on but with a JSON-from-reasoning recovery that lowers (not eliminates) the truncation risk. All three fail silently into deterministic fallbacks, so only this line-by-line read catches them; "gates green" would not. The live run path is **model-conformant**: all four locked roles resolve correctly to the operator-signed open-weight slate, no gemma/closed-source model is selected on any live default (only inert pricing keys, guardrail detectors, and an off-path legacy `models.yaml` gemini config that cannot reach the sweep), and there are no provider-cap overruns.

**Recommended structural fix (covers all three + any future caller):** hoist the `_REASONING_FIRST_MODELS` 32768 floor ahead of the `elif` chain (or duplicate it into branch 2 at `openrouter_client.py:1659-1666`) so reasoning-first models inherit the floor on the `reason()`/`reasoning_enabled=True` path too — not just the `generate()` path. The per-site `max_tokens` raises (env-named, default 32768) are the tactical patch; the branch-2 floor is the root cause.

# ---- STARVATION-EXPOSED PASS ----

```json
{
  "clamp_summary": "The 32768 floor is NARROWER than the task brief states. In openrouter_client.py the budget logic is a 3-way elif chain (lines 1640-1736): (1) `if self.model in _ALWAYS_REASON_MODELS` (the 4 GLM ids glm-5/5-turbo/4.7/5.1) -> applies only the 4096 floor (PG_GLM5_MIN_MAX_TOKENS), NEVER 32768; (2) `elif reasoning_enabled` -> applies NO floor at all; (3) `elif self.model in _REASONING_FIRST_MODELS` -> applies the 32768 floor (PG_REASONING_FIRST_MIN_MAX_TOKENS) + 384000 hard cap. Because it is an elif chain, the 32768 floor (branch 3) fires ONLY when reasoning_enabled is FALSY AND the model is one of the 6 AND it is not a GLM. Concretely: deepseek/deepseek-v4-pro is protected ONLY via generate()/generate_structured(reasoning_enabled=False) [-> _call passes reasoning_enabled=False -> branch 3 -> floored to 32768]. The SAME model via reason() or generate_structured(reasoning_enabled=True) takes branch 2 -> NO floor -> a small max_tokens passes through RAW. So the task premise 'those 6 models are AUTO-PROTECTED' is true ONLY for the reasoning-OFF (generate) path; it is FALSE for the reasoning-ON path. The real starvation ceiling for deepseek-v4-pro on the branch-2 path is ~32768 (the floor exists precisely because in-code evidence at lines 1685-1702 shows V4 Pro emits ~5-18k reasoning tokens before content), NOT ~2000 — so the '<2000' rule of thumb under-counts for this model. PROTECTED (verified): sentence_repair.py:191 (generate, max_tokens=400, deepseek-v4-pro -> branch 3 -> 32768); multi_section_generator.py:5607 fact_dedup (generate, 2048 -> 32768); clinical_classifier.py:241 (generate, 200, default deepseek-v4-pro -> 32768); STORM persona/questions/answer storm_interviews.py:475/722/820 (generate_structured reasoning_enabled=False, deepseek-v4-pro -> 32768); searcher refiner generate_structured calls (reasoning_enabled defaults False -> 32768). KNOWN-GOOD self-managed (bypass openrouter_client clamp entirely via direct httpx, all GLM-5.1, budgets un-starved this session): entailment_judge (2000 tok, effort high), semantic_conflict_detector (2000), credibility_judge_caller (8000). OFF-PATH (not imported by run_honest_sweep_r3 / run_gate_b): react_agent.py, verifier.py (1067), verifier_v2.py, section_writer.py, smart_art_generator.py, data_analyzer.py, code_executor.py, evidence_database.py, corpus_brief.py, agents/planner.py; analyzer.analyze_sources GRADE call (analyzer.py:1059, reason effort=high 4096) has NO sweep caller and the analyzer's content-reading is force-disabled in benchmark, so it is latent-class but not fired. EXCLUDED deliberate probe: openrouter_client.py:3415 (max_tokens=50 liveness/validate_reasoning). ROOT-CAUSE FIX: branch 2 (`elif reasoning_enabled`) lacks the _REASONING_FIRST_MODELS floor that branch 3 has; hoist the floor ahead of the chain (or add it to branch 2) so reasoning-first models are protected on BOTH the generate AND reason paths. Per-site max_tokens raises are only the tactical patch.",
  "exposed": [
    {
      "file_line": "src/polaris_graph/agents/evidence_deepener.py:294-298",
      "model": "deepseek/deepseek-v4-pro (DEEPENER_LLM_MODEL = PG_SWEEP_DEEPENER_MODEL default; deepener_sweep_adapter.py:24,86)",
      "max_tokens": "2000 (hardcoded literal)",
      "reasoning": "_extract_named_studies() calls client.reason(effort=os.getenv('PG_DEEPENER_REASONING_EFFORT','high'), max_tokens=2000). reason() routes through _call with reasoning_enabled=True (openrouter_client.py:2412). Comment on line 296 'operator 2026-06-13: reasoning MAX' shows effort was raised to high this session while max_tokens stayed 2000 — exactly the #1251/#1252 freshly-introduced starvation class. On the live path: run_honest_sweep_r3.py:3813-3828 fires run_deepener_sync -> deepen_evidence -> _extract_named_studies (line 149).",
      "why_starved": "deepseek-v4-pro is reasoning-first but reason() sets reasoning_enabled=True, so _call takes branch 2 (elif reasoning_enabled, openrouter_client.py:1659) which applies NO floor. Branch 3's 32768 floor (line 1703) is skipped by the elif chain. V4 Pro emits ~5-18k reasoning tokens (per in-code evidence lines 1685-1702) before content, so a raw 2000 ceiling is consumed entirely by reasoning -> finish_reason=length -> content empty. The 32768 floor that protects generate() calls does NOT reach this reason() call.",
      "fix": "Raise to >= 32768 to match the reasoning-first floor: max_tokens=int(os.getenv('PG_DEEPENER_EXTRACT_MAX_TOKENS','32768')). Severity qualifier: fires only when PG_SWEEP_EVIDENCE_DEEPENER=1 + SEMANTIC_SCHOLAR_API_KEY present + borderline corpus (should_trigger_deepener), and an empty result silently degrades to the regex 'Author et al. (YYYY)' fallback (line 326) rather than crashing — so it is a silent capability loss, not a hard failure. Structural fix preferred: apply the _REASONING_FIRST_MODELS 32768 floor in branch 2 of openrouter_client._call too."
    },
    {
      "file_line": "src/polaris_graph/agents/evidence_deepener.py:815-819",
      "model": "deepseek/deepseek-v4-pro (DEEPENER_LLM_MODEL, same client)",
      "max_tokens": "500 (hardcoded literal)",
      "reasoning": "_mechanism_search() calls client.reason(effort=os.getenv('PG_DEEPENER_REASONING_EFFORT','high'), max_tokens=500). Same reason()->reasoning_enabled=True path. Line 817 carries the same 'operator 2026-06-13: reasoning MAX' comment — effort raised to high, max_tokens left at 500. On the live path via deepen_evidence -> _mechanism_search (line 216).",
      "why_starved": "Branch 2 (reasoning_enabled) applies no floor; 32768 floor (branch 3) is bypassed by the elif chain. 500 total tokens against a model that emits 5-18k reasoning tokens guarantees empty content (finish_reason=length before any content). Even more severely starved than the 2000-token site above.",
      "fix": "Raise to >= 32768: max_tokens=int(os.getenv('PG_DEEPENER_MECHANISM_MAX_TOKENS','32768')). Same severity qualifier (conditional deepener firing; empty LLM output degrades to _fallback_mechanism_queries deterministic queries at line 829, so silent capability loss not crash). Structural fix: floor reasoning-first models in branch 2."
    },
    {
      "file_line": "src/polaris_graph/agents/storm_interviews.py:1108-1113",
      "model": "deepseek/deepseek-v4-pro (PG_GENERATOR_MODEL; client built as _StormClient(model=_STORM_MODEL=PG_GENERATOR_MODEL) at run_honest_sweep_r3.py ~3311-3313)",
      "max_tokens": "4096 (PG_STORM_OUTLINE_MAX_TOKENS default, storm_interviews.py:43)",
      "reasoning": "_generate_outline_from_conversations() calls client.generate_structured(schema=StormOutlinePlan, max_tokens=PG_STORM_OUTLINE_MAX_TOKENS, reasoning_enabled=True). generate_structured passes reasoning_enabled through to _call unchanged (openrouter_client.py:3135). On the live path: run_storm_interviews (line 1186) -> _generate_outline_from_conversations (called at line 1473); STORM is enabled by the full-capability benchmark slate. This is the ONE STORM call with reasoning_enabled=True (line 1039 comment); the other three STORM calls pass reasoning_enabled=False and ARE floored to 32768.",
      "why_starved": "reasoning_enabled=True -> _call branch 2 (line 1659) -> NO floor; the 32768 floor (branch 3, for deepseek-v4-pro) is skipped by the elif chain. 4096 is below the documented ~5-18k reasoning footprint of V4 Pro, so on a long multi-perspective outline the reasoning can consume the whole budget and truncate the JSON. The 4096>2000 rule-of-thumb is misleading here: the real floor for this model on the reasoning-on path is ~32768. Lower confidence than the deepener sites because generate_structured has a robust _extract_json_from_text(result.reasoning) recovery (openrouter_client.py:3170-3185) and an outline's reasoning footprint may be shorter than a full report section — but 4096 < documented reasoning size is a real, un-floored risk and §-1.1 posture flags uncertainty rather than silently clearing it.",
      "fix": "Raise the default to match the reasoning-first floor: PG_STORM_OUTLINE_MAX_TOKENS default 4096 -> 32768 (storm_interviews.py:43). Or, root-cause: apply the _REASONING_FIRST_MODELS floor in branch 2 of openrouter_client._call so every reasoning-on call on these 6 models inherits 32768 automatically (covers this site, both deepener sites, and any future reason()/reasoning-on caller)."
    }
  ]
}
```


# ---- MODEL-LOCK PASS ----

```json
{
  "models": [
    {
      "model": "deepseek/deepseek-v4-pro",
      "sites": "src/polaris_graph/llm/openrouter_client.py:53,547-568 (PG_GENERATOR_MODEL + OPENROUTER_DEFAULT_MODEL default); generator/analyst_synthesis.py:446; generator/sentence_repair.py:148,259,?; retrieval/deepener_sweep_adapter.py:24 (PG_SWEEP_DEEPENER_MODEL); api/disambiguation_route.py:75; clinical_generator/real_completion.py:82; config/architecture/polaris_runtime_lock.yaml:50; config/settings/openrouter_provider_routing.yaml:8",
      "on_live_path": true,
      "conformant": true,
      "issue": "GENERATOR role. Matches the operator-signed lock (required_roles.generator.model_slug=deepseek/deepseek-v4-pro). Resolved live in the sweep via PG_GENERATOR_MODEL (run_honest_sweep_r3.py:3100,3140,6459,6491). In _REASONING_FIRST_MODELS so small caller max_tokens (e.g. sentence_repair=400) auto-floors to PG_REASONING_FIRST_MIN_MAX_TOKENS=32768 (openrouter_client.py:1703) — no starvation landmine. Open-weight MIT, non-US-vendor. CONFORMANT."
    },
    {
      "model": "z-ai/glm-5.1",
      "sites": "src/polaris_graph/llm/openrouter_client.py:579 (PG_MIRROR_MODEL), 586 (PG_EVALUATOR_MODEL=PG_MIRROR_MODEL fallback), 769 (_ALWAYS_REASON_MODELS); roles/openrouter_role_transport.py:158; authority/credibility_judge_caller.py:27 (_DEFAULT_MODEL); llm/entailment_judge.py:80 (_DEFAULT_ENTAILMENT_MODEL); retrieval/semantic_conflict_detector.py:68; config/serving/verifier_roles.yaml:40; config/settings/openrouter_provider_routing.yaml:20",
      "on_live_path": true,
      "conformant": true,
      "issue": "MIRROR role + the 3 side-judges (credibility/entailment/semantic-conflict) which per the lock legacy_compat map to the mirror. All defaults are glm-5.1 — the stale gemma defaults on these 3 judges were retired this session (I-arch-002, #1249/#1251/#1252). live_judge/external_evaluator resolve PG_EVALUATOR_MODEL -> glm-5.1. In _ALWAYS_REASON_MODELS so tiny caps (live_judge max_tokens=800, semantic_conflict/credibility) floor to PG_GLM5_MIN_MAX_TOKENS=4096 (openrouter_client.py:1656-1658) — no starvation landmine. Open-weight MIT, sovereign. CONFORMANT."
    },
    {
      "model": "minimax/minimax-m2",
      "sites": "src/polaris_graph/llm/openrouter_client.py:580 (PG_SENTINEL_MODEL), 397 (pricing); roles/openrouter_role_transport.py:162; config/serving/verifier_roles.yaml:70; config/settings/openrouter_provider_routing.yaml:39; config/architecture/polaris_runtime_lock.yaml:78",
      "on_live_path": true,
      "conformant": true,
      "issue": "SENTINEL role (certified claim-decomposition detector, replaced broken Granite Guardian). Matches lock model_slug=minimax/minimax-m2. Transport sets its own budget (decomp=131072, label=4096) reconciled against live provider caps, not the openrouter_client clamp (role_transport.py:669,710). Open-weight modified-mit (permissive), non-US-vendor. CONFORMANT."
    },
    {
      "model": "qwen/qwen3.6-35b-a3b",
      "sites": "src/polaris_graph/llm/openrouter_client.py:581 (PG_JUDGE_MODEL); roles/openrouter_role_transport.py:163; config/serving/verifier_roles.yaml:103; config/settings/openrouter_provider_routing.yaml:44; config/architecture/polaris_runtime_lock.yaml:91",
      "on_live_path": true,
      "conformant": true,
      "issue": "JUDGE role (terminal arbiter). Matches lock model_slug=qwen/qwen3.6-35b-a3b. Transport budget max_tokens=262140 (role_transport.py:704) = min max_completion across the judge chain (wandb 262144 / io-net 262140), does NOT exceed a pinned provider cap. Open-weight Apache-2.0, non-US-vendor. CONFORMANT."
    },
    {
      "model": "deepseek/deepseek-v4-flash",
      "sites": "src/polaris_graph/llm/openrouter_client.py:388 (pricing dict), 781 (_REASONING_FIRST_MODELS)",
      "on_live_path": false,
      "conformant": true,
      "issue": "Not a role selection — appears only as a pricing-table key and in the reasoning-first protection set. No env default or code path selects it for the sweep. Same family (deepseek) as the generator, so it is NOT a usable evaluator/judge, but it is never wired anywhere on the live path. Open-weight, conformant family. INERT."
    },
    {
      "model": "google/gemma-4-31b-it",
      "sites": "src/polaris_graph/llm/openrouter_client.py:400 (pricing dict), 689 (error-message recommendation f-string), 512/522/527 (comments); evaluator/external_evaluator.py:29 (docstring); clinical_generator/strict_verify.py:38,166 (docstring/comment); llm/entailment_judge.py:186 (comment); retrieval/nli_benchmark_annotator.py:109 (docstring); audit_ir/model_pin.py:26 (docstring example)",
      "on_live_path": false,
      "conformant": true,
      "issue": "FORBIDDEN gemma family, but NO live default resolves to it. Every occurrence is inert: a pricing-table key, the family-segregation error-message recommendation text (openrouter_client.py:689 is an f-string, not an assignment), stale docstrings/comments, or a docstring example in model_pin (the real sweep pin passes generator_model, run_honest_sweep_r3.py:2330). The live evaluator/judge defaults that previously pointed here were repointed to glm-5.1 this session. Stale doc/comment debt only — recommend scrubbing the recommendation string + docstrings, but NOT a runtime landmine. CONFORMANT (no live selection)."
    },
    {
      "model": "google/gemma",
      "sites": "src/polaris_graph/llm/openrouter_client.py:401 (pricing dict), 608 (_FAMILY_PREFIXES gemma prefix tuple)",
      "on_live_path": false,
      "conformant": true,
      "issue": "Appears only as a pricing-dict key and as a family-detection prefix (used to DETECT and family-segregate gemma, i.e. part of the guardrail, not a selection). No code path defaults to it. INERT/guardrail."
    },
    {
      "model": "google/gemini",
      "sites": "src/polaris_graph/llm/openrouter_client.py:402 (pricing dict), 618 (_FAMILY_PREFIXES google-closed prefix)",
      "on_live_path": false,
      "conformant": true,
      "issue": "Closed-source google family. Present only as a pricing key and the 'google-closed' family-detection prefix (the no-closed-source guardrail's detector). No live default selects it. INERT/guardrail."
    },
    {
      "model": "openai/* (gpt-)",
      "sites": "src/polaris_graph/llm/openrouter_client.py:616 (_FAMILY_PREFIXES 'openai': ('openai/','gpt-'))",
      "on_live_path": false,
      "conformant": true,
      "issue": "Closed-source family registered ONLY for detection/segregation (so it can be refused), per the family_policy comment 'closed-source family fallbacks are FORBIDDEN at runtime'. No model string of this family is defaulted or selected anywhere on the live path. Guardrail entry. CONFORMANT."
    },
    {
      "model": "anthropic/* (claude-)",
      "sites": "src/polaris_graph/llm/openrouter_client.py:617 (_FAMILY_PREFIXES 'anthropic': ('anthropic/','claude-'))",
      "on_live_path": false,
      "conformant": true,
      "issue": "Closed-source family registered ONLY for detection/segregation. No live default or selection. Guardrail entry. CONFORMANT."
    },
    {
      "model": "gemini-2.5-flash / gemini-3-pro-preview / gemini-2.5-pro",
      "sites": "config/settings/models.yaml:40,52,58,67 (llm primary + fallback_model)",
      "on_live_path": false,
      "conformant": false,
      "issue": "Closed-source Google Gemini models configured as the LEGACY GEMINI agent stack (consumers per the file's own SCOPE header: src/config/core.py, src/llm/gemini_client.py, src/utils/atomic_decomposer.py). These are non-conformant model strings BUT they are NOT reachable from the DR-benchmark live path: verified that NO module under src/polaris_graph imports src.llm / gemini_client / src.config.core / google.generativeai (grep returned zero hits), and run_honest_sweep_r3.py imports only src.polaris_graph.* + src.polaris_v6.queue. So out-of-scope legacy config; flagged per the 'pay special attention to google/gemini' directive. Recommend retiring with pipeline-C/legacy cleanup, but it cannot leak onto the live inference path as wired today."
    },
    {
      "model": "cross-encoder/nli-deberta-v3-base",
      "sites": "src/polaris_graph/agents/verifier.py:1581-1582 (PG_CONTRADICTION_MODEL default); audit_ir/model_pin.py (pinned env)",
      "on_live_path": false,
      "conformant": true,
      "issue": "Local open-weight HF NLI CrossEncoder (sentence-transformers), used for contradiction detection. NOT one of the 4 locked LLM roles and the no-gemma/no-closed-source rule targets the LLM vendor inference path, not local encoders, so sovereignty-fine. Reached via agents/verifier (LangGraph pipeline-B agentic path), NOT from the sweep: run_honest_sweep_r3 imports retrieval.contradiction_detector which contains no CrossEncoder, and does not import agents.verifier. PG_CONTRADICTION_ENABLED defaults '1' but the loader at verifier.py:1575 is not on the sweep import closure. on_live_path=false for the DR sweep; conformant (open-weight, outside the 4-role lock)."
    },
    {
      "model": "flan-t5-large (PG_NLI_MODEL) / ssz1111/FaithLens (PG_FAITHLENS_MODEL)",
      "sites": "src/polaris_graph/agents/nli_verifier.py:34,64; audit_ir/model_pin.py:130-131",
      "on_live_path": false,
      "conformant": true,
      "issue": "Local open-weight HF NLI models. Gated OFF by default: PG_NLI_ENABLED defaults '0' (agents/verifier.py:161, nli_verifier path). Open-weight, outside the 4-role LLM lock, sovereignty-fine. Not active on the live sweep unless explicitly enabled. CONFORMANT."
    },
    {
      "model": "whisper base (WHISPER_MODEL)",
      "sites": "src/polaris_graph/document_ingester.py:63",
      "on_live_path": false,
      "conformant": true,
      "issue": "Local open-weight Whisper ASR model for document/audio ingestion. Not part of the DR text-sweep generation/verification path. Open-weight, outside the 4-role lock. CONFORMANT/out-of-scope."
    },
    {
      "model": "gemini_* / claude_* / gpt_* (sota_baselines.json + sota_parameters.yaml)",
      "sites": "config/sota_baselines.json:15,30,36,55-124; config/settings/sota_parameters.yaml (Gemini DR references); config/settings/thresholds.yaml:92",
      "on_live_path": false,
      "conformant": true,
      "issue": "These are BASELINE/COMPARISON benchmark DATA and parameter-tuning references (competitor Deep-Research scores, Gemini DR search-volume targets), NOT runtime model selections. No code constructs a client from these strings. Correctly classed as comparison data, not a live model string. Out-of-scope for the conformance rule."
    }
  ]
}
```
