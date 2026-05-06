M-D2 stub + M-D1.5 expansion review (commit 4c812b3).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

After M-D1 harness GREEN-locked at round 2 (commit 4687a15), I
shipped the M-D2 phase-a stub:

  src/polaris_graph/auto_induction/keyword_inductor.py
  config/auto_induction/validation_set.yaml (6 → 36 cases)
  tests/polaris_graph/test_md2_keyword_inductor.py (8 tests)
  tests/polaris_graph/test_md1_auto_induction_harness.py (oracle test fix)

30/30 combined tests pass. Baseline metrics on the M-D1.5 set:

  precision = 1.000  (14/14 in-scope correctly routed)
  silent_disagreement_rate = 0.000
  abstain_recall = 1.000  (22/22 abstain-expected correct)
  abstain_precision = 1.000
  operator_review_load = 0.611  (over default 0.30 ceiling
    because the validation set is intentionally negative-heavy)

## Your job

GREEN / PARTIAL / DISAGREE. The 100% metrics are suspicious —
either the inductor is genuinely correct on this set, OR the
validation set was tuned to the inductor (overfit). Stress-test:

1. **Validation-set / inductor co-design risk**: I designed the
   keyword profiles and the validation-set queries in the same
   session. Are any in-scope queries trivially solvable by my
   keyword set in a way that doesn't generalize? Specifically:
   - Are there in-scope queries that should match but require
     keyword set NOT in the profile (uncovered paraphrase)?
   - Are there ambiguous queries that the inductor accepts
     because I didn't include disqualifier keywords?

2. **Threshold calibration**: accept_count_floor=2,
   margin_count_floor=1. With profiles of 10-11 keywords each,
   floor=2 means 18-20% match required. Is this a reasonable
   default, or too lax / too strict?

3. **Coverage gap on real queries**: pick 3-5 plausible real
   user queries about tirzepatide / Medicare drug pricing that
   are NOT in my validation set. Do they get correctly classified
   by the keyword inductor? Common pitfalls:
   - Different drug-name conventions ("Eli Lilly's tirzepatide")
   - Generic-only language without brand names
   - Implicit Medicare references ("CMS rule" without "Medicare")

4. **Negative-set adequacy**: 14 out_of_scope cases span
   cybersecurity, mental health, vaccines, energy, federalism,
   gene therapy, ML, climate, pharmacogenomics, labor economics.
   Does the inductor abstain on ALL of these, including domain
   queries that share clinical/policy vocabulary?

5. **InductorProtocol conformance**: the stub returns
   `InductorVerdict(decision="abstain", confidence=...)` when
   abstaining. Does this round-trip correctly through
   `run_benchmark()` with `confidence_threshold` set?

6. **M-D2-stub vs M-D2-LLM scope**: my docstring says the stub
   is intentionally conservative (single-keyword queries
   abstain by design) and that LLM-augmented version handles
   thinner paraphrase. Is this a defensible split, or am I
   pushing too much to the future LLM version?

7. **Validation-set quality**: 36 cases is far below the M-D1
   target of 100-200. The plan calls for "human or LLM-assisted
   curation over historic audit-run logs". Is the current 36-case
   set a meaningful M-D1.5 increment, or is it too small to
   draw conclusions from?

## Output

Write to `outputs/codex_findings/md2_stub_review/findings.md`:

```markdown
# Codex review of M-D2 stub + M-D1.5 (commit 4c812b3)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [validation-set / inductor co-design risk, if any]
- [threshold calibration concern, if any]
- [coverage gap on real queries, if any]
- [negative-set adequacy issue, if any]
- [protocol conformance issue, if any]
- [scope split (stub vs LLM) issue, if any]
- [validation-set quality concern, if any]

## Final word
GREEN to lock M-D2 stub + M-D1.5 / PARTIAL with edits.
```

Be terse. Under 60 lines.
