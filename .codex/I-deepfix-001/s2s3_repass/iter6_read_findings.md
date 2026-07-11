# S2+S3 re-pass — iter 6 — fresh run + context-level read

base_commit d3864eaf; branch bot/sec-s2s3-repass; prior HEAD 9e2be01 (iter5) confirmed committed; this iter adds b72cbfd (disclosure) + this note.

## Fresh run (HEAD code, non-starved)
- S2: real mirror LLM, 999 sources -> 722 kept, 277 whole-dropped. cp2': outputs/s2s3_repass/iter6/s2/cp2_corpus_snapshot.json
- S3: GPU0, PG_CONSOLIDATION_NLI_WALL_SECONDS=2400, PG_FINDING_DEDUP_NLI_WALL_SECONDS=2400.
  cp3': outputs/s2s3_repass/iter6/s3/cp3_basket_snapshot.json
- nli_score_stats: total_pairs 30381, scored_pairs 30381, scored_fraction 1.0, judge_blind FALSE, degraded FALSE, truncated FALSE. NON-STARVED — judge saw every pair.

## Context-level read (fail-open, read the MEANING not a count)
- baskets 346 (was 581 original; iter5 335). corr distribution {1:343, 2:2, 3:1}.
- Eloundou 8 -> 3 baskets = 2 distinct claims (46% of jobs + 80% workforce exposure). The 46% claim is FALSE-SPLIT across #4 (eloundou_gpts_are_gpts, canonical seed) and #43 (ev_879, a governance.ai-hosted copy of the SAME paper) — byte-identical rep, should be ONE. #66 (ev_891 punku.ai) is the distinct 80% claim.
- corroboration_count = DISTINCT WORKS: CONFIRMED. Refetch triplets (ev_00X/ev_10XX/ev_11XX) collapse to m>=2 corr=1 throughout (m=4 nber.org corr=1; m=4 arxiv/stanford "15% of tasks" corr=1). Genuinely-distinct works give corr>=2: #128 corr=3 (mdpi+springer+squarespace citing the same TFP/GDP projection), #339 corr=2 (arxiv Eloundou-rubric paper + onlinedegree.com secondary).
- Fragments/refetch: 722 rows -> 617 same-work groups -> 409 visible basket-member ids. The same-paper fragment collapse WORKS. Residual: 3 same-claim byte-identical false-splits that did NOT merge (#4/#43 Eloundou; #52/#53 Brookings "0.8% decrease in the share of middle managers", both brookings.edu refetches). rep_invariant_merge_count=0 this run vs 2 in iter5 — nondeterministic NLI-edge gap.
- Chrome residual ~15 boilerplate REPS (was ~25): the basket is a REAL source but the chosen representative SENTENCE is boilerplate — #7 rtsa.eu masthead/ISSN, #257 "Published by Informa UK Limited, trading as Taylor & Francis Group.", #336 wustl "KW - artificial intelligence KW - generative AI ..." Scopus keyword dump, #292 ucla "Electronic copy available at: http://ssrn.com/abstract=...", #342 "Preprint Concept Paper This version is not peer-reviewed.", #107 cbsnews byline. Rep-SELECTION quality gap, not junk-source pollution.
- Off-topic residual ~12 baskets surface an off_subject-stamped source as their representative (was ~154 original, ~20 iter5): #64/#227 software testing, #108 social work, #250 Akron Law Review rankings, #263 regional demographics, #243 federal minimum wage, #309 hospital/medical-transcription employment, #279 content-marketing. 51 sources were topic-judge-stamped OFF_SUBJECT but KEPT (my new S2 disclosure: n_offsubject_stamped_kept=51); 39 of them were same-work-folded and never surface, 12 surface as singleton reps.

## Why the off-topic residual is NOT safely removable (the key iter-6 finding)
The OFF_TOPIC whole-drop is a deliberate TWO-KEY concurrence (topic-judge OFF_SUBJECT stamp + line-screen 100%-off_topic). Loosening it to OFF_SUBJECT-alone whole-drop was REJECTED: the single-pass topic judge FALSE-POSITIVES on credible on-topic sources. Proven on this corpus:
- ev_876 (Roosevelt Institute "The Good Life Agenda") explicitly discusses "Employers decide whether to use AI to augment labor, supervise performance, or eliminate roles entirely" — an ON-topic AI-labor source — yet was stamped OFF_SUBJECT. The two-key gate correctly KEEPS it (it has real prose, so line-screen does not 100%-drop). OFF_SUBJECT-alone whole-drop would DELETE it — a §-1.3.1 red-line violation (credible on-topic is NEVER deleted).
A garble/word-ratio whole-drop was ALSO rejected: it false-positives on real PDF-extracted prose (ev_901 spaced-letter abstract "W e i n v e s t i g...", ev_685 "Cost-Benefit Analysis and the Environment" 11k-char doc, ev_1146 EMA pharmacovigilance). So no mechanical deletion knob is safe; adding one to force the off-topic number down is the banned day-waster. The ~12 off-topic residual is the correct FAIL-OPEN floor; it is DEMOTED (weight-not-filter) and disclosed.

## iter-6 change (the only safe "build")
Additive §-1.3.1 fail-loud disclosure: S2 line_screen_summary now emits n_offsubject_stamped_kept (=51 this run), making the fail-open off-topic residual AUDITABLE instead of silent. NO deletion knob added. Commit b72cbfd.

## Remaining CLEAN targets for a future iter (no deletion risk)
1. Byte-identical rep / cross-host same-work merge (fixes #4/#43, #52/#53) — CONSOLIDATE principle, always correct. rep_invariant post-pass fired 0x this run; investigate its NLI-edge dependency so it is deterministic.
2. Rep-SELECTION boilerplate skip (masthead/ISSN/"Published by"/Scopus-KW/SSRN-cover/"not peer-reviewed") so a basket never surfaces a boilerplate sentence as its statement. Display quality, real source untouched.

## Verdict
Strong reproduction of iter5's converged state on every axis, non-starved judge. NOT clean-zero: ~15 chrome reps + ~12 off-topic baskets + Eloundou 3-not-1 + 3 byte-identical false-splits. acceptance_met = FALSE. The off-topic residual is the correct fail-open floor (removal proven unsafe); the false-split + chrome-rep are the real remaining CLEAN targets.
