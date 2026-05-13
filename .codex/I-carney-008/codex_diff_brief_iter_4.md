HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-008 diff iter 4 — close iter-3 P1 + P2

## Iter-3 verdict recap

Iter-3 returned `verdict: REQUEST_CHANGES` with:

- P1-3 (continuing) — 5 missing regulatory hosts (hpfb-dgpsa.ca, dhpp.hpfb-dgpsa.ca, dailymed.nlm.nih.gov, nmpa.gov.cn, www.nmpa.gov.cn)
- P2 (continuing operator-doc) — runbook + README + provision.sh told operators to run `egress_lockdown.sh` directly, never reached `egress_runtime_tighten.sh`
- 2 cosmetics (IPv6 verification docs, allowlist header still IPv4-only)

All resolved in commit `11cc024a`. Cumulative diff at `.codex/I-carney-008/codex_diff.patch` (1919 LOC across 23 source files; excludes the codex_diff_audit_iter_*.txt review-output files).

## P1-3 (continuing iter-2/iter-3) ✅ RESOLVED

**Iter-3 finding (verbatim):** "T1/regulatory allowlist is still under-covered. config/egress_allowlist.txt omits hpfb-dgpsa.ca / dhpp.hpfb-dgpsa.ca, while src/polaris_graph/retrieval/evidence_selector.py:98-103, config/scope_templates/clinical.yaml:124, and tests/polaris_graph/test_m42d_hc_quota_expansion.py all treat that Health Canada DHPP path as active regulatory evidence. It also omits dailymed.nlm.nih.gov from the clinical url_pattern path and nmpa.gov.cn from evidence_selector.py:107."

**Iter-4 fix (11cc024a):**

`config/egress_allowlist.txt` additions:

- Health Canada DHPP: `hpfb-dgpsa.ca`, `www.hpfb-dgpsa.ca`, `dhpp.hpfb-dgpsa.ca`
- NLM DailyMed (FDA labels): `dailymed.nlm.nih.gov`
- China NMPA: `nmpa.gov.cn`, `www.nmpa.gov.cn`

Verification (powershell):

```
$allow = Get-Content config/egress_allowlist.txt | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') } | Sort-Object -Unique
$expected = @('hpfb-dgpsa.ca','dhpp.hpfb-dgpsa.ca','dailymed.nlm.nih.gov','nmpa.gov.cn','www.nmpa.gov.cn')
foreach ($h in $expected) { if ($allow -notcontains $h) { Write-Output "MISSING $h" } else { Write-Output "OK $h" } }
```

Expected output: 5 × `OK ...` (was 5 × `MISSING ...` in iter-3).

## P2 (continuing operator-doc) ✅ RESOLVED

**Iter-3 finding (verbatim):** "runtime build-host pruning is implemented but not what operators are told to run. docs/carney_demo_runbook.md:76-86, infra/vexxhost/README.md:62-71, and infra/vexxhost/provision.sh:198-199 still instruct egress_lockdown.sh directly, not scripts/egress_runtime_tighten.sh, so build_time_hosts_pruned stays false and build-time hosts remain allowed if docs are followed."

**Iter-4 fix (11cc024a):**

1. `docs/carney_demo_runbook.md §1b` rewritten — 4-step flow:
   1. `sudo bash /opt/polaris/scripts/egress_lockdown.sh`
   2. `sudo bash /opt/polaris/scripts/egress_runtime_tighten.sh`
   3. Verify all 4 chains (iptables × ip6tables × OUTPUT × DOCKER-USER)
   4. Verify `/transparency build_time_hosts_pruned` == `true`

2. `infra/vexxhost/README.md` egress section rewritten identically.

3. `infra/vexxhost/provision.sh` closing echoes rewritten to instruct BOTH scripts + 4-chain verification + `/transparency` flag check.

After these doc changes, an operator following step-by-step now reaches `egress_runtime_tighten.sh` and `/transparency` exposes the truthful state.

## P3 cosmetic ✅ RESOLVED

- `config/egress_allowlist.txt` header rewritten: "A AND AAAA records" + "iptables (IPv4) + ip6tables (IPv6)" — was IPv4-only language carryover.
- IPv6 verification commands added inline in §1b runbook + README egress sections (`sudo ip6tables -L POLARIS_EGRESS_HOST_V6 -n -v | head -20` + `sudo ip6tables -L POLARIS_EGRESS_DOCKER_V6 -n -v | head -20`).

## Trajectory

| Iter | novel P1 | continuing P1 | P2 | convergence_call |
|---|---|---|---|---|
| 1 | 4 | 0 | 4 | continue |
| 2 | 1 (IPv6) | 2 (Brave/T1) | 3 | continue |
| 3 | 0 | 1 (5 specific hosts) | 1 (operator docs) | continue |
| 4 (target) | 0 | 0 | 0 | accept_remaining |

## Direct questions iter 4

1. **5 new hostnames** in `config/egress_allowlist.txt` cover iter-3's missing-host list exactly. The verification script confirms presence. APPROVE?
2. **Operator-doc flow** rewritten in 3 surfaces (runbook §1b, README egress section, provision.sh closing echoes) to call BOTH `egress_lockdown.sh` AND `egress_runtime_tighten.sh`. APPROVE?
3. **IPv6 verification commands + header rewrite** address both P3 cosmetics. APPROVE?
4. **Anything else blocking iter-4 APPROVE?** Per the 5-cap, iter-5 either APPROVEs or Claude force-APPROVEs on residual non-P0/P1 — front-load anything material now rather than banking it.

## What this PR explicitly does NOT do (so you don't flag them as missing)

- Code-side Serper → non-US-provider swap (deferred to GH#487 I-carney-009).
- Code-side OpenRouter → vLLM swap (deferred to GH#199 I-sov-001).
- Removing US govt T1 endpoints (FDA, NCBI, ClinicalTrials.gov, SEC EDGAR) from the allowlist.
- Multi-VM HA Vexxhost topology (Phase-2).
- Vault-based secret rotation (Phase-2).

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
