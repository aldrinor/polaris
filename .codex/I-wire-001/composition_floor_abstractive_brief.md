```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-wire-001 W6 — composition floor_abstractive (sub-issue #1314)

## FRONTIER-TECH MANDATE
Winner sourced from the 2026 upstream bake-off (board `state/section_winner_board.md` row 12,
re-judged 11x, Welch p<0.05). No grandfather downgrade. Faithfulness engine FROZEN.

## What the winner is
`floor_abstractive` (composite 20.5455, beats generation_programs / multicited_fuse /
floor_deterministic, p<0.05) IS the production module
`src/polaris_graph/generator/abstractive_writer.py` (I-beatboth-005 #1282) used as the per-basket
`writer_fn` of `verified_compose._compose_section_per_basket`. The bake-off
`run_candidate("floor_abstractive")` does exactly:
`_compose_section_per_basket(baskets, pool, writer_fn=<abstractive writer fn>, verify_fn=verify_sentence_provenance)`.

## Decision: CONFIRM-WIRED, no new flag (the deliverable is the activation recipe)
The winner is ALREADY wired flag-gated default-OFF at the real caller seam
`src/polaris_graph/generator/multi_section_generator.py:3950-3974`. When `PG_ABSTRACTIVE_WRITER` is ON
the async pre-pass + abstractive writer + writer-verify wrapper run; OFF => byte-identical deterministic
short-writer (`build_short_member_sentence`). I did NOT add `PG_COMPOSITION_FLOOR_ABSTRACTIVE`: a second
flag for one effect is a §-1.3 anti-knob and weakens the point-13 kill-switch (the plan's own W6 says
"Do NOT add a redundant second knob"). The existing `PG_ABSTRACTIVE_WRITER` IS the flag.

Activation recipe (all default-OFF): `PG_VERIFIED_COMPOSE=1` (reach the branch at 3922-3926) +
`PG_ABSTRACTIVE_WRITER=1` + `PG_STRICT_VERIFY_ENTAILMENT=enforce` (fail-closed guard,
`assert_activation_preconditions`). Bounded: `PG_PARALLEL_SECTIONS` (sections) +
`PG_ABSTRACTIVE_WRITER_CONCURRENCY` (per-basket pre-pass, default 8). Tokens MAX, deadline FINITE
(`PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=120`).

## Diff (this PR)
1. `scripts/iwire001_composition_floor_abstractive_fire_test.py` — NEW §-1.4 behavioral fire-test.
2. `tests/fixtures/iwire001/compose_gold_corrected.json` — vendored REAL-corpus gold (23 baskets
   materialized from `outputs/corpus_backups/extracted/drb_72_ai_labor/corpus_snapshot.json`,
   manifest.corpus_path proves it; no synthetic spans).
3. `.env.example` — documented the `PG_ABSTRACTIVE_WRITER*` + `PG_VERIFIED_COMPOSE` activation family
   (LAW VI). NO production-logic change (the wiring already exists).

## Faithfulness FROZEN (verify these are UNTOUCHED in the diff)
`verify_sentence_provenance` / strict_verify / NLI / 4-role / `build_verified_span_draft` /
`_compose_one_basket` / `_compose_section_per_basket` / the region gate — ZERO changes. The fire-test
imports them as-is and re-checks every composed sentence with the UNCHANGED engine.

## §-1.4 behavioral fire-test (real corpus, fail-loud)
- (OFF) flag-OFF composition == deterministic short-writer composition, reproducible byte-identical.
- (ON)  flag-ON: >=1 rendered unit GENUINELY PARAPHRASED (token-stripped text differs from its source
        span AND the verbatim K-span) AND EVERY composed sentence re-passes the UNCHANGED
        `verify_sentence_provenance` (0 breaches). A verbatim dump OR a breach => non-zero exit.
- (DEGRADE) forced writer failure degrades through the REAL compose loop to the verbatim K-span
        (token preserved, span-derived >=60% overlap).
- Real-GLM DoD: absent OPENROUTER_API_KEY is a HARD failure (never a silent exit-0).

## Files I have ALSO checked and they are clean
- `multi_section_generator.py:3950-3974` (the seam; OFF lambda passes `build_short_member_sentence`).
- `abstractive_writer.py` (flag gate `_abstractive_writer_enabled`, fail-closed
  `assert_activation_preconditions`, bounded `abstractive_pre_pass` semaphore, FINITE call deadline).
- `verified_compose._compose_section_per_basket` (writer-agnostic; takes `writer_fn` param — correct seam).
- Existing harness `scripts/iarch_beatboth011_abstractive_realcorpus_smoke.py` (#1289 ROUTE C, same
  production path) — my fire-test extends it to the full 23-basket real-corpus gold + per-sentence
  engine re-verify of the ON output + OFF byte-identical reproducibility.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
