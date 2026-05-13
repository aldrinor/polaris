# I-carney-008 Claude architect audit

**Issue:** GH#486 — Sovereign pivot: AWS archived, Vexxhost + OVH + non-US search adopted
**Branch:** `bot/I-carney-008-sovereign-pivot`
**Head commit:** `ef4da709`
**Codex diff verdict:** APPROVE iter 5 of 5

## Surface

| File | Purpose |
|---|---|
| `infra/aws/` → `infra/aws.archived/` | 14 Terraform files archived with ARCHIVED banner |
| `infra/vexxhost/provision.sh` | ~165-line bash deploy: docker + caddy + ACME + GPG bootstrap + healthy-loop fail-loud |
| `infra/vexxhost/.env.example` | Env template with POLARIS_PROVIDER=vexxhost + POLARIS_REGION=montreal-qc explicit, openrouter as transition default |
| `infra/vexxhost/README.md` | Operator runbook + sovereignty audit table + architecture diagram |
| `config/egress_allowlist.txt` | T1 corpus + bib/DOI + policy-domain hosts (clinical + policy + sovereignty all covered); BUILD-TIME ONLY block delimited for runtime-tighten |
| `scripts/egress_lockdown.sh` | Rewritten for IPv4 + IPv6 parity (iptables + ip6tables × OUTPUT + DOCKER-USER) |
| `scripts/egress_runtime_tighten.sh` NEW | Strips build-time US-corp hosts from /etc/polaris/ allowlist + sets runtime_pruned.flag + re-applies lockdown |
| `docs/carney_demo_runbook.md` | §0/§1/§1b/§5/§8/§9 rewritten for sovereign path; §1b is now a 4-step lockdown + tighten + verify-4-chains + verify-flag procedure |
| `docs/transparency.md` | T1 corpus enumerated; search-provider deferred to GH#487; AWS removed; provider field added |
| `src/polaris_v6/api/transparency.py` | + provider, + build_time_hosts_pruned; region resolves POLARIS_REGION → AWS_REGION → unknown |
| `tests/polaris_v6/api/test_transparency.py` | 9 tests (was 5): provider/region schema, AWS_REGION compat fallback, no-AWS-SG enforcement_layer regression, build_time_hosts_pruned True+False cases |
| `state/active_issue.json` | I-carney-008 in_progress, GH#486; archived I-carney-001 AWS workstream preserved as reference |
| `docs/ovh_h200_procurement_spec.md` | Earlier commit d8faf5df — procurement spec for operator to email OVH Canada sales |

## Codex iteration trajectory (P1 + P2 close-out)

| Iter | Brief outcome | Novel P1 → Continuing | P2 | Reasoning |
|---|---|---|---|---|
| 1 | REQUEST_CHANGES | 4 → — | 4 | Brave (US, factual); empty provider/region; vllm default broken; T1 fetch under lockdown |
| 2 | REQUEST_CHANGES | 1 (IPv6) → 2 (Brave residual + T1 host exactness) | 3 | Dual-stack lockdown bypass + 4 Brave surfaces + www.* allowlist gaps + git_commit pin + build/runtime split + /auth/login Next-rewrite path |
| 3 | REQUEST_CHANGES | 0 → 1 (5 specific hostnames) | 1 (operator-doc) | hpfb-dgpsa.ca, dhpp.hpfb-dgpsa.ca, dailymed.nlm.nih.gov, nmpa.gov.cn, www.nmpa.gov.cn; docs still routed to old script |
| 4 | REQUEST_CHANGES | 1 (policy-domain) → 0 | 0 | 12 US federal policy hosts + EU Commission + courtlistener |
| 5 | **APPROVE** | 0 → 0 | 0 | convergence_call: accept_remaining |

Convergence is monotonic in continuing-P1 (4→2→1→0→0) and P2 (4→3→1→0→0). Novel-P1 spikes at iter-2 (IPv6) and iter-4 (policy-domain) reflect real coverage emerging as the T1 surface specified more concretely — not adversarial drip-feeding.

## Sovereignty audit

Honest disclosure of mixed-jurisdiction layers:

- **Sovereign-Canadian:** Vexxhost orchestrator, easyDNS/Cira DNS, Canadian PIPEDA + Quebec Law 25
- **Sovereign-French-in-Canada:** OVH BHS H200 (when online; OVH Canada is the data controller, parent OVH SAS is French)
- **Non-US-non-Canadian:** search provider TBD per GH#487 (Mojeek UK / Qwant FR / Ecosia DE)
- **US govt (NOT US company):** FDA / NCBI / ClinicalTrials.gov / SEC EDGAR / federalregister.gov / regulations.gov / etc. — these are US *government* open-data endpoints of regulatory + policy law; the sovereignty filter clears them as T1; the user directive targets US private corps, not sovereign govt sources
- **US non-profit:** doi.org (CNRI), Unpaywall + OpenAlex (Our Research), arXiv (Cornell), Let's Encrypt ISRG — all disclosed in `/transparency`
- **UK non-profit:** Crossref (sovereign-aligned for Canada via UK GDPR adequacy)
- **US corp (transitional only):** OpenRouter for LLM during OVH H200 lead time; `/transparency` flags

## Verdict

READY TO MERGE. All Codex-required artifacts present:

- `.codex/I-carney-008/brief.md`
- `.codex/I-carney-008/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-carney-008/codex_diff.patch` (1124+ LOC source diff, 2060 cumulative)
- `.codex/I-carney-008/codex_diff_audit.txt` (canonical iter-5 APPROVE)
- `.codex/I-carney-008/codex_diff_audit_iter_{1,2,3,4,5}.txt` (trajectory)
- `.codex/I-carney-008/codex_diff_brief_iter_{1,2,3,4,5}.md`
- `outputs/audits/I-carney-008/claude_audit.md` (this file)

## What ships in this PR

- Complete infrastructure pivot from AWS to Vexxhost
- Egress lockdown that actually covers what pipeline-A fetches (T1 clinical + bib + DOI + policy)
- Dual-stack IPv4 + IPv6 lockdown
- Build-time vs runtime allowlist split with /transparency disclosure
- Operator runbook + provision script + Vexxhost README all aligned
- 9/9 transparency tests passing

## What ships in follow-ups (NOT this PR)

- GH#487 I-carney-009: code-side Serper → non-US search provider (Mojeek/Qwant/Ecosia)
- GH#199 I-sov-001: code-side OpenRouter → vLLM (depends on OVH H200 landing)
- GH#90 I-phase0-009: operator emails OVH Canada sales TODAY per `docs/ovh_h200_procurement_spec.md`
