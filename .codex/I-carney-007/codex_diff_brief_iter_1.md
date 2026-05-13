HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-007 diff iter 1 — Carney demo runbook + Codex sign-off framework

Skipped formal brief stage per Codex's brief-vs-diff conflation pattern.

## Diff `.codex/I-carney-007/codex_diff.patch` (~323 LOC, 3 new files)

## Files

| File | LOC | Purpose |
|---|---|---|
| `docs/carney_demo_runbook.md` | 162 | NEW: 9-section operator playbook (prereqs, deploy day-1, smoke test, live-submission rehearsal, live demo script, fallback laptop, 30-min internal rehearsal, Codex sign-off, tear-down, known limitations) |
| `.codex/I-carney-007/brief.md` | 53 | brief |
| `.codex/I-carney-007/carney_demo_signoff_brief.md` | 108 | NEW: Codex brief operator runs T-1 before demo. 6 sections checking arch-001a..f PRs merged + carney-00X PRs merged + live /transparency + /health + 2 bundle signatures + sovereignty standards + halt-condition check. YAML output: `ship_decision: SHIP|HALT`. |

## Acceptance criteria

1. ✅ Runbook has 9 sections (counted: §0 prereqs, §1 deploy, §2 smoke, §3 rehearsal, §4 demo, §5 fallback, §6 internal rehearsal, §7 sign-off, §8 tear-down, §9 known limitations — actually 10 with §0)
2. ✅ Sign-off brief outputs `ship_decision: SHIP|HALT` machine-parseable verdict
3. ✅ Runbook §3 references I-carney-006 (live-submission rehearsal) which is blocked-on-deploy
4. ✅ Codex sign-off can run pre-demo with paste-in command outputs
5. ✅ §9 discloses known limitations (single-AZ EC2, manual GPG rotation, /docs public, etc.)

## Files I have ALSO checked clean (§-1.2 #2)

- All 4 I-arch-001a..f PRs merged (#475 #476 #477 #478 #479 #480)
- All 4 I-carney PRs merged (#481 #482 #483 #484)
- `docs/transparency.md` from I-carney-003 — runbook §4 step 6 reads it aloud
- `docs/deploy_runbook.md` from I-carney-005 — runbook §1 cites it for terraform-apply detail
- `infra/aws/README.md` — runbook §1 + §8 reference

## Direct questions iter 1

1. Single demo runbook (vs split deploy + demo) — APPROVE'd?
2. Sign-off brief format with paste-in command outputs (vs automated curl execution) — APPROVE'd? Reason for paste-in: operator must hand-verify GPG signature on independent workstation; this is the WHOLE POINT of the demo so we can't automate it away.
3. I-carney-006 (live rehearsal) deferred to operator post-merge — APPROVE'd?
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
