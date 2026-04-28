# M-D9 phase 2 — BEAT-BOTH dimension scoring boundary

**Status:** v2 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/beat_both_scoring.py`
**Tests:** `tests/polaris_graph/test_md9_phase2_beat_both.py` (43 passing)
**Pairs with:** M-D9 phase 1 (`regression_lab.py`, commit 8abf160) —
the new module is independent but consumers can integrate via
`report_to_exit_code` matching the same convention.
**Substrate:** stdlib only — no LLM clients, no live HTTP, no DB.

---

## Scope

M-D9 phase 1 ships pin diff + induction-precision diff +
manifest-verdict diff. Phase 2 adds **per-dimension regression
scoring** for the 7 BEAT-BOTH dimensions documented in
`state/v17_vs_tier1_headtohead.md` and the locked memory
`autoloop_beat_tier1_mandate.md`.

The 7 dimensions:
  1. `unique_citations` — distinct URL count
  2. `regulatory_coverage` — FDA/EMA/HC/NICE source count
  3. `jurisdictional_precision` — distinct jurisdictions named
  4. `claim_frames` — claims with N + baseline + endpoint + CI
  5. `structural_depth` — table count + sub-section count
  6. `contradiction_handling_grammar` — contrast marker count
  7. `narrative_length` — body-prose word count

Each dimension has a default tolerance (env-overridable per LAW
VI) and a direction flag (all 7 are `higher_is_better=True`).

Phase 2 v1 ships:
  - `BeatBothDimension` enum (closed taxonomy of the 7)
  - `DimensionScore` dataclass + `DimensionScorer` Protocol
  - 7 concrete scorers in `BEAT_BOTH_SCORERS`
  - `score_run(manifest, *, scorers)` — pure derivation
  - `DimensionRegression` + `BeatBothReport` + `BeatBothVerdict`
  - `diff_dimension_scores(baseline, current, *, tolerances)`
  - `report_to_exit_code(report)` — RED → 1, GREEN/YELLOW → 0

Phase 2 v2 (deferred):
  - Dimension-class trend analysis (rolling-window regression)
  - Tolerance auto-calibration against run history
  - Direct integration into `regression_lab.diff_regression`
    (today they're parallel; v2 may merge into one report)
  - Real Crossref/PubMed-aware regulatory regex updates

---

## Phase 2 v1 boundaries

### 1. Pure derivation — no I/O, no LLM, no HTTP

`beat_both_scoring.py` imports only stdlib + (transitively)
typing. No LLM clients, no live HTTP, no DB, no file I/O. Every
public function is deterministic given the same input dict.

The "M-D9 phase 2 = pure derivation" boundary mirrors M-D11
phase 2 (pin replay) and M-D7 phase 1 (cache substrate) — the
substrate primitives never touch runtime services.

**Mitigation**: integration points (e.g. running `score_run` on
a freshly-completed pipeline manifest, then comparing against a
pinned baseline) live in caller code (M-D9 phase 1's
regression_lab consumers, or future M-D9 phase 2 v2 glue).

### 2. Phase 2 scores AGAINST a baseline pin, NOT competitors

The user-mandated stop criterion (per
`autoloop_beat_tier1_mandate.md`) is "V_N beats both ChatGPT
DR + Gemini 3.1 Pro DR on the 7 dimensions". That's a
**live-audit** comparison performed by Codex during
end-of-cycle reviews from V19 onward.

Phase 2 here is the **regression-substrate** layer underneath
that mandate: detects per-dimension content-shape *regressions*
between two POLARIS runs (typically baseline pin vs current
release). It does NOT compute "beat ChatGPT today" — that
requires:
- Live competitor PDFs / extracts (`state/compare_*.txt`)
- Per-dimension head-to-head scoring against those PDFs
- A different verdict mandate (BEAT-BOTH / BEAT-ONE / BEHIND)

These are V19+ live-audit responsibilities; phase 2 here is the
deterministic scoring substrate the live audit might consume.

**Mitigation**: callers wanting "is V_N beating ChatGPT?"
should invoke `score_run` on V_N's manifest AND on a
ChatGPT-output-shaped manifest (extracted from
`state/compare_chatgpt_dr.txt`), then call
`diff_dimension_scores`. That's a one-liner the live audit can
do; the substrate enables it without baking the comparison into
this module.

### 3. Scorer Protocol is pluggable; defaults are deliberate

The 7 default scorers ship in `BEAT_BOTH_SCORERS`. Callers can
pass a custom `scorers=` tuple to `score_run` for:
- Custom dimensions (e.g. "contract_draft_count" via the
  `_ContractDraftCountScorer` test pattern)
- Different scoring algorithms for the same dimension
  (e.g. a regex-tightened regulatory_coverage that adds
  pharmacovigilance hosts when M-D6 ships)
- Lower=better dimensions (the Protocol supports both
  directions; only the 7 BEAT-BOTH happen to be higher=better)

**Mitigation**: `score_run` validates the contract — a scorer
that returns a wrong-dimension or wrong-direction
`DimensionScore` raises `BeatBothScoringError` immediately. This
is the same fail-loudly pattern as M-D5 phase 1's
`ScopeClassifierError` and M-D11 phase 1's pin validators.

### 4. Each scorer is defensive on missing manifest fields

Manifests vary across pipeline revisions. Rather than tightly
couple to one schema, each scorer probes well-known field paths
and returns 0.0 with a rationale when fields are missing:

- `_citation_urls` checks `citations`, `evidence`,
  `report.citations`, `report.evidence` — first non-empty wins,
  with cross-path dedup
- `_ClaimFramesScorer` checks `claims`, `verified_claims`,
  `report.claims`. v2 (Codex round-1 LOW fix): "complete claim"
  uses `key in claim and value is not None` rather than the v1
  truthy check, so a populated `baseline=0.0` (legitimate)
  counts as present, not missing.
- `_StructuralDepthScorer`: v2 (Codex round-1 MED fix) probes
  `tables` OR `report.tables` (first non-empty wins, NOT both)
  and `sections` OR `report.sections` separately. v1 summed
  both, double-counting when manifests mirrored fields at both
  levels.
- `_ContradictionHandlingScorer` and `_NarrativeLengthScorer`
  read `report.body` or `body`
- `_RegulatoryCoverageScorer`: v2 (Codex round-1 MED fix)
  parses the URL host and checks membership in
  `_REGULATORY_HOSTS` rather than regex-searching the full URL.
  v1 falsely scored `https://example.com/redirect?u=https://fda.gov/x`
  as regulatory; v2 only counts a URL if its actual host is
  regulatory.

**Mitigation**: if downstream pipelines ship manifest schema
v2 with new field names, scorers should be updated in v2 of
their respective scorer (not breaking changes — additive
field-path probes). Tests pin the current behavior at multiple
manifest shapes (rich, thin, empty).

### 5. Per-dimension tolerances are uncalibrated until run history accumulates

Default tolerances are conservative-strict — better to flag a
borderline regression than miss it. Defaults:
- `unique_citations`: 2
- `regulatory_coverage`: 1
- `jurisdictional_precision`: 1
- `claim_frames`: 5
- `structural_depth`: 1
- `contradiction_handling_grammar`: 2
- `narrative_length`: 100 words

Severity tiers (per `diff_dimension_scores`):
- `ok`: |regression_size| ≤ tolerance
- `minor`: tolerance < regression_size ≤ 2 × tolerance
- `major`: regression_size > 2 × tolerance → CI gate trips RED

These tolerances are **not empirically calibrated**. They're
educated guesses based on V17 vs tier-1 dimension counts. Once
a few months of POLARIS run history accumulate, M-D9 phase 2 v2
may auto-calibrate per-dimension tolerances against actual
inter-run variance.

**Mitigation**: env overrides (`PG_BEAT_BOTH_<DIM>_TOLERANCE`)
let operators tighten or relax per environment. Tests pin env
override + clamping behavior.

### 6. Regression direction is `higher_is_better`-aware, not magnitude-only

A regression is movement AGAINST the dimension's "good"
direction. For higher_is_better dimensions (all 7 BEAT-BOTH
defaults), a *drop* beyond tolerance is a regression; an
*increase* never is. For lower_is_better dimensions (custom
scorers like a hypothetical "duplicate_claim_count"),
opposite.

**Mitigation**: `diff_dimension_scores` raises if baseline +
current `higher_is_better` disagree (a sanity check — the
caller's scorer config is inconsistent). Tests cover both
directions explicitly.

### 7. Verdict is GREEN/YELLOW/RED — only RED gates CI

Same convention as M-D9 phase 1 `regression_lab.report_to_exit_code`:
- GREEN: 0 (merge OK)
- YELLOW: 0 (minor regressions only — operator review, no
  hard block)
- RED: 1 (major regression — block merge)

**Why YELLOW doesn't gate**: minor regressions might be
legitimate (e.g. a deliberate refactor that drops 2 citations
because the old ones were unreliable). The CI gate should only
fire on clear-magnitude regressions; YELLOW surfaces the
discussion to the operator.

**Mitigation**: callers wanting strict gating (e.g. a release
branch where YELLOW also blocks) can wrap `report_to_exit_code`
with their own logic — the substrate exposes the verdict
directly via `report.verdict`.

---

## Codex review trail

Round-1 brief incoming. Tool hints (per M-D5 / M-D3 lessons):
- Use `python -m pytest -q tests\polaris_graph\test_md9_phase2_beat_both.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- The 7 dimensions are pinned by `test_seven_beat_both_dimensions_present`

Targeted at 2-round convergence per the M-D7/M-D10/M-D3 pattern.

---

## Lock note

Phase 2 v1 GREEN-lock target after Codex round 1-2. v2 (trend
analysis, auto-calibration, regression_lab merge) tracked
separately under M-D9 phase 2 v2.
