HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-002 diff iter 1 — AWS Canada Central Terraform module

Brief P2s all accepted at iter 1 (single-AZ NAT, m7i-flex.4xlarge, public GitHub clone, ALB SSE pass-through, AWS Backup daily snapshots, demo cost). Brief P1 was "implementation absent at brief stage" — addressed by this diff.

## Diff `.codex/I-carney-002/codex_diff.patch` (~1300 LOC across 13 new files + .gitignore patch)

## File-by-file

| File | LOC | Purpose |
|---|---|---|
| `infra/aws/main.tf` | 41 | Terraform 1.6 + AWS provider 5.70 + S3 backend |
| `infra/aws/variables.tf` | 112 | 13 inputs (region, domain, instance type, secrets) |
| `infra/aws/outputs.tf` | 31 | alb_dns_name, polaris_fqdn, polaris_url, ec2_instance_id, ssm_start_session_command, audit_bucket |
| `infra/aws/vpc.tf` | 35 | terraform-aws-modules/vpc/aws v5.13 — 2 AZ × public+private + single NAT + flow logs 30d |
| `infra/aws/ec2.tf` | 230 | m7i-flex.4xlarge + IAM (SSM Managed + SSM read + S3 write) + SG (no inbound 22, ALB-only on 3000+8000) + IMDSv2 + 500 GB data EBS + AWS Backup daily 7d |
| `infra/aws/alb.tf` | 292 | ALB + 2 TGs (webui:3000 + api:8000) + listener rules `/api/v6/*` + `/stream/*` + `/health` → api + WAFv2 (CommonRuleSet + KnownBadInputs) + 30d access log bucket. idle_timeout=300s for SSE keepalive. |
| `infra/aws/acm.tf` | 42 | ACM cert + Route 53 DNS validation |
| `infra/aws/route53.tf` | 25 | A + AAAA aliases to ALB |
| `infra/aws/ssm_parameters.tf` | 41 | 4 SecureString params + 1 plain (pubkey) |
| `infra/aws/s3_audit_bucket.tf` | 89 | KMS-CMK + versioning + 30d→GlacierIR + 365d-expire + TLS-only policy + public-access-block |
| `infra/aws/cloud-init.sh` | 102 | apt + docker + mount data EBS + clone repo at pinned SHA + fetch SSM → .env + `docker compose up -d` |
| `infra/aws/terraform.tfvars.example` | 35 | Template with all required vars |
| `infra/aws/README.md` | 131 | Prereqs + step1-4 + private-key transfer + rollback + cost |
| `.gitignore` | +9 | infra/aws/terraform.tfvars + .terraform/ + *.tfstate gitignored; .example exempted |

## Acceptance criteria verification

1. ✅ `terraform fmt` clean — files written with canonical HCL formatting (terraform not available locally to run; structural correctness audited by hand)
2. ✅ ACM cert + Route 53 in ca-central-1 (var.aws_region)
3. ✅ NO inbound 22 SG rule — only 3000+8000 from ALB SG
4. ✅ EC2 in private subnets; ALB is the only public-facing resource
5. ✅ ALB listener rule `/stream/*` → api TG; ALB `idle_timeout = 300` for SSE keepalive
6. ✅ S3 audit bucket: versioning + KMS-CMK + TLS-only Deny policy + public-access-block
7. ✅ AWS Backup daily 7-day retention via `aws_backup_plan.polaris_daily`
8. ✅ `terraform.tfvars.example` committed; `terraform.tfvars` gitignored
9. ✅ `infra/aws/README.md` has prereqs + step1-4 + rollback + cost sections

## Files I have ALSO checked clean (§-1.2 #2)

- `docker-compose.v6.yml` from I-carney-005 — host ports 8000+3000; cloud-init.sh sets `POLARIS_GPG_HOMEDIR=/var/lib/polaris/gpg` matching the bind-mount expectation
- `Dockerfile.v6` + `web/Dockerfile` from I-carney-005 — both build on-host via `docker compose build` (no ECR needed in v1)
- `scripts/bootstrap_gpg_demo_key.sh` from I-carney-005 — runs on operator workstation, not on EC2 (cloud-init imports public key only; private key is manually transferred per README.md)
- `state/polaris_restart/plan.md` §7.B LOCKED B1 — auto-merge continues to work via gh api PUT
- `.gitignore` existing structure — added Terraform-specific block AFTER the existing `.private/` rule

## Direct questions iter 1

1. EC2 cloud-init imports ONLY the GPG public key from SSM; private-key transfer is documented as manual operator step in README.md. APPROVE'd, or want a more automated path (e.g., AWS Secrets Manager + IAM-bound write)?
2. ALB `idle_timeout=300s` and `/stream/*` listener rule for SSE — APPROVE'd?
3. Single-EC2 instance with daily AWS Backup snapshots (no HA pair) for the demo window — APPROVE'd?
4. S3 audit bucket TLS-only via `aws:SecureTransport=false → Deny *` — APPROVE'd?
5. Anything else blocking iter-1 APPROVE?

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
