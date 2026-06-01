HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Same bar every iter. Reserve P0/P1 for real execution risks.
- If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused re-review after the iter-2 fix. Open at most this brief, the diff
`.codex/I-meta-006/codex_diff.patch`, and `scripts/dr_benchmark/run_scorecard.py`. No
repo-wide audit. Emit the verdict schema.

# I-meta-006 (#1006) — DIFF re-review iter 3

## Your iter-2 P1 (continuing denominator-exclusion) and what changed
`split_body_and_references` is rewritten to FAIL SAFE toward inclusion:
- It now triggers ONLY on a STRONG reference header `_STRIP_HEADER_RE` =
  References / Bibliography / Works Cited (NOT "Sources", which is routinely prose like
  "Sources of evidence"). The broad `_REFERENCES_HEADER_RE` (incl. Sources/Citations) is
  used ONLY by `parse_references` to find a source list, never to decide stripping.
- It strips the trailing block ONLY when `all(_is_citation_entry(ln) for ln in nonempty)`.
  `_is_citation_entry` drops any leading enumerator (`1.` / `[1]` / `-`), requires a 4-digit
  year, AND rejects lines whose first word is a prose sentence-starter (the/a/this/it/we/
  according/studies/...). So a numbered PROSE claim "1. The drug reduced events by 20% in the
  2020 cohort" → not a citation entry → the block is NOT stripped → the claim stays in the
  denominator.
- New smoke: `test_split_body_keeps_numbered_prose_under_references_header` (numbered prose
  under "References" kept) + `test_split_body_sources_header_not_a_strip_trigger` ("Sources"
  never strips). The prior `test_split_body_strips_terminal_reference_list` (a pure
  "1. Smith J. 2020. https://…" list IS stripped) still passes.

## Confirm
Is the denominator-exclusion path now fully closed — is there ANY reachable input where a
prose claim is silently dropped before `extract_atoms`? (header-followed-by-prose, numbered
prose, URL-bearing prose, mid-report Sources, mixed list.) Any other false-credit / silent
exclusion path?

## Evidence
21 Phase-meta006 smoke (incl. 2 new) + 12 claim_audit + dr_benchmark regression green.

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
