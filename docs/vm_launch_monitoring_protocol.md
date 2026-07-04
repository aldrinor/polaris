# VM-Launch Forensic Monitoring Protocol — MILITARY ORDER

**Operator-locked 2026-07-04. BINDING for EVERY paid pipeline run launched on ANY VM box, forever.**
("keep it as military order... mark it in your gene, and github and everything, make sure you always use
this workflow for monitoring.")

This is not optional and not per-campaign. The moment a paid run is launched on a VM box, this loop is in
force until that run is fully scored (or the operator explicitly stops it).

## The loop (repeat every 5 minutes)

1. **READ EVERYTHING.** Claude (Opus 4.8) reads EVERY newly-generated line from ALL launched VM boxes — the
   run logs, the reasoning traces, the retrieved source content, AND the output. This is a **forensic,
   §-1.1-quality read of the CONTENT** — retrieved sources, tier mix (T1–T7), extracted text cleanliness,
   intermediate section drafts checked claim-vs-cited-span, verify-drop behavior — NOT a shallow
   alive/heartbeat check. The live logs carry most of the SOTA-blocking signal BEFORE render.

2. **CONSOLIDATE TO THE OPERATOR.** Claude analyzes, consolidates, and summarizes all of it to the operator
   every 5 minutes, in plain simple English (the blind-operator standard).

3. **RED FLAG → IMMEDIATE ESCALATION.** A red flag = the run **diverging / drifting / stalling / dying /
   going crazy** — off the direction of the intended fixes and the goal. On ANY red flag, Claude
   **immediately escalates to Codex AND Fable 5** (the two independent reviewers) to judge FALSE-alarm vs
   REAL-alarm. Claude does NOT decide this alone.

4. **CODEX + FABLE 5 DECIDE THE RESPONSE.** They choose one of:
   - **HOLD** → investigate → research → fix → test → **relaunch from the NEAREST CHECKPOINT** (on an
     existing VM box OR a freshly rented box) → keep the monitoring loop going; or
   - **LET IT RUN** for a while.
   Claude executes their decision; Claude is the executor, the two reviewers are the decision authority
   (consistent with the standing "everything gated by Codex + Fable" rule).

5. **NOT COST-SHY. TIME-SHY + RESULT-SHY.** Spend whatever it takes; move as fast as possible; only accept a
   result that beats ALL target scoreboards (DeepTRACE + DeepResearch-Bench-II + DeepResearch-Bench
   RACE/FACT). **NO half-ass result** — a mediocre run moves us FARTHER from the goal, not closer.

6. **CRASH / OOM / HANG / 429 → RESUME, NEVER FRESH.** Resume from the nearest checkpoint
   (`run_gate_b.py --resume`, reload the `corpus_snapshot`); never a fresh re-run that discards good
   upstream work.

## Why this exists
The operator is blind and cannot watch the `/workflows` panel or the box logs — Claude is the forensic eyes.
A silent drift/stall/crazy-off run wastes money and, worse, time (we are in a time-and-result-shy endgame to
beat all three boards). The two-reviewer gate prevents both false-alarm thrash and real-alarm blindness.

## Related standing rules
- `feedback_read_every_line_means_forensic_quality_not_status_check` (the read-quality standard).
- `feedback_fast_beatboth_only_params_no_cost_shy` (FAST + BEAT-BOTH are the only params; cost is not a limit).
- `feedback_resume_from_closest_checkpoint_ground_rule` (resume, never fresh re-run on a crash).
- `AGENTS.md` ★ pins + `CLAUDE.md` §3.0.1 (Claude Codex Workflow; Codex + Fable the review authority).
