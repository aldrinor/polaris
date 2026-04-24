You are re-auditing M-30 after Claude addressed your pass-3
NOT_READY finding. This is pass 4.

## Pass-3 verdict

`outputs/codex_findings/m30_code_audit_pass3/findings.md` — NOT_READY:

- BLOCKER: pass-3 introduced a false-FAIL. Any uppercase next char
  after a context-dependent abbreviation was unconditionally treated
  as sentence boundary, so legitimate mid-sentence noun phrases like
  `U.S. FDA`, `U.K. Biobank`, `E.U. Horizon` were split. Demonstrated
  probe:
  `"rates were 4.2%, ..., 9.7% in the U.S. FDA database across cohorts.[1]"`
  → PT11 passed=False, wrong: `[1]` cites the same sentence.

## Pass-4 changes (commit `46fa532`)

Word-shape disambiguation replaces the single-char uppercase rule:

1. `src/polaris_graph/evaluator/external_evaluator.py`:
   - Added `_PT11_SENTENCE_STARTER_WORDS` — generalizable English
     discourse markers and articles: The, This, However, Moreover,
     Separately, Notably, And, But, In, When, While, First, Next,
     etc. No domain-specific terms.
   - `_is_abbreviation_period` uppercase-branch now inspects the
     WHOLE next word:
       • 1-char uppercase ("A", "I")                  → boundary
       • ALL-CAPS multi-char (FDA, NHS, EPA)          → non-boundary
       • Title-case in _PT11_SENTENCE_STARTER_WORDS   → boundary
       • Title-case NOT in list (proper noun):
           – next-next word starts lowercase          → non-boundary
             (proper-noun continuation: "Biobank data")
           – otherwise                                → boundary
             (safer default)

2. `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`:
   - `test_pt11_preserves_midsentence_us_fda` — exact Codex pass-3
     probe: 6 decimals before `U.S. FDA database...[1]` must PASS
     PT11.
   - `test_pt11_preserves_midsentence_uk_biobank` — U.K.+Biobank
     +lowercase continuation must PASS PT11.
   - `test_pt11_still_boundary_on_us_the` — U.S.+The (article) must
     still be boundary (decimals before U.S. FAIL PT11).

## Verifications

- `python -m pytest tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`
  → 36 passed.
- `python -m pytest tests/polaris_graph/` → 743 passed.
- PT11 on V19 real report still `passed=True`.

## Your task

1. Verify the pass-3 counter-example now PASSES PT11:
   `"...4.2%, 5.3%, 6.4%, 7.5%, 8.6%, 9.7% in the U.S. FDA database across cohorts.[1]"`
   This must pass.
2. Verify ALL pass-1 and pass-2 blockers still FAIL PT11:
   - `... in Jan. A separate ...[1]`           → fail
   - `... in the U.S. A separate ...[1]`       → fail
   - `... Smith et al. A separate ...[1]`      → fail
   - `... etc. A separate ...[1]`              → fail
3. Additional probes you may run:
   - `... in the U.K. Biobank data ...[1]`     → pass (counter-test)
   - `... in the U.S. The trial was ...[1]`    → fail (boundary)
   - `... in the E.U. ECB report ...[1]`       → pass (acronym chain)
   - `... Eli Lilly Inc. Separately reports ...[1]`
       (decimals before Inc., [1] after reports) → fail (Separately
       is in sentence-starter list)
4. Any NEW failure class introduced by pass-4?
5. Hard-coding check (unchanged): sentence-starter list is
   generalizable English prose, no domain-specific terms.

## Expected READY criteria

- All pass-1, pass-2, pass-3 blocker scenarios closed.
- Mid-sentence counter-tests still pass PT11.
- No new blockers introduced.
- Hard-coding list remains generalizable.

## Verdict format

Write `outputs/codex_findings/m30_code_audit_pass4/findings.md`:

```
# M-30 code audit — pass 4

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If READY, V20 sweep launches next. If NOT_READY, Claude fixes and
dispatches pass 5.

## Scope

Audit ONLY the pass-3 → pass-4 diff (commit `46fa532`). Do NOT audit
M-28, M-29, other PT rules, or V19 outline-decode failure (task #8).
