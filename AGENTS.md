# AGENTS.md — POLARIS agent operating rules

This file is read by Codex and any coding agent working in this repo. It mirrors the binding
LLM-governance rules in `CLAUDE.md` §9.1.8. `CLAUDE.md` is the full operating charter; read it first.

## LLM MODEL + TOKEN MAX GOVERNANCE (operator-locked 2026-06-13 — GH I-arch-003 #1253)

These are land-mine rules. Every LLM call in this repo is subject to them.

1. **Model must be RIGHT — always double-check.** Every LLM call's model must match the
   operator-signed lock `config/architecture/polaris_runtime_lock.yaml`:
   - generator = `deepseek/deepseek-v4-pro`
   - mirror = `z-ai/glm-5.1`
   - sentinel = `minimax/minimax-m2`
   - judge = `qwen/qwen3.6-35b-a3b`
   - **NO `google/gemma-*`**, no closed-source (openai / anthropic / google-closed) at runtime — sovereignty.
   - The side judges (entailment / semantic_conflict / credibility) are NOT one of the 4 locked roles;
     they map to the **mirror** (GLM-5.1) per the lock's `legacy_compat` (the retired `PG_EVALUATOR_MODEL`).
   - Stale Gemma defaults drifting into those judges caused #1249/#1251/#1252. Verify the model on EVERY call.

2. **Reasoning effort + max_tokens ALWAYS go MAX.** Never starve reasoning or output.
   - Set `max_tokens` to the model's REAL OpenRouter limit; set reasoning effort to the max (high / xhigh).
   - A starved budget truncates reasoning → empty content → fail / coverage-collapse ("half-ass job").
   - `max_tokens` is a CAP, not a target (OpenRouter bills actual usage) → a generous cap is free insurance.

3. **Read the API doc, DON'T guess** the allowed max per model:
   `GET https://openrouter.ai/api/v1/models` → per-model `context_length` + `top_provider.max_completion_tokens`.
   Reconcile vs the actual serving provider's cap (e.g. deepseek-v4-pro: OpenRouter says 384000 but the
   DeepInfra provider binary-searched to 16384).

4. The architecture lock pins MODELS but historically NOT token budgets — that gap let the starvation drift
   undetected by the conformance gate. Token caps are now a first-class governed setting; extend conformance.

Real per-model limits (OpenRouter API 2026-06-13): deepseek-v4-pro ctx 1,048,576 / out 384,000 (DeepInfra
caps 16,384); glm-5.1 ctx 202,752 / out unbounded(=ctx); minimax-m2 ctx 204,800 / out 196,608;
qwen3.6-35b-a3b ctx 262,144 / out 262,144.

## AUTONOMOUS / LONG-RUNNING WORK — anti-stall working attitude (operator-locked 2026-06-16)

The standing working attitude for any autonomous, overnight, or multi-hour task (e.g. a benchmark
sweep). The operator's deepest repeat-flagged fear is that the agent STALLS — hits a bug/crash and just
sits there instead of debugging + relaunching. The fix is STRUCTURE that makes the work survive a stall,
not a promise. Four layers:

1. **Detached work survives session-close.** Launch long runs `setsid nohup` on the box so they finish
   regardless of the agent's session/loop/stall. The output files get written no matter what — the FLOOR.
2. **Box-side watchdog survives the agent's stall.** Alongside each detached run, a bounded watchdog
   (every ~5 min: if proc dead + no output + attempts<3 → relaunch `--resume`). A crash resurrects without
   the agent. Bounded (max 3) so it can't infinite-loop and burn credit. (`scripts/iarch007_box_watchdog.sh`.)
3. **The monitoring loop re-arms on EVERY outcome** — success, abort, crash, error, or uncertainty —
   UNLESS the whole job is done + the summary written. A failure NEVER ends the loop; it triggers the
   playbook then re-arms. When unsure, the default is act + relaunch + re-arm — NEVER freeze.
4. **Durable plan/playbook FILES survive a context reset.** On resume, read the plan + emergency playbook
   off disk and reattach — the files ARE the memory.

**Forensic-FIRST (§-1.4):** on ANY anomaly read the actual log / reasoning / raw-LLM-IO line-by-line RIGHT
THEN — never surface liveness, never "wait and see." Distinguish a slow call from a hang with EVIDENCE:
the raw-LLM-IO capture-dir mtime is THE truth (a big reasoning call can run ~9 min log-silent then return);
CPU state, `ep_poll`/`do_poll` wchan, and file mtimes corroborate. A run is HUNG only if llm_io AND log AND
phase are ALL frozen past the timeout — only then kill PID-SCOPED (never name-global pkill; the operator
runs concurrent codex sessions) + relaunch `--resume`.

**Evolution loop (quick-fix → quick-relaunch):** result lands → line-by-line audit (§-1.1) → if it fails the
bar → forensic root-cause → FIX → relaunch ASAP (prefer `--resume` from the saved checkpoint to skip
re-work) → repeat. Bounded ≤3 fix-cycles per unit, then mark best-achieved + surface the residual lever.

**Hard rules:** faithfulness NEVER relaxed; open-weight verifiers only; PID/slug-scoped kills only;
commit-per-unit (uncommitted work on a shared tree gets wiped); log every incident; if a paid service nears
empty, notify the operator. Proven live 2026-06-16: a smoke hit a STORM→outline `ep_poll` hang →
forensic-diagnosed (missing hard timeout on the one reasoning-ON call) → fixed → redeployed → relaunched →
re-armed, autonomously, no stall. See `state/iarch007_overnight_plan.md` (durable plan + EMERGENCY PLAYBOOK).
