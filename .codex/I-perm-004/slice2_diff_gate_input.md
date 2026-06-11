# Codex DIFF review — I-perm-004 (#1198) SLICE 2: wire span_resolver argmax into the cited re-anchor

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
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
Wires the slice-1 (already APPROVE'd) `span_resolver` argmax into `provenance_generator._try_reanchor` Path 1 (CITED sentences), behind a NEW flag `PG_SPAN_RESOLVER` (default OFF -> byte-identical first-passing loop). When ON, the re-anchor chooses the BEST entailing prose span instead of the FIRST passing candidate (the drb_76 "rebound to the TITLE" bug). Also refines the resolver `judge_fn` signature to `(sentence, span, span_text)` and folds the slice-1 residual P2 (compact pipe link-bars -> nav_link).

## THE safety property (only real P0 class here): the bar is NEVER lowered
The §-1.1-lethal failure is laundering a drop into a pass. Verify against the code:
- The resolver's `judge_fn` is the closure `_candidate_passes(_sentence, span, _span_text)` which RE-BINDS the token to `span` and runs `verify_sentence_provenance(..., allow_local_window_fallback=False).is_verified` — the SAME full gate the first-passing loop uses. So an accepted span ALWAYS passes the exact content+numeric+entailment bar.
- After argmax picks `best`, the code re-binds to `best.best_span` and verifies ONCE MORE; `if not v.is_verified: return None` (defensive — never launder).
- The argmax can only CHOOSE among judge-accepted candidates; it changes WHICH supporting span is bound, never WHETHER an unsupported claim passes.
- OFF (`PG_SPAN_RESOLVER` unset) -> the new branch is skipped entirely; the first-passing loop is byte-identical (the existing 13 reanchor tests + the telemetry-contract test pass with the new counter=0).

If you can show a path where flag-ON accepts a sentence that flag-OFF would have DROPPED (i.e. the argmax recovers something first-passing would not, AND that something is not genuinely gate-passing), that is a P0. Note: argmax judging only `top_k` candidates means it could recover FEWER than the exhaustive first-passing loop (a SAFE reduction), or a DIFFERENT (better-quality) span among passers — but never a span the gate rejects.

## Claims ledger — verify each
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | Accepted span always passes the full gate (no laundering) | `_candidate_passes` closure = verify_sentence_provenance(allow_local_window_fallback=False); post-argmax re-verify + `if not v.is_verified: return None` | claims-true |
| C2 | OFF byte-identical | `if _span_resolver_enabled():` guards the whole new branch; first-passing loop unchanged below it | claims-true |
| C3 | top_k bounds judge calls | resolver judges `scored[:top_k]`; `_span_resolve_topk()` default 4 | claims-true |
| C4 | argmax can only reduce or improve, never lower the bar | same gate as judge; argmax over passers | claims-true |
| C5 | enforce-only laundering guard preserved | `_try_reanchor` still returns None early unless entailment==enforce (line ~1091, unchanged) | claims-true |
| C6 | telemetry contract extended (reanchor_argmax_recovered) not breaking | counter added; OFF leaves it 0; contract test updated | claims-true |

## Behavioral proof (offline, fake judge) — `test_argmax_prefers_prose_span_over_earlier_title`
A row where the supporting clause appears in BOTH a Title-Case segment (enumerated first) AND a later prose segment. Flag OFF binds the TITLE (`reanchored:`, span text contains "Trial Result"); flag ON binds the PROSE (`reanchored_argmax:...:q=prose`, span text contains "the treatment produced"); the two spans DIFFER; `reanchor_argmax_recovered==1`.

## Honest scope note
This slice wires ONLY Path 1 (cited). Path 2 (uncited verbatim-lift) + the gap-#18 ACCEPT path (re-point the token on a local-window rescue instead of passing on the original mis-pointed span) are the NEXT slice — out of scope here.

## Files (full diff: `.codex/I-perm-004/slice2_codex_diff.patch`)
- `src/polaris_graph/generator/provenance_generator.py` (+73): flags `_span_resolver_enabled`/`_span_resolve_topk`, telemetry key, Path-1 argmax branch + lazy import.
- `src/polaris_graph/generator/span_resolver.py` (judge_fn 3-arg signature + compact-pipe nav).
- `tests/polaris_graph/test_provenance_reanchor.py` (+62): telemetry key + argmax behavioral test.
- `tests/polaris_graph/generator/test_span_resolver_iperm004.py` (stub-judge 3-arg).

## Test evidence: 14 reanchor (incl. argmax behavioral + OFF byte-identity) + 9 span_resolver = 23 passed.

Review `.codex/I-perm-004/slice2_codex_diff.patch`. Confirm C1 (no laundering) + C2 (OFF byte-identical) structurally. Hunt any path where flag-ON passes a claim flag-OFF would drop on a gate the full bar rejects.
