HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-008 diff iter 2 — sovereign pivot, P1 fixes applied

## Iter-1 verdict recap

Iter 1 returned `verdict: REQUEST_CHANGES` with 4 P1 + 4 P2 + 4 P3 cosmetic findings. All P1 + the relevant P2 are addressed in commit `4f9a5ed4`. Cumulative diff at `.codex/I-carney-008/codex_diff.patch` (1124 LOC, 28 files). Incremental delta since iter-1 at `.codex/I-carney-008/codex_diff_iter_2.patch` (388 LOC, 8 files).

## P1 fix table (iter-1 → iter-2)

### P1-1 — Brave Software is Delaware corp (US) ✅ RESOLVED

**Iter-1 finding:** Brave Search API fails the "no US company anywhere" bar. `api.search.brave.com` cannot remain in the sovereign allowlist; docs claiming Brave is Czech-owned are factually incorrect.

**Iter-2 fix (4f9a5ed4):**

- `config/egress_allowlist.txt:15-22` — Brave entry removed. New comment line 18-22 documents that search-provider selection is deferred to GH#487 I-carney-009.
- `docs/carney_demo_runbook.md:13` — stack table row updated: "Live search | DEFERRED to GH#487 (Mojeek UK / Qwant FR / Ecosia DE candidates) | Non-US — Codex iter-1 caught Brave Software is Delaware-incorporated"
- `docs/carney_demo_runbook.md:31` — §0 prereqs row updated: "Non-US web search API key (see GH#487 — Mojeek UK / Qwant FR / Ecosia DE)"
- `docs/transparency.md:60-62` — egress allowlist prose now omits Brave; new paragraph documents that the search provider is deferred and Serper calls fail loudly under lockdown
- `infra/vexxhost/README.md:7,21,123` — Search row updated; sovereignty audit table row for live search updated to "DEFERRED to GH#487; Codex iter-1 caught Brave Software Inc. is Delaware-incorporated"
- `infra/vexxhost/.env.example:18-26` — `BRAVE_SEARCH_API_KEY` removed; `SERPER_API_KEY` retained as transitional fallback with comment that lockdown will drop it
- GH#487 title + body updated via gh CLI to remove Brave; candidate list now Mojeek/Qwant/Ecosia/Startpage

### P1-2 — Transparency endpoint surfaced empty provider/region ✅ RESOLVED

**Iter-1 finding:** `infra/vexxhost/.env.example` had no `POLARIS_PROVIDER` or `POLARIS_REGION`, set blank `AWS_REGION`. `transparency.py` would return `provider="unknown"` and `region=""`. Docs also referenced a fabricated `provider_jurisdiction: US` field that doesn't exist in the schema.

**Iter-2 fix (4f9a5ed4):**

- `infra/vexxhost/.env.example:29-31` — explicit `POLARIS_PROVIDER=vexxhost` + `POLARIS_REGION=montreal-qc` added under a new `# ---- Sovereign deploy provenance ----` section. Blank `AWS_REGION=` line removed (compat fallback still works at code-level if AWS_REGION is in the operator's env).
- `src/polaris_v6/api/transparency.py:188-198` — empty-string env vars now treated as missing:
  ```python
  provider = os.environ.get("POLARIS_PROVIDER", "").strip() or "unknown"
  region = (
      os.environ.get("POLARIS_REGION", "").strip()
      or os.environ.get("AWS_REGION", "").strip()
      or "unknown"
  )
  ```
- `docs/carney_demo_runbook.md:36` — fabricated `provider_jurisdiction: US` reference removed. New language: "/transparency surfaces this backend so reviewers see the US disclosure during the transition."

### P1-3 — POLARIS_LLM_BACKEND=vllm defaulted to a not-yet-built client ✅ RESOLVED

**Iter-1 finding:** Setting `POLARIS_LLM_BACKEND=vllm` in the template breaks generation because the vLLM client lives in GH#199 I-sov-001 which hasn't shipped.

**Iter-2 fix (4f9a5ed4):**

- `infra/vexxhost/.env.example:6-15` — default changed to `POLARIS_LLM_BACKEND=openrouter`. New comment block explicitly states the dual prereq (OVH H200 online AND GH#199 client shipped) before flipping to vllm.
- `docs/carney_demo_runbook.md:36` — `.env.example` default-flip prose aligned: "Flip to POLARIS_LLM_BACKEND=vllm + restart compose once (a) the OVH H200 is online with a reachable private IP, AND (b) GH#199 I-sov-001 has shipped the vLLM client code. Setting the flag without both prereqs will break generation."

### P1-4 — Mandatory egress lockdown blocked T1 evidence fetching ✅ RESOLVED

**Iter-1 finding:** Pipeline-A fetches doi.org, OpenAlex, Jina/archive, publishers — none in allowlist. With lockdown on, search would succeed but evidence body fetches would fail, dropping corpus below adequacy threshold.

**Iter-2 fix (4f9a5ed4):**

`config/egress_allowlist.txt` was expanded with the T1 corpus endpoints that pipeline-A actually fetches. Cross-referenced against `src/polaris_graph/retrieval/{evidence_selector,tier_classifier,domain_backends,frame_fetcher}.py`:

- **FDA + NIH (US govt):** `fda.gov`, `accessdata.fda.gov`, `nctr-crs.fda.gov`, `clinicaltrials.gov`, `ncbi.nlm.nih.gov`, `www.ncbi.nlm.nih.gov`, `pmc.ncbi.nlm.nih.gov`, `pubmed.ncbi.nlm.nih.gov`, `nlm.nih.gov`, `eutils.ncbi.nlm.nih.gov`
- **EMA:** `ema.europa.eu`, `europa.eu`
- **UK regulator:** `nice.org.uk`, `mhra.gov.uk`, `www.gov.uk`
- **Health Canada:** `canada.ca`, `www.canada.ca`, `hc-sc.gc.ca`, `recalls-rappels.canada.ca`, `health-products.canada.ca`, `hres.ca`, `pdf.hres.ca`, `cda-amc.ca`
- **WHO:** `who.int`, `iarc.who.int`
- **Bib/DOI infra:** `doi.org`, `dx.doi.org`, `api.crossref.org` (UK non-profit), `api.unpaywall.org`, `api.openalex.org`, `arxiv.org`, `export.arxiv.org`, `efts.sec.gov`, `www.sec.gov`

**Sovereignty alignment honest disclosure:** The audit-grade demo material is T1-only by the sovereignty filter design. T2/T3 arbitrary publisher domains (nature.com, nejm.org, thelancet.com, springer.com, etc.) are NOT in the allowlist — they're excluded by sovereignty filter AND by egress. Defense in depth, not contradiction.

This is documented in `docs/transparency.md:71-73`:

> Pipeline-A's sovereignty filter accepts only T1 (regulatory + clinical guideline) sources by default. The allowlist covers those T1 corpus hosts + the bib/DOI resolution infrastructure needed to attach them to cites. Arbitrary publisher domains (nature.com, nejm.org, thelancet.com, etc.) are NOT in the allowlist — they're T2/T3 and excluded by the sovereignty filter anyway; the egress drop is defense-in-depth.

## P2 fixes addressed

- **P2-3** (`git rev-parse polaris` inside ssh expanded on remote host): `docs/carney_demo_runbook.md §1` rewritten — resolve `POLARIS_REPO_COMMIT` + `POLARIS_DOMAIN` + `POLARIS_ACME_EMAIL` LOCALLY first, pass through ssh env explicitly in the form `ssh root@${POLARIS_DOMAIN} "POLARIS_REPO_COMMIT=${POLARIS_REPO_COMMIT} ... bash /root/provision.sh"`.
- **P2-4** (provision.sh health-loop did not fail on exhaustion): `infra/vexxhost/provision.sh:133-152` — added `healthy=0` flag, set to 1 on success, after the loop check `if [ "$healthy" -ne 1 ]; then` dumps `docker compose logs --tail=50` and `exit 1`.
- **P2-1** (POLARIS_REGION-over-AWS_REGION empty-string handling) — combined with P1-2 fix above.
- **P2-2** (provision.sh acceptable as-is per iter-1; no change).

## P3 fixes addressed

- `scripts/egress_lockdown.sh:64-66` — comment "AWS instance metadata" renamed to "link-local cloud metadata (169.254.169.254 — used by OpenStack on Vexxhost; AWS EC2 used the same address)".
- Dropping the "AWS Security Group" enforcement_layer entry was already approved in iter-1; no change in iter-2.
- Offline GPG secret bundle (§5 fallback) was approved in iter-1; no change.
- Brave rate-limit wiring is moot now (Brave removed).

## Direct questions iter 2

1. **P1-1 resolution.** Brave removed from allowlist + docs + .env template. Search provider deferred to GH#487 with explicit candidates (Mojeek/Qwant/Ecosia). Under lockdown, Serper calls fail loudly until GH#487 ships. Is the deferral pattern APPROVE'd?
2. **P1-4 allowlist expansion.** New allowlist includes US-govt endpoints (FDA, NCBI, clinicaltrials.gov, SEC EDGAR) — these are US *government* sources, distinct from US companies, and they ARE the regulatory + clinical guideline corpus pipeline-A's sovereignty filter explicitly clears (T1). The user directive "no US company anywhere" is interpreted as "no US private corp"; US govt sources of regulatory law are sovereign-aligned by their nature (FDA labels, ClinicalTrials.gov records). Is this interpretation APPROVE'd, or must we additionally annotate the allowlist with "US govt, not US company" inline?
3. **doi.org + Crossref + Unpaywall + OpenAlex + arXiv listed in transparency.md.** doi.org is CNRI (US non-profit), Crossref is UK non-profit, Unpaywall + OpenAlex are Our Research (US non-profit), arXiv is Cornell (US). All disclosed in transparency.md §4. Is the disclosure pattern APPROVE'd?
4. **transparency.py empty-string fix.** New behavior: `POLARIS_PROVIDER="" → "unknown"`; `POLARIS_REGION="" → fallback AWS_REGION="" → "unknown"`. Tests cover both new behavior and AWS_REGION compat path. 8/8 pass. APPROVE'd?
5. **Anything else blocking iter-2 APPROVE?**

## What this PR explicitly does NOT do (so you don't flag them as missing)

- Code-side Serper → non-US-provider swap (deferred to GH#487 I-carney-009).
- Code-side OpenRouter → vLLM swap (deferred to GH#199 I-sov-001).
- Removing the US govt T1 endpoints from the allowlist (these are sovereign-aligned regulatory corpus; their removal would gut audit-grade evidence at demo time).
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
