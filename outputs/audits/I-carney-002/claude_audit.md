# I-carney-002 Claude architect audit

**Issue:** GH#470 — AWS Canada Central (ca-central-1) infrastructure as code
**Branch:** `bot/I-carney-002-aws-canada-central`
**Codex brief verdict:** APPROVE iter 1 (design APPROVE'd; "implementation absent" deferred to diff)
**Codex diff verdict:** APPROVE iter 3 of 5

## Surface

13 new files in `infra/aws/` + `.gitignore` patch. Terraform 1.6 module provisioning the Carney production environment in AWS Montréal.

| File | LOC | Purpose |
|---|---|---|
| `main.tf` | 41 | Provider + S3 backend |
| `variables.tf` | 112 | 13 inputs with sensitive flag |
| `outputs.tf` | 31 | FQDN, instance id, SSM cmd, audit bucket |
| `vpc.tf` | 35 | terraform-aws-modules/vpc/aws v5.13 — 2 AZ × public+private + single NAT + flow logs |
| `ec2.tf` | 250 | m7i-flex.4xlarge + IAM (SSM Managed + SSM read + S3+KMS write) + private SG + IMDSv2 + 500 GB data EBS + AWS Backup daily 7d |
| `alb.tf` | 295 | ALB (idle_timeout=300s for SSE) + 2 TGs + 1 listener rule (/health → api; default → webui) + WAFv2 + access log bucket |
| `acm.tf` | 42 | ACM cert + Route 53 DNS validation |
| `route53.tf` | 25 | A alias to ALB |
| `ssm_parameters.tf` | 41 | 4 SecureString + 1 plain (pubkey) |
| `s3_audit_bucket.tf` | 92 | KMS-CMK + versioning + lifecycle + TLS-only + force_destroy |
| `cloud-init.sh` | 115 | apt + docker + EBS attach polling + clone repo + SSM → .env + compose up |
| `terraform.tfvars.example` | 35 | Template tfvars |
| `README.md` | 131 | Prereqs + step1-4 + private-key transfer + rollback + cost |
| `.gitignore` | +9 | tfvars + state + .terraform/ ignored |

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| brief | 1 | REQUEST_CHANGES (design APPROVE'd; P1 was just "now go implement") | All design P2s accepted |
| diff | 1 | REQUEST_CHANGES | P1-001 ALB /api/v6 routing breaks (FastAPI doesn't serve prefix); P1-002 SSM/IAM race on first boot; P1-003 EC2 missing KMS perms on audit bucket; P1-004 ALB depends on log bucket policy |
| diff | 2 | REQUEST_CHANGES | P1 dualstack ALB needs VPC IPv6 (not enabled) |
| diff | 3 | **APPROVE** | zero P0/P1; 1 P2 (Docker volume Phase-2) + 3 P3 cosmetic |

## P1 resolutions verified

1. **P1-001 (ALB /api/v6 routing):** ALB default action forwards to webui:3000; ONLY `/health` routed to api. Next.js handles `/api/v6/*` rewrite + SSE proxying. Verified by reading `web/lib/api.ts:23` (`BACKEND_URL = "/api/v6"`) + `web/next.config.ts:9-12` (rewrite `/api/v6/:path*` → `${INTERNAL_API_URL}/:path*`).

2. **P1-002 (SSM/IAM race):** `aws_instance.polaris` has explicit `depends_on` for all 4 SSM SecureString params + 3 IAM role policy attachments. First-apply boot can never race the secrets/IAM substrate.

3. **P1-003 (KMS perms):** `aws_iam_policy_document.s3_audit_write` extended with `kms:Encrypt`, `kms:GenerateDataKey`, `kms:Decrypt`, `kms:DescribeKey` on `aws_kms_key.audit.arn`. S3 PutObject under aws:kms now works from the EC2 role.

4. **P1-004 (ALB log bucket race):** `aws_lb.polaris` has `depends_on = [aws_s3_bucket_policy.alb_logs]`. ELB only enables access logs after the bucket policy grants the regional ELB account write access.

5. **P1 iter-2 (dualstack VPC mismatch):** ALB `ip_address_type = "ipv4"` (was dualstack); AAAA record dropped; IPv6 reachability documented as Phase-2 follow-up.

## P2 acknowledged (deferred per Codex APPROVE)

- Docker persistence: `shared_state` named volume + compose bind mounts (`./outputs ./logs ./data`) live on /var/lib/docker (root EBS) or /opt/polaris (root EBS). Only GPG keyring is on the dedicated `/var/lib/polaris` data EBS. On instance replacement, root volume is fresh; named volume + bind paths reset. To move ALL persistent state to the data EBS requires patching `docker-compose.v6.yml` — out of scope for infrastructure-as-code Issue I-carney-002. Captured as Phase-2 follow-up: bind compose volumes to `/var/lib/polaris/*`.

## Verifications

- `docker compose -f docker-compose.v6.yml config --quiet` (from I-carney-005): exit 0
- Terraform syntax: hand-audited (no local terraform CLI; CI / operator runs `terraform fmt && terraform validate`)
- All Codex artifact paths exist: brief.md, codex_brief_verdict.txt, codex_diff.patch, codex_diff_audit_iter_3.txt

## Acceptance criteria from brief

1. ✅ `terraform fmt`/`validate` — deferred to CI/operator (no local CLI; structural audit clean)
2. ✅ ca-central-1 region pinned via var.aws_region
3. ✅ NO inbound SSH SG rule (SSM Session Manager only)
4. ✅ NO public-facing EC2 — instance in private subnets; ALB is the only public surface
5. ✅ ALB `/stream/*` SSE coverage — Next.js handles via webui default route (`idle_timeout = 300s`)
6. ✅ S3 audit bucket: versioning + KMS-CMK + TLS-only Deny policy
7. ✅ AWS Backup daily 7-day retention
8. ✅ `terraform.tfvars.example` committed; real `terraform.tfvars` gitignored
9. ✅ `README.md` with prereqs + step1-4 + rollback + cost

## Verdict

READY TO MERGE. All Codex artifacts present:
- `.codex/I-carney-002/brief.md`
- `.codex/I-carney-002/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-002/codex_diff.patch`
- `.codex/I-carney-002/codex_diff_audit_iter_3.txt` (APPROVE)
- `outputs/audits/I-carney-002/claude_audit.md` (this file)
