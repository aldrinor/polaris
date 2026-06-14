# Codex INDEPENDENT chokepoint investigation — g3_providers_models_schemas

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

## YOUR JOB — independently re-investigate YOUR dimensions (providers, models, schemas) line-by-line in the LIVE code, then for
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


### dimension: providers
Claude SUMMARY: Audited the provider-routing surface for the live DR-benchmark run path (config/settings/openrouter_provider_routing.yaml, roles/provider_routing.py, the generator provider block in llm/openrouter_client.py:1762-1797, and the Path-B preflight gate scripts/dr_benchmark/pathB_run_gate.py). MECHANISM CALIBRATION (verified against openrouter_client.py:1956-2002): an over-budget request does NOT 400. Under allow_fallbacks:false + a pinned order, OpenRouter cap-filters its /endpoints by max_completion_tokens and returns a STRUCTURAL 404 'No endpoints found' when no surviving provider can serve the requested budget; the code raises NoEndpointError and fails the run loud — the I-arch-003 starvation disease surfaced as a routing 404. The blocking lever is allow_fallbacks:false + endpoint cap-filtering, NOT require_parameters (which only checks param SUPPORT like reasoning; the YAML/code comments conflate the two). KEYSTONE (P1): the generator path has no chain-min max_tokens clamp like the 4-role transport, and its chain's terminal `deepseek` entry has no committed cap verification. P1: the Path-B gate resolve_role_provider (pathB_run_gate.py:420) reads the /endpoints payload but never checks max_completion_tokens against the budget, so it can pin a low-cap provider (e.g. DeepInfra fp4/16384) and pass preflight, then 404 mid-run. P2: the openrouter_client env-order branch does not force allow_fallbacks=false, and PG_OPENROUTER_PROVIDER_ROUTING=0 leaves fallbacks on with no order = ful

- [P1] src/polaris_graph/llm/openrouter_client.py:1751-1753 vs config/settings/openrouter_provider_routing.yaml:14
  WHAT: Generator max_tokens has NO chain-min reconciliation. The 4-role transport clamps every verifier DOWN to the MIN max_completion_tokens of its pinned chain (_MIRROR/_SENTINEL/_JUDGE_MAX_TOKENS_CHAIN_MIN). The generator path applies only PG_REASONING_FIRST_HARD_CAP=384000 with no clamp to the real min cap of its order [wandb,siliconflow,baidu,novita,streamlake,gmicloud,deepseek]. The terminal `deepseek` first-party entry has zero committed cap verification in-repo (gmicloud verified in YAML; wandb/parasail live-verified; streamlake/siliconflow/baidu/novita only asserted by the I-arch-003 ledger; `deepseek` nowhere).
  CURRENT: order=[wandb,siliconflow,baidu,novita,streamlake,gmicloud,deepseek], allow_fallbacks:false, requested max_tokens up to PG_REASONING_FIRST_HARD_CAP=384000; no _GENERATOR_MAX_TOKENS_CHAIN_MIN clamp.
  CLAUDE_FIX: Mirror the 4-role transport: clamp body['max_tokens']=min(requested, PG_GENERATOR_MAX_TOKENS_CHAIN_MIN) re-derived from the generator chain's actual min cap, AND either drop the unverified `deepseek` terminal entry (as atlas-cloud was dropped from the judge chain, YAML:49-55) or commit a live /endpo
  WHY: Under allow_fallbacks:false, OpenRouter cap-filters the chain by max_completion_tokens. If only low-cap members survive a partial outage (e.g. `deepseek` first-party, historically fp4/16384 per the repeated YAML+code comments), the 384000 request matches NO endpoint -> structural 404 'No endpoints found' -> NoEndpointError (openrouter_client.py:1998) -> the section/run dies loud. Same I-arch-003 s

- [P1] scripts/dr_benchmark/pathB_run_gate.py:420-471 (resolve_role_provider)
  WHAT: The Path-B preflight gate resolves each role's served provider by intersecting OPENROUTER_PROVIDER_ORDER with status==0 endpoints and returning the FIRST match. It fetches the full /api/v1/models/<id>/endpoints payload (which carries max_completion_tokens per endpoint) but NEVER checks the resolved provider's cap against the role's requested max_tokens, so a low-cap provider passes preflight as eligible.
  CURRENT: Eligibility = status is None or status==0 only (line 453-454); selection = first env-order match (line 464-467). No max_completion_tokens / context_length check against the generator's 384000 (or any role budget).
  CLAUDE_FIX: After building `eligible`, also read each endpoint's max_completion_tokens (fall back to context_length when null) and skip any provider whose cap < the role's resolved max_tokens; GateError loud if none in the order clears it. This makes preflight catch the 404-class before spend.
  WHY: The live DR run goes run_gate_b -> this gate. If OPENROUTER_PROVIDER_ORDER lists a provider that is up but caps below budget (e.g. DeepInfra fp4/16384 for deepseek-v4-pro), the gate PINS it (order=[that one], allow_fallbacks:false) and reports full-power; then every 384000-token generator call returns a structural 404 'No endpoints found' and the run dies after burning retrieval cost — a false pre

- [P2] src/polaris_graph/llm/openrouter_client.py:1762-1797
  WHAT: Two fail-open routing paths. (a) The env-order branch (`elif provider_order:`, 1782-1783) sets `order` but does NOT force allow_fallbacks=false — it stays at OPENROUTER_ALLOW_FALLBACKS default 'true' (1765) unless the operator separately sets it. (b) When PG_OPENROUTER_PROVIDER_ROUTING=0, role_provider_routing returns None, the `else` sets nothing, so the generator runs allow_fallbacks=true + NO order = unrestricted auto-route to ANY provider incl. the fp4/16384 DeepInfra the chain deliberately excludes.
  CURRENT: allow_fb = OPENROUTER_ALLOW_FALLBACKS default 'true' (1765); env-order branch leaves it true; routing-disabled branch leaves order unset + fallbacks true. Only the Path-B singleton (1779-1781) and config-chain else (1796) force false.
  CLAUDE_FIX: Force provider_block['allow_fallbacks']=False whenever a non-empty order is pinned (the safe coupling the I-provider-001 comment at 1735-1736 asks the operator to do manually), and when PG_OPENROUTER_PROVIDER_ROUTING=0 fail loud or fall back to the config chain rather than auto-routing with fallback
  WHY: The YAML's stated 'off-list flaky providers NEVER tried' guarantee is silently lost the moment an operator sets OPENROUTER_PROVIDER_ORDER without OPENROUTER_ALLOW_FALLBACKS=false, or disables routing via PG_OPENROUTER_PROVIDER_ROUTING=0. OpenRouter then drifts off the pinned healthy providers to any provider — re-introducing the slow/empty/low-cap providers (Mirror-blank, DeepInfra-404) the chain 

- [P2] scripts/deploy.sh:664-665
  WHAT: The deployed .env template hard-codes a fail-open + over-budget default: OPENROUTER_PROVIDER_ORDER=Chutes,DeepInfra,Fireworks with OPENROUTER_ALLOW_FALLBACKS=true.
  CURRENT: OPENROUTER_PROVIDER_ORDER=Chutes,DeepInfra,Fireworks ; OPENROUTER_ALLOW_FALLBACKS=true
  CLAUDE_FIX: Set OPENROUTER_ALLOW_FALLBACKS=false and either drop OPENROUTER_PROVIDER_ORDER (use the committed health-ranked config chain) or set it to the lowercase fp8 full-cap slugs matching the generator chain. Remove DeepInfra from any deepseek-v4-pro generator default.
  WHY: Three compounding problems: (1) allow_fallbacks=true lets OpenRouter drift off these three to any provider (fail-open). (2) DeepInfra is the fp4/16384 provider the generator chain explicitly excludes (YAML:21-22) — pinning it for deepseek-v4-pro at 384000 budget 404s. (3) Names are TitleCase while routing slugs and the case-insensitive resolver (pathB_run_gate.py:463) expect lowercase; provider_al

- [P3] config/settings/openrouter_provider_routing.yaml:42-46 (sentinel chain)
  WHAT: Sovereignty/serving-path note: the sentinel (minimax/minimax-m2) chain leads with `google-vertex` (order: [google-vertex, novita, atlas-cloud, minimax]). The I-arch-003 model-lock pass certified the sentinel MODEL as non-US-vendor but did not scrutinize that its top-ranked SERVING provider is Google Vertex (a US vendor); the faithfulness Sentinel verdict would compute on US infra when google-vertex wins routing.
  CURRENT: sentinel order: [google-vertex, novita, atlas-cloud, minimax], ignore: []
  CLAUDE_FIX: Leave as-is for benchmark. Before the sovereign self-host cutover, demote google-vertex below the non-US providers or move it to `ignore`, and add a gate assertion that no google-vertex/closed-US provider leads any role chain when a self-host serving_route is active. The empty `ignore: []` itself is
  WHY: Does NOT choke the current benchmark run — the whole benchmark verifier path is already on the US OpenRouter router, which roles/openrouter_role_transport.py's docstring (39-47) declares acceptable for DEV/BENCHMARK ONLY, so google-vertex is internally consistent now. It becomes a sovereignty violation only if this YAML chain feeds the sovereign demo path. Flagging once so the demote is on record 


### dimension: models
Claude SUMMARY: RUNTIME BINDINGS ARE CLEAN — this is the honest headline. On the live DR-benchmark run path (run_honest_sweep_r3.py + dr_benchmark/run_gate_b.py + roles/* + llm/openrouter_client.py + the side judges), every model resolves to the operator-signed lock: generator deepseek/deepseek-v4-pro (openrouter_client.py:547, OPENROUTER_DEFAULT_MODEL .env:12), mirror z-ai/glm-5.1 (openrouter_client.py:579), sentinel minimax/minimax-m2 (:580), judge qwen/qwen3.6-35b-a3b (:581). All 4 distinct families, asserted at preflight by run_gate_b.assert_four_role_families_distinct. The 3 "side judges" the I-arch-003 governance rule flagged (entailment / semantic_conflict / credibility) were the historical gemma-drift culprits (#1249/#1251/#1252) and are ALL now fixed to default z-ai/glm-5.1 (the mirror, per lock legacy_compat): entailment_judge.py:80, semantic_conflict_detector.py:68, credibility_judge_caller.py:27, plus the run-path script defaults pathB_run_gate.py:282-283. config/settings/openrouter_provider_routing.yaml pins exactly the 4 lock slugs. CRITICALLY, unlike the timeout incident: the real C:\POLARIS\.env sets NO PG_*_MODEL role override and C:\POLARIS\.smoke_env.sh sets NO _MODEL= line — so no env file strangles or mis-pins a model the way .smoke_env.sh did the timeout. No gemma / openai/ / anthropic/ / google-gemini slug BINDS anywhere on the live inference path. GEMINI_MODEL/FIREWORKS_MODEL in .env have ZERO consumers in src/polaris_graph or the run-path scripts (legacy Gemini stack

- [P2] scripts/dr_benchmark/smoke.md:28 (also scripts/dr_benchmark/smoke.md:27)
  WHAT: The smoke-run instructions tell the operator to export PG_EVALUATOR_MODEL=google/gemma-4-31b-it. This is the SAME class of failure as the timeout incident: a smoke env file injecting a value that overrides a good code default. If a real run inherits this smoke env (as the timeout run inherited PG_SECTION_WALLCLOCK_SECONDS=600 from .smoke_env.sh), the Mirror/evaluator role binds to gemma — a model the operator-signed lock + I-arch-003 governance explicitly forbid (NO gemma on the live inference path).
  CURRENT: PG_EVALUATOR_MODEL=google/gemma-4-31b-it (documented smoke setting)
  CLAUDE_FIX: Update smoke.md to use the lock value PG_EVALUATOR_MODEL=z-ai/glm-5.1 (or omit it entirely so the GLM-5.1 code default applies). Smoke env files must never pin a non-lock model. The deeper fix is a preflight assertion that EVERY resolved role model equals the lock slug and HARD-FAILS on any gemma/op
  WHY: PG_EVALUATOR_MODEL maps to the Mirror role (lock legacy_compat). Pinning it to google/gemma-4-31b-it would (a) violate the sovereignty/lock model rule, and (b) re-introduce the exact stale non-reasoning gemma the side-judge fixes (#1249/#1251/#1252) removed — gemma is non-reasoning and produced the empty-content/coverage-collapse the lock governance was created to stop. The .smoke_env.sh timeout i

- [P2] .env.example:76 (replicated across all .claude/worktrees/*/.env.example:76)
  WHAT: The committed .env.example pins PG_EVALUATOR_MODEL=google/gemma-4-31b-it. A deploy that seeds its runtime .env by copying .env.example (a common bootstrap pattern, and the deploy-env memory notes runs are launched from per-run .env files) would bind the Mirror/evaluator role to gemma, overriding the now-correct GLM-5.1 code default.
  CURRENT: PG_EVALUATOR_MODEL=google/gemma-4-31b-it
  CLAUDE_FIX: Change .env.example:76 to PG_EVALUATOR_MODEL=z-ai/glm-5.1 (the lock mirror value) or comment it out so the code default wins. Same lock-equality preflight as above is the durable backstop.
  WHY: Same mechanism as the timeout incident: an env file value overriding a good code default. gemma is forbidden on the live inference path (lock + I-arch-003). The real C:\POLARIS\.env does NOT set this (verified — runtime is clean), but the example template would re-introduce the drift the side-judge fixes removed if used to seed a new deploy.

- [P3] src/polaris_graph/clinical_generator/strict_verify.py:37-39
  WHAT: Module docstring documents 'PG_ENTAILMENT_MODEL — entailment judge model (default: google/gemma-4-31b-it, the two-family evaluator)'. The actual binding default is now z-ai/glm-5.1 (entailment_judge.py:80, fixed by I-arch-002). The docstring is stale and contradicts the code.
  CURRENT: default: google/gemma-4-31b-it (docstring claim)
  CLAUDE_FIX: Update the docstring to 'default: z-ai/glm-5.1 (the sovereign two-family mirror evaluator, per the runtime lock; I-arch-002)'.
  WHY: Does NOT choke at runtime — strict_verify does not read PG_ENTAILMENT_MODEL itself; the actual default comes from entailment_judge.py (GLM-5.1). But a future operator reading this docstring could wrongly 'restore' gemma believing it is the intended default, re-introducing the forbidden model. Documentation drift on a clinical-safety gate is a §-1.1 hazard (misleading the next reader).

- [P3] src/polaris_graph/evaluator/external_evaluator.py:29
  WHAT: Docstring says 'Uses PG_EVALUATOR_MODEL (default google/gemma-4-31b-it) against PG_GENERATOR_MODEL'. The actual import (openrouter_client.py:586) resolves PG_EVALUATOR_MODEL = os.getenv(...) or PG_MIRROR_MODEL = z-ai/glm-5.1. Stale docstring; code is correct.
  CURRENT: default google/gemma-4-31b-it (docstring claim)
  CLAUDE_FIX: Update docstring to reflect PG_EVALUATOR_MODEL resolving to z-ai/glm-5.1 via the lock legacy_compat (PG_EVALUATOR_MODEL -> PG_MIRROR_MODEL).
  WHY: No runtime choke — code default is GLM-5.1. Misleads a future reader into thinking gemma is the evaluator default. Also: external_evaluator is the legacy Phase-5 evaluator and is not the primary Gate-B faithfulness gate (the 4-role seam is), so its blast radius is lower, but the stale gemma claim still violates lock-documentation consistency.

- [P3] src/polaris_graph/retrieval/nli_benchmark_annotator.py:109
  WHAT: Docstring for the LIVE NLI entailment path (I-cap-003 #1066, the path Gate-B actually routes NLI through) says the backend is 'a frontier OPEN-weight model (default google/gemma-4-31b-it)'. The backend it calls is entailment_judge, whose default is now z-ai/glm-5.1. Stale docstring on a live-path module.
  CURRENT: default google/gemma-4-31b-it (docstring claim)
  CLAUDE_FIX: Update docstring to 'default z-ai/glm-5.1 (the sovereign mirror, per the runtime lock)'.
  WHY: No runtime choke (calls entailment_judge -> GLM-5.1). But this is the docstring of the ACTIVE Gate-B NLI annotator, so the stale gemma claim is the most likely to mislead — a reader could believe the live NLI gate runs on gemma and 'fix' it back to the forbidden model.

- [P3] src/polaris_graph/llm/openrouter_client.py:689-690 (inside check_family_segregation RuntimeError message)
  WHAT: The family-segregation error message hard-codes the recommended evaluator pair as 'deepseek/deepseek-v4-pro (generator) + google/gemma-4-31b-it (evaluator) per loopback/audit/_open_source_models_2026.md'. It is only a guidance string, not a binding default, but it advertises the forbidden gemma model as the recommended evaluator.
  CURRENT: google/gemma-4-31b-it (recommended evaluator, in error text)
  CLAUDE_FIX: Change the recommended pair in the message to the lock values, e.g. 'deepseek/deepseek-v4-pro (generator) + z-ai/glm-5.1 (mirror/evaluator) per config/architecture/polaris_runtime_lock.yaml'.
  WHY: No runtime choke — purely an error-message string. But on a clinical-safety gate it actively recommends the lock-forbidden gemma to an operator who hits a family collision, nudging them to re-introduce the exact model the lock governance bans. Misleading guidance at the moment of a config error is a §-1.1 hazard.

- [P3] .env:419  (PG_NLI_MODEL=flan-t5-large) consumed by src/polaris_graph/agents/nli_verifier.py:34; FaithLens default at nli_verifier.py:64 / .env:1657
  WHAT: The real .env pins PG_NLI_MODEL=flan-t5-large, the old/weak encoder the operator explicitly REJECTED ('old and weak... perform very bad'). nli_verifier.py defaults flan-t5-large and offers ssz1111/FaithLens. NOT a lock role, NOT gemma, NOT closed-source — so out of THIS dimension's mismatch criteria — but flagged for completeness because it is a stale model string on a module reachable from the agent graph.
  CURRENT: PG_NLI_MODEL=flan-t5-large (and PG_FAITHLENS_MODEL=ssz1111/FaithLens)
  CLAUDE_FIX: No model-lock action required for the live path. Optional hygiene: remove the dead PG_NLI_MODEL=flan-t5-large from .env (or document it as the legacy-agent-only knob) so it cannot be mistaken for the benchmark NLI backend. Keep it as a real env var (it already is).
  WHY: Does not choke the Gate-B run: the LIVE benchmark NLI path is nli_benchmark_annotator -> entailment_judge (GLM-5.1), which I-cap-003 #1066 introduced specifically to REPLACE this flan-t5/minicheck encoder; and PG_NLI_ENABLED defaults '0'. So nli_verifier's flan-t5 default does not bind on the benchmark run path. It only matters if the legacy agentic NLI path is enabled, in which case it would run 


### dimension: schemas
Claude SUMMARY: The structured-output SCHEMAS themselves are well-hardened against model variance: every model in src/polaris_graph/schemas.py uses plain str/float fields with default=, enum-like values (verdict, decision, convergence_assessment, gap_severity, analytical_focus) are plain str NOT Literal/enum, and lenient @model_validator(mode='before') normalizers map alt-field-names and coerce types AFTER parsing. The 4-role judges, sentinel, mirror adapters, entailment_judge, semantic_conflict_detector and evidence_distiller all use loose response_format={'type':'json_object'} (the SAFE mode). The single real schema-side chokepoint is the strict json_schema path in OpenRouterClient.generate_structured (openrouter_client.py:3108-3121): it hardcodes strict:True and the pydantic model_json_schema() it emits is structurally incompatible with OpenAI-style provider strict mode (no additionalProperties:false because no schema sets model_config extra='forbid'; defaulted fields are NOT in required; nested $ref/$defs and anyOf-for-Optional). This is exactly the I-ready-018 404 disease ('No endpoints found' when strict json_schema collides with reasoning + provider.require_parameters). The current guard is a HARDCODED model allowlist (_REASONING_FIRST_MODELS at line 3110) that only protects deepseek-v4-pro/-flash and glm-5.x; any other locked-or-future slug run with reasoning OFF (an agent client pointed at qwen3.6 or minimax-m2, or any new model the operator configures) still attaches strict:True an

- [P1] src/polaris_graph/llm/openrouter_client.py:3118
  WHAT: strict:True is hardcoded inside the json_schema response_format block; only the on/off feature flag PG_STRICT_JSON_SCHEMA (default "1") is env-gated, never the strict boolean itself. There is no env var to keep json_schema mode while setting strict:false (the provider-friendly middle ground).
  CURRENT: "strict": True  (literal; feature gated by PG_STRICT_JSON_SCHEMA default "1")
  CLAUDE_FIX: Read strict from an env var: strict_flag = os.getenv('PG_STRICT_JSON_SCHEMA_STRICT','0')=='1' (default OFF/loose since the pydantic schemas are not strict-compatible), and emit "strict": strict_flag. Keep PG_STRICT_JSON_SCHEMA as the json_schema-vs-json_object switch so the live slate can use json_s
  WHY: Provider-side OpenAI-style strict mode demands a schema shape pydantic does NOT emit (see the schemas.py finding). When the provider enforces strict it rejects the call (400 'invalid schema for response_format' or, combined with reasoning+require_parameters, the I-ready-018 404 'No endpoints found'). Because the value is hardcoded, an operator cannot dial strict down to false per-model/per-provide

- [P1] src/polaris_graph/llm/openrouter_client.py:3110 (model set defined 768-782)
  WHAT: The guard that decides whether to attach strict json_schema is a HARDCODED model-membership allowlist (_effective_reasoning = reasoning_enabled or self.model in _REASONING_FIRST_MODELS). _REASONING_FIRST_MODELS is a frozenset literal of deepseek-v4-pro/-flash and glm-5.x only. Any other model run with reasoning OFF takes the strict path.
  CURRENT: _effective_reasoning = reasoning_enabled or (self.model in _REASONING_FIRST_MODELS); _REASONING_FIRST_MODELS = frozenset({glm-5/5.1/5-turbo/4.7, deepseek-v4-pro, deepseek-v4-flash})
  CLAUDE_FIX: Replace the hardcoded membership test with an env-configurable reasoning-first list (PG_REASONING_FIRST_MODELS, comma-separated, defaulting to the current frozenset) AND make the strict-attach decision robust to model identity, or simply default strict OFF (per the :3118 fix) so model identity stops
  WHY: The locked JUDGE (qwen/qwen3.6-35b-a3b) and SENTINEL (minimax/minimax-m2) are NOT in this set. They reach 4-role gates via the role transport (loose json_object, safe) today, but ANY generate_structured() call on a client whose .model is qwen/minimax/a-new-slug with reasoning OFF attaches strict:True and hits the I-ready-018 404/400. The operator directive requires every model be env-configurable,

- [P1] src/polaris_graph/schemas.py (every BaseModel; grep for model_config/extra returns zero hits)
  WHAT: No schema sets model_config = ConfigDict(extra='forbid'), so pydantic v2 model_json_schema() emits objects WITHOUT additionalProperties:false, and fields with default=/default_factory are NOT placed in the JSON-schema 'required' array. Nested models (SourceAnalysisBatch->SourceAnalysis->AtomicFact, ReportOutline->SectionOutlineItem) emit $ref/$defs and Optional[str] fields (analytical_focus:1016, year:287) emit anyOf.
  CURRENT: plain pydantic v2 defaults: no additionalProperties:false, optional/defaulted fields absent from required, nested $defs/$ref, anyOf for Optional
  CLAUDE_FIX: Do NOT bolt extra='forbid' onto these models (the normalizers deliberately accept extra/alt keys for robustness). Instead stop requesting provider strict mode: default strict:false (the :3118 fix) so the loose json_schema/json_object path is used and the pydantic-side @model_validator normalizers + 
  WHY: OpenAI-style provider strict json_schema mode (what strict:True at :3118 requests) MANDATES additionalProperties:false on every object and ALL properties in required, and several providers reject $ref/anyOf under strict. The pydantic-emitted schema satisfies none of these, so when the strict path fires the provider returns 400 ('schema invalid for strict mode') or routes to no endpoint (404). This

- [P2] src/polaris_graph/llm/openrouter_client.py:3354-3363
  WHAT: The structured-parse retry re-sends the IDENTICAL response_format (the same strict json_schema) on the retry _call(). If the first failure was a strict-schema provider rejection (404/400), the retry repeats the same wire shape and fails the same way, burning a second full reasoning-token round before any recovery.
  CURRENT: messages[-1] = retry_prompt; result = await self._call(..., response_format=response_format, ...)  # same strict response_format reused
  CLAUDE_FIX: On the validation/JSON-decode retry, set response_format=None (or {'type':'json_object'}) for the retry _call so a strict-induced provider rejection cannot recur; rely on json_hint + _extract_json_from_text + _repair_truncated_json recovery already present. Optionally gate the downgrade behind PG_ST
  WHY: A strict-schema 400/404 is deterministic, not transient: retrying with the same response_format cannot succeed. On the locked reasoning-first generator a retry can cost minutes of reasoning tokens (the operator's exact pain point: a 3-hour run dying late). The retry should DROP strict (downgrade to json_object or None) so the second attempt can actually parse via the prompt-based path.

- [P3] src/polaris_graph/schemas.py:705-707 (ThemeResult.helpfulness)
  WHAT: helpfulness is the ONLY field in the whole schema module carrying hard numeric constraints (ge=0, le=100). Under provider strict json_schema these become minimum/maximum keywords some providers reject under strict, and on the pydantic side a model returning 0-1 or 0-1000 scaled scores fails validation and that theme is dropped.
  CURRENT: helpfulness: int = Field(default=50, ge=0, le=100)
  CLAUDE_FIX: Drop ge/le and add a coerce-and-clamp @field_validator(mode='before') mirroring AtomicFact.clamp_scores (parse str/float, scale, clamp into 0-100) so out-of-range or mis-scaled values are corrected, not dropped. This also removes the lone hard-bound that aggravates provider strict mode.
  WHY: BatchClusterResult/ThemeResult is on the live map-reduce clustering path (synthesizer.py:4820). If a model emits helpfulness as 0.7, 95.0-as-fraction, or 250, the ge/le bound raises ValidationError and the theme is dropped by the batch filter, thinning clusters. Under strict provider mode the min/max keywords can also contribute to schema-invalid rejections. Inconsistent with every other score fie

- [P3] src/polaris_graph/llm/openrouter_client.py:3060 (function default; call sites e.g. agents/analyzer.py:2063 override to 16384)
  WHAT: generate_structured default max_tokens=8192 is a hardcoded function-default; not every caller overrides it with an env-driven value. A schema-heavy batch (SourceAnalysisBatch with up to 15 facts x N sources, ReportOutline with many sections) can exceed 8192 output tokens, truncating the JSON.
  CURRENT: max_tokens: int = 8192 (function default literal)
  CLAUDE_FIX: Default max_tokens from an env var: max_tokens: int = int(os.getenv('PG_STRUCTURED_MAX_TOKENS','16384')) (raise the default to a generous, usage-billed cap per the MAX-tokens directive) so structured batches are not truncated, while individual callers may still pass tighter per-call budgets.
  WHY: Same family as the token-starvation disease (I-arch-003): an 8192 cap truncates a large structured batch, dropping facts/sections after JSON-repair salvage, which thins evidence/breadth. It is a hardcoded magic number rather than an env-governed budget, so an operator cannot raise the structured-output ceiling globally without editing code.
