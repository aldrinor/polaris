# ARCHIVED 2026-05-13 — AWS Canada Central deploy

> **DO NOT USE for the Carney demo.** User directive 2026-05-13: full-sovereign
> Canadian deploy, no US-owned company anywhere. AWS data is physically in
> Montréal under ca-central-1 but Amazon is a US corporation subject to US
> CLOUD Act + US FISA — fails the sovereignty audit. The active Carney deploy
> lives at `infra/vexxhost/` (Canadian-owned hosting) paired with `infra/ovh/`
> (French-owned, in Quebec, for H200 GPU inference).
>
> See `infra/vexxhost/README.md` for the active deploy path.
>
> Keep this module: useful reference for VPC + ALB + ACM + WAF + SSM +
> Secrets Manager patterns for any future non-sovereign deployment.

---

# I-carney-002 — AWS Canada Central deploy (archived)

Terraform module that provisions the Carney demo on AWS ca-central-1 (Montréal). Hosts the `docker-compose.v6.yml` stack from I-carney-005.

## Prereqs

- Terraform >= 1.6.0
- AWS CLI configured (`aws sts get-caller-identity` resolves)
- Pre-existing Route 53 public hosted zone for `<domain_name>`
- IAM permissions: VPC + EC2 + ELB + ACM + Route 53 + KMS + S3 + SSM + IAM + WAF + Backup
- An S3 bucket for Terraform state (created out-of-band; bootstrap one with
  `aws s3 mb s3://polaris-carney-tf-state --region ca-central-1` then
  `aws s3api put-bucket-versioning --bucket polaris-carney-tf-state --versioning-configuration Status=Enabled`)
- The Carney demo GPG signing key has been generated via
  `scripts/bootstrap_gpg_demo_key.sh` from the I-carney-005 substrate;
  you have `state/polaris_gpg_keyid.txt` and `outputs/polaris_demo_pubkey.asc`

## Step 1 — `terraform init`

```bash
cd infra/aws
terraform init \
    -backend-config="bucket=polaris-carney-tf-state" \
    -backend-config="region=ca-central-1" \
    -backend-config="key=polaris-carney/terraform.tfstate"
```

## Step 2 — fill in tfvars

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set domain_name, route53_zone_name, secrets,
# polaris_repo_commit (current polaris HEAD SHA), polaris_gpg_key_id,
# polaris_gpg_pubkey (paste from outputs/polaris_demo_pubkey.asc).
```

`terraform.tfvars` is gitignored via the repo-root `.gitignore` — never commit it.

## Step 3 — `terraform plan` then `terraform apply`

```bash
terraform plan -out plan.bin
terraform apply plan.bin
```

Takes ~10 minutes. Watch for:
- VPC + NAT (~3 min)
- ACM cert + DNS validation (~3 min for Route 53 propagation)
- EC2 boot + cloud-init (~5 min — docker pulls + compose build)

## Step 4 — smoke test

```bash
# Public endpoint:
curl -fsS https://polaris.<your-domain>/health

# Webui:
curl -fsS https://polaris.<your-domain>/

# Submit a run:
curl -fsS -X POST https://polaris.<your-domain>/api/v6/runs \
    -H 'content-type: application/json' \
    -d '{"template":"clinical","question":"smoke test"}'

# SSH-via-SSM into the host:
$(terraform output -raw ssm_start_session_command)
```

## Private GPG key transfer (manual; one-time)

Cloud-init imports only the public key into the EC2 GNUPGHOME. The private key signing capability requires you to transfer the secret key from your operator workstation:

```bash
# On operator workstation:
gpg --homedir ~/.gnupg-polaris --armor --export-secret-key "<fingerprint>" > /tmp/polaris-secret.asc

# Open an SSM session to the EC2:
aws ssm start-session --target $(terraform output -raw ec2_instance_id) --region ca-central-1

# On the EC2 host:
sudo cat > /tmp/polaris-secret.asc <<EOF
<paste the armored secret key here>
EOF
sudo GNUPGHOME=/var/lib/polaris/gpg gpg --import /tmp/polaris-secret.asc
sudo shred -u /tmp/polaris-secret.asc

# Restart the api + worker so the GPG signer picks up the now-present
# private key:
cd /opt/polaris
sudo docker compose -f docker-compose.v6.yml restart api worker
```

This is intentionally manual — burning the private key into Terraform / SSM SecureString would put it inside CloudTrail decryption logs and create a longer audit trail than the demo requires.

## Rollback

```bash
terraform destroy
```

WARN: destroys VPC + EC2 + EBS + S3 audit bucket (with all bundles). EBS snapshots in AWS Backup survive `terraform destroy` (separately governed by the backup vault retention) but the vault itself is also torn down — recover snapshots BEFORE destroy if needed.

## Cost (ca-central-1, May 2026 prices)

| Resource | Hourly | Monthly |
|---|---|---|
| m7i-flex.4xlarge | $0.244 | $176 |
| ALB + WAF | ~$0.03 | $22 |
| NAT gateway (single AZ) | $0.045 | $33 |
| EBS gp3 700 GB | ~$0.10/GB/mo | $70 |
| S3 + KMS | low | <$5 |
| **Total demo-window** | | **~$306/mo** |

For Carney demo timeframe only — tear down after the meeting.

## Files in this module

| File | Purpose |
|---|---|
| `main.tf` | Provider + S3 backend |
| `variables.tf` | All inputs |
| `outputs.tf` | Operator outputs (FQDN, instance id, SSM cmd) |
| `vpc.tf` | VPC + subnets + NAT + flow logs |
| `ec2.tf` | EC2 instance + IAM + SG + data EBS + AWS Backup |
| `alb.tf` | ALB + 2 target groups + listener rules + WAF + log bucket |
| `acm.tf` | ACM cert with DNS validation |
| `route53.tf` | A alias to ALB (AAAA deferred to Phase-2 IPv6 follow-up) |
| `ssm_parameters.tf` | SSM Parameter Store entries for secrets |
| `s3_audit_bucket.tf` | KMS-encrypted versioned bucket for audit bundles |
| `cloud-init.sh` | EC2 user-data (apt, compose pull, SSM secrets, stack up) |
| `terraform.tfvars.example` | Template tfvars; copy to terraform.tfvars |
