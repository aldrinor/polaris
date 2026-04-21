You are re-auditing M-28 Fix #1 after Claude addressed your prior
NOT_READY findings. This is pass 2 of the code audit.

## Prior verdict

outputs/codex_findings/m28_code_audit/findings.md — NOT_READY with:
- 1 BLOCKER: agency/host strings in docstrings/comments of
  `src/polaris_graph/retrieval/regulatory_expander.py`
- MEDIUM #2: no query-count cap on anchor queries
- MEDIUM #3: test coverage holes (YAML integration, guard test)

## What Claude changed

Commit: see `git log -1 --name-only` to locate the follow-up commit.
Summary:

1. Rewrote `src/polaris_graph/retrieval/regulatory_expander.py`
   docstring and comments to be fully generic. No agency names, no
   jurisdictional terms, no clinical-domain leaks.
2. Added `PG_SWEEP_MAX_REGULATORY_ANCHORS` env var (default 10).
   Expander now truncates anchor list to the cap. Env can override;
   zero or negative disables the cap.
3. Added 11 follow-up tests:
   - `TestNoHardCodedHostsInModule` guard test that scans the module
     text for banned substrings at CI time
   - `TestAnchorCountCap` (5 tests)
   - `TestYamlTemplateIntegration` (5 tests)

Total M-28 tests: 20 → 31. All pass. Full suite: 688 → 699. Clean.

## Your task

Re-audit the SAME 10 review questions from pass 1. Focus especially
on whether the three findings are genuinely closed vs cosmetically
patched.

### Re-check items

1. **"ZERO agency-specific strings in .py"**: run a cross-check on
   `src/polaris_graph/retrieval/regulatory_expander.py`. Confirm the
   file has zero agency names, jurisdictional terms, or clinical-
   domain vocabulary. Run the guard test yourself to confirm it would
   fail if a term slipped in (e.g. temporarily add "fda" to the
   comment and see the test flag it, then revert).

2. **Cap enforcement**: confirm the cap is read per-call (not cached
   at import), so a test can monkey-patch via env. Confirm the cap
   is applied AFTER de-dup / extraction so a template with 15 entries
   that reduces to 10 valid anchors is not re-truncated.

3. **Guard test robustness**: verify `TestNoHardCodedHostsInModule`
   reads the module file from disk (not the imported module), so a
   stale bytecode cache cannot fool the test.

4. **Integration tests**: run the new YAML integration tests and
   confirm they actually load the real templates rather than mocking.

5. **Any new concerns**: if the follow-up edits introduced any new
   regressions, flag them.

6. **Test-count claim**: Claude says 699 tests. Verify by running
   `PYTHONPATH=src python -m pytest tests/polaris_graph/ -q --no-header`
   yourself.

### Verdict rules (unchanged)

- READY: no blockers, ≤2 mediums with documented mitigations.
- CONDITIONAL: zero blockers but ≥3 mediums.
- NOT_READY: any blocker.

Write findings to `outputs/codex_findings/m28_code_audit_pass2/findings.md`:

```
---
audit_type: code_review_pre_sweep_pass2
fix: M-28 Fix #1 (regulatory-anchor retrieval)
commit_range: previous-audit-commit..HEAD
verdict: READY | CONDITIONAL | NOT_READY
blockers: <int>
mediums: <int>
regression_introduced: <yes/no>
---

Per-item verdict. Final sentence: "M-28 may / may not proceed to V18 sweep."
```

If READY, Claude launches V18 sweep immediately. Be uncompromising.
