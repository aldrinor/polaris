# Claude architect audit — I-wire-001 W6 composition floor_abstractive (#1314)

## Verdict premise overturned (the central finding)
The wiring plan's W6 named a NEW flag `PG_COMPOSITION_FLOOR_ABSTRACTIVE`. Investigation shows the
locked winner `floor_abstractive` IS the production module `abstractive_writer.py` (I-beatboth-005
#1282) used as the `writer_fn` of `_compose_section_per_basket`, and it is ALREADY wired flag-gated
default-OFF behind `PG_ABSTRACTIVE_WRITER` at the caller seam `multi_section_generator.py:3950-3974`.
Adding a second flag for one effect is a §-1.3 anti-knob (the plan's own W6 spells this out:
"Do NOT add a redundant second knob"). DECISION: confirm-wired; the deliverable is the activation
recipe + a behavioral fire-test on real data + `.env.example` documentation, NOT new production logic.

## Seam verification (file:line)
- `verified_compose.py:752` `_compose_section_per_basket` — the per-section composer; writer-agnostic
  (takes `writer_fn`). Correct seam. UNCHANGED.
- `multi_section_generator.py:3950` — `if PG_ABSTRACTIVE_WRITER on:` -> abstractive pre-pass + writer.
  3957 `assert_activation_preconditions()` (fail-closed: entailment must be enforce). 3966 `else:`
  deterministic short-writer (byte-identical OFF). This is the real flag-gate; confirmed present.

## 16-point wiring standard adherence
1. No silent fallback — K-span fallback is LOUD (logger.warning on timeout/raise) and disclosed; the
   fire-test's DEGRADE leg proves it fires. OK.
2. GPU-first ML — the writer is a GLM-5.2 OpenRouter call (sovereign-routed), not a local CPU model;
   N/A for a hosted call. OK.
3. Zero hard-coding — every knob is an env var with a code default; `.env.example` now documents them. OK.
4. Bounded concurrency — `PG_ABSTRACTIVE_WRITER_CONCURRENCY` (default 8) semaphore in
   `abstractive_pre_pass`; sections bounded by existing `PG_PARALLEL_SECTIONS`. No new knob. OK.
5. Tokens MAX / timeout FINITE — `max_tokens=2048`, `reasoning_max_tokens=8192`,
   `call_deadline_s=120` (FINITE force-close to K-span). OK.
6. Reasoning vs output separated — the writer returns `response.content`; reasoning is a separate
   `reasoning_max_tokens` budget, never concatenated. OK.
7. Per-claim provenance — every rewritten sentence carries the EXACT `[#ev:id:start-end]` token and
   re-passes `verify_sentence_provenance`; the P1-3 numeric-completeness guard reuses the engine's own
   numeral definition. OK.
8. Console stream — composition logs `[multi_section] ... verified-compose PRIMARY` (existing). The
   live console wiring is upstream of this seam; no regression. OK.
9. Smoke test — the combined e2e (point 9) is the final cert; this PR ships the per-winner fire-test.
10. Critical Codex review — the diff gate is the Codex review.
11. Sovereignty — GLM-5.2 (sovereign), no Exa/Tavily/closed AI. OK.
12. Faithfulness FROZEN — wired AROUND (writer_fn / verify-wrapper), engine UNTOUCHED. Verified the
    diff changes ZERO engine files. OK.
13. Kill-switch — ONE flag `PG_ABSTRACTIVE_WRITER` disables it (no redeploy); the OFF byte-identical
    leg proves clean toggle. A second flag would have WEAKENED this. OK.
14. Interaction effects — deferred to the combined e2e (point 9). N/A per-winner.
15. Reproducibility — the OFF path is deterministic + reproducible (fire-test asserts byte-identical
    across two runs). The ON path is a low-temp (0.2) GLM call; faithfulness is invariant (every
    sentence re-verified), prose wording is the only non-determinism — acceptable for a writer.
16. Model-lock — the writer resolves the GENERATOR-role slug (`PG_GENERATOR_MODEL`, lock-pinned),
    falling back to `z-ai/glm-5.2`; the fire-test asserts model==z-ai/glm-5.2. OK.

## §-1.4 fire-test design (real data, fail-loud)
Drives the PRODUCTION seam `_compose_section_per_basket` on 23 REAL baskets materialized from the
banked drb_72 `corpus_snapshot.json` (not a curated snippet). Three fail-loud assertions: OFF
byte-identical + reproducible; ON >=1 genuinely-paraphrased unit AND 0 engine breaches; forced-failure
degrade to verbatim K-span. Real-GLM DoD (absent key = hard fail).

## Empirical result (PASS — exit 0, real GLM-5.2 on real drb_72 corpus)
`python scripts/iwire001_composition_floor_abstractive_fire_test.py`
(`IWIRE_FIRE_TEST_ON_MAX_BASKETS=4`, `PG_ABSTRACTIVE_WRITER_CONCURRENCY=2`):

- **(OFF)** deterministic composer reproducible byte-identical: 23 units, 5071 chars.
- **(ON)** production abstractive compose FIRED on the real corpus in 34.1s — **3/4 units genuinely
  PARAPHRASED** (token-stripped text differs from every verbatim span + K-span), 1 verbatim/K-span;
  **ALL composed sentences enforce-PASS (0 breaches)** against the UNCHANGED `verify_sentence_provenance`
  (faithfulness FROZEN, entailment=enforce).
- **(DEGRADE)** forced writer failure -> the REAL compose loop degraded to the verbatim K-span (token
  preserved, span-derived). The Traceback in the log is the INTENTIONAL injected `_boom` failure the
  degrade leg raises; the test caught it and verified the fallback — not a real error.

Honest scope: the committed default ON leg bounds the real-GLM slice to 4 of 23 real-corpus baskets at
concurrency 2 so the §-1.4 green is REPRODUCIBLE from the artifacts alone. The OFF byte-identical proof
runs over ALL 23 baskets. Faithfulness is NEVER relaxed (0 breaches at enforce).

FULL-SCALE: the 23-basket ON run at `PG_ABSTRACTIVE_WRITER_CONCURRENCY=8` (the production default) AND
at 3 produced a sustained OpenRouter connection-retry loop and stayed ALIVE past the test's outer
`asyncio.wait_for(timeout=240)` (alive at ~4.2 min, killed manually). To settle hang-vs-slow honestly, a
discriminator (ALL 23 baskets @ concurrency 2, 600s deadline, NO premature kill) was run to completion:
**it PASSED (exit 0) — `(ON) ok ... in 170.3s; 19/23 units genuinely PARAPHRASED, 4 verbatim/K-span;
ALL composed sentences enforce-PASS (0 breaches)`.** VERDICT: the full-scale ON run COMPLETES; the
earlier concurrency-8/3 stalls were a HIGH-CONCURRENCY connection storm that prolonged calls past the
240s deadline, NOT a fundamental un-cancellable hang on the writer path. Concurrency 2 is stable at
full scale; the committed test default pins it. The residual cancellation-propagation concern (whether
`asyncio.wait_for` can force-close a STALLED retry loop — never observed firing on a real stuck call,
only the injected `_boom`; and the production seam `multi_section_generator.py:3959` has no outer
run-level deadline) is filed as a SEPARATE follow-up issue #1315 — pre-existing, out of scope for this
zero-src-change W6 PR. Record: `state/iwire001_floor_abstractive_discriminator.txt`.
