You are re-auditing M-30 after Claude addressed your prior NOT_READY
findings. This is pass 2.

## Prior verdict (pass 1)

`outputs/codex_findings/m30_code_audit/findings.md` — NOT_READY:

- BLOCKER: abbreviation periods treated as non-boundary even when
  sentence-final. Example:
  `"...declines were 4.2%, 5.3%, 6.4%, 7.5% in Jan. A separate claim.[1]"`
  Under pass-1, Jan. was skipped as abbreviation → lookahead from 4.2
  reached `[1]` → PT11 falsely passed. 4 decimals belonged to the prior
  sentence and were genuinely uncited.
- MEDIUM: `_next_real_sentence_end` regex only matched `.!?` followed by
  whitespace or EOL. `.[N]` (period immediately before citation bracket)
  was not matched as a sentence terminator, so the helper would fall
  back to the 150-char cap.
- MEDIUM: test coverage gap — no counter-test for sentence-final
  abbreviations or citation-adjacent boundaries.

## Pass-2 changes (commit `d6a66a8`)

1. Abbreviation list split into two buckets in
   `src/polaris_graph/evaluator/external_evaluator.py`:
   - `_PT11_ALWAYS_NONBOUNDARY` (vs, v, etc, cf, viz, Dr, Mr, Mrs, Ms,
     Prof, Sr, Jr, Rev): period is NEVER a sentence end.
   - `_PT11_CONTEXT_DEPENDENT` (Fig, Figs, Ref, Refs, Eq, Eqs, No, Nos,
     pp, Vol, Ch, Sec, App, Inc, Ltd, Co, Corp, Gov, Dept, Jan-Dec):
     boundary status resolved by the next non-whitespace char:
       - digit / `(` / `-` / `+` → non-boundary (e.g. "Fig. 3")
       - lowercase letter → non-boundary ("Inc. reported")
       - uppercase letter → boundary ("Jan. A separate claim")
       - end-of-string → boundary
2. Multi-segment acronyms (`e.g`, `i.e`, `U.S`, `U.K`, `E.U`) and
   `et al.` are still ALWAYS non-boundary.
3. Sentence-terminator regex widened to
   `[.!?](?=\s|$|\[)` so `.[N]` is matched.
4. `_skip_trailing_citation_brackets(text, pos)` helper walks past any
   `[...]` bracket sequence. Used by both `_next_real_sentence_end`
   (extends snippet to include trailing citation so PT11 finds it) and
   `_prev_real_sentence_end` (returns position of closing `]` so
   `back_text[last + 1:]` starts cleanly in the new sentence and does
   NOT leak the prior-sentence citation into the current sentence's
   scope — a false-positive source).

## Pass-2 test additions (+11 tests, now 28 total)

- `TestContextDependentDisambiguation`:
  - Jan. followed by capital → boundary (Codex blocker).
  - Jan. followed by digit → non-boundary ("Jan. 15, 2020").
  - Inc. before capital → boundary; before lowercase → non-boundary.
  - No./Fig. before digits → non-boundary.
  - vs. before capital → still non-boundary (ALWAYS bucket).
  - Dr. before proper noun → still non-boundary (title bucket).
- `TestCitationAdjacentBoundary`:
  - `sentence.[7] Next` → `_next_real_sentence_end` returns position
    past `]`, not just past `.`.
  - `First sentence.[1] Second` → `_prev_real_sentence_end` returns
    position of `]` of `[1]`.
- `TestPT11WithAbbreviations.test_pt11_does_not_accept_next_sentence_citation`:
  - End-to-end reproduction of the Codex-blocker case: 4+ decimals in
    "in Jan. A separate…Separately reports that tirzepatide is
    efficacious.[1]" must FAIL PT11 because the citation belongs to the
    next sentence, not the one with the decimals.

## Verifications

- `python -m pytest tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py` → 28 passed.
- `python -m pytest tests/polaris_graph/` → 735 passed.
- `PT11` on V19 real report (`outputs/full_scale_v19/clinical/clinical_tirzepatide_t2dm/report.md`) → `passed=True, details=''`.

## Your task

Re-verify the two pass-1 findings are closed:

1. Is the sentence-final-abbreviation blocker genuinely fixed? Does the
   new two-bucket disambiguation correctly distinguish "Jan. A..." from
   "Jan. 15..."? Any remaining edge cases that would over-relax PT11?

2. Is the `.[N]` terminator handling correct? Does the sentence-end
   pair of helpers correctly include trailing citations AND exclude
   them from the next sentence?

3. Any NEW blockers introduced by pass-2? (Splitting the abbreviation
   list, the context-sensitive lookup, the `_skip_trailing_citation_brackets`
   helper — any of these expose a path that passes PT11 on genuinely
   uncited decimals?)

4. Hard-coding check (unchanged): confirm no domain-specific terms
   leaked into the abbreviation lists.

## Files to review

- `src/polaris_graph/evaluator/external_evaluator.py` lines 59-180
  (new helpers + two-bucket abbreviation list).
- `src/polaris_graph/evaluator/external_evaluator.py` around PT11 loop
  (unchanged structure; just uses the new helpers).
- `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py` (full file).

## Verdict format

Write `outputs/codex_findings/m30_code_audit_pass2/findings.md` with:

```
# M-30 code audit — pass 2

VERDICT: READY | NOT_READY

## Blockers (fix before V20)
- none  OR  - <list>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If VERDICT is READY, V20 sweep launches next. If NOT_READY, Claude
fixes the blockers and dispatches pass 3.

## Scope

Audit ONLY the pass-1 → pass-2 diff (commit `d6a66a8`). Do NOT audit
M-28, M-29, other PT rules, or the V19 outline-decode failure (tracked
separately as task #8 / M-31).
