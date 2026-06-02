CONFIRMATORY RE-GATE (CLAUDE.md §-1.2.6): the iter-5 P1 was a REAL denominator-bypass with a
DETERMINISTIC fix, so it was fixed (not force-approved). This single re-gate VERIFIES the fix.
Verdict APPROVE iff the acronym-led-prose denominator-bypass is closed and no new P0/P1.

REVIEW DISCIPLINE: verify ONLY `_CITATION_SHAPE_RE` / `_is_citation_entry` in
`scripts/dr_benchmark/run_scorecard.py`. Open at most this brief + that file + the diff.

# I-meta-006 (#1006) — confirmatory re-gate

## iter-5 P1 fix
`_CITATION_SHAPE_RE` now requires the SURNAME to be TITLE-CASE via `_SURNAME =
[A-Z][a-z][A-Za-z'\-]*` (capital THEN lowercase) in every author branch. An ALL-CAPS
acronym ("HPV", "DNA", "US", "AI", "MRI") fails `[A-Z][a-z]` (2nd char is uppercase), so it
is NOT a surname → acronym-led prose is NOT a citation entry → not stripped → kept in the
denominator. Your exact iter-5 sentence "HPV DNA testing in 2020 improved cervical precancer
detection in the screened cohort." → "HPV" fails the Title-Case surname → NOT a citation →
KEPT. Genuine refs ("Smith J. 2020", "Acemoglu and Restrepo, 2018", "McKinsey, 2020",
"Smith, 2020", DOI) still match. New smoke covers both HPV variants. 24 scorer + 12
claim_audit green.

## Confirm
Is the acronym-led-prose denominator-bypass closed, with no new realistic prose claim that
matches the Title-Case-surname citation shape AND front-loads a year? APPROVE if so.

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
