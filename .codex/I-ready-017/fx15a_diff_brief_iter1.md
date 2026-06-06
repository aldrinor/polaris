# FX-15a (#1118) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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
**Telemetry-correctness ONLY** — NOT a faithfulness invariant. No retrieval-selection, grounding,
strict_verify, or 4-role-decision change. Does NOT block the rerun. Diff:
`.codex/I-ready-017/fx15a_codex_diff.patch` (vs FX-11 verified tip `55d07534`).

## Bug (RB-02a), confirmed §-1.1 on the REAL held trace
`run_live_retrieval(seed_urls=...)` injected every seed as `source='primary_trial_doi'`,
`query_origin='primary_trial_doi_seed'` (`live_retriever.py` seed injection). The agentic caller
(`run_honest_sweep_r3.py`, `seed_urls=_ag_urls`) therefore mislabeled ~100 ordinary web
discoveries as primary-trial DOI seeds. §-1.1 on the held drb_72
`outputs/audits/I-ready-017/run_artifacts/retrieval_trace.jsonl`: of 41 rows with
`backend=='primary_trial_doi'`, **0 are doi.org seeds, 41 (100%) are aeaweb web/conference/SERP
URLs** (the drb_72 AI/labor question has no primary-trial DOIs configured). Full §-1.1:
`outputs/audits/I-ready-017/fx15a_s11_audit.md`.

## Fix (label-only; behavior-preserving)
1. `live_retriever.run_live_retrieval`: new params `seed_source: str = 'primary_trial_doi'` +
   `seed_query_origin: str = 'primary_trial_doi_seed'`; the seed injection uses them.
2. The reserved-seed split (`_rerank_and_reserve`) now keys on the SET
   `_SEED_SOURCE_LABELS = {primary_trial_doi, agentic_seed}` — so the relabel changes NO selection
   (agentic seeds stay reserved/undroppable/unranked-prepended exactly as before; FX-15b is what
   later makes them droppable).
3. Agentic caller (`run_honest_sweep_r3.py`) passes `seed_source='agentic_seed',
   seed_query_origin='agentic_seed'`; the off-mode DOI caller keeps defaults.
4. `plan_sufficiency_gate.SENTINEL_ORIGINS` adds `'agentic_seed'` so its overlap-fallback
   eligibility is identical to the old `primary_trial_doi_seed` (also a sentinel) — no
   plan-sufficiency behavior change.

## Evidence
- **§-1.1 on REAL held trace** (above): 41/41 mislabeled rows are ordinary web/nav.
- **Offline smoke — `test_fx15a_agentic_seed_label_iready017.py` → 5 passed**: seed-split keeps
  BOTH seed classes reserved (no selection change); `_SEED_SOURCE_LABELS` correct; `agentic_seed`
  ∈ SENTINEL_ORIGINS; injection (stubbed `_fetch_content`) yields `source/query_origin=='agentic_seed'`
  for the agentic caller and `'primary_trial_doi'`/`'primary_trial_doi_seed'` for the default.
- **Regression**: `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds` (5) +
  `test_retrieval_trace` (7) + `test_plan_sufficiency_phase3` (26) all pass.

## Adjacent files checked (and clean / scoped)
- `source=='primary_trial_doi'` is read in EXACTLY ONE place — the seed-split (now the SET). No
  other consumer.
- Custody telemetry (`multi_section_generator._m53_compute_primary_custody_log`, v29/m44) keys on
  `primary_trial_anchors` (DOI strings), NOT the seed `query_origin` — so this relabel is the
  prerequisite; lane-aware custody is FX-14.
- Other `run_live_retrieval(seed_urls=...)` callers: off-mode DOI (keeps default), gap
  (`seed_urls=[]`), exp (no seeds).

## Question for you
The citation-snowball **deepener** caller (`run_honest_sweep_r3.py`, `deep_retrieval` with
`seed_urls=_deep_urls`) ALSO currently labels its URLs `primary_trial_doi`. The Codex-approved
plan scoped FX-15a to the agentic caller only. Should the deepener be relabeled too (e.g. a
`deepener_seed` source), or is the `primary_trial_doi` label defensible for citation-snowball
discoveries (they are the cited references of the primary trials)? Anything else blocking APPROVE?
