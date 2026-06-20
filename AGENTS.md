# AGENTS.md — POLARIS agent operating rules

This file is read by Codex and any coding agent working in this repo. It mirrors the binding
LLM-governance rules in `CLAUDE.md` §9.1.8. `CLAUDE.md` is the full operating charter; read it first.

## ★ BEAT-BOTH CAMPAIGN PROTOCOL — operator-locked 2026-06-20 (BINDING, read FIRST) ★
Active mission: POLARIS **#1 on BOTH** DeepTRACE + DeepResearch-Bench-II. **THE BINDING PLAN = `state/beatboth_campaign/MASTER_PLAN.md`** (★ EXECUTION PROTOCOL section). Re-read it + `state/beatboth_campaign/loop_state.json` FIRST every tick; state the current PHASE + the single next action; deviation = STOP + flag (military anti-drift discipline).
- **Phases:** P0 lock+pin → P1 forensic audit of run7 (log/memory/reasoning/citation/output line-by-line + 2 competitors, Claude + Codex independent) → P2 benchmark both (DeepTRACE + DRB-II judges via OpenRouter) → P3 consolidate issue list → P4 two-track fix (OBVIOUS = Codex Workflow now / UNCERTAIN = research 2026 best-practice then Codex Workflow) → P5 serious preflight+smoke → P6 fresh all-GLM-5.2 run (stablest+fastest server US/China, MAX parallelism, RETRY-UNTIL-ON never-degrade) → P7 VM 5-min forensic monitor → `state/beatboth_campaign/ONGOING_BUG_LOG.md` → P8 hamster loop until #1-on-both.
- **Decisions 2026-06-20:** all-GLM-5.2 (two-family §9.1.1 dropped — test single strong family); sovereignty dropped (US/China ok); all benchmark judges via OpenRouter; $300 banked.
- **Discipline:** NEVER substitute a count for an audit or a packer for a benchmark (the overnight drift); faithfulness gates never relaxed; speed via PARALLELISM + RETRY-not-degrade; stop ONLY at #1-on-both / real halt / operator stop.

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

**Trace-the-path + replay-harness (§-1.4 — OUTPUT-defect debugging, operator-locked 2026-06-17):** when the
OUTPUT is wrong/thin (breadth collapse, too-few citations, an empty section, dropped sources, a feature that
"didn't fire") — NOT a crash — do NOT patch one symptom at a time. (1) **TRACE the whole data-flow end-to-end:**
basket → consolidation (`finding_dedup`/`fact_dedup`) → generator (`multi_section`) → verify (`strict_verify`/
NLI/4-role/provenance) → render; at each hop ask "what flows in/out, where is breadth lost?". (2) **Find EVERY
chokepoint** (one reader per hop + a completeness critic), not just the one you tripped on — output the COMPLETE
list (is it 3 landmines or 8?). (3) **Per chokepoint decide surgical-patch vs clean-module-REWRITE** — rewrite a
detect-but-never-wire layer; NEVER rewrite the faithfulness engine (the proven crown jewel). (4) **Build a
BEHAVIORAL replay-harness:** acceptance = the effect ACTUALLY APPEARS in the real output (e.g. `collapsed>0` +
multi-source baskets on a real `corpus_snapshot.json`), FAILS LOUD if not — NOT "Codex approved the diff", NOT
"tests green". (5) **Fix against the harness, then REPLAY all banked corpora end-to-end** (`resume_from_corpus`,
no re-retrieval) and §-1.1-audit the real output; fix whatever it reveals; repeat until WIDE and FAITHFUL.
WHY: diff-review/green-tests check CODE not OUTPUT-behavior → "committed + green + approved ≠ fired in the
output." Kills the 3 worries at once: unknown landmines (trace finds them), rewrite-vs-patch (per-hop verdict),
why reviews miss it (behavioral harness). First applied I-arch-008 (#1265). Mirrors `CLAUDE.md §-1.4`.

**Evolution loop (quick-fix → quick-relaunch):** result lands → line-by-line audit (§-1.1) → if it fails the
bar → forensic root-cause → FIX → relaunch ASAP (prefer `--resume` from the saved checkpoint to skip
re-work) → repeat. Bounded ≤3 fix-cycles per unit, then mark best-achieved + surface the residual lever.

**Hard rules:** faithfulness NEVER relaxed; open-weight verifiers only; PID/slug-scoped kills only;
commit-per-unit (uncommitted work on a shared tree gets wiped); log every incident; if a paid service nears
empty, notify the operator. Proven live 2026-06-16: a smoke hit a STORM→outline `ep_poll` hang →
forensic-diagnosed (missing hard timeout on the one reasoning-ON call) → fixed → redeployed → relaunched →
re-armed, autonomously, no stall. See `state/iarch007_overnight_plan.md` (durable plan + EMERGENCY PLAYBOOK).
