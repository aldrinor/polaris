HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-002 — AWS Canada Central (ca-central-1) infrastructure as code

GH#470. Critical-path day 13-14. Provisions the Carney production environment in AWS Montréal (ca-central-1) using Terraform: VPC + EC2 m7i-flex.4xlarge + ALB + ACM + Route 53 + SSM Parameter Store + EBS snapshots + S3 audit bucket.

The I-carney-005 docker compose stack (`docker-compose.v6.yml`) is the workload that runs on the EC2 instance. This issue is the cloud substrate that hosts it.

## Files I have ALSO checked clean (§-1.2 #2)

- `docker-compose.v6.yml` — single-host compose with redis+api+worker+webui. Maps host ports 8000 + 3000. State persisted in `shared_state` named volume + bind-mounted `./outputs ./logs ./data`. EC2 instance must have `/var/lib/polaris` directory with the right perms for the bind mounts.
- `Dockerfile.v6` + `web/Dockerfile` — build on the EC2 host directly via `docker compose build`. No need for ECR in v1 (single-host).
- `docs/deploy_runbook.md` — operator runbook assumes single-host. AWS deployment doc lives separately at `infra/aws/README.md` (this PR).
- `polaris-controls/CHARTER.md` — admin authority + cage constraints continue under AWS deployment. SSH from operator workstation via SSM Session Manager (no inbound SSH from internet).
- `state/polaris_restart/plan.md` §7.B LOCKED B1 — auto-merge stays in force on the AWS bring-up branch.
- `outputs/polaris_demo_pubkey.asc` (from I-carney-005 bootstrap) — published at `https://polaris.<domain>/transparency/pubkey.asc` for reviewers (I-carney-003 mounts this).

## Scope

10 files in `infra/aws/` directory + 1 doc file:

1. **`infra/aws/main.tf`** — root Terraform module, AWS provider region=ca-central-1, S3 backend for state (bucket name from variable `tf_state_bucket`).

2. **`infra/aws/vpc.tf`** — uses `terraform-aws-modules/vpc/aws` v5.x:
   - 1 VPC (10.0.0.0/16)
   - 2 public subnets (one per AZ ca-central-1a + ca-central-1b for ALB)
   - 2 private subnets (one per AZ for EC2 instances)
   - 1 NAT gateway (single-AZ for cost; HA-NAT is a Phase-2 follow-up)
   - VPC flow logs to CloudWatch with 30-day retention

3. **`infra/aws/ec2.tf`** — single m7i-flex.4xlarge instance:
   - Ubuntu 24.04 LTS AMI (data source lookup for latest)
   - Instance profile with: SSM Managed Instance Core (for Session Manager) + read access to specific Parameter Store paths under `/polaris/v6/` + read access to specific S3 prefixes
   - Security group: NO inbound 22, NO inbound 80/443 (ALB terminates TLS and forwards on 8000+3000 via private network); outbound 443 to anywhere (pulls Docker images + LLM API egress)
   - 200 GB gp3 root volume + 500 GB gp3 data volume mounted at `/var/lib/polaris` (Docker volumes + bind mounts land here)
   - User-data: install docker compose v2 + clone the polaris repo to `/opt/polaris` + pull secrets from SSM into `/opt/polaris/.env` + `docker compose -f docker-compose.v6.yml up -d` (idempotent on reboot)
   - Daily EBS snapshot via AWS Backup with 7-day retention

4. **`infra/aws/alb.tf`** — Application Load Balancer:
   - Public-facing, dualstack (IPv4+IPv6)
   - HTTPS:443 listener with ACM cert
   - Two target groups: `webui` → instance:3000, `api` → instance:8000
   - Listener rules: `/api/v6/*` → api TG, `/stream/*` → api TG (SSE), everything else → webui TG
   - HTTP:80 → 301 to HTTPS
   - WAF v2 attached with AWS managed rules (CommonRuleSet + KnownBadInputs)
   - Access logs to S3 bucket with 30-day retention

5. **`infra/aws/acm.tf`** — ACM certificate for `polaris.<domain>` + `*.polaris.<domain>` via DNS validation against Route 53 zone (zone is pre-existing, looked up by variable `route53_zone_name`).

6. **`infra/aws/route53.tf`** — A record `polaris.<domain>` → ALB alias.

7. **`infra/aws/ssm_parameters.tf`** — SSM Parameter Store entries (SecureString) for:
   - `/polaris/v6/openrouter_api_key`
   - `/polaris/v6/serper_api_key`
   - `/polaris/v6/semantic_scholar_api_key` (optional)
   - `/polaris/v6/polaris_gpg_key_id`
   - Values supplied via Terraform vars marked sensitive. The EC2 user-data fetches these via `aws ssm get-parameter --with-decryption` and writes them to `/opt/polaris/.env`.

8. **`infra/aws/s3_audit_bucket.tf`** — versioned S3 bucket for daily exported audit bundles. Lifecycle: transition to Glacier Instant Retrieval after 30 days, expire after 1 year. KMS encryption with customer-managed key. Bucket policy denies non-TLS access.

9. **`infra/aws/variables.tf`** + **`infra/aws/outputs.tf`** + **`infra/aws/terraform.tfvars.example`** — variable declarations + outputs (instance_id, alb_dns_name, route53_record) + example tfvars file.

10. **`infra/aws/cloud-init.sh`** — user-data script that the EC2 instance executes on first boot:
    - apt update + install docker.io + docker-compose-plugin + git + awscli
    - mkdir -p /opt/polaris && git clone https://github.com/aldrinor/polaris.git /opt/polaris (specific commit SHA pinned via tfvar)
    - mount data volume at /var/lib/polaris with ext4 + write /etc/fstab entry for reboot persistence
    - fetch SSM parameters → write /opt/polaris/.env
    - run `bash scripts/bootstrap_gpg_demo_key.sh` for the demo key
    - `docker compose -f /opt/polaris/docker-compose.v6.yml up -d`

11. **`infra/aws/README.md`** — operator doc:
    - Prereqs: AWS CLI configured for ca-central-1, pre-existing Route 53 zone, IAM admin
    - Step 1: `terraform init` (S3 backend bootstrap)
    - Step 2: copy `terraform.tfvars.example` to `terraform.tfvars`, fill in secrets
    - Step 3: `terraform plan` then `terraform apply`
    - Step 4: wait ~5 min for EC2 cloud-init; `curl https://polaris.<domain>/api/v6/health`
    - Rollback: `terraform destroy`
    - Cost: ~$280/mo (m7i-flex.4xlarge + ALB + NAT + 700 GB EBS + S3) — for Carney demo timeframe only; tear down after the meeting.

## Acceptance criteria

1. `terraform fmt` exits clean (Terraform 1.6+)
2. `terraform validate` exits clean for ca-central-1 provider
3. NO inbound SSH security group rule — SSM Session Manager is the only access path
4. NO public-facing EC2 — instance is in private subnets, ALB is the only public surface
5. ALB listener routes `/stream/*` to the api target group (SSE pass-through with idle timeout >= 300s)
6. S3 audit bucket has versioning + KMS-CMK encryption + TLS-only bucket policy
7. EBS daily snapshot via AWS Backup with 7-day retention
8. `terraform.tfvars.example` is committed; the real `terraform.tfvars` is gitignored
9. `infra/aws/README.md` has prereqs / step1-4 / rollback / cost sections

## Direct questions iter 1

1. Single-AZ NAT + single-EC2 (no HA) for the Carney demo — APPROVE'd? Or want multi-AZ from day 1?
2. m7i-flex.4xlarge (16 vCPU / 64 GB RAM) as the workload size — APPROVE'd, or want a different instance family (c7i, r7i, m7i-large)?
3. Cloud-init clones the repo from public GitHub at a pinned commit SHA — APPROVE'd? Or want ECR + pre-built images instead to avoid network-during-boot?
4. ALB pass-through for SSE `/stream/*` with `idle_timeout >= 300s` (vs CloudFront which terminates SSE at edge) — APPROVE'd?
5. AWS Backup daily EBS snapshots + 7-day retention vs Lifecycle Manager (DLM) — APPROVE'd?
6. Demo cost ~$280/mo accepted as Carney-demo-window-only (Codex memory note: cost is not a factor in model picks; this is procurement context). APPROVE'd as documented operator cost or want to suppress?
7. Anything else blocking iter-1 APPROVE?

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
