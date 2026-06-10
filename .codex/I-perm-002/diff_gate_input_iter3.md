# Codex DIFF review — I-perm-002 (#1196) semantic contraindication credit — ITER 3

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
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

## Resolution log — your two prior REQUEST_CHANGES are addressed. Verify against code, not my word.

### iter-1 P0-1 (interposed-qualifier negations) — RESOLVED in iter-2, you CONFIRMED resolved.
### iter-1 P2-1 (contrastive under-credit) — RESOLVED in iter-2, you CONFIRMED resolved.

### iter-2 P0-2 (RESOLVED this iter): contraction negations bypassed the expanded-only regex

Your evidence: `aren't contraindicated`, `contraindications haven't been established`, `there aren't contraindications` returned True (over-credit).

**Fix (`native_gate_b_inputs.py`):** `_contraindication_direction_present` now FIRST calls `_expand_negative_contractions(lowered_claim)` which (a) normalizes the curly apostrophe U+2019 -> ASCII `'`, then (b) expands the negative-contraction set (`aren't`->`are not`, `isn't`->`is not`, `haven't`->`have not`, `hasn't`->`has not`, `wasn't`/`weren't`/`don't`/`doesn't`/`didn't`/`won't`->`will not`/`couldn't`/`shouldn't`/`mustn't`/`needn't`/... ) to a `X not` form with a SPACE so the existing `\bnot\b` negator fires. The pre/post `_CONTRAINDICATION_NEGATION_RE` also gained `zero|free of|devoid of` absence forms.

**Verify the exact iter-2 attack strings now refuse** — see `test_on_negation_guard_refuses_inverted` params: `aren't contraindicated`, `isn't contraindicated`, `there aren't contraindications`, `haven't been established`, the U+2019 curly-apostrophe variant, `free of contraindications`, `zero contraindications`. Run it.

**And a contraction in a GENUINE warning still credits:** `shouldn't be used in immunocompromised` -> expands to `should not be used` -> directional indicator -> credits (new positive param in `test_on_credits_direction_synonyms_with_population`).

## The full guard, restated (so you can attack the whole thing fresh)

`_contraindication_direction_present(lowered)`:
1. `lowered = _expand_negative_contractions(lowered)`.
2. For each DIRECTIONAL IMPERATIVE substring present: credit UNLESS it is trailed within 16 chars by `against`.
3. Else: credit iff `contraindicat` is present AND `_CONTRAINDICATION_NEGATION_RE` does NOT match (negator within 20 chars before the stem, OR an absence predicate within 20 chars after it).
4. Else refuse.

This is gated, in production, behind: `verification.is_verified` (only strict-verified claims), exact canonical-source match, and the literal population token. Default OFF is byte-identical.

## The over-credit P0 hunt (this is the only thing that blocks)

Construct, if you can, a sentence that (a) would plausibly pass is_verified against an "avoid in immunocompromised" span, (b) cites the exact CDC source, (c) contains literal "immunocompromised", (d) makes `_contraindication_direction_present` return True after contraction expansion, yet (e) actually asserts probiotics are acceptable/safe for immunocompromised. If found, P0 with the exact string. A genuine warning that is REFUSED is at most P2 (safe under always-release) — report it but it does not block APPROVE.

## Files changed (full diff: `.codex/I-perm-002/codex_diff.patch`)

- `src/polaris_graph/roles/native_gate_b_inputs.py` — the matcher; `_expand_negative_contractions` added, `_contraindication_direction_present` calls it first.
- `tests/polaris_graph/replay/d8_replay_harness.py` — `corpus_satisfaction` passthrough (default False unchanged).
- `tests/polaris_graph/roles/test_semantic_contraindication_iperm002.py` — matrix incl. all iter-1/iter-2 P0/P2 regressions + drb_76 flip.
- `scripts/dr_benchmark/run_gate_b.py` — slate activation (3 lock sites).

## Test evidence (run on this iter-3 code)

- `test_semantic_contraindication_iperm002.py` + replay + `test_native_gate_b_inputs.py`: 98 passed, 1 xfailed.
- gate-b slate/preflight: 112 passed.
- drb_76 behavioral flip (corpus_satisfaction=True): OFF `released_insufficient_safety_evidence` -> ON `released_with_disclosed_gaps`, safety_floor insufficient -> ok.
- OFF byte-identical confirmed.

Review `.codex/I-perm-002/codex_diff.patch`. Confirm P0-2 is resolved by the code. Hunt a new over-credit P0.
