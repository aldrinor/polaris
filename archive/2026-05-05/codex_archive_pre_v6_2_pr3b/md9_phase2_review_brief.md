M-D9 phase 2 v1 review (commit 28b0354).

**Tool hints (per M-D5/M-D3 lessons)**: use
`python -m pytest -q tests\polaris_graph\test_md9_phase2_beat_both.py`.
Skip `outputs/codex_*` and `.codex_tmp/` in `rg`.

## Context

Phase D M-D9 phase 2: BEAT-BOTH dimension scoring substrate.
8 phase D milestones already GREEN-LOCKED (M-D2 phase a/b,
M-D3 phase 1, M-D5 phase 1, M-D7 phase 1, M-D9 phase 1, M-D10
phase 1, M-D11 phase 1+2). Convergence pattern: 2-3 rounds when
threat-model ships with v1.

## What v1 ships

`src/polaris_graph/audit_ir/beat_both_scoring.py`:
  - BeatBothDimension enum: 7 dimensions per locked memory
    `autoloop_beat_tier1_mandate.md` and
    `state/v17_vs_tier1_headtohead.md`:
      unique_citations, regulatory_coverage,
      jurisdictional_precision, claim_frames, structural_depth,
      contradiction_handling_grammar, narrative_length
  - DimensionScore dataclass (value + higher_is_better +
    rationale)
  - DimensionScorer Protocol — pluggable; 7 default scorers
    ship in BEAT_BOTH_SCORERS
  - score_run(manifest, *, scorers): pure derivation;
    validates Protocol contract
  - DimensionRegression + BeatBothReport + BeatBothVerdict
    (GREEN/YELLOW/RED)
  - diff_dimension_scores: direction-aware (higher_is_better),
    severity tiers (ok / minor / major), tolerance via env or
    explicit override
  - report_to_exit_code: RED→1, GREEN/YELLOW→0

Phase 2 v1 SCOPE BOUNDARY (per advisor):
  - Scores AGAINST a baseline pin, NOT live competitors
  - Pure derivation — no LLM, no HTTP, no DB
  - V19+ live-audit consumes this; "beat ChatGPT" is V19+'s job

`tests/polaris_graph/test_md9_phase2_beat_both.py` — 39 tests:
  - 7 dimensions present + named correctly
  - score_run on rich, thin, empty manifests
  - Each scorer's value pinned (citations dedup, regulatory
    regex, jurisdiction map, claim-frame all-fields,
    structural depth tables+sections, contradiction markers,
    word count)
  - Citation extraction defensiveness (dict entries with
    url/source_url/doi/pmid, dedup across paths, non-string
    entries skipped)
  - Diff verdicts: GREEN (no change, within tolerance),
    YELLOW (minor regression), RED (major regression)
  - Direction-flip on lower=better custom dimension
  - Tolerance env override + clamp negative + invalid
    fallback
  - Custom scorer via Protocol
  - Contract violations (wrong dim name, wrong direction,
    non-DimensionScore return) fail loudly
  - CI exit code mapping for all 3 verdicts
  - Input contract on non-dict manifest

`docs/md9_phase2_threat_model.md` — 7 boundaries:
  1. Pure derivation — no I/O
  2. Phase 2 scores against baseline, NOT competitors
  3. Scorer Protocol pluggable; defaults are deliberate
  4. Each scorer defensive on missing fields
  5. Per-dimension tolerances uncalibrated until run history
  6. Direction-aware regression detection
  7. GREEN/YELLOW/RED with only RED gating CI

M-D suite: 372/372 (was 333; +39).

## Your job

GREEN-LOCK or PARTIAL.

1. **7 dimensions match locked memory**:
   - [ ] enum values match the memory list exactly
   - [ ] BEAT_BOTH_SCORERS has all 7 + each scorer's
     dimension matches its enum value
   - [ ] direction is higher_is_better=True for all 7

2. **Substrate correctness**:
   - [ ] score_run is pure (no I/O, deterministic)
   - [ ] each scorer is defensive on missing fields
   - [ ] Protocol contract enforced (3 distinct violation
     paths: wrong type return, wrong dimension name, wrong
     direction)
   - [ ] direction-aware regression detection works for both
     higher=better and lower=better dimensions

3. **CI gate readiness**:
   - [ ] severity tiers (ok/minor/major) computed correctly
     per advisor's "1x/2x tolerance" thresholds
   - [ ] only RED returns 1 (matches phase 1 convention)
   - [ ] env-overridable tolerances (LAW VI)

4. **Threat-model coherence**:
   - [ ] 7 boundaries match code (no v2-style drift)
   - [ ] boundary 2 explicitly notes phase 2 ≠ live competitor
     comparison
   - [ ] tool-hint preamble present

5. **Stop criterion**: GREEN-lock if remaining findings are
   minor (doc nits, test pin tightening). PARTIAL only if you
   find:
     (a) A dimension scorer that can crash on adversarial input
     (b) Direction logic flipped or mishandled
     (c) Severity tier boundary off-by-one (e.g. exactly at
         tolerance is mistakenly classified as regression)
     (d) CI exit-code semantics drift from phase 1 convention
     (e) Threat-model boundary contradicted by code

6. **Phase-2 readiness**: with v1 substrate, can phase 2 v2
   (trend analysis, auto-calibration, regression_lab merge)
   layer cleanly?

## Output

`outputs/codex_findings/md9_phase2_review/findings.md`:

```markdown
# Codex round 1 — M-D9 phase 2 v1 (commit 28b0354)

## Verdict
GREEN / PARTIAL / DISAGREE

## Coverage
- [x/no] 7 dimensions match locked memory
- [x/no] score_run pure + defensive + Protocol-validated
- [x/no] direction-aware diff (both directions)
- [x/no] severity tiers + CI exit code
- [x/no] threat-model 7 boundaries match code

## New findings (if any)
- [HIGH/MED/LOW] [...]

## Final word
GREEN to lock M-D9 phase 2 / PARTIAL with edits.
```

Be terse. Under 50 lines.
