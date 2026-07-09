# Launch readiness — both boxes (Fable, 2026-07-08, wvopy9lvt)

## box2_resume (ssh6.vast.ai:38794, 2x A100-SXM4-80GB, container 7f89282c8e9f) [resume]

### BLOCKERS
- 4IR DETERMINISTIC RE-ABORT: the run just died at the run-validity gate because config/scope_templates/workforce.yaml bakes the optional theory_4ir_framing slot ('Fourth Industrial Revolution framing (contextual)') into every workforce contract; strict_verify keeps 0 sentences, the disclosed-gap HEADER still renders, and run_validity_gate.py's body-wide forbidden_reformulations scan aborts. Codex-confirmed root cause (flag_default_off: the purpose-built prune in journal_only_filter.py is dark because JOURNAL_ONLY_BENCHMARK_SLUGS is empty). The 12-fix UNIFIED_BUILD_PLAN does NOT cover this. Relaunching the resume without a question-gate/prune of that slot (or removing the stale 4IR facet from workforce.yaml for drb_72) is a GUARANTEED wasted paid run — it will abort at render again.
- B1 RESUME-BLINDNESS (the special check): as specced, B1 will NOT fire on the banked corpus. The WT-4 build must add the resume-load re-screen (extend the A15 degraded predicate at run_honest_sweep_r3.py:12919-12924 to OR the furniture-density predicate when PG_FURNITURE_DENSITY_SCREEN=1) AND the launch env must set PG_RESUME_REFETCH_DEGRADED=1 — it was NOT set on wave 2, so even base A15 was detection-only. Without both, B1/B2 are exercised on approximately zero banked rows.
- GATED COMMIT DOES NOT EXIST YET: Opus build in flight; the relaunch script's git pin (9627e7b9) must be updated to the new dual-gate-approved commit, and the openrouter_provider_routing.yaml generator allow_fallbacks:true config edit verified present in it, before launch.
- STALE 31.7GB GPU ALLOCATION on card 1 (two ~31.7GB chunks, only one live mineru server) — restart the mineru vllm server cleanly (keep CUDA_VISIBLE_DEVICES=1, util 0.4, port 30000) to reclaim before launch.
- Old run already stopped (pid 76099 dead via teardown-wall os._exit after the 4IR abort) — no kill needed; pre-launch guard only: pgrep -f run_gate_b.py must be empty, else pkill -f 'run_gate_b.py --only drb_72_ai_labor'.

### special_verdict
B1 IS BLIND ON RESUME as currently specced — definitive, code-proven. Chain: (1) a --resume reloads corpus_snapshot.json frozen with NO re-retrieval; extraction (access_bypass.py, where B1's PG_FURNITURE_DENSITY_SCREEN runs per UNIFIED_BUILD_PLAN WT-4) never executes for banked rows. (2) The ONLY re-fetch doorway on resume is the A15 cascade, and its degraded-detector (run_honest_sweep_r3.py:12919-12924) flags a row ONLY on content_starved / fetch_failed / landing_page flags or is_content_starved(grounding) — a banked furniture direct_quote (long, dense ToC/nav/author chrome) is non-starved and unflagged, so it is NEVER flagged, NEVER enters refetch_degraded_resume_rows, and B1/B2 never touch it. (3) resume_refetch.py's own docstring confirms the detector 'only ever FLAGS a starved/failed/landing row'. VERDICT: BLOCKER — the WT-4 build MUST add a resume-load re-screen: when PG_FURNITURE_DENSITY_SCREEN=1, OR the B1 furniture-density predicate into the A15 _is_degraded expression at run_honest_sweep_r3.py:12919 (import the predicate read-only), so furniture rows get resume_refresh_pending and flow into the PG_RESUME_REFETCH_DEGRADED=1 re-fetch cascade (which also exercises B2's mineru path and propagates recovered spans to V30 FrameRows via the existing P6 seam). ADDITIONALLY: PG_RESUME_REFETCH_DEGRADED was NOT set on wave 2 and must be =1 on this relaunch or even the flagged rows stay detection-only. With the re-screen + flag, B1 steps 1-2 and B2 ARE exercised on resume; B1 step 3 (span re-selection) fires on the re-fetched rows only, which is the intended surface. Zyte/Serper/Exa/Jina keys are all present in /workspace/POLARIS/.env, so the re-fetch cascade will not starve.

### verified_flag_slate
```
set -a; source /workspace/box2_deep_env.sh; set +a
# ── proven credibility slate (wave-2, dual-gate 4598e575) ──
export PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-5.2 PG_CREDIBILITY_JUDGE_HYBRID_TIERS=T1,T2,T6,T7 PG_CREDIBILITY_PASS_WALL_S=6000 PG_CREDIBILITY_PASS_BANK_FRAC=0.85 PG_CREDIBILITY_JUDGE_POOL_WALL_S=2400 PG_CREDIBILITY_PASS_MAX_INFLIGHT=20 PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10 PG_CREDIBILITY_JUDGE_SLOT_WAIT_S=180 PG_CREDIBILITY_JUDGE_PROGRESS_EVERY=25 PG_BREADTH_ENRICHMENT_ENABLED=1
# ── proven wave-2 quality + topic-gate flags ──
export PG_RENDER_CHROME_SCREEN=1 PG_SOURCE_FURNITURE_CHROME=1 PG_COT_PREAMBLE_STRIP=1 PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED=1 PG_ANALYST_SYNTHESIS_BASKET_MODE=1 PG_ANALYST_SYNTHESIS_BASKET_FULLTEXT=1 PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP=1 PG_COMPOSE_NO_UNRELATED_GLUE=1 PG_DEDUP_REFHEADER_STRICT=1 PG_DEDUP_REFHEADER_MAX_LEN=80 PG_RESUME_RUN_TOPIC_JUDGE=1 PG_QUARANTINE_UNJUDGED_TOPIC=0 PG_TOPIC_GATE_RESCUE_ON_STAMP=1 PG_OFFTOPIC_RELEVANCE_OVERRIDE=0
# ── committed base fixes, explicit ON per PART 3 ──
export PG_CONSOLIDATION_NLI_SUBBUCKET=1 PG_QUERY_META_STATUS_SCREEN=1
# ── PART-3 12-fix activation slate (names binding per UNIFIED_BUILD_PLAN) ──
export PG_COMPOSE_OFFTOPIC_BASKET_SCREEN=1 PG_BOUNDARY_QUOTE_HYGIENE_V2=1 PG_ASPECT_OFFTOPIC_SLOT_GUARD=1 PG_CONTRACT_FRAGMENT_PROSE_DEDUP=1 PG_SUMMARY_TABLE_ANCHOR_SECTION=1 PG_CONTRACT_GAP_PLAIN_DISCLOSURE=1 PG_SLOT_PROSE_SENTENCE_CITES=1 PG_SLOT_FRAGMENT_SNAP=1
export PG_OPENROUTER_THINK_LEAK_STRIP=1 PG_JUDGE_OFFENUM_PROVIDER_ROTATE=1   # B6 kill-switches, default-ON, set explicitly
export PG_FURNITURE_DENSITY_SCREEN=1 PG_FURNITURE_REFETCH=1 PG_SPAN_SELECT_FURNITURE_AWARE=1   # B1
export PG_MINERU25_TIMEOUT_PER_PAGE_S=<builder-final ~1.5-3> PG_MINERU25_BREAKER_THRESHOLD=<builder-final> PG_MINERU25_BREAKER_COOLDOWN_S=<builder-final>   # B2 (keep PG_MINERU25_TIMEOUT_S=75 floor from env)
export PG_OPENROUTER_KEEPALIVE_EXPIRY_S=2 PG_OPENROUTER_MAX_KEEPALIVE=8 PG_OPENROUTER_FRESH_CONN_ON_DISCONNECT=1   # B3
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1 PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1 PG_ABSTRACTIVE_WRITER_CONCURRENCY=24   # B3/B4
export PG_CONTRACT_BIND_DOI_FALLBACK=1 PG_CONTRACT_REANCHOR_CLEAN_SIBLING=1 PG_AUTHOR_ABSTRACT_HEADER_STRIP=1   # B5
# ── RESUME-CRITICAL (missing from wave-2 env — required for B1/B2 to fire on banked rows) ──
export PG_RESUME_REFETCH_DEGRADED=1
# ── diagnostics ──
export PYTHONFAULTHANDLER=1 PYTHONIOENCODING=utf-8
export CUDA_VISIBLE_DEVICES=0   # main proc on card 0; mineru server stays pinned to card 1
```

### corrected_launch_command
cd /workspace/POLARIS && git fetch origin bot/I-wire-001-integration && git reset --hard <NEW_DUAL_GATED_COMMIT> && [source the verified_flag_slate above] && setsid python scripts/dr_benchmark/run_gate_b.py --only drb_72_ai_labor --out-root outputs/paid_drb72_deep --resume > /workspace/paid_deep_wave3.log 2>&1 < /dev/null &

### readiness items
- [PASS] 1. Models (no gemma/wrong-model drift) — Env: PG_GENERATOR_MODEL=z-ai/glm-5.2, PG_MIRROR_MODEL=z-ai/glm-5.2, PG_EVALUATOR_MODEL/PG_ENTAILMENT_MODEL/PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-5.2 (lock legacy_compat mirror). Code defaults: sentinel=
- [PASS] 2. Token max not starved — Judge starvation root fix is committed: judge_reasoning_block.py numeric reasoning cap for glm judges + starved-budget fail-loud warning. token_limit_resolver.py: kimi-k2.6 (262144 ctx, 262144 complet
- [PASS] 3. Credibility concurrency + slate — box2_relaunch_wave2.sh (proven) carries the full slate: PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10 (the parallel hang fix), POOL_WALL_S=2400, PASS_WALL_S=6000, BANK_FRAC=0.85, HYBRID_TIERS=T1,T2,T6
- [NEEDS_ACTION] 4. GPU device pins (2-card split) — Split is CORRECT: mineru vllm server pinned CUDA_VISIBLE_DEVICES=1 (verified /proc/43967/environ); main run gets CUDA_VISIBLE_DEVICES=0 with PG_EMBED_DEVICE/PG_RERANKER_DEVICE/PG_NLI_DEVICE/PG_CONSOLI
- [PASS] 5. Mineru server + client backend — Server up (pid 43967, mineru-vllm-server --gpu-memory-utilization 0.4 --port 30000), /v1/models returns MinerU2.5-2509-1.2B (max_model_len 16384). Env: PG_MINERU25_BACKEND=vlm-http-client, PG_MINERU25
- [NEEDS_ACTION] 6. Full PART-3 fix-flag slate — Expected pre-commit: NONE of the 12-fix flags exist in the current box env (code not deployed yet). Also missing from the box env and the wave-2 script and MUST be added: PG_ABSTRACTIVE_WRITER_CONCURR
- [NEEDS_ACTION] 7. PYTHONFAULTHANDLER / PYTHONIOENCODING / out-root / --only / --resume — PYTHONFAULTHANDLER=1 present in the proven script. PYTHONIOENCODING is NOT set anywhere — add utf-8. Command shape is correct and proven: run_gate_b.py --only drb_72_ai_labor --out-root outputs/paid_d
- [PASS] 8. Corpus checkpoint + old-run stop — corpus_snapshot.json present: 13,476,292 bytes, Jul 8 04:20 UTC (plus a .prefix_bak twin) at /workspace/POLARIS/outputs/paid_drb72_deep/workforce/drb_72_ai_labor/. Old run pid 76099 is ALREADY DEAD — 

---

## box1_fresh (ssh9.vast.ai:20988, 2x A100-SXM4-80GB, host 20b4155c17d7) [fresh]

### BLOCKERS
- Gated 12-fix code commit not yet on the box (HEAD=9627e7b, topic-gate test-driver commit). Launch script must git fetch + git reset --hard <GATED_SHA> first — do not launch on the current HEAD.
- MUST pass --official-question (and belt PG_BENCHMARK_OFFICIAL_QUESTION=1). Without it the drb_72_ai_labor slug runs the I-safety-002b FIR safety prompt, not the scoped DRB question — the whole run would be non-comparable to box2 and wasted.
- MUST use a brand-new clean out-root (outputs/paid_drb72_fresh3) — paid_drb72_fresh and paid_drb72_fresh2 both hold leftovers and PG_AUTO_RESUME=1 is set, so a dirty out-root can silently resume stale state. Never reuse paid_drb72_deep.
- The credibility slate, the two committed base flags, PG_ABSTRACTIVE_WRITER_CONCURRENCY=24, and ALL PART-3 fix flags are absent from the box env files — the launch script must export every line of the verified_flag_slate.
- B2's PG_MINERU25_TIMEOUT_PER_PAGE_S / BREAKER values below are builder-proposed placeholders — confirm the final values against the gated diff before launch.
- PG_ABSTRACTIVE_WRITER_CONCURRENCY=24 is safe ONLY with the B3/B4 fixes deployed (PG_WRITER_WALL_BASKET_SCALED etc.). If launching without the gated commit for any reason, revert to the proven 8 with wall 720.

### special_verdict
BOX1 KEY CHECK: PASS — all three fetch-critical keys are PRESENT and LIVE-PROBED from the box itself: SERPER_API_KEY in /workspace/POLARIS/.env returned a real Google search result (SERPER_ENABLED=true, daily budget 50); ZYTE_API_KEY returned an HTTP-200 extract from api.zyte.com; OPENROUTER_API_KEY (box2_deep_env.sh + .env) validated against /api/v1/key with no hard limit. EXA_API_KEY and JINA_API_KEY are also present as secondary backends. run_gate_b.py auto-loads .env from the working directory (load_dotenv, verified in source), so the fresh fetch will NOT starve for keys. Belt: PG_MIN_FETCH_YIELD=0.30 is armed, so even an unexpected starvation halts BEFORE composition instead of banking a deficient corpus. ONE ADDITIONAL CRITICAL CATCH for this box: the fresh launch MUST include --official-question — without it, drb_72_ai_labor generates on the I-safety-002b FIR safety prompt (a different program shares the slug per run_gate_b.py:6369), not the scoped DRB question box2 ran, making the run non-comparable and wasted. Gold file is present (third_party/DeepResearch-Bench-II) so the flag fails loud only if that vanishes.

### verified_flag_slate
```
set -a; source /workspace/box2_deep_env.sh; set +a
# models (belt; code already resolves these — no gemma anywhere)
export PG_GENERATOR_MODEL=z-ai/glm-5.2 PG_MIRROR_MODEL=z-ai/glm-5.2 PG_EVALUATOR_MODEL=z-ai/glm-5.2 PG_ENTAILMENT_MODEL=z-ai/glm-5.2
export PG_JUDGE_MODEL=moonshotai/kimi-k2.6 PG_SENTINEL_MODEL=minimax/minimax-m2 PG_FOUR_ROLE_REASONING_EFFORT=xhigh
# device pins (mineru vllm owns card 1; pipeline card 0 — do NOT source a100_complete_env.sh L3 split)
export CUDA_VISIBLE_DEVICES=0 PG_EMBED_DEVICE=cuda:0 PG_RERANKER_DEVICE=cuda:0 PG_NLI_DEVICE=cuda:0 PG_CONSOLIDATION_NLI_DEVICE=cuda:0 PG_CONTENT_RELEVANCE_DEVICE=cuda:0
export PG_MINERU25_BACKEND=vlm-http-client PG_MINERU25_SERVER_URL=http://localhost:30000 PG_MINERU25_CLI_PATH=/root/mineru_svc/bin/mineru
# proven credibility slate (the parallel fix that cured the hang)
export PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-5.2 PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10 PG_CREDIBILITY_JUDGE_POOL_WALL_S=2400 PG_CREDIBILITY_PASS_WALL_S=6000 PG_CREDIBILITY_PASS_BANK_FRAC=0.85 PG_CREDIBILITY_JUDGE_HYBRID_TIERS=T1,T2,T6,T7 PG_CREDIBILITY_JUDGE_PROGRESS_EVERY=25 PG_CREDIBILITY_PASS_MAX_INFLIGHT=20 PG_CREDIBILITY_JUDGE_SLOT_WAIT_S=180 PG_BREADTH_ENRICHMENT_ENABLED=1
# committed base fixes (e6b6d31f)
export PG_CONSOLIDATION_NLI_SUBBUCKET=1 PG_QUERY_META_STATUS_SCREEN=1
# wave-2 proven quality fixes (box2-proven)
export PG_RENDER_CHROME_SCREEN=1 PG_SOURCE_FURNITURE_CHROME=1 PG_COT_PREAMBLE_STRIP=1
export PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED=1 PG_ANALYST_SYNTHESIS_BASKET_MODE=1 PG_ANALYST_SYNTHESIS_BASKET_FULLTEXT=1 PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP=1
export PG_COMPOSE_NO_UNRELATED_GLUE=1 PG_DEDUP_REFHEADER_STRICT=1 PG_DEDUP_REFHEADER_MAX_LEN=80
export PG_RESUME_RUN_TOPIC_JUDGE=1 PG_QUARANTINE_UNJUDGED_TOPIC=0 PG_TOPIC_GATE_RESCUE_ON_STAMP=1 PG_OFFTOPIC_RELEVANCE_OVERRIDE=0
# UNIFIED_BUILD_PLAN PART-3 12-fix slate — ALL ON
export PG_COMPOSE_OFFTOPIC_BASKET_SCREEN=1 PG_BOUNDARY_QUOTE_HYGIENE_V2=1 PG_ASPECT_OFFTOPIC_SLOT_GUARD=1
export PG_CONTRACT_FRAGMENT_PROSE_DEDUP=1 PG_SUMMARY_TABLE_ANCHOR_SECTION=1 PG_CONTRACT_GAP_PLAIN_DISCLOSURE=1
export PG_SLOT_PROSE_SENTENCE_CITES=1 PG_SLOT_FRAGMENT_SNAP=1
export PG_OPENROUTER_THINK_LEAK_STRIP=1 PG_JUDGE_OFFENUM_PROVIDER_ROTATE=1
export PG_FURNITURE_DENSITY_SCREEN=1 PG_FURNITURE_REFETCH=1 PG_SPAN_SELECT_FURNITURE_AWARE=1
export PG_MINERU25_TIMEOUT_PER_PAGE_S=2 PG_MINERU25_BREAKER_THRESHOLD=6 PG_MINERU25_BREAKER_COOLDOWN_S=60   # builder-proposed; confirm vs gated diff
export PG_OPENROUTER_KEEPALIVE_EXPIRY_S=2 PG_OPENROUTER_MAX_KEEPALIVE=8 PG_OPENROUTER_FRESH_CONN_ON_DISCONNECT=1
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1 PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_CONTRACT_BIND_DOI_FALLBACK=1 PG_CONTRACT_REANCHOR_CLEAN_SIBLING=1 PG_AUTHOR_ABSTRACT_HEADER_STRIP=1
export PG_ABSTRACTIVE_WRITER=1 PG_ABSTRACTIVE_WRITER_CONCURRENCY=24   # 24 requires B4 deployed; else 8
# hygiene + scoped question + fetch-yield halt
export PYTHONFAULTHANDLER=1 PYTHONIOENCODING=utf-8 PG_BENCHMARK_OFFICIAL_QUESTION=1 PG_MIN_FETCH_YIELD=0.30
# (provider_routing generator allow_fallbacks=true is a YAML change inside the gated commit, not env)
```

### corrected_launch_command
cd /workspace/POLARIS && git fetch origin bot/I-wire-001-integration && git reset --hard <GATED_12FIX_COMMIT_SHA> && OUT=outputs/paid_drb72_fresh3 && { [ -e "$OUT" ] && echo "ABORT: $OUT exists — pick a clean folder" && exit 1; } ; source <the verified_flag_slate above> ; setsid python scripts/dr_benchmark/run_gate_b.py --only drb_72_ai_labor --out-root "$OUT" --official-question > /workspace/paid_fresh3.log 2>&1 < /dev/null &

### readiness items
- [PASS] 1. Models (no gemma / wrong model drift) — box2_deep_env.sh pins PG_GENERATOR_MODEL / PG_MIRROR_MODEL / PG_EVALUATOR_MODEL / PG_ENTAILMENT_MODEL / PG_CREDIBILITY_JUDGE_MODEL all = z-ai/glm-5.2 (operator-approved all-GLM #1285; PG_PERMIT_GENERA
- [PASS] 2. Token max not starved — token_limit_resolver.py pins moonshotai/kimi-k2.6 at (262144, 262144); PG_FOUR_ROLE_REASONING_EFFORT=xhigh set; PG_SECTION_WRITER_MAX_TOKENS=24576, PG_AGENTIC_SUMMARY_MAX_TOKENS=24576, PG_STORM_OUTLIN
- [NEEDS_ACTION] 3. Credibility concurrency + slate — box2_deep_env.sh bakes ONLY PG_CREDIBILITY_PASS_WALL_S=6000. The rest of the proven slate (PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10 — THE parallel hang fix, PG_CREDIBILITY_JUDGE_POOL_WALL_S=2400,
- [PASS] 4. GPU device pins (2-card split) — mineru-vllm-server is running with CUDA_VISIBLE_DEVICES=1 (--gpu-memory-utilization 0.4, port 30000): nvidia-smi shows 34.0GB used on card 1, card 0 free. box2_deep_env.sh pins the pipeline to CUDA_VI
- [PASS] 5. Mineru server + client env — curl http://localhost:30000/v1/models returns MinerU2.5-2509-1.2B (max_model_len 16384) — server up and serving. Client env matches: PG_MINERU25_BACKEND=vlm-http-client, PG_MINERU25_SERVER_URL=http://
- [NEEDS_ACTION] 6. Full 12-fix flag slate (PART 3) — ZERO of the PART-3 fix flags exist anywhere on the box yet (expected — the gated commit is still in flight). Also MISSING from the box env: the two committed base flags (PG_CONSOLIDATION_NLI_SUBBUCKET
- [NEEDS_ACTION] 7. PYTHONFAULTHANDLER / IOENCODING / out-root / resume flag — PYTHONFAULTHANDLER=1 exists only in the wave-2 overlay script, PYTHONIOENCODING is unset everywhere — both go in the slate. Out-root: outputs/paid_drb72_fresh AND paid_drb72_fresh2 already exist with 
- [PASS] 8. FRESH-box special: search+fetch keys live, comparable question — LIVE-PROBED from the box: SERPER_API_KEY returned a real Google search result (SERPER_ENABLED=true, daily budget 50); ZYTE_API_KEY returned a 200 extract of example.com; OPENROUTER_API_KEY validated a

---

