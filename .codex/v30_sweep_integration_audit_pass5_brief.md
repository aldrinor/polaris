V30 sweep integration audit — pass 5.

**Skip git status.** Two files only.

## Context

Pass-4 verdict: CONDITIONAL-blockers. Three issues:
1. Disclosure prose overclaimed "populated with bound evidence"
   → wrap with Phase-1 preamble + rename H2 header.
2. Non-gap row with empty direct_quote still PASSed → new
   `_row_has_retrieval_evidence(row)` guard.
3. Stale happy-path test asserted no retrieval_only warning +
   "Frame coverage" in disclosure → realigned.

Commit `1fe1499` addresses all three. 316/316 regression pass.

## What to verify

Files (commit `1fe1499`):

1. `src/polaris_graph/v30_sweep_integration.py` — disclosure
   preamble wrap + `_row_has_retrieval_evidence` guard + renamed
   H2 header.
2. `tests/polaris_graph/test_v30_sweep_integration.py` — 20
   tests (was 18; +2 for degraded-row guard).

Check:

1. **Blocker 1**: disclosure text starts with "PHASE-1
   RETRIEVAL COVERAGE..." + explicit "does NOT claim ... cited
   ... in the verified report" + "Phase 2" pointer. report.md
   H2 header is "V30 Phase-1 Retrieval Coverage Disclosure".
2. **Blocker 2**: `_row_has_retrieval_evidence` correctly
   distinguishes:
   - non-gap + non-empty quote → True
   - non-gap + empty quote + OA URL → True
   - non-gap + empty quote + no OA → False
   - None row → False
   - HUMAN_CURATED → True
3. **Blocker 3**: happy-path test asserts the new semantics
   (mandatory warning, phase-1 preamble in disclosure).
4. **Fifth-round adversarial**:
   - Any remaining surface where manifest/report could be
     misread as report-coverage?
   - Any row state where `_row_has_retrieval_evidence` still
     false-passes?
   - Edge case: HUMAN_CURATED with empty direct_quote (would
     that happen? M-61 parser rejects empty quote on parse).

## Output

Write to
`outputs/codex_findings/v30_sweep_integration_audit/pass5_findings.md`.

Format:
```markdown
# Codex V30 sweep integration audit — pass 5

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-4 blockers resolved
<verified / still open>

## Fifth-round adversarial attempts
<list each>

## Residual concerns
<anything>

## Next
On APPROVED: sweep integration ready for Phase-1 live-run.
```

Keep under 60 lines. If APPROVED, task #28 → live run.
