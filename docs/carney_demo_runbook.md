# Carney demo runbook — operator playbook

This is the single source of truth for the PM Mark Carney POLARIS demo. Read end-to-end before the meeting; refer back during.

**Demo target window:** 2026-06-05 to 2026-06-09. Updated 2026-05-13 after all I-arch-001* + I-carney-002..005 PRs merged.

---

## §0 — Prereqs (1 week before demo)

| Item | Owner | Status |
|---|---|---|
| AWS account with ca-central-1 IAM admin | Ops | (verify) |
| Route 53 public hosted zone | Ops | (verify) |
| `terraform` + `gh` + `aws` CLIs installed | Ops | `terraform --version && gh --version && aws --version` |
| Demo signing GPG key generated | Ops | `bash scripts/bootstrap_gpg_demo_key.sh` |
| OpenRouter + Serper API keys procured | Ops | private records |
| Carney office contact + demo time confirmed | Lead | calendar invite |
| Fallback laptop ready | Lead | `docker compose -f docker-compose.v6.yml up -d` on laptop |

## §1 — Deploy day-1 (T-7 before demo)

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: domain_name, route53_zone_name, polaris_repo_commit
# (current polaris HEAD SHA), openrouter/serper keys, polaris_gpg_key_id,
# polaris_gpg_pubkey, static_accounts_yaml (bcrypt hashes), gpg_private_key_armored.

aws s3 mb s3://polaris-carney-tf-state --region ca-central-1
aws s3api put-bucket-versioning \
    --bucket polaris-carney-tf-state \
    --versioning-configuration Status=Enabled

terraform init \
    -backend-config="bucket=polaris-carney-tf-state" \
    -backend-config="region=ca-central-1" \
    -backend-config="key=polaris-carney/terraform.tfstate"

terraform plan -out plan.bin
terraform apply plan.bin
```

Wait ~10 minutes for EC2 + ACM + cloud-init. Verify:

```bash
curl -fsS https://polaris.<your-domain>/health
curl -fsS https://polaris.<your-domain>/transparency | jq
```

### §1b — Install egress lockdown (mandatory before §2 smoke test)

Per Codex iter-1 P1-2: cloud-init does NOT auto-run `egress_lockdown.sh` because the first compose build needs pypi/npmjs/debian access. After the first `docker compose up -d` succeeds inside cloud-init, SSM into the host and install the lockdown:

```bash
INSTANCE_ID=$(cd infra/aws && terraform output -raw ec2_instance_id)
aws ssm start-session --target $INSTANCE_ID --region ca-central-1
# Inside the SSM session:
sudo bash /opt/polaris/scripts/egress_lockdown.sh
sudo iptables -L POLARIS_EGRESS_HOST -n -v | head -20
sudo iptables -L POLARIS_EGRESS_DOCKER -n -v | head -20
```

Both chains must show DROP rules at the bottom + the allowlisted IPs as ACCEPT. Without this step, the deploy claims egress controls but they are NOT enforced — `/transparency`'s `enforcement_layer` field would be inaccurate.

## §2 — Smoke test (T-3 before demo)

Authenticate, submit a clinical question, verify the bundle round-trips:

```bash
TOKEN=$(curl -fsS -X POST https://polaris.<your-domain>/api/v6/auth/login \
    -H 'content-type: application/json' \
    -d '{"username":"carney_office","password":"<reviewer-pw>"}' \
    | jq -r .access_token)

# Submit a run.
RUN_ID=$(curl -fsS -X POST https://polaris.<your-domain>/api/v6/runs \
    -H "Authorization: Bearer $TOKEN" \
    -H 'content-type: application/json' \
    -d '{"template":"clinical","question":"Is tirzepatide effective for type 2 diabetes?"}' \
    | jq -r .run_id)
echo "Run: $RUN_ID"

# Tail the event stream.
curl -N -H "Authorization: Bearer $TOKEN" \
    https://polaris.<your-domain>/api/v6/stream/$RUN_ID

# Fetch the signed bundle.
curl -fsS -H "Authorization: Bearer $TOKEN" \
    -o bundle.tar.gz \
    https://polaris.<your-domain>/api/v6/runs/$RUN_ID/bundle.tar.gz
tar -xzf bundle.tar.gz

# Verify the GPG signature from the operator workstation (NOT from inside
# the deploy — the whole point is independent verification).
cd audit_*/
curl -fsS https://polaris.<your-domain>/transparency/pubkey.asc | gpg --import
gpg --verify manifest.yaml.asc manifest.yaml
```

Expect: `Good signature from "POLARIS Carney Demo <signing@polaris.local>"`.

## §3 — Live-submission rehearsal (T-2 before demo, I-carney-006)

Per `state/polaris_restart/issue_breakdown.md` I-carney-006 acceptance: run 5 canonical clinical/policy questions PLUS 5 staff-style questions that Carney's office is likely to ask. For EACH submitted run, complete the line-by-line §-1.1 audit per CLAUDE.md before the demo:

| # | Question | Domain | Expected gate |
|---|---|---|---|
| 1 | Is tirzepatide effective for type 2 diabetes? | clinical | success or partial_qwen_advisory |
| 2 | What is Canada's federal pharmacare proposal status? | policy | success |
| 3 | How does the NORAD modernization plan affect Arctic sovereignty? | defense → policy fallback | success |
| 4 | What does Canada's AI sovereignty strategy say about model residency? | ai_sovereignty | success |
| 5 | What are the workforce implications of the Canada-US digital services tax? | workforce | success |
| 6-10 | Staff-style softer-phrased variations of the above | mixed | mix of success + abort_corpus_inadequate |

For each: audit the bundle per CLAUDE.md §-1.1 (line-by-line claim against cited span). VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE per claim. Compile into `outputs/audits/carney_demo_rehearsal_<date>/` for the demo binder.

## §4 — Live demo (T=0)

1. Open https://polaris.<your-domain>/ in browser, log in as `carney_office`.
2. Show the home / intake screen.
3. Submit Q1 (tirzepatide) — narrate the scope gate + retrieval + verification phases as SSE events stream.
4. When the run completes, click into the Inspector — show source-tier mix, verified-sentence Inspector pane.
5. Download the bundle — verify the signature on operator laptop (NOT in browser; demo independence).
6. Navigate to `/transparency` — read aloud the sovereignty filter, evaluator models, egress allowlist. Hand Carney's office the URL.
7. Submit Q2 (pharmacare) — observe sovereignty cascade in real time.
8. Take questions.

## §5 — Fallback laptop

If the AWS deploy is unreachable (DNS, ALB down, etc.) during the demo:

**One-time setup (T-3 before demo):** populate the laptop's `.env` + `/etc/polaris/static_accounts.yaml` from AWS Secrets Manager AND SSM Parameter Store so the laptop matches the production substrate. Codex iter-2 P1 fix: use the right service per secret; pipe to `sudo tee` for the static_accounts file.

```bash
cd /local/polaris

# 1. Define helpers for SSM Parameter Store vs Secrets Manager.
ssm_get() {
    aws ssm get-parameter --name "$1" --with-decryption \
        --query Parameter.Value --output text --region ca-central-1
}
sm_get() {
    aws secretsmanager get-secret-value --secret-id "$1" \
        --query SecretString --output text --region ca-central-1
}

# 2. Write .env at repo root (compose reads this).
# SSM Parameter Store: API keys + GPG key fingerprint (per infra/aws/ssm_parameters.tf).
# Secrets Manager:    JWT secret + static accounts + GPG private key (per infra/aws/secretsmanager.tf).
cat > .env <<EOF
OPENROUTER_API_KEY=$(ssm_get /polaris/v6/openrouter_api_key)
SERPER_API_KEY=$(ssm_get /polaris/v6/serper_api_key)
POLARIS_GPG_KEY_ID=$(ssm_get /polaris/v6/polaris_gpg_key_id)
POLARIS_JWT_SECRET=$(sm_get polaris/v6/jwt_secret)
POLARIS_GPG_HOMEDIR=$HOME/.gnupg-polaris
POLARIS_STATIC_ACCOUNTS_PATH=/etc/polaris/static_accounts.yaml
POLARIS_ETC_DIR=/etc/polaris
POLARIS_API_PORT=8000
POLARIS_WEB_PORT=3000
PG_MAX_COST_PER_RUN=5.00
EOF
chmod 600 .env

# 3. Write static_accounts.yaml to /etc/polaris (mirroring EC2 host path).
# Pipe through sudo tee — running `sudo bash -c "sm_get ..."` would not see
# the function definition since sudo starts a fresh shell.
sudo mkdir -p /etc/polaris
sudo chmod 750 /etc/polaris
sm_get polaris/v6/static_accounts_yaml | sudo tee /etc/polaris/static_accounts.yaml > /dev/null
sudo chmod 640 /etc/polaris/static_accounts.yaml

# 4. Import the GPG private key into the local keyring.
mkdir -p ~/.gnupg-polaris && chmod 700 ~/.gnupg-polaris
sm_get polaris/v6/gpg_private_key_armored | gpg --homedir ~/.gnupg-polaris --batch --import

# 5. Bring up the stack.
docker compose -f docker-compose.v6.yml down
docker compose -f docker-compose.v6.yml up -d --build

# 6. Smoke test.
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/transparency | jq
```

Localhost demo at http://localhost:3000. Auth + signing + sovereignty filter all behave identically to the AWS deploy since the laptop loads the SAME secrets. `/transparency` will show `region: "unknown"` (no AWS_REGION env) — disclose this if a reviewer asks why.

## §6 — 30-minute internal rehearsal (T-1 before demo)

Schedule a 30-min Zoom with at least one non-engineer:
- They follow the demo script as the "Carney's office" surrogate.
- Time each step. Target: full demo < 20 min (10 min buffer for questions).
- Verify the bundle GPG verify on their workstation (not yours).
- Verify the /transparency page is readable.
- Pad any unclear narration.

## §7 — Codex sign-off (T-1 before demo)

Per Codex iter-1 P1-1: the sign-off must NOT pipe the static brief alone (that lets Codex see placeholders, not real evidence). Instead, copy the brief to a working file, RUN each curl/GPG/iptables command, and PASTE the actual outputs into the working file BEFORE shipping to Codex.

```bash
# Copy brief to evidence file.
cp .codex/I-carney-007/carney_demo_signoff_brief.md \
   /tmp/carney_demo_signoff_evidence.md

# Run each §3 command and append its output. Example for §3a:
echo "" >> /tmp/carney_demo_signoff_evidence.md
echo "## §3a evidence (live transparency response):" >> /tmp/carney_demo_signoff_evidence.md
echo '```' >> /tmp/carney_demo_signoff_evidence.md
curl -fsS https://polaris.<your-domain>/transparency \
    >> /tmp/carney_demo_signoff_evidence.md
echo '```' >> /tmp/carney_demo_signoff_evidence.md

# Repeat for §3b /health, §3c bundle Q1 GPG verify, §3d bundle Q2 GPG verify,
# §4 egress chain output. Then submit to Codex:
env -u OPENAI_API_KEY codex exec --skip-git-repo-check - < /tmp/carney_demo_signoff_evidence.md
```

If the evidence file still contains `<your-domain>` or other placeholders, ABORT — Codex would otherwise sign off on the example template instead of the real deploy. Expected verdict: `verdict: APPROVE ship_decision: SHIP convergence_call: accept_remaining`. Anything REQUEST_CHANGES or `ship_decision: HALT` → escalate to I-carney-006 (live rehearsal) for the failing question.

## §8 — Post-demo tear-down

```bash
# Recover audit bundles BEFORE destroy.
aws s3 sync s3://polaris-carney-audit-<acct-id>/ ./carney_demo_bundles/

# Tear down the AWS stack.
cd infra/aws
terraform destroy
```

## §9 — Known limitations (disclose during demo if asked)

- Single-AZ EC2 (no HA pair) — for demo window only
- Manual GPG private key rotation (Secrets Manager rotation_lambda is Phase-2)
- Pipeline-A only (pipeline-B legacy + pipeline-C frozen per architecture.md §5)
- 18-domain egress allowlist enforced via iptables (not VPC NACLs — also defense-in-depth Phase-2)
- /docs + /redoc + /openapi.json public for operator ergonomics — gate to admin in Phase-2
