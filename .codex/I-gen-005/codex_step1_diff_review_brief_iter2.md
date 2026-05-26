# Codex iter 2 — Step 1 diff review (response to iter 1 P1 findings)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker,
  classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by
  Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" —
  DON'T. Surface it now. The 5-cap means iter 6 doesn't exist;
  banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What changed since iter 1

You returned `REQUEST_CHANGES` with 3 P1 findings and 1 P2 finding.
**All 3 P1 findings are now fixed.** The diff is in
`.codex/I-gen-005/codex_diff_iter2.patch` (436 lines, two files:
`src/polaris_graph/generator/provenance_generator.py` +
`scripts/test_i_gen_005_iter2_adversarial.py`).

### P1 #1 — Token-exact matching (your line 547 finding)

**Status: FIXED**

`_find_local_support_window()` was using `norm.find(d)` for placement
and `d in window_text` for validation. Both were substring matches, so
`50` matched inside `150`/`21.50` and positive `1.07` matched inside
`-1.07`.

**The fix** (provenance_generator.py:533-653):

- Walks `direct_quote` with a regex (`_DECIMAL_NUMBER_RE` for the
  decimal path, `_NUMBER_RE` for the integer path) using `finditer()`.
- For each match, requires `m.group(0) in needed_tokens` (full regex
  match, not substring).
- Validates inside the chosen window the SAME way:
  `window_tokens = {m.group(0) for m in token_regex.finditer(window_text)}`
  then `if not needed_tokens.issubset(window_tokens): continue`.
- Added `token_regex: Optional[Any] = None` parameter so the integer
  path at line 945 can pass `_NUMBER_RE` to keep tokenization
  consistent with how the caller built `needed_tokens`.

### P1 #2 — Range-dash safety (your line 484 finding)

**Status: FIXED**

`_normalize_unicode_minus()` was mapping U+2013/U+2014/U+2012 to
ASCII `-` unconditionally, so positive range `8.12–8.21` became
`8.12-8.21` and `_DECIMAL_NUMBER_RE` extracted fake negative `-8.21`.

**The fix** (provenance_generator.py:488-520):

```python
_RANGE_DASH_BETWEEN_DIGITS = _re_normalize.compile(
    r"(\d)([–—‒])(\s*\d)"
)
def _normalize_unicode_minus(text: str) -> str:
    if not text: return text
    # Step 1: range dashes between digits → space
    out = _RANGE_DASH_BETWEEN_DIGITS.sub(r"\1 \3", text)
    # Step 2: U+2212 always → ASCII minus (real minus sign)
    out = out.replace("−", "-")
    # Step 3: stray non-range dashes → ASCII '-' (rare narrative use)
    out = (out.replace("–", "-").replace("—", "-").replace("‒", "-"))
    return out
```

Range-dash regex requires a digit on the LEFT and (optional spaces +)
digit on the RIGHT, so it only fires when the dash is between numeric
content. Narrative em-dashes between words (`"—Tirzepatide—"`) are
still normalized to ASCII `-` for safety.

U+2212 MINUS SIGN is preserved as a real minus (always converted to
ASCII `-`, never replaced with space).

### P1 #3 — Whole-direct_quote entailment fallback (your line 975 finding)

**Status: FIXED**

The entailment fallback used to re-judge the sentence against
`combined_full = " ".join(aggregated_full_text)` — exactly the same
architectural shape as the rejected whole-document numeric fallback,
which you flagged as P1.

**The fix** (provenance_generator.py:1035-1122):

When the narrow-span judge returns `NEUTRAL/CONTRADICTED`:

1. Strip the sentence (dose patterns, placebo comparators, thresholds).
2. Compute `sentence_dec_local` + `sentence_content_local`.
3. For each cited token's evidence:
   - If sentence has decimals, call `_find_local_support_window()`
     with `min_content_overlap=2`, `window=400`.
   - If a window is recovered → judge against the **window text only**
     (`direct_quote[win[0]:win[1]]`).
   - Break on first qualifying window.
4. If no local window is found, **fail closed** (do NOT fall back to
   whole document). Use the original narrow-span verdict to add the
   `entailment_failed` failure.
5. If sentence has no decimals (pure semantic claim with no numeric
   anchor), there is no way to localize → fail closed via the
   `else` branch.

This closes the architectural symmetry you flagged: numeric AND
entailment both now use bounded local-window or fail.

### P2 #1 — Three-placement cluster issue (your line 562 finding)

**Status: FIXED (promoted from P2 to "addressed in iter 2 scope")**

You flagged that the three placements (start/middle/end around the
rarest anchor) might miss valid clusters where the anchor is in the
middle of an asymmetric cluster.

**The fix** (provenance_generator.py:594-651):

The new `_find_local_support_window` uses **cluster-based placement**:

- For each occurrence of the rarest token (anchor):
  - For each OTHER needed token, find the occurrence whose midpoint
    is closest to the anchor's midpoint.
  - Compute the cluster's `min_start` and `max_end`.
  - If `max_end - min_start <= window`, place a window covering the
    cluster with symmetric slack padding.
  - Re-validate token-exactness inside the chosen window.

Any cluster whose extent is within the window size is discovered.

## Adversarial test suite (run locally, all 12 assertions pass)

`scripts/test_i_gen_005_iter2_adversarial.py` — 12 assertions across
5 test groups. **Run yourself**:

```
PYTHONIOENCODING=utf-8 python scripts/test_i_gen_005_iter2_adversarial.py
```

### Test results

**TEST 1 — Token-exact (P1 #1) — 4/4 PASS:**
- `50` does NOT match inside `150`, `21.50`, `503`
- `503` DOES match (positive control)
- Positive `0.56` does NOT match inside negative `-0.56`
- `-0.56` DOES match when present

**TEST 2 — Range-dash safety (P1 #2) — 6/6 PASS:**
- `8.12–8.21` normalizes to `8.12 8.21` (no `-8.21`)
- `8.12–8.21` extracts as `{'8.12', '8.21'}` (both positive)
- `−1.44%` (U+2212) preserves as `-1.44` (real negative)
- Mixed range `−7.5 to −12.9` preserves both negatives

**TEST 3 — Cancer-50% adversarial via full verifier (must drop) — PASS:**
- Sentence: "Tirzepatide reduces cancer by 50% in patients with
  metabolic syndrome [#ev:ev_fab:0-100]."
- Evidence: ev_fab has `50%` in unrelated "family history of cancer"
  paragraph.
- V4 Pro cites narrow byte range 0-100 (intro only).
- `verify_sentence_provenance` returns `is_verified=False` with
  `no_content_word_overlap_any_cited_span` failure on the narrow span.
- **Architectural note**: the content-word-overlap gate (line 977)
  operates on `aggregated_span_text` (the narrow cited span), NOT on
  the recovered local window. This is the additional defense layer
  that catches semantic-mismatch fabrications: local-window only
  relaxes the NUMERIC strict check; the narrow-span content-word check
  remains a hard gate.

**TEST 4 — SURPASS grounded sentence (must pass) — 2/2 PASS:**
- Signed decimals `-0.59` + `-1.04` find local window at (179, 579)
- SURPASS-3 numbers `-2.37` + `-1.34` find local window (no regression)

**TEST 5 — Cluster placement (P2) — PASS:**
- Multi-token `{1.5, 2.0}` cluster: nearest `2.0` to rare `1.5` is
  found within 400 chars even though `2.0` has 5 occurrences

## Your architectural concerns from iter 1

You also flagged 4 architectural concerns at lower priority. My
responses:

1. **"400 chars is a plausible starting window for recall, but it is
   not a safety boundary."**
   Agreed. The local-window check only relaxes the **numeric** strict
   check. The downstream `content_word_overlap` gate (line 977) still
   operates on `aggregated_span_text` (narrow cited span), and the
   entailment judge is now also bounded to the local window. So
   recall-vs-safety: local window EXPANDS numeric tolerance only, by
   one defense layer.

2. **"min_content_overlap=2 is weak in this corpus; `patients`,
   `type`, `diabetes`, and `tirzepatide` co-occur around many
   unrelated numbers."**
   Acknowledged. My adversarial TEST 3 confirms this: when sentence,
   evidence, and unrelated numbers all fit in 332 chars, the
   local-window helper alone CAN'T distinguish semantic mismatch.
   That's why the full verifier path has THREE additional gates:
   narrow-span content-word overlap (line 977) + trial-name match
   (line 988) + entailment judge with local-window backstop (line 1027).
   Together they drop the adversarial. Should I bump min_content_overlap
   to 3 inside `_find_local_support_window` as a belt-and-braces
   improvement? Trade-off: legitimate sentences with very few content
   words (e.g., "Tirzepatide reduces weight by 12.9%" → {tirzepatide,
   reduces, weight} where "reduces" doesn't substring-match "reduced")
   might lose recall. **Your call.**

3. **"Step 2 is still needed: verifier fallback should not substitute
   for fixing live_deepseek_generator._find_best_span_for_sentence."**
   Agreed. Step 2 is on the plan. Step 1 unblocks the smoke test to
   measure pass-rate AFTER verifier fix; Step 2 reduces the false
   citations at the source so Step 1's fallback fires less often.

4. **"Recovered local windows are not added to `aggregated_span_text`,
   so later content-overlap and entailment checks still reason over
   the original bad span or the whole document."**
   This is now intentional — the narrow-span content-word check is the
   semantic backstop for cases like the cancer-50% adversarial, and
   the entailment fallback uses the recovered local window directly
   (not via `aggregated_span_text`). I traced this in TEST 3.

## Files for you to read

1. `src/polaris_graph/generator/provenance_generator.py:480-653`
   (`_normalize_unicode_minus` + `_find_local_support_window`)
2. `src/polaris_graph/generator/provenance_generator.py:860-968`
   (decimal-path + integer-path callers)
3. `src/polaris_graph/generator/provenance_generator.py:970-986`
   (content_word_overlap gate on narrow span — still active)
4. `src/polaris_graph/generator/provenance_generator.py:1020-1122`
   (entailment judge with local-window backstop — P1 #3 fix)
5. `scripts/test_i_gen_005_iter2_adversarial.py` (12 assertions)
6. `.codex/I-gen-005/codex_diff_iter2.patch` (full diff)

## Questions for you

1. Are the 3 P1 fixes complete and correct as landed?
2. Is the P2 cluster fix sufficient or are there cluster shapes I'm
   still missing?
3. min_content_overlap=2 vs 3 in `_find_local_support_window`: keep
   at 2 (current) or bump to 3 (defense-in-depth, possible
   recall hit)?
4. Any NEW P1 findings you see in the iter 2 diff?
5. Approval to run the smoke test?

## Output schema (verbatim, do not omit fields)

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
p0_or_p1_findings_on_iter2:
  - severity: P0 | P1
    location: <file:line>
    issue: |
      (specific bug or risk; quote code if applicable)
    proposed_fix: |
      (specific fix)
novel_p0: [...]   # ONLY genuinely new findings in iter 2 diff
continuing_p0: [...]
p1: [...]
p2: [...]
min_content_overlap_recommendation: KEEP_2 | BUMP_TO_3 | OTHER
  rationale: |
    (your reasoning)
approval_to_run_smoke: YES | NO
if_no: |
  (must-fix items before smoke)
if_yes: ""
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

EMIT YAML ONLY. Don't drip-feed. The operator's directive is "Pls
keep this iteration until Codex approve" — push back hard if there
are real blockers but don't manufacture findings to extend the cycle.
