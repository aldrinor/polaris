# I-gen-005 Step 3k — atom_extractor per-cell safety atoms (design)

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
```

## Problem (real smoke evidence)

Source evidence ev_000 (SURPASS-2 NEJM) contains a markdown safety table:

```
| Nausea | 82 (17.4) | 111 | 90 (19.2) | 124 | 104 (22.1) | 136 | 84 (17.9) | 126 | 360 (19.2) | 497 |
| Diarrhea | 62 (13.2) | 120 | 77 (16.4) | 99 | 65 (13.8) | 102 | 54 (11.5) | 68 | 258 (13.7) | 389 |
| Vomiting | 27 (5.7) | 35 | 40 (8.5) | 56 | 46 (9.8) | 61 | 39 (8.3) | 53 | 152 (8.1) | 205 |
| Patients with ≥1 serious adverse event | 33 (7.0) | — | 25 (5.3) | — | 27 (5.7) | — | 13 (2.8) | — |
| ... events leading to treatment discontinuation | (6.0) | (8.5) | (8.5) | (4.1) ...
```

V4 Pro lifts per-arm percentages from these cells in safety.s000 / s001:

> "Nausea occurred in 17.4%, 19.2%, 22.1%, and 17.9% of patients..."
> "Serious adverse events were reported in 7.0%, 5.3%, 5.7%, and 2.8%..."

But current `extract_atoms_from_evidence` emits only **4 safety atoms** from ev_000:
- atom_022 endpoint=discontinuation value=28 entity=semaglutide
- atom_023 endpoint=discontinuation value=6.0 entity=semaglutide
- atom_024 endpoint='adverse events' value=0.2 entity=semaglutide
- atom_025 endpoint='adverse events' value=5 entity=semaglutide

All entities are "semaglutide" (the comparator named in trial description) — incorrect per-arm binding. All cells of Nausea/Diarrhea/Vomiting rows produce ZERO atoms because `_find_endpoint` looks at the first endpoint match in the broader literal_text — not the row header.

Result: V4 Pro's claims are REFUSED because no atom_NNN cites match.

## Proposed design

Add a NEW path in `extract_atoms_from_evidence` that **detects markdown table rows and emits per-cell atoms** with endpoint = row header, before the existing per-number walk.

### Table-row detection

A line is a table row if:
1. Starts with `|` (allowing whitespace)
2. Has ≥3 `|` separators
3. First non-empty cell (between `|`s) contains at least one endpoint vocab term (`_SAFETY_TABLE_HEADER_RE`)
4. NOT a header-divider row (i.e., not `|---|---|---|`)

### Per-cell extraction

For each detected safety table row:
1. Extract row-header endpoint (first cell, matched against `_SAFETY_TABLE_HEADER_RE`)
2. For each subsequent cell containing a number:
   - Identify the percentage value (heuristic: number followed by `%`, OR number inside `(...)`, OR bare number where the row context indicates percentage)
   - Emit ONE atom with:
     - endpoint = row header (e.g., "Nausea")
     - value = the percentage
     - unit = "%"
     - entity = trial name from the broader evidence (fallback — column-to-arm mapping is out of scope for Step 3k)
     - literal_text = the row text (for verifier provenance)
     - primary_section = "Safety"

### What we explicitly DO NOT do

- Parse column headers to map columns to arm names (next step if needed)
- Restructure non-table evidence (this is purely additive)
- Modify the existing per-number walk (so non-table evidence behavior is unchanged)

### Why this is safe

Existing extractor walks every number in direct_quote regardless of table format — but classifies cell percentages as non-OUTCOME or binds wrong endpoint. The new table-row path runs BEFORE the existing walk and emits high-confidence per-cell atoms. The existing walk continues but is unlikely to re-emit (atoms are deduplicated by (endpoint, value, entity) tuple if I add dedup, or both emissions are kept and the catalog will have N+M atoms).

For Codex: should I add (endpoint, value, entity) dedup, or just let both code paths emit?

### Test plan

1. Real-evidence test: feed ev_000's direct_quote to the extractor, assert ≥20 safety atoms emitted (5 rows × 4 arms).
2. Per-row test: a synthetic 1-row markdown safety table → 4 atoms (Nausea + 4 arms).
3. Non-table behavior unchanged: feed a prose-style sentence, assert same atoms as pre-Step-3k.
4. Mixed test: evidence with prose + table together → both paths fire.

## Questions for Codex

1. Is the markdown-table heuristic sufficient (line starts with `|`, ≥3 `|`, first cell matches `_SAFETY_TABLE_HEADER_RE`)? Or do you need a stricter detector (e.g., require pipe-divider row above)?
2. What about `( ... )` cells like "82 (17.4)" — which number becomes the atom? The percentage in parens (17.4) is more informative than the sample count (82). Heuristic: prefer the number followed by `%` or inside `(...)` when both appear in a cell.
3. Should I add (endpoint, value, entity) deduplication, or accept N+M emission overlap?
4. Per-arm column-header parsing — out of scope for Step 3k or required?
5. Failure modes you predict from this design?

## Output schema

```yaml
verdict: APPROVE_DESIGN | REQUEST_CHANGES

table_detection_heuristic: SUFFICIENT | TOO_NARROW | TOO_BROAD

cell_number_extraction_strategy: CLEAR | UNCLEAR

dedup_required: YES | NO | OPTIONAL

per_arm_column_mapping_scope: IN_SCOPE | OUT_OF_SCOPE | DEFER

novel_p0: []
novel_p1: []
p2: []

ready_to_implement: YES | NO
```

EMIT YAML ONLY.
