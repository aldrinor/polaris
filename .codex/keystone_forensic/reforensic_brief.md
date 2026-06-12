# RE-FORENSIC (round 2) — keystone citation-fix WORKED structurally; now RECALL is too low

The #1217 fix (REDUCE emits short [ev_XXX] markers, deterministic span re-fit) WORKED: the distiller now produces strict_verify-VERIFIED cited prose (was 0; now drop_rate 0.00 on what it writes). Two jobs: (1) §-1.1 verify the kept sentence is faithful; (2) find why RECALL is low and the ONE fix to raise distill verified >= legacy WITHOUT weakening strict_verify.

## THE NEW FACTS (cheap 8-source smoke, drb_76 Safety section, deepseek-v4-pro)
- distill: 1 verified, drop_rate 0.00, 7 body words. LEGACY: 6 verified, drop_rate 0.45, 154 words.
- ALL 8 MAP calls PRODUCED findings (output tokens 292/335/439/454/536/608/4407/4612 — none empty/no_relevant).
- BUT the VALIDATED findings ledger had only **1 finding** (DISTILL_DEBUG: "ledger=1 findings"). So `_validate_finding` REJECTED ~7 of 8 sources' findings.
- The 1 kept distill sentence: "Colibactin induces double-strand breaks in cultured cells [colibactin_pks_ecoli_mechanism]." (verified.)

## §-1.1 (job 1): is the kept distill sentence faithful?
Claim-by-claim vs the cited source span. distill output: .codex/keystone_forensic/distill_smoke.txt; legacy output: .codex/keystone_forensic/legacy_smoke.txt. Confirm ZERO fabrication in the distill arm.

## RECALL (job 2): why does _validate_finding reject ~7/8 findings the MAP produced?
After the prior fixes, the remaining HARD rejectors in `_validate_finding` (evidence_distiller.py ~470-595) are:
- step 1 `_locate_span_in_source`: exact -> stripped -> whitespace-flexible regex of the SAME tokens. A finding whose support_quote the MAP model PARAPHRASED (changed words, not just whitespace) is unlocatable -> rejected.
- step 4 `_all_numbers_in_span`: EVERY number in the claim must appear in the (located) support_quote span. A claim with a number not in its own narrow support_quote -> rejected.
- (step 6 entailment is now NON-BLOCKING; step 5 atom-map is KEEP.)
INVESTIGATE which dominates. Compare: legacy gets 6 verified from the SAME 8 sources because the writer composes over the raw quotes + `_find_best_span_for_sentence` re-fits a prose span. The distiller's MAP emits a NARROW support_quote per finding; if the model's support_quote doesn't EXACTLY contain the claim's words/numbers, step 1 or 4 kills it.

## THE QUESTION
What is the ONE change to raise distill recall to >= legacy WITHOUT weakening strict_verify (which stays the SOLE authority on the FINAL prose)? Candidates to rule between:
(a) The MAP support_quote is too NARROW — instruct the MAP to return a WIDER quote (the full sentence containing the claim), so step-1/step-4 locate succeeds and the REDUCE has more to cite.
(b) step 4 `_all_numbers_in_span` is too strict at the EXTRACTION stage (it's redundant with the final strict_verify) — relax it to non-blocking like step 6, since strict_verify re-checks numbers on the final prose.
(c) step 1 should fall back to a fuzzy/best-overlap locate (reuse the I-perm-004 span_resolver) instead of rejecting.
(d) the MAP prompt should emit MULTIPLE findings per source (legacy writes 6 sentences from 8 sources; the MAP may be emitting 1 atomic finding per source then losing it).
Give the single highest-recall-leverage change, faithfulness-safe (final strict_verify unweakened), with file:line.
