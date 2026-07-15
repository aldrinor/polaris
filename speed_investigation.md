
================================================================================
LANE: QUALITY-CONSTRAINT AUDIT  (subagent, 2026-07-12)
Invariants: (I1) DEEP COVERAGE 328/329 baskets | (I2) FAITHFULNESS verdict-identity
(strict_verify + NLI kept/dropped set unchanged; no derived number via [CITE:ev_xxx])
| (I3) cp4_used=agentic (never degrade-to-seed) | (I4) NO DEADLOCK.
Code anchors read (READ-ONLY, outline_agent worktree):
  - outline turn loop / degrade: src/polaris_graph/outline/outline_agent.py:1885, :2051-2102
      cp4_used set at :2080 -> "agentic" ONLY if no exception; ANY exception (incl. the
      outer asyncio.wait_for at :2054, timeout = wall_seconds(900)+grace) => degraded_to_seed
      => cp4_used="agentic-degraded-seed". Turn budget: max_turns=24, wall=900s (:106-108).
  - retrieval is ONE query/turn wrapped in asyncio.to_thread(run_live_retrieval): :732.
      asyncio.to_thread uses the LOOP DEFAULT executor (bounded ~min(32,cpu+4)).
  - compose concurrency (MAP pure per-basket + SERIAL REDUCE): verified_compose.py:2846-2995,
      knob PG_COMPOSE_BASKET_WORKERS (default 1 => byte-identical serial). REDUCE at :2904
      applies §3.5 marker filter + footprint-number + subset/text dedup IN ORDER.
  - side-judge in-flight cap (verify_fn NLI POSTs): llm/judge_concurrency.py
      acquire_judge_slot, default PG_SIDE_JUDGE_MAX_CONCURRENCY=4, "0"=unbounded.
  - strict_verify gate: clinical_generator/strict_verify.py:1-40 (checks a-e mechanical +
      f entailment PG_STRICT_VERIFY_ENTAILMENT).
  - parallel_fetch substrate EXISTS but NOT wired to live_retriever (phase-1 only):
      audit_ir/parallel_fetch.py header. retrieval_cache has eviction API: audit_ir/retrieval_cache.py.

PER-IDEA VERDICT (threatened invariants -> concrete guard):

1) PARALLEL RETRIEVAL (fan-out the per-turn fetch / multiple queries per turn)
   Threatens: I4 (deadlock), I2 (verdict set), I3 (degrade).
   - I4: run_live_retrieval is wrapped in asyncio.to_thread (loop default executor). Fanning
     out N to_thread calls per turn, each of which internally fetches, can saturate the shared
     default executor; if a compose/verify to_thread is also live they starve each other.
     GUARD: give retrieval fan-out its OWN dedicated ThreadPoolExecutor (never the default
     to_thread pool), bound it independently, and keep a per-fetch timeout (fetch_limiter
     FETCH_TIMEOUT=30). Never let a child task block on a pool its parent thread occupies.
   - I2: fan-out changes ARRIVAL ORDER of fetched rows -> the fold-in dedup (_fold_in url-dedup
     -> offset-renumber -> S2 stamp) is ORDER-SENSITIVE, so a different arrival order can change
     WHICH rows survive => different evidence pool => different NLI kept/dropped set. GUARD:
     collect all fan-out results then fold them in a DETERMINISTIC canonical order (e.g. sort by
     candidate/url key) before the serial fold-in — mirror the compose MAP-then-serial-REDUCE
     pattern. Verdict-identity must be A/B proven at FULL 328 scale, not a small sample.
   - I3: NOT a shortcut by itself; but if fan-out raises unhandled it trips the :2061 except and
     degrades to seed. GUARD: per-round try/except already at :740 returns a failed ToolResult
     (loop continues) — keep that; do not let fan-out exceptions escape to :2054.
   SAFE IF GUARDED. Genuinely reduces the ~24min agentic phase (serial one-fetch-per-turn is the
   long pole) WITHOUT dropping baskets.

2) FETCH CACHE (reuse source-fetch responses; retrieval_cache.py)
   Threatens: I2 (faithfulness via staleness), minor I1.
   - I2: a stale cached source that has been RETRACTED/superseded is a faithfulness liability —
     it can keep a claim whose evidence no longer exists. GUARD: cache already ships eviction
     (evict_by_url / evict_older_than) — pure TTL is explicitly rejected in the module. Cache the
     FETCH BYTES only; keep strict_verify + NLI running LIVE on cached content (verdict computed
     fresh, never cached). Cache-key canonicalization must not merge two DIFFERENT sources.
   SAFE IF GUARDED (verdict recomputed, eviction on retraction). Does not touch coverage.

3) TURN CAP (lower PG_OUTLINE_AGENT_MAX_TURNS / PG_REACT_MAX_ITERATIONS to end the loop sooner)
   Threatens: I1 (coverage), I3 (agentic), I2.
   - I1/I3: cutting turns starves the gap-ledger — finish_outline BOUNCES while pending gaps +
     budget remain (:1898). Fewer turns => fewer baskets discovered/filled => this is "speed up by
     dropping coverage." And a hard turn cap that leaves gaps is functionally a quieter
     degrade-to-seed. DISQUALIFIED as a primary speedup: it buys wall-time by REDUCING retrieval
     depth, violating I1. (Only legitimate if the loop is PROVABLY converged — pending_count==0 and
     no deficiencies — in which case it changes nothing.)
   DISQUALIFIED (drops coverage / weakens agentic depth).

4) OFF-LOOP-ONLY COMPOSE (the verdict-safe to_thread wrap already ported; workers=1)
   Threatens: none of I1/I2/I3 by construction; watch I4.
   - This is the SAFE baseline: workers<=1 => serial loop byte-identical (:2851-2852,:2997-2999),
     verdict-identical, coverage-neutral, cannot degrade. Its ONLY win is moving compose OFF the
     event loop so async retrieval overlaps — modest (compose is the smaller slice per the brief).
   - I4 residual: it still uses asyncio.to_thread => the default-executor contention above. GUARD:
     dedicated executor, not the default to_thread pool.
   SAFE. This is the floor that must hold if the aggressive path is disabled.

5) BASKET-WORKER SHARDING (PG_COMPOSE_BASKET_WORKERS>1 + raised side-judge semaphore(48))
   Threatens: I4 (this is the one that ALREADY DEADLOCKED — 19/20 threads futex_wait, SIGKILL), I2.
   - I4 ROOT CAUSE (mechanism): nested bounded pools. The compose MAP opens ThreadPoolExecutor(
     max_workers=N) at verified_compose.py:2981/2992; each map thread calls verify_fn -> NLI POST
     -> acquire_judge_slot (shared process-global BoundedSemaphore, judge_concurrency.py:169).
     Meanwhile the whole compose is (or is called under) an asyncio.to_thread wrap that consumes
     the LOOP DEFAULT executor (~32 threads). At 328-basket scale: default-executor threads are
     all parked holding the compose call, the ThreadPool(48) threads all park in
     acquire_judge_slot / fut.result -> classic thread-pool STARVATION: no thread free to run the
     continuation that would release a slot. Raising the semaphore to 48 did NOT cure it (it also
     removes the de-storm 429 protection, judge_concurrency.py:31-37) — it just moves the wedge.
     CONCRETE GUARD (all required):
       (a) Run the compose MAP on a DEDICATED, module-owned ThreadPoolExecutor — NEVER nested
           inside an asyncio.to_thread that shares the loop default executor.
       (b) Keep basket_workers * section_concurrency <= a fixed global thread budget, and keep
           the side-judge cap >= that in-flight count so judge POSTs never block behind their own
           producers (but keep it <= provider-safe ~4-8 per host to preserve 429 de-storm — do
           NOT jump to 48).
       (c) Add acquire_judge_slot(timeout=...) on the COMPOSE path too (the timeout+JudgeSlotTimeout
           degrade already exists for the advisory judge, :165-176) so a wedged holder force-frees
           its slot instead of futex-waiting forever.
       (d) Watchdog: a per-section wall so a stalled MAP force-cancels instead of SIGKILL.
   - I2: sharding is verdict-safe ONLY because REDUCE stays serial in original basket order
     (:2904-2953). GUARD: never parallelize the reduce; A/B the kept/dropped set at full scale.
   SAFE ONLY WITH (a)-(d). As shipped/attempted (workers>1 + sem 48, nested on default executor)
   it is DISQUALIFIED until the nesting + shared-executor deadlock is fixed. A speedup that hangs
   is not a speedup (I4).

6) LOWER VERIFY CONCURRENCY (reduce PG_SIDE_JUDGE_MAX_CONCURRENCY / verifier semaphores)
   Threatens: I2 indirectly, I3, and it is usually the WRONG DIRECTION for speed.
   - The side-judge cap is a FAITHFULNESS-STRENGTHENING de-storm (fewer 429 -> fewer
     retry-exhaustion fail-CLOSED drops -> MORE claims verified with SAME verdicts,
     judge_concurrency.py:17-24). Lowering it further only SLOWS verify (fewer in flight); RAISING
     it too far re-introduces the 429 storm that fail-CLOSED-drops claims -> that CHANGES the NLI
     kept set (I2) AND can push the outline past wall -> degrade (I3). GUARD: keep the cap in the
     validated ~4-8/host band; treat it as a correctness knob, not a speed knob. It is NOT a
     speedup lever — flag any plan that trades verify concurrency for wall-time.
   NOT A SAFE SPEEDUP (either slows verify or risks verdict-changing 429 drops).

7) BATCHED JUDGE (coalesce many NLI/entailment claims into one provider call)
   Threatens: I2 (verdict-identity), I4 mildly.
   - I2: batching N claims into one prompt changes the model INPUT (cross-claim context, shared
     token budget, truncation) => a per-claim verdict can flip vs the one-claim-per-POST baseline.
     strict_verify entailment (check f) and the NLI kept/dropped set are defined per-sentence; a
     batched verdict is NOT guaranteed identical. GUARD: only safe if batching is a pure transport
     coalesce that yields BYTE-IDENTICAL per-claim verdicts (same model/prompt/temp/max_tokens/
     parsing, no shared context, deterministic split) — must be proven verdict-identical at full
     scale before adoption; otherwise DISQUALIFIED (weakens verify gate by changing verdicts).
   - I4: fewer POSTs actually EASES the semaphore pressure (mild positive for deadlock).
   SAFE ONLY IF proven per-claim verdict-identical; default posture DISQUALIFIED.

SUMMARY:
  DISQUALIFIED as shortcuts: (3) turn cap (drops coverage/agentic depth); (5) as-attempted
    workers>1+sem48 nested on default executor (deadlock); (7) batched judge unless byte-identical.
  NOT A SPEED LEVER: (6) verify concurrency (correctness knob; wrong direction).
  SAFE WITH NAMED GUARDS: (1) parallel retrieval [dedicated pool + deterministic fold-in order +
    contained exceptions], (2) fetch cache [bytes-only, live verdict, eviction-on-retraction],
    (4) off-loop-only compose [floor, keep dedicated executor], (5) basket sharding ONLY with
    dedicated executor + bounded nesting + judge-slot timeout + watchdog + serial reduce.
  CROSS-CUTTING GUARD FOR EVERY IDEA: full-328-scale verdict-identity A/B (the small A/B that
    "passed but never exercised full-scale concurrency" is INSUFFICIENT), and assert
    cp4_used=="agentic" + rendered basket count ~328/329 on the sped-up run.


================================================================================
LANE: WHOLE-PIPELINE PROFILE  (subagent, 2026-07-12)
Goal: split the deep route_all render into phases, measure each phase's wall-time
share from REAL logs, name the biggest lever AFTER retrieval, and test whether the
41% sentence-drop rate wastes compute.

DATA SOURCES (measured, not estimated):
  - logs/step4_route_all_compose.log  -> the ONE clean, COMPLETED route_all=329-basket
    deep run. elapsed_seconds=1449.7 (24.2 min). Phase timestamps below are from this log.
  - outputs/step3_treatment_compose.log (elapsed 1715.1s) + step3_control_compose.log
    (1671.0s) -> two more completed 329-basket runs; used to cross-check drop rate.
  - outputs/_16way_run.log -> the DEADLOCK/SIGKILL run (semaphore max=48). It never
    reached a full compose: retrieval degraded (one search_more_evidence fetched 162/200
    URLs in 466.2s, then the react loop hit TimeoutError at ~17.7 min -> DEGRADE TO SEED),
    then compose was SIGKILLed at 05:14:38. Compose/verify/RACE NOT measurable from it.

PHASE BREAKDOWN (step4_route_all, 1449.7s total):
  | # | Phase                                                   | Window            | Dur  | %     |
  | A | Init + outline SEED digest (1 deepseek gen = 118.5s)    | 04:10:43->04:13:05| 142s | 9.8%  |
  | B | AGENTIC RETRIEVAL (react loop, search_more_evidence)    | 04:13:05->04:25:22| 737s | 50.8% |
  | C | outline finalize + content_dedup + consolidate + cred   | 04:25:22->04:25:55|  33s | 2.3%  |
  | D | COMPOSE draft + strict_verify + repair_loop + regen     | 04:25:55->04:34:29| 514s | 35.5% |
  | E | fact_dedup + analyst_synthesis + final render/faithful  | 04:34:29->04:34:56|  27s | 1.9%  |

  - Credibility pass = FREE here: "no production credibility judge wired (judge=None)",
    priors-only + threaded, runs inside window C's 33s. Not a lever.
  - dedup/consolidate: content_dedup 1036->961 findings + W9 consolidate (52 baskets) =
    part of the 33s window C. Not a lever.
  - RACE score: NOT present in ANY render log. RACE is a separate downstream eval harness,
    not part of render-pipeline timing. CANNOT measure it from these logs.

RANKING BY TIME (deep run wall-clock):
  1. Retrieval (react loop)          737s / 50.8%
  2. Compose + strict_verify         514s / 35.5%
  3. Outline seed digest             142s /  9.8%  (a single 118.5s deepseek outline_digest gen)
  4. dedup/consolidate/credibility    33s /  2.3%
  5. fact_dedup/analyst/render        27s /  1.9%

  Retrieval-variance note: this CLEAN run's retrieval was 12.3 min, NOT the ~24 min in the
  brief. Retrieval's TAIL is dominated by mega-fetches at the 200-URL fetch_cap (16way run:
  one react turn fetched 162/200 URLs in 466s = 7.7 min, then TimeoutError degraded the loop).
  So "24 min retrieval / 30+ min e2e" is the BAD-tail case; "12 min / 24 min" is the clean case.
  Either way: retrieval #1, compose #2.

BIGGEST LEVER AFTER RETRIEVAL = COMPOSE + strict_verify (Phase D, 514s / 35.5%).
  Mechanics (multi_section_generator.py + log): compose is PER-SECTION (8 sections) under a
  concurrency semaphore of max=5 (step3 AND step4 clean runs both used max=5; the 48-way was
  the deadlock run). Each section: draft -> strict_verify (drops non-entailed sentences) ->
  repair_loop (per-failing-sentence LLM re-draft + re-verify) -> if kept_fraction < 0.40 REGEN
  the whole section once ("post-M-41c kept_fraction=0.36 below min 0.40 — retrying").
  strict_verify itself is a LOCAL CrossEncoder NLI (consolidation_nli.entails_directional,
  nli-deberta-v3-base on cuda:0) -> "ZERO new model / OpenRouter spend". So VERIFY is cheap and
  IS the faithfulness gate (I2). The cost/waste is the LLM GENERATION around it.

IS THE 41% DROP RATE WASTING COMPUTE? YES — quantified.
  Drop rates (dropped/(verified+dropped)):
    step3_control    64/155 = 41.3%   (the "41%")
    step3_treatment  70/150 = 46.7%
    step4_route_all  68/133 = 51.1%
  Direct waste in Phase D (step4): 38 compose LLM generate calls for 8 sections = 10 big
  draft/regen calls + 28 SMALL (<3k in_tok) repair_loop calls. The 28 repair calls exist ONLY
  because sentences failed strict_verify (repair_loop attempts up to =10 for one section).
  2 of 8 sections REGENERATED (Introduction kept_fraction=0.36; Empirical=0.32) -> whole section
  drafted a 2nd time. WORST CASE (step3_treatment "Automation, Tasks, and Job Reinstatement"):
  verified=0 dropped=16 regen=True -> a section drafted TWICE that produced ZERO surviving
  sentences. Pure waste; regen gained nothing.
  ~45% of drafted sentences are discarded AFTER generation. Rough wall-time of drop-driven
  repair+regen in Phase D ~ 130-180s of the 514s (~25-35% of compose), partially hidden by max=5.

RANKING BY SPEEDUP LEVERAGE (after retrieval), invariant-safe:
  1. Compose concurrency (Phase D, 514s). Currently max=5; compose_fix ships 16-way; 48-way
     DEADLOCKED. Safe: raise section concurrency 5 -> tested 8-16 so per-section repair/regen
     latency overlaps. Risk I4 (stay below the 48 futex-starvation ceiling; dedicated bounded
     pool, NOT unbounded semaphore(48); keep OFF-LOOP to_thread). Verdict-identical (I2): each
     section's strict_verify runs unchanged.
  2. Cut drop-driven waste WITHOUT touching the gate (Phase D). Raise FIRST-PASS entailment
     yield so fewer drafts fail (tighter per-sentence span grounding in the draft prompt), and
     SKIP regen when it historically converges to verified~=0 (the verified=0/regen=True case
     gains nothing but costs a full redraft). This changes what you FEED the gate, never the
     gate -> keeps kept/dropped NLI verdict set byte-identical (I2). Do NOT loosen verification
     to lower the drop rate.
  3. Outline seed digest (Phase A, 142s). One 118.5s deepseek outline_digest call. Smaller
     lever; cutting risks outline quality / I3 (must stay cp4_used=agentic). Low priority.

CAVEAT: the drop itself is the faithfulness gate and CHEAP (local NLI). The recoverable compute
is the GENERATION of doomed sentences + repair_loop + full-section regen — not the verification.
Any fix must keep the kept/dropped NLI verdict set byte-identical (I2) and cp4_used=agentic (I3).

================================================================================
LANE: RETRIEVAL (agentic outline react loop)  (subagent, 2026-07-12)
Goal: find WHY the ~agentic retrieval phase is the long pole; propose coverage/
faithfulness-safe speedups. All numbers below are REAL, measured from the deep
render log outputs/../logs/step4_route_all_compose.log (PG_OUTLINE_AGENT=1,
corpus cp4_corpus_s3gear_329, evidence=997, clusters=329, route_all).

MEASURED PHASE BREAKDOWN (step4_route_all, one full deep render):
  - END-TO-END: 1449.7s (24.2 min)  [elapsed_seconds in log tail]
  - RETRIEVAL/OUTLINE phase: 04:10:46 -> 04:25:22 = 876s (14.6 min = 60% of run)
      * seed outline build + seed checklist: 04:10:46 -> 04:13:05 = 139s
      * agentic react loop:                  04:13:05 -> 04:25:22 = 737s
  - COMPOSE phase: ~04:25:22 -> 04:34:52 = ~570s (9.5 min = 40%)  => retrieval IS the long pole.
  Corroboration (seed-checklist -> "multi_section outline:" across other deep logs):
      step2=898s, step3_treatment=922s, _16way_run=1062s, step4=737s(loop only).
      => retrieval/outline phase is consistently ~12-18 min. (Brief's "~24 min" is the
      high end / a heavier run; I could not reproduce 24 min in the logs on hand, but
      retrieval is unambiguously the dominant phase every time.)

REACT-LOOP INTERNALS (measured):
  - 13 search_more_evidence calls; total FETCH wall = 346.3s; total NEW rows kept = 42.
  - Non-fetch LLM overhead inside the loop = 737 - 346 = ~391s (53% of the loop):
      _decide (reasoning_effort=high, max_tokens=131072, reasoning_max=32768; decide wall 660s)
      + after_fold full-section checklist (ran 11x, each an LLM per section)
      + fold-in per-row S2 topic-judge.
    Per turn that is ~20-24s of LLM latency that is NOT fetching; one post-bounce _decide
    alone took ~62s (04:22:34 -> ~04:23:36).
  - WITHIN a single search, URL fetch is ALREADY parallel: live_retriever.py:6363-6441
    parallel_fetch(max_workers=band 8-14, per_task_timeout=120s, per-host cap 4). So the
    per-search 12-56s is bounded by the slowest URL in the batch, NOT sequential fetching.
    => lack of intra-search fetch concurrency is NOT the bottleneck.

THREE CONCRETE WASTE SOURCES (measured, in priority order):

  W1. TURN-LEVEL SERIALIZATION. The seed checklist named 3 gaps AT ONCE (04:13:05) but the
      loop drains them ONE gap per turn, re-running the full per-section after_fold checklist
      LLM between every fetch. 13 sequential turns * (fetch ~27s + checklist ~10-15s + decide
      ~7-62s). The ~391s of non-fetch LLM overhead is largely the between-fetch checklist +
      decide serialization.

  W2. ZERO-YIELD REDUNDANT RE-FETCHES. Four consecutive searches 04:20:01/04:20:36/04:21:08/
      04:21:59 for the SAME aspect ("impacts across various industries", re-worded each time)
      each fetched 8-10 URLs but kept=0 — every URL was a url-dup already in ev_store
      (url-dup dropped 9/9, 10/10, 8/8, 9/9). The whole 04:19:35 -> 04:22:34 stretch = 179s
      (24% of the react loop) produced ZERO new rows. Serper returns the same top URLs for
      near-identical queries; there is no query->URL-set cache and no per-aspect "URL set
      already exhausted -> stop re-searching" breaker at the fetch layer (the section-veto at
      outline_agent.py:1630 only covers structurally-unhomeable SECTIONS, not exhausted aspects).

  W3. HEAVY DECIDE. _decide uses reasoning_effort=high + max_tokens=131072 for what is a menu
      pick over ~5 tools; it is the variable tail (one call ~62s). query_derive also carries
      max_tokens=131072 default (outline_agent.py:134) though bounded by reasoning_max.

PROPOSED SPEEDUPS (retrieval lane; coverage + faithfulness safe):

  R1 [BIG, safe-with-guards]  PARALLEL GAP DRAIN + single checklist per round.
     Fetch the N PENDING ledger gaps concurrently (bounded 3-4), then fold-in SEQUENTIALLY in a
     deterministic order and run the after_fold checklist ONCE per batch instead of once per
     fetch. Collapses ~13 sequential turns into ~4-5 batched rounds and removes the redundant
     between-fetch checklists. Est saving ~3-5 min.
     QUALITY: coverage unchanged (same gaps fetched); search_more_evidence only ADDS candidate
     rows — the strict_verify + NLI kept/dropped set is computed downstream and is unchanged.
     RISK/GUARD: (a) fold_in_fetched_rows (url-dedup -> offset-renumber hard assert -> S2 stamp)
     is ORDER-SENSITIVE, so keep fold-in SERIAL in a canonical (sorted url/candidate-key) order —
     parallelize only the FETCHES. (b) Give the fan-out its OWN dedicated ThreadPoolExecutor,
     NOT asyncio.to_thread's shared loop-default pool — this is exactly the shared-executor
     nesting that produced the 328-scale futex deadlock; cap concurrency low (3-4) since the
     outline agent runs ONCE per report (not per basket) so it needs no aggressive fan-out.
     (c) contain fan-out exceptions per-round (the :740 try/except already returns a failed
     ToolResult) so nothing escapes to :2054 and trips degrade-to-seed. MUST A/B verdict-identity
     at full 328 scale + assert cp4_used=="agentic".

  R2 [MEDIUM, safe]  PER-ASPECT URL-EXHAUSTION BREAKER + intra-run query/URL-set cache.
     Cache Serper query->URL-set within a run; when a derived query's candidate URL set is
     >=~90% already in ev_store, SKIP the fetch and route the aspect straight to
     UNFILLED+disclosed (the module already discloses at the retry cap) instead of re-wording
     and re-firing. Directly kills the W2 179s zero-yield stretch. Est saving ~2-3 min.
     QUALITY: does NOT drop any basket (baskets are the pre-existing 329 clusters; this only
     stops re-fetching evidence already pooled); disclosure preserved; verdicts unaffected.
     RISK/GUARD: key the breaker on URL-SET overlap AFTER the same url-dedup rule, never on query
     TEXT, so a genuinely-new query is never suppressed.

  R3 [SMALL, needs A/B]  CHEAPER DECIDE. Drop the _decide call (only) to reasoning_effort=medium
     / smaller reasoning_max_tokens, and lower PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS from 131072.
     Est saving ~30-90s.
     QUALITY: decide is a routing choice, not a faithfulness judgment; checklist critic + strict_
     verify + NLI untouched. RISK: it CAN change WHICH gaps are searched -> different evidence
     pool -> not strictly verdict-identical. Flag: gate behind full-scale verdict-identity A/B;
     lower priority than R1/R2.

  DISQUALIFIED: a blanket lower PG_OUTLINE_AGENT_MAX_TURNS is a coverage cut (starves the gap
  ledger while pending+budget remain) — same verdict as the quality-audit lane's idea (3). The
  W2 breaker (R2) achieves the same wall savings WITHOUT dropping depth, so prefer it.

## ADVERSARIAL VERDICT: "Cut react-loop turns (max_turns cap)" — DISQUALIFIED (keeps_quality=FALSE)

Reviewed 2026-07-12. Verdict: REJECT as a primary lever. Confirms the proposal's own self-assessment.

### Static evidence (read-only, outline_agent worktree)
- `src/polaris_graph/outline/outline_agent.py:106-108` — MAX_TURNS=24, WALL=900s, gap_retries/aspect=2.
- `outline_agent.py:1885` loop guard: `while ws.turn < self.max_turns and ws.elapsed_seconds() < self.wall_seconds`.
- `outline_agent.py:1894-1909` finish handling: on `finish_outline`, re-runs checklist and reads
  `pending = ws.gap_ledger.pending_count`. If `(deficiencies or pending) and budget_remains` -> BOUNCES
  (`continue`) and keeps searching. It only ACCEPTS/breaks when pending==0 AND no new deficiencies, OR
  when budget is already gone.
- `outline_agent.py:1917-1922` — any todo still PENDING at loop exit is recorded UNFILLED (two distinct
  reasons: "budget exhausted after retries" / "...before this gap was ever searched").
- `src/polaris_graph/tools/react_agent.py:45` — `PG_REACT_MAX_ITERATIONS` default 5 (per-URL react depth).

### Why it fails the invariants
The loop is coverage-bound, not idle-bound. The cap is the exact budget that lets the agent bounce and
keep filling pending gaps. Lowering max_turns (or wall) makes `budget_remains` go False earlier while
`pending>0`, so those todos exit marked PENDING = baskets never discovered/filled.
- I1 DEEP COVERAGE: violated — fewer turns -> fewer baskets filled -> renders < 328/329. Speed comes
  entirely out of coverage. Not a legal saving.
- I3 AGENTIC: violated — a hard cap that exits with pending gaps is a quiet degrade of agentic depth
  (the observed seed+partial degradation mode), not cp4_used=agentic to completion.
- I2 FAITHFULNESS / I4 DEADLOCK: not the failure mode here (verdict gate untouched; no new concurrency),
  but that does not rescue it — I1/I3 alone disqualify.

### The saving is illusory in the only legal case
The only legitimate case is a PROVABLY converged loop (pending_count==0 AND no checklist deficiencies).
But in that case the loop ALREADY breaks via the ACCEPTED path at :1905-1909 before reaching the cap —
so max_turns is not the binding constraint and cutting it saves ~0 wall-time. Where cutting turns DOES
save wall-time (24min pole), it is precisely because pending gaps still exist -> coverage drop.

REAL SAVING: 0 in the legal (already-converged) case; "large" only by dropping coverage in the illegal
case. keeps_quality = FALSE.

---

## ADVERSARIAL VERDICT — PG_SIDE_JUDGE_MAX_CONCURRENCY as a "speed lever" (2026-07-12)

CLAIM UNDER TEST: whether tuning `PG_SIDE_JUDGE_MAX_CONCURRENCY` (the side-judge in-flight cap)
is a safe wall-time speedup. VERDICT: **keeps_quality = FALSE. Not a speedup at all — it is a
correctness knob.** Keep it in the validated ~4-8/host band; both directions are unsafe or useless.

MEASURED / CODE-VERIFIED EVIDENCE (both worktrees byte-identical — `diff` = IDENTICAL):
- `judge_concurrency.py:55` DEFAULT_MAX_CONCURRENCY = 4; `:51-54` memory standard "<=4 agents in
  flight", operators MAY raise "if provider capacity allows". Docstring `:17-24,:31-37` states the
  cap is a faithfulness-STRENGTHENING de-storm: fewer simultaneous mirror-chain POSTs -> fewer 429 ->
  fewer retry-exhaustion fail-CLOSED `('ENTAILED','judge_error')` sentinels -> MORE claims verified
  with the SAME verdicts. Root cause it cures: ~32 simultaneous entailment POSTs 429-stormed the
  `friendli` lead host on the 2026-07-04 preflight, collapsing the abstract/full-verify layers.
- The cap governs THREE verify-path judges only: `entailment_judge.py:155`,
  `credibility_judge_caller.py:143`, `semantic_conflict_detector.py:125` — all in the COMPOSE/verify
  phase, NOT the agentic-retrieval react loop that dominates wall time (~24 of ~30 min). So even in a
  best case it cannot touch the dominant slice.

WHY BOTH DIRECTIONS FAIL:
- RAISE toward 48 (for "speed"): re-introduces the exact 429 storm the cap was built to kill.
  Retry-exhaustion fail-CLOSED drops CHANGE the NLI kept set => violates INVARIANT 2 (faithfulness
  verdict-identity). The storm's 15-50s rate-limit backoffs also burn wall; with
  `PG_OUTLINE_AGENT_WALL_SECONDS_DEFAULT = 900` (outline_agent.py:108) a storm can push the outline
  past the 900s wall => degrade-to-seed => violates INVARIANT 3 (cp4_used=agentic). Note this is a
  DIFFERENT semaphore from the compose-basket-workers(48) that DEADLOCKED at 328-scale, but "48" is
  the same wrong direction.
- LOWER below the band: only SLOWS the verify pass (fewer POSTs in flight). Negative saving. No
  invariant broken, but no benefit — strictly worse.
- The `credibility_pass_concurrency` override (multi_section_generator.py:10157) already raises the
  cap ONLY for the ADVISORY credibility pass (fail-open priors fallback), so even that scoped bump is
  faithfulness-neutral BY CONSTRUCTION and is not a general speed lever for the binding entailment cap.

BOTTOM LINE: the saving is None (the honest claim), and any move made "for speed" (raise) risks
invariants 2 and 3. Default-FALSE applies on both counts: marginal/negative saving AND invariant risk.
Recommendation: pin it in the ~4-8/host band and treat any plan that moves it as a correctness change
requiring a verdict-identity A/B, never as a wall-time optimization.

================================================================================
LANE: ADVERSARIAL VERIFY — "BATCH N CLAIMS INTO ONE VERIFY PROMPT" (subagent, 2026-07-12)
VERDICT: keeps_quality = FALSE (disqualified on I2; saving is marginal even if it worked)
READ-ONLY. Code anchors (outline_agent worktree):
  - strict_verify.py:529  verdict,reason = _get_judge().judge(sentence_clean, combined_span)
      -> ONE judge() call PER SENTENCE. Entailment mode DEFAULT = "enforce" (I-bug-095,
         _entailment_mode()). NEUTRAL/CONTRADICTED -> DROP; judge_error sentinel -> DROP.
  - entailment_judge.py:792  prompt = _select_entailment_prompt().format(span=span, sentence=sentence)
      -> template is SINGLE (span, sentence). One POST, one claim.
  - entailment_judge.py:830-835  json_body: temperature=0.0, max_tokens=_ent_maxtok,
      reasoning.effort=high, messages=[one user msg]. Model is GLM-5.1, a REASONING model.
  - entailment_judge.py:267-270  max_tokens chain-min = 131072 (un-starved ON PURPOSE:
      arch-002/arch-004-F19 = the reasoning model burns budget internally; starving it
      -> finish=length -> EMPTY content -> json.loads(None) -> judge_error -> coverage collapse).
  - entailment_judge.py:740-763  judge() has a per-(model,sentence,span,variant) verdict CACHE
      (temp=0 idempotent dedup). Batching bundles DIFFERENT neighbors -> destroys this cache key.
  - judge_concurrency.py:17-29 + strict_verify context: the REAL transport coalesce already
      exists = process-global bounded semaphore (PG_SIDE_JUDGE_MAX_CONCURRENCY, default 4),
      "changes ONLY when a POST is admitted — never model/prompt/temp/max_tokens/JSON/verdict".
  - NO batch-judge code exists anywhere in the judge path (grep: none). This is net-new surface.

WHY THE PREMISE IS FALSE (the speedup's own gate: "pure transport coalesce, BYTE-IDENTICAL
per-claim verdicts, same prompt, no cross-claim context, deterministic split"):
  Batching N claims into ONE prompt is a MODEL-INPUT change, not a transport change. Every clause
  of its own admission gate fails by construction:
  1. "same prompt" — VIOLATED. The template is single (span,sentence); a batch needs a NEW
     N-pair template. Different bytes in -> not guaranteed same verdict out.
  2. "no shared cross-claim context" — VIOLATED. All N claims share one context window; the model
     attends across them. Claim k's verdict can shift given claims 1..k-1. This is I2 exactly.
  3. "same max_tokens" — VIOLATED in effect. max_tokens becomes a SHARED budget across N reasoning
     traces. With chain-min 131072 split N ways, later claims truncate mid-reasoning -> finish=length
     -> EMPTY/partial JSON -> ('ENTAILED','judge_error:…') sentinel -> FAIL-CLOSED DROP in enforce.
     This is the SAME failure arch-002/F19 fought for a SINGLE claim, re-introduced N-fold. It flips
     verdicts (I2) and can mass-drop -> threatens I1 coverage too.
  4. "same JSON parsing" — VIOLATED. _extract_first_json_object takes the EARLIEST top-level JSON
     value (parses ONE verdict). A batch needs an N-element array + realign parser = new code, new
     failure modes (model emits N-1/N+1/reordered/mislabeled items on a free-text reasoning model).
  5. "deterministic split" — NOT guaranteed. Reasoning models reorder/merge/omit list items;
     verdict[i]->claim[i] realignment is not deterministic. A misalignment silently swaps verdicts.
  Net: it changes the model INPUT and the response contract -> cannot be assumed verdict-identical ->
  DISQUALIFIED under I2 (kept/dropped NLI set must be byte-identical). To adopt you must PROVE
  verdict-identity at full 328 scale EVERY run = a full re-verification A/B each run = the claimed
  "net negative" is REAL, not hypothetical.

DOES IT EVEN SAVE MEANINGFUL WALL-TIME? No (marginal).
  - Established: 30+min end-to-end is DOMINATED by AGENTIC RETRIEVAL (~24min). COMPOSE is the smaller
    slice; the entailment/verify POSTs are a SUB-slice of COMPOSE. Batching targets a fraction of a
    fraction — off the critical path.
  - The verify POSTs are ALREADY (a) idempotent-CACHED per (sentence,span) [dedups repeats for free]
    and (b) bounded to concurrency 4 with burst-spread. The transport pressure the batch claims to
    ease (I4 semaphore) is ALREADY solved faithfulness-neutrally by judge_concurrency.py. The batch
    buys the same POST-count relief the semaphore already provides, at the cost of I2.
  - In enforce, each claim already runs high-effort reasoning; N claims in one call don't cut total
    reasoning tokens, they just serialize them behind one shared budget (slower per-call, truncation
    risk). If PG_STRICT_VERIFY_ENTAILMENT=off (an operator production mode), there is NO per-claim POST
    to batch and the saving is exactly ZERO.

INVARIANT SCORECARD:
  I1 DEEP COVERAGE  — AT RISK: shared-budget truncation -> judge_error fail-closed -> mass drops.
  I2 VERDICT-IDENTITY — VIOLATED (primary disqualifier): cross-claim context + shared token budget +
     new prompt/parse/split can flip per-claim NEUTRAL/CONTRADICTED/judge_error -> altered kept/dropped set.
  I3 AGENTIC — untouched by this change (verify is post-retrieval), no direct effect.
  I4 NO DEADLOCK — mild positive (fewer POSTs), but the semaphore ALREADY delivers this without I2 cost.

BOTTOM LINE: Reject. Batching is a model-input change masquerading as a transport coalesce; it cannot
be assumed verdict-identical, its own adoption gate forces a full-scale re-verification A/B every run
(net-negative), and it targets a sub-slice of the smaller (compose) phase while the 24min agentic
retrieval remains the real long pole. The genuine transport win it claims (fewer POSTs) is already
banked by the existing bounded semaphore + verdict cache, faithfully.

================================================================================
ADVERSARIAL VERIFY: "PROFILING ATTRIBUTION" SPEEDUP  (subagent, 2026-07-12)
CLAIM UNDER TEST: rank post-retrieval time; compose+verify (514s/35.5%) is the
biggest lever after retrieval. STATED SAVING: "identifies where ~9min lives".
VERDICT: keeps_quality=FALSE — accurate diagnosis, but NOT a speedup (0s saved).

MEASURED (step4_route_all_compose.log, corpus=329, baskets=329, elapsed=1449.7s):
  A outline seed digest  04:10:43->04:13:06  = 143s  (~142 claimed) OK
  B retrieval react loop  04:13:06->~04:25:23 = 737s  (last ReactDecision 04:24:44,
                                                       dedup starts 04:25:55) OK
  C dedup/consolidate/cred ~04:25:23->04:25:56 = 33s  OK
  D compose + strict_verify ~04:25:56->04:34:29 = 513s (~514 claimed) OK
  E fact_dedup / render   04:34:29->04:34:56    = 27s  OK
  SUM=1453 ~= elapsed 1449.7 (4s overlap/rounding). Attribution CONFIRMED.

QUALITY INVARIANTS on THIS run (from compose_summary.json / log):
  I1 coverage: baskets=329, outline_sections=8, kept=8, dropped_sections=0. OK.
  I2 faithfulness: faithfulness_pass=true, leaked_cite_ev_tokens=0,
     unresolved_markers=[]; verified=65 dropped=68. OK.
  I3 agentic: finish_outline BOUNCED at turn 18 (kept looping on pending gaps),
     no degrade-to-seed line present. OK (agentic held).
  I4 deadlock: run completed cleanly (no SIGKILL). OK.
  => Measuring changes NOTHING, so it cannot violate any invariant. TRUE trivially.

WHY keeps_quality=FALSE anyway (per "FALSE if saving is marginal"):
  * This finding is a PROFILING ATTRIBUTION, not a code change. Real wall-time
    saved by the finding itself = 0s. It only points at where to optimize.
  * SCALE CAVEAT (important): this run = 24.2min total / 12.3min retrieval. The
    brief's established deep render = 30+min total / ~24min retrieval. So the
    35.5% compose share is drawn from a run where retrieval was HALF the brief's
    dominant phase. On the true 30-min render, retrieval's share GROWS and
    compose's 35.5% SHRINKS — the specific percentage is NOT portable, though the
    ranking (retrieval #1, compose #2) is robust.
  * Even hypothetically zeroing compose+verify (impossible w/o breaking I2) buys
    only ~35% of THIS run and less of the slower deep render; retrieval (the
    brief's ~24min long pole) is untouched by this lever.
  CONCLUSION: numbers are REAL and CORRECT; keep as a routing diagnosis. But it is
  not a speedup and must not be scored as one.

================================================================================
ADVERSARIAL VERDICT — "Cache fetched BYTES only (retrieval_cache.py), verdict live"
================================================================================
CLAIM: bytes-only per-workspace cache keyed by canon DOI/PMID/URL; strict_verify+NLI
run LIVE on cached content so verdict is recomputed fresh; eviction-on-retraction.
CLAIMED SAVING: run-dependent, largest on re-runs/overlap; ZERO on cold single run.

VERDICT: keeps_quality = FALSE (default-FALSE: saving is ZERO on the target workload
AND carries a residual cross-run faithfulness risk). Details below are code-verified.

FINDING 1 — NOT WIRED TO THE HOT PATH (delivers 0 as shipped).
  `grep -rn 'RetrievalCacheStore(' src` => NO production instantiation; the store is
  constructed ONLY in tests (test_md7_retrieval_cache, test_md7_phase2_cache_warming,
  test_md10_freshness_monitor, test_md3_decision_telemetry).
  The REAL hot fetch path is live_retriever.run_live_retrieval (httpx). It NEVER
  references retrieval_cache / make_cache_key (grep = "NO"). cache_warming.py and
  freshness_monitor.py name the types but are NOT invoked by any orchestration/graph
  entrypoint (only parallel_fetch mentions cache_warming in a docstring). So the M-D7
  cache is effectively dead code on the render path: it saves 0 wall-time today.
  Realizing ANY saving REQUIRES editing live_retriever's fetch loop — forbidden here
  (READ-ONLY; a wheel is live in outline_agent).

FINDING 2 — WRONG SLICE even if wired. The dominant ~24/30 min is the agentic-retrieval
  react loop, serialized "one turn at a time" because each turn's `_decide`
  (react_agent.py:715) is an LLM call that picks the NEXT url from PRIOR results, then
  `_execute_tool` (:743). A bytes cache only shortens the HTTP fetch inside
  `_execute_tool`; it CANNOT shorten the serial LLM-decision latency that is the very
  reason turns are serial. It attacks the fetch sub-slice, not the LLM-dependency chain
  that dominates.

FINDING 3 — ZERO ON THE STATED PROBLEM (proposer's own admission). The target is a
  SINGLE deep render (route_all, 328/329 baskets, ~30 min). Proposer states saving is
  "zero on a cold single run." That IS the workload. Benefit accrues only to
  re-runs/overlapping queries — a different workload than the one under investigation.

FINDING 4 — INTRA-RUN OVERLAP ALREADY PARTLY COVERED. live_retriever already ships two
  perf de-dups that eat most of the "same source fetched by two baskets" gain:
    - versioned authority_enrich.sqlite cache (live_retriever.py:93-116) whose version
      is bumped PRECISELY so cached retracted / boundary-year rows are REBUILT, not
      served stale;
    - a process-local per-URL negative refetch cache (:420, reset each run via
      reset_refetch_cache :434).
  A new raw-bytes cache is largely redundant with these for within-run overlap.

FINDING 5 — RESIDUAL FAITHFULNESS RISK (I2, not fully closed). Verdict recomputed live
  on cached BYTES is only as faithful as the bytes. Cross-run: if a source is retracted
  between runs and the M-D10 freshness daemon does not fire, live NLI runs on stale
  bytes and can KEEP a claim whose real-world evidence was retracted. Eviction
  (evict_by_url) is EVENT-DRIVEN, not guaranteed; pure-TTL is explicitly rejected in the
  header. Note the existing authority_enrich cache solved exactly this by CONTENT-VERSION
  bumping (force-rebuild); a raw-bytes cache has no equivalent content-version guard
  beyond the eviction hook. Bounded but nonzero — proposer acknowledges (I2).

INVARIANT LEDGER: I1 coverage neutral (true). I3 cannot-degrade (true). I4 no-deadlock
  (true — SQLite BEGIN IMMEDIATE per-call conns, no thread-pool storm). I2 faithfulness:
  verdict-identical ONLY when cached bytes == fresh bytes; stale-across-runs opens a
  residual keep-retracted window mitigated but not eliminated by event-driven eviction.

BOTTOM LINE: On the measured problem (one cold 328-basket render) the saving is ZERO by
  the proposer's own statement, the mechanism isn't even wired to the hot path, and it
  targets the fetch sub-slice rather than the serial-LLM react loop that dominates. That
  is the marginal-saving default-FALSE, compounded by a residual cross-run I2 risk.
  Recommendation: do NOT count this as a wall-time optimization for deep renders; if ever
  wired, treat it as a correctness change gated by a full-scale verdict-identity A/B and
  a guaranteed (not best-effort) eviction-on-retraction contract.

================================================================================
LANE: ADVERSARIAL VERIFY — "FAN-OUT FETCH ON DEDICATED POOL + CANONICAL FOLD"
(subagent, 2026-07-12)  VERDICT: keeps_quality = FALSE (saving overstated + I2 risk)

CLAIM UNDER TEST: fan out the per-turn fetch on a DEDICATED ThreadPoolExecutor,
keep FETCH_TIMEOUT=30, fold results in a canonical sorted (url/candidate-key)
order before the serial fold-in (compose MAP->serial-REDUCE mirror). CLAIMED
saving: "several to ~10+ min", "directly parallelizes the dominant serial fetch pole."

MEASURED (logs/step4_route_all_compose.log, the one clean 329-basket deep run):
  - e2e 1449.7s. React loop 737s. 13 search_more_evidence fetches.
  - TOTAL fetch wall across ALL 13 turns = 346.3s = 5.77 min (per-fetch:
    34.1/20.5/14.4/22.3/24.7/38.6/56.3/17.0/22.3/16.9/18.0/48.5/12.7). Max = 56.3s.
  - Non-fetch LLM overhead in loop = 737-346 = ~391s (53% — decide+checklist).

FINDING 1 — SAVING IS OVERSTATED / MARGINAL (physical ceiling < claim):
  The entire fetch pole is 5.77 min; you cannot save "~10+ min" from it. Absolute
  best case (all 13 fetches in one perfectly-overlapped wave) collapses 346.3s ->
  ~max single fetch ~56s => ceiling ~4.8 min — AND only if you ALSO collapse the
  391s serial decide/checklist, which the STATED speedup does NOT touch. Worse:
  intra-search fetch is ALREADY parallel — live_retriever.py:6437 parallel_fetch,
  max_workers band 8-14 (:6376-6382), per-host cap 4, own concurrent.futures pool.
  So a "serial fetch pole" exists ONLY cross-turn, and cross-turn fetch is
  entangled with the serial _decide loop (one query/turn, outline_agent.py:732):
  you cannot fetch gap N+1 until _decide N (downstream of fold N) picks it. Real
  achievable saving is a fraction of 4.8 min, not "several to 10+ min."

FINDING 2 — I2 (VERDICT-IDENTITY) CONCRETELY RISKED; the named guard is INSUFFICIENT:
  The stated guard "fold in canonical sorted url/candidate-key order" does NOT
  reproduce the serial baseline. _fold_in.py:167-172 dedups fetched_rows against
  workspace.existing_urls() — i.e. against the store AS MUTATED BY PRIOR TURNS.
  The serial loop drops cross-turn url-dups precisely because each turn INSERTS
  before the next turn dedups (measured W2: url-dup dropped 9/9,10/10,8/8,9/9 over
  four same-aspect turns = 36 rows). Batching N turns' rows into one fold (or
  re-sorting into a new order) means those cross-turn dups are NOT deduped against
  each other (intra-batch same-url rows both pass :168-172, get distinct ids via
  _offset_renumber, and flow into _stamp_and_delete). Extra rows can survive the
  S2/off-topic screen => DIFFERENT evidence pool => the NLI kept/dropped set can
  change. "Deterministic order" != "identical to serial." A correct guard would
  fold turn-by-turn in EXACT baseline gap order with identical incremental dedup —
  which "sort by url key" is NOT. Full-scale verdict-identity A/B remains UNPROVEN
  (prior lanes flag the small A/B "never exercised full-scale concurrency").

FINDING 3 — I3 (AGENTIC) SECONDARY RISK: to fan out you must drain multiple pending
  gaps WITHOUT re-running _decide between them (decide is downstream of each fold).
  That changes the agent's control flow / which queries fire — a behavior change,
  not a transparent parallelization.

FINDING 4 — I4 (DEADLOCK): the dedicated-pool guard IS the correct mitigation; kept
  small (3-4) and OFF the loop-default executor it avoids the futex-starvation seen
  in the 48-way run. This one invariant is plausibly satisfiable — but it does not
  rescue Findings 1-3.

FINDING 5 — I1 (COVERAGE): not threatened; same gaps fetched, no baskets dropped. OK.

BOTTOM LINE: keeps_quality = FALSE. (a) The dominant fetch pole is only 5.77 min
and already intra-search parallel, so the "10+ min" claim is physically impossible
and the real saving is marginal unless the decide/checklist serialization (the true
53% pole) is ALSO restructured. (b) The specific guard proposed ("canonical sorted
fold") does NOT guarantee I2 verdict-identity — there is a concrete cross-turn
url-dedup divergence that can change the NLI kept set, and it is unproven at 328
scale. Not adversarially safe as specified.

================================================================================
ADVERSARIAL VERIFY (subagent, 2026-07-12): "OFF-LOOP COMPOSE ON A DEDICATED EXECUTOR"
SPEEDUP = keep the shipped off-loop to_thread(compose) baseline BUT run it on a
module-owned ThreadPoolExecutor instead of the default asyncio.to_thread pool,
"to avoid contention with retrieval." CLAIMED SAVING = "the overlap with retrieval."

MEASURED / READ-CONFIRMED FACTS (outline_agent worktree, READ-ONLY):
- Pipeline is a STRICTLY SEQUENTIAL langgraph (graph_v2.py:641-675):
    plan -> search -> storm -> fetch_content -> crag_analyze
      -> plan_outline (THE react retrieval loop; run_live_retrieval wrapped in
         asyncio.to_thread at outline_agent.py:732; ~24min agentic phase)
      -> blueprint (:657 hard edge)
      -> write_one_section (THE compose phase; fan-out parallel sections :660-664)
      -> verify_one_section -> assemble -> END
  => Retrieval (plan_outline) FULLY COMPLETES before compose (write_one_section)
     starts. They are DIFFERENT graph nodes on a hard sequential edge. They NEVER
     run concurrently.
- Off-loop wrap is ALREADY the shipped baseline: multi_section_generator.py:6079
  and :6130 already do `await asyncio.to_thread(_compose_section_per_basket, ...)`
  (comment "2026-07-12 SPEED MERGE, port of 1f9da4c"). The proposed change's only
  DELTA is default-pool -> dedicated-pool.
- workers<=1 => serial byte-identical branch (verified_compose.py:2851-2854 gate,
  :2955 `if _parallel_baskets`, :2997-2999 `break`). At workers=1 _parallel_baskets
  is False => NO nested ThreadPoolExecutor is created inside compose.

VERDICT ON THE CLAIMED SAVING: the mechanism DOES NOT EXIST.
1. "moves compose off the event loop so ASYNC RETRIEVAL OVERLAPS" — FALSE. Retrieval
   is a prior, completed graph node. Nothing is retrieving during compose, so there
   is nothing for compose to overlap with. The real (small) benefit of the off-loop
   wrap is INTRA-COMPOSE section parallelism (fan_out_write / PG_MAX_PARALLEL_SECTIONS:
   keep sibling sections' async writer/verify HTTP + judge 429 backoffs unfrozen) —
   and that benefit is ALREADY delivered by the shipped baseline, not by this delta.
2. "dedicated executor to avoid CONTENTION WITH RETRIEVAL" — FALSE. Retrieval's
   to_thread calls are not in flight during compose, so the default pool is not
   shared with retrieval at that time. At workers=1 each parallel section consumes
   exactly ONE default-pool thread; a handful of sections vs a ~min(32,cpu+4) default
   pool is not contended. The dedicated-executor delta removes contention that does
   not occur. Net wall-time delta over the shipped off-loop baseline: ~0 (unmeasurable).

VERDICT ON THE 4 INVARIANTS (the change itself is harmless):
  I1 coverage      KEPT  (workers=1 serial byte-identical; no basket dropped)
  I2 faithfulness  KEPT  (byte-identical serial => verdict-identical)
  I3 agentic       KEPT  (touches compose phase only; react loop / degrade path untouched)
  I4 no-deadlock   KEPT  (workers=1 => no nested pool => the futex_wait storm cannot
                          occur; dedicated pool adds no reentrancy since compose does
                          not resubmit to it; size pool >= max_parallel_sections to
                          avoid trivial queueing). Note this is NEUTRAL, not a fix —
                          the default pool does not deadlock at workers=1 either; the
                          observed SIGKILL deadlock was the workers>1 + sem(48) path.

CONCLUSION: keeps_quality = FALSE. Not because it risks an invariant (it does not) —
it preserves all four — but because the CLAIMED WALL-TIME SAVING IS NONEXISTENT, not
merely "small": retrieval and compose are sequential graph phases with zero overlap,
and the dedicated-executor delta over the already-shipped off-loop baseline buys no
measurable time. Per the "default FALSE if the saving is marginal" rule, this fails
the "REALLY saves meaningful wall-time" half of the test. The off-loop baseline is
worth KEEPING for its intra-compose section-parallelism benefit; the dedicated-pool
addition is a safe no-op, not a speedup.

================================================================================
LANE: ADVERSARIAL VERIFY — "basket sharding + guards (a)-(d)" (subagent, 2026-07-12)
VERDICT: keeps_quality = FALSE (saving marginal; I4 unresolved; guard (c) tensions I2).
Code re-read at REAL line numbers in the live worktree (brief's line refs were stale):

CONFIRMED (fair to the proposal):
 - REDUCE is serial in ORIGINAL basket order: verified_compose.py:3525-3533
   `_mapped = list(_ex.map(_map_one_basket, section_baskets))` (blocks for ALL maps)
   then `for _cand in _mapped: _reduce_candidates(_cand)` serially. MAP (_map_one_basket
   3414-3460) reads NO seen_* state. So sharding is STRUCTURALLY verdict-safe for the
   dedup/consolidation ordering (I2 dedup-order OK), and does NOT touch coverage (I1) or
   agentic (I3). The proposal's "never parallelize the reduce" is already honored.

DISQUALIFYING / UNRESOLVED:
 1) SAVING IS MARGINAL (fails "meaningful wall-time"). Brief: retrieval ~24min of ~30+min
    end-to-end; compose is the smaller slice. Proposer's own claim: "single-digit minutes
    at best." Even an ideal compose parallelization cannot dent the ~24min agentic long
    pole. Wrong lane for the wall-time win. (Could NOT run a full 328 render to measure —
    read-only + 30min + deadlock/SIGKILL risk; reporting proposer+brief figures as stated.)

 2) I4 (no-deadlock): guards (a)-(d) are a DESIGN PROPOSAL, not implemented. Proposer
    concedes "as-attempted it hangs -> DISQUALIFIED until (a)-(d)." Real nesting confirmed:
      - _compose_section_per_basket is invoked via `await asyncio.to_thread(...)` at
        multi_section_generator.py:5476 & 5527 => runs on the LOOP DEFAULT executor
        (~min(32,cpu+4)), and sections run in parallel (PG_MAX_PARALLEL_SECTIONS), so many
        such wrappers occupy default-executor threads at once.
      - Each then opens its OWN basket pool ThreadPoolExecutor(max_workers=_basket_workers)
        at verified_compose.py:3530, and each map thread may open the INNER synth-verify pool
        ThreadPoolExecutor(max_workers=_vw) at :1851 (PG_PARALLEL_VERIFY_SYNTH>=2), each of
        which calls verify_fn -> entailment_judge -> acquire_judge_slot (shared global sem,
        default 4) -> yet another ThreadPoolExecutor(1) POST (entailment_judge.py:155-158).
      3-4 nested bounded pools + one shared global semaphore = the observed starvation wedge.

 3) GUARD (d) IS NOT CLEANLY IMPLEMENTABLE. The codebase itself documents the blocker:
    multi_section_generator.py:9529 & 9563 — "asyncio.to_thread is not cancellable, so the
    worker itself keeps running until process teardown." A per-section watchdog wall can only
    ABANDON a wedged MAP worker, not cancel it. Worse: the basket pool uses
    `with ThreadPoolExecutor(...) as _ex:` (verified_compose.py:3530) whose __exit__ calls
    shutdown(wait=True) — it will BLOCK on the wedged thread, re-hanging the section. Abandoned
    workers also keep holding the shared judge sem + default-executor slots. So (d) as a "cancel
    instead of SIGKILL" does not actually free the wedge with the current structure.

 4) GUARD (c) TENSIONS I2 (verdict-identity). The BINDING compose/entailment path acquires with
    NO timeout: entailment_judge.py:155 `with _acquire_judge_slot():`. The JudgeSlotTimeout
    degrade (judge_concurrency.py:165-176) is wired ONLY for the ADVISORY credibility judge
    (credibility_judge_caller.py:143, which is explicitly "NOT a binding gate"). Adding
    acquire_judge_slot(timeout=) to the binding entailment gate means a wedged-but-would-verify
    claim now times out => the sentence is dropped/degraded => the kept/dropped NLI set CHANGES.
    Force-freeing a slot on a BINDING verdict path is not verdict-neutral. This is the opposite
    of I2, and it is the guard the proposal leans on to prevent the hang.

 5) I2 UNPROVEN AT SCALE. The passing verdict-identity A/B "never exercised full-scale
    concurrency." No full-328 kept/dropped-NLI A/B exists. Structural serial-reduce is
    necessary but not sufficient proof; the map now realizes cross-basket in-flight judge
    concurrency the serial loop never reached, and the sem/timeout interactions (pt 4) can move
    verdicts. Must be A/B-proven byte-identical at 328 scale BEFORE adoption — not done.

BOTTOM LINE: The two guards that actually prevent the hang are the two that are unimplemented
and internally conflicted — (c) trades I2 for I4, and (d) can't cancel a non-cancellable
to_thread worker so the section join re-hangs. Combined with a saving the proposer admits is
single-digit minutes against a ~24min retrieval long pole, this does not clear the bar.
Default to keeps_quality=FALSE. (Retrieval fan-out — LANE audit idea #1 — is the correct
lane for real wall-time; compose sharding is at best a small, hard-to-make-safe secondary.)

================================================================================
LANE: ADVERSARIAL VERIFY of SPEEDUP R3  (subagent, 2026-07-12)
PROPOSAL: (a) _decide reasoning_effort high->medium; (b) smaller reasoning_max_tokens;
          (c) lower PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS from 131072.
CLAIM: ~30-90s saved. VERDICT: keeps_quality = FALSE (breaks I2; risks I1/I3; saving marginal).

CODE ANCHORS (READ-ONLY, outline_agent):
  - _decide: outline_agent.py:1141-1248. Call at :1218-1228:
      generate_structured(..., reasoning_enabled=True, reasoning_effort="high",
      reasoning_max_tokens=_reasoning_max_tokens()[=32768], max_tokens=PG_OUTLINE_DECIDE_MAX_TOKENS[=131072]),
      wrapped in wait_for(PG_OUTLINE_DECIDE_WALL_SECONDS=660).
  - reasoning_max_tokens is a SHARED knob (_reasoning_max_tokens, :180-181, PG_OUTLINE_REASONING_MAX_TOKENS
      default 32768) used by decide AND _run_checklist AND query_derive AND the seed _call_outline.
      Lowering it is GLOBAL, not decide-only.
  - query_derive: :674-709. max_tokens=PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS (131072), content is ONE LINE;
      ANY exception fail-opens to derived="" -> query=raw aspect_text (:699-709).
  - _decide exception handling: caught at :1888-1892 -> BREAKS the loop early (does NOT degrade-to-seed,
      cp4 stays "agentic") -> pending gaps left UNFILLED -> fewer baskets. Outer wait_for degrade at :2054-2075.

MEASURED (logs/step4_route_all_compose.log, the clean 329-basket run, 1449.7s total):
  All 24 _decide (structured:ReactDecision) calls, dur / reasoning-tokens:
    1.5/142  2.8/342  3.0/468  4.8/652  5.2/712  4.4/603  8.5/817  7.1/901  6.1/1010
    6.5/911  3.0/335  12.5/1678 12.8/1862 8.0/1002 6.9/810 9.4/1281 6.9/922 5.9/778
    7.7/1142 6.2/605  13.4/1894 11.1/1426 10.1/1300 6.3/491
  SUM of all 24 decides = ~170s (11.7% of 1449.7s). MAX reasoning per call = 1894 tokens.
  query_derive calls (generate, content 5-140 bytes) = ~1-3s each, reasoning ~200-500 tok.
  The 62s decide the proposal cites is NOT in this clean run (a bad-tail post-bounce outlier).

WHY IT FAILS THE INVARIANTS:
  I2 (FAITHFULNESS verdict-identity) — DIRECT VIOLATION, admitted by the proposal's own RISK I2.
    _decide's reasoning IS the routing deliberation that picks which gap to search and (via
    query_derive) what query string. effort high->medium changes that deliberation -> different
    tool/gap chosen -> DIFFERENT search_more_evidence queries -> DIFFERENT fetched URLs -> DIFFERENT
    evidence pool -> DIFFERENT NLI kept/dropped set. This is NOT verdict-identical, full stop.
    "decide is routing not faithfulness" is a category error: routing selects the evidence that
    faithfulness is computed over. The gate stays intact but its INPUT changes -> verdicts change.

  (b) smaller reasoning_max_tokens — REDUNDANT on happy path, DANGEROUS on dense corpus.
    Happy path: reasoning already terminates at 142-1894 tokens, FAR below the 32768 ceiling, so
    lowering the ceiling saves ~0s for 23 of 24 calls. It only "bites" when it truncates. The
    code's own header (:110-134) documents this ceiling was RAISED precisely because glm-5.2's
    unbounded reasoning prelude hit ~21k tokens (84453 chars) on the dense DRB-72 AI-labor corpus
    and threw ReasoningFirstTruncationError. Setting reasoning_max_tokens "smaller" re-arms that
    crash. Consequences on a dense corpus:
      - decide truncation -> caught :1888 -> loop BREAKS early -> pending gaps UNFILLED ->
        FEWER baskets rendered -> I1 (deep coverage) VIOLATION (and quieter loss of agentic depth).
      - query_derive truncation -> fail-open to raw aspect (:699) -> different query -> I2.
      - checklist truncation -> fail-open retry at 2x budget -> ADDS latency (anti-speedup).
    Because the knob is shared, you cannot lower it for decide alone without also endangering
    checklist/query_derive/seed.

  (c) lower PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS — ~ZERO real saving, only downside.
    This caps TOTAL content tokens; the derived query is ONE LINE (5-140 bytes measured). Output
    terminates naturally at ~50 tokens; a 131072 ceiling is never approached, so lowering it saves
    no wall-time. If lowered far enough to truncate the reasoning prelude, derive fail-opens to the
    raw aspect string -> different query -> I2. Strictly no-upside, possible-downside.

  I3 (cp4_used=agentic) — indirect. A decide truncation ends the loop via :1892 (cp4 stays
    "agentic") but with unfilled gaps = degraded coverage; a checklist/outer-wall path (:2061) flips
    cp4 to "agentic-degraded-seed". Either way quality drops.

  I4 (no deadlock) — R3 does not touch concurrency, so it neither causes nor cures the deadlock.

REAL SAVING (measured, not estimated): MARGINAL and SPECULATIVE.
  Best case, effort high->medium shaves reasoning on 24 calls whose reasoning is ALREADY tiny
  (mostly <1k tokens) -> plausibly a few s/call, i.e. tens of seconds, against a 1449.7s run
  (~2-4%) where fetch/retrieval is 50.8% and compose 35.5%. Sub-lever (b) saves 0s on the happy
  path; sub-lever (c) saves ~0s always. The cited 62s single decide is a bad-tail outlier that
  medium-effort would not reliably eliminate. Net: a small, unreliable saving purchased at the
  cost of a non-verdict-identical evidence pool.

BOTTOM LINE: R3 is DISQUALIFIED. It is verdict-CHANGING by construction (I2), risks premature
  loop-exit/coverage loss and truncation-degrade on dense corpora (I1/I3), and its measured saving
  is marginal (~2-4% at best, ~0 for two of its three sub-levers). "Gate behind full-scale A/B" does
  not rescue it: the A/B would MEASURE the verdict drift, and any non-identical kept/dropped set
  fails I2 regardless. Not a safe speedup.

================================================================================
LANE: R2 ADVERSARIAL VERDICT  (subagent, 2026-07-12)  --  keeps_quality = FALSE
SPEEDUP R2: "cache Serper query->URL-set; when a derived query's candidate URL set is
>=~90% already in ev_store, SKIP the fetch and route the aspect to UNFILLED+disclosed."
CLAIMED SAVING: ~2-3 min.  READ-ONLY audit; no full run measured (stated where unverified).

CODE ANCHORS READ (outline_agent worktree, READ-ONLY):
 - fold-in seam: outline/_fold_in.py:150 fold_in_fetched_rows -> url-dedup (:167-173,
   dedup ONLY on source_url string vs workspace.existing_urls()) -> _offset_renumber
   (:31, hard id-collision assert) -> _stamp_and_delete (:59, chrome + topic-judge) ->
   insert survivors into ev_store.
 - retrieval tool: outline/outline_toolkit.py:412 _tool_fetch_url (ALREADY skips a URL
   already in existing_urls at :434) ; outline_agent.py:645 _tool_search_more_evidence
   -> derive query via LLM (:692) -> run_live_retrieval in to_thread (:732) -> merge ->
   fold_in (:754). Disclosure line :761-766 reports "url-dup dropped N, kept N".
 - gap ledger: outline_agent.py:403 mark_retry_or_unfilled — PENDING while attempts<cap,
   else UNFILLED+disclosed (this is the NORMAL terminal state R2 wants to reach early).
 - run_live_retrieval signature: live_retriever.py:5405 — takes seed_urls but has NO
   param for the caller's already-held ev_store URL set. It therefore re-fetches
   already-held URLs; fold_in url-dups them post-hoc. => the re-fetch WASTE R2 targets is
   REAL. But the dedup is purely on URL string; a URL already in ev_store is ALWAYS
   dropped regardless of fetched content.

WHY IT FAILS THE INVARIANTS (the load-bearing flaw is the ~90% threshold):

I2 FAITHFULNESS VERDICT-IDENTITY  -- VIOLATED at 90%.
  At >=90% overlap, up to ~10% of candidate URLs are GENUINELY NEW (not in ev_store).
  Skipping the whole fetch discards them. Any new URL whose fetched row would SURVIVE
  fold-in (not url-dup, not chrome, not off-topic) would have entered ev_store and been
  eligible for strict_verify/NLI. Suppressing it CHANGES the evidence pool => can change
  the kept/dropped NLI verdict SET. The brief requires speed to be VERDICT-IDENTICAL.
  R2's own justification ("no new rows => no NLI-set change") is TRUE ONLY at 100%
  overlap, FALSE at 90%. The cited evidence (04:20-04:22 url-dup 9/9,10/10,8/8,9/9 =>
  kept=0) is exactly the 100%-overlap case and does NOT support the 90% generalization.

I1 DEEP COVERAGE (328/329)  -- can be VIOLATED at 90%, same root cause.
  A basket becomes renderable when it holds >=1 surviving row. If the skipped ~10% new
  URLs contained the only row for some basket, that basket goes unrendered => coverage
  drops below 328. R2's guard ("baskets are pre-existing clusters, we only stop
  re-fetching pooled evidence") is only correct when the candidate set is 100% pooled;
  at 90% it can starve a basket. This is a coverage-dropping shortcut, not a free win.

I3 AGENTIC (cp4_used=agentic)  -- not directly tripped, but an erosion vector.
  Routing to UNFILLED is the normal disclosed terminal state and does NOT set
  cp4_used=agentic-degraded-seed (that flag is exception/timeout-only, per prior lane
  :2054/:2080). So R2 does not directly flip the flag. HOWEVER, aggressively converting
  fillable aspects to UNFILLED early is a quiet nudge toward the "seed+partial under
  load" degradation the brief explicitly warns about (fewer aspects actually retrieved).

I4 NO DEADLOCK  -- NOT threatened. R2 removes work; it adds no concurrency. Clean here.

SAVING REALITY  -- marginal / unverified as stated.
  - R2 must still fire the Serper search to KNOW the candidate URL set, and still pays the
    per-call derive-query LLM (:692). It saves only the FETCH+classify slice, not search.
  - The "~2-3 min" figure equals the SINGLE observed 179s pathological stretch (one aspect,
    'impacts across various industries', 4 repeats). It is NOT a measured whole-run
    aggregate. I could not run the full 328-basket render, so the run-wide saving is
    UNVERIFIED. Extrapolating one stretch to a whole-run number is optimistic.

THE ONLY VERDICT-SAFE VARIANT (which is NOT what R2 proposes):
  (a) 100%-overlap breaker ONLY: skip iff EVERY candidate URL (after the same url-dedup
      rule) is already in ev_store — then kept=0 is guaranteed and skipping is truly
      verdict-identical. This is a strict subset of R2's 90% and reclaims strictly less
      time. OR
  (b) per-URL fetch skip: plumb existing_urls into run_live_retrieval so already-held URLs
      are not re-fetched (they were destined for url-dup drop anyway) while genuinely-new
      URLs in the SAME query are still fetched. Verdict-identical AND keeps coverage.
  Both are safe; NEITHER is R2 as written. Note (b) requires editing live_retriever.py
  (:5405 has no held-url param) — forbidden here (live wheel in outline_agent).

BOTTOM LINE: R2 as specified (>=~90% aspect-level all-or-nothing skip) is NOT
verdict-identical (I2) and can drop a basket (I1); its saving is a single-stretch
observation, not a measured aggregate. keeps_quality = FALSE. The 100%-overlap / per-URL
variant is the salvageable idea, but it is a different, smaller, and (for per-URL)
wheel-editing change.

---

## ADVERSARIAL VERDICT — "reduce drop-driven waste (tighter draft prompt + skip non-converging regen)" (2026-07-12)

CLAIM UNDER TEST: (a) tighten per-sentence span grounding in the DRAFT prompt so fewer first-pass
drafts fail; (b) SKIP the whole-section regen when it "historically converges to verified~=0".
CLAIMED SAVING: ~130-180s of a ~514s compose phase by cutting non-converging regens + repair round-trips.
VERDICT: **keeps_quality = FALSE.** Part (a) is NOT verdict-identical (violates I2). Part (b) cannot be
done without a predictor, and the only available signal is exactly the coverage-rescue case (risks I1/I3).
Saving is unverified and, in the only invariant-legal case, ~0.

CODE-VERIFIED ANCHORS (compose_fix worktree, READ-ONLY):
- Regen decision: multi_section_generator.py:5779-5786 — regen fires deterministically iff
  `post_filter_fraction < min_kept_fraction` (DEFAULT_VERIFIER_PASS_THRESHOLD=0.40, generator.py:56)
  AND report.total_in>0.
- Regen ADOPTION gate: :5833 `if len(report2_kept_after_m41c) > post_filter_kept:` — the retry result
  is kept ONLY if it produces STRICTLY MORE kept sentences than the first pass; otherwise the first pass
  survives. So a regen that yields 0 is already DISCARDED — but the LLM call was already spent.
- Regen is a DIFFERENT, non-deterministic sample: :3614-3654 tighter_retry injects a HARD OUTPUT
  CONTRACT (anti-CoT, [ev_XXX]-per-sentence, few-shot) and :3693-3699 drops temperature 0.3 -> 0.1.
  It is not a replay of the first draft; it is a purpose-built rescue attempt.
- History comment :3688-3692: the HARD CONTRACT was once STRIPPED after Smoke #3 saw "zero
  verified-sentence lift in 12 retries" at temp 0.3, then RE-ADDED with cold temp because it DID lift.
  I.e. the team already empirically tuned regen specifically so it stops being a zero-yield waste. The
  proposal would undo a fix the pipeline already earned.

WHY PART (a) VIOLATES I2 (faithfulness verdict-identity):
- The invariant is "kept/dropped NLI verdict set unchanged; speed must be verdict-identical." Changing
  the DRAFT prompt changes the draft TEXT -> different sentences are fed to strict_verify -> a DIFFERENT
  set of NLI verdicts. That is by definition NOT verdict-identical. The proposer's own reframe ("change
  only what is FED to strict_verify") concedes it changes the gate's INPUT, which changes verdicts.
- It is also an UNPROVEN quality experiment, not a speedup: "tighter grounding" may raise OR lower yield;
  a stricter contract can suppress groundable-but-differently-phrased sentences and REDUCE coverage (I1).
  It cannot be validated without a full 328-basket A/B, and any prompt A/B that changes even one verdict
  fails the identity bar. It also does not remove any LLM call by itself (same draft call); the alleged
  saving is a downstream, probabilistic "maybe fewer regens."

WHY PART (b) CANNOT BE DONE INVARIANT-SAFELY:
- There is NO historical-convergence oracle in this pipeline. Retrieval is live/agentic, so evidence
  pools differ every run; a section that yielded 0 last time can yield >0 this time. Cross-run "skip"
  memory is a coverage gamble, not a proven no-op.
- The ONLY signal available at decision time is the first-pass result. But first-pass verified=0 (the
  worst-case "Automation, Tasks..." section, verified=0 dropped=16) is EXACTLY the case where the regen
  is the sole COVERAGE-RESCUE path: with 0 first-pass kept, the :5833 gate adopts ANY regen with >=1
  kept. Skipping regen on low/zero first-pass yield therefore DROPS sections the regen would have
  rescued -> renders < 328/329 (violates I1) and pushes the section to the gap-stub/dropped path
  (pressure on I3). You cannot distinguish, a priori, a rescuable section from an unrescuable one — the
  proposal trades guaranteed coverage for a probabilistic time saving.
- The regen is stochastic + cold-temp + different-contract (above), so it is genuinely a fresh draw;
  "it converged to 0 once" does not prove "it converges to 0 always." A truly-safe skip would require
  proving the retry is a deterministic no-op, which it provably is NOT.

SAVING REALITY:
- The 130-180s / 514s figure is the proposer's estimate; it is NOT independently measurable here — a full
  328-basket compose is expensive and OVERNIGHT_PROGRESS records root-owned run_s5_i3.py jobs distorting
  compose timing. UNVERIFIED.
- Structurally the regen is ONE extra _call_section per regenerated section (2 of 8 in the cited run) and
  the repair loop is already bounded (sentence_repair MAX_PER_SECTION cap; verified_compose
  _writer_repair_max default 2). These are real costs, but the only invariant-safe way to cut them is to
  make sections pass on the FIRST draft — which is part (a), the non-verdict-identical prompt change. So
  the two halves collapse into one disqualified lever.

BOTTOM LINE: default-FALSE on two independent counts — (a) is not verdict-identical (I2) and is an
unmeasured quality change; (b) has no safe skip signal and its only trigger is the coverage-rescue case
(I1/I3). The saving is unverified and, restricted to a provably-safe no-op, ~0.

================================================================================
ADVERSARIAL VERDICT: "Raise section-level compose concurrency 5 -> 8..16"
(subagent, 2026-07-12; READ-ONLY; outline_agent worktree)
VERDICT: keeps_quality = FALSE (knob misidentified; safe variant saving is marginal,
claimed-saving variant threatens I3/I1).

KNOB MISIDENTIFICATION (root defect in the proposal):
  There are TWO nested compose concurrency caps, not one:
   (A) SECTION semaphore = the real "section-level compose concurrency."
       multi_section_generator.py:10545-10556  _section_concurrency = max_parallel_sections
       DEFAULT = 3 (fn default :9555), env knob PG_PARALLEL_SECTIONS. asyncio.Semaphore.
   (B) GLOBAL LLM semaphore = PG_MAX_CONCURRENT_LLM, DEFAULT = 5
       llm_provider.py:79,124-157 ("Concurrency semaphore (re)initialized: max=5").
       "across ALL pipeline nodes." EVERY OpenRouter call acquires it
       (openrouter_client.py:1889-1891 get_semaphore()).
  The proposal's evidence ('max=5', 38x) is knob (B), the GLOBAL cap — NOT section concurrency.
  Proof it is the AGENTIC/OUTLINE phase, not compose: in logs/step4_route_all_compose.log
  all 19 "max=5" re-inits (04:10:47->04:25:00) interleave with update_outline / auto-assign /
  topic_gate (the fresh-loop-per-turn react loop). Re-init stops at 04:25; the compose/section-
  write phase then runs in ONE persistent loop (no more re-inits). elapsed_seconds=1449.7 total,
  outline_sections=8, kept=8, dropped=0.  => "section concurrency" is at 3, not 5.

WHY THE SAFE VARIANT (raise ONLY PG_PARALLEL_SECTIONS 3->8/12) CANNOT DELIVER 2-4 min:
  - Section drafts still contend on the GLOBAL LLM sem=5 (B). With sem(B)=5 unchanged, effective
    LLM concurrency is capped at 5 no matter how high PG_PARALLEL_SECTIONS goes. Going effective
    3 -> 5 on an 8-section report is ~1 extra wave on the draft step only: order tens of seconds,
    NOT 2-4 min.
  - Saving is also bounded by section COUNT (here 8; runs often have 4-7). sem>sections is a no-op.
  - Compose here is verify/repair-heavy (65 verified + 68 dropped = 133 NLI checks + regens). NLI
    entailment is capped SEPARATELY at PG_SIDE_JUDGE_MAX_CONCURRENCY=4 (judge_concurrency.py),
    untouched by either generation knob. If compose is verify-bound, generation concurrency buys ~0.

WHY THE VARIANT THAT COULD HIT 2-4 min BREAKS INVARIANTS:
  To approach the claimed saving you must ALSO raise the GLOBAL sem (B). But (B) is global — it
  cannot be scoped to compose; it also governs the ~14-min AGENTIC outline/retrieval phase.
  - I3 (degrade): brief-documented "outline can DEGRADE to seed+partial under load"; more in-flight
    LLM calls per turn => more 429/timeout => higher degrade-to-seed => cp4_used != agentic. THREAT.
  - I1 (coverage): 429/timeout on section calls => _TRANSIENT_SECTION_FAILURES => gap-stub / dropped
    sections. THREAT.

INVARIANT CHECK, SAFE VARIANT (PG_PARALLEL_SECTIONS only, sem(B) left at 5):
  - I2 verdict-identity: OK BY CONSTRUCTION. Code comment 10534-10544: "each section is still
    generated and verified INDEPENDENTLY and IDENTICALLY ... results merged back in original plans
    order ... output unchanged. The knob is a CONCURRENCY bound, never a section TARGET." strict_verify
    per section unchanged.
  - I4 deadlock: OK for THIS knob. It is an asyncio.Semaphore on a single cooperative loop — NOT the
    PG_COMPOSE_BASKET_WORKERS thread-pool that futex-deadlocked at 48-way. Different mechanism.
  - I1/I3: OK (compose-phase only; does not touch the agentic outline loop).
  => The SAFE variant keeps all 4 invariants but its saving is MARGINAL (~tens of seconds), far below
     the 2-4 min claim, because global sem(B)=5 and side-judge=4 are the true binding caps.

MEASUREMENT HONESTY: I did NOT run a 5->12 scaling A/B — that needs a full ~24-min paid render
(read-only + no-spend constraint). The 2-4 min figure is UNVERIFIED and, from the nested-cap
structure above, structurally implausible for the verdict-safe knob in isolation.

BOTTOM LINE: FALSE. As framed the proposal targets the wrong "5" (global cap, not section cap=3).
The verdict-safe section-only knob is bounded by global sem=5 / side-judge=4 to a marginal saving;
reaching the claimed 2-4 min requires lifting the global LLM cap, which endangers I3 (degrade) and
I1 (coverage) in the dominant agentic phase. Default-to-FALSE stands.

================================================================================
R1 ADVERSARIAL VERDICT (subagent, 2026-07-12) — "batch-fetch N PENDING gaps
concurrently, fold serial in sorted order, run after_fold checklist ONCE/batch"
VERDICT: keeps_quality = FALSE. Fails I2 (verdict-identity), premise inflated,
I4 unretired. Measured from logs/step4_route_all_compose.log (the deep render).

CODE ANCHORS (READ-ONLY):
  - outline_agent.py:659-660 DOCSTRING invariant: search_more_evidence is "One
    retrieval in flight at a time (§8.4 — this coroutine is awaited, NEVER fired
    concurrently by the driver)." R1 directly violates a documented design law.
  - The after_fold checklist at :1862 is NOT a redundant between-fetch step. It is
    (a) the CONVERGENCE gate — its output decides mark_complete (:1873) vs
    mark_retry_or_unfilled (:1867) for the just-fetched gap — AND (b) gap DETECTOR
    #1 (:1252) that MINTS NEW gaps mid-loop. Dropping it to once/batch changes both.
  - fold-in (_fold_in.py) url-dedup(:167-173) + next_ev_offset renumber(:175-177):
    order-sensitive. R1 keeps fold serial/sorted — that part is defensible — but
    it does NOT address the checklist path-dependence, which is the real threat.
  - run_live_retrieval ALREADY fans out URL fetch/enrich over its OWN
    ThreadPoolExecutor internally (live_retriever.py:2548-2555 oa-enrich-batch,
    :6363-6439 fetch workers scale with candidate count). Each search call is
    already internally parallel across ~10 URLs.

I2 FAITHFULNESS — VIOLATED (not merely at-risk). The 13 turns are NOT 13
independent gaps that can be pre-batched. Traced from the log, the loop is a
PATH-DEPENDENT convergence, not a fan-out:
  - The after_fold gap set MUTATES every round: 2->3->3->2->2->3->3 gaps named,
    and the aspect "explicitly defining inclusion criteria for high-quality
    English-language journal articles" is FIRST MINTED at 04:18:10 (turn ~6) — it
    did NOT exist at seed, so it is uncomputable in any seed-time batch.
  - 1-2 STICKY aspects ("contextualizing AI as a driver of the 4th Industrial
    Revolution", "impacts across various industries") re-fire in nearly EVERY
    after_fold checklist. Turns ~8-11 (04:20:01/04:20:36/04:21:08/04:21:59) all
    return kept=0 (url-dup dropped 9/10/8/9) — pure serial-dedup churn that only
    exists BECAUSE the checklist keeps re-naming the same aspect against the
    incrementally-grown pool. Batching + one checklist changes these decisions.
  Because the SET of queries fired is produced by the serial checklist sequence,
  a batch/one-checklist variant fires a DIFFERENT query set -> folds a DIFFERENT
  URL set -> DIFFERENT ev_store -> DIFFERENT strict_verify+NLI kept/dropped set.
  The proposal's own claim ("search_more_evidence only ADDS rows, downstream set
  identical") is FALSE: the rows added are chosen by the loop it is altering. The
  mandated full-328 A/B verdict-identity proof has NOT been run — and the trace
  predicts it would FAIL.

SAVING PREMISE — INFLATED. Loop 04:13:05->04:25:22 = 737s. Sum of the 13
"in Xs" fetch stamps = 34.1+20.5+14.4+22.3+24.7+38.6+56.3+17.0+22.3+16.9+18.0
+48.5+12.7 = 346.3s fetch; ~390.7s is non-fetch (decide + ~11 checklists +
topic-judge). But:
  - Fetch is ALREADY internally parallel (per-call latency 12-56s IS the parallel
    fetch of a ~10-URL batch). A 4-wide OUTER fan-out runs 4 already-parallel
    batches at once for marginal wall gain while 4x-ing thread pressure.
  - The ~390s non-fetch is decide+checklist LLM calls. R1 "saves" here ONLY by
    dropping checklists — which is exactly the convergence/discovery change that
    breaks I2. You cannot bank that time without changing the evidence pool.
  - At any instant only 2-4 gaps are PENDING and they are largely the SAME
    re-judged aspects; effective parallel width is low and rounds are sequentially
    dependent. The "13 turns -> 4-5 rounds" model does not match the trace.

I4 DEADLOCK — UNRETIRED. search_more_evidence nests to_thread(run_live_retrieval)
:732 AND _stamp_and_delete nests to_thread(classify_topic_relevance) _fold_in.py:116
on the SHARED loop-default executor; run_live_retrieval then opens its OWN internal
pools. Running N search calls concurrently multiplies BOTH the outer shared-pool
to_thread wrappers and the inner pools — the same nested-shared-executor category
that SIGKILL-deadlocked at 328 scale. R1's "dedicated executor for fetches" does
NOT cover these nested to_thread calls (they live inside READ-ONLY code). Risk is
LOWER than compose (outline runs once/report, N=3-4) but is UNPROVEN at full scale.

I3 AGENTIC — degraded in spirit, flag survives conditionally. Batching bypasses the
per-turn LLM _decide (:1141) that IS the react agency; cp4_used stays "agentic"
(:2080) only if nothing raises. A new concurrent gather adds exception surface; if
it escapes to the :2054 wait_for it trips degrade_to_seed (cp4_used=
"agentic-degraded-seed"). Containable but a net-new risk on a phase that today
completed clean (this run: NO agent_run_aborted_degrade_to_seed; only benign
per-source down-weight/label warnings at :2094/:2274).

BOTTOM LINE: R1 buys, at best, a slice of the 346s fetch that is already largely
parallelized internally, and can only touch the 390s non-fetch by dropping the
after_fold checklist — which is the convergence+discovery engine, so doing so is
NOT verdict-identical. Real defensible saving is marginal and comes bundled with a
concrete I2 break and an unproven I4. keeps_quality = FALSE.

---

# LANE: COMPOSE DEADLOCK ROOT-CAUSE (added 2026-07-12)

## TL;DR
The 328-basket freeze is NOT a re-entrant judge-slot acquire and NOT a cross-async-boundary
`asyncio.Semaphore` bug. The entailment client is thread-local (safe) and the compose per-basket
verify is SERIAL (no nested acquire). The actual lock is **unclamped, multiplicative thread ×
shared-threading-semaphore OVER-SUBSCRIPTION with no timeout/no-wall backstop**:

- `_compose_basket_workers()` (verified_compose.py:232-243) returns `PG_COMPOSE_BASKET_WORKERS`
  verbatim with **NO global clamp**. It is applied **per section**, so the live basket-worker
  thread count = `PG_PARALLEL_SECTIONS` (multi_section_generator.py:10545-10556, default 3, env-
  overridable) × `PG_COMPOSE_BASKET_WORKERS`. Each of those threads, per NLI POST, ALSO spawns an
  inner `ThreadPoolExecutor(max_workers=1)` (entailment_judge.py:156) → ~2× thread amplification.
- Every one of those threads contends for ONE process-global `threading.BoundedSemaphore`
  (`acquire_judge_slot`, judge_concurrency.py:137-182; the run set it to 48).
- The BINDING entailment acquire is `with _acquire_judge_slot():` with **NO timeout**
  (entailment_judge.py:155) — the ONLY judge consumer with no backstop. The credibility judge uses
  `timeout=slot_wait` (credibility_judge_caller.py:143) and the credibility scorer pool has a hard
  `as_completed(timeout=pool_wall)` wall (credibility_skill.py:429). The compose path has neither.
- The basket-map JOIN `list(ThreadPoolExecutor(_basket_workers).map(_map_one_basket, section_baskets))`
  (verified_compose.py:2992) and the outer `asyncio.to_thread(_compose_section_per_basket)` wrap
  (multi_section_generator.py:6079/6130) also have **no wall**. So once the judge semaphore is
  over-subscribed by sections×workers threads (plus GIL/futex thrash from the 2× amplified thread
  population on a 128-core box where the default `asyncio.to_thread` executor is 32), there is no
  timeout, no wall, and no escape valve — saturation becomes an unrecoverable wedge (the observed
  "19/20 in futex_wait, 0 progress 8.8 min, SIGKILL").

## What it is NOT (ruled out by reading, so we don't fix the wrong thing)
1. NOT a re-entrant BoundedSemaphore acquire. `_verify_all_sentences_synth` in outline_agent is a
   plain SERIAL for-loop (verified_compose.py:1585-1611) — no PG_PARALLEL_VERIFY_SYNTH nested pool was
   ported. Verify holds at most one slot at a time and releases it per POST. The credibility pass
   (the other judge-slot consumer) runs at multi_section_generator.py:10190, textually and in
   execution BEFORE Stage-2 section generation (10534) — so it does not overlap/hold slots during
   compose. No single thread holds slot#1 while blocking on slot#2 ⇒ no classic re-entrant deadlock.
2. NOT a cross-async-boundary semaphore bug. The async `get_semaphore()` (llm_provider.py:124, an
   `asyncio.Semaphore` bound to the loop) is used only by the async `OpenRouterClient._call`. The
   off-loop compose uses the SYNC entailment judge (thread-local httpx client, no loop hop:
   entailment_judge.py:139-183 uses `client.post` on a worker thread, never
   `run_coroutine_threadsafe`). So the asyncio semaphore is never acquired across the off-loop
   boundary.
3. NOT a shared-client close-while-in-flight race. entailment_judge.py:672-710 gives each worker
   thread its OWN `threading.local()` client; `client.close()` on the 150s total-deadline path only
   touches the calling thread's client.

## Why compose_fix gated parallel-verify OFF by default (documented, and it is NOT "deadlock")
compose_fix verified_compose.py:1818-1826: `PG_PARALLEL_VERIFY_SYNTH` defaults OFF because the
record/replay A/B certifier **cannot byte-certify the multi-basket compose path** — that path is
non-deterministic run-to-run EVEN fully serial (concurrent writer/section scheduling reorders a
downstream accumulator; the report sha bistably flips at PYTHONHASHSEED=0 independent of any verify-
parallelism). The loop is proven order-preserving in isolation, so it is faithfulness-neutral by
construction, but stays OPT-IN until the certifier's own non-determinism is resolved. i.e. the OFF-
default is a CERTIFIABILITY guard, not a deadlock guard — which is exactly why the small verdict-
identity A/B passed and never exercised full-scale concurrency, and why the deadlock was latent.
Note: outline_agent's `PG_COMPOSE_BASKET_WORKERS` defaults 1 (SERIAL) for the same reason —
verified_compose.py:233. The port kept the safe default; the deadlock only appears when a run lifts it.

## Safe subset that CANNOT deadlock
A) OFF-LOOP-ONLY (RECOMMENDED): keep `asyncio.to_thread(_compose_section_per_basket)` with
   `PG_COMPOSE_BASKET_WORKERS=1`. This is the piece the lane brief already certified verdict-safe.
   It frees the event loop (sibling sections + writer HTTP callbacks + judge 429 backoffs stop being
   frozen on the main loop) and gives real SECTION-level parallelism (PG_PARALLEL_SECTIONS), with
   exactly ONE judge-slot consumer per section-thread — no second, unclamped, semaphore-contending
   tier. Cannot deadlock: peak judge demand = active_sections, trivially < cap; no re-entrancy; each
   POST is bounded by the 150s total-deadline; nothing waits forever.
B) BASKET-WORKERS > 1 made deadlock-proof: two structural guarantees, both verdict-identical (they
   change only HOW MANY baskets compose at once; the REDUCE is serial + order-preserving, so
   kept/dropped and dedup are byte-identical):
   (i) CLAMP demand to supply in `_compose_basket_workers()` so the shared judge semaphore is NEVER
       over-subscribed:
         judge_cap = resolve_max_concurrency() (0/unbounded => no clamp)
         sections  = max(1, PG_PARALLEL_SECTIONS or max_parallel_sections)
         return max(1, min(raw, judge_cap // sections))
       This guarantees sections × basket_workers ≤ judge_cap ⇒ no thread ever parks on an exhausted-
       forever semaphore ⇒ the no-timeout entailment acquire can no longer wedge.
   (ii) Set PG_SIDE_JUDGE_MAX_CONCURRENCY ≥ sections × basket_workers explicitly for the run (belt-
        and-braces with (i)), and keep active_sections small enough that sections × basket_workers ×
        2 (the inner TPE(1) amplification) stays well under the default `asyncio.to_thread` executor
        (32 on this 128-core box) to avoid GIL/futex thrash.

## The exact fix (minimal, verdict-identical)
1. verified_compose.py `_compose_basket_workers()` (:232): add the demand-to-supply clamp above so
   `sections × basket_workers ≤ judge_cap`. One-function change; default (workers=1) path untouched.
2. Ship with PG_COMPOSE_BASKET_WORKERS=1 (off-loop-only) as the default speedup until (1) lands.
3. Do NOT "fix" this by giving the entailment acquire a fail-closed timeout: on JudgeSlotTimeout the
   entailment judge would emit the fail-closed ('ENTAILED','judge_error') sentinel that consumers
   DROP — which would CHANGE the kept/dropped verdict set and violate faithfulness invariant #2. The
   clamp is the verdict-safe lever (it never drops a claim; it only serializes baskets).

## Measurement honesty
I did NOT run a live 328-basket repro: it is the 30-min deep render whose failure mode IS the
deadlock, and the lane is READ-ONLY on a live wheel. Findings above are from static reading of the
exact ported code (file:line cited). The one number I measured on this box:
`os.cpu_count()=128` ⇒ default `asyncio.to_thread` executor = min(32,132)=32 threads (so the observed
"19/20" dump is a py-spy snapshot of a contended pool / GIL-wait set, not the default-executor bound).

---

## ADVERSARIAL VERDICT — "certifiability-guard" analysis note (2026-07-12)

PROPOSED "SPEEDUP": no code change; a documentation claim that compose_fix gated
`PG_PARALLEL_VERIFY_SYNTH` OFF-by-default as a CERTIFIABILITY guard (record/replay A/B cannot
byte-certify the run-to-run-nondeterministic multi-basket path), NOT a deadlock guard.

VERDICT: keeps_quality = FALSE.
Not because it violates an invariant (it does not — zero code change), but because it is NOT a
speedup: CLAIMED SAVING is undefined and the real wall-time saving is ~0. It is a correct
diagnostic note, not a performance change.

Evidence claims — ALL VERIFIED against the exact ported code:
- compose_fix verified_compose.py:1818-1826 — the gate comment literally states the rationale is
  "the record/replay A/B certifier cannot byte-certify this multi-basket compose path because the
  path is non-deterministic run-to-run EVEN fully serial ... it is faithfulness-neutral by
  construction, but it stays OPT-IN until the certifier's own non-determinism is resolved."
  => CERTIFIABILITY guard, confirmed verbatim. Not a deadlock guard.
- outline_agent verified_compose.py:1585-1611 — `_verify_all_sentences_synth` is a plain SERIAL
  for-loop; `PG_PARALLEL_VERIFY_SYNTH` appears 0 times in the whole file (grep -c = 0). The nested
  synth-verify pool was NEVER ported. => NOT re-entrant; verify holds <=1 judge slot at a time.
- No `run_coroutine_threadsafe` in outline_agent verified_compose.py / entailment_judge.py (grep
  empty). async `get_semaphore` (llm_provider.py:124) is `asyncio.Semaphore`, loop-bound, used only
  by the async client. => the off-loop SYNC entailment judge does not cross the async boundary.
- entailment_judge.py:680-710 — each worker gets its OWN `threading.local()` httpx client; rebuild
  touches only the calling thread's client. => no shared-client close race.

WHY IT SAVES NO MEANINGFUL WALL-TIME (the decisive point):
1. Analysis-only. Renders 0 baskets faster by itself.
2. It does not even UNLOCK a speedup. The synth-verify pool is (a) not ported and (b) the wrong
   lever: the established profile says AGENTIC RETRIEVAL (~24 min) dominates and COMPOSE is the
   smaller slice; per-sentence verify is a sub-slice of compose. Parallelizing it cannot move the
   ~30-min end-to-end pole.
3. The actual full-scale DEADLOCK was in a DIFFERENT mechanism — `PG_COMPOSE_BASKET_WORKERS`
   (verified_compose.py:232, 2846) + semaphore(48) basket-level pool — which this note neither
   touches nor fixes. Correctly diagnosing "verify is not the deadlock source" does not remove the
   basket-pool deadlock, so it does not make the parallel path safe to ship.

NET: the note is technically ACCURATE and useful (it correctly warns against a mis-fix that would
relax the faithfulness gate), and it keeps all 4 invariants trivially by changing nothing — but it
is not a speedup. Real saving ~0. keeps_quality=FALSE.

================================================================================
LANE: ADVERSARIAL VERIFY of proposed _compose_basket_workers() JUDGE-CAP CLAMP
(subagent, 2026-07-12)  VERDICT: keeps_quality = FALSE (disqualified)
Proposal: judge_cap=resolve_max_concurrency() (0=>unbounded); sections=max(1,PG_PARALLEL_SECTIONS
or max_parallel_sections); return max(1, min(raw, judge_cap // sections)); set
PG_SIDE_JUDGE_MAX_CONCURRENCY >= sections*basket_workers.
Anchors read (compose_fix, READ-ONLY):
  verified_compose.py:249-259 (_compose_basket_workers), :1827-1857 (nested synth-verify pool _vw),
  :3411-3533 (basket MAP pool + serial REDUCE); multi_section_generator.py:5476/5527 (compose runs via
  asyncio.to_thread on the LOOP DEFAULT executor), :9947-9958 (PG_PARALLEL_SECTIONS, default 3);
  judge_concurrency.py:55 DEFAULT_MAX_CONCURRENCY=4, :81-104 resolve_max_concurrency (0=>unbounded),
  :151-183 acquire_judge_slot; entailment_judge.py:139-183 _post_with_total_deadline.

DEFECTS (measured / code-verified):
D1 FORMULA BROKEN FOR UNBOUNDED. resolve_max_concurrency()=0 for PG_SIDE_JUDGE_MAX_CONCURRENCY=0.
   0 // sections = 0 -> min(raw,0)=0 -> max(1,0)=1 => FORCES SERIAL. The proposal's parenthetical
   "(0=>unbounded, no clamp)" is FALSE; literal arithmetic collapses to 1 worker. Zero saving.
D2 DEFAULT KNOBS => SERIAL. At the shipped de-storm cap J=4 and default sections=3: workers=4//3=1
   => serial => ZERO wall-time saving. Any concurrency REQUIRES raising J above 4.
D3 RAISING J RE-OPENS THE 429 STORM (I1+I2). DEFAULT_MAX_CONCURRENCY=4 exists BECAUSE ~32 simultaneous
   POSTs 429-stormed friendli (judge_concurrency.py:51-55). Feeding the basket pool needs J~=48 (e.g.
   16 workers x 3 sections) which removes that de-storm. A 429 storm -> fail-CLOSED judge_error
   sentinels -> DROPPED verified sentences -> kept/dropped NLI set CHANGES (I2 broken) and coverage
   can drop (I1). Trades deadlock risk for verdict-drift risk.
D4 DEMAND MODEL INCOMPLETE. Real leaf judge demand = sections x basket_workers x V, where V =
   PG_PARALLEL_VERIFY_SYNTH / PG_PARALLEL_VERIFY inner pool (verified_compose.py:1851). Each basket
   also issues MANY sequential verify_fn calls (75 verify_fn refs / 7 direct call sites). The clamp
   only bounds sections x basket_workers <= J; "demand<=supply by construction" holds ONLY if V=1,
   which the proposal never pins. With V>1 the semaphore is oversubscribed again.
D5 MISDIAGNOSED DEADLOCK (I4 NOT established). acquire_judge_slot is never "exhausted-forever":
   _post_with_total_deadline (entailment_judge.py:155-183) holds the slot only for ONE POST under a
   HARD 150s force-close deadline, then releases on every exit. So steady-state semaphore queueing
   self-heals in <=150s; the observed 8.8-min ZERO-progress hang (SIGKILL) is a circular-wait /
   thread-exhaustion, NOT semaphore backlog. Equalizing demand<=supply does not address it. The
   proposal implements NONE of the real guards (dedicated executor OFF the shared to_thread default
   pool; acquire-timeout on the compose path; per-section watchdog). Note: compose is dispatched via
   asyncio.to_thread (loop DEFAULT executor, ~min(32,cpu+4)); the basket pool nests under it - the
   exact nesting the prior lane flagged as the deadlock root cause, left unfixed here.
D6 VERDICT-IDENTITY NOT CERTIFIABLE (I2). The module's OWN comment (verified_compose.py:1820-1826)
   states the multi-basket compose path is non-deterministic run-to-run EVEN fully serial and the
   record/replay certifier CANNOT byte-certify it. The serial REDUCE is order-preserving (good) but
   concurrency-induced verify TIMEOUTS under load can flip a verdict to the fail-closed DROP that a
   serial run would not hit -> kept/dropped set diverges. Verdict-identity is asserted, not proven.

MEASURED FORMULA TABLE (python repro of the exact proposed expression):
  raw=16 J=0  s=3 -> 1 (serial; proposal claims "no clamp")
  raw=16 J=4  s=3 -> 1 (serial at defaults)
  raw=16 J=4  s=1 -> 4
  raw=16 J=48 s=3 -> 16 (requires unsafe J=48)
  raw=16 J=48 s=6 -> 8

REAL SAVING: none guaranteed. At safe/default knobs it degenerates to serial (0 saving); the only
configs that yield concurrency demand an unsafe judge cap that reopens the 429 storm (I1/I2) and
does nothing about the actual thread-exhaustion hang (I4). DISQUALIFIED.

================================================================================
LANE: ADVERSARIAL VERIFY — "SHIP THE OFF-LOOP-ONLY SUBSET (to_thread + workers=1)"
(subagent, 2026-07-12)
VERDICT: keeps_quality = FALSE — all 4 invariants KEPT, but it is NOT a new speedup:
it is the ALREADY-LIVE default state, so the incremental wall-time saving is ZERO.

READ-CONFIRMED FACTS (outline_agent worktree = the live wheel; READ-ONLY):
- The off-loop wrap is ALREADY SHIPPED, not a proposal:
    multi_section_generator.py:6079 and :6130 both do
    `await asyncio.to_thread(_compose_section_per_basket, ...)`
    (comment "P0 OFF-LOOP ... 2026-07-12 SPEED MERGE, port of 1f9da4c").
  Delta count vs baseline: outline_agent src has 7 `asyncio.to_thread(` vs the
  POLARIS baseline's 4 -> the 3 extra ARE the compose off-loop wraps, already in
  the live worktree.
- PG_COMPOSE_BASKET_WORKERS defaults to 1 (verified_compose.py:238 `os.getenv(..., "1")`;
  values <=1 coerce to 1 at :243). It is NOT forced anywhere in /workspace/POLARIS/.env
  or the launch_*.sh scripts. So workers=1 is ALSO already the live default.
  => "Ship off-loop + workers=1" == the current live config. Nothing new to ship.
- At workers=1 the serial branch runs: _parallel_baskets is False, so NO inner basket
  ThreadPoolExecutor is created inside compose (verified_compose.py gate; the map/break
  path is skipped). MAP+REDUCE are serial in original basket order => byte-identical
  => verdict-identical.

MEASURED (real run, no new render launched — read the existing full-scale log):
- logs/step4_route_all_compose.log : a route_all run (corpus clusters=329) on THIS exact
  off-loop + workers=1 config ran end-to-end and COMPLETED — NO SIGKILL:
    `[gen] elapsed=1449.7s outline=8 sections kept=8 verified=65 dropped=68`
  i.e. the live baseline already completes; the SIGKILL only ever happened on the
  AGGRESSIVE workers>1 + semaphore(48) path (outputs/_16way_run.log), which no one
  proposes to ship.

WHY THE CLAIMED SAVING IS NONEXISTENT (not merely marginal):
1. "Recovers compose from unrecoverable hang (SIGKILL) to completing" — the SIGKILL
   baseline is the BROKEN workers>1 + sem(48) config, NOT a shippable baseline. Measured
   against the actual working baseline (off-loop + workers=1, which is what's live and
   what completed in 1449.7s), the incremental delta is 0.
2. Retrieval (plan_outline react loop, ~24min) and compose (write_one_section) are
   SEQUENTIAL langgraph nodes on a hard edge — they never overlap. Compose is the smaller
   slice. The off-loop wrap's only genuine benefit is INTRA-compose section parallelism
   (siblings' writer/verify HTTP + judge 429 backoffs stay unfrozen) — and that benefit
   is ALREADY delivered by the live baseline, not by "shipping" it again. It cannot touch
   the ~24min agentic long pole either way.

INVARIANTS (the config itself is safe — this is a KEEP-what's-live, not a risk):
  I1 coverage      KEPT  (workers=1 serial; no basket dropped; route_all coverage intact)
  I2 faithfulness  KEPT  (workers=1 serial MAP+REDUCE byte-identical => verdict-identical;
                          entailment acquire keeps its UNBOUNDED/no-timeout binding at
                          entailment_judge.py:155 => no JudgeSlotTimeout drop-sentinel =>
                          kept/dropped set unchanged. Residual: cross-SECTION concurrency
                          is genuinely exercised for the first time by the off-loop wrap;
                          the verdict-identity A/B that certified it was small-scale, not
                          full 328. But this residual attaches to the ALREADY-LIVE wrap,
                          not to anything this proposal newly introduces.)
  I3 agentic       KEPT  (compose is a later, separate graph node; cp4_used / degrade-to-
                          seed is decided in the retrieval node upstream — off-loop compose
                          cannot retroactively change it.)
  I4 no-deadlock   KEPT  (workers=1 => no nested basket pool; live judge-slot demand =
                          <= PG_PARALLEL_SECTIONS (default 3) concurrent holders vs cap 48,
                          each POST's inner ThreadPoolExecutor(1) does NOT re-acquire =>
                          the 19/20-futex_wait storm — a workers>1 + sem(48) amplification —
                          cannot occur. Confirmed by the 1449.7s clean completion.)

CONCLUSION: keeps_quality = FALSE. It preserves all four invariants, but it delivers NO
new wall-time saving: it is the config that is already live and already completing. Per
the "default FALSE if the saving is marginal" rule (here the incremental saving is 0, and
even a hypothetical perfect compose parallelization can't dent the ~24min retrieval long
pole), it fails the "REALLY saves meaningful wall-time" half of the test. The off-loop +
workers=1 baseline is worth KEEPING; re-labelling it as a shippable speedup is a no-op.

================================================================================
FINAL SYNTHESIS — RANKED QUALITY-SAFE SPEEDUP PLAN  (Fable, 2026-07-12)
Inputs: all lane profiles + all adversarial verdicts above. Only ONE finding survived
adversarial verification, and it is a NEGATIVE finding (intra-search fetch is already
parallel — live_retriever.py:6363-6441, workers band 8-14, per-host cap 4). Every
affirmative speedup proposal was disqualified. This synthesis is therefore mostly a
"protect the floor + defer one safe lever" plan, and it says so honestly.

(1) END-TO-END BREAKDOWN (measured, logs/step4_route_all_compose.log, 329 baskets,
    completed clean, elapsed=1449.7s = 24.2 min):
      A  seed outline digest        142s   9.8%   (one 118.5s deepseek call)
      B  AGENTIC REACT LOOP         737s  50.8%   = fetch 346.3s + non-fetch LLM ~391s
                                                    (24 decides = ~170s; ~11 checklists;
                                                    topic-judge). Zero-yield stretch 179s (24%).
      C  dedup/consolidate/cred      33s   2.3%
      D  COMPOSE + strict_verify    514s  35.5%   (65 verified / 68 dropped)
      E  fact_dedup/render           27s   1.9%
    The brief's "30+ min / ~24-min retrieval" is the BAD-TAIL case (_16way_run: one
    466s mega-fetch of 162/200 URLs, then wall-clock TimeoutError -> DEGRADE TO SEED).
    SINGLE BIGGEST HONEST LEVER: there is no surviving legal optimization that dents
    the 737s clean-run loop. The biggest honest lever is TAIL CONTROL — the ~6-10 min
    gap between the 24.2-min clean run and the 30+-min bad-tail run, which is also an
    I3 QUALITY bug (that tail run degraded to seed). No mechanism for it has yet been
    adversarially cleared; it is the top candidate for the next investigation round.

(2) RANKED PLAN (most wall-time protected/saved first, all 4 invariants kept):
  P0 — PIN THE SAFE COMPOSE CONFIG (protects completion; saving vs live baseline = 0;
       vs the 16-way attempt = hang -> completion).
       Do: keep the shipped off-loop wrap (multi_section_generator.py:6079/:6130
       asyncio.to_thread) with PG_COMPOSE_BASKET_WORKERS unset/1 (default, confirmed:
       verified_compose.py _compose_basket_workers coerces <=1 to 1; no override in
       /workspace/POLARIS/.env or launch scripts). Keep PG_SIDE_JUDGE_MAX_CONCURRENCY
       in the 4-8/host band; PG_PARALLEL_SECTIONS=3.
       GUARD: add a startup assert that refuses/clamps PG_COMPOSE_BASKET_WORKERS>1
       (and any sem>=48 judge cap) until the re-engineered path in (3) exists and has
       passed a FULL-328 verdict-identity A/B. Never re-run the sem(48) config.
  P1 — FIX THE BAD TAIL AS A CORRECTNESS BUG (worth ~6-10 min on affected runs, and
       required for I3 regardless of speed). The 466s mega-fetch + 900s wall trip is
       what produces both the 30+-min runs AND degrade-to-seed. No cleared mechanism
       yet. Constraint for any future fix: must not cut fetch_cap/coverage and must
       not cap turns; raising the outline wall for route_all deep runs is quality-
       preserving but SLOWER — acceptable, because a degraded run is worth zero.
  P2 — 100%-OVERLAP PER-ASPECT EXHAUSTION SKIP (the only salvageable affirmative
       lever; DEFERRED to next wheel — needs the live_retriever/outline seam, which is
       read-only while the wheel is live). Skip the fetch+classify slice iff EVERY
       candidate URL (after the SAME url-dedup rule, never query text) is already in
       ev_store — then kept=0 is guaranteed, ev_store is byte-identical, checklist
       inputs identical, hence verdict-identical by construction. Keep gap-ledger
       transitions (mark_retry_or_unfilled) unchanged. NOTE: this is the legal subset
       of R2; the 90% variant stays disqualified (I1/I2).
       Measured ceiling (clean run): turns 8-11 fetch stamps 17.0+22.3+16.9+18.0 =
       74s + fold/classify overhead inside the 179s zero-yield stretch => ~1-2 min,
       NOT the earlier ~2-3 min claim (decide/checklist in that stretch must stay).
       GATE: full-328 verdict-identity A/B + cp4_used==agentic + ~328/329 rendered.
  P3 — NOTHING ELSE. Disqualified (do not re-propose without new evidence): R1 batch
       gap drain (checklist IS the convergence/discovery engine; batching changes the
       query set -> I2); R3 cheaper decide (routing selects evidence -> I2; decides
       total only ~170s); turn/wall caps (I1/I3); basket sharding incl. the judge-cap
       clamp (collapses to serial at safe knobs; concurrency requires J~48 -> 429
       storm -> I2; I4 guards unimplementable as specified); judge-cap moves in either
       direction (correctness knob); batched judge prompts (I2 by construction);
       bytes fetch-cache (0 on a cold single run, not wired); section concurrency
       3->8 (bounded by global LLM sem=5 -> tens of seconds); draft-prompt tightening
       / regen skip (I2; regen is the coverage-rescue path); intra-search fetch
       concurrency (already exists — the one CONFIRMED finding).

(3) COMPOSE DEADLOCK — EXACT SAFE FIX:
  Root cause (code-verified, static): multiplicative thread oversubscription with no
  escape valve — PG_PARALLEL_SECTIONS(3) x PG_COMPOSE_BASKET_WORKERS(16) map threads,
  each NLI POST spawning an inner ThreadPoolExecutor(1) (~2x amplification), all
  contending on ONE process-global threading.BoundedSemaphore; the BINDING entailment
  acquire has NO timeout (entailment_judge.py:155); the basket-map join and the outer
  asyncio.to_thread have no wall; `with ThreadPoolExecutor` __exit__ blocks on a
  wedged worker (shutdown(wait=True)); to_thread is non-cancellable. Raising the sem
  to 48 moved the wedge and stripped the 429 de-storm; it is not a fix.
  THE FIX THAT SHIPS: off-loop + workers=1, enforced by the P0 startup guard. Do NOT
  add a timeout to the binding entailment acquire — JudgeSlotTimeout emits the fail-
  closed ('ENTAILED','judge_error') sentinel that consumers DROP, changing the
  kept/dropped set (I2). Do NOT ship the judge-cap clamp (disqualified D1-D6: yields
  workers=1 at safe knobs anyway; ignores inner verify width V; misdiagnoses the
  wedge). workers>1 stays OFF the table until a re-engineered path exists (dedicated
  module-owned executor off the to_thread default pool + complete demand model incl.
  V + a watchdog that can actually free a wedge) AND passes a full-328 A/B.
  OFF-LOOP-ONLY FALLBACK — CONFIRMED deadlock-free AND verdict-identical:
    - workers=1 => _parallel_baskets False => NO nested basket pool; serial MAP+REDUCE
      in original basket order = byte-identical => verdict-identical by construction.
    - Peak judge-slot demand = PG_PARALLEL_SECTIONS(3) <= cap(4); each POST bounded by
      the 150s total-deadline; no re-entrancy (verify loop is serial, holds <=1 slot).
    - EMPIRICAL: the full 329-basket route_all COMPLETED clean on exactly this config
      (1449.7s, no SIGKILL, faithfulness_pass=true, leaked_cite_ev_tokens=0,
      verified=65/dropped=68 gate intact, finish_outline bounced at turn 18 and kept
      looping — agentic held, no degrade line).

(4) HONEST CEILING:
  - A faithful, agentic, full-coverage 328/329-basket deep render runs ~24 min TODAY
    when nothing goes wrong (1449.7s measured, all four invariants verified in-log).
    That is already close to the floor.
  - After P2 lands (next wheel, A/B-gated): ~22-23 min clean. After P1: the 30+-min
    tail collapses toward the clean number on runs that would have gone bad.
  - Realistic floor ~20-22 min on current models. CANNOT be sped up without
    sacrificing quality:
      * The serial react-loop LLM chain (~391s decide+checklist): each query is chosen
        from the previous fold — it IS the agentic convergence engine; parallelizing,
        batching, or cheapening it changes the evidence pool => verdict drift (I2).
      * Cross-turn fetch overlap: blocked by the same decide dependency; intra-search
        fetch is already parallel and bounded by the slowest URL.
      * strict_verify/NLI: per-sentence entailment at unstarved token budgets under
        the 4-8 judge cap — the faithfulness gate itself; every "verify faster" idea
        examined (batching, timeouts, cap raises) changes verdicts.
      * Drop-driven repair/regen (~130-180s of compose): regen is the coverage-rescue
        path; the only way to shrink it changes draft text => changes verdicts.
      * Coverage itself: 329 baskets must each be composed and verified; that work is
        the product, not overhead.
