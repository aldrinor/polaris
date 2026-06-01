HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Same bar every iter. Reserve P0/P1 for real execution risks.
- If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused re-review after iter-1 fixes. Open at most this brief, the diff
`.codex/I-meta-006/codex_diff.patch`, `scripts/dr_benchmark/run_scorecard.py`, and
`src/polaris_graph/benchmark/report_claim_extractor.py`. No repo-wide audit. Emit the schema.

# I-meta-006 (#1006) — DIFF re-review iter 2

## Your iter-1 findings and what changed
- **P1 (denominator-exclusion bypass — REAL):** FIXED. `split_body_and_references` now uses
  the LAST references-header match (terminal) and strips the trailing block ONLY when it is
  ≥60% reference-list-like (`_looks_like_reference_line`: URL / `[N].`/`N.` prefix / Author-Year
  leading). When substantial prose follows the (last) header, it does NOT strip — it FAILS SAFE
  toward inclusion (returns the full text as body). A mid-report `## Sources` followed by answer
  prose, or a header followed by prose, NO LONGER excludes those claims. New smoke:
  `test_split_body_keeps_prose_after_nonterminal_header` (prose kept) +
  `test_split_body_strips_terminal_reference_list` (terminal list stripped).
- **P2-1 (bare/bold heading):** FIXED. `_REFERENCES_HEADER_RE` now matches a bare `References`
  line, a `## References` heading, and `**References**`, plus `Sources/Bibliography/Works Cited/
  Citations`.
- **P2-2 (unicode superscripts):** FIXED. `_SUPERSCRIPT_RE` parses `⁰¹²³⁴⁵⁶⁷⁸⁹` runs →
  numbered citations resolved against the references; superscripts are stripped from atom text.
  New smoke `test_gemini_unicode_superscript_citation`.

## Confirm (front-load any continuing/novel P0/P1)
1. Is the denominator-exclusion bypass fully closed — no reachable path where prose claims are
   silently dropped before scoring (header-followed-by-prose, mid-report Sources, no-header)?
2. Does the ≥60% reference-list-like heuristic ever wrongly strip a TERMINAL block that is
   actually prose (re-introducing exclusion), or wrongly keep a real reference list (the minor
   lane1 distortion you classified P2 — acceptable)?
3. Any OTHER path to a false faithfulness credit or a silent claim exclusion?

## Evidence
- 19 Phase-meta006 smoke (incl. the 3 new fix tests) + 12 claim_audit + dr_benchmark
  regression green. No live client.

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
