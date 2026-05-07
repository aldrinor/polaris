# Codex Diff Review — I-f15-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f15-002 — embed extracted span text ≤500 chars (UTF-8 safe)
**Brief:** APPROVED iter 2 (0/0/0P1, 1 P2 bookkeeping)
**Canonical-diff-sha256:** `85b29160ce9d3ff8d2b06ea6316ba1d5cf792902539bee038da25a592f26952f`
**LOC:** 127 net (33 src + 94 test)
**Tests:** 11/11 PASS

## Files

```
src/polaris_graph/audit_bundle/span_truncate.py            NEW +33
tests/polaris_graph/audit_bundle/test_span_truncate.py     NEW +94
```

## What changed

`truncate_span()` helper per brief iter-2 algorithm:
- `cut = max_chars - 1` so output is ≤ `max_chars` total INCLUDING ellipsis.
- Walk-back loop guards both `unicodedata.combining(next_ch) != 0` and ZWJ join (either side).
- `max_chars=0` → `""`; `max_chars=1` → `"…"`.

Tests cover the 9 scenarios from the brief plus a constants-sanity test:
- short passthrough (no ellipsis)
- ASCII / CJK truncation (exact 500)
- Arabic shadda combining walk-back
- ZWJ cut-after / cut-before / compound-emoji not split
- max_chars=0 / max_chars=1
- utf-8 byte-safe round-trip
- module constants

## Risks for Codex Red-Team

1. **Algorithm faithfulness.** Implementation matches brief iter-2 algorithm byte-for-byte (modulo the `bool(next_ch)` short-circuit ensuring we don't call `unicodedata.combining("")`).
2. **`bool(next_ch)` guard.** When `cut == len(text)` (off-end of string), `next_ch = ""`. `unicodedata.combining("")` raises TypeError; the guard prevents that. This case occurs only when `max_chars > len(text)` — which the early `len(text) <= max_chars` returns before the loop.
3. **No grapheme breakage in compound-emoji case.** Test `test_compound_emoji_not_split` positions FAMILY (5 codepoints) at indexes 497-501 so the natural cut at index 499 lands inside the ZWJ sequence; walk-back drives cut to 497, output is `"a"*497 + "…"`, no ZWJ in output.
4. **Cap math holds.** `cut` starts at `max_chars - 1` and only decreases. Final length = `cut + 1` ≤ `max_chars`. Verified by exact-500 assertions in `test_ascii_truncation_total_500` and `test_cjk_truncation_total_500`.
5. **No new package dep.** Stdlib `unicodedata` only.
6. **CHARTER §1 LOC cap.** 127 net. Under 200.
7. **Hermetic tests.** No env vars, no file IO, no network.
8. **Brief iter-2 P2 bookkeeping (9 vs 10 tests):** the impl shipped 11 tests (added `test_module_constants` for sanity). Brief stays consistent with reality.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
