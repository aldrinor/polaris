# Codex DIFF review — I-perm-004 (#1198) SLICE 1 span_resolver — ITER 2 (confirm P2 fix)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## You APPROVED iter-1 (zero P0/P1). This iter folds in your two classifier P2s. Confirm + hunt fresh.

### P2-1/P2-2 (RESOLVED): nav/link-bar chrome mis-read as prose@conf-1.0
Your evidence: `home | articles | current issue | archives | about the journal | submit manuscript.` and `www.example.com current issue archive author guidelines submit manuscript editorial board contact us.` classified as `prose`.

**Fix (`span_resolver.py`):** `_NAV_RE` gained journal-chrome keywords (submit manuscript / author guidelines / editorial board / current issue / about the journal / contact us); added `_NAV_SEPARATOR_RE` so a span with >=2 pipe/bullet separators (`| • · ▪ »`) is `nav_link`. `classify_span` now returns `nav_link` on keyword OR >=2 separators. Strictly additive: it can only move a span prose->nav_link (LOWER confidence) — it can never create an over-credit. New regression params in `test_classify_boilerplate_buckets` cover both your strings.

### P2-3 (acknowledged, not changed): `_QUALITY_PENALTY` is a module-level dict
Module constant, never mutated. Left as a conventional module constant (not frozen) — flag again only if you consider it a real risk.

## Unchanged safety invariant to re-confirm
`resolve_best_entailing_span` can ONLY return a span the injected `judge_fn` accepted (`if not judge_fn(...): continue`). The classifier change does not touch that gate.

## Files (full diff: `.codex/I-perm-004/slice1_codex_diff.patch`)
- `src/polaris_graph/generator/span_resolver.py` (pure).
- `tests/polaris_graph/generator/test_span_resolver_iperm004.py` (9 tests, +2 nav regressions).

## Test evidence: 9 passed (incl. the two nav-chrome regressions).

Confirm the P2 fix; hunt any NEW classify_span over-confidence (a clearly-boilerplate span returning `prose`) or any way the argmax returns a non-judge-accepted span.
