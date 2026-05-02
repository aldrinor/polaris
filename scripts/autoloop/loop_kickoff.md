# POLARIS Autoloop — User-Facing Kickoff

**Plan v13 §K Step 17 (Live kickoff).** This document is the user's one-page
runbook for starting and managing the autoloop. **Do NOT run live kickoff until
all of §K Steps 1-16 (smoke tests) have passed.**

## Prerequisites (all of these MUST be satisfied)

Per Plan v13 §G decisions:

- [ ] **#1** Budget commitment signed (`$32-70k ceiling`, email to me)
- [ ] **#6** GitHub auth refreshed: `! gh auth refresh -h github.com -s workflow,admin:repo_hook,repo`
- [ ] **#9** Canonical reconciliation commit signed (BOOTSTRAP commit landed)
- [ ] **#10** Self-hosted Canadian GitHub Actions runner online (label `polaris-ca-bhs`)
- [ ] **#11** OPENAI_API_KEY set in `codex_runtime` GitHub Environment + budget cap
- [ ] **#12** ANTHROPIC_API_KEY in `.env` + monthly cap (~$300-800)
- [ ] **#13** GPG keypair created; public key at `docs/keys/msn_public.gpg`
- [ ] §K Step 16 smoke task `bootstrap_smoke` PASSED end-to-end
- [ ] `state/bootstrap_active` deleted (signals smoke complete, gate active)

Decisions #2 (OVH H200), #3 (Vast.ai), #4 (evaluator), #5 (IP counsel), #7
(walkthrough evaluators), #8 (Carney's office) land at their action-by dates per
§G — they don't block kickoff but do block specific phases.

## How to start

```bash
cd C:/POLARIS
pip install -r requirements-orchestrator.txt
# Verify env
test -n "$ANTHROPIC_API_KEY" || (echo "ANTHROPIC_API_KEY missing"; exit 1)
codex --version
# Start orchestrator
python scripts/autoloop/orchestrator.py
```

The orchestrator runs in the foreground; keep the terminal open. Heartbeat at
`state/orchestrator_status.json`.

## How to stop

- **Graceful**: `Ctrl-C` in the orchestrator terminal. Heartbeat preserved; resume
  by re-running the same command.
- **Halt-driven**: orchestrator emits `state/halt_<timestamp>_<task_id>.md` and
  exits 0 if any of the 7 halt conditions per Plan v13 §H fires. Read marker, fix,
  re-run.

## How to monitor

- `cat state/orchestrator_status.json` — current task, iter, phase
- `tail -f outputs/audits/codex_audit.jsonl` — append-only audit chain
- GitHub PR queue on `polaris` branch — every task lands as a PR

## How to halt the autoloop indefinitely

```bash
rm C:/POLARIS/state/autoloop_active   # disables the Stop hook block
# orchestrator process: Ctrl-C
```

To resume: `touch state/autoloop_active && python scripts/autoloop/orchestrator.py`

## Failure modes you might see (each maps to §H halt-condition)

| Halt # | Marker name | Likely cause | Resolution |
|---|---|---|---|
| 1 | `halt_*_*.md` | canonical hash drift | Investigate; do NOT auto-resume; user re-signs reconciliation |
| 2 | `halt_*_*.md` | 24h wall-clock exceeded | Review logs; bump deadline OR reduce task scope OR halt |
| 3 | `halt_*_*.md` | $100/task budget breach | Review spend log; bump cap with explicit user authorization OR halt |
| 4 | `halt_*_*.md` | 3× REQUEST_CHANGES on same task | Read latest verdict; revise task brief OR architecture |
| 5 | `halt_*_*.md` | user-action-blocked w/ no prep | Action the user-side task per §G OR define new prep sub-task |
| 6 | `halt_*_*.md` | cross-review integrity (Claude ↔ Codex disagree) | Manual resolution; update plan if substantive |
| 7 | `halt_*_*.md` | quality bar unreachable | User decides best-of-best switch OR pause |

## Things you should NOT do mid-build

- Edit any pinned canonical file (will trigger halt #1 on next task)
- Run `git push --force` on `polaris` (branch protection rejects)
- Run `git commit --no-verify` (precommit hook will be bypassed but server-side
  verdict-validate workflow rejects merge)
- Manually create files at `outputs/audits/verdicts/` (HMAC validation will fail)

## End state

When all tasks in `task_acceptance_matrix.yaml` reach APPROVE, orchestrator
prints "Loop complete" and exits. End-of-phase PRs `polaris → main` are still
your manual sign-off (per §C-server, requires 1 user approval each). Final
Phase 5 handover follows §G #8 (Carney's office contact + briefing).
