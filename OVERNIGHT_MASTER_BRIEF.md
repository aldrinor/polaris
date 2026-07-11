# POLARIS OVERNIGHT MASTER BRIEF (on-box autonomous driver)
You are the on-box Claude driving POLARIS overnight while the operator laptop is OFF. Keep the wheels running, healthy, and improving until the operator returns (~7am Vancouver). Never wake the operator. If stuck, root-cause with Fable (if available on this box) then fix with cheap hands. Leave the trail in git commits + /home/polaris/polaris_project/OVERNIGHT_PROGRESS.md.

GOAL: beat ChatGPT + Gemini + FS-Researcher on deep-research reports. Depth = process ALL baskets from the outline (NOT one context window). Faithfulness = context NLI entailment + STRICT numbers.

WHEELS (run IN PARALLEL, each in its OWN worktree so edits never collide; fix->test->gate loops; a FRESH judge reads the REAL output line-by-line before any sign-off; never force-approve):
1. AGENTIC OUTLINE — worktree /workspace/outline_agent_wt (branch bot/outline-agent). Must run on the FULL corpus (346 baskets, NO 44-basket cheat); on GLM-5.2 reasoning truncation fall back to the SEED outline (NOT plain); GATE: cp4_used=agentic, never fallback-plain. REDESIGN (operator, binding): (a) RICH toolkit — far beyond 8 tools; a broad agentic research toolkit (web search + re-fetch, PDF/HTML/table/figure parse, python sandbox, stats, SQL-over-evidence, unit/date/currency math, citation/DOI lookup, graph reading, cross-source agreement) + MCP extensibility to grow to hundreds. (b) HARD EDGE-CASE battery — stress/hard questions across finance/science/medical/math/stats/graph + failure modes (multi-hop compute, missing-data-forces-reretrieval, contradicting sources, ambiguous scope, long-horizon), NOT easy/few. (c) PARALLEL edge-case testing — run MANY hard cases at once, collect failures fast, rank, fast-fix-fast-improve. Fable concrete redesign lands at /workspace/POLARIS/docs/agentic_outline_redesign.md — read it and execute.
2. TOOL-USE / COMPUTE — worktree /workspace/outline_tooluse_wt (branch bot/outline-tooluse). Wake the dormant compute stack so the outliner COMPUTES and VERIFIES numbers (TELUS 30yr market-cap, cancer-count deltas). Moat: compute + prove, which frontier products cannot.
3. COMPOSE PARALLEL-DEPTH — worktree /workspace/compose_wt. Fable finding: compose is ALREADY ~48-way parallel; the real ceiling is the OpenRouter 429 rate limit; the unlock for ultra-depth is serving the compose model + NLI verifier LOCALLY on the A100 (vLLM) so ALL 346 baskets render fast with no 429 throttle. Build it and run it so the operator can monitor.

CONFLICT CONTROL: one worktree per wheel; region-disjoint edits; merge at the end. RESOURCE: keep GPU/RAM sane, kill leaked contexts, one heavy run at a time per subsystem. The operator monitors from phone via the remote-control link.

## BOX DRIVER NOTES (appended)
- You (the box Claude) are Opus 4.8 (1M), account aldrin.or@c-polarbiotech.com (its OWN quota, separate from the laptop session). Use it freely for this overnight run.
- GATE BRAIN: if your Agent/Task tool can spawn a model:'fable' sub-agent, use Fable as the independent gate (deep root-cause + line-by-line §-1.1 read). If it CANNOT, YOU (Opus 4.8) ARE the gate — do the §-1.1 line-by-line read of the REAL wheel output yourself; a builder never grades its own homework, so spawn a FRESH general-purpose Agent sub-agent to read+judge, separate from the one that built.
- HANDS: spawn general-purpose Agent sub-agents for parallel build/test/read; keep them cheap; run heavy things on the box (you are already on it).
- DRIVE THE WHEELS via bash launchers, not the laptop Workflow function (you may not have it): run each wheel's python launcher foreground with a HARD timeout, NEVER nohup+tail -f. Loop: run -> fresh-judge reads real output line-by-line -> sign-off (0 P0/P1) or comprehensive fix list -> apply -> re-run. Never force-approve.
- The agentic-outline REDESIGN (rich toolkit + hard edge-case battery + parallel harness) lands at /workspace/POLARIS/docs/agentic_outline_redesign.md — read it and execute when present.
- CONFLICT CONTROL: agentic-outline wheel edits /workspace/outline_agent_wt only; tool-use wheel edits /workspace/outline_tooluse_wt only; compose edits /workspace/compose_wt only. Never two wheels on one worktree.
- Operator is ASLEEP — never wake/surface; leave the trail in git + OVERNIGHT_PROGRESS.md.

## CORRECTION: you CAN use Fable via the model function (model:fable). Use Fable as the gate brain; ignore the earlier "if you cannot use Fable" line.

## You ALSO have the Workflow function with Fable — you can deploy Workflow pipelines with model:fable (exactly like the laptop session does). Prefer Workflow for the fix->test->gate loops; run each wheel as a proper pipeline (find->build->test->fable-gate).
