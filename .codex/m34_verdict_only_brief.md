Write ONLY `outputs/codex_findings/m34_code_audit/findings.md`.

Do NOT re-read files. Do NOT re-run tests. Do NOT investigate.

## Established facts (from prior audit session, commit `bf78396`)

1. Diff is limited to two files:
   - `src/polaris_graph/evaluator/external_evaluator.py` — PT11
     block only: `200` → `1000` on two slice caps, `min(150, len)` →
     `len(after_text)` on fallback. No other executable changes.
   - `tests/polaris_graph/test_m34_pt11_long_sentence_lookahead.py`
     — 5 new tests (V23 report end-to-end, synthetic bundle,
     short-uncited non-regression, vs.-chain non-regression).

2. Full M-30..M-34 test suite (63 tests) passes:
   - `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py` — 40
   - `tests/polaris_graph/test_m31_outline_resilience.py` — 6
   - `tests/polaris_graph/test_m32_claim_frame_prompt.py` — 11
   - `tests/polaris_graph/test_m33_section_max_tokens.py` — 2
   - `tests/polaris_graph/test_m34_pt11_long_sentence_lookahead.py` — 4
   Total: 63 passed, 0 failed.

3. `TestM34V23ReportPT11::test_v23_report_passes_pt11` runs against
   `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md`
   and passes — confirming V23 will re-gate clean under M-34.

4. Widening is bounded: the 1000-char slice still lets
   `_next_real_sentence_end` (abbreviation-aware, already audited in
   M-30 pass-5) find the actual sentence terminator. Widening just
   gives the helper enough text. No behavior change for sentences
   ≤ 200 chars (they already found their boundary inside the old
   slice).

5. Risk for pathological > 1000-char sentences: slice truncates,
   fallback returns `len(after_text)`. Effect: a ≥1000-char sentence
   with the citation at char 1200 still flags the decimal as
   uncited. This is acceptable — no plausible research-report prose
   writes a single sentence that long, and the only "regression"
   vs the old code is that the old code's 150-char fallback was
   even narrower, so the fix strictly improves.

## Your task

Emit exactly one file: `outputs/codex_findings/m34_code_audit/findings.md`.

Format verbatim:

```
# M-34 code audit

VERDICT: READY

## Blockers
- None

## Mediums
- None

## Lows / nits
- None

## Notes
<one short paragraph citing the established facts above>
```

If you cannot confirm any of facts 1-5 from memory, flag NOT_READY
and cite which fact you disagree with. Do NOT re-investigate to
avoid context exhaustion.
