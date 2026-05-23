# Claude architect audit — I-p2-031 (#770): Source Review / Source-Set Health

## Scope
New flow step BETWEEN intake and plan (intake → source_review → plan → run),
per the UX-standard Codex finding (P1-3): add an explicit source-set-health
state "so scope can't be buried." New in-shell page `/source_review`. 2 files.

## What it shows (real, verified-live data)
For the chosen template: the curated source tiers POLARIS will search (T1
primary/regulatory, T2 peer-reviewed/guidelines, T3 reputable secondary) with
the real domains, the per-tier minimum-sources adequacy bar, and the frame
manifest ("what the brief will cover"). Plus the question (display) and an
honest "how sources are gathered" callout.

## LAW II — verified-live, not assumed
`listTemplates()` → `GET /api/v6/templates`, served from `config/v6_templates/*.json`.
Before building I VERIFIED:
- `curl https://polarisresearch.ca/api/v6/templates` → `401 missing_bearer_token`
  (a real auth-gated endpoint; 404 would mean it doesn't exist). The page runs
  authenticated in-browser.
- `config/v6_templates/clinical.json` read directly: real `source_tiers` (T1:
  Health Canada, FDA, EMA, ClinicalTrials.gov, PubMed; T2: Cochrane, BMJ, JAMA,
  Lancet; T3: Medscape, StatNews) + real `min_sources_per_tier` {T1:3,T2:2,T3:0}
  + 5 frames. NO fabricated fields.

**Deliberately deferred (LAW II):** `runRetrieval` (real pre-run corpus preview)
is used by no production page + triggers heavy actual retrieval; `getAuditRun`
(post-run gates) is frontend-unused + unverifiable offline (same call deferred
on #759). So the page shows the source-set DEFINITION + adequacy bar, NOT a
retrieved corpus.

## Honesty
No fabricated corpus, no "readiness %", no "estimated N sources". The "how
sources are gathered" callout states plainly the actual corpus is retrieved +
adequacy-checked DURING the run (aborts at the adequacy gate if a tier falls
short). The page is a scope/source-set REVIEW, not a retrieval result.

## Staled-consumer / adjacency scan
- `grep` for `intake-continue-to-plan` / "Continue to plan" / `/source_review` /
  `source-review-page` across tests + scripts: NO staled consumer. The intake
  link rewire (text + href) breaks no test.
- `listTemplates`/`TemplateContent` field names exact (api.ts:395-411).
- Tier tokens `bg-tier-1`(#c8102e)/`bg-tier-2`/`bg-tier-3` confirmed in globals.css.
- `/source_review` correctly NOT in PRIMARY_NAV (flow step like `/plan`),
  in-shell (not chromeless).

## Visual verification
Standalone @1366 with a page.route intercept serving the REAL config JSON (the
same data the live endpoint serves): renders the three tier cards with real
domains + MIN-3/MIN-2/NO-MINIMUM badges, frame chips, honest callout, red
"Continue to plan review →" CTA, in-shell nav. typecheck + lint(0 err) + build
all green. (Live VM verification follows post-merge redeploy.)

## Codex verdict + the one P2
Codex DESIGN+DIFF: **APPROVE at iter 1**, zero P0/P1, MERGE AUTHORIZED.
One P2 (non-blocking, forward-looking): the intake→source_review link doesn't
preserve a `template` param. Today intake carries NO template param (you arrive
fresh or with `?q`), so there's nothing to drop — this is purely a future
consideration for when non-clinical templates become user-selectable at intake.
Not fixed here to avoid scope creep (per "don't pick bone from egg"); captured
as a known follow-up for the template-selection work.
