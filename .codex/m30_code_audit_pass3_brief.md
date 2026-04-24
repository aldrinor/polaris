You are re-auditing M-30 after Claude addressed your pass-2
NOT_READY finding. This is pass 3.

## Pass-2 verdict

`outputs/codex_findings/m30_code_audit_pass2/findings.md` — NOT_READY:

- BLOCKER: `_is_abbreviation_period` short-circuited to non-boundary for
  every ALWAYS_NONBOUNDARY token and for multi-segment acronyms / `et
  al.`, regardless of what followed. Three demonstrated false-pass
  cases:
    - `"...4.2%, 5.3%, 6.4%, 7.5% in the U.S. A separate claim.[1]"`
    - `"...4.2%, 5.3%, 6.4%, 7.5% as reported by Smith et al. A
       separate claim.[1]"`
    - `"...4.2%, 5.3%, 6.4%, 7.5%, etc. A separate claim.[1]"`
  All three: decimals in the prior sentence genuinely uncited; `[1]`
  belongs to the next sentence. Pass-2 reported PT11 passed.
- LOW/nit: citation-adjacent sentence-end test didn't assert exact
  position past `]`.

## Pass-3 changes (commit `2bd0845`)

1. `src/polaris_graph/evaluator/external_evaluator.py`:
   - `_PT11_ALWAYS_NONBOUNDARY` shrunk to the tokens that virtually
     never end a sentence in practice:
       `{ vs, v, cf, viz, Dr, Mr, Mrs, Ms, Prof, Sr, Jr, Rev }`
   - `etc` moved to `_PT11_CONTEXT_DEPENDENT`.
   - Multi-segment acronyms (e.g, i.e, U.S, U.K, E.U) and `et al.`
     now flow through the context-dependent next-char
     disambiguation instead of short-circuiting to non-boundary.
   - Uppercase letter after whitespace → boundary (new sentence).
     Digit / `(` / `-` / `+` / lowercase → non-boundary.

2. `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`:
   - +4 PT11 end-to-end tests (Jan, U.S., et al, etc) that assert
     FAIL when the abbreviation is sentence-final + `[1]` in next
     sentence, replacing the single pass-2 Jan-only test with a
     systematic table-driven approach (`_mk_uncited_report` helper).
   - +2 counter-tests ("U.S. market", "et al. in 2023") asserting
     mid-sentence cases still PASS PT11 (fix doesn't over-tighten).
   - Strengthened citation-adjacent assertion:
     `_next_real_sentence_end` now asserted to return the exact
     position past `]`.

## Verifications

- `python -m pytest tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`
  → 33 passed.
- `python -m pytest tests/polaris_graph/` → 740 passed.
- PT11 on V19 real report still `passed=True` (Codex's original V19
  fix not regressed).

## Your task

Verify ALL pass-2 findings are closed:

1. Do the three new counter-tests (U.S., et al., etc.) accurately
   reproduce the pass-2 blocker scenarios, and does PT11 now FAIL
   on each as expected?

2. Does the context-dependent rule correctly split the ambiguous
   abbreviations? Specifically:
     - `U.S. market` → non-boundary (ship)
     - `U.S. A separate` → boundary (ship)
     - `et al. in 2023` → non-boundary (ship)
     - `et al. A separate` → boundary (ship)
     - `etc. and more` → non-boundary (ship)
     - `etc. A separate` → boundary (ship)

3. Low/nit: does the tightened citation-adjacent test now assert the
   exact position past `]` (not just "at or past")?

4. Any NEW failure class introduced by pass-3?

5. Hard-coding check (unchanged): confirm no domain-specific terms.

## Expected READY criteria

- All three pass-2 blocker scenarios now FAIL PT11 (genuinely uncited
  → flagged).
- Mid-sentence counter-tests still PASS PT11 (not over-tightened).
- `_next_real_sentence_end` test asserts exact bracket-close position.
- No new blockers introduced.

## Verdict format

Write `outputs/codex_findings/m30_code_audit_pass3/findings.md` with:

```
# M-30 code audit — pass 3

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

If READY, V20 full-scale sweep launches next. If NOT_READY, Claude
fixes and dispatches pass 4.

## Scope

Audit ONLY the pass-2 → pass-3 diff (commit `2bd0845`). Do NOT audit
M-28, M-29, other PT rules, or V19 outline-decode failure (task #8).
