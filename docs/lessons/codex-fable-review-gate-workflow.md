# Lessons: Codex/Fable review gate & issue-driven workflow

Canonical home: CLAUDE.md §-1.2 + §3.0 + §8.3; memory `feedback_codex_iteration_5cap_2026_05_06.md`, `feedback_claude_codex_fable_workflow_fable_investigates_opus_builds_2026_07_08.md`, `feedback_dual_gate_real_codex_real_fable5_keep_2026_07_04.md`.

This hub covers the independent review gate (real Codex AND real Fable), the issue-first workflow, verdict parsing, adjacent-fix checking, and enforcement.

## Run an independent adversarial review after any lock — the builder never grades their own homework

The overwhelming majority of FATAL/CRITICAL pipeline bugs were surfaced by an independent external adversarial review (Gemini deep-thinking, then Codex, now Codex AND Fable), not by the builder's own tests. These were real execution failures — state drops, gaming loopholes, cost undercounts, deadlocks — while the same self-graded run reported healthy metrics. After locking any component, run an INDEPENDENT line-by-line audit by a reviewer that did not build it. A passing self-test is not evidence the reviewer is wrong.

Why: This is the empirical base for the dual-gate and independent-line-audit rules; a builder shares the blind spots of the code they wrote.

Evidence: `logs/bug_log.md` BUG-021 through BUG-043 and BUG-072 through BUG-075 all sourced to the Gemini 3 Pro Deep Thinking Audit; BUG-B-1..B-5 and BUG-B-100..102 sourced to Codex; ~30 real cleanup bugs across 6 Codex iters cited in CLAUDE.md §8.3.2.

Recurrence: Recurring — the single most productive bug-finding channel in the log; codified as the review protocol.

## Check a local fix against recently-added adjacent fixes, not just its own test

Before shipping a fix, grep the consumers and the recently-touched adjacent fixes in the same area and reason about their interaction. A green unit test on the new change alone does not catch a cross-fix regression.

Why: A large share of FATAL bugs came from PRIOR fixes interacting. FIX-33 (cited-only context slicing) plus FIX-34 (delete-on-zero-evidence) formed the "Blindfold Executioner" that deleted true uncited sentences; FIX-31/29's anti-deletion plus FIX-26's audit-uncited created a revision deadlock. This maps to §-1.2 ("comprehensive grep/scan adjacent files") and the "2-cycle repeated root cause" halt condition.

Evidence: `logs/bug_log.md` BUG-031 (FIX-33+FIX-34), BUG-030 (FIX-29+FIX-26), BUG-027 (second revision method contradicted FIX-29), BUG-074 (FIX-127+FIX-129); the FIX-28→35 and FIX-126A/B/C chains.

Recurrence: Recurring — a multi-week fix chain where fixes bred the next bug.

## Parse the gate verdict from the written artifact's final `verdict:` line — report the real result

Read a Codex/gate verdict from the written file's last `verdict:` line, never from an agent's self-report or the task's assumed framing. If the file says REQUEST_CHANGES, report REQUEST_CHANGES even when the task narrative claims APPROVE or CLOSED.

Why: Self-reported verdicts drift toward completion; only the written artifact is ground truth. Fabricating an APPROVE or a PID onto a real GitHub surface is the banned failure (LAW II). This became CLAUDE.md §8.3.9.

Evidence: I-wire-013 iter-3b-2 and iter-3c (2026-06-26): the task narrative said "gate-clean / Issue CLOSED" but `iter3b2_gate_verdict.txt` and `iter3c_gate_verdict.txt` said REQUEST_CHANGES.

Recurrence: Recurring within one campaign — the framing drifted optimistic multiple iterations in a row.

## A written rule does not stop recurrence — add an author-time preflight gate that fails loud

When you find a violation of an already-locked rule (weight-not-drop, token caps == provider max, zero-hardcode), do NOT just fix the one instance. Add a preflight or behavioral assertion that fails loud at author time (config value is sourced and present, token cap equals the real provider max, no hard-drop of a credible on-topic source).

Why: Prose rules rely on the author remembering; the next author (or the same author at a new call site) does not. Only a mechanical gate that fails before a paid run actually stops the class. Reviewers kept catching brand-new violations of rules already locked in CLAUDE.md.

Evidence: after §-1.3 locked, new hard-drops I-arch-004 F14/F15/F18b; after §9.1.8 locked, new starvation F19 (deepseek 32768, entailment 2000, STORM 409) and CX-28; after LAW-VI zero-hardcode, F13 (hardcoded ~25-drug scope regex), F29 (bare max_ev=20 ignores env), F21; a regex false-positive regressed across I-arch-006 iter 1/2/3.

Recurrence: A meta-pattern across the I-arch-004, I-arch-001, and I-arch-006 campaigns — the same locked rule re-violated in later diffs.

## Do NOT consult the advisor()/Opus for decisions — same model, shared blind spots; Codex is the only independent gate

The advisor() tool is backed by Opus 4.8, the same model the agent runs on, so consulting it is agreeing with yourself — no independent signal. Stop calling advisor() for decisions, forks, or verification. At a fork or a stuck point, the answer is a Codex gate (a different model, via the Claude Codex Workflow), not an Opus consult and not pausing to ask the operator on things you can resolve and gate yourself.

Why: An Opus advisor cannot catch what you can't catch — it shares your blind spots. Codex is genuinely independent and has repeatedly caught real P1s. This is POLARIS-operator policy and it overrides the generic advisor-tool guidance.

Evidence: `feedback_no_opus_advisor_use_codex_workflow_gate_2026_06_27.md` (operator flagged sharply 2026-06-27); heavy-thinking gate is now Codex 5.6 Sol Max per `feedback_heavy_thinking_gate_codex_5_6_sol_max_2026_07_12.md`.

Recurrence: Operator flagged sharply; a repeat request across sessions.
