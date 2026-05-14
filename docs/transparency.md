# POLARIS Carney demo — public transparency reference

This document tells reviewers (incl. PM Mark Carney's office) how to audit that this POLARIS deploy is sovereign, signed, and bound by the policies it claims.

The machine-readable companion is `GET /transparency` on the live deploy.

## 1. Sovereignty filter

POLARIS' clinical-grade filter accepts only **Tier 1 (T1)** sources by default. T1 is the regulatory + clinical guideline corpus (FDA, EMA, NICE, Health Canada, etc.) marked `legal_cleared` in the evidence pool.

Sentences citing non-T1 sources are **redacted** from the bundle. If a section has zero passing sentences after the cascade, the section is **dropped**. If a report has zero passing sections, the pipeline raises `SovereigntyFilterEmptiedReportError` (HTTP 422 from `/runs/{id}/bundle.tar.gz`).

Tier definitions:

| Tier | Description | Default sovereignty status |
|---|---|---|
| T1 | Regulatory + clinical guideline corpora | legal_cleared = true |
| T2 | Peer-reviewed primary literature | requires explicit operator clearance |
| T3 | Unverified web content + raw uploads | excluded; fallback on unknown tiers |

Verify: `curl https://polaris.<domain>/transparency/policy` returns the `sovereignty_filter` block.

## 2. Evaluator models

Pipeline-A uses a **two-family evaluator**: generator and verifier are from different training lineages so an internal failure in one family can't pass the other.

Current models in production (from `/transparency`):
- **Generator:** `${PG_GENERATOR_MODEL}` (default `deepseek/deepseek-v4-pro`)
- **Evaluator:** `${PG_EVALUATOR_MODEL}` (default `qwen/qwen-2.5-72b-instruct`)

`openrouter_client.check_family_segregation` raises `RuntimeError` at construction if the configured models are not from different families.

## 3. GPG signing — verifying a bundle

Every audit bundle returned by `GET /runs/{run_id}/bundle.tar.gz` contains a `manifest.yaml.asc` GPG detached signature over `manifest.yaml`. Verify on your workstation:

```bash
# Fetch the demo signing public key.
curl -fsS https://polaris.<domain>/transparency/pubkey.asc > polaris.pubkey.asc
gpg --import polaris.pubkey.asc

# Fetch a bundle.
curl -fsS https://polaris.<domain>/api/v6/runs/<run_id>/bundle.tar.gz > bundle.tar.gz
tar -xzf bundle.tar.gz
cd audit_*/

# Verify the signature over manifest.yaml.
gpg --verify manifest.yaml.asc manifest.yaml
```

A successful verification prints `Good signature from "POLARIS Carney Demo <signing@polaris.local>"`. The fingerprint must match the `signing_key_fingerprint` field in `/transparency`.

## 4. Egress allowlist

The Vexxhost host (Canadian-owned hosting, Montréal) runs `scripts/egress_lockdown.sh` which installs iptables rules in BOTH `OUTPUT` (host-originated) and `DOCKER-USER` (container-forwarded) chains. Off-allowlist traffic on 80/443 is **dropped + logged via the kernel iptables LOG target** with prefix `[POLARIS-EGRESS-DROP]`. The script's own install/config events go to `/var/log/polaris-egress.log`; the drop log lines land wherever rsyslog/journald is configured to forward kernel facility messages (typically `/var/log/kern.log` or `journalctl -k`).

Current allowlist domains (from `/transparency`, sovereign pivot per I-carney-008, search per I-carney-010):

- `openrouter.ai`, `api.openrouter.ai` — LLM API (transitional; replaced by private OVH H200 vLLM endpoint when `POLARIS_LLM_BACKEND=vllm`)
- `google.serper.dev` — Serper web search (US-based; see "Web search provider" below)
- `api.semanticscholar.org` — Semantic Scholar (US AI2 non-profit; disclosed; removable for stricter sovereignty)
- T1 corpus endpoints — `fda.gov`, `accessdata.fda.gov`, `clinicaltrials.gov`, `ncbi.nlm.nih.gov`, `pmc.ncbi.nlm.nih.gov`, `pubmed.ncbi.nlm.nih.gov`, `ema.europa.eu`, `nice.org.uk`, `mhra.gov.uk`, `www.gov.uk`, `canada.ca`, `hc-sc.gc.ca`, `recalls-rappels.canada.ca`, `health-products.canada.ca`, `hres.ca`, `cda-amc.ca`, `who.int`, `iarc.who.int`
- Bibliographic / DOI infrastructure — `doi.org`, `dx.doi.org`, `api.crossref.org` (UK non-profit), `api.unpaywall.org`, `api.openalex.org`, `arxiv.org`, `export.arxiv.org`, `efts.sec.gov`, `www.sec.gov`
- `github.com`, `codeload.github.com` — source clones
- `registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com` — Docker registry
- `acme-v02.api.letsencrypt.org`, `r3.o.lencr.org` — Let's Encrypt TLS cert renewal (public attestation only; no data leaves)

**Web search provider:** Serper (`google.serper.dev`), a US-based search API. This is a deliberate, disclosed exception to the "no US company" posture, accepted per operator directive 2026-05-13.

What Serper receives: the search query string itself, plus the normal request metadata any HTTP API call carries — the API account/key, source IP, timestamp, and user-agent — which Serper's privacy policy (serper.dev/privacy) describes it logging as system/access activity. What Serper does NOT receive: the uploaded corpus, the evidence pool, the generated report, or any operator-entered content. Serper returns only result URLs + snippets; POLARIS then fetches the actual T1 evidence directly from the government corpus endpoints listed above.

The rationale for accepting the exception: POLARIS's sovereignty constraint protects the **LLM inference path and the generated report data** — those run on Canadian/non-US infrastructure (Vexxhost orchestrator + OVH H200 inference). A web-search query is a short keyword string carrying no confidential research content; the sensitive artifact is the synthesized report, which never transits Serper. A reviewer who wants zero US touch in the search path can swap Serper for a non-US provider (Mojeek UK / Qwant FR / Ecosia DE) — the retrieval code is provider-shaped — but that is not required for the sovereignty posture as scoped.

Build-time hosts (`pypi.org`, `files.pythonhosted.org`, `deb.debian.org`, `security.debian.org`, `registry.npmjs.org`, `dl.cloudsmith.io`) are in the allowlist for first-boot image build; operators tighten further by removing them post-build. Full set in `config/egress_allowlist.txt`.

**No AWS endpoints.** SSM, EC2 messages, and S3 hosts are explicitly NOT in the allowlist (per I-carney-008 sovereignty audit).

**Tier-1 evidence fetching under lockdown.** Pipeline-A's sovereignty filter accepts only T1 (regulatory + clinical guideline) sources by default. The allowlist covers those T1 corpus hosts + the bib/DOI resolution infrastructure needed to attach them to cites. Arbitrary publisher domains (nature.com, nejm.org, thelancet.com, etc.) are NOT in the allowlist — they're T2/T3 and excluded by the sovereignty filter anyway; the egress drop is defense-in-depth.

DNS (53), NTP (123), and link-local metadata (169.254.169.254) remain unrestricted as required substrate.

Verify: `curl https://polaris.<domain>/transparency/policy` returns the `egress_allowlist` array and the `enforcement_layer` list (host iptables + Docker DOCKER-USER).

## 5. Code provenance

`/transparency` returns:
- **`git_commit`** — short SHA of the POLARIS commit deployed
- **`polaris_version`** — `__version__` from `src/polaris_v6/__init__.py`
- **`deploy_timestamp`** — server-side UTC timestamp at /transparency request
- **`provider`** — orchestrator hosting provider (`vexxhost` for the sovereign deploy; `fallback_laptop` for the offline fallback in `docs/carney_demo_runbook.md §5`)
- **`region`** — datacenter region (`montreal-qc` for Vexxhost; `none` for fallback laptop)
- **`dependencies.python`** — first 50 lines of `requirements-v6.txt`

The container images are built from `Dockerfile.v6` and `web/Dockerfile` at the pinned commit; no pre-built registry images are used. Operator can verify by SSH into the host and running `git rev-parse HEAD` inside `/opt/polaris`.

## 6. Filing a sovereignty escalation

If a reviewer finds:
- A non-T1 source content surfacing in a verified sentence
- A bundle whose `manifest.yaml.asc` fails GPG verification
- An off-allowlist egress drop in the kernel log (`journalctl -k | grep POLARIS-EGRESS-DROP`)

Email the operator with the `run_id` + the specific claim/path. The operator can re-run the bundle generation OR confirm the issue is a Tier-2 source mistakenly marked T1.

For the Carney demo, escalation contact is the POLARIS deploy operator listed in the Canadian-registrar DNS WHOIS record for the deploy domain.
