# I-arch-007 — GENERATION 0-SOCKET STALL forensic (2026-06-16 ~20:30Z)

## Symptom (3 of 5 fixed runs wedged at generation entry)
- Q76 ssh7:23714 (pid2411), Q72 ssh4:27202 (pid2377), Q78 ssh5:27242 (pid2055): stage=`generation_in_progress`, but:
  - STAT=`Ssl` (sleeping), wchan=`ep_poll`, ~0 CPU (1-3 ticks / 4s).
  - ZERO established TCP connections (box-global ESTAB to :443 = 0). 53 orphaned socket fds, none connected.
  - `running_cost_usd` FROZEN to 7 decimals at the pre-generation value across 13-39 min (Q76 $3.3264, Q72 $3.0092, Q78 $3.2038).
  - ZERO generation log lines since `OpenRouter client initialized: deepseek-v4-pro` (19:49 Q76). Launch log frozen.
  - child count = 0 (NOT a subprocess/process-pool deadlock).
  - run_status.json `last_update_utc` advances ~1/min = a heartbeat thread, NOT work progress.
- Q75 ssh2:27070 = retrieval_done, running sentence-transformer Batches fine (CrossEncoder OK). Q90 ssh2:27886 = agentic round 12 (deep retrieval). Neither at generation yet → neither wedged.
- Old Q90 ssh1:35096 = pre-fix, separate, 8h+ unstamped.

## Root cause = documented "0-socket provider stall"
- `src/polaris_graph/generator/multi_section_generator.py:153-161`: KNOWN failure — a section LLM call where the provider (deepseek-v4-pro via OpenRouter) accepts then stalls with NO open socket, so the httpx read-timeout CANNOT fire (no socket to time out). The asyncio task wedges in ep_poll.
- ONLY mechanism that catches it = `PG_SECTION_WALLCLOCK_SECONDS` asyncio.wait_for (line 203): wait_for(wall) → TimeoutError → retry once → fail-loud → VISIBLE gap-stub for that section. Faithfulness-neutral (only affects WHETHER a section generates; strict_verify/NLI/4-role/provenance untouched).
- NOT a crash (CrossEncoder=0, torchvision=0). NOT credit exhaustion (OpenRouter credits 950 total / 796.79 used = ~$153 left). NOT the torchvision deploy defect.

## Why recovery is SLOW (and why I can't just tighten it)
- Gate-B slate (run_gate_b.py:499,1070) FLOORS `PG_SECTION_WALLCLOCK_SECONDS` to **9000s** (max(existing,slate)). Hierarchy is preflight-ASSERTED fail-closed (line 1344): per-call 6500 < section-wall 9000 < run-wall (live 21600). So I CANNOT set section-wall=1800 — preflight raises, and the #1248 forensic explicitly rejected 600/1800 as TRUNCATING legit sections (a 64000-tok section @ ~15 tok/s = ~4267s legit, so 9000s is the correct non-truncating backstop).
- Consequence: a persistently-wedged section waits 9000s (150min) → retry → 9000s → gap-stub = up to ~5h. Q76 wedged 19:49, backstop fires ~22:19 (attempt1) / ~24:49 (attempt2). Run-wall 21600s (6h) bounds the whole run. So runs are NOT lost — they're SLOW, and may gap-stub sections if the wedge is persistent.

## THE OPEN QUESTION (decides self-recover vs all-gap report)
- openrouter_client.py:274-276: generator is pinned `allow_fallbacks=false`; OpenRouter does NOT auto-advance off an empty 200; same-provider retry would re-stall. The blank-200 path excludes the blanking provider (`body['provider']['ignore']`), but a 0-socket STALL never returns a 200 — does the stall path trigger the same provider-exclusion on retry, or re-hit the SAME pinned provider and re-wedge?
  - If retry RE-ROUTES → runs self-recover (slowly).
  - If retry RE-STALLS on same provider → 2 attempts both wedge → gap-stub every section → all-gap report after burning ~5h. THE bad outcome.

## Decision fork (pending advisor)
1. LET RIDE to the 9000s backstop (respects forensic-validated design; risks 5h burn + gap-heavy report if wedge persistent + no re-route).
2. KILL pid-scoped + `--resume` from corpus_snapshot.json (all 3 have it — retrieval NOT lost) + relaunch. But relaunch hits same provider → may re-wedge immediately.
3. Provider-level fix: make the section retry/stall re-route to a healthy deepseek-v4-pro provider (or reduce PG_SECTION_MAX_TOKENS so the provider stops choking) — the real fix if wedge is persistent.

## RESOLUTION (2026-06-16 ~20:48Z) — confirmatory test + canary-first resume of all 3
- CONFIRMATORY REPRO (ssh7, live): deepseek-v4-pro pinned to **wandb** returned FINE (first token 0.8s, done 34.5s) AND baidu returned fine (10s). So WandB is NOT down now → the wedge was a TRANSIENT provider stall at ~19:49-20:08 that left the asyncio transport wedged on now-dead sockets (immune to read-timeout per the #1248 comment); the section wall-clock (9000s) had not yet fired. My "wandb-staller" hypothesis was DISPROVEN by the test (ran it before acting — correct call).
- FIX = kill slug-scoped + `--resume` from corpus_snapshot.json (retrieval NOT lost) + provider HARDENING via env: `OPENROUTER_PROVIDER_ORDER=baidu,siliconflow,novita,streamlake,deepseek,wandb` + `OPENROUTER_ALLOW_FALLBACKS=true` (takes the `elif provider_order` branch in openrouter_client.py:1936, allow_fallbacks stays true → a stall can advance instead of wedging; no Path-B active so it takes effect). Config file UNCHANGED (operator's wandb-lead pin persists for future runs).
- Executed all 3: Q76 pid131798 / Q72 pid128781 / Q78 pid99766. ALL passed BEHAVIORAL_CANARY_OK (live deepseek-v4-pro probe on startup). Re-running cheap gates from snapshot → generation. Watching whether they clear the multi-section generation entry (the real test).
- Q75 (ssh2:27070) + Q90 (ssh2:27886) still in retrieval on the ORIGINAL processes (stale wandb-first + allow_fallbacks=false config) → may wedge at THEIR generation transition. Q90 has no snapshot yet (mid agentic round 12) so can't pre-resume. PLAN: watch their gen transition; kill+resume with the same provider hardening if they wedge.
- Provider order env vars saved on each box: /root/q76_resume.env, q72_resume.env, q78_resume.env.

## SECOND WAVE (2026-06-16 ~21:04Z) — 2 more wedges caught by forensic sweep
- Q90 (ssh2:27886, ORIGINAL proc, old wandb-first config): entered generation 20:44, cost FROZEN at $3.1640237280000014 across 2 probes (20:59 + 21:01) while heartbeat advanced → SAME generation-entry 0-socket wedge, old config. Now had a corpus_snapshot (2.98MB) → kill+resume with provider fix → new PID 61866, BEHAVIORAL_CANARY_OK. WATCH generation entry.
- Q78 (ssh5, RE-WEDGED): first resume (pid99766) cleared gates to corpus_approval (20:48:52) then froze 13min — 0 CPU, ZERO sockets, do_poll — hung at the POST-APPROVAL credibility/semantic-conflict step (BEFORE generation; different spot than the generator wedge). The semantic_conflict/credibility are SIDE JUDGES (mirror/GLM, atlas-cloud-first routing) → the generator provider override may not cover them (allow_fallbacks=true should). Re-resumed → new PID 99950, BEHAVIORAL_CANARY_OK. IF it freezes a 3rd time at corpus_approval→credibility (cost $0.0, do_poll, 0 sockets) = DETERMINISTIC hang in that side-judge path → investigate src/polaris_graph/retrieval/semantic_conflict_detector.py + synthesis/credibility_pass.py for a missing per-call timeout; do NOT blind re-resume again.
- VERIFIED healthy (cost climbing + completed-generate log lines): Q76 (pid131798, 4-section outline, 1 section $0.0318), Q72 (pid128781, $0.042), Q75 (pid4382 ORIGINAL, $3.00->$3.16).
- WEDGE-vs-HEALTHY discriminator (no py-spy needed): HEALTHY = running_cost_usd CLIMBING across ticks + "generate completed" lines. WEDGED = cost FROZEN to many decimals across 2 ticks + 0 ESTAB to :443 + cpu_delta~0 + wchan ep_poll/do_poll. run_status last_update advancing is just a heartbeat thread, NOT progress.

## ROOT-CAUSE FIX FINDINGS (2026-06-16 ~21:32Z, workflow w0pjizcvq) — the systemic empty/non-JSON-response failure, 3 sites
Common cause: a provider returns an empty / non-JSON 200 ('Expecting value: line 1 column 1 (char 0)'); handled gracefully at the semantic-conflict judge (LABEL+SHIP) but HANGS/COLLAPSES at 3 other sites.

SITE 1 — section-body gen (Q76 wedge): first contract-slot call `_m63_llm_call` (multi_section_generator.py:6751-6770/6814-6825). BOUNDED by PG_CONTRACT_SLOT_STALL_TIMEOUT_S=1200 → 1230s wall (openrouter_client.py:1968-1980), but MAX_RETRIES=2 (bare const :909, NOT env) → up to 3×1230s=~61min freeze. Degrades to not_extractable gap (faithfulness-neutral). ENV FIX (no redeploy): PG_CONTRACT_SLOT_STALL_TIMEOUT_S=750 (>545s legit-regulatory floor; halves each wall). Full fix needs PG_LLM_MAX_RETRIES env-ize (code).

SITE 2 — entailment judge (Q72 wedge): entailment_judge.py judge() :423-549; empty-200 at :446 treated as generic-retryable → re-POSTs trickle socket → burns PG_ENTAILMENT_TOTAL_S=150s (HANG-J3 total-deadline _post_with_total_deadline :114-136). ENV FIX (no redeploy, HEAD has HANG-J3): PG_ENTAILMENT_TOTAL_S=45 (import-time→resume restart) + PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 (already set). Fail-closed DROPS the sentence (strict_verify.py:295-301, provenance_generator.py:2064/2236) — faithfulness STRICTLY PRESERVED. Code fix = explicit empty-200 short-circuit (faster, same drop).

SITE 3 — 4-role SENTINEL seam (THE curator_gap maker, OLDQ90): ONE claim's sentinel blank → BlankVerdictError → sentinel_adapter.py:426 RE-RAISES → sweep_integration.py:585-591 tears down WHOLE D8 seam → run_honest_sweep_r3.py:9917 hardcodes coverage_fraction=0.0 → curator_gap/held. ENV PARTIAL (no redeploy): PG_ALWAYS_RELEASE=1 + PG_REDACT_HELD_UNSUPPORTED=1 (both default-ON) → ships released_with_disclosed_gaps (unadjudicated body) instead of empty hold; PG_ROLE_CALL_TIMEOUT_S=900 bounds the stall. ENV CANNOT make it per-claim-continue. **CODE KEYSTONE (requires_redeploy=TRUE):** sentinel_adapter.py:426-435 route RoleTransportError → existing _FAIL_CLOSED path (UNGROUNDED+parsed_ok=False; the failed claim → UNSUPPORTED, seam CONTINUES with REAL coverage), gated `PG_SENTINEL_TRANSPORT_DEGRADE` default-ON, OFF=byte-identical legacy. Faithfulness STRENGTHENED (never returns GROUNDED on transport fault). This is what makes genuine 4-role beat-both vs unadjudicated-shipped.

### ENHANCED RESUME ENV (fold into every auto-resume; env-only, no redeploy):
... existing: OPENROUTER_PROVIDER_ORDER=baidu,siliconflow,novita,streamlake,deepseek,wandb + OPENROUTER_ALLOW_FALLBACKS=true
... ADD: PG_CONTRACT_SLOT_STALL_TIMEOUT_S=750 PG_ENTAILMENT_TOTAL_S=45 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 PG_ROLE_CALL_TIMEOUT_S=900 PG_ALWAYS_RELEASE=1 PG_REDACT_HELD_UNSUPPORTED=1
NEXT: build sentinel code fix (PG_SENTINEL_TRANSPORT_DEGRADE) + Codex-gate; deploy on the next box-restart (don't disrupt healthy runs solely for it; they ship via always-release meanwhile + get §-1.1 audited).

## CRITICAL ESCALATION (2026-06-16 ~22:02Z) — the real blocker is a VERIFICATION CONCURRENCY DEADLOCK, not a per-call timeout
- Monitor cycle (accuracy-fixed) shows Q76/Q72/Q78 ALL wedged at the post-generation entailment/4-role verification gate. Q78 was resumed WITH the full enhanced env (incl PG_ENTAILMENT_TOTAL_S=45) and RE-WEDGED at the same spot in ~8min.
- VERIFIED ON BOX (ssh5): deployed entailment_judge.py HAS the HANG-J3 mechanism (_post_with_total_deadline line114, PG_ENTAILMENT_TOTAL_S line111, fut.result(timeout=total_s) line126) AND PG_ENTAILMENT_TOTAL_S=45 IS set in the wedged proc env. So the per-call deadline is PRESENT + ACTIVE — yet the run still hangs 7+ min.
- SIGNATURE: cost frozen, 0 sockets, entailment "attempt 1/3" logged then NO attempt 2/3, and 23-64 WORKER THREADS parked in futex_wait_queue = a THREADPOOL/LOCK DEADLOCK in the parallel-verify phase (PG_PARALLEL_VERIFY=24), triggered by empty-response judges. A per-call timeout CANNOT break a lock-deadlock.
- CONSEQUENCE: env mitigations do NOT fix this. The current 5 (old code) keep deadlocking at verification; a new-5 cohort with ONLY the sentinel fix would ALSO deadlock here. Whack-a-mole resume is non-converging.
- CANDIDATE LEVERS (pending advisor): (a) ENV: PG_PARALLEL_VERIFY=1 (or small) -> serial verify, no threadpool deadlock, but slow; (b) CODE: fix the verify-concurrency deadlock (the entailment empty-response handling + the futex lock) — needs build+redeploy; (c) confirm whether the deadlock is the threadpool itself or a shared RLock (cost-ledger / 4-role write).
- Sentinel fix committed 376ac812 but NOT on any box (grep=0). Entailment empty-response code fix NOT built.

## CODE-CONFIRMED ROOT CAUSE (2026-06-16 ~22:14Z) — read the source, refuted the starvation theory
Read `provenance_generator.py:2552-2804` + `entailment_judge.py:160-370` directly (not guessed):
- **`PG_PARALLEL_VERIFY` default = 1 (SERIAL).** `_parallel_verify_workers()` returns 1 unless an explicit N>=2; the legacy serial loop is the byte-identical default. The wedged runs were launched with **PG_PARALLEL_VERIFY=24** → `strict_verify` takes the parallel branch (`ThreadPoolExecutor(max_workers=24)` + `_pool.map(_verify_in_context, ...)`, line 2803-2804).
- **Nested executors:** each parallel-verify worker → `_verify_one_findings_sentence` → `verify_sentence_provenance` → entailment `judge()` → which ALSO spawns its OWN `ThreadPoolExecutor(max_workers=1)` per call for the HANG-J3 deadline (entailment_judge.py:123) + `fut.result(timeout=total_s)`. So 24 outer workers each share ONE lazy-singleton httpx.Client AND each spin a nested deadline-watcher = the 23-64 `futex_wait` threads observed. Under empty/trickle 200s the nested deadline should fire at 45s, but the swarm contends on the shared client pool + cost-ledger writes → lock-deadlock the per-call timeout can't break.
- **Entailment STARVATION REFUTED.** Lines 347-362: effort is COERCED to `high` (any lower value forced up per 2026-06-13 §9.1.8 governance) and max_tokens defaults to 131072 (chain MIN). Comment 173-176: GLM bake-off PROVED `high`+that budget completes with valid JSON (finish=stop) — fix F19 already closed the blank-content starvation. So setting `PG_ENTAILMENT_REASONING_EFFORT`/`MAX_TOKENS` lower is a SILENT NO-OP; that was the wrong lever.

### CONFIRMED FIX FOR THE BEHAVIORAL-PROOF RESUME (faithfulness-neutral):
- **`PG_PARALLEL_VERIFY=1`** → serial verify = the byte-identical DEFAULT code path (NOT a relaxation; same verify_sentence_provenance gate, same kept/dropped). Removes the entire threadpool/lock dimension. Slower but COMPLETES; a deadlocked run is infinitely slow, so serial strictly wins here.
- KEEP the enhanced env (provider order + allow_fallbacks + PG_ENTAILMENT_TOTAL_S=45 + PG_CONTRACT_SLOT_STALL_TIMEOUT_S=750 + PG_ROLE_CALL_TIMEOUT_S=900 + PG_ALWAYS_RELEASE=1 + PG_REDACT_HELD_UNSUPPORTED=1).
- The 4-role D8 seam (AFTER entailment) still needs the SENTINEL CODE FIX (376ac812, PG_SENTINEL_TRANSPORT_DEGRADE) deployed to fully ship a genuine 4-role beat-both report. To prove ONE run end-to-end, the proof box needs BOTH serial-verify AND the deployed sentinel fix.
- PLAN: confirm via board which box is wedged at entailment; do a focused thread diagnostic on ONE to confirm futex_wait threads are in the verify pool; then resume that ONE box with PG_PARALLEL_VERIFY=1 (+ sentinel fix if past entailment) as the end-to-end proof BEFORE any new-5 cohort.

## FIVE FALSIFICATIONS (2026-06-16 ~22:55Z) — operator: serial is NON-VIABLE, make PARALLEL work; find the choke point, fix with Codex, resume
Operator directive (binding): one-at-a-time verify makes POLARIS commercially non-viable. DO NOT ship serial. Find the EXACT choke point in the 24-wide parallel verify, fix it (Codex-gated) so parallel works, then redeploy all 5 from nearest checkpoint.

Built `scripts/diagnostics/entailment_concurrency_probe.py` (bare judge) + `verify_path_concurrency_probe.py` (real strict_verify path) with faulthandler armed. Ran FIVE experiments; ALL returned GREEN (no deadlock):
1. bare judge, 24 threads, silent-sleep poison, Windows → OK (graceful "client has been closed").
2. bare judge, small pool + repeated poison, Windows → OK.
3. bare judge, small pool + repeated poison, LINUX box → OK ("[Errno 9] Bad file descriptor", graceful).
4. bare judge, TRICKLE poison (Cloudflare-style), LINUX box → OK.
5. REAL strict_verify(draft,pool), PG_PARALLEL_VERIFY=24 + PG_STRICT_VERIFY_ENTAILMENT=enforce, 180 sentences, trickle poison, LINUX → OK (3.6s, kept=162 dropped=18). The poison judge calls time out at PG_ENTAILMENT_TOTAL_S and DROP gracefully.

CONCLUSION: the deadlock is NOT the entailment judge's shared client (REFUTED 4×) NOR the strict_verify parallel orchestration in isolation (REFUTED 1×). A poison/trickle timeout is handled GRACEFULLY everywhere offline. The production wedge needs context my offline probes lack — leading hypothesis: the **asyncio event loop**. strict_verify (sync, spawns its own 24-thread pool) is called from `contract_section_runner.py:181 _verify_one_stream` inside the async section flow; if sections are offloaded to the asyncio DEFAULT ThreadPoolExecutor (loop.run_in_executor(None,...)) and that bounded default executor is exhausted while inner work needs it — or a sync verify-pool blocks the loop while something inside awaits a loop-bound primitive (the "Concurrency semaphore max=5" asyncio.Semaphore) — you get 0 sockets + all threads futex_wait. NOT yet proven.

### GROUND TRUTH IN FLIGHT: Q90 parallel + faulthandler (the definitive dump)
Q90 (ssh2:27886) relaunched 22:38 with PG_PARALLEL_VERIFY=24 + `/root/polaris/sitecustomize.py` (faulthandler.register(SIGUSR1, all_threads=True)) + PYTHONFAULTHANDLER=1. BEHAVIORAL_CANARY_OK. pid 67102. It re-runs generation from corpus_snapshot (~30-40min) then RE-WEDGES at verification. THEN: `kill -USR1 67102` → faulthandler dumps ALL Python thread stacks to the run log → read the EXACT lock/await that 64 threads are blocked on. That is the choke point. Q90 box has the dumper armed; the 4 healthy runs (Q72/Q75/Q76/Q78, all generating) do NOT (can't inject without restart).
NEXT: dump Q90 → identify exact choke point → write minimal parallel-safe fix (keep concurrency) + a red→green test (reuse verify_path_concurrency_probe harness, now targeted) → Codex gate → redeploy all 5 from nearest checkpoint. GH issue for the fix tracked under I-arch-007.

## BREAKTHROUGH (2026-06-16 ~23:33Z) — faulthandler dump pinpoints the REAL choke point: the ADVISORY credibility pass
SIGUSR1 dump of the stalled Q90 (pid 67102, generation_in_progress, futex=1, 0 sockets, frozen 19min since 23:14:26 "[provenance] entailment_passed_on_local_window ev=ev_184"). Saved: outputs/audits/iarch007_death_forensic/q90_genstall_faulthandler.txt.

THE STUCK STACK (thread 0x...c507640):
  threading.wait <- futures/_base.py result <- entailment_judge.py:126 _post_with_total_deadline (fut.result) <- :430 judge
  <- provenance_generator.py:2056 verify_sentence_provenance <- credibility_pass.py:236 _verify_member_in_isolation
  <- :304 _assemble_baskets <- :521 _run_chain <- :400 run_credibility_analysis <- concurrent.futures.thread._worker
  nested worker (thread 0x...21fd640): httpx.post -> httpcore -> ssl.py:1168 read  (STUCK on a trickle socket)
  main thread (0x...1f81740): asyncio loop select/run_forever <- run_gate_b.py:2253 main

WHY MY 5 PROBES WENT GREEN: I tested strict_verify + the bare judge. The wedge is in a DIFFERENT path — the ADVISORY
credibility pass (`PG_SWEEP_CREDIBILITY_REDESIGN` slate ON, log "credibility-redesign slate: on=True required=False"),
which ALSO calls verify_sentence_provenance -> the SAME entailment judge singleton, but with NO wall-clock bound on the
pass itself. A single trickle-socket judge call (HANG-J3 _post_with_total_deadline) hangs and there is no outer timeout
to degrade the ADVISORY pass -> the whole run freezes on a non-binding step.

KEY: credibility_pass is ADVISORY (credibility_pass.py:215/335 — "NEVER re-run as a gate", "basket_verdict is a pure
LABEL... never feeds is_verified/strict_verify"). So bounding/degrading it on timeout is FAITHFULNESS-NEUTRAL (strict_verify
+ 4-role D8 remain the only binding gates). Fix direction: (a) wall-clock bound the advisory credibility pass -> degrade to
priors-only + disclosed-gap on timeout (matches its existing judge_error LABEL-not-HOLD posture); (b) root-fix the entailment
judge trickle-hang / shared-singleton-client-close leak so it cannot hang in ANY caller. NOT PG_PARALLEL_VERIFY (that is
strict_verify's pool — a different path; sister-session directive #2 targets the wrong pool for THIS wedge). Sister #1
(deploy 376ac812 PG_SENTINEL_TRANSPORT_DEGRADE) IS correct + separate (the D8 4-role seam, ~177 claims) — bundle it.

THREE DEATH MODES (all 5 runs, 2026-06-16 night): (1) generation 0-socket stall (Q90/Q72/Q76 frozen post-outline, futex=1,
0 sockets, cost frozen 1-3h); (2) advisory credibility-pass entailment trickle-hang (THIS dump; Q75 heading in); (3)
abort_excessive_gap (Q78: only 2/6 sections verified < 40% floor -> refused to ship, postgen_checkpoint.json saved).
NOTE: postgen_checkpoint.json ALREADY EXISTS (Q78 log) -> a post-generation resume checkpoint is partly built already.

## Hard constraints
Faithfulness NEVER relaxed. The 9000s wall is faithfulness-neutral but DON'T tighten below the legit-section ceiling. Open-weight only. PID/slug-scoped kills ONLY. corpus_snapshot.json enables --resume (no retrieval loss). SERIAL VERIFY IS NON-VIABLE (operator 2026-06-16) — the fix MUST keep parallel.

## INCIDENT 2026-06-16 19:13 — death-fix ITEM-1 reverted by a colliding writer; breadth never built
**Detected during loop tick.** Between 19:02 and 19:13:
- ITEM-4 (sentinel transport degrade) was COMMITTED as 376ac812 (sentinel_adapter.py + test only) — GOOD, that piece is durable.
- ITEM-1 (credibility-pass wall-deadline in multi_section_generator.py, the HANG keystone) was REVERTED: working tree == HEAD, `git log -S PG_CREDIBILITY_PASS_WALL_S` finds NOTHING, no dangling commit / worktree holds it. Most likely a `git restore multi_section_generator.py` by a sibling agent isolating the sentinel commit or avoiding the breadth collision. The other death-fix items (1b credibility_pass.py, 2a entailment_judge.py, 5 generation_snapshot.py, 6 run_gate_b/run_honest_sweep, all death tests) are STILL in the working tree (uncommitted).
- Breadth item-2 production code (weighted_enrichment.py + flag + append) was NEVER built — the breadth workflow produced only 2 test files (test_resolver_multicitation, test_breadth_corroborator_faithfulness), test-only. weighted_enrichment.py absent, PG_BREADTH_ENRICHMENT_ENABLED unwired.

**ROOT CAUSE = multiple parallel workflow writers on shared files (multi_section_generator.py) without a single-writer lock — exactly the advisor's warning.** Collision is now over (no live codex/python procs; last write 19:03).

**RECOVERY PLAN (single writer = me, direct edits; Codex = gate):**
1. Re-apply ITEM-1 wall-deadline to multi_section_generator.py from the exact 19:02 diff (in-context): `_cred_pass_wall_s = float(os.getenv("PG_CREDIBILITY_PASS_WALL_S","600"))`; wrap the `asyncio.to_thread(run_credibility_analysis...)` in `asyncio.wait_for(..., timeout=_cred_pass_wall_s)`; `except (asyncio.TimeoutError, CredibilityPassError)`; `_cred_cause` TimeoutError branch; logger + disclosed-gap use `_cred_cause`.
2. Build breadth item-2 in the SAME file pass (single writer): new weighted_enrichment.py + `_breadth_enrichment_enabled()` default-OFF + ~8-line append AFTER credibility resolves (~:6707 NOT :6482) + PG_BREADTH_ENRICHMENT_ENABLED=1 in run_honest_sweep_r3 Gate-B slate + mandatory negative-control test.
3. ONE combined Codex diff gate. NO more background workflows touching src.
4. Smoke (ast.parse + targeted tests) before gate.
Faithfulness NEVER relaxed.

## COLLISION-2 2026-06-16 ~19:30 — I (Claude) became a 2nd writer DURING the live workflow (operator-flagged)
The `iarch007-breadth-build` Workflow was STILL RUNNING (3/4 agents, 32m, 442k tok) building weighted_enrichment.py + the append. I wrongly concluded at 19:13 it was test-only (weighted_enrichment.py absent then) and hand-edited multi_section_generator.py (keystone restore + breadth append) + created weighted_enrichment.py BY HAND. That is the SAME two-writer collision I diagnosed — caused by me.
RULE GOING FORWARD: the WORKFLOW is the single writer for breadth. I do NOT hand-edit src while it runs. When it completes -> reconcile to ONE coherent version (mine vs workflow's), confirm keystone present (re-apply once if missing), one combined Codex gate. Do NOT revert now (agent may be mid-write). FREEZE until the workflow completion notification.

## RE-PREFLIGHT GO 2026-06-16 ~21:42 — hardened tree clears the gate
Re-preflight w35wp5o00 lane verdicts (from journal): death hang_possible=FALSE / overall=no_hang_possible (residual CLOSED); caps any_contract_or_source_cap=FALSE; cites basket_multicitation_wired=TRUE + single_source_anywhere=FALSE; faith any_gate_moved=FALSE; Codex gate APPROVE no_hang=true 0 P0/P1 (confirms role-POST force-close+RoleTransportError + credibility-judge total-deadline). All 4 operator non-negotiables PASS. (Synth agent rate-limited writing its prose report — verdict taken from the authoritative lane results.) DECISION: GO. Awaiting operator go for the paid 5-box deploy/resume per state/iarch007_deploy_recipe.md.
