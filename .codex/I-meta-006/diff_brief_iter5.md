HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (the cap).
- If this returns REQUEST_CHANGES, the diff is force-APPROVE'd on remaining-non-P0/P1
  per CLAUDE.md §8.3.1; do NOT bank issues for iter 6. Surface any TRUE P0 (a false
  faithfulness CREDIT) distinctly from a residual reference-stripping heuristic edge.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused final review of `_is_citation_entry` / `_CITATION_SHAPE_RE` /
`split_body_and_references` in `scripts/dr_benchmark/run_scorecard.py`. Open at most this
brief + that file + the diff. No repo-wide audit. Emit the verdict schema.

# I-meta-006 (#1006) — DIFF re-review iter 5 (cap)

## Your iter-4 P1 (acronym-led prose) and what changed
`_is_citation_entry` now requires, in addition to the positive `_CITATION_SHAPE_RE`
(author-initials / "Surname, Year" / "& Author" / "et al" / DOI), that the YEAR is
FRONT-LOADED — present within the FIRST 5 whitespace tokens. A reference front-loads
author+year ("Smith J. 2020 ..."); a prose claim's year is embedded later ("HPV DNA
testing improved cervical precancer detection in the 2020 screening cohort" → first 5
tokens "HPV DNA testing improved cervical" → no year → NOT a citation entry → KEPT).
A Vancouver-style reference with a late year is simply NOT stripped (kept as atoms =
acceptable minor over-inclusion), never a prose claim dropped. New smoke
`test_split_body_keeps_acronym_led_prose_under_references`. 24 Phase-meta006 smoke +
12 claim_audit green.

## Severity framing for the cap
The whole `split_body_and_references` concern is whether a real PROSE claim can be
silently dropped from the lane1 denominator (a report dodging faithfulness scoring). It
does NOT create a false faithfulness CREDIT (the §-1.1 judge still reads fetched spans
for every atom that IS extracted). The stripping ALSO only fires under a STRONG
References/Bibliography/Works-Cited header AND only when EVERY trailing line is a
front-loaded-year positively-shaped citation entry; ANY ambiguous line → no strip
(fail-safe inclusion). If a residual contrived case remains, classify it honestly
(reference-stripping heuristic edge vs a true denominator bypass on realistic input).

## Confirm
Is there a REALISTIC prose claim (clinical/policy research sentence) that, as the sole
trailing line under a References header, both matches `_CITATION_SHAPE_RE` AND front-loads
a year within 5 tokens, and would be dropped? If yes, give the exact sentence. If only
contrived/implausible cases remain, APPROVE.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
