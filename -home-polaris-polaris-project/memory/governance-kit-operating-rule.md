---
name: governance-kit-operating-rule
description: "Standing rule — ALL agent/orchestration work runs inside the govkit (bot/repo-knowledge-base); the operator is blind, work in military order"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

The operator requires that **all agent work runs within the governance kit** (branch `bot/repo-knowledge-base`, `docs/agent_environment/` + `gov/` + `tools/`). Work in disciplined, enforced order — the operator is BLIND and reads every message by ear, once.

**Why:** five repeating failures (drip-fed partial answers, tunnel-vision one-spot fixes, git/doc drift, long jargon-y messages, dumping context-heavy decisions on the operator). Each checker mechanically blocks one.

**How to apply — every time, no exceptions:**
- **Operator messages:** run through `tools/lint_operator_message.py` before sending. Max 5 sentences, flat lists only (no nesting — indentation is silent by ear), no emoji, no jargon (banned list lives in `gov/operator_voice.md`), max 35 words/sentence. Pasted command output goes in a real fenced block (skipped by the linter).
- **Spawning any sub-agent:** prepend the matching `gov/spawn_templates/{claude,codex,kimi}.md`; require the `gov/agent_payload.schema.json` back (13 required keys incl. `findings` with real quotes, `not_covered`, `metrics`); reject a payload with empty `not_covered`. Validate with `tools/validate_agent_payload.py`.
- **Fan-out:** run ONE agent → validate its payload → 5 → the rest. If >20% fail, kill the fan-out and report.
- **Issues:** `gov/issue_template.md`, checked with `tools/check_pr_body.py <f> --issue`. Requires a measured scope (real command + numeric output; estimates rejected) and a data-path trace naming every stage + chokepoint as file:line.
- **PRs:** `gov/pull_request_template.md`, checked with `tools/check_pr_body.py`. Requires issue link, evidence, review verdict, out-of-scope, and a real rollback command. The checker opens every file/line named — invented paths are rejected.
- **Decisions:** follow `gov/decision_protocol.md` — either DECIDE and say (what / why / what-would-make-it-wrong), or ask exactly ONE question with your recommendation marked and one plain line per option. Never hand the operator a decision needing context they lack.
- **Measure, don't estimate.** Every number comes from a command you ran and paste. Blocking is proof; existence is not.

**Wiring (installed 2026-07-20):** `.githooks/pre-commit` runs the 3 checkers on staged governance files only (`core.hooksPath=.githooks`, relative → safe no-op in worktrees without it); `.github/workflows/govkit_checks.yml` runs report-only on every PR (proven firing green on PR #1405, run 29724326021). Branch protection unchanged (4 workflows red; a required check would block every merge). NOT yet merged to main (unrelated histories).

Self-tests: `validate_agent_payload` 33/33, `lint_operator_message` 32/32, `check_pr_body` 32/32, all exit 0.

See [[codex-sol-max-reasoning]], [[code-review-readiness]].
