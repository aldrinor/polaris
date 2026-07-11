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
