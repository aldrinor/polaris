HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P2/P3.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused re-review of the Phase-7 DIFF after iter-1 fixes. Open at
most: this brief, `.codex/I-meta-005-phase-7/codex_diff.patch`, and
`src/polaris_graph/generator/provenance_generator.py` +
`src/polaris_graph/generator/quantified_analysis.py` if needed. Do NOT run a repo-wide
audit. Emit the verdict schema.

# I-meta-005 Phase 7 (#991) — DIFF re-review iter 2

## Your iter-1 findings and what changed
- **P1-1 (suffix-match false-accept — REAL wedge hole):** FIXED. `verify_modeled_atom`
  no longer uses `before.endswith(display_value)`. It now compares the FULL adjacent
  number string captured by `_CALC_ADJACENT_NUMBER_RE` against `display_value`, and if
  that is not an exact string match it RE-CANONICALIZES the parsed adjacent value via
  the SAME `_canonical_display(value, unit, display_kind)` and requires `recanon ==
  display_value`. "123.40%" -> canonical "123.40%" != "23.40%" -> DROP. New smoke
  P7-23 asserts exactly your example (and that legit "23.40%" passes).
- **P1-2 (rel_tol=1e-9 magnitude drift — REAL wedge hole):** FIXED by the SAME
  canonicalize-and-compare. The loose numeric backstop, `_is_calc_equal`, and
  `_CALC_EQ_REL_TOL`/`_CALC_EQ_ABS_TOL` are REMOVED. "$1,000,000,000,999.00" ->
  canonical "$1,000,000,000,999.00" != "$1,000,000,000,000.00" -> DROP. A benign
  reformat ("$1000000000000.00", no commas) re-canonicalizes to the SAME string ->
  PASS. New smoke P7-24 asserts your example + the drift drop + the benign-reformat pass.
- **P2-1 (audit bundle incomplete):** FIXED. `quantified_model.json` per-field now
  persists `display_kind`, `unit`, `modeled_used`, and `sourced_tokens` (not just
  value+display_value).
- **P2-2 (sentence-level modeled label):** ACCEPTED as disclosure-completeness, not a
  wedge failure (your own classification — the NUMBER stays executor-correct). Left
  sentence-level (matches brief P7-7/P7-8). If you now consider per-input naming a hard
  requirement, say so and I will add it; otherwise it stays as a documented P2/P3.

## To verify (front-load any continuing/novel P0/P1)
1. Confirm the canonicalize-and-compare closes BOTH false-accept classes (suffix +
   magnitude) and introduces NO new false-DROP of a legitimate canonical number.
2. Confirm `fld["unit"]`/`fld["display_kind"]` are always populated for every field id
   (output, sensitivity `out@in=x`, break-even `out.break_even`) so the re-canonical
   step never silently falls back to the wrong kind. (break-even uses unit="",
   kind="number".)
3. Any OTHER path where a number that is not the declared formula's executed output
   reaches verified_text? (registry resolution, field lookup, adjacency capture,
   token strip, OFF byte-identity.)

## Evidence
- 29 Phase-7 smoke (P7-1..P7-24 + sweep orchestrator) ALL PASS, incl. the two new
  Codex-case tests. Regression: generator (32) + synthesis + crown_jewels (CJ-002/003/004)
  green. OFF byte-identity unchanged.

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
