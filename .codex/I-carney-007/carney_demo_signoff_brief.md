HARD ITERATION CAP: 5 per document. This is the FINAL demo sign-off.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-007 demo sign-off — does this deploy ship?

Operator: paste the outputs of the §3 commands below before submitting this brief.

## §1 — Architecture seam (I-arch-001a..001f) shipped + tested

Confirm all 6 sub-issues merged:

```
$ gh pr list --state merged --search "I-arch-001 in:title"
#475 I-arch-001a — run_store atomic schema (...)
#476 I-arch-001b — V30 contract synthesizer (...)
#477 I-arch-001c — refine TEMPLATE_TO_SCOPE_DOMAIN (...)
#478 I-arch-001d — artifact_to_slice_chain bridge (...)
#479 I-arch-001e — SSE Redis Streams (...)
#480 I-arch-001f — e2e capstone test (...)
```

VERDICT: PASS / FAIL on this section.

## §2 — Carney deploy substrate (I-carney-002, 003, 004, 005) shipped

```
$ gh pr list --state merged --search "I-carney-00 in:title"
#481 I-carney-005 — v6 deploy substrate
#482 I-carney-002 — AWS Canada Central infrastructure
#483 I-carney-003 — Sovereignty + transparency endpoint + egress controls
#484 I-carney-004 — Static_accounts auth + AWS Secrets Manager
```

VERDICT: PASS / FAIL.

## §3 — Live deploy verifies (paste outputs)

### 3a. /transparency reachable + signed

```
$ curl -fsS https://polaris.<domain>/transparency | jq
{
  "region": "ca-central-1",
  "git_commit": "<sha>",
  ...
}
```

Paste the actual response. VERDICT: PASS / FAIL.

### 3b. /health reachable

```
$ curl -fsS https://polaris.<domain>/health
{"status":"ok","version":"..."}
```

VERDICT: PASS / FAIL.

### 3c. Bundle signature verifies on Q1 (tirzepatide)

```
$ TOKEN=$(curl -fsS -X POST .../auth/login ... | jq -r .access_token)
$ # Submit, wait, fetch bundle.tar.gz
$ tar -xzf bundle.tar.gz && cd audit_*
$ gpg --verify manifest.yaml.asc manifest.yaml
gpg: Good signature from "POLARIS Carney Demo <signing@polaris.local>"
```

VERDICT: PASS / FAIL.

### 3d. Bundle signature verifies on Q2 (different question)

Same flow with a Canada-US or pharmacare question. VERDICT: PASS / FAIL.

## §4 — Sovereignty + audit standards

- /transparency lists T1-only cleared tiers per CLAUDE.md §9.1 invariant 1
- Bundle's verified_report has zero T2+ sources cited in passing sentences
- Bundle's manifest.yaml decision_id + report_id + pool_id chain matches the source artifact directory
- egress_lockdown.sh has been run on the EC2 host (operator confirms via SSM session)

VERDICT: PASS / FAIL on each.

## §5 — Halt conditions per CLAUDE.md §3.0

Operator confirms NONE of these fired in the last 24h:
- canonical pin SHA mismatch
- CHARTER.md / PLAN.md SHA pin mismatch
- Issue jump attempt
- PR opened with missing artifact triple
- Codex unavailable > 1h
- 2-cycle repeated root cause
- 200-LOC PR cap exceeded without exemption
- 3+ PRs queued for user in 24h (reviewer fatigue)

VERDICT: ALL CLEAR / SOME FIRED.

## §6 — Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
ship_decision: SHIP | HALT
sections_passed: [§1, §2, §3a, §3b, §3c, §3d, §4, §5]
sections_failed: [...]
blocking_concerns: [...]
non_blocking_concerns_recorded_as_followup_issues: [...]
```
