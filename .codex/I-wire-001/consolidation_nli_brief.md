```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-wire-001 W1 — wire consolidation_nli (Bidirectional-NLI, nli-deberta-v3-base)

GitHub sub-issue: https://github.com/aldrinor/polaris/issues/1306 (under umbrella #1303).
Plan: `docs/winner_wiring_plan_2026.md` §3 W1. Winner board: `state/section_winner_board.md:18`.

## What this wires
The bake-off section winner for consolidation/baskets — **Bidirectional-NLI
(nli-deberta-v3-base)** — flag-gated **default-OFF** (`PG_CONSOLIDATION_NLI`). It unions
literal `_finding_key` clusters whose representative CLAIMS bidirectionally entail (same-
claim paraphrases the exact subject/predicate/value floor leaves separate, board R=0.0),
so corroboration (count + distinct hosts) rises. Faithfulness engine FROZEN — this is a
CONSOLIDATION/grouping (§-1.3), never a verify change.

## Seam (VERIFIED file:line on this branch's HEAD f2262bab)
- PRIMARY (the §-1.4 canary seam): `src/polaris_graph/synthesis/finding_dedup.py` —
  `dedup_by_finding`. The flag-gated NLI hook runs AFTER the literal `groups` dict is built
  and BEFORE the per-cluster representative/corroboration loop, so `corroboration_count`
  and `member_hosts` reflect the merged basket. New result field `nli_merge_count`.
  Helpers: `_apply_consolidation_nli` (value-bucket → bounded-parallel pairwise NLI →
  union-find), `_cluster_value_bucket`, `_claim_sentence`/`_cluster_text`.
- COMPANION (plan-listed): `src/polaris_graph/generator/fact_dedup.py` — `build_groups`
  gains a flag-gated `_build_nli_prose_groups` block mirroring `_build_prose_groups`
  (clusters the empty-numeric sentences by NLI). NOTE: this is the SENTENCE-redundancy
  →cross-reference path (the OPPOSITE direction to multi-citation), so the behavioral
  canary asserts on `dedup_by_finding`, not here.
- New module: `src/polaris_graph/synthesis/consolidation_nli.py` — the lazy-loaded
  cross-encoder + `score_pairs` (bounded-parallel) + `group_clusters` (union-find).

The plan named `_same_work_key:316` as a seam; I deviated DELIBERATELY (see audit §"seam
correction"): `_same_work_key`/`consolidate_same_work` merges the SAME paper at multiple
URLs and FOLDS members to one canonical host — running NLI there would push corroboration
DOWN, the opposite of the canary. The correct sub-function in the same file is the
`_finding_key` cluster-merge in `dedup_by_finding`.

## Bounded-parallel (operator mandate — wired from the start)
`PG_CONSOLIDATION_NLI_WORKERS` (default 8) caps a `ThreadPoolExecutor` over pair-chunks in
`consolidation_nli.score_pairs`. Grouping is a deterministic union-find post-step (attach-
to-lowest-index) over the GATHERED, sorted edge list — identical for any worker count
(proven: stub-`predict_fn` unit test, workers=1 == workers=8). Value-bucketing
(`_cluster_value_bucket`) caps pairwise cost to per-bucket O(k²) (drb_72: 346 clusters →
174 value-buckets, largest bucket 48 → 1128 pairs, under `PG_CONSOLIDATION_NLI_MAX_PAIRS`
=20000). Prose path bounded by `PG_CONSOLIDATION_NLI_MAX_SENTENCES` (default 200).

## §-1.4 behavioral fire-test — `scripts/fire_test_consolidation_nli.py`
Three fail-loud assertions on a REAL banked `corpus_snapshot.json`:
1. CORE: flag-OFF == legacy, byte-identical, `nli_merge_count==0` (default-OFF inert).
2. MECHANISM (controlled input): 3 synonym paraphrases (mortality/death rates/fatalities
   reduced 30% → 3 distinct literal keys) MERGE; the ANTONYM (increased 30%) stays
   SEPARATE (bidirectional polarity guard); merged basket ≥2 hosts.
3. PRECISION (real rows): two real same-VALUE/different-CLAIM pairs from drb_75
   (ev_393 dexamethasone-preterm vs ev_061 protein-older-men; ev_262 vs ev_779) STAY
   SEPARATE.

## ⚠ HONEST LIMITATION (LOUD — per the avoidable-negligence rule, do NOT bury)
**Natural clean firing on the banked corpora was NOT achieved; flag-ON activation is
BLOCKED pending an upstream fix. Default-OFF ships safe.**
- On the REAL clinical corpus (drb_75, 787 rows): `nli_merge_count==0` after the precision
  fix (no false merges, but no natural merges either).
- The FIRST input choice (`_row_text` = full `direct_quote`) produced FALSE merges
  (dexamethasone-preterm + protein-older-men) because the bodies are multi-thousand-char
  "Title: … URL Source: …" web-fetch dumps > the cross-encoder's ~512-token limit, so two
  unrelated papers weakly entail on shared boilerplate. Switching the NLI input to the
  focused `context_snippet` claim window killed those false merges (clinical → 0).
- On the REAL workforce corpus (drb_72): the only merges are SPURIOUS over-merges driven
  by the same boilerplate (e.g. value-bucket 1.0 with 48 clusters, density 0.00 = 2
  spurious edges that union-find chains into a blob). Expanding the snippet to the full
  sentence REGRESSED this (more boilerplate) and was reverted.
- ROOT CAUSE: the bake-off scored P=1.0 on CURATED claim pairs; the production input
  (brittle clinical extractor + boilerplate-heavy fetched bodies) is a different
  distribution. The principled fix is UPSTREAM claim-sentence extraction (a clean claim
  sentence per row), tracked as a follow-up; NOT a margin/threshold knob (banned §-1.3).
- BACKSTOP (why default-OFF + the residual over-merge is not silently lethal): the
  downstream consumer `credibility_pass._regroup_graph_by_finding_dedup` is "grouping +
  relabel ONLY — no member newly passes any gate"; every basket member is still verified
  IN ISOLATION against its OWN span. A false merge inflates a corroboration COUNT (a
  Signal-D weight) and can misattribute a corroborator citation — a real §-1.1 concern —
  which is EXACTLY why activation is gated OFF until the upstream input fix lands.

## Files I have ALSO checked and they're clean
- `credibility_pass.py:930` (`basket_consume_finding_dedup_enabled` consumer) — relabel/
  edge-remap only; per-member isolated verify UNCHANGED. `_assemble_baskets` verify-enforce
  unchanged. Faithfulness engine not touched.
- `scripts/run_honest_sweep_r3.py:9498` (live `dedup_by_finding` call, `domain=q["domain"]`)
  — unchanged; default-OFF means byte-identical.
- `scripts/breadth_replay_harness.py` — independent harness, asserts on `corroboration_count`
  (the same field), still valid; my change adds `nli_merge_count` only.
- `weighted_enrichment._work_identity` — unaffected (I touched `_finding_key` clustering,
  not `_same_work_key`).

## Acceptance for THIS PR (honest)
Wired default-OFF + byte-identical proven on a real corpus + mechanism proven on controlled
input + real false-pairs held separate + bounded-parallel. NATURAL real-corpus firing and
report.md multi-citation propagation are explicitly NOT claimed; activation deferred to an
upstream claim-extraction follow-up + the combined cert run.
