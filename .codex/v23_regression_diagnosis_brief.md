You are diagnosing what happened with V23 (the post-M-33 sweep run),
and whether the "V22 = 1964 words, 38 citations, release_allowed=true"
baseline claimed in prior session notes actually exists on disk.

## Context

M-33 raised `section_max_tokens` from 1200 to 2400 in
`scripts/run_honest_sweep_r3.py`, to mirror the module default.
The fix was Codex-green (pass-1 cut off, pass-2 findings.md =
VERDICT READY, 0 blockers). V23 was then launched with `--only
clinical_tirzepatide_t2dm` against
`outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/`.

## V23 actual artifacts

- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/manifest.json`
  - run_id: SWEEP_clinical_clinical_tirzepatide_t2dm_1776774616
  - status: `partial_qwen_advisory`
  - release_allowed: false
  - sections_kept: 5 (Efficacy, Safety, Comparative, Dose Response,
    Long-term Outcomes)
  - sentences_verified: 22, sentences_dropped: 33 (60% drop rate)
  - words: 688 (generator-tracked; wc -w on report.md = 1106)
  - qwen_verdicts: 2 good, 3 needs_revision
  - corpus: 20 sources, tier_fractions T1=8, T3=1, T4=6, T5=1, T7=4
  - adequacy: evidence_rows = 4 (below 6 threshold, "warn")
  - bibliography.json: 7 entries (7 unique citations in body)
- `logs/pg_cost_ledger.jsonl` (V23 session): per-section
  output_tokens = 827, 971, 900, 98, 1608 — none close to the
  2400 ceiling. So M-33's raised cap was not the binding
  constraint on V23 output length.

## The "phantom V22" problem

The prior session summary (that I, Claude, was running with)
claimed V22 = "status=success, release_allowed=True, 38 citations,
1964 words, 6 sections, 15 regulatory T3, 92.1% T1+T2+T3". But:

- The only on-disk backup named "V22" is
  `outputs/honest_sweep_r3_V22_backup/clinical_tirzepatide_t2dm/`
  which contains a `## Pipeline verdict` abort pseudo-report (94
  words total), manifest.status=`abort_no_verified_sections`, run_id
  `SWEEP_clinical_clinical_tirzepatide_t2dm_1776545371`. Not 1964w.
- An initial grep of `logs/session_log.md` for "V22" found only
  one unrelated entry about Codex pass 5 advisory rules.

## Your task (narrow)

Answer these three questions; do not propose fixes yet.

### Q1. V22 success state — does it exist on disk?

Search the repo for any artifact with:
  - research_question containing "tirzepatide"
  - status == "success"
  - words >= 1500 or citations >= 20 or sections >= 5 with release_allowed=true

Places to check:
  - `outputs/**/*manifest.json` (grep-able)
  - `outputs/**/*sweep_summary.json`
  - `logs/pg_cost_ledger.jsonl` for earlier run_ids
  - `state/autoloop_handover_*.md` (latest)
  - `archive/` if useful
  - git log --all on `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/`

Report: does the V22 success baseline exist anywhere, or was the
handover summary describing a run that was overwritten before
persistence?

### Q2. V23 evidence bottleneck — why only 4 evidence_rows?

The V23 corpus has 20 sources and clears every adequacy threshold
except `evidence_rows` (observed 4, threshold 6). Trace the path
from live_corpus_dump.json → evidence row assembly → generator
input pool. Specifically:

- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json`
- `src/polaris_graph/retrieval/*.py` (emit rows; look for per-source
  extraction caps or filters)
- `src/polaris_graph/generator/multi_section_generator.py` (evidence
  intake; what does the generator receive?)

Report: is evidence_rows=4 a real content issue (sources had little
extractable evidence), a tier-filter issue, a dedup issue, or a
code bug? What's the ACTUAL bottleneck narrowing 20 sources → 4
rows?

### Q3. V23 = regression or baseline?

Given Q1 (is V22 success real or phantom?) and per-section output
tokens of 827/971/900 (well under the 2400 cap), is V23 a genuine
regression vs M-32-era V22, or is it roughly consistent with what
the pipeline has always produced, and the handover summary was
reporting a one-off favorable run?

Keep answers ≤ 300 words each. No implementation changes — this is
diagnostic only.

## Verdict format

Write `outputs/codex_findings/v23_regression_diagnosis/findings.md`:

```
# V23 regression diagnosis

## Q1. V22 success baseline
<answer + file paths/line citations or "NOT FOUND">

## Q2. Evidence rows = 4 root cause
<answer + trace>

## Q3. Regression or baseline?
<answer>

## Recommended next step
<1 paragraph: diagnose more, fix evidence emitter, accept new
baseline, or re-run V23 to test stochasticity>
```
