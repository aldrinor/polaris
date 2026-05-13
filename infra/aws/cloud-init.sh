#!/bin/bash
# I-carney-002 — EC2 user-data executed on first boot.
#
# Brings the docker compose v6 stack online on a fresh Ubuntu 24.04 host.
# Idempotent on reboot (`docker compose up -d` is idempotent; SSM fetches
# overwrite .env each boot).

# Codex iter-1 P1-3: do NOT enable xtrace globally because it would print
# POLARIS_JWT_SECRET, POLARIS_STATIC_ACCOUNTS_YAML, and POLARIS_GPG_PRIVKEY
# verbatim to cloud-init logs / journald. Errors-only + pipefail.
set -eo pipefail

AWS_REGION="${aws_region}"
POLARIS_REPO_URL="${polaris_repo_url}"
POLARIS_REPO_BRANCH="${polaris_repo_branch}"
POLARIS_REPO_COMMIT="${polaris_repo_commit}"
AUDIT_BUCKET_NAME="${audit_bucket_name}"

# ----- 1. apt + docker compose v2 + git + awscli -----
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    docker.io \
    docker-compose-v2 \
    git \
    awscli \
    gnupg \
    curl \
    jq

systemctl enable --now docker

# ----- 2. mount /var/lib/polaris on the attached data EBS -----
# Codex diff iter-1 P2 + iter-2 P2: never unconditionally `mkfs -F`; tolerate
# slow EBS attachment by polling for the device for up to 120s. Resolve by
# device-name across instance generations (nvme* on Nitro, xvd* on Xen).
DATA_DEV=""
for attempt in $(seq 1 60); do
    for candidate in /dev/nvme1n1 /dev/xvdf /dev/sdf; do
        if [ -b "$candidate" ]; then
            DATA_DEV="$candidate"
            break 2
        fi
    done
    echo "[cloud-init] waiting for data EBS to attach (attempt $attempt/60)"
    sleep 2
done
if [ -z "$DATA_DEV" ]; then
    echo "[cloud-init] ERROR: data EBS device not attached after 120s — failing loud per LAW II" >&2
    exit 1
fi
echo "[cloud-init] data EBS detected at $DATA_DEV"

# Only mkfs if the device has NO existing filesystem (idempotent on replacement).
if ! blkid "$DATA_DEV" >/dev/null 2>&1; then
    echo "[cloud-init] new data volume — formatting $DATA_DEV with ext4"
    mkfs.ext4 -L polaris-data "$DATA_DEV"
else
    echo "[cloud-init] existing filesystem on $DATA_DEV — skipping mkfs"
fi

mkdir -p /var/lib/polaris
mount LABEL=polaris-data /var/lib/polaris || mount "$DATA_DEV" /var/lib/polaris
grep -q "polaris-data" /etc/fstab || \
    echo "LABEL=polaris-data /var/lib/polaris ext4 defaults,nofail,noatime 0 2" >> /etc/fstab

mkdir -p /var/lib/polaris/{outputs,logs,data,state,gpg}
chmod 700 /var/lib/polaris/gpg

# ----- 3. clone POLARIS at pinned commit -----
mkdir -p /opt
if [ ! -d /opt/polaris/.git ]; then
    git clone "$POLARIS_REPO_URL" /opt/polaris
fi
cd /opt/polaris
git fetch origin "$POLARIS_REPO_BRANCH"
git checkout "$POLARIS_REPO_COMMIT"

# ----- 4. fetch SSM secrets → /opt/polaris/.env -----
ssm_get() {
    aws ssm get-parameter \
        --name "$1" \
        --with-decryption \
        --region "$AWS_REGION" \
        --query Parameter.Value \
        --output text 2>/dev/null
}

OPENROUTER_API_KEY=$(ssm_get /polaris/v6/openrouter_api_key)
SERPER_API_KEY=$(ssm_get /polaris/v6/serper_api_key)
SEMANTIC_SCHOLAR_API_KEY=$(ssm_get /polaris/v6/semantic_scholar_api_key || true)
POLARIS_GPG_KEY_ID=$(ssm_get /polaris/v6/polaris_gpg_key_id)
POLARIS_GPG_PUBKEY=$(ssm_get /polaris/v6/polaris_gpg_pubkey || true)

# ----- 4b. I-carney-004: fetch Secrets Manager substrate -----
sm_get() {
    aws secretsmanager get-secret-value \
        --secret-id "$1" \
        --region "$AWS_REGION" \
        --query SecretString \
        --output text 2>/dev/null
}

POLARIS_JWT_SECRET=$(sm_get polaris/v6/jwt_secret)
POLARIS_STATIC_ACCOUNTS_YAML=$(sm_get polaris/v6/static_accounts_yaml)
POLARIS_GPG_PRIVKEY=$(sm_get polaris/v6/gpg_private_key_armored)

# Write static_accounts.yaml to /etc/polaris/ (host) AND make it available
# to the api container via bind-mount. The container path /app/config/
# is baked in by Dockerfile.v6 `COPY config/`; for the runtime override
# we set POLARIS_STATIC_ACCOUNTS_PATH=/etc/polaris/static_accounts.yaml
# in the api+worker env_file so the container reads the host-managed YAML.
mkdir -p /etc/polaris
chmod 750 /etc/polaris
echo "$POLARIS_STATIC_ACCOUNTS_YAML" > /etc/polaris/static_accounts.yaml
chmod 640 /etc/polaris/static_accounts.yaml

cat > /opt/polaris/.env <<EOF
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
SERPER_API_KEY=$SERPER_API_KEY
SEMANTIC_SCHOLAR_API_KEY=$SEMANTIC_SCHOLAR_API_KEY
POLARIS_GPG_KEY_ID=$POLARIS_GPG_KEY_ID
POLARIS_GPG_HOMEDIR=/var/lib/polaris/gpg
POLARIS_API_PORT=8000
POLARIS_WEB_PORT=3000
PG_MAX_COST_PER_RUN=5.00
POLARIS_AUDIT_S3_BUCKET=$AUDIT_BUCKET_NAME
POLARIS_GIT_COMMIT=$POLARIS_REPO_COMMIT
AWS_REGION=$AWS_REGION
POLARIS_JWT_SECRET=$POLARIS_JWT_SECRET
POLARIS_STATIC_ACCOUNTS_PATH=/etc/polaris/static_accounts.yaml
EOF
chmod 600 /opt/polaris/.env

# ----- 5. import the published GPG public key into the demo keyring -----
# I-carney-002 P1-pending: only the public key is published via SSM; the
# private key MUST be generated/imported by operator out-of-band (the
# bootstrap script runs on the operator workstation per the I-carney-005
# runbook, then the operator copies the private key into the EC2 keyring
# via SSM Session Manager). Cloud-init only imports the public half so
# `bundle.tar.gz` requests will return 503 gpg_unavailable until the
# operator finishes the private-key transfer.
#
# I-carney-003 P1-002: ALSO persist the armored ASCII to disk so the
# /transparency/pubkey.asc endpoint can serve it without shelling to gpg.
if [ -n "$POLARIS_GPG_PUBKEY" ]; then
    export GNUPGHOME=/var/lib/polaris/gpg
    echo "$POLARIS_GPG_PUBKEY" | gpg --import || true
    echo "$POLARIS_GPG_PUBKEY" > /var/lib/polaris/gpg/polaris_demo_pubkey.asc
    chmod 644 /var/lib/polaris/gpg/polaris_demo_pubkey.asc
fi

# I-carney-004: import GPG PRIVATE key from Secrets Manager (replaces the
# manual operator-side SSM Session Manager transfer step from I-carney-002).
# Private key remains in the dedicated /var/lib/polaris/gpg keyring (mode 700).
if [ -n "$POLARIS_GPG_PRIVKEY" ]; then
    export GNUPGHOME=/var/lib/polaris/gpg
    # Codex iter-1 P2: fail loud on import error (private key is the entire
    # reason for the bundle-signing substrate; silent failure would let the
    # deploy come up serving 503s on every /runs/{id}/bundle.tar.gz).
    echo "$POLARIS_GPG_PRIVKEY" | gpg --batch --import
    # Wipe the env var so it doesn't leak into journald via systemd unit logs.
    unset POLARIS_GPG_PRIVKEY
fi

# ----- 5b. Install egress allowlist + lockdown (I-carney-003) -----
mkdir -p /etc/polaris
cp /opt/polaris/config/egress_allowlist.txt /etc/polaris/egress_allowlist.txt
chmod 644 /etc/polaris/egress_allowlist.txt
# Note: egress_lockdown.sh is NOT auto-run on boot. Operator runs it AFTER
# `docker compose up -d` succeeds the first time so build-time hosts can
# be tightened. See docs/transparency.md §4.

# ----- 6. bring up the compose stack -----
cd /opt/polaris
docker compose -f docker-compose.v6.yml up -d --build

# ----- 7. self-test -----
sleep 30
for i in $(seq 1 20); do
    if curl -fsS http://localhost:8000/health > /dev/null; then
        echo "[cloud-init] api healthy at boot+$((i*5))s"
        break
    fi
    sleep 5
done
