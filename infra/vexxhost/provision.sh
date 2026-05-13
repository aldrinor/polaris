#!/bin/bash
# I-carney-008 — POLARIS Carney demo bootstrap on a fresh Vexxhost Ubuntu 24.04 VM.
#
# Run as root on a freshly-provisioned Vexxhost VM in the Montréal region.
# Replaces the AWS Terraform module + cloud-init + Secrets Manager flow with
# a single bash script for the sovereign Canadian deploy.
#
# Prereqs (operator does these BEFORE running this script):
#   1. Vexxhost VM provisioned (Ubuntu 24.04, 8 vCPU / 32 GB / 100 GB SSD, Montréal)
#   2. DNS A record pointing polaris.<domain> at the VM's public IP
#   3. SSH key access as root or sudo user
#   4. /root/.env populated with all secrets (see infra/vexxhost/.env.example)
#   5. /root/polaris_demo_pubkey.asc + /root/polaris_demo_secret.asc (GPG keys)
#
# Usage:
#   scp infra/vexxhost/.env.example root@polaris.<domain>:/root/.env  (edit first)
#   ssh root@polaris.<domain>
#   curl -fsSL https://raw.githubusercontent.com/aldrinor/polaris/polaris/infra/vexxhost/provision.sh | bash
#
# OR copy this script up and run it directly.

set -eo pipefail

# Config (override via env before running).
POLARIS_REPO_URL="${POLARIS_REPO_URL:-https://github.com/aldrinor/polaris.git}"
POLARIS_REPO_BRANCH="${POLARIS_REPO_BRANCH:-polaris}"
POLARIS_REPO_COMMIT="${POLARIS_REPO_COMMIT:-}"   # required; no default — must pin
POLARIS_DOMAIN="${POLARIS_DOMAIN:-}"             # e.g. polaris.example.ca
POLARIS_ACME_EMAIL="${POLARIS_ACME_EMAIL:-}"     # Let's Encrypt contact

if [ "$(id -u)" -ne 0 ]; then
    echo "[provision] ERROR: must run as root" >&2
    exit 1
fi
if [ -z "$POLARIS_REPO_COMMIT" ]; then
    echo "[provision] ERROR: POLARIS_REPO_COMMIT must be pinned (no floating HEAD)" >&2
    exit 1
fi
if [ -z "$POLARIS_DOMAIN" ]; then
    echo "[provision] ERROR: POLARIS_DOMAIN must be set" >&2
    exit 1
fi
if [ ! -f /root/.env ]; then
    echo "[provision] ERROR: /root/.env not found. Populate from infra/vexxhost/.env.example" >&2
    exit 1
fi
if [ ! -f /root/polaris_demo_pubkey.asc ] || [ ! -f /root/polaris_demo_secret.asc ]; then
    echo "[provision] ERROR: GPG keys not staged at /root/polaris_demo_{pubkey,secret}.asc" >&2
    exit 1
fi

echo "=== POLARIS Vexxhost provisioning ==="
echo "Domain: $POLARIS_DOMAIN"
echo "Repo:   $POLARIS_REPO_URL @ $POLARIS_REPO_COMMIT"
echo "===================================="

# ----- 1. apt + docker + caddy + git + gnupg -----
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    docker.io \
    docker-compose-v2 \
    git \
    gnupg \
    curl \
    jq \
    debian-keyring \
    debian-archive-keyring \
    apt-transport-https \
    ca-certificates

# Caddy from official Cloudsmith repo (Czech/EU-mirrored, not US — and even
# if Cloudsmith CDN edges via US, the package itself is fetched once at
# install and we don't depend on Caddy phoning home at runtime).
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy

systemctl enable --now docker

# ----- 2. clone POLARIS at pinned commit -----
mkdir -p /opt
if [ ! -d /opt/polaris/.git ]; then
    git clone "$POLARIS_REPO_URL" /opt/polaris
fi
cd /opt/polaris
git fetch origin "$POLARIS_REPO_BRANCH"
git checkout "$POLARIS_REPO_COMMIT"

# ----- 3. wire .env -----
cp /root/.env /opt/polaris/.env
chmod 600 /opt/polaris/.env

# Codex iter-2 P2-1: .env template defaults POLARIS_GIT_COMMIT=REPLACE_ME_REPO_SHA.
# Overwrite from the resolved pin so /transparency surfaces the real commit
# rather than the placeholder.
sed -i "s|^POLARIS_GIT_COMMIT=.*|POLARIS_GIT_COMMIT=${POLARIS_REPO_COMMIT}|" /opt/polaris/.env
if ! grep -q "^POLARIS_GIT_COMMIT=" /opt/polaris/.env; then
    echo "POLARIS_GIT_COMMIT=${POLARIS_REPO_COMMIT}" >> /opt/polaris/.env
fi

# ----- 4. /etc/polaris substrate (auth + egress allowlist) -----
mkdir -p /etc/polaris
chmod 750 /etc/polaris

# static_accounts.yaml expected in /root/static_accounts.yaml (operator-prepared).
if [ -f /root/static_accounts.yaml ]; then
    cp /root/static_accounts.yaml /etc/polaris/static_accounts.yaml
    chmod 640 /etc/polaris/static_accounts.yaml
else
    echo "[provision] WARN: /root/static_accounts.yaml not found; auth will fail until provided" >&2
fi

# Egress allowlist baked from the repo.
cp /opt/polaris/config/egress_allowlist.txt /etc/polaris/egress_allowlist.txt
chmod 644 /etc/polaris/egress_allowlist.txt

# ----- 5. GPG keyring -----
export GNUPGHOME=/var/lib/polaris/gpg
mkdir -p "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
cp /root/polaris_demo_pubkey.asc "$GNUPGHOME/polaris_demo_pubkey.asc"
chmod 644 "$GNUPGHOME/polaris_demo_pubkey.asc"
gpg --batch --import /root/polaris_demo_pubkey.asc
gpg --batch --import /root/polaris_demo_secret.asc
# Wipe the secret key file from /root — it now lives only in the GPG keyring.
shred -u /root/polaris_demo_secret.asc

# Ensure POLARIS_GPG_HOMEDIR in .env points at /var/lib/polaris/gpg.
if ! grep -q "POLARIS_GPG_HOMEDIR=/var/lib/polaris/gpg" /opt/polaris/.env; then
    echo "POLARIS_GPG_HOMEDIR=/var/lib/polaris/gpg" >> /opt/polaris/.env
fi

# ----- 6. bring up the compose stack -----
cd /opt/polaris
docker compose -f docker-compose.v6.yml up -d --build

# ----- 7. wait for api + webui healthchecks -----
# Codex iter-1 P2-4: if the wait loop exhausts without success, FAIL the
# script rather than silently emitting "deployed" on an unhealthy stack.
echo "[provision] waiting for api + webui healthchecks..."
healthy=0
for i in $(seq 1 60); do
    if curl -fsS http://localhost:8000/health > /dev/null && \
       curl -fsS http://localhost:3000/ > /dev/null; then
        echo "[provision] api + webui healthy at boot+$((i*5))s"
        healthy=1
        break
    fi
    sleep 5
done
if [ "$healthy" -ne 1 ]; then
    echo "[provision] ERROR: api + webui did not become healthy within 300s." >&2
    echo "[provision] Compose logs (last 50 lines):" >&2
    docker compose -f docker-compose.v6.yml logs --tail=50 >&2 || true
    exit 1
fi

# ----- 8. Caddy reverse proxy + Let's Encrypt -----
cat > /etc/caddy/Caddyfile <<EOF
${POLARIS_DOMAIN} {
    tls ${POLARIS_ACME_EMAIL}

    # /health + /transparency + /auth + /api + /stream + everything else → webui:3000
    # webui's Next.js rewrites handle /api/v6/* and /transparency/* server-side.
    reverse_proxy localhost:3000 {
        # SSE keepalive: don't buffer.
        flush_interval -1
    }

    # /health probe goes direct to backend for cleaner ops signal.
    handle /health {
        reverse_proxy localhost:8000
    }

    log {
        output file /var/log/caddy/polaris.log
        format json
    }
}
EOF
mkdir -p /var/log/caddy
caddy fmt --overwrite /etc/caddy/Caddyfile
systemctl reload caddy

echo ""
echo "=================================================================="
echo "POLARIS deployed on Vexxhost. Public URL:"
echo "  https://${POLARIS_DOMAIN}/"
echo ""
echo "Verify:"
echo "  curl https://${POLARIS_DOMAIN}/health"
echo "  curl https://${POLARIS_DOMAIN}/transparency | jq"
echo ""
echo "Egress lockdown is NOT yet enabled. Run BOTH after first compose build:"
echo "  sudo bash /opt/polaris/scripts/egress_lockdown.sh"
echo "  sudo bash /opt/polaris/scripts/egress_runtime_tighten.sh"
echo ""
echo "Verify all 4 chains (iptables x ip6tables x OUTPUT x DOCKER-USER):"
echo "  sudo iptables  -L POLARIS_EGRESS_HOST     -n -v | head -20"
echo "  sudo iptables  -L POLARIS_EGRESS_DOCKER   -n -v | head -20"
echo "  sudo ip6tables -L POLARIS_EGRESS_HOST_V6  -n -v | head -20"
echo "  sudo ip6tables -L POLARIS_EGRESS_DOCKER_V6 -n -v | head -20"
echo ""
echo "Confirm /transparency build_time_hosts_pruned is true after tighten:"
echo "  curl -fsS https://${POLARIS_DOMAIN}/transparency | jq .build_time_hosts_pruned"
echo "=================================================================="
