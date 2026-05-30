HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Do NOT explore the repo; the plan + the two fixes are fully described below. Emit ONLY the YAML verdict
  block first, then ≤4 sentences.

## iter-1 + iter-2 REQUEST_CHANGES — BOTH header:cell fabrication classes now FIXED (re-gate, iter 3):
A cell gets a `header: cell` prefix ONLY when the source DECLARES an authoritative header (a row using
`<th>`), AND the columns are unambiguous. Two cases DEGRADE to plain ' | '-joined cells (numbers survive,
never under a fabricated header the source never stated):
- **iter-1 P1 — colspan/rowspan:** `_SPAN_ATTR_RE` detects `colspan=`/`rowspan=`; if present → joined
  (index-zip would mis-align columns). Tests: colspan → `Nausea | 12% | 3.8%`, NO `Tirzepatide:`; rowspan →
  joined, no `Arm:`/`Value:`.
- **iter-2 P1 — headerless multi-row:** the prior `header_idx = next(... <th> ..., 0)` fell back to row 0 as
  headers, so a headerless table `<tr><td>Nausea</td><td>12%</td></tr><tr><td>Vomiting</td><td>3.8%</td></tr>`
  fabricated `Nausea: Vomiting | 12%: 3.8%`. FIX: `th_row_idx = next(... <th> ..., None)`; if `th_row_idx is
  None` → degrade to joined (no association). Association runs ONLY when a real `<th>` header row exists
  (mapped raw_rows→parsed index). New test asserts the headerless multi-row case emits NO `:` association.
11 tests PASS (incl. both degradation cases). The header:cell association now fires ONLY on a declared
`<th>` header in a span-free table — every other shape degrades to joined, never a fabricated header.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
Feeds strict_verify (table cells become provenance-verifiable). PURELY ADDITIVE to fetched text — no
verification-logic change. NO SPEND (regex only, no network, no model).

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR13: table-aware HTML linearization (#954)

Codex CONFIRMED-CORE (PARTIAL) gap (#950): `_strip_html` (live_retriever.py) flattens `<table>` markup to
running text, so a result-table cell loses its column-header association ("Discontinuation due to nausea …
3.8%" collapses to a floating "3.8") and integer / %-without-decimal cells become unanchored. strict_verify
then can only verify the loose decimals surviving in prose → the richest clinical data (results tables) is
under-verified. Codex p0: fix BEFORE relying on clinical numeric provenance. NO SPEND.

## GROUNDED FACTS (verified)
- `_strip_html(html)` (live_retriever.py:721) runs `trafilatura.extract` then a regex tag-strip fallback —
  both flatten tables, dropping header↔cell association.
- `_build_provenance_quote(content, head_chars=1500, window_chars=500)` keeps the first 1500 chars + windows
  around bare decimals; a cited span's text is what strict_verify checks for numeric + content overlap. So
  the fix is to make table cells survive in the FETCHED TEXT with their headers — verification logic is
  unchanged.
- `_fetch_content` → `_strip_html` is the single text-extraction chokepoint; fixing `_strip_html` covers
  every fetched source.

## CONCRETE PROPOSAL (additive, no-network, default-ON)
1. New `linearize_html_tables(html) -> str` (pure regex, fail-open): for each `<table>`, parse `<tr>` rows +
   `<th>/<td>` cells; the header row = the first row containing `<th>` (else row 0); emit each DATA row as
   `header: cell | header: cell` (one row per line). Headerless/1-col tables fall back to ` | `-joined cells.
   Any error / no tables → "" (never raises, never fabricates).
2. `_strip_html` APPENDS the linearized tables to the base extracted text (`base + "\n\n" + tables`), so the
   cells survive WITH headers regardless of how trafilatura/the fallback flattened them. Additive — never
   removes base text. Gated default-ON by `PG_FETCH_TABLE_LINEARIZE` (off → exact current behavior).
3. NO change to `_build_provenance_quote`, strict_verify, tier classification, or evidence-row build — this
   only enriches the fetched text the existing chokepoint already consumes.

## HONEST SCOPE
- This makes result-table cells PROVENANCE-VISIBLE (header-associated) so a claim citing them can pass
  strict_verify's content + decimal checks. It does NOT add a decimal window for integer-only cells — the
  integer-overlap fallback already in verify_sentence_provenance handles integer support; this PR's job per
  the issue is the header↔cell survival, which it delivers.
- Regex table parsing (not a full HTML parser / BeautifulSoup) keeps it dependency-free and matches the
  existing regex-fallback style; nested tables / colspan are not perfectly modeled but degrade to joined
  cells (never wrong, just less structured) — acceptable for a provenance-survival pass.

## Tests (offline, NO SPEND)
header↔cell association survives ("Tirzepatide 15 mg: 3.8%"); integer + %-cells preserved ("…: 938");
`_strip_html` appends tables to base text; no-table HTML unchanged (no " | " injected); malformed/None →
fail-open ""; kill-switch off → no append; garbage never raises. 8 pass + 31 no-regression on the retrieval
module.

## Constraints / frozen
snake_case; explicit imports; no except:pass (the two `except Exception` are fail-open with a noqa, matching
the existing _strip_html trafilatura guard). Untouched: strict_verify, _build_provenance_quote, tier
classifier, evidence rows, the §9.1 chokepoint. ≤120 LOC. NO SPEND.

## The real risks to rule on
1. Is appending linearized tables to fetched text purely additive (no verification-logic change, can't drop
   or alter base text)? (Claim: yes — base text is always retained; tables are concatenated.)
2. Can the regex table parser raise or fabricate on malformed/nested/colspan HTML? (Claim: no — fail-open to
   "", degrade to joined cells; proven by the malformed/garbage tests.)
3. Could the appended table text mislead provenance (e.g. associate a cell with the wrong header)? (Claim:
   header row = first `<th>` row else row 0, zipped by column index — standard; a mis-modeled colspan
   degrades to joined cells, never a wrong header:cell that the source didn't state.)
4. Default-ON acceptable for an additive fetch-enrichment? (kill-switch present.)

APPROVE iff this adds a no-network, fail-open table linearizer that makes result-table cells survive WITH
their headers in fetched text, is purely additive (verification logic + chokepoint untouched), default-ON
with a kill-switch, and is offline-tested with NO SPEND.
