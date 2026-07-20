# Prompt to paste into Claude VM

TASK: install the governance kit, prove every piece actually blocks, wire it so it runs automatically, and adopt it in how you work. Do the whole thing, then report once.

## Why this exists

Five failures keep repeating in this project. A governance kit was designed to stop each one mechanically. It was designed independently by Fable 5, Codex, and Kimi K3, then reviewed by Codex at maximum reasoning, and every piece was proven to block a real violation before it was committed.

The five failures:
1. Agents hand each other partial answers, so findings arrive drip-fed over many rounds.
2. An agent fixes the one spot it tripped on and misses the rest of the data path.
3. GitHub and the docs are inconsistent, so nobody can reconstruct why a change happened.
4. Messages to the operator are long, nested, and full of jargon. The operator is BLIND and reads by ear.
5. Agents dump technical choices on the operator, who does not have the context to decide.

## Step 1 — get the kit and prove it runs here

```
cd /workspace/POLARIS
git fetch origin bot/repo-knowledge-base
git checkout bot/repo-knowledge-base   # or merge it into your branch
ls gov/ tools/validate_agent_payload.py tools/lint_operator_message.py tools/check_pr_body.py
```

Run all three self-tests and paste the real output:

```
python3 tools/validate_agent_payload.py --selftest
python3 tools/lint_operator_message.py --selftest
python3 tools/check_pr_body.py --selftest
```

Expected on the laptop: 33/33, 32/32, 32/32, all exit 0. If any number differs on the VM, STOP and report the exact failing case. Do not proceed with a broken checker.

## Step 2 — read the kit

Read these before changing anything:
- `gov/operator_voice.md` - how to write to the operator
- `gov/decision_protocol.md` - how to ask, or not ask, for a decision
- `gov/agent_payload.schema.json` - what every sub-agent must return
- `gov/spawn_templates/claude.md`, `codex.md`, `kimi.md` - what to prepend when spawning each model
- `gov/issue_template.md` and `gov/pull_request_template.md`
- `docs/agent_environment/00_plan.md` - the setup plan
- `docs/agent_environment/proposal_kimi_k3.md` - the fullest design, useful for anything ambiguous

## Step 3 — prove each checker BLOCKS, with your own inputs

A file existing proves nothing. Blocking proves it. Write your own bad inputs, not the built-in fixtures, and confirm the exit code is non-zero:

```
# a message with jargon, nested bullets, and too many sentences -> must exit 1
python3 tools/lint_operator_message.py your_bad_message.md ; echo "exit=$?"
# a payload claiming DONE with an empty not_covered -> must exit 1
python3 tools/validate_agent_payload.py your_bad_payload.json ; echo "exit=$?"
# a PR body missing the rollback section -> must exit 1
python3 tools/check_pr_body.py your_bad_pr_body.md ; echo "exit=$?"
```

Paste the real exit codes. Non-zero on bad input is the whole point: a hook only blocks on non-zero.

## Step 4 — wire them so they run without anyone remembering

Known state, verified on 2026-07-19, do not assume otherwise:
- `git config core.hooksPath` points at `C:\POLARIS\.git\hooks`, a path that no longer exists. Every git hook is currently a silent no-op. Fix the path or unset it.
- The existing `pre-commit` and `commit-msg` hooks are deliberate stubs from 2026-05-04 that `exit 0`. Enforcement was moved server-side on purpose.
- Branch protection on `main` requires ZERO status checks. Twelve workflow files exist and not one can block a merge. PR review IS required and admins are included.
- Four workflows fail 100% of runs: `codex_verdict_check`, `protection_drift_check`, `cleanup_pr_ancestry_check`, `architecture-conformance`. Three are green: `legacy-protection`, `status-schema-parity`, `python-ci`.

Do this:
1. Fix `core.hooksPath` so hooks resolve, and verify with `git rev-parse --git-path hooks`.
2. Write a real `pre-commit` hook that runs the three checkers on staged files only, and prove it blocks a deliberately bad commit.
3. Add a CI workflow that runs all three checkers on every PR. Start it report-only.
4. Do NOT change branch protection. Four workflows are red; making checks required now would block every merge. Report what you would require once they are green.

## Step 5 — adopt the kit in how you work, starting now

- Before any message to the operator, run it through `tools/lint_operator_message.py`. Fix what it flags.
- When spawning any sub-agent, prepend the matching file from `gov/spawn_templates/` and require the payload schema back. Reject a payload with an empty `not_covered`.
- Before scaling any fan-out: run ONE agent, validate its payload, then 5, then the rest. If more than 20 percent fail, kill the fan-out and report.
- Open issues with `gov/issue_template.md`. It requires the counting COMMAND and its pasted output. Estimates are rejected. It requires a trace of the whole data path with every chokepoint named.
- Open PRs with `gov/pull_request_template.md` and check the body with `tools/check_pr_body.py` before opening.
- Follow `gov/decision_protocol.md`: decide and say what you decided and why, or ask exactly ONE question with your recommendation marked and one plain line per option.

## Step 6 — report once, then stop

Report in plain English. Maximum 12 sentences. Flat lists only, never nested. No jargon, no emoji, no cheerleading. State:
- What now exists on the VM.
- What each piece BLOCKS, with the real exit code as proof.
- What you wired, and the evidence it fired.
- What you did NOT do, and why.
- The single next action.

Run your own report through `tools/lint_operator_message.py` before sending it. If it fails, fix it.

## Rules that apply to you while doing this

- One shot. Everything in your first reply. There are no follow-up rounds.
- Measure, do not estimate. Any number you state comes from a command you ran; paste the command.
- Blocking is proof. Existence is not.
- Never hand the operator a decision needing context they do not have.
- If you get stuck twice on the same step, or stuck for 30 minutes, stop and say what you tried. Silent sitting is a protocol violation.
