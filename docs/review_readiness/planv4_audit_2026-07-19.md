# Plan-V4 Audit — 2026-07-19 (codex-gated)

**Scope:** audit of Phase 0/1 execution order against Plan V4's safety rules.
**Anchor:** `b6e8ef5` (pre-initiative pipeline state; first runtime change is `43214a2`).

---

## Finding

**Phase 0 baseline was skipped.** All Phase 1 runtime work was performed on top of an
**un-pinned oracle** — there was no anchored manifest, no repaired/validated harness, and no
characterized baseline before runtime modules were changed. This is a direct violation of
**Plan V4 safety rule 1**: no runtime change may be evaluated against an oracle that was not
first pinned and validated at the anchor.

Because the oracle was not pinned first, every "behavior-preserving" claim made during Phase 1
stood on a moving reference: there is no frozen baseline to compare against, so those changes
were never actually shown to preserve behavior.

---

## Corrected order (per codex)

The execution order is corrected to put the oracle first and retro-validate everything built on
the un-pinned one:

1. **Manifest anchored to `b6e8ef5`** — pin requirements.lock digest, python/OS, model routing
   slugs, secret *digests* (no raw values), seeds, exact commands, input fixtures.
   (Landed: `docs/review_readiness/baseline_manifest.json`, commit `28ae7f7`.)
2. **Repair + validate the harness** — restore the acceptance/oracle harness to a runnable,
   trustworthy state at the anchor before it is used to judge anything.
3. **N ≥ 3 characterization** — run baseline-vs-baseline N ≥ 3× on the deterministic oracle to
   measure intrinsic run-to-run RACE spread, and fill the equivalence band.
4. **Comparison protocol** — the normative same/not-same contract, written *ahead* of measurement.
   (Landed: `docs/review_readiness/comparison_protocol.md`; band value still TODO pending step 3.)
5. **Selector fixtures** — the fixture set the comparison keys verdicts against.
6. **Retro-validate every runtime change module-by-module** — because Phase 1 ran on the
   un-pinned oracle, each already-landed runtime change is re-evaluated individually against the
   now-pinned baseline, not waved through.

---

## Status downgrades

| Item | Prior claim | Corrected status |
|------|-------------|------------------|
| 1A / 1C-order | done | **VIOLATED** — ran before the oracle was pinned (rule 1 order violation) |
| 2B | in progress | **NOT-STARTED** |
| S3 | assumed present | **MISSING** |

---

## Rationale

The two absolute charter rules make the order non-negotiable: **faithfulness verdicts are frozen**
and **RACE + faithfulness are never quarantined**. Neither can be honored without a pinned baseline
to freeze *against*. "Not shown to be behavior-preserving" resolves to **stop / retro-validate**,
never to **proceed** — so the Phase 1 work is not discarded, it is re-judged module-by-module
against the anchored oracle under the comparison protocol.
