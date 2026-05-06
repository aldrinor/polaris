# Codex round 2 — M-LIVE-2 v2 (1 P0 + 4 P1 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `6e421cb` (pushed to origin/polaris)
- Brief format: `.codex/REVIEW_BRIEF_FORMAT_v2.md` (autoloop V3)
- Driver output: `outputs/m_live_2_beat_both/manifest.json`

## R1 findings (all 5 closed in v2)

**R1 P0 — Driver hard-coded pre-M-LIVE-1-v2 path:**
- Fix: `_find_latest_polaris_manifest_path()` discovers latest
  `run_<timestamp>/.../manifest.json`; falls back to
  `tests/fixtures/m_live_4_baseline/`.

**R1 P1 #1 — _SECTION_HEADER_RE too greedy:**
- v1: matched any short uppercase line; ChatGPT scored 145
- v2: requires Markdown `#{1,4}` heading prefix; ChatGPT=0,
  POLARIS=6 → BEAT-BOTH

**R1 P1 #2 — narrative_length / contradiction_handling dead:**
- v1: scorers read `report.body`, only populated
  `narrative_word_count` → both 0 across all 3
- v2: populate `report.body` for POLARIS (report.md) +
  competitors (raw prose) → POLARIS 2120/2, ChatGPT 4830/27,
  Gemini 6835/18

**R1 P1 #3 — claim_frames structurally dead:**
- v1: scored TIE 0/0/0 — meaningless
- v2: verdict logic emits "N/A" when all 3 are 0.0 →
  honest signal that the dimension isn't measurable on
  current extraction

**R1 P1 #4 — Citations bag cross-poisons 3 dimensions:**
- v1: synthetic regulatory proxy URLs from text mentions
  (FDA/EMA/Health Canada → fake URLs) injected into the same
  citations bag feeding unique + regulatory + jurisdictional
- v2: drop proxy injection. Competitors that don't cite
  regulatory URLs explicitly score lower on regulatory_coverage
  — the correct comparative signal.

## v2 empirical result

| Dimension | POLARIS | ChatGPT | Gemini | Verdict |
|---|---:|---:|---:|---|
| structural_depth | 6 | 0 | 0 | BEAT-BOTH |
| jurisdictional_precision | 1 | 2 | 2 | TIE |
| unique_citations | 30 | 20 | 43 | BEHIND |
| regulatory_coverage | 1 | 4 | 10 | BEHIND-BOTH |
| narrative_length | 2120 | 4830 | 6835 | BEHIND-BOTH |
| contradiction_handling_grammar | 2 | 27 | 18 | BEHIND-BOTH |
| claim_frames | 0 | 0 | 0 | N/A |

Summary: 1 BEAT-BOTH, 0 BEAT-ONE, 1 TIE, 1 BEHIND,
3 BEHIND-BOTH, 1 N/A.

(Note: this is M-LIVE-1 SMOKE input with lean retrieval —
PG_SWEEP_MAX_SERPER=10. Full-scale POLARIS run is expected to
close most BEHIND-BOTH gaps. M-PROD-1 will run that.)

## Tool hints
- `python scripts/run_m_live_2_beat_both.py` → fresh run
- Read driver: `scripts/run_m_live_2_beat_both.py`
- Read extractor:
  `src/polaris_graph/audit_ir/competitor_manifest_extractor.py`
- Do NOT re-litigate R1 findings already addressed

## Acceptance bar (v2 — unchanged from v1)
1. 3 score_run + 2 diff_dimension_scores called (verifiable in
   manifest.json)
2. Per-dimension verdicts for all 7 BEAT-BOTH dimensions
3. Extraction is deterministic (same input → same output)
4. Manifest written to `outputs/m_live_2_beat_both/manifest.json`

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly — do not manufacture findings.
- Do NOT re-raise R1 findings. In-scope: regressions in v2 +
  P0/P1 missed in R1.

## Skepticism gate
Before declaring a verdict, list:
- which files you read + line ranges
- which acceptance criteria you confirmed evidence for
- which R1 findings you verified are closed in v2

## Anti-nits (do NOT flag)
- Prose grammar / formatting / docstring style
- R1 findings already addressed
- Architectural decisions explicitly documented as out-of-scope
  (e.g., claim_frames LLM-extraction, full-scale comparison)

## Verdict format
```
## Files scanned
## R1 findings closure verification
## Acceptance bar verification (v2)
## Findings (NEW only — exclude R1 already addressed)
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict
APPROVE | REQUEST_CHANGES
```

## Round metadata
This is round 2 of 5. v2 patch touches:
- Driver: path discovery + report.body + N/A verdict logic
- Extractor: tightened section regex + dropped regulatory
  proxies + populated report.body in output

R1 findings should not be re-raised. In-scope: regressions in
v2 patch + P0/P1 missed in R1.
