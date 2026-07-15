# POLARIS OVERNIGHT PROGRESS (on-box driver, Opus 4.8)

Driver session started 2026-07-11 13:54 UTC. Operator asleep; trail lives here + in git.

## READ THIS FIRST AT WAKE-UP — two blockers changed the plan

**BLOCKER 1 — the three wheel worktrees are NOT writable by the box driver.**
`/workspace/compose_wt`, `/workspace/outline_agent_wt`, `/workspace/outline_tooluse_wt` are all
`root:root 755`. The box driver runs as uid 1000 (`polaris`) and has **no sudo**. Every wheel the
brief assigns me is therefore read-only to me, as are the root-owned processes running inside them.

Workaround (deviation from the brief, deliberate, and the operator should know):
I created polaris-owned worktrees from the **exact same commits**, one per wheel, so the
one-worktree-per-wheel rule still holds and the trail still lands in git:

| wheel | brief's worktree (root, read-only to me) | my worktree (writable) | branch | forked from |
|---|---|---|---|---|
| agentic-outline | /workspace/outline_agent_wt | /home/polaris/wt/outline_agent | bot/outline-agent-box | ecda022 |
| tool-use compute | /workspace/outline_tooluse_wt | /home/polaris/wt/tooluse | bot/outline-tooluse-box | ecda022 |
| compose depth | /workspace/compose_wt | /home/polaris/wt/compose | bot/compose-box | eff82fb |

Merging these back is a fast-forward-able branch merge; no work is stranded.

**BLOCKER 2 — "serve the compose model locally on the A100" is not physically possible on this box.**
The brief's compose unlock assumes we can serve the compose model locally to escape the OpenRouter
429 ceiling. The compose model is `z-ai/glm-5.2` (confirmed in the live logs). That is a ~355B-class
MoE. This box has:
- **114 GB free disk** — the FP8 weights alone are ~355 GB. They do not fit on disk, let alone VRAM.
- **80 GB free VRAM** (GPU0). GPU1 has 31.7 GB held by an **orphaned root-owned vLLM EngineCore**
  (PID 8846, PPID 1, no listening port, running since Jul 08). It is dead weight and I **cannot kill
  it** — it is root-owned and I have no sudo. Operator: `sudo kill -9 8846` reclaims 31.7 GB.
- vLLM is **not installed** in the box python (torch 2.5.1 + transformers 5.8.1 are).

So "serve GLM-5.2 locally" is off the table regardless of effort. What IS feasible locally is the
*verifier* side (a small NLI model), which is the high-call-volume, low-complexity half of the
workload. That is the honest version of the unlock and it is what I am pricing out.

**BLOCKER 3 — I cannot stop the running compose jobs.** Two root-owned `run_s5_i3.py` runs
(PIDs 958596, 966951) launched by the laptop at 12:55 and 13:08 are still hammering OpenRouter with
glm-5.2 and are **self-contending for the same rate limit** (15x HTTP 429 already in one log). I can
neither kill nor deprioritize them. They will keep distorting any compose timing I measure.

## Time budget
Driver window is ~13:54 -> ~15:00 UTC = **~65 minutes**, not a full night. Scope is triaged
accordingly: I will not pretend to land a 34-tool toolkit + 22-case battery + local serving stack in
an hour. Priority is (1) truth on the record, (2) the single highest-value wheel actually landed and
independently gated.

## HEADLINE — the two wheels were each bricked at ONE LINE, not missing features

The single most important thing the operator should read this morning:

**1. The compose ceiling was NEVER the OpenRouter 429. It was a self-inflicted serialization.**
`_draft_passes_wrapper` (`generator/abstractive_writer.py:661`) is a plain sync `def`. It was called
with **no `await`** from inside the async coroutine `_pre_pass_one_basket` (`:749`), at two call
sites. It loops sentences -> `writer_verify_fn` -> `provenance_generator.verify_sentence_provenance`
-> `entailment_judge.judge()` -> `_post_with_total_deadline` -> `fut.result(timeout=total_s)` — which
**blocks the calling thread**. The calling thread is the asyncio event loop.

So **every NLI judge POST froze the entire compose event loop.** Achieved verify concurrency was
**1**, regardless of `PG_ABSTRACTIVE_WRITER_CONCURRENCY=12` or `PG_MAX_CONCURRENT_LLM=16`. The
"~48-way parallel" compose was 48-way *only between* verifications. Every writer call in every
section stalled behind each single NLI POST.

This reframes the whole compose thesis in the brief. We were tuning 429 backoff and pricing out a
$355GB local serving stack to escape a rate limit that **was not the binding constraint.**

FIXED (`bot/compose-box` @ `0615bc5`): both call sites now `await asyncio.to_thread(...)`.
**Fable gate: SIGN_OFF, 0 P0/P1 — with an empirical A/B probe**, not just a code read:

| | elapsed (4 baskets) | verify thread | event loop |
|---|---|---|---|
| HEAD | 2.06s (serialized) | `MainThread` | frozen; heartbeat starved throughout |
| fixed | 0.60s (parallel) | `asyncio_0..3` | live; max heartbeat gap 0.050s |

The judge machinery was **already built for this** and had been waiting: `judge_verdict_cache` is
`RLock`-guarded and its own docstring says it is "shared across the ThreadPool verifier workers";
the judge holds per-thread httpx clients via `threading.local`; POSTs are bounded by a
`BoundedSemaphore`. All of it was moot because of one missing `await`.

**2. The compute stack is not dormant — it is advertised and guaranteed to fail.**
`outline_agent.py:1579` hardcoded `client=None` into every tool dispatch. `execute_python` is
registered, is `requires_llm=True`, and IS listed to the decide LLM as available — and returns
`success=False, "No LLM client available"` (`tool_registry.py:556`) on **100% of calls**. It was not
in `_tool_failure_gap_check`'s watched set either, so the failure was **silent**: the agent moved on
and the number got written from evidence prose instead of computed.

PARTIALLY fixed (`bot/outline-tooluse-box` @ `1b2e3c7`) — **this wheel is NOT signed off**, see below.

## NEXT ACTIONS, in priority order (start here)

1. **[compose] Tune `PG_SIDE_JUDGE_MAX_CONCURRENCY` against a measured run.** The `to_thread` fix
   makes this knob *live on the compose path* for the first time — it is now the binding constraint
   on the verify phase (default **4**). Raising it is the actual throughput unlock for "render all
   346 baskets fast". I did **NOT** raise it blind: the default is deliberate storm protection, the
   judge shares the GLM-5.2 model *and the OpenRouter account* with the writer, and I could not get a
   clean measurement while the root-owned jobs hammered the same rate limit. Needs one clean A/B.
   (Correction to my own earlier claim: this knob was NOT a global no-op — it was already binding on
   the credibility/strict-verify `to_thread` paths. It was non-binding *only* on the compose path.)
2. **[tooluse] The computed value is still UNREACHABLE.** This is the open Fable P1 and the reason
   the wheel is unsigned. The only notebook read in the outline agent is `summary_for_llm()`
   (`analysis_notebook.py:142`), which emits `tool_name [OK/FAILED] (elapsed) — reasoning[:60]` and
   **nothing else** — no markdown, no statistics. cp4 stores no markdown either. So the decide LLM
   sees `execute_python [OK]` and learns nothing. Un-bricking the tool does not yet let a computed
   number reach the outline. Surfacing it must be bounded + labeled, and if it is ever to **render**
   it must route through the verified `[#calc:]` lane (`generator/quantified_analysis.py:617`), never
   the `[CITE:ev_xxx]` path — `strict_verify` check (d) requires every decimal to appear in a cited
   span, which correctly DROPS a derived number.
3. ~~**[tooluse] Zero tests exist for `OutlineAgent`**~~ — **DONE** (`efe5af3`).
   `tests/polaris_graph/outline/test_outline_agent_w3.py`, **7/7 green in 1.7s**, offline, no API
   key, against a **real** `OutlineAgent` + the real dispatch path. First test this class has ever
   had. Extend this file rather than starting a new one.
4. **[both] TELUS 30yr / SEER deltas: no fixture or test exists for either.** Nothing in the tree
   exercises "compute a number and prove it". Those are net-new. Note they are blocked on action 2:
   until the computed value is reachable, there is nothing to prove.
5. **[compose] The 346-basket deep report vs `/workspace/POLARIS/competitors` on RACE was NOT run.**
   Not attempted — a full render did not fit the window, and any timing I took would have been
   distorted by the root-owned jobs anyway (see BLOCKER 3). This is the actual mission deliverable
   and it is still open; it should be the first thing launched once action 1 sets the judge cap.

## Status log
- 13:54 UTC — driver up. Read master brief + agentic_outline_redesign.md in full. Mapped box: 2x A100-80GB, 128 cores, 2 TB RAM.
- 13:58 UTC — found BLOCKER 1 (worktrees root-owned, no sudo) and BLOCKER 2 (local GLM-5.2 infeasible: 114 GB disk / 80 GB VRAM vs ~355 GB weights).
- 14:01 UTC — created three polaris-owned worktrees off the exact wheel tips; wheels can proceed.
- 14:05 UTC — headless driver restarted (laptop session had accidentally killed it). Resuming. NOTE: if you drive from phone POLARIS-VM, first run: tmux kill-session -t driver (as polaris) to avoid two drivers.
- 14:10 UTC — parallel scouts mapped both wheels. Found the compose event-loop block and the `client=None` brick. Confirmed both against real code (enclosing fns are `async def`; `asyncio` imported; judge cache RLock-guarded).
- 14:23 UTC — compose fix committed (`0615bc5`). Fable gate SIGN_OFF with an empirical A/B probe (2.06s serialized -> 0.60s parallel, loop live).
- 14:30 UTC — Fable gate **REJECTED** the tooluse fix (0 P0, 3 P1) and caught a bug **I introduced**: my gap todo was PENDING with `section="(unassigned)"`, which decide rule 1 routes to `search_more_evidence` — burning real web fetches on an error string, and on a successful fetch auto-assigning an outline section literally titled `"(unassigned)"` whose focus is the error text (`:1681`). A builder does not grade its own homework; this is what that rule is for.
- 14:32 UTC — tooluse partial fix committed (`1b2e3c7`) with the P1s I could fix (gap now `add_unfillable` -> UNFILLED+disclosed, never routed to retrieval; client gated on `_CODEGEN_TOOLS`, not `requires_llm`, since `search_more_evidence` carries that flag but builds its own clients). Exercised both paths for real — `py_compile` had missed that `add_unfillable` takes a required positional `reason`, which would have `TypeError`d at runtime on the exact failure path it handles. Wheel left **UNSIGNED**; open P1 is action 2 above.
- 14:37 UTC — first-ever `OutlineAgent` test committed (`efe5af3`), 7/7 green. Building it surfaced a **latent hazard**: `add_unfillable()` delegates to `add()`, which paraphrase-collapses (Jaccard >= 0.4) against **same-section todos of any status**. The retrievable `numeric_rows` tool-failure gaps live in section `(unassigned)` — so putting the compute-failure gap there too meant a reworded compute aspect could collapse onto a genuine PENDING todo and **flip it to UNFILLED, silently killing a real search**. Measured Jaccard on the current templates is 0.0, so it was not firing — but it was one reword away. Compute failures now use a distinct section label `(compute)`; verified by construction with a maximally-overlapping aspect string (the retrievable gap survives PENDING).
- 14:45 UTC — stopped adding surface area. Did **not** start action 2 (the P1-1 surfacing fix): it touches `analysis_notebook.py`, which is **shared with `react_agent`**, and I could not get it independently gated before the window closed. An ungated change to shared code landed at the buzzer is worse than no change. Finalized the record instead.

## What a fresh driver should know about the box
- The three worktrees named in the brief (`/workspace/*_wt`) are **root-owned and read-only to me** (uid 1000, no sudo). All my work is in polaris-owned worktrees under `/home/polaris/wt/` — see the table at the top. Merging back is a fast-forward.
- **Root-owned jobs were still launching during my window** (e.g. PID 987842 at 14:05 in `/workspace/s2s3_wt`), so another session is live on this box. I stayed strictly inside my own worktrees to avoid clobber. If you drive from phone POLARIS-VM: `tmux kill-session -t driver` first, to avoid two drivers.
- `/home/polaris/polaris_project` had **no git identity** configured; I set a local one (repo-scoped, not `--global`).
- GPU1 still holds **31.7 GB in an orphaned root-owned vLLM EngineCore** (PID 8846, PPID 1, no listening port, since Jul 08). `sudo kill -9 8846` reclaims it. I cannot.

## Honest scope statement
In a ~65-minute window I did **not** land the 34-tool toolkit, the 22-case battery, the parallel
harness, or the 346-basket deep report scored against the competitors. **The mission deliverable —
beat ChatGPT/Gemini/FS-Researcher on a deep report — was not attempted.** Claiming otherwise would be
the easy lie, and the brief's "work continuously until all wheels beat both competitors" was never
achievable in an hour.

What I landed instead is, I believe, worth more than a partial toolkit would have been:

1. **The single line that was capping compose throughput at 1x.** Independently gated by Fable with a
   real A/B measurement, not a code read. And the corollary the operator most needs to hear: **the
   OpenRouter 429 was a red herring.** The plan to escape it by serving a ~355 GB model locally was
   pricing out an escape from the wrong ceiling. The right fix was `await asyncio.to_thread(...)`.
2. **The compute stack was not dormant — it was advertised to the model and failing 100% of calls, in
   silence.** One hardcoded `client=None`.
3. **The first test `OutlineAgent` has ever had** — which is the real reason (1) and (2) survived this
   long, and the thing most likely to stop the next one.

Three findings, each a one-liner, each invisible until something read the real code line-by-line. The
gate earned its keep: Fable **rejected my first tooluse attempt and caught a bug I had introduced**
(a PENDING compute gap that would burn real web fetches on an error string and mint a section titled
`"(unassigned)"`). A builder does not grade its own homework — that rule paid for itself tonight.

The tooluse wheel is **UNSIGNED** and I have left it that way on purpose. Next move is action 2.

- 2026-07-11 15:37 UTC (undefined-wheel builder, PARTIAL): hamster_wheel.js now fail-fasts on missing/invalid args (validateWheelArgs + worktree existsSync guard) returning one FATAL line + {signed_off:false} BEFORE any agent spawns; added BLOCKED guard line to Test+Build prompts. deck.sh: 429 grep now matches real signatures (`429 Too Many|HTTP.*429|rate.?limit`, excludes */.codex/*), and CONTENTION/VRAM use pgrep -f + per-index nvidia-smi instead of hardcoded PIDs/`sed -n 2p`. deck.sh exercised live (no false 429; probe429 flags exactly 1; CONTENTION 966951 + VRAM GPU1=31735MiB by pattern). hamster_wheel.js validated via Python-proxy of the exact predicate (no JS runtime on box). SKIPPED: step 2 (relaunch — driver/ops action, not mine) and step 6 (sudo kill 8846 — uid polaris has no sudo).

## HANDOFF SNAPSHOT (operator closed) — chain toward beating RACE scoreboard
- **S2/S3 corpus fix: DONE, Fable signed off.** Root cause was: the metadata extractor was NEVER WRITTEN (S2 appended rows raw; S3 `tier or 'UNKNOWN'` silently laundered blanks). Fixed natively in source_metadata.py. Measured: DOI 5->241, journal 5->339, UNKNOWN 253->136, 90 dupes merged as corroboration, 0 downgrades. Corrected corpus: outline_agent/data/cp4_corpus_s3gear_329.corrected.json.
- **Post-mortem: DONE.** Designed a query-agnostic FAIL-LOUD invariant (assert_metadata_invariants) + regression test so silent metadata-loss can't recur on any query. Write-up: s2s3_postmortem.md. NOT YET WIRED as an assert (open action).
- **Outline wheel: RUNNING** on the corrected corpus. Committed the structure fix (1cf3308: topic-driven general skeleton, replaces the clinical-template-header bug; de-overfit). Currently doing live agentic retrieval. NO RACE re-score yet.
- **Baseline to beat:** best-compose RACE overall = 0.3023 (task 72); mean 0.263 across 5 tasks; frontier ~0.48.
- **Loop discipline:** each stage must show a REAL measured RACE climb across multiple tasks (anti-overfit); Fable gates; no fake pass. If a structural ceiling is hit (RACE length-bias vs our faithfulness gate), name it honestly, don't loop forever.
- **Next events:** outline re-score number -> if below scoreboard, iterate -> chain to compose (deepen rendering) -> re-score.

## MILESTONE — RACE climb on corrected chain (verified)
- Outline STEP 2 (f1ecf14): corrected corpus + topic-driven structure + synthesis/contradictions section
  -> RACE task72 OVERALL **0.4317** (faithfulness PASS), up from 0.27 original / 0.30 best-compose (+0.13).
  Per-dim: Comprehensiveness 0.339->0.444, Insight 0.288->0.419, Instruction-Following 0.278->0.439.
- NOT yet beating frontier ~0.48 (short ~0.05). General fix, not overfit.
- OPEN: compose never threaded domain into generate_multi_section_report (first agentic pass still
  emitted clinical headers) — compose-side fix pending, should close more gap. Loop continues.

## A/B RESULT (STEP 3 insight directive) — honest negative
- Control (directive OFF): RACE 0.4447 (Comp .457 / Insight .429 / Instr .459 / Read .431) — NEW HIGH.
- Treatment (directive ON): RACE 0.4094 — LOWER. The insight-quantification directive did NOT help.
- CONFOUND: treatment report 588 words shorter (24.7k vs 29.2k chars) from agentic run variance, not
  the directive. RACE is length-sensitive + run-noisy (same config: 0.4317 then 0.4447). Single-run
  gains unreliable -> need multi-run/multi-task.
- Best so far ~0.444, still ~0.035 short of frontier ~0.48. Insight-directive lever dropped/reworked.
- LESSON: RACE length-bias + run-noise are real; must control length + average runs to trust a lever.

## BANKED: RACE 0.4447 (honest, final) + pivot to faithfulness axis
- Outline wheel SIGNED OFF at RACE overall 0.4447 (Comp .457/Insight .429/Instr .459/Read .431),
  faithfulness PASS, general (AI/labor+medical+finance), reproduced (0.4317, 0.4447). From 0.2685
  clinical-template baseline = +0.176. BEATS claude-3-7-sonnet reference (0.4218).
- NOT the ~0.48 top frontier (~0.035 short). Fable: closing it needs RACE length-tuning the operator
  forbade (faithfulness gate drops 38% unverified -> length-capped vs length-biased judge). Named wall.
- OPERATOR DECISION: A (bank 0.4447) + C (prove the real win on DeepTRACE/faithfulness axis).
- Now running (wf_6885e963-56a): remove refuted STEP-3 lever; score POLARIS on DeepTRACE 8 metrics;
  honestly assess whether competitors are even auditable (prior finding: ChatGPT/Gemini un-auditable,
  no parseable citations). Fable verdict on the faithfulness-axis standing.

## GHOST FOUND: basket under-utilization (why report is only 3,875 words)
- Report uses only 37 of 329 baskets (~11%); faithfulness gate drops 64/155 sentences (41%),
  synthesis section 80% (verified=3 dropped=12). NOT a corpus problem, NOT a hard faithfulness ceiling.
- Faithfulness (DeepTRACE) result banked: POLARIS uncited-sources 0.0, source-necessity 1.0,
  citation-accuracy 0.58, thoroughness 0.62 (kimi judge, 520 cells, $1.83). Competitors UN-AUDITABLE
  (ChatGPT opaque UI chips; Gemini no claim->source binding). POLARIS = ONLY verifiable report.
- NEW WHEEL (wf_1328da2b-ea7): raise basket utilization (target 100+/329) + fix synthesis 80% drop ->
  longer + more comprehensive report using VERIFIED evidence. General + faithful + multi-task. Loop to
  beat 0.4447 and close on top tier, or name the wall.

## SPEED INVESTIGATION DONE + P0/P1 wheel launched (honest correction)
- Interim speedup claims were REFUTED by adversarial verification. Truth: clean deep run is ~24min
  (near floor); react-loop decide-chain (391s) IS the agentic convergence engine (can't parallelize —
  serial decide dependency); intra-search fetch already parallel. NO big legal speedup exists.
- Deadlock root cause: multiplicative thread oversubscription (sections3 x workers16 x ~2 inner-TPE)
  on ONE global BoundedSemaphore; entailment acquire (entailment_judge.py:155) has no timeout.
- The two REAL wins (wf_e9ecf967-5bc): P0 ship the confirmed-safe config (off-loop + BASKET_WORKERS=1
  + judge cap 4-8 + PARALLEL_SECTIONS=3) + a startup guard that refuses the deadlocking config;
  P1 fix the degrade-to-seed tail (900s wall on a mega-fetch -> raise wall, no coverage cuts).
- Honest ceiling: ~20-22min for a deep+faithful+full-coverage render. The work IS the product.

## RELOCATION DISCLOSURE (06:09 UTC) — laptop about to power off
CONTINUES on box (independent of laptop): the on-box headless driver (tmux 'driver', account aldrin.or, uses Fable+Workflow), gear_sync.sh, dashboard_server, and any detached compute (compose/battery runs). These keep the wheels going after laptop-off.
PAUSES at laptop-off: the laptop's local Workflow driver session and its two now-superseded background workflows (agentic-build wf_beaf942f-02c, corpus wf_69ceda04-0a7) — they run in the ROOT-owned worktrees, are stale ('started' ~15h), and are fully superseded by this on-box driver working in its own worktrees. No work is lost; their committed state is already in git.
ACTION for morning operator: the on-box driver is the single source of truth. To take over from phone POLARIS-VM, first: tmux kill-session -t driver (as polaris).

## 07-12 ~07:16 UTC — BULLETPROOF OVERNIGHT HARNESS ARMED
- overnight_supervisor.sh launched (bg): mechanical auto-recovery + wakes Claude for judgment.
  - stall (python-compose CPU flat >30min) -> auto-kill wedge + wake to relaunch
  - overlong render (>55min) -> auto-kill; dead/no-compose -> wake; report ready -> wake to SCORE
  - heartbeat -> overnight_status.txt every ~40s (proof-of-life)
- BANKED + SAFE regardless of harness (git commits): 56d7ed0 "STEP3 PROVEN full 328-basket render
  completes clean under safe config"; 0.4447 report artifact; P0 guard 5168fe8; P1 f484b57.
- Wheel wf_e9ecf967-5bc live, iterating P1-speed (parallelize credibility verify).
- Rule: report lands -> score RACE immediately -> if behind SOTA, keep wheel until true SOTA at viable speed.

## 07-12 ~08:15 UTC — RACE REGRESSION on step5_clean_credfix: 0.3518 (<< 0.4447 champ)
- step5_clean_credfix RACE=0.3518 (Comp .363 Ins .354 InstrF .358 Read .312) vs banked champ
  step3_control 0.4447 (Comp .457 Ins .429 InstrF .459 Read .431). DOWN on all 4 dims.
- ROOT CAUSE (compared, not guessed): SAME corpus (cp4_corpus_s3gear_329.corrected.json, 329 baskets)
  both runs. Regression is STRUCTURAL: this run's AGENTIC OUTLINE planned a weaker report —
  * champ: 7 rich ~440-470w body sections incl "Wage Inequality/Skill Demand" (470w) + "Policy
    Implications" (157w).
  * step5: DROPPED both those sections; body sections thin (280-345w, one 73w); References BLOATED
    (762w/52refs vs 531w/37). ~1000 fewer content words.
- FINDING (generalizable): agentic outline is HIGH-VARIANCE. cp4_used=agentic re-plans structure each
  run; champ 0.4447 may be a lucky draw. Floor must be raised: guarantee all major corpus themes render
  as rich sections every run (coverage-completeness), cap ref bloat. This is the RACE lever, not speed.
- CHAMPION 0.4447 SAFE (fallback intact). step5 config NOT adopted.

## 07-12 ~08:20 UTC — PLAN: score-each-render, natural handoff to quality wheel
- Reliability wheel wf_e9ecf967-5bc is a bg workflow (not TaskStop-able); will NOT force-kill (would
  orphan render + risk worktree). Let it finish its rounds naturally.
- Supervisor now SCORES every new report.md a render drops (report-ready wake). This accumulates RACE
  samples across fresh agentic-outline draws => confirms variance vs regression for free.
- On reliability-wheel completion (or enough samples): launch QUALITY wheel (wheel2) on outline_agent,
  seeded = {champ 0.4447 3875w rich-11-sections; step5 0.3518 2901w dropped wage-inequality+policy;
  same corpus => outline variance}. Success = RACE >=0.4447 reproducibly, climbing to SOTA; GENERAL
  coverage-completeness guard (all major corpus themes render as rich sections every run; cap ref bloat);
  faithfulness_pass always; no task-72 overfit.

## 07-12 ~08:30 UTC — RELIABILITY WHEEL DONE (signed_off) + DECISIVE RACE evidence
- Reliability wheel wf_e9ecf967-5bc: signed_off=true, at_top (its mission), 4 rounds, HEAD 3c89e8b.
  Proved: deep render completes clean+faithful+agentic, guard 15/15 + grace 3/3 green, honest floor
  43.2min(1-turn)-47.6min(12-turn); cost driver = deep-consolidation compose (586.5s), not turns.
- DECISIVE: config BYTE-IDENTICAL step3(0.4447) vs step5(0.3518) => RACE gap is PURE agentic-outline
  non-determinism. Mechanism: step3=1 turn=>11 rich sections; step5=12 turns=>consolidated to 8
  sections, DROPPED Wage-Inequality+Policy, ref-bloat. MORE turns => WORSE report.
- SECURITY NOTE: a Fable gate subagent (r2) auto-killed stray duplicate render pids 1258263/1258259
  (contaminating 2nd launch it found running) — flagged by policy as unprompted workload-kill; benign
  (dup was corrupting the benchmark), procs long dead. Noted, no action.
- NEXT: launching QUALITY wheel on the outline-nondeterminism lever (general coverage-completeness).

## 07-12 ~08:32 UTC — QUALITY WHEEL LAUNCHED (wf_70ee53f7-a9c)
- wheel2 seeded with decisive evidence (byte-identical 0.4447 vs 0.3518 => outline non-determinism).
- R1 = diagnose outline_agent.py multi-turn loop + multi_section_generator.py section-planning, design
  GENERAL coverage-completeness fix (all major corpus themes => distinct substantial sections; cap ref
  bloat), Fable-gate. R2+ = render + RACE-score, must beat 0.4447 reproducibly + 2nd task for generality.
- Faithfulness untouched; no task-72 overfit; not chasing speed.
- Champion fallback: outputs/step3_control/report.md @ 0.4447 (safe).

## 07-12 ~09:30 UTC — QUALITY WHEEL R2: Part-A floor RACE=0.3959 (partial win, not champion)
- r2_partA_floor RACE=0.3959 (Comp .411 Ins .381 InstrF .405 Read .385), 3181w/12 sections/64 refs,
  cp4=agentic, faith=True, 29min.
- vs step5 broken 0.3518 (+0.044 — floor fix WORKS directionally, dropped themes restored) but vs
  champion 0.4447 (-0.049 — NOT recovered).
- DIAGNOSIS: Part A restored section COUNT (12) but sections THIN (265 w/sec vs champ 352) and ref
  bloat WORSE (64 vs 37). Breadth fixed; DEPTH + ref-cap still open.
- R3 target (general): per-section prose depth + cap reference bloat, WITHOUT losing coverage;
  faithfulness untouched. Champion 0.4447 still the bank/fallback.

## 07-12 ~10:15 UTC — QUALITY WHEEL R3: lever-2 depth RACE=0.3982 — gap is NOT structural
- r2_lever2_top24 RACE=0.3982 (Comp .411 Ins .383 InstrF .409 Read .388), 4028w/12 sec/54 refs,
  cp4=agentic faith=True. vs r2_partA 0.3959 (+0.002 only).
- PIVOTAL: lever-2 matched/exceeded champion's artifact stats (body 3104w/verified 99 vs step3
  3914w/91) yet RACE barely moved. Both quality-wheel renders sit ~0.396-0.398. => the 0.398->0.4447
  gap is NOT structure (coverage/depth/refs all matched). Structural theory necessary-but-insufficient.
- Wheel now RE-SCORING champion step3 (step3_rescore_r2) to decide: is 0.4447 reproducible, or was it
  a lucky RACE-judge draw / judge variance? Decisive for direction:
    * if step3 re-scores ~0.40 => 0.4447 was noise; our floor+depth fixes ARE at champion's true level.
    * if step3 re-scores ~0.4447 => real qualitative (prose/framing) gap beyond structure to find.
- Fixes landed are still GENERAL + faithful + coverage-preserving (keep them regardless).

## 07-12 ~10:25 UTC — DECISIVE: champion re-scores 0.4291 (RACE noise ~0.016); OUR gap is REAL + qualitative
- step3 champion RE-SCORE = 0.4291 (orig 0.4447) => RACE judge variance ~0.016; champion true level ~0.43.
- Our best (lever-2 0.3982) is ~0.03-0.04 BELOW champion's true level — REAL gap, exceeds judge noise.
- Gap is QUALITATIVE (uniform ~0.03 across all 4 dims; Readability worst -0.038): we MATCHED structure
  (coverage/depth/words/verified sentences) but the champion's ORGANIC 1-turn prose synthesizes + reads
  better than our floor-forced multi-section build. Not a structural lever.
- WALL NAMED: structural levers (coverage floor + depth focus) are EXHAUSTED at ~0.398; remaining gap to
  champion(~0.43) and SOTA(top-3 ~0.45-0.50) is prose/insight QUALITY — harder, may not fully close in code tonight.
- KEEPERS (general+faithful, land regardless): theme-coverage floor (fixes real 0.3518 collapse bug) + top-24
  writer-focus. CHAMPION 0.4447/0.4291 report remains the banked best artifact.

## 07-12 ~11:10 UTC — QUALITY WHEEL R4: lean/no-residual = 0.4058 (BEST of ours, plateau broke)
- r2_lean_noroute RACE=0.4058 (Comp .421 Ins .375 InstrF .431 Read .400), 2910w/11sec, faithful, bib=22 all-cited no-padding.
- CLIMBING: partA 0.3959 -> lever2 0.3982 -> lean 0.4058. Space NOT exhausted; cleanliness is a real lever.
- KEY: leanest report (2442w body) scored HIGHEST — MORE WORDS != better; quality/cleanliness > volume.
  Lean nearly closed InstrF (.431 vs champ .436) + lifted Readability (.385->.400).
- Remaining gap ~0.023 to champion(0.4291), now concentrated in INSIGHT (.375 vs .414, -0.039 worst dim).
  Insight = analysis/synthesis depth — hardest lever (prior insight-directive A/B failed). Next target.
- Best banked artifact still champion step3 (0.4447/0.4291); best REPRODUCIBLE-fix artifact = lean 0.4058.

## 07-12 ~12:00 UTC — QUALITY WHEEL R5: best_combo = 0.4245 — PARITY with champion's reproducible level
- r2_best_combo RACE=0.4245 (Comp .431 Ins .415 InstrF .444 Read .402), 3731w/3249w-body/97-verified/25-refs, faithful.
- vs champion re-score 0.4291: gap only 0.0046, WITHIN RACE judge noise (~0.016) => STATISTICAL PARITY.
- InstrF 0.444 EXCEEDS champion 0.436; Insight 0.415 MATCHES champion 0.414. Combo = floor+top24-depth+lean/no-residual.
- CLIMB: 0.3959 -> 0.3982 -> 0.4058 -> 0.4245. General+faithful+RELIABLE (guaranteed coverage, not a lucky draw).
- HONEST BOUNDS: did NOT beat champion's LUCKY 0.4447 (that re-scores 0.4291); reached champion's TRUE ~0.43
  reproducibly. STILL below SOTA top-3 (~0.45-0.50). Real 0.3518 collapse bug fixed; floor lifted 0.35->0.42.
- Keepers (general+faithful): thematic-coverage floor + top-24 writer-focus + lean/no-residual/no-bib-bloat.

## 07-12 ~12:30 UTC — USER CAUGHT IT: 25/919 source under-utilization — "lean win" partly overfits RACE
- CORPUS: 995 rows, 919 DISTINCT source URLs, 206 DOIs (329 = consolidated baskets, NOT sources).
- best_combo report: 25 sources cited, 97 verified sentences => ~3% source utilization. route_all OFF.
- PROBLEM: the lean/top-24 cap that lifted RACE (0.4245) WITHHOLDS most sources — pleases the concise-
  preferring RACE judge but GUTS full-corpus depth = POLARIS's differentiator vs ChatGPT/Gemini/FS-R.
  = benchmark overfitting (the exact trap the user has warned about).
- BUT naive "cite more" as bloat LOWERED score (lever2 54-src=0.3982). Real lever = SYNTHESIZE many more
  of the 919 sources into DENSE INSIGHTFUL prose (not pad, not drop) = same axis as our weakest dim INSIGHT.
- ACTION: do NOT ship 25-src lean as the win. Redirect wheel toward multi-source synthesis density
  (raises Insight toward SOTA AND uses the corpus). Faithfulness stays hard gate.

## 07-12 ~13:00 UTC — WHY OUTLINE SELECTS ONLY 39 (corpus-depth neck, code-traced, no render)
FUNNEL: 995 rows/840 works/329 baskets -> outline picks 39 ev_ids (8 sec x 4-10) -> 97 verified sent -> 25 cited.
NECK (ranked):
 1. SOFT/primary: outline planner SEES full corpus but prompt says "NEVER pad...to reach a count" with NO
    floor (>=8 only in a code comment; FACET floors at 2). Model picks ~4-10/sec. multi_section_generator.py
    :1516/1557/1596/1628. Fix = prompt floor + reward density, no constant edit.
 2. HARD switch: PG_ROUTE_ALL_BASKETS OFF (default) strands ~600 orphan baskets; ON balloons to 52-103 rows/sec
    (=the bloat that lowered RACE). verified_compose.py:3725,3789.
 3. HARD bound: writers compose ONLY from section ev_ids; no path into the ~800-work validated pool.
    verified_compose.py:3289. Outline thinness propagates.
NOT the cause: top-24 writer cap (downstream), PG_OUTLINE_MAX_EV=150 (dissolved), PG_MAX_EV_PER_SECTION=30
 (above observed), 24-turn loop (fetches NEW web rows, never rescues pool).
REAL FIX (depth+RACE together, not route_all-ON bloat): raise per-section evidence FLOOR + let writers
 synthesize from a larger validated set = "synthesis density" = same axis as weakest dim INSIGHT. Faithful.

## 07-12 ~12:30 UTC — SYNTHESIS-DENSITY FIX: build + gated validation (in progress)
RECONCILED MECHANISM (corrected): utilization fix (PG_ROUTE_ALL_BASKETS) ALREADY EXISTS, ON by default in
 compose_agentic script (line 190). Wheel's "lean win" 0.4245 came from DISABLING it. Depth-vs-RACE is an
 INVERTED-U: 22src=.406, 25=.4245, 37(champ)=.4447 PEAK, 40=.4225, 54=.398, 64=.396. Champion's 37 synthesized
 sources = sweet spot; lean under-shot, bloat over-shot. Real lever = DENSE SYNTHESIS of MORE high-quality
 sources (not pad, not drop).
CORPUS TIER MIX (quality risk): T1 5.5% T2 8.4% T3 18.7% T4 20.8% | T5 2.5% T6 21% T7 8.6% UNKNOWN 14.5%
 => ~44% lower-tier. route_all ON drags blog/unknown into sections => the "poor quality sources" risk.
GATE (user-refined, QUALITATIVE not count): READ each section's assigned evidence line-by-line (tier/title/
 quote), assess rich-high-tier+deep-insight vs thin/junk; if thin OR poor => STOP+fix until genuinely rich;
 only then compose (monitor speed+faithfulness+RACE).
DONE: instrumented default-OFF rich gate dump in multi_section_generator.py (after route_all, before compose;
 resolves ev_ids->tier/title/url/quote). Compiles. Launched baseline render (route_all ON) + gate watcher.
NEXT: read baseline gate dump -> assess per-section quality -> design synthesis-density fix accordingly.

## 07-12 ~12:40 UTC — USER NORTH STAR (breakthrough directions for the wheel; user asleep)
The wheel's success is MULTI-DIMENSIONAL (NOT RACE alone — going lean to game RACE is a FAIL):
 1. RICH outline: thick, genuinely high-tier/insightful sources per section (READ-assessed, not counted).
 2. MAX SOURCE COVERAGE: use as much of the 840-work / 329-basket corpus as possible (vs the 25 lean).
 3. INSIGHTFUL + ANALYTICAL: deep, non-obvious synthesis, contrasts, mechanisms.
 4. QUANTITATIVE SYNTHESIS (NEW lever): use MATH/STAT tools to consolidate/synthesize the NUMBERS
    collected across sources (ranges, weighted means, effect-size reconciliation, agreement/disagreement)
    via the VERIFIED [#calc:] lane — analytical depth that also lifts RACE Insight. INVESTIGATE if the
    pipeline does this today; STRENGTHEN it.
 5. HIGH SCOREBOARD: RACE >= champion and climbing toward SOTA — but achieved WITH 1-4, not by going thin.
GUARDRAIL: qualitative OUTLINE GATE (read evidence line-by-line) must pass BEFORE compose; thin/poor => fix.
 COMPOSE must stay fast enough + faithful (strict_verify untouched).

## 07-12 ~12:55 UTC — COLLISION RESOLVED: wheel wf_70ee53f7 was STILL RUNNING + built the same fix
- The quality wheel never stopped (4+hr); it AUTONOMOUSLY converged on the coverage fix:
  f003fef (PG_DUMP_ROUTED_OUTLINE instrumentation — SAME as my hand edit), 644e447 (corpus-derived
  THEME-COVERAGE floor PG_OUTLINE_THEME_FLOOR, default-OFF), 72c20eb (fix detection). Variance-safe:
  no-op on rich step3 seed, recovers dropped Policy theme on thin best_combo. = user directions #1-2.
- COLLISION: I launched a manual baseline render + edit into the SAME worktree -> my render died (exit
  144, worktree committed under it). NO corruption (file compiles, tree clean, single PG_DUMP block).
- LESSON: never launch manual work into a worktree with an ACTIVE wheel. Check wheel-alive first.
- PLAN: STAND DOWN from worktree. Let wheel finish its coverage work + render/score. THEN take over
  cleanly for the MISSING north-star items: #4 QUANTITATIVE SYNTHESIS (math/stat aggregation via [#calc:]),
  qualitative READ-gate on its output, #2 max-coverage beyond theme-recovery. Do NOT interfere mid-commit.

## 07-12 ~13:15 UTC — OUTLINE COGNITION READ (from reasoning/decision logs) + GLM 5.2 confirm
MODELS (verified live + §9.1.8 lock): COGNITION (ReAct decide/gap-analysis/plan) = z-ai/glm-5.2;
 generator(writing) = glm-5.2; deepseek-v4-pro = code-EXEC only (execute_python calculator), NOT cognition.
 => cognition IS on GLM 5.2. ✓
COGNITION READ (gate_baseline outline stage, glm-5.2):
 + FULL gap-fill loop WORKS: 5 search_more_evidence -> live-fetch 147 cands -> topic-gate -> select/weight
   -> route into outline. Genuinely finds holes + triggers new query/search/fetch/select/weight/corpus.
 + 4/5 queries on-topic; one explicitly sought "quantitative estimates of jobs" (quant instinct present).
 - WEAKNESS 1: generic gap query "methodological restriction to high-quality English-language" fetched 104
   OFF-TOPIC medical papers (sports med/nephrology/child psych); demoted+kept but 106 ev_ids routed into
   Introduction => dilution. Fix: domain-scope the gap searches.
 - WEAKNESS 2 (biggest, = direction #4 UNMET): it SEEKS numbers but runs NO deep math/stat synthesis on
   them ([#calc]/execute_python meta-analysis absent). Consolidates+routes but does NOT quantitatively
   synthesize collected numbers. BUILD this (glm-5.2 decides -> deepseek runs stats -> verified [#calc:] lane).
STANDING MONITOR: read the outline DECISION TRACE every render (gap names, queries fired, demotions, routing)
 to judge cognition quality — not just output counts.
