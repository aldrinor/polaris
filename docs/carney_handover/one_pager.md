# POLARIS — Sovereign Canadian Deep Research

**Built for the Office of the Prime Minister · 2026**

---

## What POLARIS does

POLARIS is a deep research AI built sovereign to Canada. It produces evidence-graded research reports on policy questions in 8 domains spanning your government's seven officially-named priorities, plus clinical health research as a legacy template:

- Health Canada / FDA · USMCA / WTO · StatCan / CMHC · DND / NORAD · ECCC / NRCan · ISED / CIFAR · GAC / DFAIT · ESDC / IRCC

Every claim in every report ships with a **provenance token** that points to the exact span of the primary source it came from. Every report carries a **family-segregated** verifier (DeepSeek V4 generator + Gemma 4 31B verifier on different lineages) so neither model can certify its own output. Every report can be **replayed** to detect drift over time.

---

## Why it's different

| Capability | ChatGPT 5.5 Pro DR | Gemini 3.1 Pro DR | POLARIS v6 |
|---|---|---|---|
| Sovereign Canadian compute | ❌ US | ❌ US | ✅ OVH Beauharnois |
| Two-family verifier (lineage-segregated) | ❌ self-checks | ❌ self-checks | ✅ enforced at construction |
| Per-sentence provenance token to source span | partial | partial | ✅ every sentence |
| Click-to-evidence in browser | ❌ | ❌ | ✅ Inspector view |
| Frame coverage panel above-the-fold | ❌ | ❌ | ✅ |
| Refusal honesty (5 personal-advice patterns) | inconsistent | inconsistent | ✅ enforced + tested |
| Replay drift detection | ❌ | ❌ | ✅ Pin replay diff |
| Audit bundle export with embedded source spans | ❌ | ❌ | ✅ EvidenceContract v1.0 JSON |

---

## What you get on day one

- A URL: `https://polaris.gc.ca` (provisional — final domain assigned by your office)
- A login: SSO via your office's identity provider
- 8 templates pre-loaded with vetted Tier-1 sources for each domain
- The full POLARIS source code under Apache-2.0-style licensing, including:
  - Sovereign-Canadian inference cluster setup (OVH BHS H200, vLLM-served)
  - DeepSeek V4 weights (MIT)
  - Gemma 4 31B weights (Apache 2.0 + Gemma Use Policy — LOW severity, no government-use restriction)
  - All test suites, golden fixtures, and benchmark scoring code

---

## Honest limits

- **Scope.** POLARIS is a research-synthesis tool, not a personal-advice service. It refuses (with rationale) requests for individual clinical / legal / financial / political-endorsement advice. This is enforced in code, not just policy.
- **Data residency.** Cognition (LLM serving + uploaded documents + audit bundles) stays on Canadian infrastructure. Frontend CDN + observability dashboards may use US-based providers; no Canadian-resident data crosses the border for these.
- **Source coverage.** POLARIS draws from public-government, vetted-academic, and major-Canadian-media tiers. Paywalled sources are cited with DOI links, not redistributed verbatim, pending IP-counsel sign-off (under way).

---

## Handover support

- **First 30 days post-handover (2026-09-06 → 2026-10-06):** warm support from POLARIS build team. Bug reports answered same-day, no new feature commitments.
- **After 2026-10-06:** best-effort. Your office's team owns operational ownership thereafter (per `docs/blockers.md` §6).
- **Runbook:** `docs/runbook.md` (deployment, model rotation, evaluator-failure escalation).
- **Source code:** GitHub repo handed over; commit history is the audit trail.

---

## Three documents in this package

1. This one-pager (you are here).
2. `5min_video_script.md` — 5-minute walkthrough script + recording.
3. `bundle_export_sample.json` — a real EvidenceContract v1.0 audit bundle sampled from the launch run, so your team can inspect the artifact format without standing up the cluster.

---

*Built sovereign. Built honest. Built so every claim can be checked.*
