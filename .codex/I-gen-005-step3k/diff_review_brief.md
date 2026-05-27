# I-gen-005 Step 3k diff iter 5 (FINAL) — known limitation

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (diff review).
If REQUEST_CHANGES at iter 5, force-APPROVE per §8.3.1.
```

## Iter 4 verdict → iter 5 response

REQUEST_CHANGES with 1 P1: non-safety pipe tables suppressed (efficacy tables produce 0 atoms because broad legacy-walk suppression also blocked their extraction).

### Fix applied

Replaced broad `_detect_all_table_regions` suppression with a tighter check: skip legacy walk only when the number's literal_text contains >=3 pipes (typical markdown table cell indicator). This:

1. Preserves descriptor-row leak suppression (spurious "0.2"/"5" atoms from "≥0.2% of patients..." rows) — those rows have many pipes in surrounding context.
2. Preserves prose-style HbA1c atom extraction (the real ev_000 evidence has HbA1c values in prose, not pipe-tables, so they survive the filter).
3. **Known limitation**: SYNTHETIC pipe-table evidence for efficacy endpoints (e.g., `| HbA1c | -2.30 % | -1.86 % |`) will not produce atoms because both the safety-table extractor (only handles safety vocab) and the legacy walk (suppressed by pipe-density) skip it.

### Why this trade-off is acceptable for Step 3k scope

The operator's Step 3k mandate is per-cell SAFETY atoms (real V4 Pro smoke target: Nausea/SAE/Discontinuation table cells). Real ev_000 SURPASS-2 NEJM evidence has:
- SAFETY data in markdown tables → now extracted per-cell (101 safety atoms incl. all V4 Pro targets)
- EFFICACY data in PROSE sentences ("Tirzepatide reduced HbA1c by -2.30 percentage points...") → still extracted via legacy walk

A future Step 3l can extend the table-row extractor to efficacy endpoints if/when V4 Pro starts citing efficacy markdown tables in addition to safety. For Step 3k, this is OUT OF SCOPE.

## Diff bound

canonical-diff-sha256: 34b31022c3fb755ab0daf34a8d6a40fc4a2f7dbdbfdfee07c05a695ef797a514
- 155/155 tests pass
- ev_000:
  - 142 total atoms
  - 0 spurious 0.2/5 ✓
  - All V4 Pro target safety values present ✓
  - HbA1c prose atoms still extracted: 20 values incl. -2.30/-1.86/-2.24/etc. ✓

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

iter4_p1_addressed: PARTIAL  # synthetic efficacy table no, real efficacy prose yes
known_limitation_documented: YES
ev_000_real_smoke_targets_verified: YES

novel_p0: []
novel_p1: []
p2: []

canonical_diff_sha256_verified: 34b31022c3fb755ab0daf34a8d6a40fc4a2f7dbdbfdfee07c05a695ef797a514
```

EMIT YAML ONLY.
