# Codex DIFF review — I-perm-002 (#1196) semantic contraindication credit — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## Your iter-1 verdict was REQUEST_CHANGES with ONE P0 + ONE P2. Both are now resolved. Verify the resolution against the actual code — do not take my word.

### P0-1 (RESOLVED): contiguous negation list missed interposed-qualifier inversions

Your evidence: with the flag ON the matcher credited `CDC reports no known contraindications to S. boulardii probiotics in immunocompromised patients` plus `not generally contraindicated`, `not clearly contraindicated`, `need not be contraindicated`, `not recommended against`.

**Root cause:** the bare positive substring (`contraindicat...` / `not recommended`) fired while the brittle CONTIGUOUS negation list (`no contraindication`, `not contraindicated`) did not match the interposed-qualifier form.

**Fix (`native_gate_b_inputs.py`, the new `_contraindication_direction_present` + constants):** the contiguous negation list is DELETED. Direction is now two fail-closed routes:
1. DIRECTIONAL IMPERATIVES (`_CONTRAINDICATION_DIRECTIONAL_INDICATORS` — "not recommended", "should be avoided", "should/must not be used/given/administered", "not be used in"). The bare concept word is NO LONGER in this list. Each is guarded against the in-place inverter: a match immediately trailed (within `_DIRECTIONAL_TAIL_WINDOW`=16 chars) by "against" is rejected (`not recommended against use` -> not a contraindication).
2. The bare STEM `contraindicat` counts as positive ONLY when `_CONTRAINDICATION_NEGATION_RE` does NOT match. That regex catches a negator BEFORE the stem within a tight 20-char interposition window (`no|not|never|without|none|lack(s)|few|rare|absent|unknown|unestablished|...` + `[\w\s,'()/-]{0,20}?` + `contraindicat`) OR an absence predicate AFTER the stem (`contraindicat\w* ... unknown|not (been) established|absent|unclear|unlikely|none|negligible|rare|few`). ONE negated mention disqualifies the stem for the whole claim.

**Verify the exact attack strings now refuse** — see `test_on_negation_guard_refuses_inverted` params (all of: `no known contraindications`, `not generally contraindicated`, `not clearly contraindicated`, `need not be contraindicated`, `not recommended against use`, `contraindications are unknown`, `contraindications have not been established`). Run it.

### P2-1 (RESOLVED, improved): whole-claim "are safe" scan under-credited a contrastive warning

Your evidence: `Although probiotics are safe for most adults, S. boulardii probiotics are not recommended for immunocompromised patients` returned False.

**Fix:** the whole-claim safe/recommended refuse list is DELETED entirely. A genuine warning now credits via its directional imperative regardless of a co-occurring "are safe" clause. See the new POSITIVE param in `test_on_credits_direction_synonyms_with_population` (the "although ... safe for most adults ... not recommended for immunocompromised" case now returns True). The protection against an actually-safe claim is the per-signal negation + the population anchor + is_verified + NLI, not a blunt whole-claim string ban.

## The 20-char window trade-off (deliberate, please sanity-check the direction)

`no known contraindications` (9-char interposition) -> REFUSED. `there is no doubt probiotics are contraindicated in immunocompromised patients` (24-char interposition between "no" and the stem) -> CREDITED (a genuine warning). The window is tuned so a SHORT inverting qualifier is caught while an unrelated DISTANT negation does not suppress a real warning. Both directions are tested. If you can name a SHORT (<20 char interposition) inverting form that still credits, that is a P0 — give the exact sentence.

## The over-credit P0 hunt (unchanged mandate)

Over-crediting a contraindication is §-1.1-LETHAL (a report that wrongly believes it warned). Construct, if you can, a sentence that (a) would pass is_verified against an "avoid in immunocompromised" span, (b) cites the exact CDC source, (c) contains literal "immunocompromised", (d) makes `_contraindication_direction_present` return True, yet (e) actually asserts probiotics are acceptable/safe for immunocompromised. If you find one, P0 with the exact string. Under-credit (a real warning refused) is at most P2 (safe under always-release) — still report it.

## Files changed (full diff: `.codex/I-perm-002/codex_diff.patch`)

- `src/polaris_graph/roles/native_gate_b_inputs.py` (+115) — the matcher; `_contraindication_direction_present` rewritten for iter-2.
- `tests/polaris_graph/replay/d8_replay_harness.py` (+19) — `corpus_satisfaction` passthrough (default False unchanged).
- `tests/polaris_graph/roles/test_semantic_contraindication_iperm002.py` (+206) — matrix incl. all iter-1 P0/P2 regressions + drb_76 flip.
- `scripts/dr_benchmark/run_gate_b.py` (+20) — slate activation (3 lock sites).

## Test evidence (already run on my tree, this iter-2 code)

- `test_semantic_contraindication_iperm002.py` + `test_iperm001_release.py` + `test_native_gate_b_inputs.py` + replay: 71 passed.
- gate-b slate/preflight/capability: 112 passed.
- drb_76 behavioral flip (corpus_satisfaction=True): OFF `released_insufficient_safety_evidence` -> ON `released_with_disclosed_gaps`, safety_floor insufficient -> ok.
- OFF byte-identical confirmed across all native_gate_b/replay/seam tests.

Review `.codex/I-perm-002/codex_diff.patch`. Confirm P0-1 + P2-1 are resolved by the code (not just by my claim). Hunt a new over-credit P0.
