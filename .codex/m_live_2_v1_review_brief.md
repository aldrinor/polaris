# Codex round 1 — M-LIVE-2 v1 (BEAT-BOTH head-to-head driver)

## Pre-flight
- Branch: `polaris`
- Commit: `8668d51`
- New files:
  - `src/polaris_graph/audit_ir/competitor_manifest_extractor.py`
    (extractor: prose → manifest dict)
  - `scripts/run_m_live_2_beat_both.py` (driver: 3 score_run +
    2 diff_dimension_scores + per-dimension verdict)
- Driver output: `outputs/m_live_2_beat_both/manifest.json`

## Scope
M-LIVE-2 substrate per `docs/full_online_plan_FINAL.md` Phase F.
Compares POLARIS run vs ChatGPT DR + Gemini DR on the 7
M-D9 BEAT-BOTH dimensions.

## Tool hints
- Run driver: `python scripts/run_m_live_2_beat_both.py`
- Read driver source: `scripts/run_m_live_2_beat_both.py`
- Read extractor source:
  `src/polaris_graph/audit_ir/competitor_manifest_extractor.py`
- Read scoring contract:
  `src/polaris_graph/audit_ir/beat_both_scoring.py:737-858`
- Inputs:
  - `outputs/m_live_1_smoke/clinical/clinical_tirzepatide_t2dm/`
    (POLARIS run; SMOKE config — see Caveats below)
  - `state/compare_chatgpt_dr.txt`
  - `state/compare_gemini_dr.txt`

## Acceptance bar
1. **3 score_run + 2 diff_dimension_scores called** (per FINAL_PLAN
   spec). Verifiable in `manifest.json`: keys
   `polaris_scores`, `chatgpt_scores`, `gemini_scores`,
   `polaris_vs_chatgpt_verdict`, `polaris_vs_gemini_verdict`.
2. **Per-dimension verdict for all 7 BEAT-BOTH dimensions**:
   BEAT-BOTH / BEAT-ONE / TIE / BEHIND / BEHIND-BOTH classifications
   present in `per_dimension_verdicts` for `claim_frames`,
   `contradiction_handling_grammar`, `jurisdictional_precision`,
   `narrative_length`, `regulatory_coverage`, `structural_depth`,
   `unique_citations`.
3. **Extraction risk surfaced**: per FINAL_PLAN M-LIVE-2 risk —
   "extraction normalization can invalidate verdict". Verify the
   extractor's output is reproducible (same input → same output)
   and per-dimension extraction is independent (one extractor's
   error doesn't pollute other dimensions).
4. **Manifest written**: `outputs/m_live_2_beat_both/manifest.json`
   contains the canonical per-dimension breakdown.

## Severity rubric
- **P0** — production-breaker: driver crashes; verdict math wrong;
  extractor reads competitor data into wrong fields (cross-poison)
- **P1** — phase-rework: acceptance bar criterion not met;
  extractor produces wildly skewed counts that obviously
  invalidate the verdict (e.g. structural_depth=145 for ChatGPT
  looks suspicious — re-extract and confirm or refute)
- **P2** — governance precision: extractor handles edge cases
  poorly but doesn't change verdict outcome
- **P3** — polish: regex tuning, comment clarity

**APPROVE iff zero P0 + zero P1.** P2/P3 → `deferred_polish`,
non-blocking.

## Empirical v1 result (against M-LIVE-1 SMOKE manifest)

| Dimension | POLARIS | ChatGPT | Gemini | Verdict |
|---|---:|---:|---:|---|
| unique_citations | 30 | 22 | 45 | BEHIND |
| regulatory_coverage | 1 | 6 | 11 | BEHIND-BOTH |
| jurisdictional_precision | 1 | 2 | 2 | TIE |
| structural_depth | 6 | 145 | 59 | BEHIND-BOTH |
| claim_frames | 0 | 0 | 0 | TIE |
| narrative_length | 0 | 0 | 0 | TIE |
| contradiction_handling_grammar | 0 | 0 | 0 | TIE |

Summary: 0 BEAT-BOTH, 4 TIE, 1 BEHIND, 2 BEHIND-BOTH.

## Caveats (in scope for review)

1. **POLARIS input is the M-LIVE-1 SMOKE run, not full-scale.**
   Smoke knobs: `PG_SWEEP_MAX_SERPER=10` (vs production 50),
   `PG_LIVE_MAX_EV_TO_GEN=30` (vs 300), `PG_SWEEP_FETCH_CAP=30`
   (vs 500). A shippable BEAT-BOTH verdict requires a full-scale
   run.

2. **Extractor precision concerns:**
   - `structural_depth=145` for ChatGPT looks high — the
     `_SECTION_HEADER_RE` matches ANY uppercase line; competitor
     prose has many footnote numbers and ALL-CAPS headers that
     trigger false positives.
   - `claim_frames=0` everywhere — extractor doesn't parse
     N+baseline+endpoint+CI from prose well. This is a known
     limitation; needs prompt-style extraction for v2.
   - `narrative_length=0` everywhere — `_NarrativeLengthScorer`
     looks at a specific manifest path that none of our 3
     manifests populate uniformly.

3. **Per FINAL_PLAN M-LIVE-2:** "Codex review independently
   re-extracts competitor manifests; reconcile if disagreement."
   Codex should run the extractor itself, compare its results to
   the committed `outputs/m_live_2_beat_both/manifest.json`, and
   flag any divergence as P1 (extraction non-determinism).

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write **"no P0/P1 found"**
  explicitly — do not manufacture findings.
- Run the driver yourself: `python scripts/run_m_live_2_beat_both.py`.
  Compare its output to the committed manifest. Disagreement = P1.
- Verify extractor is deterministic: run extraction on the same
  competitor file twice, confirm byte-identical output.

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- Suggestions to "consider using LLM-based extraction instead of
  regex" — that's a Phase G design decision, not v1 scope
- Per-regex precision suggestions without functional impact

## Verdict format
```
## Files scanned
- path:line-range
- ...

## Acceptance bar verification
- Criterion 1 [3 score_run + 2 diff calls]: <evidence or NONE>
- Criterion 2 [7 dimension verdicts]: <evidence or NONE>
- Criterion 3 [extraction reproducibility]: <evidence or NONE>
- Criterion 4 [manifest written]: <evidence or NONE>

## Findings

### P0 (blocking)
- [file:line] description

### P1 (blocking)
- [file:line] description

### deferred_polish (P2/P3, non-blocking)
- [file:line] description

## Verdict
APPROVE | REQUEST_CHANGES

Convergence: APPROVE iff zero P0 + zero P1.
```

## Round metadata
This is round 1. Round-2+ findings must be either (a)
regressions in v(N) patch or (b) P0/P1 missed in R1.
Hard iter cap: 5 rounds.
