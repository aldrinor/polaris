# I-carney-007 Claude architect audit

**Issue:** GH#474 — Carney demo runbook + transparency + fallback laptop + 30-min internal rehearsal + Codex sign-off
**Branch:** `bot/I-carney-007-demo-runbook-signoff`
**Codex diff verdict:** APPROVE iter 3 of 5

## Surface

| File | LOC | Purpose |
|---|---|---|
| `docs/carney_demo_runbook.md` | 180 | NEW: 10-section playbook (§0 prereqs through §9 known limitations) |
| `.codex/I-carney-007/carney_demo_signoff_brief.md` | 108 | NEW: Codex T-1 sign-off brief; outputs `ship_decision: SHIP|HALT` |
| `.codex/I-carney-007/brief.md` + diff_brief_iter_{1,2,3}.md | 4 docs | Codex iteration trail |

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| diff | 1 | REQUEST_CHANGES | P1-1 sign-off evidence piped from placeholders; P1-2 egress lockdown install missing; P1-3 fallback laptop env wrong |
| diff | 2 | REQUEST_CHANGES | P1-3 carry-over: SSM vs SM service confusion + sudo subshell bug |
| diff | 3 | **APPROVE** | zero P0/P1; 2 P2 cosmetic non-blocking |

## P1 resolutions

1. **P1-1 evidence ingestion:** §7 now does heredoc-append of curl/GPG/iptables output to a working evidence file, with placeholder-abort check (`<your-domain>` etc.). Codex sees real evidence, not template.
2. **P1-2 egress lockdown:** §1b inserted between deploy + smoke as MANDATORY step. Operator SSM-into-host, runs lockdown, verifies both chains.
3. **P1-3 fallback laptop:** `ssm_get` (Parameter Store) for API keys + GPG fingerprint; `sm_get` (Secrets Manager) for JWT + accounts + private key. Static_accounts via `sm_get ... | sudo tee` to avoid sudo subshell variable loss.

## Verdict

READY TO MERGE. All Codex artifacts present:
- `.codex/I-carney-007/brief.md`
- `.codex/I-carney-007/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-007/codex_diff.patch`
- `.codex/I-carney-007/codex_diff_audit_iter_3.txt` (APPROVE)
- `outputs/audits/I-carney-007/claude_audit.md` (this file)

## What ships in this PR

After PR #485 merges, the Carney demo is **code-complete**. Remaining work is operator-side:

1. Operator runs `terraform apply` per `docs/carney_demo_runbook.md §1`.
2. Operator runs `scripts/egress_lockdown.sh` per §1b.
3. Operator executes I-carney-006 (live-submission rehearsal) per §3 — generates audit binder.
4. Operator runs the Codex sign-off brief T-1 per §7.
5. Day-of-demo: §4 script.
6. Post-demo: §8 tear-down.

I-carney-006 stays as `pending` in the task list; operator marks it `completed` after running the rehearsal on the deployed system.
