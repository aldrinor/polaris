HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Read ONLY the patch file below. Do NOT explore the repo. Emit ONLY the YAML verdict block first, then
  ≤4 sentences.

## iter-1 REQUEST_CHANGES — both remaining fabrication P1s (row-header / empty-th-before-data) FIXED by
## COLLAPSING to a single conservative rule. Re-verify the regenerated patch:
`linearize_html_tables` now emits a `header: cell` association ONLY for the CANONICAL column-header table:
`not _SPAN_ATTR_RE` AND row0 multi-column AND row0 is ENTIRELY `<th>` AND all row0 header texts non-empty AND
`<th>` appears in NO later row. EVERY other shape degrades to ' | '-joined cells. This single rule subsumes
ALL five fabrication sub-cases (colspan, rowspan, headerless-multirow, row-header mixed `<th>/<td>`,
empty-`<th>`-before-data) — a cell can never get a column header the source didn't declare. Cells are now
parsed tag-aware (`_parse_row_cells` returns `(tag, text)`). New tests: row-header → joined no `:`;
empty-th → joined no `:`; canonical positive control associates. 14 table tests + 29 no-regression PASS.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-table-extraction/codex_diff.patch` (2 files, +228/-8). Feeds strict_verify (table
cells become provenance-verifiable); PURELY ADDITIVE to fetched text. NO SPEND.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR13: table-aware HTML linearization (#954)

Verify the diff implements the brief-gate-APPROVE'd design (brief APPROVE iter 3, after the two fabrication
fixes).

## What to verify
1. `linearize_html_tables(html)` (pure regex, fail-open '') emits `header: cell` ONLY when the source
   DECLARES an authoritative header — a row using `<th>` — in a span-free table. Two cases DEGRADE to plain
   ' | '-joined cells (NO fabricated header:cell association):
   - colspan/rowspan present (`_SPAN_ATTR_RE`) → joined (iter-1 P1 fix);
   - NO `<th>` row anywhere (`th_row_idx is None`) → joined (iter-2 P1 fix; the prior `... , 0` row-0
     fallback fabricated `Nausea: Vomiting`).
   When a `<th>` row exists, its parsed index is mapped from raw_rows (counting non-empty rows) and data
   rows zip to it by column index.
2. `_strip_html` APPENDS the linearized tables to the base extracted text (base unchanged), gated default-ON
   by `PG_FETCH_TABLE_LINEARIZE`; off → exact prior behavior.
3. NO change to `_build_provenance_quote`, strict_verify, tier classification, or evidence-row build.

## Evidence (verified by Claude main-thread, NO SPEND)
- 11 tests PASS: header↔cell survives ("Tirzepatide 15 mg: 3.8%"); integer/%-cells; `_strip_html` append;
  no-table unchanged; **colspan → joined, NO `Tirzepatide:`** ; **rowspan → joined, no `Arm:`/`Value:`** ;
  **headerless multi-row → joined, NO `:` association (no `Nausea: Vomiting`)** ; malformed/None/garbage →
  fail-open ""; kill-switch off → no append. `py_compile` OK. Patch +228/-8.

## The real risks to rule on
1. Can ANY table shape still emit a header:cell the source did not declare? (Claim: no — association fires
   ONLY on a `<th>`-declared header in a span-free table; colspan/rowspan AND headerless-multi-row both
   degrade to joined. The two P1s are pinned by tests.)
2. Is the raw_rows→parsed header-index mapping correct when leading rows are all-empty? (guarded: if the
   mapped index ≥ len(parsed), degrade to joined.)
3. Purely additive to fetched text (base never dropped/altered; verification logic untouched)?
4. Fail-open on malformed/nested/None (never raises)?

APPROVE iff the diff makes result-table cells survive WITH headers ONLY from declared `<th>` rows in
span-free tables, degrades every ambiguous shape (span / headerless-multi-row) to joined cells without
fabricating provenance, is purely additive + kill-switchable, and is offline-tested with NO SPEND.
