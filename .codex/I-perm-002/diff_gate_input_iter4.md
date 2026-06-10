# Codex DIFF review — I-perm-002 (#1196) semantic contraindication credit — ITER 4

```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
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

## Resolution log — every prior finding addressed. Verify against code.

- iter-1 P0-1 (interposed-qualifier stem negation) — RESOLVED (you confirmed).
- iter-1 P2-1 (contrastive under-credit) — RESOLVED (you confirmed).
- iter-2 P0-2 (contraction negations) — RESOLVED (you confirmed).
- iter-3 P0-3 (interposed "against" beyond fixed window) — RESOLVED this iter (below).
- iter-3 P2 (plural concept token) — RESOLVED this iter (below).

### iter-3 P0-3 (RESOLVED): `not recommended ... against use` interposed beyond the 16-char window

Your evidence: `... are not recommended by the CDC source against use in immunocompromised patients` returned True because "against" fell outside the 16-char tail window.

**Fix (`native_gate_b_inputs.py`, `_contraindication_direction_present`):** the fixed tail window is GONE. The "recommend against" idiom is unique to the recommend family, so "not recommended" is now its OWN route: a `not recommended` occurrence credits ONLY when "against" does NOT appear ANYWHERE in the remaining claim text after it (whole-tail scan — not gameable by interposition). The other imperatives ("should be avoided", "should/must not be used/given/administered") have no such idiom and are matched plainly. Verify with `test_on_negation_guard_refuses_inverted` params: the immediate, mid, and far-interposed `against` forms all refuse; the genuine `not recommended for ... immunocompromised` (no downstream "against") still credits.

### iter-3 P2 (RESOLVED): plural "contraindications" not relaxed

**Fix:** `_CONTRAINDICATION_CONCEPT_TOKENS` now includes "contraindications". See `test_on_relaxes_plural_concept_token` (a plural-requirement entity credits a genuine warning and refuses an inverted one).

## The current guard, restated for a fresh attack

`_contraindication_direction_present(lowered)`:
1. `lowered = _expand_negative_contractions(lowered)` (aren't->are not, curly apostrophe normalized).
2. For each `not recommended` occurrence: credit iff "against" is NOT anywhere in the text after it.
3. Else: any of the directional imperatives present -> credit.
4. Else: `contraindicat` present AND no `_CONTRAINDICATION_NEGATION_RE` match (negator within 20 chars before the stem, OR absence predicate within 20 chars after) -> credit.
5. Else refuse.

Production gating (unchanged): only is_verified claims reach the matcher; exact canonical-source match required; literal population anchor required; default OFF byte-identical.

## The over-credit P0 hunt (the ONLY blocking class)

Find a sentence that (a) plausibly passes is_verified against an "avoid in immunocompromised" span, (b) cites the exact CDC source, (c) contains literal "immunocompromised", (d) makes the guard return True, yet (e) actually asserts probiotics are acceptable/safe for immunocompromised. Give the exact string if found. A genuine warning that is REFUSED is at most P2 (safe under always-release); report it but it does not block APPROVE.

## Files changed (full diff: `.codex/I-perm-002/codex_diff.patch`)

- `src/polaris_graph/roles/native_gate_b_inputs.py` — the matcher.
- `tests/polaris_graph/replay/d8_replay_harness.py` — `corpus_satisfaction` passthrough (default False unchanged).
- `tests/polaris_graph/roles/test_semantic_contraindication_iperm002.py` — matrix incl. all iter-1/2/3 P0/P2 regressions + plural token + drb_76 flip.
- `scripts/dr_benchmark/run_gate_b.py` — slate activation (3 lock sites).

## Test evidence (run on this iter-4 code)

- `test_semantic_contraindication_iperm002.py` + replay + `test_native_gate_b_inputs.py`: 101 passed, 1 xfailed.
- gate-b slate/preflight: 112 passed.
- drb_76 behavioral flip (corpus_satisfaction=True): OFF `released_insufficient_safety_evidence` -> ON `released_with_disclosed_gaps`, safety_floor insufficient -> ok.
- OFF byte-identical confirmed.

Review `.codex/I-perm-002/codex_diff.patch`. Confirm P0-3 + the plural P2 are resolved. Hunt a new over-credit P0.
