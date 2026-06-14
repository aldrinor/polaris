# Codex INDEPENDENT chokepoint investigation — g2_token_caps

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this is (operator §-1.1: BOTH Claude and Codex run independent line-by-line audits in parallel; cross-review combines findings)
You are the INDEPENDENT second auditor. POLARIS deep-research pipeline, repo root is the current dir (C:\POLARIS).
Live run path = scripts/run_honest_sweep_r3.py + scripts/dr_benchmark/run_gate_b.py and everything they import
(generator/multi_section_generator, generator/provenance_generator, roles/*, authority/*, retrieval/*, agents/*,
llm/openrouter_client). UI (web/**), frozen legacy (src/orchestration/**), tests = OUT OF SCOPE.

CONTEXT: a 3-hour validation run just DIED at status=error_unexpected — a report section exceeded a 600s
wall-clock TWICE and the section gathers lack return_exceptions=True so one slow section cancels all siblings
and crashes the whole run. The 600s came from a smoke env file (PG_SECTION_WALLCLOCK_SECONDS=600,
PG_LLM_TIMEOUT_SECONDS=300); code default is 0=unlimited / GENERATOR_TIMEOUT=1800. Operator directives:
timeouts UNLIMITED-with-watchdog OR 1.5x the realistic generate time (sized off the 64000-token section
budget, not the stale 16384); EVERY param must be a PG_ .env var (hardcoding is "super lethal"); the pipeline
MUST have CHECKPOINTS (carry DATA not VERDICTS — always re-run faithfulness gates on resume). Locked models:
generator=deepseek/deepseek-v4-pro, mirror=z-ai/glm-5.1, sentinel=minimax/minimax-m2, judge=qwen/qwen3.6-35b-a3b;
no gemma/closed-source on the live path.

## YOUR JOB — independently re-investigate YOUR dimensions (reasoning_token_caps, output_caps_and_mixing) line-by-line in the LIVE code, then for
## EACH Claude finding below: CONFIRM / REFUTE / PARTIAL by reading the actual file:line yourself (do NOT
## just agree). Then find any chokepoint in your dimensions Claude MISSED. Read the API/code, don't guess.

## Output schema (YAML, required — loose prose rejected):
```yaml
verdict: APPROVE | REQUEST_CHANGES   # APPROVE iff Claude's findings for your dims are sound AND complete (no missed P0/P1)
confirmed: [ ...finding locations you verified correct... ]
refuted: [ {location: , why_claude_is_wrong: } ]
partial: [ {location: , correction: } ]
novel_chokepoints: [ {location: , what: , why_it_chokes: , fix: , severity: P0|P1|P2|P3} ]
notes: ""
```

## CLAUDE'S FINDINGS FOR YOUR DIMENSIONS (verify each against the real code):


### dimension: reasoning_token_caps
Claude SUMMARY: Live DR path = run_honest_sweep_r3.py + dr_benchmark/run_gate_b.py and their imports. I audited every reasoning-budget site claim-by-claim against code. SCOPE CLOSED (no sampling): IN-PATH and audited = llm/openrouter_client.py (central _call_impl reasoning branches), generator/multi_section_generator.py, generator/evidence_distiller.py, agents/evidence_deepener.py, agents/analyzer.py, tools/react_agent.py, roles/openrouter_role_transport.py, roles/sentinel_adapter.py (no independent reasoning cap — transport owns the body), llm/entailment_judge.py, authority/credibility_judge_caller.py, retrieval/semantic_conflict_detector.py. OUT OF SCOPE (confirmed NOT imported by either entrypoint): llm/loopback_client.py (sovereign self-host passthrough, reports reasoning OK, not the OpenRouter benchmark path), clinical_generator/real_completion.py (comment-mentioned only, not imported), api/disambiguation_route.py (UI/API), generator/analyst_synthesis.py (no reasoning sites). OVERALL VERDICT: the I-arch-003/I-arch-002 (2026-06-13/14) campaign un-starved the section generator (PG_SECTION_MAX_TOKENS=64000, 40% reasoning = 25600 > V4 Pro's documented ~17-18k burn) and the three side judges (entailment 2000, credibility 8000, semantic-conflict 2000, all with effort coerced UP to high). BUT the newer distiller MAP/REDUCE keystone paths kept the OLD small EXPLICIT reasoning_max_tokens caps (4096/5000) on the SAME V4-Pro model — a ~5x tighter reasoning budget than the legacy section path, and 

- [P1] src/polaris_graph/generator/evidence_distiller.py:108-109 (consumed at multi_section_generator.py:2087)
  WHAT: REDUCE keystone path (I-perm-016) hard-caps V4-Pro reasoning at 5000 tokens for full-section synthesis
  CURRENT: _reduce_reasoning_tokens() = PG_DISTILL_REDUCE_REASONING_TOKENS default 5000; passed as reasoning_max_tokens to client.generate() on model=generator (deepseek-v4-pro)
  CLAUDE_FIX: Raise PG_DISTILL_REDUCE_REASONING_TOKENS default to >=20000 (above V4 Pro's documented burn) to match the un-starved legacy section path, and verify enforcement via GET /api/v1/models/deepseek/deepseek-v4-pro/endpoints on the pinned chain. max_tokens is usage-billed so a generous reasoning budget is
  WHY: deepseek-v4-pro is reasoning-first and emits ~17-18k reasoning tokens before content per the code's own I-gen-003 evidence (openrouter_client.py:1702-1710). A 5000-token reasoning cap on full-section REDUCE synthesis is ~3.5x below that burn. The legacy section path was un-starved by I-arch-003 (40% of 64000 = 25600 reasoning), but this NEWER keystone path kept the old small explicit cap on the SA

- [P2] src/polaris_graph/generator/evidence_distiller.py:100-101 (consumed at evidence_distiller.py:1045 via _map_one_source)
  WHAT: MAP per-source distill path hard-caps V4-Pro reasoning at 4096 tokens
  CURRENT: _map_reasoning_tokens() = PG_DISTILL_MAP_REASONING_TOKENS default 4096; passed as reasoning_max_tokens to client._call(reasoning_enabled=False) on model=generator (deepseek-v4-pro)
  CLAUDE_FIX: Raise PG_DISTILL_MAP_REASONING_TOKENS default to a value above the realistic per-source MAP reasoning burn (measure on the pinned chain; >=8000 as a starting floor) OR drop the explicit cap and let branch 3's 40%-of-max_tokens computation apply. Verify enforcement before trusting current value as a 
  WHY: Same model/burn asymmetry as REDUCE. 4096 reasoning is ~4x below V4 Pro's documented ~17-18k. MAP is per-source extraction (lighter than full synthesis) so the burn may be smaller, but the cap is still an explicit sub-burn reasoning ceiling on a reasoning-first model that the I-arch-003 sweep did not touch. Same enforcement caveat: provider no-op is unverified post-re-pin. If enforced -> truncated

- [P2] src/polaris_graph/roles/openrouter_role_transport.py:274-278
  WHAT: Only the 4-role transport uses true-MAX reasoning effort (xhigh); every other reasoning site defaults to 'high', which this same module documents as a silent downgrade of the operator MAX directive
  CURRENT: _REASONING_EFFORT = os.getenv('PG_FOUR_ROLE_REASONING_EFFORT', 'xhigh'); the module comment (274-276) states 'high is a LOWER allocation, so the prior high default silently DOWNGRADED the operator MAX-reasoning directive'. Side judges, GRADE, deepener, react-scaffold/critique all default 'high'.
  CLAUDE_FIX: Introduce a single shared default PG_REASONING_EFFORT_MAX='xhigh' and route all V4-Pro/Qwen reason()-path effort defaults through it (deepener, GRADE, react critique/scaffold), matching the 4-role transport. Leave GLM-path side judges at 'high' (no-op) but document why. Confirm xhigh vs high allocat
  WHY: The operator directive is reasoning effort ALWAYS goes MAX. If 'high' < 'xhigh' on a model that honors the distinction, every non-4-role reasoning call runs at sub-MAX. This is MOOT on GLM paths (effort is a documented no-op on GLM per transport:688 — max_tokens binds, and those are un-starved), so entailment/credibility/semantic-conflict effort='high' is fine. But it is a REAL sub-MAX default on 

- [P2] src/polaris_graph/tools/react_agent.py:5931
  WHAT: ReAct interpretation-critique reason() call hardcodes max_tokens=2048 (top-level), starving the reasoning+verdict budget if the agent model is NOT reasoning-first
  CURRENT: max_tokens=2048 (HARDCODED literal, not env); effort=os.environ.get('PG_CRITIQUE_REASONING_EFFORT','high'). Comment claims 'max_tokens routes through openrouter_client so the reasoning-first floor (>=4096/16384) applies'.
  CLAUDE_FIX: Replace the literal 2048 with int(os.getenv('PG_CRITIQUE_MAX_TOKENS','16384')) so the budget is env-governed and generous regardless of model family; do not rely on the reasoning-first floor to silently rescue a hardcoded small value.
  WHY: The claimed protection (reasoning-first 32768 floor) ONLY applies if the injected agent client model is in _REASONING_FIRST_MODELS. For any non-reasoning-first scaffold/agent model, 2048 top-level max_tokens with effort=high means reasoning consumes the budget and the InterpretationCritique JSON verdict truncates -> empty -> schema-parse skip. Even on a reasoning-first model, hardcoding 2048 viola

- [P2] src/polaris_graph/tools/react_agent.py:2384-2385
  WHAT: ReAct analysis-scaffold reason() call hardcodes both effort='high' and max_tokens=4096
  CURRENT: effort="high" (HARDCODED, not env), max_tokens=4096 (HARDCODED, not env), timeout=_SCAFFOLD_TIMEOUT
  CLAUDE_FIX: Make both env-governed: effort=os.getenv('PG_REACT_SCAFFOLD_REASONING_EFFORT','xhigh'), max_tokens=int(os.getenv('PG_REACT_SCAFFOLD_MAX_TOKENS','16384')). Align effort default with the 4-role transport's xhigh.
  WHY: Two non-governed budgets on a reasoning() call. effort='high' is sub-MAX vs xhigh on models that honor it (operator: effort ALWAYS MAX). max_tokens=4096 on a non-reasoning-first agent model leaves little room after reasoning for the framework output; on a reasoning-first model the 32768 floor rescues it but the literal still violates the EVERY-budget-is-an-env-var rule. The hardcoding is the letha

- [P3] src/polaris_graph/agents/analyzer.py:2072 and 2233
  WHAT: Source-analysis extraction caps reasoning at 2048 tokens (PG_EXTRACTION_REASONING_MAX_TOKENS) to curb GLM runaway
  CURRENT: reasoning_max_tokens=int(os.getenv('PG_EXTRACTION_REASONING_MAX_TOKENS','2048')); reasoning_enabled=False, max_tokens=16384 (PG_EXTRACTION_MAX_TOKENS). Comment: caps GLM-5.1 runaway reasoning observed at 10,813 tokens/batch.
  CLAUDE_FIX: Re-derive the cap empirically against the largest real batch (DUR-2 batch_size=3): if GLM's useful extraction reasoning exceeds 2048 on multi-source batches, raise the default to cover the p95 burn (e.g. 4096-6000) while still bounding the 10,813 runaway. Keep it env-governed (already is).
  WHY: This is a DELIBERATE cap on the GLM-5.1 evaluator/extractor (not the V4-Pro generator) because GLM always reasons server-side even with reasoning_enabled=False and ran to 10,813 tokens. GLM HONORS reasoning.max_tokens (transport:688), so 2048 is genuinely binding. For a 3-source x ~15-fact batch, 2048 reasoning may truncate the analytical pass on complex multi-source batches -> degraded SourceAnal


### dimension: output_caps_and_mixing
Claude SUMMARY: Line-by-line trace of every max_tokens (output) cap and every reasoning/output-budget conflation on the DR-benchmark run path (run_honest_sweep_r3 -> multi_section_generator -> openrouter_client + roles/* + the 3 side-judges). HEADLINE: the run that died at error_unexpected died on the WALL-CLOCK (timeout dimension), NOT on an output cap — post-I-arch-003 the LIVE generator path and the native 4-role verifier transport are largely un-starved. The genuine in-dimension defects are about MIXING and DEAD KNOBS, not raw starvation: (1) THE CORE CONFLATION — the 3 reasoning side-judges (entailment / semantic_conflict / credibility, all GLM-5.1, a reasoning model) each carry ONE max_tokens that must hold BOTH the reasoning burn AND the JSON verdict, with reasoning sized only by `reasoning.effort:high` and NO separate `reasoning.max_tokens` cap — reasoning eats first, the verdict gets the remainder. The 4-role Judge (same model class) was raised by I-arch-003 to 262140 WITH the structural `reasoning_cap << total` separation, while these three were only raised to 2000/2000/8000 under effort-based reasoning with no numeric separation — a 30-130x asymmetry across structurally identical faithfulness-critical reasoning judges, which is exactly the conflation this dimension hunts. (2) DEAD/MISLEADING KNOBS — every small generator-targeted cap (outline 2500, fact_dedup 2048, sentence_repair 400, trial-table 800, limitations/m50 400, REDUCE 8192, STORM questions/answers 1024/2048) is silentl

- [P1] src/polaris_graph/retrieval/semantic_conflict_detector.py:373-380 (max_tokens at :377, reasoning at :378)
  WHAT: Semantic-conflict side-judge (GLM-5.1, a REASONING model) builds a raw httpx body with a SINGLE max_tokens=2000 that must hold BOTH the reasoning burn AND the JSON conflict verdict, while reasoning is sized ONLY by reasoning.effort=high with NO separate reasoning.max_tokens. One pool, reasoning consumes first.
  CURRENT: max_tokens = max(256, PG_SEMANTIC_CONFLICT_MAX_TOKENS default 2000); reasoning = {effort: high}; model default z-ai/glm-5.1; gated by the credibility-redesign / conflict-detection lane
  CLAUDE_FIX: Mirror the I-arch-003 4-role pattern: set an explicit numeric reasoning.max_tokens (e.g. PG_SEMANTIC_CONFLICT_REASONING_MAX_TOKENS) STRICTLY below the total, and raise the total well above it (the invariant reasoning_cap + verdict_room << max_tokens), so the conflict verdict can never be crowded out
  WHY: effort=high on GLM lets thinking run unbounded against the 2000 total; the I-arch-002 history in this very file shows max_tokens=60 already truncated mid-reasoning -> empty content -> json.loads(None) -> fail-open NEUTRAL (silently MISSES a real contradiction). 2000 un-starves the 60-token crash but is the SAME single-pool design with no structural reasoning<<total guarantee, unlike the 4-role Jud

- [P1] src/polaris_graph/llm/entailment_judge.py:97 (_DEFAULT_ENTAILMENT_MAX_TOKENS=2000), 245-252 (body: max_tokens at :249, reasoning at :250)
  WHAT: Strict-verify NLI entailment side-judge (GLM-5.1 reasoning model) — SINGLE max_tokens=2000 holds BOTH reasoning and the ENTAILED/NEUTRAL/CONTRADICTED JSON verdict; reasoning sized only by reasoning.effort (default high, sub-max coerced UP), NO separate reasoning.max_tokens.
  CURRENT: _DEFAULT_ENTAILMENT_MAX_TOKENS = 2000 (PG_ENTAILMENT_MAX_TOKENS); reasoning {effort: high}; gated by PG_STRICT_VERIFY_ENTAILMENT (default OFF)
  CLAUDE_FIX: Add an explicit numeric reasoning.max_tokens (PG_ENTAILMENT_REASONING_MAX_TOKENS) below the total and raise max_tokens above it to preserve reasoning_cap << total, matching the 4-role Judge's structural separation. Do not relax the entailment verdict itself.
  WHY: Same single-pool conflation as the semantic-conflict judge. In-file I-arch-002 history: max_tokens=100 burned the whole budget on reasoning -> finish=length, EMPTY content -> coverage collapse (the drb_72-class over-drop). 2000 measured to finish=stop today, but there is no structural reasoning<<total guard; a harder span can re-truncate. The 4-role Judge (identical model class, identical faithful

- [P2] src/polaris_graph/authority/credibility_judge_caller.py:36 (_DEFAULT_MAX_TOKENS=8000), 117-125 (body: max_tokens at :121, reasoning at :124)
  WHAT: Credibility side-judge (GLM-5.1 reasoning model) — SINGLE max_tokens=8000 holds BOTH reasoning and the credibility JSON; reasoning sized only by reasoning.effort=high, NO separate reasoning.max_tokens.
  CURRENT: _DEFAULT_MAX_TOKENS = 8000 (PG_CREDIBILITY_JUDGE_MAX_TOKENS); reasoning {effort: high}; model z-ai/glm-5.1; gated by PG_SWEEP_CREDIBILITY_REDESIGN
  CLAUDE_FIX: Add PG_CREDIBILITY_JUDGE_REASONING_MAX_TOKENS (numeric reasoning cap strictly below the 8000 total) to enforce reasoning_cap << total, harmonizing all reasoning judges on the I-arch-003 separation pattern.
  WHY: Single-pool conflation. In-file I-arch-002 history: max_tokens=512 truncated mid-thought (finish=length) -> judge_error + a sync httpx call that FROZE the asyncio loop. 8000 is more generous than the other two side-judges but is still effort-only reasoning with no numeric reasoning<<total guarantee; a verbose reasoning trace can still crowd the verdict. Consistent treatment with the 4-role Judge's

- [P2] src/polaris_graph/generator/multi_section_generator.py:5070 (outline 2500), 2793 (sentence_repair 400), 5607 (fact_dedup 2048), 6349 (trial table 800), 6192 (limitations 400), 6424 (m50 subsection 400)
  WHAT: Six small fixed/low max_tokens caps on generator-targeted (deepseek-v4-pro) calls. Because deepseek-v4-pro is in _REASONING_FIRST_MODELS, openrouter_client _call_impl branch-4 (line 1720-1722) silently FLOORS every request UP to PG_REASONING_FIRST_MIN_MAX_TOKENS=32768. So these caller values are dead/overridden — the operator-facing intent is a lie, and a non-reasoning-first model override (PG_*_MODEL) would NOT be floored and could genuinely starve.
  CURRENT: outline_max_tokens=2500 (param default), sentence_repair max_tokens=400, fact_dedup max_tokens=2048, trial_summary_table_max_tokens=800, limitations_max_tokens=400, m50_subsection_max_tokens=400 — several are hardcoded literals, not env vars
  CLAUDE_FIX: Make every literal an env var, and set the defaults at or above the reasoning-first floor (32768) so the surfaced value matches the executed value and so a non-floored model override is not starved. Stop relying on the branch-4 floor as a silent rescue.
  WHY: Not starvation on deepseek (floor rescues to 32768) but a CORRECTNESS/transparency defect: the knob shown to the operator (e.g. 400) is not what runs (32768). The hardcoded literals (400/2048/800) violate LAW VI. If an operator points PG_SWEEP_*/PG_*_MODEL at a non-reasoning-first model, the floor does not apply and 400 tokens truncates a real extraction/repair/dedup output -> dropped content.

- [P2] src/polaris_graph/generator/evidence_distiller.py:104-105 (_reduce_max_tokens=8192), 108-109 (_reduce_reasoning_tokens=5000); consumed at multi_section_generator.py:2082-2088
  WHAT: REDUCE keystone section-writer path (I-perm-016) passes max_tokens=PG_DISTILL_REDUCE_MAX_TOKENS=8192 AND reasoning_max_tokens=PG_DISTILL_REDUCE_REASONING_TOKENS=5000 to the deepseek-v4-pro generator. 8192 is BELOW the 32768 reasoning-first floor, so the operator's 8192 knob is silently overridden UP to 32768 (a no-op knob); the 5000 reasoning cap is passed to the provider but the code itself notes (openrouter_client ~1699-1701) the provider does NOT enforce reasoning.max_tokens for V4 Pro.
  CURRENT: PG_DISTILL_REDUCE_MAX_TOKENS=8192, PG_DISTILL_REDUCE_REASONING_TOKENS=5000 (also MAP: PG_DISTILL_MAP_MAX_TOKENS=8192, PG_DISTILL_MAP_REASONING_TOKENS=4096); REDUCE path gated by PG_USE_RESEARCH_PLANNER (default OFF — the drb_76/run-that-died ran OFF-mode legacy, so this is LATENT, not the live death
  CLAUDE_FIX: Raise PG_DISTILL_REDUCE_MAX_TOKENS to at least the legacy PG_SECTION_MAX_TOKENS level (e.g. 64000) so REDUCE sections get parity with legacy, and stop relying on the silent floor. Document that reasoning_max_tokens is advisory for V4 Pro and size the TOTAL to absorb the full ~18k reasoning burn plus
  WHY: Two defects: (a) the 8192 knob is a lie — branch-4 floors it to 32768, so an operator tuning PG_DISTILL_REDUCE_MAX_TOKENS sees no effect; (b) reasoning/output mixing — after the floor, 32768 total minus V4-Pro's ~17-18k reasoning burn (the 5000 reasoning_max_tokens is unenforced per the code's own note) leaves ~14k content, roughly HALF the 64000 legacy section budget, which can truncate a large c

- [P2] src/polaris_graph/roles/judge_adapter.py:35 (_DEFAULT_MAX_TOKENS=16), 98/122/140 (request param). Override only at openrouter_role_transport.py:726-729; self-host openai_compatible_transport.py:_build_body:294-307 does NOT override the judge.
  WHAT: Terminal-arbiter Judge (Qwen3.6, a reasoning model) request hardcodes max_tokens=16. On the LIVE benchmark OpenRouter transport this is overridden to 262140 (safe). But on the SELF-HOST transport (PG_FOUR_ROLE_TRANSPORT=self_host — the lock's sovereign serving route) the 16 is the only allowlisted max_tokens and is NOT overridden; _build_body only floors the Sentinel.
  CURRENT: _DEFAULT_MAX_TOKENS = 16 (hardcoded literal, no env var); self-host transport keeps it; the self-host code explicitly handles reasoning <think> separation and reasoning-budget-exhaustion blanks for Qwen, so the judge CAN reason on self-host
  CLAUDE_FIX: Make the judge max_tokens an env var (PG_JUDGE_MAX_TOKENS) defaulting to a generous reasoning-safe value, and have the self-host transport (_build_body) apply the same generous override/floor for the judge role that the OpenRouter transport already applies, so the enum verdict has reasoning room on 
  WHY: On self-host, a reasoning Qwen with a 16-token TOTAL budget burns all 16 on reasoning -> empty content -> parse_judge_verdict raises JudgeEnumError, which run_judge deliberately does NOT catch (fail-loud) -> the exact mid-run error_unexpected crash class the operator is fighting. Latent because the benchmark default transport is openrouter (which overrides to 262140), but it is the documented FINA

- [P3] src/polaris_graph/generator/multi_section_generator.py:220 (PG_SECTION_MAX_TOKENS=64000) — consumed at the legacy OFF-mode section call :2407-2411 (the actually-LIVE path on the run that died)
  WHAT: The primary section-writer output budget on the live legacy path is PG_SECTION_MAX_TOKENS=64000, deliberately bounded ~6x BELOW the 384000 provider max (and below PG_REASONING_FIRST_HARD_CAP=384000) to avoid a multi-minute wall-clock runaway.
  CURRENT: PG_SECTION_MAX_TOKENS = 64000 (env-overridable); deepseek-v4-pro, branch-4 honors it verbatim (between the 32768 floor and the 384000 cap)
  CLAUDE_FIX: Keep 64000 as the default (it is not starving anything) but document explicitly that it is a deliberate sub-max ceiling chosen for wall-clock, and that operators wanting true MAX can raise it toward 384000; ensure the wall-clock guard (separate dimension) is sized to the chosen ceiling so a generous
  WHY: Does NOT choke real sections today: ~8-30k output observed vs a 64000 ceiling = ample headroom (this is generous, not a starvation cap). Flagged only because under the operator's literal 'generation tokens go MAX' directive a budget set below the provider max is an intentional cap-below-max; the code's stated rationale is wall-clock-runaway avoidance, which is a TIMEOUT concern, not an output-budg

- [P3] src/polaris_graph/roles/openrouter_role_transport.py:630-631 (docstring) vs actual code at :726-728 (Judge 262140) and :735-736 (Sentinel 4096)
  WHAT: The _build_openrouter_body docstring still states the OLD defaults ('PG_VERIFIER_REASONING_MAX_TOKENS, default 16384' and 'PG_SENTINEL_MAX_TOKENS, default 256') while the code now uses 262140 (Judge) and 4096 (Sentinel classifier) after I-arch-003. The native 4-role transport itself is correctly mixed (Mirror reasoning_cap 100000 << 131072 total; Sentinel decomp 131072; Judge 262140) — no starvation, just stale docs.
  CURRENT: docstring says default 16384 / 256; code: PG_VERIFIER_REASONING_MAX_TOKENS default 262140, PG_SENTINEL_MAX_TOKENS default 4096
  CLAUDE_FIX: Update the docstring to the current I-arch-003 defaults (262140 Judge / 131072 Mirror+Sentinel-decomp / 4096 Sentinel-classifier) and the reasoning_cap << total invariant, so the documented and executed budgets agree.
  WHY: Does not choke runtime (code is correct and well-separated). It is a maintenance/clarity hazard: an operator reading the docstring to size a budget would set a value ~16x too low, re-introducing a verifier-starvation regression. In a clinical-safety pipeline, stale budget docs on the verifier transport are a real footgun.
