HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-007 — Carney demo runbook + transparency + Codex sign-off

GH#474. The final deliverable. Single-page operator playbook + Codex sign-off framework.

## Files I have ALSO checked clean (§-1.2 #2)

- `docs/transparency.md` (I-carney-003) — the reviewer-visible doc; this issue references it from the runbook
- `docs/deploy_runbook.md` (I-carney-005) — operator deploy doc; this issue's `carney_demo_runbook.md` is the day-of-demo playbook (different scope)
- `infra/aws/README.md` (I-carney-002) — terraform apply reference; runbook §1 cites it
- `scripts/bootstrap_gpg_demo_key.sh` (I-carney-005) — pre-demo step in §0
- All I-arch-001a..001f + I-carney-002/003/004/005 PRs merged — §1+§2 sign-off rely on this state

## Scope

3 new files:

1. **NEW `docs/carney_demo_runbook.md`** (~140 LOC): the day-of-demo operator playbook. 9 sections: §0 prereqs, §1 deploy day-1, §2 smoke test, §3 live-submission rehearsal (I-carney-006 acceptance), §4 live demo script, §5 fallback laptop, §6 30-min internal rehearsal, §7 Codex sign-off, §8 post-demo tear-down, §9 known limitations.

2. **NEW `.codex/I-carney-007/carney_demo_signoff_brief.md`**: the Codex brief the operator runs T-1 before demo. 6 sections: arch-001 PR audit, carney-00X PR audit, live deploy verifies (transparency + health + 2 bundle signatures), sovereignty/audit standards, halt-condition check, output schema for SHIP vs HALT.

3. **PATCH `state/active_issue.json`** — mark I-carney-007 as in_progress (per CLAUDE.md §3.0 issue-driven workflow; this is the LAST issue before the Carney demo).

## Acceptance criteria

1. `docs/carney_demo_runbook.md` has all 9 sections
2. Sign-off brief outputs a `ship_decision: SHIP|HALT` machine-parseable verdict
3. Runbook references I-carney-006 (live submission rehearsal) — that issue's acceptance ties into §3 of the runbook
4. Codex sign-off can run pre-demo (T-1) and verify all merged + live deploy paths
5. Runbook §9 honestly discloses known limitations (single-AZ EC2, manual GPG rotation, etc.)

## Direct questions iter 1

1. Single runbook for the demo day vs splitting into deploy + demo + tear-down — APPROVE'd as single doc?
2. Codex sign-off brief calls for `ship_decision: SHIP|HALT` machine-parseable verdict — APPROVE'd?
3. I-carney-006 (live-submission rehearsal) is referenced from runbook §3 but its execution happens AFTER this issue ships (requires the deployed system). Acceptable to mark I-carney-006 as blocked-on-deploy (operator runs the rehearsal post-PR-485), or want to merge it into this issue?
4. Anything else blocking iter-1 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
