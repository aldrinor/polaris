# Codex DIFF review — I-perm-004 (#1198) SLICE 1: span_resolver keystone

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required — loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope of THIS slice (review only this)

`src/polaris_graph/generator/span_resolver.py` — a NEW PURE module + its unit test. It is **INERT**: nothing imports it yet, so it changes ZERO production behavior. The wiring into `provenance_generator` / `strict_verify` and the #1180 widening bakeoff are LATER slices — out of scope here. Review the primitive's correctness + safety, not the (not-yet-present) wiring.

## What it is

The verifier drops real claims whose [#ev] token points at a non-entailing span while a genuinely-entailing span sits ELSEWHERE in the same row (confirmed on saved drb_76 verification_details: 40 verified / 41 dropped of 81; 29 `entailment_failed`). The existing `_try_reanchor` accepts the FIRST passing candidate with no boilerplate filter → drb_76 rebound to the row TITLE. This module replaces first-passing with a boilerplate-aware ARGMAX.

- `classify_span(text) -> prose|title|header|affiliation|nav_link|url|altmetric|reference_list` — deterministic.
- `resolve_best_entailing_span(direct_quote, sentence, candidate_spans, *, judge_fn, numeric_match_fn, top_k)` — lexical pre-rank → judge top_k → argmax over entailing candidates (prose preferred) → Decision-B fields (best_span, provenance_quality, confidence, entailed) or None.

## THE safety property to verify (the only thing that can be a P0 here)

The §-1.1-lethal failure is MANUFACTURING support — returning a span that does NOT entail the sentence. The structural claim is: **`resolve_best_entailing_span` can only ever return a span for which the injected `judge_fn(sentence, span_text)` returned True.** Verify this against the code (the `if not judge_fn(...): continue` is the only gate; nothing else can populate `best`). If you can construct an input where it returns a non-judge-accepted span, that is a P0.

Secondary safety: a boilerplate-only support must NOT read as high confidence. Verify `_QUALITY_PENALTY` makes any boilerplate quality's confidence materially lower than prose, and that confidence is entailment-dominated (base 1.0) not lexical (`_LEXICAL_NUDGE` 0.05 cap). The caller (later slice) uses `provenance_quality` to LABEL; the resolver must never itself upgrade boilerplate to prose.

## Claims ledger — verify each against the code

| # | Claim | Where | Status |
|---|---|---|---|
| C1 | Only a judge-accepted span is ever returned | `resolve_best_entailing_span` loop: `if not judge_fn(...): continue` then `best=...` | claims-true |
| C2 | Judge calls bounded by top_k | `for ... in scored[: max(1, top_k)]` AFTER pre-rank sort | claims-true |
| C3 | Argmax prefers prose over a co-entailing boilerplate span | key `(-_QUALITY_PENALTY[quality], confidence)`; prose penalty 0.0 is the max | claims-true |
| C4 | Boilerplate-only support is labeled low, never silent high | `_span_confidence` subtracts `_QUALITY_PENALTY`; title penalty 0.45 -> conf ~0.55 | claims-true |
| C5 | classify_span is deterministic + total (never raises, empty -> header) | `classify_span` guards | claims-true |
| C6 | Confidence entailment-dominated not lexical | base 1.0, lexical nudge cap 0.05 | claims-true |
| C7 | Pure: no network / no LLM / no global mutable state | module has only `re` + dataclass | claims-true |

## Honest uncertainties to pressure-test (P2/P3 expected, not P0)

- `classify_span` is a heuristic. Mis-bucketing prose↔title is at worst a confidence-label error (a real prose span penalized as a title = SAFE under-confidence; a title mislabeled prose = over-confidence — flag any concrete case where a clearly-boilerplate span returns `prose`). Give exact text if found.
- The `_URL_RE` prose-vs-url split (`< _PROSE_MIN_WORDS words OR < 55% letters`) — challenge with a concrete span that should be url but reads prose, or vice-versa.
- Tie-breaking in the argmax when two prose spans have equal confidence (first-by-prerank wins) — is that acceptable? (I believe yes; flag if not.)

## Files (full diff: `.codex/I-perm-004/slice1_codex_diff.patch`)

- `src/polaris_graph/generator/span_resolver.py` (new, pure).
- `tests/polaris_graph/generator/test_span_resolver_iperm004.py` (new, 9 tests, stub judge).

## Test evidence

- `test_span_resolver_iperm004.py`: 9 passed (classifier buckets; argmax picks entailing prose over a lexically-similar title; title-only labeled low; None when nothing entails; only judge-accepted span returned; judge calls ≤ top_k; numeric mismatch lowers confidence).

Review the diff. Confirm C1 (can-only-return-judge-accepted) holds structurally. Flag any concrete classify_span over-confidence (boilerplate -> prose) case.
