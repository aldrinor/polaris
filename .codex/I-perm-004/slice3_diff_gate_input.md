# Codex DIFF review — I-perm-004 (#1198) SLICE 3: gap-#18 accept-path token re-point

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify minor stuff P2/P3.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this slice does
In `verify_sentence_provenance`, when the gap-#18 BOUNDED LOCAL-WINDOW RESCUE accepts a sentence whose narrow cited span did NOT directly entail (the `else:` branch after `verdict2` is ENTAILED), the [#ev] token was left on its ORIGINAL mis-pointed span (idx-9: shipped bound to a badge/altmetric span while the support sits elsewhere in-row). This slice captures the rescue window's OFFSETS and RE-POINTS the token to that window at the return. Behind `PG_SPAN_RESOLVER` (default OFF -> byte-identical), SINGLE-token only.

## THE safety properties to verify (P0 class)
1. **No new pass.** The re-point is applied at the return ONLY when `is_verified` (which is `len(failures)==0`, computed from the UNCHANGED checks). It NEVER appends to `failures`, NEVER flips a drop to a keep. A sentence that would drop still drops; the re-point only relabels WHICH span a KEPT sentence's surviving token cites. Verify there is no path where the re-point makes `is_verified` True.
2. **OFF byte-identical.** `reanchor_local_to` is set ONLY inside `if _span_resolver_enabled() and local_win is not None and local_ev_id is not None and len(tokens)==1`. With the flag OFF it stays None, the return uses `sentence`/`tokens` unchanged. Verify nothing else reads it.
3. **Faithful re-point.** The rescue window was found by `_find_local_support_window`/`_find_local_content_window` (numeric/content match) AND judged ENTAILED (verdict2 not NEUTRAL/CONTRADICTED) before `reanchor_local_to` is set in the accept branch. So the re-pointed span genuinely entails — the token now cites a span that actually grounds the claim, strictly MORE faithful than the original mis-pointed span. Confirm the capture happens in the ENTAILED branch only.
4. **Single-token scope.** `len(tokens)==1` guard both at capture and at apply; multi-token sentences keep current behavior (no re-point) — the which-token-to-move combinatorics are out of scope (matches `_try_reanchor` v1). Confirm a multi-token sentence is never partially re-pointed.

If you find any path where flag-ON changes is_verified vs flag-OFF, or re-points to a span the judge did NOT entail, that is a P0.

## Claims ledger — verify each
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | re-point never changes is_verified | `is_verified = len(failures)==0` computed BEFORE the re-point block; re-point only rewrites sentence/tokens | claims-true |
| C2 | OFF byte-identical | `reanchor_local_to` set only under `_span_resolver_enabled()`; default None; return uses original on None | claims-true |
| C3 | re-pointed span genuinely entails | capture is in the `else` (verdict2 ENTAILED) branch; window was numeric/content-matched | claims-true |
| C4 | single-token only | `len(tokens)==1` at both capture and apply | claims-true |
| C5 | only a KEPT sentence is re-pointed | apply guarded by `is_verified` | claims-true |

## Behavioral proof (offline, MarkerJudge) — `test_span_repoint_iperm004.py`
Single-token sentence; narrow span clears the content floor but judge NEUTRAL; wider local window contains the predicate -> ENTAILED -> rescue accepts. Flag OFF keeps `[#ev:a:0-37]` (byte-identical, no warning); flag ON re-points to a DIFFERENT span that contains the marker + emits `reanchored_local_window:`. Also a sanity test that the rescue fires.

## Scope note
Only the gap-#18 ACCEPT path (allow_local_window_fallback=True). The cited DROP path (_try_reanchor Path 1) was slice 2 (already APPROVE'd). Uncited Path 2 + #1180 widening are later slices.

## Files (full diff: `.codex/I-perm-004/slice3_codex_diff.patch`)
- `src/polaris_graph/generator/provenance_generator.py` (+50): `local_win` capture (2 sites), `reanchor_local_to` function-scope var, capture in the accept branch, re-point at the return.
- `tests/polaris_graph/generator/test_span_repoint_iperm004.py` (new, 3 tests).

## Test evidence: 62 passed across the faithfulness suite (phase0b gap-#18, rescue-guard, reanchor, span-provenance, span_resolver, span_repoint); OFF byte-identical.

Review the diff. Confirm C1 (re-point never changes is_verified) + C2 (OFF byte-identical) structurally. Hunt any laundering or non-entailed re-point path.
