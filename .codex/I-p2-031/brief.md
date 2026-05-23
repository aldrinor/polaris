# Codex DESIGN+DIFF review — I-p2-031 (#770): Source Review / Source-Set Health

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `f0a48d8c7fe71637a034b083c5ff84dd3d45bc4006956fca2e1795c586211588`. web/ only, 2 files. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## 200-LOC cap exemption (please validate)
~304 patch lines; ~280 are the single new file `web/app/source_review/page.tsx` (one atomic new page), the rest a small intake-link rewire. Consistent with prior Phase-2 page builds (#759, #761). If you judge the size a real review risk, say so.

## Context
#770 = "Source Review / Source-Set Health", a NEW flow step BETWEEN intake and plan (intake → source_review → plan → run). Per the UX-standard Codex finding (P1-3): the winning flow is intake → review/approve sources → plan → run; add an explicit source-set-health state "so scope can't be buried." This page surfaces, BEFORE the run, the curated source set POLARIS will search for the chosen template + the per-tier adequacy bar the corpus must clear.

## Data source (LAW II — VERIFIED-live, not assumed)
`listTemplates()` → `GET /api/v6/templates`, served from the authoritative `config/v6_templates/*.json`. I VERIFIED this is real before building:
- `curl https://polarisresearch.ca/api/v6/templates` → `401 {"error":"missing_bearer_token"}` (a real auth-gated endpoint — a 404 would mean it doesn't exist). It runs authenticated in-browser (the page is behind auth).
- Read `config/v6_templates/clinical.json` directly: real `source_tiers` (T1: Health Canada, FDA, EMA, ClinicalTrials.gov, PubMed; T2: Cochrane, BMJ, JAMA, Lancet; T3: Medscape, StatNews) + real `min_sources_per_tier` {T1:3, T2:2, T3:0} + 5 frames. NO fabrication.

**Deliberately NOT used (would risk LAW II):** `runRetrieval` (a real pre-run corpus preview) is used by NO production page — only the dev `/retrieval` harness — and triggers actual retrieval (cost/heavy); `getAuditRun` (post-run gates) is frontend-unused + unverifiable offline (same call I deferred on #759). So the page shows the source-set DEFINITION + the adequacy bar, NOT a retrieved corpus.

## Honesty (LAW II)
The page does NOT fabricate a retrieved corpus, a "readiness %", or "estimated N sources". It states plainly (the "How sources are gathered" callout): the actual corpus is retrieved + adequacy-checked DURING the run, which aborts at the adequacy gate if any tier falls below its minimum — "scope is enforced, not assumed."

## Diff (2 files)
1. `web/app/source_review/page.tsx` (NEW): in-shell page (snake_case route folder, matches /pin_replay /audit_live). Suspense + useSearchParams (q + template; template defaults to "clinical" via the same allow-list as plan). On mount: `listTemplates()` → find the chosen template → render. Sections: question display, per-tier cards (T1 = Canada-red `bg-tier-1` dot, T2/T3 neutral; domains + min-required badge), frame-manifest chips, honest "how sources are gathered" callout, "Continue to plan review →" → `/plan?q=&template=`. #750 LoadingState/ErrorState for the fetch (offline harness → ErrorState; verified-content screenshot taken with a page.route intercept serving the REAL config json).
2. `web/app/intake/components/intake_form.tsx`: the in-scope continue link rewired from `/plan?q=` → `/source_review?q=` ("Review sources →"), inserting the new step. testid `intake-continue-to-plan` kept.

## Files I have ALSO checked and they're clean
- `grep` for `intake-continue-to-plan` / "Continue to plan" / `/source_review` / `source-review-page` across tests + scripts: NO staled consumer (no test asserts the old link text/href).
- `listTemplates` + `TemplateContent` (source_tiers, min_sources_per_tier, frame_manifest) field names exact (api.ts:395-411).
- Tier tokens `bg-tier-1`(#c8102e Canada-red)/`bg-tier-2`/`bg-tier-3` confirmed in globals.css.
- `/source_review` correctly NOT in PRIMARY_NAV (nav.ts) — it's a flow step like `/plan`, not top-nav. In-shell (not in app_shell_gate CHROMELESS).

## Claude visual audit (standalone @1366, REAL config data via page.route intercept)
In-shell (POLARIS·Canada nav + Canadian-hosted badge). Renders: "Review the source set" + the question + Template: clinical; three tier cards with the REAL domains (Health Canada/FDA/EMA/ClinicalTrials.gov/PubMed · Cochrane/BMJ/JAMA/Lancet · Medscape/StatNews) + MIN 3/MIN 2/NO MINIMUM badges; frame chips (Efficacy outcomes, Safety/adverse events, Regulatory labelling deltas, Post-market surveillance, Subgroup analyses); honest "how sources are gathered" callout; red "Continue to plan review →" CTA.

## Review focus (16-dim design rubric + diff)
1. Honesty: does the page avoid implying a corpus has been retrieved? Is the "definition + adequacy bar, retrieved during run" framing unambiguous?
2. LAW II: is building on `listTemplates` (verified-live endpoint + real config) defensible, given runRetrieval/getAuditRun were correctly deferred?
3. Flow: intake → source_review → plan wired cleanly (params preserved; no staled test)?
4. Design dims: hierarchy, the tier-card density, token use (tier-1 = national red OK here as a tier signal?), a11y (tier dots aria-hidden + text labels; in-shell single landmark), responsive (3-col → 1-col).
5. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
