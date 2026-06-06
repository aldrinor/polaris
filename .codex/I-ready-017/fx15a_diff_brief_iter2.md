# FX-15a (#1118) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
Telemetry-correctness ONLY — no retrieval-selection / grounding / strict_verify / 4-role change.
Diff: `.codex/I-ready-017/fx15a_codex_diff.patch` (vs FX-11 verified tip `55d07534`).

## Your iter-1 verdict (addressed)
**P1:** "Deepener seed URLs remain on the default `primary_trial_doi` / `primary_trial_doi_seed`.
Citation-snowball URLs are primary-trial-derived but not direct primary-trial DOI seeds, so future
deep_retrieval traces can still pollute `backend=='primary_trial_doi'` telemetry. Relabel them,
e.g. `deepener_seed`, and add that label to both the reserved seed source set and sentinel origins
to preserve behavior."

## What iter-2 changed (exactly your P1)
1. `_SEED_SOURCE_LABELS` (live_retriever) → `{primary_trial_doi, agentic_seed, deepener_seed}` — so
   deepener seeds stay in the reserved/undroppable/unranked lane (no selection change).
2. `plan_sufficiency_gate.SENTINEL_ORIGINS` → adds `'deepener_seed'` (fallback-eligibility
   preserved, identical to the old `primary_trial_doi_seed` it carried before).
3. The deepener caller (`run_honest_sweep_r3.py`, `deep_retrieval` with `seed_urls=_deep_urls`)
   now passes `seed_source='deepener_seed', seed_query_origin='deepener_seed'`.

This is the SAME behavior-preserving pattern used for `agentic_seed` in iter-1.

## Evidence
- **Offline smoke — `test_fx15a_agentic_seed_label_iready017.py` → 6 passed** (added a deepener
  injection-label test + the seed-split now reserves all 3 classes + both new labels are sentinels).
- **Regression**: `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds` (5) +
  `test_plan_sufficiency_phase3` (26) all pass.
- §-1.1: `outputs/audits/I-ready-017/fx15a_s11_audit.md` (updated for the deepener relabel).

## Remaining caller audit (complete)
Of all `run_live_retrieval(seed_urls=...)` callers: off-mode DOI keeps the default
`primary_trial_doi` (correct — those ARE DOI seeds); agentic → `agentic_seed`; deepener →
`deepener_seed`; gap (`seed_urls=[]`) and exp (no seeds) inject nothing. No seed lane is left
mislabeled.

## Question
Is the deepener relabel correct + behavior-preserving (reserved lane + sentinel both updated), and
are all seed lanes now truthfully labeled? Anything blocking APPROVE?
