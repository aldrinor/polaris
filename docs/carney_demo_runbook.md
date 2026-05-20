# Carney demo runbook — operator playbook

This is the single source of truth for the PM Mark Carney POLARIS demo. Read end-to-end before the meeting; refer back during.

**Demo target window:** 2026-06-05 to 2026-06-09.

**Stack (revised 2026-05-20 per current deploy state — see `project_polaris_already_deployed` memory):**

| Layer | Provider | Ownership |
|---|---|---|
| Orchestrator hosting | OVH BHS5 Québec VM `polaris-orchestrator` (51.79.90.35) | French-owned (non-US) |
| LLM inference (production) | OpenRouter (`deepseek/deepseek-v4-pro` generator + `google/gemma-4-31b-it` evaluator per I-cd-009) | US — disclosed in `/transparency`; sovereign GPU lands at the Session-A cluster bring-up (Seq 39 / #644) before the dress rehearsal |
| LLM inference (sovereign target) | OVH H200 (Beauharnois QC) OR Scaleway/Hetzner EU per operator directive 2026-05-18 (Canada-only GPU was too hard/expensive/slow; EU GPU allowed at demo stage) running DeepSeek V4 Pro + Gemma 4 31B via vLLM | French / EU-owned (non-US) |
| Live search | Serper (`google.serper.dev`) | US — disclosed exception per operator directive 2026-05-13; search queries carry no confidential content, reports stay sovereign. See `docs/transparency.md` §4. |
| Bib / DOI / T1 corpus | doi.org + Crossref (UK) + Unpaywall + OpenAlex + arXiv + government endpoints | Mixed; disclosed per layer |
| DNS | easyDNS or Cira | Canadian |
| TLS CA | Let's Encrypt ISRG | US 501(c)(3) — public attestation only, no data leaves |
| **AWS** | ARCHIVED at `infra/aws.archived/` | Was US-owned — fails sovereignty audit |
| **Vexxhost** | RETIRED (was the 2026-05-13 plan; current deploy is OVH BHS5 per `project_polaris_already_deployed` memory) | Canadian-owned but unused for the current deploy |

**Domain status (2026-05-20):** the live demo URL today is the bare IP `http://51.79.90.35:3000`. Domain + TLS land at **Seq 36 / I-cd-036 / #636** (Caddy/TLS + production-domain acceptance). The dress rehearsal (Seq 42 / I-D-01 / #647) runs against the domain.

See `state/restart_instructions.md` + the I-A-01 (#606) + I-B-01 (#622) PRs for the current OVH deploy path. The §1 below describes the **original** Vexxhost-targeted flow; preserved for reference but NOT what's live today.

---

## §0 — Prereqs (1 week before demo, sovereign deploy)

| Item | Owner | Status |
|---|---|---|
| Vexxhost Montréal account + project + SSH key | Ops | https://my.vexxhost.com/ |
| Vexxhost VM provisioned (Ubuntu 24.04 LTS, `v3-32` or larger, floating IPv4 + IPv6) | Ops | `ssh root@<floating-ip>` reachable |
| Canadian-registrar domain + DNS A record `polaris.<domain>` → VM floating IPv4 | Ops | `dig +short polaris.<domain>` returns the IP |
| `gh` + `ssh` + `scp` CLIs installed | Ops | `gh --version && ssh -V` |
| Demo signing GPG key generated | Ops | `bash scripts/bootstrap_gpg_demo_key.sh` |
| Serper API key (web search — US, disclosed) | Ops | https://serper.dev/ |
| OVH BHS H200 procurement initiated | Ops | email per `docs/ovh_h200_procurement_spec.md` to salescanada@ovhcloud.com |
| OVH H200 + Vexxhost private-network peering confirmed | Ops | private IPv4 reachable from Vexxhost VM (vLLM endpoint `http://<priv-ip>:8000/v1`) |
| `static_accounts.yaml` filled with bcrypt-hashed reviewer pwd (at `/etc/polaris/static_accounts.yaml` on VM — NEVER in repo `config/`) | Ops | `python -c "from passlib.hash import bcrypt; print(bcrypt.using(rounds=12).hash('<pw>'))"` |
| Carney office contact + demo time confirmed | Lead | calendar invite |
| Fallback laptop ready | Lead | `docker compose -f docker-compose.v6.yml up -d` on laptop |

**During the OVH H200 lead-time (5-10 business days):** the orchestrator runs with `POLARIS_LLM_BACKEND=openrouter` as a transitional fallback (this is the `.env.example` default). `/transparency` surfaces OpenRouter as the active inference backend so reviewers see the US disclosure during the transition. Flip to `POLARIS_LLM_BACKEND=vllm` + restart compose once (a) the OVH H200 is online with a reachable private IP, AND (b) GH#199 I-sov-001 has shipped the vLLM client code. Setting the flag without both prereqs will break generation.

## §1 — Deploy day-1 (T-7 before demo, sovereign Vexxhost path)

**Prereqs done in §0:** Vexxhost VM provisioned, DNS A record pointing at it, GPG keys generated, Serper API key obtained, OVH H200 server delivered + private network peered, `.env` filled, `static_accounts.yaml` filled.

```bash
# 0. Resolve the commit to pin LOCALLY (Codex iter-1 P2-3: $(git rev-parse polaris)
#    inside the ssh heredoc would expand on the remote host, where the repo
#    may not exist or may point at a different commit).
POLARIS_REPO_COMMIT=$(git rev-parse polaris)
POLARIS_DOMAIN=polaris.<your-domain>
POLARIS_ACME_EMAIL=ops@<your-domain>

# 1. Stage files on the Vexxhost VM.
scp infra/vexxhost/.env.example       root@${POLARIS_DOMAIN}:/root/.env  # edit FIRST
scp outputs/polaris_demo_pubkey.asc   root@${POLARIS_DOMAIN}:/root/
scp ~/polaris_demo_secret.asc         root@${POLARIS_DOMAIN}:/root/
# I-cd-014: NEVER stage static_accounts.yaml inside the repo `config/` — it
# is gitignored AND dockerignored. Operator generates it locally OUTSIDE
# the repo (e.g., /tmp/polaris_secrets/static_accounts.yaml) and scps to
# /root/ on the VM; `infra/vexxhost/provision.sh:102-107` then copies it
# to /etc/polaris/static_accounts.yaml with chmod 640.
scp /tmp/polaris_secrets/static_accounts.yaml root@${POLARIS_DOMAIN}:/root/static_accounts.yaml
scp infra/vexxhost/provision.sh       root@${POLARIS_DOMAIN}:/root/

# 2. Run provisioning — pass the locally-resolved commit through ssh env.
ssh root@${POLARIS_DOMAIN} \
    "POLARIS_REPO_COMMIT=${POLARIS_REPO_COMMIT} \
     POLARIS_DOMAIN=${POLARIS_DOMAIN} \
     POLARIS_ACME_EMAIL=${POLARIS_ACME_EMAIL} \
     bash /root/provision.sh"
```

Provisioning takes ~10 minutes (apt + docker pull + Next.js build + Caddy ACME). Verify:

```bash
curl -fsS https://polaris.<your-domain>/health
curl -fsS https://polaris.<your-domain>/transparency | jq
```

### §1b — Install egress lockdown + runtime tighten (mandatory before §2 smoke test)

Per Codex iter-1 P1-2 + iter-2 P2-2 + iter-3 P2: `provision.sh` does NOT auto-run egress lockdown (first compose build needs pypi/npmjs/debian access). After the first `docker compose up -d` succeeds, SSH into the host and run BOTH:

```bash
ssh root@polaris.<your-domain>
# Inside the SSH session:

# 1. Install IPv4 + IPv6 lockdown with the FULL allowlist (build-time hosts
#    still included so re-runs of `docker compose build` work).
sudo bash /opt/polaris/scripts/egress_lockdown.sh

# 2. Tighten by stripping the build-time block (GitHub, Docker registry,
#    Cloudflare CDN, pypi, npmjs, debian, cloudsmith) from the runtime
#    allowlist. After this step `/transparency` reports
#    build_time_hosts_pruned: true.
sudo bash /opt/polaris/scripts/egress_runtime_tighten.sh

# 3. Verify all 4 chains.
sudo iptables -L POLARIS_EGRESS_HOST -n -v | head -20
sudo iptables -L POLARIS_EGRESS_DOCKER -n -v | head -20
sudo ip6tables -L POLARIS_EGRESS_HOST_V6 -n -v | head -20
sudo ip6tables -L POLARIS_EGRESS_DOCKER_V6 -n -v | head -20

# 4. Confirm the pruned flag is visible to /transparency.
curl -fsS https://polaris.<your-domain>/transparency | jq '.build_time_hosts_pruned'
# expected: true
```

All four chains (iptables + ip6tables × OUTPUT + DOCKER-USER) must show DROP rules at the bottom + the allowlisted IPs as ACCEPT. Without these two steps the deploy claims egress controls but they are NOT enforced — `/transparency`'s `enforcement_layer` field would be inaccurate AND `build_time_hosts_pruned` would remain false, indicating that GitHub/Docker/pypi/npm are still reachable from the runtime.

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

## §5 — Fallback laptop (sovereign — no US KMS dependency)

If the Vexxhost deploy is unreachable (DNS, network outage, etc.) during the demo:

**One-time setup (T-3 before demo):** populate the laptop's `.env` + `/etc/polaris/static_accounts.yaml` from an encrypted offline secret bundle. No US-owned KMS (AWS Secrets Manager / GCP KMS / Azure Key Vault) is on the sovereign hot-path; the operator workstation holds the master `polaris_demo_secrets.tar.gz.gpg`, decrypted by the operator's personal GPG key (NOT the demo signing key — different keyring).

```bash
cd /local/polaris

# 1. Decrypt the offline secret bundle (operator's personal GPG key).
gpg --decrypt ~/polaris_demo_secrets.tar.gz.gpg | tar -xz -C /tmp/polaris_secrets
# Bundle layout (encrypt-only-once, kept on a YubiKey + paper backup):
#   /tmp/polaris_secrets/.env                  — same as infra/vexxhost/.env.example, filled in
#   /tmp/polaris_secrets/static_accounts.yaml  — bcrypt-hashed reviewer pwd
#   /tmp/polaris_secrets/gpg_private_key.asc   — POLARIS demo signing key (private)

# 2. Stage .env at repo root (compose reads this).
cp /tmp/polaris_secrets/.env .env
chmod 600 .env

# 3. Stage static_accounts.yaml at /etc/polaris (matches Vexxhost host path).
sudo mkdir -p /etc/polaris
sudo chmod 750 /etc/polaris
sudo cp /tmp/polaris_secrets/static_accounts.yaml /etc/polaris/static_accounts.yaml
sudo chmod 640 /etc/polaris/static_accounts.yaml

# 4. Import the GPG private key into a separate laptop keyring.
mkdir -p ~/.gnupg-polaris && chmod 700 ~/.gnupg-polaris
gpg --homedir ~/.gnupg-polaris --batch --import /tmp/polaris_secrets/gpg_private_key.asc

# 5. Shred the decrypted plaintext.
shred -u /tmp/polaris_secrets/.env /tmp/polaris_secrets/gpg_private_key.asc
shred -u /tmp/polaris_secrets/static_accounts.yaml
rmdir /tmp/polaris_secrets

# 6. Bring up the stack.
docker compose -f docker-compose.v6.yml down
docker compose -f docker-compose.v6.yml up -d --build

# 7. Smoke test.
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/transparency | jq
```

Localhost demo at http://localhost:3000. Auth + signing + sovereignty filter all behave identically to the Vexxhost deploy since the laptop loads the SAME secrets. `/transparency` will show `provider: "fallback_laptop"` instead of `provider: "vexxhost"` — disclose this if a reviewer asks why.

**Fallback LLM backend:** the laptop cannot reach OVH H200's private IP. Set `POLARIS_LLM_BACKEND=openrouter` in the laptop `.env` and document this in the demo narration: "Vexxhost down → OpenRouter (US) used as transitional fallback for inference; the sovereign deploy path uses self-hosted vLLM."

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

## §8 — Post-demo tear-down (sovereign)

```bash
# Recover audit bundles from the Vexxhost VM BEFORE destroy.
ssh root@polaris.<your-domain> "tar -czf /tmp/carney_bundles.tar.gz /var/lib/polaris/run_bundles"
scp root@polaris.<your-domain>:/tmp/carney_bundles.tar.gz ./carney_demo_bundles.tar.gz

# Vexxhost: power-off + delete VM via web console OR openstack CLI:
openstack server delete polaris-carney

# OVH: keep the H200 server if doing Phase-2 work; otherwise file a cancellation
# ticket via the OVH manager web console (per OVH Canada T&Cs).
```

## §9 — Known limitations (disclose during demo if asked)

- Single-VM Vexxhost (no HA pair) — for demo window only
- Manual GPG private key rotation (auto-rotation via Vexxhost Hashicorp Vault is Phase-2)
- Pipeline-A only (pipeline-B legacy + pipeline-C frozen per architecture.md §5)
- ~20-domain egress allowlist enforced via iptables on the VM (no managed cloud NACL on Vexxhost compute path — sovereign tradeoff vs hyperscaler defense-in-depth)
- /docs + /redoc + /openapi.json public for operator ergonomics — gate to admin in Phase-2
- TLS certs from Let's Encrypt (Internet Security Research Group, US 501(c)(3)). The cert is a public attestation; no data leaves to ISRG. Sovereign-strict tradeoff: replacing with a Canadian CA is Phase-2.
