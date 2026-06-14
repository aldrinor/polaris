# Codex INDEPENDENT chokepoint investigation — g1_timeouts_errorroot

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

## YOUR JOB — independently re-investigate YOUR dimensions (timeouts, error_root_cause_and_unknowns) line-by-line in the LIVE code, then for
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


### dimension: timeouts
Claude SUMMARY: The run died because a SMOKE-slate env override PG_SECTION_WALLCLOCK_SECONDS=600 wrapped each whole report section in asyncio.wait_for at 600s, while a single reasoning-first generator call alone is allotted 1800s and can legitimately need ~2979s (32768-token floor / 11 tok/s slow band). 600 is structurally below even one inner generator call, so it was GUARANTEED to kill real work — it only LOOKED survivable in smoke because the smoke section ran on the 103 tok/s fast band (~318s). The code default is 0=unlimited, so the smoke file is the sole cause of THIS death. Beyond the killer, the same disease appears everywhere: an outer asyncio.wait_for wrap tighter than the inner per-call timeout it contains. (1) GENERATOR_TIMEOUT_SECONDS=1800 is itself now stale — its comment derives 1800 from a 16384-token ceiling, but PG_REASONING_FIRST_MIN_MAX_TOKENS is now 32768 (double), so by the operator's own 1.5x formula the writer's own per-attempt budget should be ~4500s or unlimited. (2) PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS=300 wraps a reasoning-first generator (deepseek-v4-pro=PG_GENERATOR_MODEL) analysis call whose inner timeout is 1800 — outer 300<inner 1800, silently truncates agentic search when PG_AGENTIC_SEARCH_IN_BENCHMARK is on. (3) PG_VERIFY_PER_CALL_TIMEOUT=300 wraps verifier-role calls whose httpx bound is PG_VERIFIER_LLM_TIMEOUT_SECONDS=900 — outer 300<inner 900. (4) semantic_conflict_detector._JUDGE_TIMEOUT_S=30.0 is HARDCODED (LAW VI) and out of sync with its own 2026-06-1

- [P0] .smoke_env.sh (smoke slate, operator-cited) overriding multi_section_generator.py:66-96 (_section_wallclock_seconds / _run_section_with_wallclock)
  WHAT: Per-section wall-clock guard: each whole report section (generate + strict_verify + one regen) is wrapped in asyncio.wait_for(timeout=PG_SECTION_WALLCLOCK_SECONDS); on TimeoutError it retries once then raises TimeoutError -> the run aborts with status=error_unexpected. THE FINDING THAT KILLED THE RUN.
  CURRENT: Smoke slate: PG_SECTION_WALLCLOCK_SECONDS=600. Code default (multi_section_generator.py:68): os.getenv('PG_SECTION_WALLCLOCK_SECONDS','0') => 0 = unlimited (no wait_for wrap). .env does NOT set it. So 600 came purely from the smoke env file.
  CLAUDE_FIX: Do NOT run the validation/production sweep with the smoke slate. Set PG_SECTION_WALLCLOCK_SECONDS to a CALCULATED generous floor, not unlimited (the guard legitimately catches a real 0-socket provider wedge per the code comment). A section = generate + verify + 1 regen, so wall-clock >= GENERATOR_TI
  WHY: 600s is BELOW even a single inner generator call's own budget (GENERATOR_TIMEOUT_SECONDS=1800). A real reasoning-first section emits ~8-30k output tokens; at the code-cited ~11 tok/s slow band the 32768-token reasoning-first floor alone is ~2979s. It only survived smoke because that section ran on the ~103 tok/s fast band (32768/103 ~= 318s < 600). On a real slow-band section it is STRUCTURALLY GU

- [P1] src/polaris_graph/llm/openrouter_client.py:801 (GENERATOR_TIMEOUT_SECONDS) used at :1809-1814
  WHAT: Per-attempt timeout the reasoning-first GENERATOR (deepseek-v4-pro, in _REASONING_FIRST_MODELS at :778-782) inherits when the caller passes no explicit timeout (the multi_section generator's client.generate calls pass none, so they use this).
  CURRENT: GENERATOR_TIMEOUT_SECONDS = int(os.getenv('PG_GENERATOR_LLM_TIMEOUT_SECONDS','1800')) = 1800s. .env does NOT override it -> 1800 is live.
  CLAUDE_FIX: Recalculate from the CURRENT min/max token floor, not the stale 16384 comment: timeout = 1.5 x (PG_REASONING_FIRST_MIN_MAX_TOKENS / slow_rate) = 1.5 x (32768/11) ~= 4500s; recommend PG_GENERATOR_LLM_TIMEOUT_SECONDS=4500 (or 0/unlimited with the $ cap PG_MAX_COST_PER_RUN as the real backstop, per the
  WHY: The 1800 value + its justifying comment (:795-800) derive from a 16384-token reasoning-first ceiling (16384/11 ~ 24min, capped at 1800). PG_REASONING_FIRST_MIN_MAX_TOKENS is now 32768 (openrouter_client.py:1678) — DOUBLE the ceiling the comment assumes. By the operator's own formula 1.5 x (32768 / 11 tok/s) ~= 4468s, and the hard cap PG_REASONING_FIRST_HARD_CAP is 384000 tokens. So 1800s is now to

- [P1] src/polaris_graph/agents/searcher.py:1672 and :2061 (PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS, defined src/polaris_graph/state.py:250)
  WHAT: asyncio.wait_for wrap around _agentic_round_analysis, which calls generate_structured on the agentic client built with model=PG_GENERATOR_MODEL (= deepseek-v4-pro, the reasoning-first generator) — confirmed at scripts/run_honest_sweep_r3.py:3933 (_AG_MODEL = PG_GENERATOR_MODEL). On the DR run path when PG_AGENTIC_SEARCH_IN_BENCHMARK=1.
  CURRENT: PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv(...,'300')) = 300s (state.py:250). .env:252 also sets it to 300.
  CLAUDE_FIX: Raise to be consistent with the generator's per-call budget: PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS >= GENERATOR_TIMEOUT_SECONDS (i.e. >= 1800, ideally the recalculated ~4500). At minimum it must never be below the inner timeout of the model it wraps. If the analysis call is deliberately capped to a sm
  WHY: Outer-tighter-than-inner: this 300s wrap bounds a reasoning-first deepseek-v4-pro call whose own per-call timeout is GENERATOR_TIMEOUT_SECONDS=1800. If the analysis call reasons longer than 300s (high-effort reasoning on a large round context is plausible), the outer wait_for fires first and the searcher logs 'agentic analysis timed out ... stopping search loop' then breaks (:1674-1680) — silently

- [P1] src/polaris_graph/retrieval/semantic_conflict_detector.py:69 (_JUDGE_TIMEOUT_S) used at :349 (httpx.Client(timeout=_JUDGE_TIMEOUT_S)) for the POST at :417
  WHAT: httpx client timeout for the NLI semantic-conflict judge POST. The judge model is GLM-5.1 (z-ai/glm-5.1, the locked mirror/evaluator) and the call was just re-tuned (:361-378) to run reasoning effort=high with max_tokens up to 2000 and response_format json_object.
  CURRENT: _JUDGE_TIMEOUT_S = 30.0 — HARDCODED literal, no os.getenv. (The conflict judge is gated behind PG_SWEEP_NLI_CONFLICT, so active only when that flag is on for the run.)
  CLAUDE_FIX: Make it an env var and raise it to match the credibility judge: read PG_SEMANTIC_CONFLICT_JUDGE_TIMEOUT_S with default 120.0 (and add a connect=15.0 like credibility_judge_caller:153). At minimum 120s so high-effort GLM reasoning completes; the fail-open path must not be reached on legitimate slow r
  WHY: LAW VI hardcode + starvation chokepoint, and out of sync with its OWN recent fix: the same module (:361-372) was patched 2026-06-13 to let GLM-5.1 do high-effort reasoning so it stops returning empty content, but a high-effort reasoning completion at 2000 max_tokens can easily exceed a 30s httpx wall under provider load. On timeout the judge fails OPEN to ('neutral',0.0) -> a real contradiction is

- [P2] src/polaris_graph/agents/verifier.py:398 and :1060 (PG_VERIFY_PER_CALL_TIMEOUT)
  WHAT: Per-call timeout used to estimate/wrap individual verifier-role LLM calls in the verification gather (base gather bound = PG_VERIFY_GATHER_TIMEOUT=1800, state.py:98).
  CURRENT: int(os.getenv('PG_VERIFY_PER_CALL_TIMEOUT','300')) = 300s. .env:106 sets PG_VERIFY_PER_CALL_TIMEOUT=300.
  CLAUDE_FIX: Raise PG_VERIFY_PER_CALL_TIMEOUT to be >= the verifier transport per-POST timeout (>= 900) so the verify-layer wrap never pre-empts the transport's own budget; recommend PG_VERIFY_PER_CALL_TIMEOUT=900 to match PG_VERIFIER_LLM_TIMEOUT_SECONDS, and keep PG_VERIFY_GATHER_TIMEOUT=1800+ as the aggregate.
  WHY: Outer-tighter-than-inner pattern: a verifier role (mirror/sentinel/judge on OpenRouter) has an inner httpx POST bound of PG_VERIFIER_LLM_TIMEOUT_SECONDS=900 (openrouter_role_transport.py:407) plus a PG_ROLE_CALL_TIMEOUT_S=3600 watchdog. A 300s per-call estimate/bound is below the 900s the transport itself allows, so a legitimately slow reasoning verifier call can be cut off by the verify layer bef

- [P2] src/polaris_graph/roles/openai_compatible_transport.py:56 (_TIMEOUT_SECONDS) used at :489
  WHAT: httpx POST timeout for the SELF-HOSTED mirror/sentinel/judge transport (OpenAICompatibleRoleTransport). Activates only when PG_<role>_BASE_URL points at a self-hosted vLLM; the default locked arch runs these 3 roles on OpenRouter via openrouter_role_transport.py instead.
  CURRENT: _TIMEOUT_SECONDS = int(os.getenv('PG_LLM_TIMEOUT_SECONDS','90')) = 90 default. The smoke slate sets PG_LLM_TIMEOUT_SECONDS=300; .env sets it to 600.
  CLAUDE_FIX: Give the self-host transport its own verifier-scoped knob mirroring the OpenRouter path: read PG_VERIFIER_LLM_TIMEOUT_SECONDS (default 900) here instead of the generic PG_LLM_TIMEOUT_SECONDS=90, so the two transports are consistent. Keep PG_LLM_TIMEOUT_SECONDS for non-verifier generic calls only.
  WHY: This transport reuses the GENERIC PG_LLM_TIMEOUT_SECONDS knob (shared with embeddings/retrieval) as the bound for a reasoning verifier completion. At the bare default 90s a high-effort reasoning verdict (GLM/MiniMax/Qwen) is truncated/timed out -> RoleTransportError / fail-closed. It is wired to the wrong knob (a verifier reasoning call should use a verifier-scoped timeout like the OpenRouter sibl

- [P3] src/polaris_graph/retrieval/llm_throttle.py:42 (LLM_CALL_TIMEOUT) used at :88-91; consumers: src/polaris_graph/synthesis/verifier_v2.py, src/polaris_graph/synthesis/synthesizer_v2.py
  WHAT: throttled_llm_call wraps fn in asyncio.wait_for(timeout=LLM_CALL_TIMEOUT). Verified the multi_section_generator does NOT route through this (no throttled_llm_call import in generator/*.py), so the DR writer is NOT strangled by it. Consumers are the pipeline-B synthesis modules.
  CURRENT: LLM_CALL_TIMEOUT = int(os.getenv('PG_LLM_CALL_TIMEOUT','300')) = 300s. Not set in .env (default 300 live).
  CLAUDE_FIX: Keep 300s for the lightweight throttled calls it actually wraps, but if any reasoning-first generate is ever routed through throttled_llm_call, pass an explicit per-call timeout >= GENERATOR_TIMEOUT_SECONDS or branch on _REASONING_FIRST_MODELS as openrouter_client does. Document that the generator m
  WHY: If a reasoning-first generator call were ever routed through this throttle, the 300s outer wrap would kill it well under GENERATOR_TIMEOUT_SECONDS=1800. Currently latent for the DR run because verifier_v2/synthesizer_v2 are LangGraph pipeline-B modules NOT imported by scripts/run_honest_sweep_r3.py. Flagged so a future wiring of the generator behind the throttle does not silently reintroduce the o

- [P3] src/polaris_graph/agents/synthesizer.py:2660 & :2886, src/polaris_graph/synthesis/section_writer.py:2191 (PG_SECTION_WRITE_TIMEOUT)
  WHAT: Per-section write/revise/remediate timeout in the LangGraph pipeline-B synthesis path (NOT the multi_section_generator DR path). Named almost identically to the killer wall-clock, so explicitly disambiguated.
  CURRENT: int(os.getenv('PG_SECTION_WRITE_TIMEOUT','300')) = 300s. .env:111 sets PG_SECTION_WRITE_TIMEOUT=300.
  CLAUDE_FIX: For pipeline B: raise PG_SECTION_WRITE_TIMEOUT to >= the generator per-call budget (>= 1800, ideally the recalculated ~4500) so a real reasoning-first section write is not strangled, OR derive it from the section max_tokens via 1.5 x max_tokens/rate. Not blocking for the DR run.
  WHY: 300s is below the reasoning-first generator's 1800s budget, so a slow section write in pipeline B would be cut off. It is LATENT for the DR validation run because run_honest_sweep_r3.py imports multi_section_generator, not agents/synthesizer or synthesis/section_writer (confirmed: no import of those in the sweep). It bites the pipeline-B UI run, not the run that just died.

- [P3] src/polaris_graph/tools/react_agent.py:7914 (timeout=60) and :7916 (wait_for timeout=75); also :48 default '240' vs :3559/:8162 default '180' for PG_REACT_INTERPRET_TIMEOUT
  WHAT: Hardcoded per-call literals on the react/8-phase analysis decision call (generate_structured max_tokens=512, timeout=60, outer wait_for=75). Plus an inconsistent default for the SAME env var PG_REACT_INTERPRET_TIMEOUT (240 at module load, 180 at the two read sites).
  CURRENT: 60 and 75 are bare literals (no env). PG_REACT_INTERPRET_TIMEOUT default is '240' at :48 but '180' at :3559 and :8162 — three reads, two different defaults.
  CLAUDE_FIX: Replace the 60/75 literals with PG_REACT_DECISION_TIMEOUT (default 90, outer +15) read at call time. Unify the PG_REACT_INTERPRET_TIMEOUT default to a single value (pick 240) across :48/:3559/:8162. These bound reasoning-first calls, so size them via the model's max_tokens, not a bare literal.
  WHY: LAW VI: 60/75 are hardcoded timeouts, not env-driven. The decision call is small (512 tokens) so 60s is usually adequate, but it is NOT overridable, and if PG_GENERATOR_MODEL (reasoning-first) backs this client the reasoning preamble can blow past 60s. The split default (240 vs 180) for one env var means the effective interpret timeout depends on which code path reads it — a silent inconsistency.

- [P3] src/polaris_graph/retrieval/live_retriever.py:1882 (timeout=10.0), :1950 (timeout=15.0); contrast domain_backends.py:48 (HTTP_TIMEOUT IS env via PG_DOMAIN_HTTP_TIMEOUT)
  WHAT: Hardcoded httpx fetch/metadata timeouts. :1882 = Unpaywall DOI resolve (10.0); :1950 = another metadata GET (15.0). The rest of live_retriever is env-driven (DEFAULT_HTTP_TIMEOUT via PG_LIVE_HTTP_TIMEOUT; per_task fetch via PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS), so these two literals are the outliers.
  CURRENT: :1882 timeout=10.0 (HARDCODED literal); :1950 timeout=15.0 (HARDCODED literal). (The per_task_timeout 120.0 fallback at :3151 is NOT a violation — it is the parse-error fallback for the env-driven PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS.)
  CLAUDE_FIX: Route both through env vars consistent with the rest of live_retriever: PG_UNPAYWALL_TIMEOUT_SECONDS (default 15) at :1882 and PG_OA_METADATA_TIMEOUT_SECONDS (default 20) at :1950 — or simply reuse DEFAULT_HTTP_TIMEOUT (PG_LIVE_HTTP_TIMEOUT). Zero hard-coded fetch timeouts per LAW VI.
  WHY: LAW VI: two retrieval fetch timeouts are bare literals while the rest of the module is env-driven. Not a reasoning chokepoint (lightweight metadata GETs), but 10s/15s can prematurely drop a slow-but-valid Unpaywall/OA resolver under load, silently shrinking the corpus. Lower severity because they are external-fetch, not generator timeouts, and fail soft (return []).


### dimension: error_root_cause_and_unknowns
Claude SUMMARY: root cause plus critic findings below

- [P0] multi_section_generator.py:5550, 5509, also 6432; except run_honest_sweep_r3.py:8484
  WHAT: ROOT CAUSE: the two main gathers (plus M-50 gather 6432) omit return_exceptions=True; one section TimeoutError (line 93) aborts the whole run via the 8484 except as error_unexpected. No generation checkpoint exists.
  CURRENT: asyncio.gather, no return_exceptions; generation not persisted
  CLAUDE_FIX: return_exceptions=True on the 3 gathers; map exceptions to gap-stub SectionResults (321-347), not raw (dedup 5583-5584 AttributeErrors). Persist each SectionResult for resume.
  WHY: One slow or wedged section nukes ~3h with no per-section isolation or checkpoint.

- [P0] run_gate_b.py slate 426-716, floors 720-735; knob 66-70
  WHAT: PG_SECTION_WALLCLOCK_SECONDS and PG_GENERATOR_LLM_TIMEOUT_SECONDS absent from the slate/preflight, so smoke 600 passes unvalidated. Retry-multiplication puts any sub-1800s cap below one attempt.
  CURRENT: not slated; 600; default 0=unlimited; per-attempt 1800
  CLAUDE_FIX: Slate as 0 or a calculated ceiling; do NOT max-floor (0=unlimited becomes a strangler). Enforce at least 1.5x generator-timeout x attempts.
  WHY: 600s strangles reasoning-first sections (~1440s slow band). Same disease as I-arch-003.
