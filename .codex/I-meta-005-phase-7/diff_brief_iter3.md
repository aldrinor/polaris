HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings. No drip-feeding. Same bar every iter.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; rest P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW DISCIPLINE: focused re-review after iter-2 fixes. Open at most this brief, the
diff `.codex/I-meta-005-phase-7/codex_diff.patch`, and
`src/polaris_graph/synthesis/tradeoff_modeler.py` + `provenance_generator.py` if needed.
No repo-wide audit. Emit the verdict schema.

# I-meta-005 Phase 7 (#991) — DIFF re-review iter 3

## Your iter-2 findings and what changed
- **P1 (sci-notation false-DROP — REAL):** FIXED. `_canonical_display` "number" kind
  NEVER emits scientific notation now. A 6-sig-fig value Python would render as
  "1e+06" is EXPANDED to a plain fixed-point decimal via `format(Decimal(s), "f")`,
  then thousands-grouped + trailing-zero-stripped. So 1_000_000 -> "1,000,000" (not
  "1e+06"); 1e-7 -> "0.0000001". currency/percent/ratio/count never used sci notation.
  New smoke **P7-25** asserts the plain-decimal display AND that a number-kind field
  verifies against its own canonical display (no false-drop) while a wrong number drops.
- **P2 (stale tol constants):** FIXED. `_CALC_EQ_REL_TOL`/`_CALC_EQ_ABS_TOL` REMOVED;
  Regime C equality is purely canonicalize-and-compare (no numeric tolerance).

## To verify (front-load any continuing/novel P0/P1)
1. Confirm `_canonical_display("number")` produces NO scientific notation for any
   reachable magnitude (large ints, tiny fractions, negatives) and round-trips through
   the verifier's adjacency capture + re-canonicalization.
2. Confirm the canonicalize-and-compare false-ACCEPT guarantees from iter-1 still hold
   (suffix + magnitude) and the false-DROP from iter-2 is closed — together: no false
   accept AND no false drop of a legitimate canonical computed number.
3. Any remaining path where a number that is not the declared formula's executed output
   reaches verified_text, OR a legitimate executed number is wrongly dropped?

## Evidence
- 30 Phase-7 smoke (P7-1..P7-25 + sweep orchestrator) ALL PASS. Regression: generator
  (32) + crown_jewels (47) + synthesis green = 114 total. OFF byte-identity unchanged.

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
