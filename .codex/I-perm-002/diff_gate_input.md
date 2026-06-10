# Codex DIFF review — I-perm-002 (#1196) semantic contraindication credit + negation guard

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

## What this diff does (one line)

Behind `PG_SWEEP_SEMANTIC_CONTRAINDICATION` (default OFF -> byte-identical), the S0 `contraindications` content requirement `contraindicated` is satisfied by a high-precision contraindication-DIRECTION synonym set; the population token stays literal; a deterministic negation guard refuses any inverted claim. On the saved drb_76 run the genuine warning credits and the run flips `released_insufficient_safety_evidence` -> `released_with_disclosed_gaps` without fabricating.

## THE clinical-safety constraint you are reviewing against (§-1.1)

OVER-crediting a contraindication is LETHAL: a report that wrongly believes it warned a population it never warned. UNDER-crediting is a SAFE disclosed gap under always-release (I-perm-001). Your review must hunt the over-credit direction specifically: **can ANY inverted / negated / opposite-direction claim earn S0 `contraindications` credit with the flag ON?** If yes, that is a P0.

## Ground-truth evidence (verify these against the diff + the cited files; don't take my word)

1. **Real drb_76 claim 03-001** (`outputs/audits/beatboth8/drb_76/four_role_claim_audit.json`): sentence = "On the basis of these data, the authors explicitly advise that _S. cerevisiae_ var. _boulardii_ probiotics are **not recommended** for patients who are **immunocompromised**, critically ill, or have indwelling catheters". severity S3, covered_element_ids [] (un-credited today).
2. **The entity** (`config/scope_templates/clinical.yaml:942-967`): id `probiotic_immunocompromised_contraindication`, severity S0, s0_category `contraindications`, `coverage_content_requirements: [contraindicated, immunocompromised]`, `url_pattern: https://wwwnc.cdc.gov/eid/article/27/8/21-0018_article`. The CDC source body says probiotics "should be avoided for patients who ... are immunocompromised" — it NEVER contains the literal token "contraindicated".
3. **The real evidence record** (`outputs/audits/beatboth8/drb_76/evidence_pool.json`, evidence_id `probiotic_immunocompromised_contraindication`): `source_url` == the entity `url_pattern` EXACTLY -> the canonical-source match holds.
4. **Pre-existing guards the matcher sits behind** (verify in `native_gate_b_inputs.py`): line 465 `if not verification.is_verified: continue` (only strict-verified claims reach the matcher); line 348 `_entity_canonical_match` required before content; line 350 content-requirement gate for S0.

## Claims ledger — each claim -> where to verify -> status

| # | Claim | Verify at | Status |
|---|---|---|---|
| C1 | Flag default OFF is byte-identical literal-exact match | `native_gate_b_inputs._content_requirements_satisfied` (semantic=False -> `token_lower not in lowered` else-branch); test `test_off_is_literal_exact_unchanged` | claims-true |
| C2 | Only the concept token `contraindicated`/`contraindication` is relaxed; every other token (e.g. `immunocompromised`) stays literal | the `if semantic and token_lower in _CONTRAINDICATION_CONCEPT_TOKENS:` branch vs `elif token_lower not in lowered`; test `test_on_population_anchor_stays_literal` | claims-true |
| C3 | Negation guard refuses inverted claims even when a positive indicator co-occurs | `_contraindication_direction_present` returns False if any `_CONTRAINDICATION_NEGATIONS` present BEFORE checking indicators; tests `test_on_negation_guard_refuses_inverted`, `test_on_is_strictly_safer_than_off_for_negated_contraindicated` | claims-true |
| C4 | Real drb_76 warning credits with flag ON; run flips to `released_with_disclosed_gaps`, safety_floor ok, WITHOUT fabricating | `test_drb76_flips_to_released_with_disclosed_gaps` (skipif saved pool absent); coverage 2/5 -> 3/5 | claims-true |
| C5 | `replay_release_outcome` default unchanged (corpus_satisfaction=False preserves I-perm-001 baseline) | `d8_replay_harness.replay_release_outcome` new kwarg default False; `test_iperm001_release.py` still green | claims-true |
| C6 | Slate activation: flag in slate + required + force-on so it is LIVE (not inert) on the next run, fail-closed if operator =0 | `run_gate_b.py` three edits; runtime assert in this brief's test run confirmed all three | claims-true |

## Specific over-credit attack surface to adversarially probe (this is the P0 hunt)

- Does the negation list miss a common inverted construction that a real LLM report would emit and that would co-occur with `immunocompromised` + a positive indicator? Concretely: is there a phrasing where the claim asserts probiotics ARE acceptable/safe for immunocompromised yet (a) passes `is_verified`, (b) cites the exact CDC source, (c) contains `immunocompromised` literally, (d) contains a positive indicator substring, and (e) contains NO negation-list phrase? If you can construct one, that is a P0 — give the exact sentence.
- Substring-collision check: does any negation phrase accidentally suppress a GENUINE warning (causing a SAFE under-credit, P2 at worst) — e.g. does "are safe" fire inside an unrelated clause of a real warning sentence? Under-credit is safe, so this is at most P2, but flag it.
- Is `_contraindication_direction_present` whole-claim scan (not proximity) the right call? I argue yes (proximity windows are fragile per the qualitative-negation lesson; whole-claim errs toward under-credit = safe). Challenge if you disagree.

## Files changed (full diff: `.codex/I-perm-002/codex_diff.patch`)

- `src/polaris_graph/roles/native_gate_b_inputs.py` (+100, ~30 logic) — the matcher + sets + 2 helpers.
- `tests/polaris_graph/replay/d8_replay_harness.py` (+19) — `corpus_satisfaction` passthrough on `replay_release_outcome`.
- `tests/polaris_graph/roles/test_semantic_contraindication_iperm002.py` (+190) — matrix + negation + behavioral flip.
- `scripts/dr_benchmark/run_gate_b.py` (+20) — slate activation (3 lock sites).

## Test evidence (already run on my tree)

- `test_semantic_contraindication_iperm002.py` + `test_iperm001_release.py`: 25 passed.
- `tests/roles/test_native_gate_b_inputs.py` + replay + `test_gate_b_seam.py` + fx03 + required_entity: 91 passed, 1 xfailed (OFF byte-identical, no regression).
- gate-b slate/preflight/capability: 112 passed.

Review the diff at `.codex/I-perm-002/codex_diff.patch`. Verify the claims ledger against the actual code. Hunt the over-credit P0 specifically.
