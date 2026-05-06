# Codex round 4 — M-LIVE-2 v4 (R3 P1 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `0d5281a`
- Brief format: lean autoloop V3

## R3 closure
**R3 P1 [extraction asymmetry off-by-1]:**
- v3 inlined `_SECTION_HEADER_RE` regex directly but skipped
  `_extract_sections()`'s filters (≤80 char + non-digit-only).
  POLARIS 132-char H1 was counted by v3, dropped by competitor
  rules → off-by-1 overstating POLARIS by 1 section.
- v4 fix: call `_extract_sections()` and `_extract_tables()`
  helpers DIRECTLY. Now both sides pass through the same code
  path — identical extraction semantics.

POLARIS structural_depth: 29 (v3) → 28 (v4). Matches Codex R3's
own count.

## Round summary so far
- R1: REQUEST_CHANGES — 1 P0 + 4 P1
- R2: REQUEST_CHANGES — 0 P0 + 2 P1
- R3: REQUEST_CHANGES — 0 P0 + 1 P1 (R1+R2 verified closed)
- R4: ?

8 findings closed across 3 rounds. Each round narrower. Round 4
of 5 hard cap.

## Acceptance bar (unchanged from prior rounds)
1. 3 score_run + 2 diff_dimension_scores
2. Per-dimension verdicts for all 7 BEAT-BOTH dimensions
3. Deterministic extraction (now using shared helpers)
4. Manifest written to `outputs/m_live_2_beat_both/manifest.json`

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1/R2/R3 findings already addressed.

## Skepticism gate
List which files you read + line ranges + which closures you
verified.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- Findings already addressed
- Test coverage (deferred to v5)

## Verdict format
```
## Files scanned
## R1+R2+R3 closure verification
## Acceptance bar verification
## Findings (NEW only)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 4 of 5 hard cap.
