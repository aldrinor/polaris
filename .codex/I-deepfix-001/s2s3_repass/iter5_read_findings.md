# S2+S3 re-pass — iter 5 — fresh run + context-level read

base_commit d3864eaf; branch bot/sec-sec... (local); HEAD iter-4 fix 2021ccf confirmed committed.

## Run (HEAD code, non-starved)
- S2: real mirror LLM, 999 sources in -> 728 kept, 271 whole-dropped (chrome captcha shells + off-topic). cp2': outputs/s2s3_repass/iter5/s2/cp2_corpus_snapshot.json
- S3: GPU0, PG_CONSOLIDATION_NLI_WALL_SECONDS=2400, PG_FINDING_DEDUP_NLI_WALL_SECONDS=2400.
  cp3': outputs/s2s3_repass/iter5/s3/cp3_basket_snapshot.json
- nli_score_stats: total_pairs 39903, scored_pairs 39903, scored_fraction 1.0, judge_blind false, degraded false, truncated false. NON-STARVED (run2 earlier was 0/130 scored = blind). The never-starve fix WORKS when given wall+free GPU.

## Counts (context-level read, fail-open)
- baskets 335 (was 581). multi-member 44, singletons 291.
- Eloundou 8 -> 3 baskets: [15% tasks] m=4 corr=1 (4 mirrors repec/semanticscholar/stanford/ar5iv collapsed to 1 work); [46% jobs] m=2 (the two byte-identical iter-3 singletons MERGED via rep-invariant); [beta-metric] anthropic derivative m=1. The 3 are DISTINCT claims -> arguably correct at claim level.
- corroboration = distinct works: MECHANISM WORKS (m=4 -> corr=1). One residual over-count: [46% jobs] corr=2 = canonical eloundou_gpts_are_gpts + governance.ai-hosted copy of the SAME paper (should be 1).
- chrome residual ~14: license/masthead/nav/quiz boilerplate (CC-BY lines, 'Published by Informa UK', 'make sure you are on a federal government site', EBSCO nav cards, CliffsNotes quiz). NOT captcha shells (those removed at S2).
- off-topic residual ~20 CONFIRMED whole-source (titles verified): Cost-Benefit-Analysis Wikipedia (ev_678), Decomposing Climate Risks in Stock Markets WP/23/141 (ev_1078), Finance Growth and Inequality WP/21/164 (ev_564), Sierra Leone education finance (ev_1211/1067), Later school start times RAND (ev_695), Information Frictions in Real Estate Markets (ev_1064), interest-groups public opinion (ev_842), murine stress model (ev_1189), literature-review-checklist methodology (ev_1121), Financial Analysts Journal portfolio theory (ev_556). These slipped past S2 topic gate -> iter-6 target.
- fragments: mirror-refetches collapsed; cross-source same-paper sentence fragments (Noy&Zhang ~6 baskets, Brynjolfsson-Li-Raymond ~4) partially remain (many are legitimately-different claims). Same-work axis 728 rows -> 636 works.

## Verdict
Strong improvement on every axis + non-starve judge proven. NOT clean: ~20 off-topic + ~14 chrome still leak, Eloundou is 3 not 1, one corroboration over-count. acceptance_met = false. iter-6 target = S2 topic-gate recall on the ~20 confirmed off-topic finance/education/climate/biology sources + boilerplate-fragment fold + governance.ai same-work link.
