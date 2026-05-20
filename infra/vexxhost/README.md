# infra/vexxhost — sovereign Canadian deploy

The active Carney demo deploy path. Replaces `infra/aws.archived/` (US-owned, fails sovereignty audit).

**Hosting:** Vexxhost (Canadian-owned, Montréal datacenter).
**LLM inference:** OVH BHS H200 (French-owned, Beauharnois QC) running self-hosted DeepSeek V4 Pro + Gemma 4 31B via vLLM. See `docs/ovh_h200_procurement_spec.md`.
**Search:** Serper (`google.serper.dev`), US-based — a disclosed exception per operator directive 2026-05-13. Search queries carry no confidential content; the sovereign constraint protects the LLM inference path + report data. See `docs/transparency.md` §4.
**Sovereignty posture:** the LLM inference path and the generated report data run on Canadian / non-US infrastructure (Vexxhost orchestrator + OVH H200 inference). Serper web search is the one disclosed US exception in the runtime path — see §4 of `docs/transparency.md` for the rationale and what Serper does/does not see.

## Prereqs (operator, T-7 before demo)

1. Vexxhost account + project in Montréal region. Free tier available; demo workload fits in v3-32 (8 vCPU / 32 GB / 100 GB SSD).
2. Provision a single Ubuntu 24.04 LTS VM via Vexxhost web console:
   - Flavor: `v3-32` or larger
   - Image: Ubuntu 24.04 LTS
   - Network: floating public IPv4 + IPv6
   - SSH key uploaded
3. Domain registered + DNS A record for `polaris.<your-domain>` pointing at the VM's floating IPv4. Use a Canadian registrar (easyDNS, Cira, Hover-Canada-billing) for the sovereignty story.
4. GPG demo signing key generated on operator workstation: `bash scripts/bootstrap_gpg_demo_key.sh`. Produces `outputs/polaris_demo_pubkey.asc` and a fingerprint in `state/polaris_gpg_keyid.txt`. ALSO export the secret: `gpg --homedir ~/.gnupg-polaris --armor --export-secret-key "POLARIS Carney Demo" > polaris_demo_secret.asc`.
5. Serper API key from https://serper.dev/ — the web search backend. US-based, disclosed exception per operator directive 2026-05-13 (search queries non-confidential; reports stay sovereign). REQUIRED.
6. OVH H200 server provisioned in BHS — see `docs/ovh_h200_procurement_spec.md`. Note its private IP; default vLLM endpoint is `http://10.0.0.42:8000/v1`.
7. bcrypt-hashed `static_accounts.yaml` prepared locally **outside the repo** (e.g., `/tmp/polaris_secrets/static_accounts.yaml`); template structure at `config/static_accounts.example.yaml`. I-cd-014 (GH#610): the real file MUST NEVER be staged inside `config/` — it is gitignored AND dockerignored to prevent accidental check-in or Docker-image inclusion.

## Deploy (single command)

```bash
# 1. Stage files on the VM.
scp infra/vexxhost/.env.example root@polaris.<domain>:/root/.env  # edit first
scp outputs/polaris_demo_pubkey.asc root@polaris.<domain>:/root/
scp ~/polaris_demo_secret.asc       root@polaris.<domain>:/root/
# I-cd-014: NEVER scp from inside the repo. Operator-local source path is
# /tmp/polaris_secrets/static_accounts.yaml (outside repo); destination is
# /root/static_accounts.yaml on the VM — `infra/vexxhost/provision.sh:102-107`
# then copies it to /etc/polaris/static_accounts.yaml.
scp /tmp/polaris_secrets/static_accounts.yaml root@polaris.<domain>:/root/static_accounts.yaml
scp infra/vexxhost/provision.sh     root@polaris.<domain>:/root/

# 2. Run provisioning.
ssh root@polaris.<domain> "
    export POLARIS_REPO_COMMIT=<git rev-parse polaris on your workstation>
    export POLARIS_DOMAIN=polaris.<your-domain>
    export POLARIS_ACME_EMAIL=ops@<your-domain>
    bash /root/provision.sh
"
```

Provisioning takes ~10 minutes (apt + docker pull + Next.js build + Caddy ACME).

## Smoke test

```bash
curl -fsS https://polaris.<your-domain>/health
curl -fsS https://polaris.<your-domain>/transparency | jq

TOKEN=$(curl -fsS -X POST https://polaris.<your-domain>/api/v6/auth/login \
    -H 'content-type: application/json' \
    -d '{"username":"carney_office","password":"<password>"}' \
    | jq -r .access_token)

curl -fsS -X POST https://polaris.<your-domain>/api/v6/runs \
    -H "Authorization: Bearer $TOKEN" \
    -H 'content-type: application/json' \
    -d '{"template":"clinical","question":"Is tirzepatide effective for type 2 diabetes?"}'
```

## Egress lockdown + runtime tighten (T-6 before demo)

After the first successful deploy + Caddy ACME provisioning succeeds:

```bash
ssh root@polaris.<domain>

# 1. IPv4 + IPv6 lockdown with full allowlist.
sudo bash /opt/polaris/scripts/egress_lockdown.sh

# 2. Strip build-time hosts (github/docker/cloudflare/pypi/npm/debian) from
#    the RUNTIME allowlist, set the runtime_pruned.flag, re-apply lockdown.
sudo bash /opt/polaris/scripts/egress_runtime_tighten.sh

# 3. Verify all 4 chains.
sudo iptables   -L POLARIS_EGRESS_HOST    -n -v | head -20
sudo iptables   -L POLARIS_EGRESS_DOCKER  -n -v | head -20
sudo ip6tables  -L POLARIS_EGRESS_HOST_V6 -n -v | head -20
sudo ip6tables  -L POLARIS_EGRESS_DOCKER_V6 -n -v | head -20
```

All four chains must show DROP rules at the bottom + the allowlisted IPs as ACCEPT. `curl https://polaris.<domain>/transparency | jq .build_time_hosts_pruned` should return `true` after `egress_runtime_tighten.sh`.

## Architecture

```
                                Internet
                                    │
                                    │ HTTPS:443
                                    ▼
                          ┌──────────────────────┐
                          │  Vexxhost Montréal   │
                          │  Ubuntu 24.04 VM     │
                          │                      │
                          │   Caddy (TLS + LE)   │
                          │        │             │
                          │        ▼             │
                          │   webui:3000 (Next)  │
                          │        │             │
                          │  /api/v6/* rewrite   │
                          │        ▼             │
                          │   api:8000 (FastAPI) │──────┐
                          │   worker (Dramatiq)  │      │
                          │   redis:6379         │      │
                          │                      │      │ private network
                          └──────────────────────┘      │ (VPN or peered)
                                                        │
                                                        ▼
                              ┌──────────────────────────┐
                              │   OVH BHS H200 GPU       │
                              │   vLLM serving DeepSeek  │
                              │   V4 Pro + Gemma 4 31B   │
                              └──────────────────────────┘
                                          │
                                          ▼
                                 Serper web search (US, disclosed)
                                 + government T1 sources
                                 (FDA, NICE, EMA, MHRA,
                                  Health Canada, WHO, NCBI)
```

## Why not Terraform

The Vexxhost OpenStack Terraform provider exists, but for a single VM the operator-time overhead of writing + reviewing the HCL exceeds the time saved over a web-console click + ssh + bash. If you scale to >3 VMs later, port `provision.sh` into a Terraform module then.

## Sovereignty audit checklist (for transparency.md reviewers)

| Layer | Provider | Ownership | Jurisdiction |
|---|---|---|---|
| Orchestrator hosting | Vexxhost | Canadian | Canada (PIPEDA + Quebec Law 25) |
| LLM inference (when OVH H200 online + GH#199 ships) | OVH Canada | French (parent: OVH SAS) | Canada (OVH Canada entity is the data controller) |
| LLM inference (transition default) | OpenRouter | US | US (transitional only — disclosed in `/transparency`) |
| Live search | Serper (`google.serper.dev`) | US-based search API (legal entity not independently verified; Serper's Terms at serper.dev/terms specify the governing law) | Disclosed exception per operator directive 2026-05-13: search queries carry no confidential content; sovereignty protects the LLM inference path + report data, not the keyword query. See `docs/transparency.md` §4. |
| Source corpora (T1) | Government sites (FDA, EMA, Health Canada, NICE, MHRA, WHO, NCBI) | Sovereign per source | Each source jurisdiction |
| Bib / DOI infrastructure | doi.org (CNRI US), Crossref (UK), Unpaywall + OpenAlex (US non-profits), arXiv (Cornell US), SEC EDGAR (US govt) | Mixed; disclosed | Mixed |
| DNS | easyDNS or Cira | Canadian | Canada |
| TLS cert | Let's Encrypt (Internet Security Research Group) | US 501(c)(3) | US — BUT cert is a public attestation, no data leaves to ISRG |

Decision tree per layer documented in `docs/transparency.md`.
