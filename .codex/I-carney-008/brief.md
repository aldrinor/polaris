# I-carney-008 brief — sovereign pivot

**GH:** #486
**Branch:** `bot/I-carney-008-sovereign-pivot`
**Authored:** 2026-05-13

## What

Replace the AWS Terraform deploy (Carney demo substrate from I-carney-002..007) with a fully sovereign Canadian stack. AWS ca-central-1 was physically in Montréal, but Amazon is a US corporation subject to the US CLOUD Act + US FISA — fails the sovereignty audit per user directive 2026-05-13 verbatim: **"Full sovereign — no US company anywhere."**

## Stack pivot

| Layer | Before | After |
|---|---|---|
| Orchestrator hosting | AWS EC2 (ca-central-1) | Vexxhost (Canadian-owned, Montréal) |
| LLM inference (production) | OpenRouter (US) | OVH BHS H200 (French-owned, Beauharnois QC) running vLLM (depends on GH#90 procurement + GH#199 client code) |
| LLM inference (transition) | OpenRouter (US) | OpenRouter (US) — kept as transitional fallback; `/transparency` discloses |
| Live search | Serper (US) | DEFERRED to GH#487 (Mojeek UK / Qwant FR / Ecosia DE candidates); Brave was Codex-rejected at iter-1 because Brave Software Inc. is Delaware-incorporated (US) |
| Secret store | AWS Secrets Manager + SSM Parameter Store | Encrypted offline `polaris_demo_secrets.tar.gz.gpg` on operator workstation YubiKey |
| Bib / DOI / T1 corpus | doi.org + Crossref + Unpaywall + OpenAlex + arXiv + government endpoints | Same; disclosed per layer |
| DNS | Route 53 | easyDNS or Cira (Canadian) |
| TLS CA | ACM | Let's Encrypt (US 501(c)(3) ISRG; public attestation only, no data leaves) |

## Acceptance criteria

1. `infra/aws/` → `infra/aws.archived/` with ARCHIVED banner in README ✅
2. `infra/vexxhost/` created: `provision.sh`, `.env.example`, `README.md` ✅
3. `config/egress_allowlist.txt`: AWS endpoints removed; T1 govt corpus + bib/DOI + policy-domain hosts added; build-time vs runtime split documented ✅
4. `docs/carney_demo_runbook.md` §0/§1/§1b/§5/§8/§9 updated for sovereign path ✅
5. `docs/transparency.md` updated; new `provider` field disclosed ✅
6. `src/polaris_v6/api/transparency.py` `provider` + `region` + `build_time_hosts_pruned` fields added, empty-string env-vars handled ✅
7. `scripts/egress_lockdown.sh` IPv4 + IPv6 parity (iter-2 P1-2) ✅
8. `scripts/egress_runtime_tighten.sh` NEW — strips build-time US-corp hosts post-build ✅
9. Codex diff review APPROVE within 5-iter cap ✅ (APPROVE on iter 5)
10. Tests pass: 9/9 transparency ✅

## Codex iteration trail

| Iter | Verdict | Novel P1 | Continuing P1 | P2 | Key findings |
|---|---|---|---|---|---|
| 1 | REQUEST_CHANGES | 4 | 0 | 4 | Brave is Delaware-corp (US); empty provider/region; vllm default; egress drops T1 fetches |
| 2 | REQUEST_CHANGES | 1 | 2 | 3 | Novel IPv6 bypass; continuing Brave/T1 cleanup; pruning + git_commit + auth path |
| 3 | REQUEST_CHANGES | 0 | 1 | 1 | 5 specific missing regulatory hosts; operator docs reference old script |
| 4 | REQUEST_CHANGES | 1 | 0 | 0 | Policy-domain hosts (12) missing |
| 5 | **APPROVE** | 0 | 0 | 0 | zero P0/P1/P2/P3; convergence_call: accept_remaining |

## Follow-up Issues opened

- **GH#487 I-carney-009** — Replace Serper with non-US search provider (Mojeek/Qwant/Ecosia code-side swap)
- **GH#199 I-sov-001** (existing) — Replace OpenRouter with sovereign vLLM (depends on OVH H200 landing)
- **GH#90 I-phase0-009** (existing) — OVH BHS H200 procurement (HARD GATE; operator action this week per user directive)
