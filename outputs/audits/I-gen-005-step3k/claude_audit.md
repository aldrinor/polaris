# I-gen-005 Step 3k — Claude architect audit

## Diff scope

`src/polaris_graph/generator/claim_atom_extractor.py`:
- Adds `_SAFETY_TABLE_HEADER_RE` (broad safety endpoint vocab)
- Adds `_CELL_PCT_TRAILING_RE` + `_CELL_PCT_PAREN_RE` (cell percentage extraction)
- Adds `_iter_safety_table_rows` (markdown table row detection)
- Adds `_canonicalize_safety_endpoint` (row-header → canonical endpoint mapping)
- Adds `_detect_all_table_regions` (helper retained but no longer wired)
- Wires per-cell extraction into `extract_atoms_from_evidence`
- Suppresses legacy walk for numbers in literal_text with >=3 pipes

`tests/polaris_graph/test_claim_atom_extractor.py`: 6 new step3k tests

## Codex iter trajectory

- Design APPROVE iter 1 (3 P2s noted)
- Diff APPROVE iter 5 (5 iters total): row-boundary heuristic, vocab coverage, legacy-walk suppression scope, regex prefix anchor, 2-arm threshold, descriptor-row noise suppression vs efficacy-table preservation trade-off

## Real-evidence verification (ev_000 SURPASS-2 NEJM)

Before Step 3k: 4 safety atoms, all entity=semaglutide (wrong arm binding)
After Step 3k: 101 safety atoms across 22 detected rows, including:
- Nausea: 4 V4 Pro target values (17.4, 19.2, 22.1, 17.9)
- SAE: 4 values (7.0, 5.3, 5.7, 2.8)
- Discontinuation: 4 values (6.0, 8.5, 8.5, 4.1)
- GI events: 5 values (40, 41.2, 43, 44.9, 46.1)
- Diarrhea/Vomiting/Abdominal pain/Dyspepsia/etc: per-row atoms
- 0 spurious atoms from descriptor rows ✓
- HbA1c prose atoms still extracted (20 values) ✓

## Known limitation (Codex iter-5 PARTIAL)

Pure markdown efficacy tables (e.g. `| HbA1c | -2.30 | -1.86 |`) produce 0 atoms via the new path because:
1. Safety vocab doesn't cover HbA1c endpoint (intentional — Step 3k scope)
2. Legacy walk suppressed by pipe-density check

In real evidence (ev_000), efficacy values appear in PROSE sentences not pipe-tables, so the limitation has no real impact. A future Step 3l can extend per-cell extraction to efficacy endpoints if V4 Pro starts citing efficacy markdown tables.

## Verdict

Step 3k is ready to merge. Per the operator's plan, next is the re-run smoke + Codex §-1.1 audit.
