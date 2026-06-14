# Codex INDEPENDENT chokepoint investigation — g5_checkpoints_hardcodes

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

## YOUR JOB — independently re-investigate YOUR dimensions (checkpoints, hardcoded_params) line-by-line in the LIVE code, then for
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


### dimension: checkpoints
Claude SUMMARY: The live DR run path (run_honest_sweep_r3.run_one_query) is STRICTLY FORWARD-ONLY with ZERO stage-level resume. The pipeline stages execute in one monolithic try-block — scope -> retrieval (run_live_retrieval, in-memory LiveRetrievalResult) -> corpus adequacy/approval -> composition (generate_multi_section_report, all sections via asyncio.gather) -> per-sentence strict_verify/NLI -> 4-role D8 seam -> manifest. EVERY durable artifact (report.md L6834, evidence_pool.json L7059, verification_details.json L7025, bibliography.json L6835, manifest.json) is written ONLY AT THE END, after composition succeeds. There is no per-stage persisted snapshot and no resume read on re-run. So the exact failure observed (a section wallclock TimeoutError raised inside the composition gather, multi_section_generator.py:93) propagates to the bare `except Exception` at run_honest_sweep_r3.py:8484, writes a content-free error_unexpected manifest, and DISCARDS everything — the ~3h of retrieval + any completed sections + all verification. Nothing on disk can be reloaded; a re-run re-fetches every URL and re-generates every section from zero. The only on-disk reuse layers are sub-stage accelerators (authority_enrich.sqlite per-source enrich cache in live_retriever; the best-effort retrieval_cache.sqlite cache-warming layer, only warmed for q.canonical_urls and never consulted as a corpus checkpoint) — neither is a stage checkpoint. The sweep loop itself (L8826-8851) calls run_one_query unconditionally 

- [P0] scripts/run_honest_sweep_r3.py:8826-8851 (sweep loop in main_async) + 8484-8533 (bare except Exception handler)
  WHAT: Per-query forward-only execution with no resume: the sweep loop calls `summary = await run_one_query(q, out_root)` unconditionally for every query, and any uncaught exception inside run_one_query (incl. the composition TimeoutError that killed this run) lands in the bare `except Exception` at 8484 which writes a content-free error_unexpected manifest and returns — discarding ~3h of retrieval + any completed sections + all verification. On a re-run to the same --out-root the whole pipeline re-executes from scratch; there is NO check for an existing terminal manifest.json and NO stage snapshot to reload.
  CURRENT: run_one_query is called unconditionally (L8837); the except-handler (L8484) writes only {run_id, slug, domain, question, status:error_unexpected, error, cost_usd, budget_cap_usd} — none of the in-memory retrieval/corpus/section state is persisted; no `--resume`, no skip-if-complete, no checkpoint.js
  CLAUDE_FIX: Introduce a run_dir/checkpoint/ directory and a run_dir/checkpoint.json stage-pointer ({stage, completed:[...], sha-of-inputs}). After EACH stage boundary, write that stage's durable snapshot (see other findings). Add a `--resume` CLI flag (and PG_RESUME_FROM_CHECKPOINT env) that, on entry to run_on
  WHY: A late-stage composition failure (the observed wallclock x2 TimeoutError) throws away every prior stage. Because retrieval (the single most expensive + slowest stage) is purely in-memory until report assembly, the entire multi-hour run is unrecoverable and must restart from URL fetch zero. This is the literal cause of the 3-hour loss the operator is furious about.

- [P0] scripts/run_honest_sweep_r3.py:3466-3479 (retrieval = run_live_retrieval(...)) and the absence of any retrieval-result write before composition
  WHAT: The retrieval corpus — the most expensive and slowest stage (this run spent the bulk of 3h here) — is held ONLY as an in-memory LiveRetrievalResult object. It is never serialized to a reloadable artifact at the retrieval boundary. evidence_pool.json (L7059) is the only on-disk representation of the corpus and it is written AFTER generate_multi_section_report returns — so a composition failure means the corpus was never persisted at all.
  CURRENT: run_live_retrieval(...) returns into the local `retrieval` var (L3466); no `(run_dir/'corpus_snapshot.json').write_text(...)` follows. evidence_pool.json is written at L7059, strictly downstream of the L6093 composition call.
  CLAUDE_FIX: Immediately after run_live_retrieval returns (and after the corpus adequacy/approval gates pass), serialize the full selected corpus (selected_rows + per-source spans + tier/authority weights + retrieval counts) to run_dir/checkpoint/corpus_snapshot.json and stamp checkpoint.json stage='retrieval_do
  WHY: Re-running after a composition/verification failure re-fetches every URL (Serper/S2/OpenAlex/Zyte/crawl4ai), re-classifies tiers, and re-enriches authority — the multi-hour, real-money part — even though that work was already 100% done and valid. There is nothing to resume from.

- [P0] src/polaris_graph/generator/multi_section_generator.py:5509-5511 and 5550-5552 (asyncio.gather over _run_section_with_wallclock) + 73-96 (the wallclock guard that raised)
  WHAT: Composition runs all sections concurrently in a single asyncio.gather. There is NO per-section persistence: completed section results live only in the returned list (section_results, ~L5558). When one section's wallclock guard raises TimeoutError (L93), the gather fails, all sibling in-flight sections are cancelled, and EVERY already-completed section in that batch is lost — the whole report restarts.
  CURRENT: contract_results = await asyncio.gather(*[_run_section_with_wallclock(...) for p in contract_plans]) (L5509); legacy_results likewise (L5550). No section result is written to disk as it completes; a single section TimeoutError aborts generate_multi_section_report entirely.
  CLAUDE_FIX: Persist each SectionResult to run_dir/checkpoint/sections/<section_id>.json the moment it completes (inside _run_section_with_wallclock's success path, or via gather's return_exceptions=True so one section's failure does not cancel siblings). On --resume, reload completed sections from disk and only
  WHY: A reasoning-first section can legitimately take ~24 min (code comment) at the ~11 tok/s slow band; if section 5 of 6 wedges and trips the guard, sections 1-4 (which may already represent expensive successful generation + verification) are discarded with it. There is no way to resume composition with the surviving sections.

- [P1] scripts/run_honest_sweep_r3.py:7025-7065 (verification_details.json + evidence_pool.json written only after composition) and 7527-7583 (run_four_role_seam, the late D8 stage)
  WHAT: Per-sentence verification (strict_verify/NLI) and the 4-role D8 seam are late, expensive stages whose outputs (verification_details.json L7025, four_role_claim_audit.json) are written only on the success path, downstream of composition. A failure anywhere in verification or the D8 seam (e.g. the abort_verifier_degraded path at L7072, or a seam exception) discards the completed corpus AND the completed composition with no snapshot to resume from — verification re-runs require re-generation, which requires re-retrieval.
  CURRENT: verification_details.json written at L7025 and evidence_pool.json at L7059, both strictly after the L6093 generate_multi_section_report call; the 4-role seam runs at L7527+ even later. No verification checkpoint exists, so any post-composition failure restarts from stage zero.
  CLAUDE_FIX: After composition assembles the report, write run_dir/checkpoint/composed_report.json (report text + per-sentence provenance + ev_pool) and stamp checkpoint.json stage='composed'. On --resume past 'composed', reload it and re-enter at verification/D8 without re-generating. Persist verification_detai
  WHY: The D8 4-role seam is itself a long, multi-call LLM stage (mirror/sentinel/judge, MAX reasoning) prone to the same provider stalls as generation. A stall here loses retrieval+composition too, compounding the cost of an already-late failure.

- [P1] src/polaris_graph/retrieval/live_retriever.py:77-83, 871-957, 1061-1066 (authority_enrich.sqlite) + scripts/run_honest_sweep_r3.py:1862-1918, 8707-8729 (retrieval_cache.sqlite cache-warming)
  WHAT: The two on-disk reuse layers that DO exist are sub-stage accelerators, not stage checkpoints, and neither rescues a mid/late failure. authority_enrich.sqlite caches only per-source authority-enrich payloads (keyed doi:/url:), so a re-run still re-issues all Serper/S2 searches and re-fetches all page bodies. retrieval_cache.sqlite is a best-effort cache-warming layer warmed ONLY for queries that declare q.canonical_urls (most sweep queries do not) and is never consulted as a resumable corpus snapshot.
  CURRENT: AUTHORITY_CACHE_DB = cache/authority_enrich.sqlite (L80), get at L1066 — payload-only, not corpus. retrieval_cache.sqlite warmed via warm_cache(skip_existing=True) at L1902/8718, gated by PG_USE_CACHE_WARMING, keyed off canonical_urls only; the live run does not read it back to skip a full retrieval
  CLAUDE_FIX: Do not rely on these as checkpoints. Implement the dedicated corpus_snapshot.json (see retrieval finding) which captures the SELECTED corpus post-fetch/post-tier/post-selection, and make --resume load that. Optionally extend the cache layer to key on the actual fired search queries (not just canonic
  WHY: These caches give a false impression of resumability. After a composition failure they shave only the metadata-enrich and a handful of canonical fetches off a re-run — the search fan-out, the bulk page fetches, tier classification, selection, AND all of generation+verification still re-run in full. The operator's 3h is not recovered.

- [P2] scripts/run_honest_sweep_r3.py:2817-2820, 5909-5912, 7106-7110 (I-rdy-011 cooperative-cancel checkpoints) — the only thing named 'checkpoint' in the live path
  WHAT: The only constructs named 'checkpoint' in the live run path are I-rdy-011 cooperative-CANCEL probes (_abort_if_cancelled). They check for a user cancel signal at stage boundaries and write a 'cancelled' manifest — they persist NO stage state and provide NO resume. They are easy to mistake for resume checkpoints; they are the opposite (clean abort, not recoverable save).
  CURRENT: if _abort_if_cancelled(q, run_dir, run_id, summary, _log): return summary (L2819, 5910, 7107). These write manifest.status='cancelled' and discard all in-memory state; no snapshot is taken at these boundaries.
  CLAUDE_FIX: Reuse these EXACT three boundary points as the insertion sites for the real stage snapshots (corpus after the pre-retrieval probe completes the stage; composed-report at the post-generation probe). Co-locating the durable-snapshot write with each existing cooperative-cancel probe is the surgical, mi
  WHY: Their presence at exactly the right boundaries (pre-retrieval, post-deepener, post-generation) hides the absence of real resume checkpoints — a reviewer scanning for 'checkpoint' sees them and may conclude resume exists. It does not.

- [P2] src/polaris_graph/generator/multi_section_generator.py:5805-5846, 6011 (M-44 section-regeneration loop also under the same all-or-nothing gather)
  WHAT: The secondary regeneration loop (sections_needing_regen) re-runs sections through the same _run_section_with_wallclock + asyncio.gather pattern with no incremental persistence, so a wallclock trip during REGENERATION also discards the entire (already largely complete) report. This is a second instance of the same all-or-nothing composition hazard, on the more fragile retry path.
  CURRENT: regen_results = await asyncio.gather(... _run_section_with_wallclock(_bounded_run, plan) ...) (L5844-5846); single-section regen at L6011 also via _run_section_with_wallclock with no on-disk save of the already-good sections.
  CLAUDE_FIX: Apply the same per-section persistence (PG_CHECKPOINT_SECTIONS) to the regen loop: keep the first-pass section results on disk so a regen-stage failure falls back to the first-pass verified sections rather than discarding the whole report. Use return_exceptions=True here too so one regen failure doe
  WHY: Regeneration runs after the first full composition pass — i.e. even later, after even more sunk cost. A wedge here loses the most work of any failure point, and it is on the retry path that is by definition already handling a marginal section.


### dimension: hardcoded_params
Claude SUMMARY: Audited the DR-benchmark live run path (scripts/run_honest_sweep_r3.py -> multi_section_generator -> provenance_generator -> live_deepseek_generator -> roles/* 4-role verifier -> retrieval/live_retriever -> agents/{searcher,evidence_deepener} -> llm/openrouter_client) line-by-line for hardcoded params that the operator requires to be .env-driven. GOOD NEWS first: the params most central to the operator's two stated diseases are already correctly env-wrapped: every LLM model string (PG_GENERATOR_MODEL / PG_MIRROR_MODEL / PG_SENTINEL_MODEL / PG_JUDGE_MODEL, openrouter_client.py:547-581, defaults = the locked deepseek/glm/minimax/qwen, NO gemma/closed-source); the generator per-call timeout (PG_GENERATOR_LLM_TIMEOUT_SECONDS=1800, :801, correctly resolved for reasoning-first writers at :1809-1814 so a section is NOT killed at the cheap 90s); the per-section wall-clock guard (PG_SECTION_WALLCLOCK_SECONDS, multi_section_generator.py:66-68, default 0 = UNLIMITED -- the 600s that killed the run came from the SMOKE env file, not code); the 4-role verifier effort/tokens/timeouts (PG_FOUR_ROLE_REASONING_EFFORT=xhigh, PG_VERIFIER_REASONING_MAX_TOKENS, PG_VERIFIER_LLM_TIMEOUT_SECONDS=900, PG_ROLE_CALL_TIMEOUT_S=3600, roles/openrouter_role_transport.py); the reasoning-first floor/cap (PG_REASONING_FIRST_MIN_MAX_TOKENS=32768 / PG_REASONING_FIRST_HARD_CAP=384000); and the evidence_deepener (PG_DEEPENER_EXTRACT_MAX_TOKENS / PG_DEEPENER_MECHANISM_MAX_TOKENS=32768). REMAINING CHOKEPOINTS fall i

- [P1] scripts/run_honest_sweep_r3.py:3021-3023 (and the duplicate fallbacks at :3056 PG_SIMPLE_FETCH_CAP and :3065 PG_SWEEP_FETCH_CAP)
  WHAT: Retrieval-breadth budget for the live sweep: how many Serper results, Semantic-Scholar results, and URLs to FETCH per query. This is the master 'how many sources flow into the pipeline' knob.
  CURRENT: PG_SWEEP_MAX_SERPER default "12", PG_SWEEP_MAX_S2 default "12", PG_SWEEP_FETCH_CAP default "40" (PG_SIMPLE_FETCH_CAP also "40").
  CLAUDE_FIX: Raise the DEFAULTS to the operator-intended full-breadth values (~1000 fetch_cap; serper/s2 scaled to feed it), OR fail loud at startup if these resolve below a 'full-capability' floor unless an explicit PG_AUTHORIZED_DOWNGRADE token is set. The names already exist; only the throttled defaults must 
  WHY: These ARE os.getenv-wrapped, but the DEFAULTS are the throttled 12/12/40 the operator explicitly flagged on 2026-06-04 as the silent '~40 URLs vs intended ~1000' downgrade (feedback_no_downgrade_without_operator_approval). A run launched with no env override silently caps the corpus at 40 fetched URLs -> starves breadth and basket-corroboration before composition even begins. CLAUDE.md §-1.3 DNA =

- [P1] scripts/run_honest_sweep_r3.py:6107
  WHAT: outline_max_tokens passed to generate_multi_section_report() -- the token budget for the section-outline LLM call that decides the report's section structure.
  CURRENT: outline_max_tokens=2500  (a bare integer literal at the call site)
  CLAUDE_FIX: Wrap in os.environ.get: outline_max_tokens=int(os.environ.get('PG_OUTLINE_MAX_TOKENS', '2500')) (mirroring how section_max_tokens/limitations_max_tokens/max_parallel_sections are already wrapped two lines below).
  WHY: It is a HARDCODED literal at the call site that CLOBBERS the env-overridable module default. No PG_ env var can move it -- the same regression class the in-code comment at :6100-6113 itself documents ('script override clobbers module default'). If the outline JSON for a wide corpus (5-6 sections x 12-20 ev_ids) exceeds 2500 tokens it truncates mid-JSON and falls back to a 3-section deterministic o

- [P2] scripts/run_honest_sweep_r3.py:6099
  WHAT: section_temperature passed to generate_multi_section_report() -- sampling temperature for every section-prose generation call.
  CURRENT: section_temperature=0.3  (bare literal at the call site)
  CLAUDE_FIX: section_temperature=float(os.environ.get('PG_SECTION_TEMPERATURE', '0.3')); likewise expose PG_OUTLINE_TEMPERATURE for outline_temperature (module default 0.2, also not passed at the call site).
  WHY: Hardcoded literal at the call site; no env var can tune generation temperature for the live writer. The operator directive is that EVERY tunable (incl. temperature) be a PG_ env var ('hardcoding is super lethal'). Temperature directly affects faithfulness/recall trade-off of the writer, so it must be operator-tunable without a code edit.

- [P2] src/polaris_graph/generator/multi_section_generator.py:5098 (trial_summary_table_max_tokens) and :5110 (m50_subsection_max_tokens)
  WHAT: Token budgets for two real LLM-authored sub-sections on the active path: the Trial Summary table call (:3600) and the M-50 per-trial subsection calls (:6424). The sweep call site never passes either, so the module-default literals are what actually run.
  CURRENT: trial_summary_table_max_tokens: int = 800 ; m50_subsection_max_tokens: int = 400
  CLAUDE_FIX: Replace the literals with int(os.getenv('PG_TRIAL_SUMMARY_TABLE_MAX_TOKENS', '800')) and int(os.getenv('PG_M50_SUBSECTION_MAX_TOKENS', '400')); raise the defaults to a non-starving value for the reasoning-first writer (>= the PG_REASONING_FIRST_MIN_MAX_TOKENS floor or clearly document why a small cl
  WHY: Bare integer defaults with no PG_ env var, and run_honest_sweep_r3.py:6093-6214 never overrides them -> the live run uses 800 and 400. These feed client.generate() (reasoning OFF), so on the reasoning-first deepseek-v4-pro writer they are below the model's reasoning-token footprint on a content-heavy table -> finish_reason=length -> truncated/empty table or subsection silently dropped (same starva

- [P2] src/polaris_graph/generator/multi_section_generator.py:2793-2794
  WHAT: max_tokens and temperature for the sentence-repair LLM call (repair_dropped_section_sentences) that re-writes strict_verify-dropped sentences -- runs on every section on the live path.
  CURRENT: max_tokens=400, temperature=0.2 (both bare literals)
  CLAUDE_FIX: max_tokens=int(os.getenv('PG_SENTENCE_REPAIR_MAX_TOKENS', '400')), temperature=float(os.getenv('PG_SENTENCE_REPAIR_TEMPERATURE', '0.2')); reconsider the 400 default against the reasoning-first floor.
  WHY: Hardcoded, no PG_ knob. 400 total tokens on the reasoning-first generator is one of the most starved budgets on the path (the I-arch-003 forensic flagged the analogous deepener 500-token site as 'most starved' -> empty output). A starved repair call returns empty -> the dropped sentence is permanently lost -> avoidable recall loss with no operator visibility or tuning lever.

- [P2] src/polaris_graph/generator/multi_section_generator.py:5607-5608
  WHAT: max_tokens and temperature for the fact-dedup CONSOLIDATION rewrite LLM call (_dedup_llm_callable) -- the basket-consolidation step that merges same-claim sources (CLAUDE.md §-1.3 'CONSOLIDATE, DON'T DROP').
  CURRENT: max_tokens=2048, temperature=0.2 (both bare literals)
  CLAUDE_FIX: max_tokens=int(os.getenv('PG_FACT_DEDUP_MAX_TOKENS', '2048')), temperature=float(os.getenv('PG_FACT_DEDUP_TEMPERATURE', '0.2')); raise the default to clear the reasoning-first footprint.
  WHY: Hardcoded, no PG_ knob. 2048 on the reasoning-first writer can be eaten by reasoning tokens -> truncated/empty consolidation -> baskets fail to merge or merge wrong. This sits squarely on the consolidation DNA path, so a silent starve here degrades the architecture's core promise, untunable by the operator.

- [P2] src/polaris_graph/retrieval/live_retriever.py:102-104
  WHAT: Parallel-fetch worker-pool sizing: the floor, ceiling, and per-candidate divisor that bound how many concurrent fetch threads run (consumed at :3137-3143).
  CURRENT: _FETCH_WORKERS_FLOOR = 8 ; _FETCH_WORKERS_CEILING = 48 ; _FETCH_WORKERS_PER_CANDIDATE = 16
  CLAUDE_FIX: Wrap each: _FETCH_WORKERS_FLOOR=int(os.getenv('PG_FETCH_WORKERS_FLOOR','8')), _FETCH_WORKERS_CEILING=int(os.getenv('PG_FETCH_WORKERS_CEILING','48')), _FETCH_WORKERS_PER_CANDIDATE=int(os.getenv('PG_FETCH_WORKERS_PER_CANDIDATE','16')); raise the ceiling default to match the de-throttled fetch_cap.
  WHY: The in-code comment claims 'LAW VI -- no magic numbers', but only the explicit override PG_LIVE_RETRIEVER_MAX_WORKERS is env-wrapped; the FLOOR/CEILING/PER_CANDIDATE that drive the auto-scale formula are bare module constants. With the operator de-throttling fetch_cap toward ~1000, the hardcoded ceiling of 48 silently caps fetch concurrency -> retrieval wall-clock balloons on a large corpus (the o

- [P2] src/polaris_graph/retrieval/live_retriever.py:90-94 and :279 (_SERPER_PAGE_MAX) and :1347 (_JSONLD_MAX_CHARS)
  WHAT: Module-level retrieval caps: per-source result caps + content char cap + HTTP timeout (DEFAULT_MAX_SERPER/S2/FETCH_CAP/CONTENT_MAX/HTTP_TIMEOUT) and two bare constants _SERPER_PAGE_MAX=20, _JSONLD_MAX_CHARS=20000.
  CURRENT: PG_LIVE_MAX_SERPER=20, PG_LIVE_MAX_S2=20, PG_LIVE_FETCH_CAP=40, PG_LIVE_CONTENT_MAX=25000, PG_LIVE_HTTP_TIMEOUT=20 (env-wrapped, throttled defaults); _SERPER_PAGE_MAX=20 and _JSONLD_MAX_CHARS=20000 (bare literals, NOT env-wrapped).
  CLAUDE_FIX: De-throttle the DEFAULT_* defaults (consistent with the P1 sweep fix) and wrap the two bare constants: _SERPER_PAGE_MAX=int(os.getenv('PG_SERPER_PAGE_MAX','20')), _JSONLD_MAX_CHARS=int(os.getenv('PG_JSONLD_MAX_CHARS','20000')).
  WHY: The DEFAULT_* family is env-wrapped but defaults to the same throttled 20/20/40 class as the sweep knobs (a no-env direct retriever call is capped at 40 URLs). _SERPER_PAGE_MAX and _JSONLD_MAX_CHARS are bare magic numbers with no env knob -- the page-max silently bounds how deep Serper paginates, capping breadth independent of the env fetch_cap.

- [P2] src/polaris_graph/llm/openrouter_client.py:804-805
  WHAT: LLM retry policy shared by every call on the path (generator, verifiers, outline, dedup): retry count and exponential-backoff base.
  CURRENT: MAX_RETRIES = 2 ; RETRY_BACKOFF_BASE = 2.0 (bare module constants)
  CLAUDE_FIX: MAX_RETRIES=int(os.getenv('PG_LLM_MAX_RETRIES','2')); RETRY_BACKOFF_BASE=float(os.getenv('PG_LLM_RETRY_BACKOFF_BASE','2.0')).
  WHY: Both are hardcoded with no PG_ env var. Retry count and backoff directly govern resilience to transient provider stalls (the exact failure mode -- a 0-socket wedge -- the wall-clock guard was added for). The operator requires every such tunable to be env-driven; an operator hitting a flaky provider cannot raise retries without a code change.

- [P3] src/polaris_graph/llm/openrouter_client.py:1563/1592 (_call/_call_impl) and 2697/2734 (generate/_generate_impl) and 3060 (generate_structured) and 1561/1590 (reasoning_effort)
  WHAT: The default max_tokens and reasoning_effort kwargs on the core client methods that callers fall back to when they do not pass an explicit value.
  CURRENT: _call/_call_impl max_tokens=16384, reasoning_effort='high'; generate max_tokens=4096; generate_structured max_tokens=8192; temperature=0.7 throughout.
  CLAUDE_FIX: Make the signature defaults read a module-level env default, e.g. max_tokens: int = _DEFAULT_GENERATE_MAX_TOKENS where _DEFAULT_GENERATE_MAX_TOKENS=int(os.getenv('PG_DEFAULT_GENERATE_MAX_TOKENS','4096')); and reasoning_effort=os.getenv('PG_DEFAULT_REASONING_EFFORT','high'). Lower priority because li
  WHY: These are hardcoded method-signature defaults. On the live path the section writer DOES pass an explicit section_max_tokens so the 16384/4096 defaults are usually overridden -- but any current or future caller that omits max_tokens (e.g. a small auxiliary call) silently inherits a fixed budget with no env backstop, and the reasoning-first FLOOR (32768) only rescues reasoning-ON paths. The operator

- [P3] src/polaris_graph/generator/live_deepseek_generator.py:411-412
  WHAT: generate_live_draft() default temperature and max_tokens for a one-shot draft generation.
  CURRENT: temperature: float = 0.3, max_tokens: int = 2000
  CLAUDE_FIX: max_tokens=int(os.getenv('PG_LIVE_DRAFT_MAX_TOKENS','2000')) (and raise the default for the reasoning-first writer), temperature=float(os.getenv('PG_LIVE_DRAFT_TEMPERATURE','0.3')); or delete the dead function if confirmed unused.
  WHY: max_tokens=2000 is a hardcoded default with no PG_ knob; on the reasoning-first deepseek-v4-pro writer 2000 is below the model's reasoning footprint -> empty/truncated draft. CURRENTLY LATENT: grep shows generate_live_draft has no live call site (only its definition), so it does not run this sweep -- but it is a re-wire land mine of the exact I-arch-003 starvation class sitting in a run-path modul

- [P3] src/polaris_graph/agents/searcher.py:194, 705, 746, 850, 938
  WHAT: Hardcoded per-call timeouts on the agentic-search lane's external search-API calls (OpenAlex / urllib executor wraps), active when PG_AGENTIC_* is enabled and agents.searcher is imported at run_honest_sweep_r3.py:3930.
  CURRENT: timeout=30.0 (x4) and timeout=45.0 (urllib.urlopen timeout=30 at :194)
  CLAUDE_FIX: Route through a named env knob, e.g. timeout=float(os.getenv('PG_SEARCH_API_TIMEOUT_SECONDS','30')) (and a distinct PG_SEARCH_HTML_TIMEOUT_SECONDS for the 45s HTML-fetch leg).
  WHY: Bare literals, no PG_ env var. A slow but legitimate search backend gets cut at 30-45s with no operator lever to extend -- the same 'arbitrary small timeout strangles real work' pattern, on the breadth-feeding search lane. Lower severity than the generator timeouts because these bound cheap search calls, not the multi-minute reasoning writer, and only fire on the agentic lane.
