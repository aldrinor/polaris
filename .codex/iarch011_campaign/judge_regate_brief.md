HARD ITERATION CAP: 3. This is iter 2 of 3. Front-load all findings; verdict APPROVE iff zero P0 and zero P1.
3-PRONG: reject your own suggestion if it (1) relaxes faithfulness, (2) grandfathers, (3) adds a cap/floor/throttle. (A stricter fail-closed parser is pro-faithfulness, not a neck-choke.)

STATIC review (do NOT run pytest) of C:/POLARIS/.codex/iarch011_campaign/judge_iter2.patch — the iter-2 fix for B12/B14/B01.

ITER-1 P1 you raised (CORRECT, accepted): the extractor could salvage an inner verdict object out of a MALFORMED outer envelope (raw_decode fails at the outer `{`, then it advanced one char into the interior and decoded the nested verdict) -> malformed/partial content became an accepted verdict (fail-closed -> fail-open).
ITER-2 FIX to verify (BOTH judges, entailment_judge.py + semantic_conflict_detector.py): on `raw_decode` JSONDecodeError the extractor now RAISES (fail-closed) instead of `search_from = start + 1; continue` — so it never descends into a failed object's interior. A COMPLETE leading non-verdict object is still skipped by its end offset on the success path (the garbled-200 + skip-leading-scratchpad cases still work). New regression cases assert a malformed outer envelope with a nested verdict object RAISES (`malformed_outer_nested_verdict`, `malformed_outer_array_nested_verdict`).

VERIFY: (1) malformed/partial/truncated content now fails closed in BOTH judges; (2) the legitimate garbled-200 (valid object + trailing text) and skip-leading-complete-non-verdict-object cases still parse; (3) no new fail-open path. Output schema; final line `verdict: APPROVE|REQUEST_CHANGES`.
