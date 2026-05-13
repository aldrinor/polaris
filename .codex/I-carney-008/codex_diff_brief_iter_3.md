HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-008 diff iter 3 — exact P1+P2 fix-table since iter-2

## Iter-2 verdict recap

Iter-2 returned `verdict: REQUEST_CHANGES` with:

- P1-1 (continuing) Brave still in 4 surfaces
- P1-2 (novel) IPv6 egress bypass on dual-stack Vexxhost
- P1-3 (continuing) www.* T1 hosts missing from allowlist
- P2-1 POLARIS_GIT_COMMIT placeholder reached prod
- P2-2 Build-time US-corp hosts in runtime allowlist
- P2-3 README smoke used unrewritten /auth/login

All P1 + all P2 are addressed in commit `bad02cea`. Cumulative diff at `.codex/I-carney-008/codex_diff.patch` (1705 LOC across 21 source files, EXCLUDING the codex_diff_audit_iter_*.txt files themselves — those are review-output artifacts and not part of this review).

## P1 fix table (iter-2 → iter-3)

### P1-1 (continuing) — Brave references in 4 places ✅ RESOLVED

**Iter-2 finding (verbatim):** "Brave is not fully removed from active operator surfaces. docs/carney_demo_runbook.md:44 still says 'Brave Search key obtained'; infra/vexxhost/README.md:107 still shows 'Brave Search API (CZ)' in the architecture diagram; state/active_issue.json:10 and :17 still route GH#487/live_search back to Brave."

**Iter-3 fix (bad02cea):**

1. `docs/carney_demo_runbook.md:44` — Prereqs paragraph changed:
   - OLD: "...GPG keys generated, **Brave Search key obtained**, OVH H200..."
   - NEW: "...GPG keys generated, **non-US search API key obtained per GH#487 (or transitional Serper with disclosure)**, OVH H200..."

2. `infra/vexxhost/README.md:107` — Architecture diagram changed:
   - OLD: `Brave Search API (CZ) / + government sources / (FDA, NICE, Health Canada)`
   - NEW: `Non-US search API (GH#487, pending) / + government T1 sources / (FDA, NICE, EMA, MHRA, Health Canada, WHO, NCBI)`

3. `state/active_issue.json:10` — follow_up_issues entry corrected:
   - OLD: `"title": "Replace Serper with Brave Search in real_fetcher.py"`
   - NEW: `"title": "Replace Serper with non-US search provider (Mojeek/Qwant/Ecosia)"`

4. `state/active_issue.json:17` — sovereign_stack.live_search corrected:
   - OLD: `"live_search": "Brave Search API (Czech-owned)"`
   - NEW: `"live_search": "DEFERRED to GH#487 (Mojeek UK / Qwant FR / Ecosia DE candidates — non-US; Codex iter-1 caught Brave Software is Delaware-incorporated)"`

A `grep -i brave` across the working tree now matches ONLY: (a) historical references in this iter-3 brief itself, (b) the iter-1 verdict text in `.codex/I-carney-008/codex_diff_audit_iter_1.txt`, (c) infra/vexxhost/README.md:7 which is the explanation of why Brave was removed. None of the matches direct operators to USE Brave.

### P1-2 (novel) — IPv6 egress bypass ✅ RESOLVED

**Iter-2 finding (verbatim):** "The Vexxhost path provisions IPv6, but lockdown is IPv4-only. infra/vexxhost/README.md:16 and docs/carney_demo_runbook.md:29 require floating IPv4 + IPv6, while scripts/egress_lockdown.sh:37-47 resolves only A records and lines 58-84/104-112 install only iptables rules. Off-allowlist HTTPS over IPv6 bypasses the claimed egress control."

**Iter-3 fix (bad02cea):**

`scripts/egress_lockdown.sh` rewritten to install IPv4 AND IPv6 chains in parallel:

- `resolve_allowlist_v4()` — uses `getent ahostsv4` to enumerate A records
- `resolve_allowlist_v6()` — uses `getent ahostsv6` to enumerate AAAA records
- `install_chain()` now takes `$4 = ipt` (either `iptables` or `ip6tables`) and applies the same chain shape per stack
- IPv4 metadata: `iptables -A ... -d 169.254.169.254/32 -j ACCEPT`
- IPv6 link-local: `ip6tables -A ... -d fe80::/10 -j ACCEPT`
- Bail-loud check: `if ! command -v ip6tables; then exit 1` — refuses to install with a known IPv6 leak

Chain names:

- IPv4: `POLARIS_EGRESS_HOST` (into OUTPUT), `POLARIS_EGRESS_DOCKER` (into DOCKER-USER)
- IPv6: `POLARIS_EGRESS_HOST_V6` (into OUTPUT), `POLARIS_EGRESS_DOCKER_V6` (into DOCKER-USER)

Final log line: `egress lockdown complete (IPv4 + IPv6)`.

### P1-3 (continuing) — T1 allowlist exact-hostname coverage ✅ RESOLVED

**Iter-2 finding (verbatim):** "The expanded allowlist still does not cover several code-recognized T1/regulatory hosts, so lockdown can still block cleared evidence. config/egress_allowlist.txt:38-57 omits common exact hosts like www.fda.gov, www.nice.org.uk, www.clinicaltrials.gov, and www.ema.europa.eu; code paths recognize/target those and other regulatory hosts in src/polaris_graph/audit_ir/competitor_manifest_extractor.py:105-110, src/polaris_graph/retrieval/domain_backends.py:151-159, and src/polaris_graph/retrieval/tier_classifier.py:132-156."

**Iter-3 fix (bad02cea):**

`config/egress_allowlist.txt` expanded:

- `www.fda.gov`, `labels.fda.gov` added next to `fda.gov`
- `www.clinicaltrials.gov` added next to `clinicaltrials.gov`
- `cdc.gov`, `www.cdc.gov` added (tier_classifier REGULATORY_DOMAINS includes cdc.gov)
- `www.nlm.nih.gov` added next to `nlm.nih.gov`
- `www.ema.europa.eu`, `www.europa.eu` added
- `www.nice.org.uk`, `www.mhra.gov.uk`, `gov.uk` (bare) added next to www.gov.uk
- `www.canada.ca`, `www.hc-sc.gc.ca`, `www.hres.ca`, `www.cda-amc.ca` added
- AU/NZ/JP regulator hosts (tier_classifier:152-154): `tga.gov.au`, `www.tga.gov.au`, `medsafe.govt.nz`, `www.medsafe.govt.nz`, `pmda.go.jp`, `www.pmda.go.jp`
- DE/FR (tier_classifier:158): `bfarm.de`, `www.bfarm.de`, `ansm.sante.fr`, `www.ansm.sante.fr`
- `www.who.int`, `www.iarc.who.int` added

Cross-referenced against tier_classifier.py:132-156 REGULATORY_DOMAINS literal + evidence_selector.py:92-110 + domain_backends.py:151-160 site:queries.

## P2 fix table

### P2-1 — POLARIS_GIT_COMMIT placeholder ✅ RESOLVED

`infra/vexxhost/provision.sh:97-103` (Step 3 .env wiring) — added `sed -i "s|^POLARIS_GIT_COMMIT=.*|POLARIS_GIT_COMMIT=${POLARIS_REPO_COMMIT}|" /opt/polaris/.env` plus fallback append if the key didn't exist in the template.

### P2-2 — Build-time hosts in runtime allowlist ✅ RESOLVED

Two-part fix:

1. `config/egress_allowlist.txt` — BUILD-TIME ONLY banner inserted before the github/registry/pypi block, with a clear instruction to operators that runtime tightening copies the file to /etc/polaris/ MINUS the build-time block.

2. `scripts/egress_runtime_tighten.sh` NEW — awk-strips the build-time block (delimited by `# ----- BUILD-TIME ONLY` start and `# I-carney-008: AWS-specific endpoints` end markers), writes `/etc/polaris/runtime_pruned.flag`, re-runs `egress_lockdown.sh`. Includes a post-strip sanity check that fails loudly if github.com/pypi.org/etc. survived.

3. `src/polaris_v6/api/transparency.py:46-58` — new `build_time_hosts_pruned: bool` field; reads `Path(POLARIS_RUNTIME_PRUNED_FLAG or /etc/polaris/runtime_pruned.flag).exists()`. New test `test_transparency_build_time_hosts_pruned_flag_true` pins true case; updated `test_transparency_returns_required_keys` pins false default.

### P2-3 — README smoke /auth/login → /api/v6/auth/login ✅ RESOLVED

`infra/vexxhost/README.md:51` — token-fetch curl now uses `/api/v6/auth/login` matching what Next rewrites expose. `infra/vexxhost/provision.sh:152-156` Caddyfile reverse_proxies everything to webui:3000, and Next rewrites only handle `/api/v6/*`; bare `/auth/login` was a 404.

## Direct questions iter 3

1. **P1-1 Brave removal in 4 surfaces** — runbook prereq line, README diagram, active_issue.json title + sovereign_stack.live_search all swapped. Anything else still pointing operators at Brave? (Audit files are read-only review output, not operator surfaces.) APPROVE?
2. **P1-2 IPv6 lockdown parity** — ip6tables chains installed alongside iptables; bail-loud on missing ip6tables binary; fe80::/10 link-local accepted; AAAA resolution via getent ahostsv6. APPROVE?
3. **P1-3 www.* + AU/NZ/JP/DE/FR regulator hostnames** — cross-referenced against tier_classifier REGULATORY_DOMAINS literal + evidence_selector hosts + domain_backends site:queries. Anything else under-covered? APPROVE?
4. **P2-2 build/runtime split via flag** — `build_time_hosts_pruned: bool` on `/transparency` surfaces whether `scripts/egress_runtime_tighten.sh` has been run. Default False (build-time hosts still active). Operator marked it as a mandatory T-6 step in `docs/carney_demo_runbook.md §1b` (already present). APPROVE?
5. **Anything else blocking iter-3 APPROVE?**

## Convergence

Iter-1: 4 P1 + 4 P2 + 4 P3. All P1 + relevant P2 + P3 fixed in iter-2.
Iter-2: 3 P1 (1 novel IPv6 + 2 continuing carry-over surfaces) + 3 P2. All P1 + all P2 fixed in iter-3.

Trajectory: novel-P1 count dropped 4→1→0 (target this iter). Continuing-P1 dropped from 4 (iter-1 carry-over candidates) → 2 (iter-2 carry-over) → 0 (target this iter). Convergence direction is correct.

## What this PR explicitly does NOT do (so you don't flag them as missing)

- Code-side Serper → non-US-provider swap (deferred to GH#487 I-carney-009).
- Code-side OpenRouter → vLLM swap (deferred to GH#199 I-sov-001).
- Removing US govt T1 endpoints (FDA, NCBI, ClinicalTrials.gov, SEC EDGAR) from the allowlist. These are US *government* sources of the regulatory + clinical guideline corpus; the sovereignty filter explicitly clears them as T1.
- Multi-VM HA Vexxhost topology (Phase-2).
- Vault-based secret rotation (Phase-2).
- Editing the codex_diff_audit_iter_*.txt files (they are review output, not operator surfaces).

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
