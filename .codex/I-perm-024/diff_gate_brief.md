# Codex DIFF gate — I-perm-024 (#1216): beat-both scorer metric extension

HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (the cap).

## ITER-5 CHANGES — fundamentally robust over-merge fix (your iter-4 P1 + P2)
You showed `CD4+`/`CD4-`, `pks+`/`pks-`, `IL-1α`/`IL-1β` still merged because the token regex
drops sign suffixes + Greek. Rather than patch each notation, the swap guard now PRESERVES every
distinguishing character:
- `_subject_tokens` is rewritten: split on WHITESPACE, lowercase, strip ONLY surrounding
  sentence/grouping punctuation (`_SUBJECT_EDGE_STRIP`), keep the token BODY VERBATIM. So `cd4+`
  ≠ `cd4-`, `il-1α` ≠ `il-1β`, `pks+` ≠ `pks-`, `her2+` ≠ `her2-`, `il-6` ≠ `il-10`, `sglt2` ≠
  `dpp4`, `zn` ≠ `cu`. Any two DISTINCT entity strings differ in ≥1 preserved char → mutual
  swap → BLOCK. This cannot lose a distinguishing character that survives whitespace-splitting +
  edge-punctuation-stripping, so it is robust to the whole notation class (not another patch).
- Legitimate merges preserved: reorder-restatements (identical subject sets → no swap) and the
  dietary-fiber elaboration (subset on one side → no swap) still merge.
- iter-4 P2: `PG_BENCH_EXTENDED_METRICS` added to `_BENCHMARK_FORCE_ON_FLAGS` so a nonstandard
  operator value (e.g. "2") is force-set to "1" in the broad run (no setdefault drift).
New test `test_dedup_blocks_sign_and_greek_entity_swaps` covers CD4+/CD4-, pks+/pks-,
IL-1α/IL-1β, HER2+/HER2-, ER+/ER- (all → 2 clusters). 28 #1216 tests + 36 existing pass.

NOTE on the cap: this is iter 5. If you find a residual same-class P1, please say so plainly —
per CLAUDE.md §8.3.1 the doc is force-APPROVE'd at the cap and the residual becomes a follow-up
issue; but I believe the character-preserving subject tokenization closes the class.

---

HARD ITERATION CAP (iter-4 header, superseded above): 5 per document. This is iter 4 of 5.

## ITER-4 CHANGE — ROBUST whole-class fix for entity over-merge (your iter-3 P1)
iter-1/2/3 patched the over-merge class piecemeal (semaglutide/liraglutide → alpha; SGLT2/DPP4
→ alphanumeric; IL-6/TNF, IL-6/IL-10 → you showed `IL-6` tokenized to just `{6}` because the
hyphen split it and `il` was dropped). Replaced the patches with a ROBUST design:
- `_TOKEN_RE` now PRESERVES internal hyphens/slashes: `[a-z0-9]+(?:[-/][a-z0-9]+)*` → `IL-6`,
  `IL-10`, `CD4/CD8` are ONE token each (not split into a dropped `il` + a bare digit).
- NEW `_subject_tokens(text)`: the swap guard runs over EVERY letter-bearing, non-stopword
  token with NO length floor — so short clinical entities the content-token length≥3 filter
  drops are still seen: `Zn`/`Cu`/`Mg`/`Fe` metal ions, `IL-6`/`IL-10`/`TNF` cytokines,
  `SGLT2`/`DPP4` drug classes, `CD4`/`CD8`. Any two DISTINCT subjects → mutual swap → BLOCK.
- `_substantive_token_swap` now takes pre-extracted subject sets (plain mutual-non-empty).
- Jaccard still runs over the noise-reduced content tokens (length≥3).
- Being maximally inclusive for the swap guard only makes the dedup MORE conservative
  (under-merge = §-1.1-safe; the cost is a synonym-paraphrase not merging, never a distinct
  fact merging).
New test `test_dedup_blocks_hyphenated_and_short_entity_swaps` covers IL-6/TNF, IL-6/IL-10,
Zn/Cu, Mg/Fe, CD4/CD8 (all → 2 clusters). 27 #1216 tests + 36 existing scorer tests pass;
the legitimate-merge cases (reorder restatements, dietary-fiber elaboration) still merge.

---

HARD ITERATION CAP (iter-3 header, superseded above): 5 per document. This is iter 3 of 5.

## ITER-3 CHANGE (your iter-2 continuing P1 — alphanumeric entity swap)
You showed `t.isalpha()` missed alphanumeric biomedical tokens (SGLT2/DPP4, IL6/TNF,
PCSK9/DPP4), so distinct drug-class claims with matching numerics still merged. FIXED:
`_substantive_token_swap` now treats a "subject token" as ANY token CONTAINING a letter
(`any(c.isalpha() for c in t)`), so `sglt2`/`dpp4` trigger the mutual-swap block. Pure-digit
tokens stay excluded (numeric differences are the signature-conflict guard's job).
New tests: `test_dedup_blocks_alphanumeric_entity_swap` (SGLT2/DPP4, IL6/TNF, PCSK9/DPP4 →
2 clusters each) + `test_alphanumeric_entity_swap_does_not_inflate_citation_rate`
(citation_support_rate stays 0.5). 62 scorer tests pass (26 #1216 + 36 existing).

---

HARD ITERATION CAP (iter-2 header, superseded above): 5 per document. This is iter 2 of 5.

## ITER-2 CHANGES (addressing your iter-1 P1 + P2; re-read the patch)

- **iter-1 P1 (over-merge of distinct same-template facts differing only by entity) —
  FIXED.** New `claim_dedup._substantive_token_swap(a, b)`: two claims may merge only if
  they do NOT have a MUTUAL alphabetic-content-token swap. "semaglutide ... 20 percent" vs
  "liraglutide ... 20 percent" → a_only={semaglutide}, b_only={liraglutide}, both alpha →
  SWAP → blocked, even at Jaccard ≥ 0.80 with matching numerics. A pure elaboration
  ("fiber" vs "dietary fiber") has extras on ONE side only (subset, not swap) → still
  merges. Wired into `dedup_claims` as a guard against ALL cluster members (not just rep),
  alongside the numeric-conflict guard. Tests:
  `test_dedup_blocks_entity_swap_with_matching_numbers` (2 clusters) +
  `test_entity_swap_does_not_inflate_citation_support_rate` (citation_support_rate stays
  1/2, NOT 1/1 — the exact inflation you flagged).
- **iter-1 P2 (safety_floor_recall silently shrinks denominator on registry/rubric
  mismatch) — FIXED.** Denominator is now the PRE-REGISTERED tagged count
  (`len(safety_element_ids)`), not the count present in the rubric. A tagged id missing
  from the supplied rubric is surfaced in `missing_from_rubric` AND counts against recall
  (fail-safe — a mismatch lowers recall + is visible, never a false-high). Test:
  `test_safety_floor_denominator_is_preregistered_count` (E7 absent → total 2, value 0.5,
  missing_from_rubric=[Q76-E7]).
- **Build:** 24 tests pass (was 21 + 3 new); 36 existing scorer tests still pass.

---

HARD ITERATION CAP (iter-1 header, superseded above): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## The diff to review
`.codex/I-perm-024/codex_diff.patch` (staged). 7 files, +746/-5. Read these EXACT files
(do NOT scan the whole repo — codex_* temp dirs are access-denied and crash exec):
- NEW `src/polaris_graph/benchmark/claim_dedup.py` (143) — Claimify-style claim-atom dedup.
- NEW `src/polaris_graph/benchmark/extended_metrics.py` (233) — the 5 metrics + ScoredClaim.
- NEW `config/dr_benchmark/safety_floor_elements_v3.json` (44) — pre-registered safety tags.
- NEW `tests/dr_benchmark/test_extended_metrics_iperm024.py` (252) — 20 tests.
- EDIT `src/polaris_graph/benchmark/benchmark_scorecard.py` (+10) — optional `extended` param.
- EDIT `scripts/dr_benchmark/run_scorecard.py` (+60) — extended path + env flag.
- EDIT `scripts/dr_benchmark/run_gate_b.py` (+9) — slate force-on.

The brief was APPROVED at `.codex/I-perm-024/codex_brief_verdict_iter2.txt` (read it for the
acceptance criteria + the iter-1 P1/P2 resolutions this diff implements).

## What it does (measurement-only; ZERO pipeline/gate change)
Extends the claim-audit scorecard with 5 claim-by-claim metrics (faithfulness_precision,
citation_support_rate, diversity_score, required_entity_recall, safety_floor_recall) +
Claimify dedup, behind the default-OFF `PG_BENCH_EXTENDED_METRICS` flag. It runs AFTER the
report exists, over the already-audited per-claim ledger (ClaimRows) + the frozen rubric. It
touches NO generator / strict_verify / 4-role / D8 / retrieval code.

## Red-team this against `.codex/codex_red_team_checklist.md`, focus:
1. **§-1.1 (clinical, the crux):** confirm every metric is derived from audited
   ClaimRows/RubricElements, NEVER from raw report text. `ScoredClaim.text` is used ONLY by
   `dedup_claims` (text clustering); no metric VALUE reads text. Is there any path where raw
   report string-presence leaks into a metric? (There must be none — that's the §-1.1 ban.)
2. **Bad-verdict-never-hidden (iter-1 P2):** `_verdict_aware_keep` collapses only repeated
   VERIFIED rows and keeps EVERY non-VERIFIED row. Verify a {VERIFIED, UNSUPPORTED}-same-fact
   cluster cannot drop the UNSUPPORTED. Any verdict that could be hidden?
3. **Dedup over-merge safety:** `_signatures_conflict` blocks merging claims with different
   decimals/years/dollars; merge requires ≥0.80 content Jaccard AND no numeric conflict. Can
   two DISTINCT facts (e.g. different drug, same %) wrongly merge and undercount?
4. **Byte-identical when off:** `build_scorecard(extended=None)` adds no key;
   `run_scorecard(extended=None)` reads env (unset→False). Confirm zero behavior change when
   the flag is off (the test asserts it; verify the code path).
5. **diversity_score is never a decision input:** confirm no comparator/PASS/aggregate path
   consumes it (test greps benchmark_scorecard.py + claim_audit_scorer.py for "diversity"=0).
6. **citation_support_rate floor:** a VERIFIED claim with citation_id=None is NOT counted as
   cited (traceability floor). Correct?
7. **Pre-registration honesty:** `safety_floor_elements_v3.json` tags only frozen-rubric
   element_ids that the rubric's own text justifies (quoted); non-clinical Q72/Q90 are empty
   (pending, not false-0). No invented claims. pinned to the JSON file sha 2a39d9dd….

## Honest caveats for you to weigh
- **Size:** +746 lines exceeds the 200-LOC soft cap, but it is ONE cohesive new measurement
  subsystem (2 modules + data + test) with NO change to any existing behavior path; 252 lines
  are tests, 44 are data. Splitting would be artificial. Flag if you disagree.
- **Paid proof:** the scorer is pure aggregation over a §-1.1 audit ledger; its metric VALUES
  need the operator-gated paid judge (the broad beat-both run), where the slate force-on
  archives the block. What is proven offline (cash-free): metric math, dedup, byte-identical,
  and that it runs end-to-end over the 10 REAL stored competitor reports (extended block
  well-formed; rubric metrics report `pending` until the paid audit supplies rubric coverage).
- Tests: 20 new pass; 36 existing scorer tests pass (no regression).
