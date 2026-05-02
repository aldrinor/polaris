# POLARIS Self-Hosted Canadian Runner — Provisioning Guide

**Plan v13 §G #10** runner setup. All steps once, on a fresh Canadian VM.

## Hardware / hosting

Recommended: OVH Canada Beauharnois VLE-32 or larger (8 vCPU + 32GB RAM minimum). Azure Canada Central also acceptable. Must be in Canadian jurisdiction (sovereignty per Plan v13 §F).

Estimated cost: ~$50-100/mo.

## OS

Ubuntu 24.04 LTS recommended (best Docker support + AppArmor profile compatibility).

## Required packages

```bash
sudo apt update
sudo apt install -y \
    docker.io docker-compose-v2 \
    git gh \
    apparmor-utils \
    iptables \
    curl jq python3-pip
```

## Step 1 — Install GitHub Actions runner

Per https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners

```bash
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.323.0.tar.gz -L \
    https://github.com/actions/runner/releases/download/v2.323.0/actions-runner-linux-x64-2.323.0.tar.gz
tar xzf actions-runner-linux-x64-2.323.0.tar.gz

# Configure with token from https://github.com/aldrinor/polaris/settings/actions/runners/new
./config.sh --url https://github.com/aldrinor/polaris --token <YOUR_RUNNER_TOKEN> \
    --labels self-hosted,polaris-ca-bhs --unattended

# Install as service
sudo ./svc.sh install
sudo ./svc.sh start
```

## Step 2 — Install Codex CLI + login

```bash
npm install -g @openai/codex-cli
codex --version  # verify
codex login       # opens browser, completes OAuth flow
ls -la ~/.codex/auth.json  # verify token landed
```

## Step 3 — Install Claude Code (for Agent SDK to work in CI)

```bash
npm install -g @anthropic-ai/claude-code
claude login     # OAuth with subscription account
```

## Step 4 — Place Caddy config

```bash
sudo mkdir -p /etc/polaris/proxy
sudo cp scripts/autoloop/runner/Caddyfile /etc/polaris/Caddyfile
sudo chmod 644 /etc/polaris/Caddyfile
```

## Step 5 — Place egress-firewall script

```bash
sudo cp scripts/autoloop/runner/polaris_egress_firewall.sh /usr/local/bin/polaris_egress_firewall.sh
sudo chmod +x /usr/local/bin/polaris_egress_firewall.sh
```

## Step 6 — Configure Docker for userns-remap (REQUIRED for firewall script compat)

**Use userns-remap on root Docker.** Rootless Docker is theoretically more secure
but is INCOMPATIBLE with `polaris_egress_firewall.sh` (needs host-visible Docker
bridge + `sudo iptables` against it). Codex round-3 P1 fix: README previously
offered rootless as primary; corrected to userns-remap as REQUIRED.

```bash
sudo bash -c 'cat > /etc/docker/daemon.json <<EOF
{
  "userns-remap": "default",
  "live-restore": true,
  "iptables": true
}
EOF'
sudo systemctl restart docker

# Verify userns-remap active
docker info | grep "userns"   # should show: userns
```

## Step 7 — AppArmor profile for Codex container

```bash
sudo cp scripts/autoloop/runner/apparmor-polaris-codex-runner /etc/apparmor.d/polaris-codex-runner
sudo apparmor_parser -r /etc/apparmor.d/polaris-codex-runner
sudo aa-status | grep polaris-codex-runner  # verify loaded
```

(AppArmor profile authored separately; see `apparmor-polaris-codex-runner` once added.)

## Step 8 — seccomp profile for Codex container

```bash
sudo cp scripts/autoloop/runner/seccomp.json /etc/polaris/seccomp.json
sudo chmod 644 /etc/polaris/seccomp.json
```

(seccomp profile authored separately; will land alongside AppArmor.)

## Step 9 — Build polaris-codex-runner Docker image

```bash
cd /tmp
git clone https://github.com/aldrinor/polaris.git
cd polaris
sudo docker build -t polaris-codex-runner:latest -f scripts/autoloop/runner/Dockerfile.codex-runner .
# Tag with pinned SHA per workflow reference
sudo docker tag polaris-codex-runner:latest polaris-codex-runner:pinned-sha
```

(Dockerfile authored separately.)

## Step 10 — Verify smoke run

```bash
# From the runner, simulate the workflow's Phase B locally:
mkdir -p /tmp/codex_input /tmp/codex_output
echo '# Smoke test brief' > /tmp/codex_input/trusted_brief.md

docker network create --internal polaris-internal
docker network create polaris-egress
sudo /usr/local/bin/polaris_egress_firewall.sh polaris-egress api.openai.com 443

docker run -d --name polaris-codex-proxy \
    --network polaris-internal --user 1000:1000 \
    --cap-drop ALL --read-only --tmpfs /tmp \
    --security-opt no-new-privileges \
    --volume /etc/polaris/Caddyfile:/etc/caddy/Caddyfile:ro \
    caddy:2-alpine
docker network connect polaris-egress polaris-codex-proxy

# Wait for Caddy ready
for i in {1..15}; do
    docker exec polaris-codex-proxy wget -q -O - http://localhost:8443/health && break
    sleep 1
done

# Cleanup
docker stop polaris-codex-proxy
docker rm polaris-codex-proxy
docker network rm polaris-internal polaris-egress
```

## Step 11 — Configure GitHub branch protection (one-time, via gh CLI)

After GitHub auth refresh (decision #6) lands:

```bash
# Branch protection on polaris (per-PR gate)
gh api -X PUT /repos/aldrinor/polaris/branches/polaris/protection \
    -F required_status_checks[strict]=true \
    -F 'required_status_checks[contexts][]=codex-verdict-check / verdict-validate' \
    -F enforce_admins=true \
    -F required_pull_request_reviews=null \
    -F restrictions=null

# Branch protection on main (stricter — for end-of-phase PRs)
gh api -X PUT /repos/aldrinor/polaris/branches/main/protection \
    -F required_status_checks[strict]=true \
    -F 'required_status_checks[contexts][]=codex-verdict-check / verdict-validate' \
    -F enforce_admins=true \
    -F 'required_pull_request_reviews[required_approving_review_count]=1' \
    -F restrictions=null

# GitHub Environment for codex_runtime (if using API-key path; not needed for OAuth)
# Skip if using OAuth from runner's ~/.codex/auth.json
```

## Step 12 — Smoke an end-to-end PR

Open a no-op PR against `polaris`. Verify CI Phase A/B/C all run on the self-hosted runner. Verify status check passes. Verify merge queue accepts the PR.

## Verification

After all 12 steps:
- [ ] Runner shows online at https://github.com/aldrinor/polaris/settings/actions/runners
- [ ] Codex CLI authenticated (`codex --version` works without prompting)
- [ ] Claude Code authenticated (`claude --version` works)
- [ ] Caddy + firewall script in place
- [ ] AppArmor + seccomp profiles loaded
- [ ] Docker image `polaris-codex-runner:pinned-sha` available
- [ ] Branch protection enabled on polaris + main
- [ ] No-op smoke PR merges via CI

After verification: orchestrator can be started locally on developer machine; first real task (post-bootstrap) lands as `task/<id>/iter_1` branch → PR to polaris → CI runs on this runner.
