# generous_limits.sh — I-deepfix-001 (#1344)
# ---------------------------------------------------------------------------
# PURPOSE: raise EVERY discovered time-wall + budget knob to GENEROUS values so a
# real Gate-B run has ALL the time (and money) it needs to produce a HIGH-QUALITY
# full report. Operator directive: TIME is NOT a limit, COST is NOT a limit. A
# thin / stub report from a starved wall is the failure we are killing here.
#
# USAGE:  source .codex/I-deepfix-001/generous_limits.sh   # BEFORE run_gate_b.py
#
# SCOPE:  WALLS + BUDGETS ONLY. NO faithfulness knob is touched (no
#         PG_PROVENANCE_MIN_CONTENT_OVERLAP, no strict_verify / NLI thresholds,
#         no D8 role MODELS). See the "DELIBERATELY NOT OVERRIDDEN" footer.
#
# HOW run_gate_b.py's slate INTERACTS WITH THIS FILE (verified in
# apply_full_capability_benchmark_slate, scripts/dr_benchmark/run_gate_b.py:4040):
#   * FLOOR knobs  -> slate does max(existing, slate_value); a HIGHER value here is
#                     KEPT. All the big guillotines below are FLOOR knobs, so this
#                     file genuinely raises them under run_gate_b.
#   * DIRECT knobs -> not in the slate at all; read straight from env at their call
#                     site, so this file's value is authoritative.
#   * FORCE-EXACT  -> the slate OVERWRITES env to its pinned value. Six walls below
#                     are force-exact (tagged [FORCE-EXACT]); this file's generous
#                     value takes effect on the DIRECT run_honest_sweep_r3.py path
#                     but is pinned back by run_gate_b's slate. To actually raise
#                     those under Gate-B, edit the slate value in run_gate_b.py.
#
# ORDERING (preflight_full_capability HARD-asserts these — values below satisfy them):
#   generator(10800) < section(14400) < run-wall(43200);  seam <= run-wall;  retrieval < run-wall.
# ---------------------------------------------------------------------------

# ===========================================================================
# TIER 1 — PRIMARY WALLS  (FLOOR: env wins under run_gate_b)
# ===========================================================================
export PG_RUN_WALL_CLOCK_SEC=43200            # run-wall guillotine: 14400 (Gate-B) / 10800 (hist) -> 43200 (12h)
export PG_SECTION_WALLCLOCK_SECONDS=14400     # per-section wall: 9000 (Gate-B) / 900 (smoke) -> 14400 (4h/section)
export PG_GENERATOR_LLM_TIMEOUT_SECONDS=600  # per-call generator LLM: 10800(3h, BUG-hang) -> 600 (10m). A single gen call is <2m; 10m = fail-fast on a HUNG provider + retry a different one. Section wall (14400) + run wall (43200) stay the real budgets.
export PG_RETRIEVAL_QUESTION_WALL_SECONDS=5400 # shared per-question retrieval activation wall: 5400 -> 5400 (90m; < run-wall)

# ===========================================================================
# TIER 2 — RETRIEVAL-PHASE WALLS  (read live from env at call time)
# ===========================================================================
export PG_RETRIEVAL_WALL_SECONDS=5400         # live_retriever per-question retrieval wall: 1800 -> 5400 (90m)
export PG_FETCH_DEADLINE_SECONDS=210          # per-URL content-fetch deadline / worker abandon-join: 90 -> 210 (ABOVE the ~195s capped mineru cascade, so a slow-but-legit PDF worker FINISHES and RELEASES its in-flight slot instead of leaking it — drb_72 #1369 leak-safety)
# UNIT 6 fetch-concurrency + leak-safety (drb_72 fix wave #1369): the 922-timeout HANG-AND-LEAK cure.
# NOT a wall change — aligns the live fetch semaphore to the pool + caps the PDF worker so the cascade fits under the abandon-join.
export PG_BYPASS_MAX_INFLIGHT=16             # 48 blew the container PID-cap (12544) via headless-browser fan-out on box1 preflight; 16 proven-safe, leak-fix (mineru 75s + abandon-join 210s) still cures starvation. DEEPFIX #1369
export PG_MINERU25_TIMEOUT_S=75             # mineru PDF per-call cap: 300(orig)/90(new default) -> 75 (cascade 60+60+75=195 fits under the 210 abandon-join)
export PG_MIN_FETCH_YIELD=0.30              # NEW hard fetch-yield HALT gate: abort BEFORE composition if <30% of candidates fetched (never bank a starved corpus again)
export PG_LIVE_HTTP_TIMEOUT=60                # per-request httpx timeout (FLOOR): 30 -> 60
export PG_OA_RECOVERY_DEADLINE=60            # OpenAccess recovery whole-attempt wall: 20 -> 60
export PG_OPENALEX_ENRICH_DEADLINE=90        # per-call OpenAlex enrich wall: 45 -> 90
export PG_TRAFILATURA_SUBPROCESS_TIMEOUT_SECONDS=120 # trafilatura child extract timeout: 20 -> 120
export PG_WALL_CLASSIFY_RESCUE=1             # keep-not-drop already-fetched bodies at the wall break: off -> ON (faithfulness-neutral)
export PG_DISTILL_MAP_CALL_WALL_S=3600       # per distill_map call wall: 1800 -> 3600 (above ~1475s healthy max)
export PG_TIER_LLM_BATCH_WALL_SECONDS=1800   # W5 LLM credibility-tiering batch wall: 600 -> 1800

# ===========================================================================
# TIER 3 — VERIFY / D8 / CONSOLIDATION WALLS
# ===========================================================================
export PG_VERIFY_GATHER_TIMEOUT=32400        # verify-stage asyncio gather timeout: 1800 -> 32400 (9h; > seam, < run-wall)
export PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS=28800 # [FORCE-EXACT] whole 4-role D8 seam wall: 7200 -> 28800 (8h; slate pins 7200 under Gate-B)
export PG_NLI_ANNOTATION_WALL_S=1800         # consolidation NLI/entailment annotation pass wall: 420 -> 1800
export PG_CREDIBILITY_PASS_WALL_S=6000       # [FORCE-EXACT] advisory W5 credibility-pass wall: 1200/3000 -> 6000 (slate pins 3000 under Gate-B)

# ===========================================================================
# TIER 4 — PER-LLM-CALL REQUEST TIMEOUTS
# ===========================================================================
export PG_LLM_TIMEOUT_SECONDS=300            # shared non-reasoning per-call timeout (FLOOR): 90/180 -> 300
export PG_LLM_LONG_TIMEOUT_SECONDS=600       # 'long' non-reasoning per-call floor: 180 -> 600
export PG_VERIFIER_LLM_TIMEOUT_SECONDS=1800  # verifier / cited-span per-call timeout: 900 -> 1800
export PG_ENTAILMENT_TOTAL_S=600             # [FORCE-EXACT] entailment/NLI judge per-call wall: 150/300 -> 600 (slate pins 300 under Gate-B)
export PG_CREDIBILITY_JUDGE_TOTAL_S=600      # [FORCE-EXACT] credibility binding-judge per-call wall: 300 -> 600 (slate pins 300 under Gate-B)
export PG_ROLE_TRANSPORT_TOTAL_S=600         # [FORCE-EXACT] generic 4-role verifier per-call transport wall: 300/900 -> 600 (slate pins 300 under Gate-B)
export PG_ROLE_TRANSPORT_TOTAL_S_JUDGE_FLOOR=3600 # slow-Judge per-call wall FLOOR (NOT force-exact -> genuinely lifts Judge even under Gate-B): 1800 -> 3600
export PG_ROLE_TRANSPORT_TOTAL_S_SENTINEL=900     # Sentinel per-call transport wall: 300 -> 900
export PG_ROLE_TRANSPORT_TOTAL_S_MIRROR=1800      # Mirror per-call transport wall: 900 (generic) -> 1800
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=900  # [FORCE-EXACT] abstractive-writer per-call compose deadline: 120/180 -> 900 (slate pins 180 under Gate-B)
export PG_SCOPE_INTENT_FRAME_TIMEOUT_SEC=600      # scope intent-frame LLM per-call timeout: 150 -> 600
export PG_ADEQUACY_CRAG_LLM_TIMEOUT_SECONDS=600   # adequacy/CRAG LLM per-call timeout: 180 -> 600 (still clamped by remaining retrieval wall)
export PG_SSE_READ_STALL_TIMEOUT_SECONDS=300      # per-chunk SSE read-stall detector: 120 -> 300 (tolerate long reasoning pauses; still bounded)
export PG_LLM_CALL_WATCHDOG_GRACE_SECONDS=120     # asyncio watchdog grace above actual timeout: 30 -> 120

# ===========================================================================
# TIER 5 — MISC STAGE / LIFECYCLE WALLS
# ===========================================================================
export PG_CONTRACT_SLOT_STALL_TIMEOUT_S=2400 # contract-slot stall/wedge timeout: 1200 -> 2400
export PG_STRUCTURED_DATA_TOTAL_TIMEOUT=3600 # structured-data (quantified) extraction stage wall: 1800 -> 3600
export PG_AGENTIC_MAX_TIME_SECONDS=3600      # agentic-search loop wall: 1800 -> 3600 (agentic force-OFF in Gate-B; generous anyway)
export PG_LOOPBACK_TIMEOUT_SEC=10800         # sovereign local loopback per-call timeout: 7200 -> 10800 (sovereign path only)
export PG_TEARDOWN_WALL_SECONDS=120          # post-run grace before watchdog force-exit: 30 -> 120 (let a slow-but-finishing teardown complete)
export HF_HUB_DOWNLOAD_TIMEOUT=120           # HuggingFace per-file model download timeout (FLOOR): 30 -> 120 (cold-VM cache)
export PG_MINERU25_HEALTH_PROBE_TIMEOUT_S=30 # preflight mineru25 vLLM health-probe timeout: 5 -> 30

# ===========================================================================
# TIER 6 — SPEND CAPS  (money never stops the run)
# ===========================================================================
export PG_MAX_COST_PER_RUN=300               # real per-RUN cross-instance spend cap (FLOOR + set_max_cost_per_run): 10/150 -> 300 USD
export OPENROUTER_BUDGET_USD=300             # per-client-instance budget ceiling: 50 -> 300 USD

# ===========================================================================
# TIER 7 — RETRIEVAL PARTITION RATIOS  (pinned at DEFAULT on purpose)
# These are FRACTIONS of the (now 3x larger) retrieval wall, not walls themselves.
# Each phase already gets ~3x more ABSOLUTE time from the raised wall above; raising
# one fraction would STARVE its sibling phase, so they stay at their defaults.
# ===========================================================================
export PG_RETRIEVAL_FETCH_WALL_FRACTION=0.75      # fetch share of remaining retrieval wall: unchanged (scales with raised wall)
export PG_RETRIEVAL_W2_WALL_FRACTION=0.5          # W2 content-relevance share: unchanged (scales with raised wall)
export PG_POST_FETCH_ENRICH_WALL_FRACTION=0.5     # OpenAlex enrich pre-batch share: unchanged (scales with raised wall)

# ===========================================================================
# DELIBERATELY NOT OVERRIDDEN (out of scope / governed elsewhere)
# ---------------------------------------------------------------------------
#  * FAITHFULNESS knobs — UNTOUCHED (walls/budgets only): PG_PROVENANCE_MIN_CONTENT_OVERLAP,
#    strict_verify / NLI / D8 thresholds, and the D8 role MODELS (PG_ENTAILMENT_MODEL /
#    PG_EVALUATOR_MODEL / PG_EMBED_MODEL / PG_EMBEDDER_MODEL / PG_RERANKER_MODEL). The §9.1.8
#    runtime lock owns these; raising a wall must never move a faithfulness dial.
#  * max_tokens caps — left to the §9.1.8 lock / role transport (instruction: do NOT lower;
#    none are starving below the model's real limit): PG_SECTION_MAX_TOKENS (64000),
#    PG_SECTION_REASONING_MAX_TOKENS (16384), PG_MIRROR_REASONING_MAX_TOKENS (100000),
#    PG_MIRROR_MAX_TOKENS (131072), PG_SENTINEL_DECOMPOSITION_MAX_TOKENS (131072),
#    PG_SENTINEL_MAX_TOKENS (4096), PG_D8_VERDICT_MAX_TOKENS (16384; kept bounded so
#    OpenRouter load-balances all Judge providers), PG_REASONING_FIRST_MIN_MAX_TOKENS (32768).
#  * PG_WALL_RESCUE_WEIGHT (0.25) — a credibility WEIGHT, not a time/budget knob; left as-is.
#  * PG_SECTION_RUNWALL_MARGIN_S (120) — a gap SUBTRACTED from the section budget; raising it
#    would REDUCE work time, so left at default.
#  * PG_FOUR_ROLE_SEAM_GEN_MULTIPLE (4) — only used when the seam timeout is UNSET; we set the
#    seam explicitly above, so it is moot.
#  * PG_ROLE_TRANSPORT_DEGRADE — a behavior switch (degrade-vs-halt), not a wall; left default ON.
#  * Retry / backoff counts (not walls; raising can slow or hurt): PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES,
#    PG_ENTAILMENT_RATE_LIMIT_FLOOR_S, PG_ENTAILMENT_RATE_LIMIT_CAP_S, PG_RATE_LIMIT_FLOOR_S,
#    PG_CREDIBILITY_JUDGE_TOTAL_DEADLINE_RETRIES, PG_PREFLIGHT_CATALOG_RETRIES — left at default.
#  * _ENTAILMENT_TIMEOUT_S (30s per-read GAP) is HARDCODED in entailment_judge.py with no env
#    hook — it cannot be overridden here; the real per-call bound is PG_ENTAILMENT_TOTAL_S (raised above).
#
# FORCE-EXACT REMINDER: under scripts/dr_benchmark/run_gate_b.py the slate pins these six back to
# their slate values regardless of this file — PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS(7200),
# PG_CREDIBILITY_PASS_WALL_S(3000), PG_CREDIBILITY_JUDGE_TOTAL_S(300), PG_ROLE_TRANSPORT_TOTAL_S(300),
# PG_ENTAILMENT_TOTAL_S(300), PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S(180). To raise them for a Gate-B
# run, change the slate value in run_gate_b.py; the generous values here apply on the direct
# run_honest_sweep_r3.py path. (PG_ROLE_TRANSPORT_TOTAL_S_JUDGE_FLOOR is NOT force-exact, so the
# slow-Judge per-call wall above genuinely rises even under Gate-B.)
# ===========================================================================
