HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-citation-leak/codex_diff.patch` (2 files, +50/-6). NO SPEND.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR7: scrub bare [ev_NNN] citation-leak tokens (#946)

Verify the diff implements the brief-gate-APPROVE'd plan (brief APPROVE iter 1).

## What to verify
1. `_EV_TOKEN_RE` changed from `\[#ev:[^\]]*\]` to `\[#?ev[:_][^\]]*\]` — now matches `[#ev:...]` AND bare
   `[ev_012]` / `[ev_012:1-5]`, while the `[:_]` guard preserves numeric `[N]` markers and ordinary
   bracketed words `[event]`/`[evidence]` (next char is a letter, not `:`/`_`).
2. `_scrub_ev_tokens` docstring + WARN message updated to "ev-token ([#ev:...] or bare [ev_NNN])".
   Single chokepoint unchanged (called at analyst_synthesis.py:476 on synthesis text before report assembly).
3. Verified core untouched: `[N]` marker handling (`_scrub_invalid_n_markers`), strict_verify, provenance,
   the verified-findings layer's internal `[#ev:...]` → `[N]` conversion.

## Evidence (verified by Claude main-thread, NO SPEND)
- 44 tests PASS (test_analyst_synthesis.py + test_analyst_synthesis_safety.py), incl. 6 NEW: bare `[ev_012]`
  scrubbed; bare with span `[ev_007:12-48]` scrubbed; mixed prefixed+bare both scrubbed; ordinary
  `[event]`/`[evidence]`/`[1]`/`[2]` PRESERVED; no dangling `[ev_`/`[#ev` substring survives.

## The real risks to rule on
1. Does `\[#?ev[:_][^\]]*\]` over-match any legitimate token? (Claim: no — `[N]`, `[event]`, `[evidence]`
   untouched; verified by the new preservation test.)
2. Any case a bare `[ev_NNN]` should be RESOLVED to `[N]` rather than scrubbed? (Claim: no — the synthesis
   layer cites by `[N]` only; an ev-token there is always a leak.)

APPROVE iff the diff scrubs bare `[ev_NNN]` (+span) at the existing chokepoint, preserves `[N]` + ordinary
bracketed words, is covered by the offline tests, and leaves the verified core untouched.
