HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Same bar. Reserve P0/P1 for real execution risks. If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused re-review of `_is_citation_entry` / `split_body_and_references`
in `scripts/dr_benchmark/run_scorecard.py` after the iter-3 fix. Open at most this brief +
that file + the diff. No repo-wide audit. Emit the verdict schema.

# I-meta-006 (#1006) — DIFF re-review iter 4

## Your iter-3 P1 and what changed
The NEGATIVE not-prose denylist is REPLACED by a POSITIVE bibliographic-shape requirement.
`_is_citation_entry(line)` now strips a leading enumerator, requires a 4-digit year, AND
requires `_CITATION_SHAPE_RE.match`, which matches ONLY:
- `Surname, 2020` (author + year),
- `Surname J.` / `Doe A,` / `Smith, JA.` (author + initials, initials = 1-3 caps + word boundary),
- `Surname and/& Surname`,
- `Surname et al`,
- a `doi:` / `doi.org` line.
A prose claim like `Semaglutide reduced cardiovascular events by 20% in the 2020 cohort`
fails all alternatives (the second token `reduced` is a lowercase word, not an initial / not
`and`/`&` / not `et al` / no `Surname,Year`), so it is NOT a citation entry → the block is
NOT stripped → the claim stays in the denominator. Block stripping still requires a STRONG
header (References/Bibliography/Works Cited, not Sources) AND `all(_is_citation_entry)`.

New smoke: proper-noun-led numbered prose under `References` is KEPT; an author-initials list
IS stripped; `Sources` never triggers; the prior numbered-prose + terminal-list cases pass.
23 Phase-meta006 smoke + 12 claim_audit green.

## Confirm
Is the denominator-exclusion path now closed — is there a reachable prose claim (any
realistic clinical/policy sentence) that matches `_CITATION_SHAPE_RE` and would be dropped
under a References header? If a residual exists, state the exact sentence; otherwise APPROVE.

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
