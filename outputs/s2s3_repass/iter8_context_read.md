# S2/S3 re-pass iter 8 — fresh run + context-level read (Opus, on polaris-core)

Fresh run of current HEAD (iter-7 fix 7b72d41) on the REAL drb_72 corpus (999 sources).

## Results
- S2: 999 in -> 539 kept, 460 whole-dropped (off-topic/junk), 1842 off-topic lines + 522 junk lines dropped; 48 off-subject stamped-but-kept (fail-open residual).
- S3: 247 baskets (was 581). 30 multi-member, 46 same-work multi-member groups, nli scored_fraction=1.0 (judge NOT blind), 1 chrome DELETED with disclosure (ev_447 researchgate 'Just a moment...' captcha).

## Context-level read (all 247 baskets read)
- basket_count = 247 (was 581).
- chrome_remaining ~2 residual in baskets: B185 enago.com editing-service nav/AI-disclaimer, B187 doi.org jstpm journal email-alert chrome. (+1 chrome deleted w/ disclosure). Was ~25.
- offtopic_remaining ~10 confident single-member baskets: cost-benefit-analysis Wikipedia, quant-finance papers (Quant GANs), cliffsnotes assistive-tech quiz, law-review rankings, social-work Texas population, education/student-loan, chemistry-textbook study, quant-finance reading list, attorney ad, HR resume example. Was ~154.
- corroboration_count = DISTINCT WORKS: TRUE. B000 four NBER w31161 URLs -> corrob=1; B005 three arxiv 2303.10130 mirrors -> corrob=1; B023 Noy_Zhang two filenames -> corrob=1. Refetch triplets collapse. (minor edge over-counts: empty-url member, paper+SM.)
- Eloundou 'GPTs are GPTs': folded into ONE same-work group (wharton+openai+worldbank+nyfed mirrors collapsed), correctly SPANS ~5 claim baskets for DISTINCT claims (15% B005/B054, 46% B016, 47-56% B055, rubric B050). The same-15%-claim fragmentation dropped 8 -> 2.

## Residual defects still needing work
1. SSRN same-work OVER-MERGE (§-1.3): swid id:ssrn:4375283 folds 6 DISTINCT papers (4375283 Noy-Zhang, 5136877 Bick-Blandin-Deming survey, 4414065, 4527336, 5316265) into one work. Claim baskets stay separate, but the distinct-works annotation is wrong.
2. Exact-duplicate basket B134/B135: ev_190 + ev_1058, identical URL (squarespace Projected-Impact PDF) + identical claim + identical claim_group_id -> two baskets not merged (byte-identical union miss).
3. ~10 off-topic single-member baskets leak (S2 topic-judge fail-open residual, offsubject_stamped_kept=48).
4. Eloundou 15% claim still in 2 baskets (B005 + B054).
