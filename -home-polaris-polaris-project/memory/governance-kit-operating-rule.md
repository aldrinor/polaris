---
name: governance-kit-operating-rule
description: "Standing rule — ALL agent/orchestration work runs inside the govkit (bot/repo-knowledge-base); the operator is blind, work in military order"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

The operator requires that **all agent work runs within the governance kit**. The kit lives on **`gate-inversion`** (merged via PR #1408: `gov/` + `tools/` + `docs/agent_environment/`); wiring added in `878de86`. Work in disciplined, enforced order — the operator is BLIND and reads every message by ear, once.

**Why:** five repeating failures (drip-fed partial answers, tunnel-vision one-spot fixes, git/doc drift, long jargon-y messages, dumping context-heavy decisions on the operator). Each checker mechanically blocks one.

**STANDING DISCIPLINES (operator-confirmed 2026-07-20, apply to ALL future work):**
1. Every improvement runs INSIDE this infra (govkit + gate-inversion). No side-channel work.
2. Naming is plain and descriptive — NO casual/inflated/adjective names (the rename work established this).
3. GitHub is updated on EVERY change (commit + push each fix; never let git/doc drift).
4. New settings go through the central config layer (`resolve()` + `config_defaults.py`), NEVER a hardcoded `os.getenv("X", literal)` — a hardcoded value is the exact bug the config consolidation fixed. Offered to add a CI/pre-commit guard that blocks any NEW raw `os.getenv` outside settings.py (pending operator go-ahead) so this is machine-enforced, not just remembered.
The 5 foundation gates are all codex-approved + pushed to gate-inversion (config 8264c3d+58e0809, checkpoints 695951c, logging 8d23105, entailment-off + run-recipe 3cb46b8). Owner-only remainder: 27 conflicting-default config keys need a product decision.

**HARD BINDING (this fixed the twice-slipped bug): NEVER run `gh issue create` or `gh pr create` until `python3 tools/check_pr_body.py <body>` (add `--issue` for issues) has exited 0 on that exact body file.** Check first, create only on pass — do not create-then-fix. Same for operator messages: lint BEFORE sending, never after.

**MACHINE GUARDS (installed 2026-07-20, in `~/.local/bin`, so keep `$HOME/.local/bin` on PATH — my bash preamble does):**
- `~/.local/bin/gh` wraps the real gh (moved to `~/.local/bin/gh-real`). On `issue create` / `pr create` it runs `check_pr_body.py` on the `--body-file` ONLY when that file's first heading is `# Pull request` or `# Issue` (i.e. a govkit body — mine always are); a failing govkit body is BLOCKED before any PR/issue is made. Non-govkit bodies and all other gh commands pass straight through, so concurrent bots are untouched.
- `~/.local/bin/opmsg <file>` is the gate for operator messages: it lints via `lint_operator_message.py` and prints the message only if it passes; otherwise it blocks. Route every operator report through `opmsg`.
- Stable checker copy at `~/.govkit/tools/` + `~/.govkit/gov/` (decoupled from any worktree, so the guards survive a worktree removal). These are box-local; re-create from the gate-inversion kit if the box resets.

**How to apply — every time, no exceptions:**
- **Background tasks:** NEVER spawn watchdog/`sleep`-poll chains — wait for the harness completion notification (it fires automatically); at most one Monitor with a real exit condition; keep the live/lingering count near zero. Codified in `gov/background_task_discipline.md` (committed 7fc2a45) + [[background-task-lifecycle-rule]].
- **Operator messages:** run through `tools/lint_operator_message.py` before sending. Max 5 sentences, flat lists only (no nesting — indentation is silent by ear), no emoji, no jargon (banned list lives in `gov/operator_voice.md`), max 35 words/sentence. Pasted command output goes in a real fenced block (skipped by the linter).
- **Spawning any sub-agent:** prepend the matching `gov/spawn_templates/{claude,codex,kimi}.md`; require the `gov/agent_payload.schema.json` back (13 required keys incl. `findings` with real quotes, `not_covered`, `metrics`); reject a payload with empty `not_covered`. Validate with `tools/validate_agent_payload.py`.
- **Fan-out:** run ONE agent → validate its payload → 5 → the rest. If >20% fail, kill the fan-out and report.
- **Issues:** `gov/issue_template.md`, checked with `tools/check_pr_body.py <f> --issue`. Requires a measured scope (real command + numeric output; estimates rejected) and a data-path trace naming every stage + chokepoint as file:line.
- **PRs:** `gov/pull_request_template.md`, checked with `tools/check_pr_body.py`. Requires issue link, evidence, review verdict, out-of-scope, and a real rollback command. The checker opens every file/line named — invented paths are rejected.
- **Decisions:** follow `gov/decision_protocol.md` — either DECIDE and say (what / why / what-would-make-it-wrong), or ask exactly ONE question with your recommendation marked and one plain line per option. Never hand the operator a decision needing context they lack.
- **Measure, don't estimate.** Every number comes from a command you ran and paste. Blocking is proof; existence is not.

**Wiring (on gate-inversion, commit 878de86, 2026-07-20):** `.githooks/pre-commit` runs the 3 checkers on staged governance files only (`core.hooksPath=.githooks`, relative → safe no-op in worktrees without it); proven to block a bad operator message, a bad payload, and a bad PR body. `.github/workflows/govkit_checks.yml` runs report-only on every PR. **Do NOT target `main`** — it holds 2 files and shares no history with the codebase; nobody works from it. `gate-inversion` is the real 10,017-file tree, is UNPROTECTED (direct push OK, no approval needed), and is where PRs target. Do not ask the operator to approve/click/grant anything.

Self-tests: `validate_agent_payload` 33/33, `lint_operator_message` 32/32, `check_pr_body` 32/32, all exit 0.

See [[codex-sol-max-reasoning]], [[code-review-readiness]].
