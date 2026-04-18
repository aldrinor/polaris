# Deep-dive R6 — Retrieval/generator evidence divergence (BUG-M-201)

**Target**: M-201. Corpus gates reason over all classified URLs, but
generation only sees `evidence_rows[:PG_LIVE_MAX_EV_TO_GEN]` (default
20) in raw retrieval order. This lets the pipeline certify corpus X
(tier-balanced) and synthesize from X' (different, smaller, possibly
unbalanced).

## Real evidence

`clinical_afib_anticoagulation/run_log.txt`:
  `[corpus] total=20 T1=0% T2=0% T3=5% T5=50% ...`
  `[generation] evidence=4` (4 of 20 surviving to generator)

The gate said "adequacy: expand" based on 20 sources, but the
generator only got 4 of those — and the 4 may not be the same tier
mix.

## Mandate

1. Read `scripts/run_honest_sweep_r3.py:620-640` and
   `src/polaris_graph/retrieval/live_retriever.py`.
2. Determine: what controls which evidence is passed to the generator?
   Is there any sort/filter, or just `[:20]`?
3. Choose: (a) compute gates over the generator-visible pool;
   (b) add explicit tier-balanced + relevance-ranked selection so
   the top-N are representative of the full pool;
   (c) raise PG_LIVE_MAX_EV_TO_GEN high enough that divergence
   is unlikely (cost tradeoff).
4. Spec fix + 4-6 tests.

## Output

`outputs/codex_findings/deep_dive_round_6/findings.md` with standard
frontmatter.

## Duration

5-10 minutes.

## Context

- Rounds R1-R5 committed. Current HEAD ~ commit 9d9a5ef.
- `outputs/codex_findings/full_audit_pass_1/findings.md` §2
- Real log: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt`
