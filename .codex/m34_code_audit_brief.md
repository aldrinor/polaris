You are auditing M-34 (PT11 lookahead-window widen: 200→1000 chars)
as a code review. V23 full-scale already ran; the goal is to re-gate
the existing V23 report.md with the M-34 evaluator change — no
re-generation, no re-sweep.

## Scope discipline

Audit ONLY the diff introduced by commit `bf78396`. Two files:

1. `src/polaris_graph/evaluator/external_evaluator.py`
   — inside PT11 block, the `after_text`/`back_text` slice bounds
   and None-fallback for `_next_real_sentence_end`.
2. `tests/polaris_graph/test_m34_pt11_long_sentence_lookahead.py`
   — 5 tests.

Do NOT invent probe patterns. Do NOT expand scope beyond these two
files.

## Context

V23 actual-size full-scale sweep completed in 114 min with:
- status=abort_evaluator_critical
- release_allowed=false
- rule_blockers=["PT11"]
- evaluator_rule_checks: PT11 says "3 numeric claims without adjacent
  citation marker (out of 36 decimals in prose)."
- Qwen 5/5 GOOD; all other 11 rules pass; PT13 advisory (not blocker)

Inspection of V23 report.md isolated the three uncited decimals. All
three appear in LONG sentences (300-450 chars) whose terminating
`[N]` citation sits past the 200-char lookahead window that PT11
used. One example:

    "A systematic review and network meta-analysis of subcutaneous
    GLP-1 receptor agonists and tirzepatide concluded that all
    tirzepatide doses were comparable to semaglutide 2.0 mg and
    superior to semaglutide 1.0 mg and 0.5 mg in reducing HbA1c,
    and that tirzepatide 15 mg, 10 mg, and 5 mg demonstrated
    greater weight loss efficacy than semaglutide 2.0 mg, 1.0 mg,
    and 0.5 mg, respectively.[5]"

Decimal "2.0" at char ~95; citation "[5]" at char ~440. The 200-char
window truncates before `[5]`. Same pattern for the other two
(FDA/NICE dosing sentences).

## Changes

### Production code (external_evaluator.py)

Before:
```python
after_text = text_stripped[m.end():m.end() + 200]
lookahead_end = _next_real_sentence_end(after_text)
if lookahead_end is None:
    lookahead_end = min(150, len(after_text))
...
back_text = text_stripped[max(0, m.start() - 200):m.start()]
```

After:
```python
after_text = text_stripped[m.end():m.end() + 1000]
lookahead_end = _next_real_sentence_end(after_text)
if lookahead_end is None:
    lookahead_end = len(after_text)
...
back_text = text_stripped[max(0, m.start() - 1000):m.start()]
```

### Tests

5 new in `test_m34_pt11_long_sentence_lookahead.py`:
1. `TestM34V23ReportPT11::test_v23_report_passes_pt11` — end-to-end
   against `outputs/full_scale_v23/.../report.md`. Skips if file
   absent. Assert PT11 passes.
2. `TestM34LongSentenceSyntheticBundle::test_mixed_bundle_passes_under_m34`
   — bundle of 3 V23-shape long sentences + filler, assert PT11 passes.
3. `TestM34Nonregressions::test_short_uncited_sentence_still_fails`
   — many decimals / no citations → still fails PT11.
4. `TestM34Nonregressions::test_vs_decimal_chain_still_works` — M-30
   non-regression for `vs.`-chained decimals with trailing citation.
5. (Implicit) M-30 abbreviation test suite still passes — 63/63 total
   M-30..M-34 tests.

## Your task

1. Read the PT11 diff. Confirm it is exactly two cap changes (200→1000,
   200→1000) plus one fallback change (`min(150, ...)` → `len(...)`).
   No other executable changes.

2. Reason about the widening: is 1000 chars safe? What are the
   boundaries it could cross incorrectly? Specifically:
   - Could the wider window scan PAST a real sentence boundary and
     pick up a citation belonging to the NEXT sentence?
     (Answer should be NO because `_next_real_sentence_end` is
     called on the slice and returns the first real terminator — the
     widening just gives the helper enough text to find one.)
   - Is there a path where N≥1000-char sentences exist? If so, the
     slice still truncates and the fallback now returns
     `len(after_text)`. Evaluate whether that could mis-count for a
     pathological run.

3. Run the M-30..M-34 suite:
   `python -m pytest -q tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py tests/polaris_graph/test_m31_outline_resilience.py tests/polaris_graph/test_m32_claim_frame_prompt.py tests/polaris_graph/test_m33_section_max_tokens.py tests/polaris_graph/test_m34_pt11_long_sentence_lookahead.py`
   Report pass/fail counts.

4. Confirm V23 would re-gate clean under M-34. Path:
   `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md`
   has 36 decimals with 3 uncited under old code. Under M-34 it
   should show 0 uncited (the 3 offenders now fall inside the
   widened lookahead). Either call `run_rule_checks` directly or
   run `TestM34V23ReportPT11::test_v23_report_passes_pt11`.

5. Scope check: do NOT touch the V23 manifest.json or sweep_summary
   files in this pass. That's the re-gate step, tracked separately.

## Out of scope

- The pending task "Refactor PT11 to sentence-containment check" —
  acknowledged as the long-term fix; M-34 is the tactical patch.
- The PT13 advisory reasons — not a blocker.
- V23 narrative-depth vs ChatGPT DR / Gemini DR — that's Codex DR
  pass 11's job, post-regate.

## Verdict format

Write `outputs/codex_findings/m34_code_audit/findings.md`:

```
# M-34 code audit

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<pytest pass count, re-gate prediction, any observations>
```

If READY, proceed to re-gate V23 (update manifest.json,
evaluator_rule_checks.json, sweep_summary files) via a narrow
scripted update, then launch Codex DR output audit pass 11.
