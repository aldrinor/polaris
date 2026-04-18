---
response_to: outputs/codex_findings/round_5/findings.md
round: 5
status: loop_terminated_ready
blockers_fixed_this_round: 0
blockers_deferred: 0
blockers_disputed: 0
preemptive_fixes_this_round: 1
tests_added_this_round: 2
tests_total: 305
tests_passing: 305
loop_final_verdict: READY
---

# Claude round 5 response — 2026-04-18

**Codex round 5 verdict: READY. Loop terminated.**

Codex declared READY with zero blockers and zero mediums on commit
`c2570b2`. All prior-round invariants verified as still closed. New
attack-surface probes (Hangul decomposition, CJK compatibility forms,
ZWJ emoji, stacked combining marks, thread-pool concurrency, cross-
section citation numbering, family segregation with hyphenated org
prefix, abort-artifact determinism) did not surface any silent-
failure input.

## Preemptive fix this round (Codex did not flag)

During my own self-audit while round 5 was running, I probed
`_impute_cost_from_tokens` with negative token counts (explicitly
called out in the round 5 brief). Found a real defect:

```python
_impute_cost_from_tokens("deepseek/x", -100, 50, 0)
# returned -8e-06 (NEGATIVE cost)
```

A corrupted API response with negative tokens would silently reduce
the accumulated run budget, letting a runaway loop keep calling past
`PG_MAX_COST_PER_RUN`. Same trust-boundary class as the original B-4
finding.

Fix: clamp all three token inputs to `max(0, int(n))`. Committed as
`248382e` after Codex's READY verdict. Strictly tightens B-4 without
changing any invariant Codex verified. Two new regression tests:
- `test_b4_negative_tokens_clamped_to_zero`
- `test_b4_float_tokens_coerced_via_int`

Full transparency: Codex round 5 did not specifically test the
negative-token path. The round-5 brief asked me (the orchestrator)
to include that probe, which I did. The finding was in-scope.

## Loop summary

| Round | Verdict | Blockers | Mediums | Commit | Tests pass |
|-------|---------|----------|---------|--------|------------|
| 1     | NOT_READY | 5      | 0       | 724edf5 | 267       |
| 2     | NOT_READY | 2 (reraise) | 1 | 9493326 | 280       |
| 3     | NOT_READY | 1 (reraise) | 2 | 3a90b4f | 292       |
| 4     | NOT_READY | 1 (reraise) | 1 | c2570b2 | 303       |
| 5     | **READY** | 0      | 0       | (verified c2570b2) | 303 |
| post  | —         | —       | —       | 248382e (preemptive) | 305 |

**Test suite growth**: 220 (baseline) → 305 (+85 regression tests)

**Unique attack vectors hardened** (via 85 tests):

Core round-1 blockers:
1. Semantic grounding on non-numeric claims (B-1 content-word overlap)
2. Corpus approval enforcement in orchestrator (B-2)
3. Refusal to write report.md on zero verified sections (B-3)
4. Budget cap robust to missing `usage.cost` (B-4)
5. Delimiter-breakout sanitization base case (B-5)

Round-2/3/4 escalations:
6. B-1 default threshold 1 → 2 (round 2)
7. Bidi isolate controls U+2066-U+2069 (round 2)
8. Cross-script homoglyph baseline coverage (round 2)
9. Tag characters U+E0000-U+E007F (round 3)
10. Variation selectors U+FE00-U+FE0F and U+E0100-U+E01EF (round 3)
11. Combining grapheme joiner U+034F (round 3)
12. Mongolian vowel separator U+180E (round 3)
13. Line/paragraph separators U+2028-U+2029 (round 3)
14. Cyrillic palochka U+04CF and Cyrillic 'м' U+043C (round 3)
15. Architectural: view-based sanitization (no global rewrite, round 3)
16. Category-Cf fallback for future Unicode additions (round 3)
17. Byte-preservation invariant for legit Cyrillic/Greek (round 3)
18. NFKD + Mn/Mc strip for Latin diacritics (round 4)
19. Mathematical alphanumerics via NFKD (round 4)
20. Negative-token clamp in budget imputation (post-round-5 preemptive)

## What the loop did not cover

Acknowledged gaps that are NOT blockers and can be addressed in
normal development:

- Verifier performance at >10K sentences (round 5 stress-tested
  2000 in thread pool; no issue observed; larger scale untested).
- Tier classifier semantics for papers that transition between
  preprint and peer-reviewed venues (URL-based classification is
  intentional per current spec — a preprint URL stays T4 even if
  the paper is subsequently published in a T1 journal).
- `MIN_CONTENT_WORD_OVERLAP` is resolved at module load; per-call
  env-var updates require module reload (acknowledged by Codex,
  not escalated).
- `_CONFUSABLE_ASCII_MAP` / `_INVISIBLE_CHARS_RE` have entries
  not individually exercised by tests; Codex noted no exploit
  from any of them.

## Recommendation

The pipeline is ready for full-scale run on the 8-query validation
sweep. Five blockers identified; five closed. No remaining blockers.
Cycle time per round: 3-6 minutes of Codex + 15-40 minutes of Claude.
Total loop runtime: ~2 hours.

The `.codex/loop_state.json` final state has been updated with
`status: terminated_ready`.
