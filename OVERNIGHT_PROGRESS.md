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

## Status log
- 13:54 UTC — driver up. Read master brief + agentic_outline_redesign.md in full. Mapped box: 2x A100-80GB, 128 cores, 2 TB RAM.
- 13:58 UTC — found BLOCKER 1 (worktrees root-owned, no sudo) and BLOCKER 2 (local GLM-5.2 infeasible: 114 GB disk / 80 GB VRAM vs ~355 GB weights).
- 14:01 UTC — created three polaris-owned worktrees off the exact wheel tips; wheels can proceed.
