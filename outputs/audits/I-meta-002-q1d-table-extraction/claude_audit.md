# Claude architect audit — PR13: table-aware HTML linearization (#954)

**Issue:** #954 (q1d-d, Codex CONFIRMED-CORE PARTIAL #950 — last depth-critical fix). **Branch:**
`bot/I-meta-002-q1d-table-extraction`. **Both Codex gates APPROVE** — brief iter-3 + diff iter-2 (zero
P0/P1/P2). **NO SPEND** — pure regex, no network/model; 14 offline tests.

## What this fixes

`_strip_html` flattens `<table>` markup to running text, so a result-table cell loses its column-header
association ("Discontinuation due to nausea … 3.8%" collapses to a floating "3.8") and integer /
%-without-decimal cells become unanchored. strict_verify could then only verify loose decimals surviving in
prose → the richest clinical data (results tables) was under-verified (Codex p0). This adds a no-network,
fail-open table linearizer that makes result-table cells survive in the fetched text WITH their column
headers, appended additively (base text never altered) behind a default-ON kill-switch.

## The clinical-safety design (5 fabrication sub-cases → one conservative rule)

Codex review surfaced FIVE distinct ways an index-zip over irregular HTML tables can FABRICATE a `header:
cell` association the source never stated (provenance-misleading): colspan, rowspan, headerless-multi-row,
row-header (`<th>` as each row's first cell), and empty-`<th>`-before-data. Rather than enumerate guards,
the implementation collapses to ONE maximally-conservative rule: emit a `header: cell` association ONLY for
the CANONICAL column-header table —

- no colspan/rowspan anywhere, AND
- the first non-empty row is ENTIRELY `<th>` with non-empty header text, AND
- the table has >1 column, AND
- `<th>` appears in NO later row (so it is column headers, not per-row row-headers).

EVERY other shape DEGRADES to plain ` | `-joined cells: the number still survives in text next to its row
label (the issue's value), but a cell can NEVER receive a column header the source did not declare. Cells
are parsed tag-aware (`_parse_row_cells` → `(tag, text)`) so a column-header row is distinguishable from a
row-header. Fail-open ('' on any error/malformed/None — never raises, never breaks fetch).

## Untouched

`_build_provenance_quote`, strict_verify, tier classification, evidence-row build, the §9.1 chokepoint. This
only enriches the fetched text the existing chokepoint already consumes; verification logic is unchanged.

## Tests (14, NO SPEND)

Canonical column-header → associates; integer/%-cells preserved; `_strip_html` append; no-table unchanged;
**all five fabrication sub-cases degrade to joined with NO `:` association** (colspan, rowspan, headerless-
multi-row, row-header mixed `<th>/<td>`, empty-`<th>`-before-data); malformed/None/garbage → fail-open "";
kill-switch off → no append. Plus 29 no-regression (live_retriever_rerank + retrieval_trace). `py_compile` OK.

## Verdict

Makes result-table cells survive WITH their column header ONLY from a declared canonical `<th>` header row
in a span-free table, degrades every ambiguous shape to joined cells without fabricating provenance, is
purely additive + kill-switchable, leaves strict_verify untouched, and is offline-tested NO SPEND. Both
gates APPROVE. Ready to queue for operator merge — the LAST depth-critical fix of the queue.
