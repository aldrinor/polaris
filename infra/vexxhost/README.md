# infra/vexxhost — sovereign Canadian deploy

The active Carney demo deploy path. Replaces `infra/aws.archived/` (US-owned, fails sovereignty audit).

**Hosting:** Vexxhost (Canadian-owned, Montréal datacenter).
**LLM inference:** OVH BHS H200 (French-owned, Beauharnois QC) running self-hosted DeepSeek V4 Pro + Gemma 4 31B via vLLM. See `docs/ovh_h200_procurement_spec.md`.
**Search:** DEFERRED to GH#487 I-carney-009 (Mojeek UK / Qwant FR / Ecosia DE candidates — non-US). Codex iter-1 caught Brave Software Inc. is Delaware-incorporated (US), so the original Brave plan is invalid.
**No US company anywhere in the runtime path.**

## Prereqs (operator, T-7 before demo)

1. Vexxhost account + project in Montréal region. Free tier available; demo workload fits in v3-32 (8 vCPU / 32 GB / 100 GB SSD).
2. Provision a single Ubuntu 24.04 LTS VM via Vexxhost web console:
   - Flavor: `v3-32` or larger
   - Image: Ubuntu 24.04 LTS
   - Network: floating public IPv4 + IPv6
   - SSH key uploaded
3. Domain registered + DNS A record for `polaris.<your-domain>` pointing at the VM's floating IPv4. Use a Canadian registrar (easyDNS, Cira, Hover-Canada-billing) for the sovereignty story.
4. GPG demo signing key generated on operator workstation: `bash scripts/bootstrap_gpg_demo_key.sh`. Produces `outputs/polaris_demo_pubkey.asc` and a fingerprint in `state/polaris_gpg_keyid.txt`. ALSO export the secret: `gpg --homedir ~/.gnupg-polaris --armor --export-secret-key "POLARIS Carney Demo" > polaris_demo_secret.asc`.
5. Non-US web search API key per GH#487 I-carney-009 (Mojeek UK / Qwant FR / Ecosia DE — pick at PR time; OPTIONAL during transition while pipeline-A runs on cached corpus + direct T1 government endpoints).
6. OVH H200 server provisioned in BHS — see `docs/ovh_h200_procurement_spec.md`. Note its private IP; default vLLM endpoint is `http://10.0.0.42:8000/v1`.
7. bcrypt-hashed `static_accounts.yaml` prepared locally (template at `config/static_accounts.example.yaml`).

## Deploy (single command)

```bash
# 1. Stage files on the VM.
scp infra/vexxhost/.env.example root@polaris.<domain>:/root/.env  # edit first
scp outputs/polaris_demo_pubkey.asc root@polaris.<domain>:/root/
scp ~/polaris_demo_secret.asc       root@polaris.<domain>:/root/
scp config/static_accounts.yaml     root@polaris.<domain>:/root/  # filled-in version
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

TOKEN=$(curl -fsS -X POST https://polaris.<your-domain>/auth/login \
    -H 'content-type: application/json' \
    -d '{"username":"carney_office","password":"<password>"}' \
    | jq -r .access_token)

curl -fsS -X POST https://polaris.<your-domain>/api/v6/runs \
    -H "Authorization: Bearer $TOKEN" \
    -H 'content-type: application/json' \
    -d '{"template":"clinical","question":"Is tirzepatide effective for type 2 diabetes?"}'
```

## Egress lockdown (T-6 before demo)

After the first successful deploy + Caddy ACME provisioning succeeds:

```bash
ssh root@polaris.<domain>
sudo bash /opt/polaris/scripts/egress_lockdown.sh
sudo iptables -L POLARIS_EGRESS_HOST -n -v | head -20
sudo iptables -L POLARIS_EGRESS_DOCKER -n -v | head -20
```

Both chains must show DROP rules at the bottom + the allowlisted IPs as ACCEPT.

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
                                 Brave Search API (CZ)
                                 + government sources
                                 (FDA, NICE, Health Canada)
```

## Why not Terraform

The Vexxhost OpenStack Terraform provider exists, but for a single VM the operator-time overhead of writing + reviewing the HCL exceeds the time saved over a web-console click + ssh + bash. If you scale to >3 VMs later, port `provision.sh` into a Terraform module then.

## Sovereignty audit checklist (for transparency.md reviewers)

| Layer | Provider | Ownership | Jurisdiction |
|---|---|---|---|
| Orchestrator hosting | Vexxhost | Canadian | Canada (PIPEDA + Quebec Law 25) |
| LLM inference (when OVH H200 online + GH#199 ships) | OVH Canada | French (parent: OVH SAS) | Canada (OVH Canada entity is the data controller) |
| LLM inference (transition default) | OpenRouter | US | US (transitional only — disclosed in `/transparency`) |
| Live search | DEFERRED to GH#487 | Non-US (Mojeek UK / Qwant FR / Ecosia DE candidates) | TBD per provider; Codex iter-1 caught Brave Software Inc. is Delaware-incorporated (US), invalidating the original Brave plan |
| Source corpora (T1) | Government sites (FDA, EMA, Health Canada, NICE, MHRA, WHO, NCBI) | Sovereign per source | Each source jurisdiction |
| Bib / DOI infrastructure | doi.org (CNRI US), Crossref (UK), Unpaywall + OpenAlex (US non-profits), arXiv (Cornell US), SEC EDGAR (US govt) | Mixed; disclosed | Mixed |
| DNS | easyDNS or Cira | Canadian | Canada |
| TLS cert | Let's Encrypt (Internet Security Research Group) | US 501(c)(3) | US — BUT cert is a public attestation, no data leaves to ISRG |

Decision tree per layer documented in `docs/transparency.md`.
