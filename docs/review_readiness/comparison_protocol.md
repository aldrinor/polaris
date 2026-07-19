# Comparison Protocol — Phase 0-A (Plan V4 item 0A-4)

**Status:** normative. This document defines — *before any change is measured* — what it means
for the pipeline to be "unchanged" under a refactor. It is the contract every Phase 1+ change is
judged against. It is written *ahead* of measurement on purpose: the definition of "same" must not
be chosen after seeing a diff, or it degenerates into rationalizing whatever happened.

The two absolute rules from the initiative charter apply here and are load-bearing below:
**(1) faithfulness is frozen** — its verdicts are never relaxed to make a change pass; and
**(2) the RACE score and faithfulness verdicts are never quarantined** — they cannot be excluded
from the comparison to keep a change green.

---

## 0. Scope

- **Applies to:** any change asserted to be *behavior-preserving* (config migration, refactor,
  dependency pin, environment move). Feature changes that intend to move behavior are out of scope
  and follow a separate acceptance path — but they must still *declare* the intended delta so this
  protocol is not silently used to launder a real behavior change.
- **Governing measure:** the **RACE score** (the pipeline's governing quality score) and the
  **faithfulness verdicts** (per-fixture, per-claim faithfulness pass/fail as emitted by the
  pipeline). These are the arbiters. Everything else is secondary evidence.
- **Oracle:** comparison runs on the **deterministic regression oracle** (frozen inputs, pinned
  model/tool/browser versions, recorded responses), NOT the live web+model harness. The live
  harness is a smoke test and is never the arbiter of "unchanged" — live retrieval and generation
  are mutable and cannot support a same/not-same verdict.

---

## 1. Definition of "the pipeline did not change"

A change is declared **behavior-preserving ("same")** if and only if **ALL THREE** of the following
hold. These are conjunctive — failing any one is not "same."

### 1.1 RACE within a declared equivalence band, over N ≥ 3 repeats

Run the governed scenario **N ≥ 3 times** on the deterministic oracle, both before (baseline) and
after the change. For every scenario, the after-change RACE score must lie within the
**declared equivalence band** (see §4) of the baseline RACE, on *every* repeat.

- The band is a *pre-declared, symmetric* tolerance `±ε` around the baseline RACE, plus a bound on
  run-to-run spread (see §4). It is fixed BEFORE the after-change run is scored.
- "Within band on every repeat" — not "the mean is within band." A single out-of-band repeat is a
  regression (§2), because it means the band does not actually contain this change's behavior.
- N ≥ 3 is a floor, not a target. If variance is not yet characterized, N is set by the
  characterization run (§4) and may be higher.

### 1.2 Faithfulness verdicts match EXACTLY, keyed per fixture

For each fixture, the pipeline emits faithfulness verdicts. Comparison is done as a
**per-fixture-keyed mapping**:

```
verdict_map : fixture_id -> faithfulness_verdict(s)
```

The after-change `verdict_map` must equal the baseline `verdict_map` **key by key**. For every
`fixture_id` present in either run, the verdict(s) must be identical.

- **Keyed, NOT set-based.** Comparing unordered *sets* of verdicts (e.g. "12 PASS, 3 FAIL both
  before and after") is explicitly **insufficient and forbidden as the equality test**. A set
  discards fixture identity, ordering, and multiplicity: two runs can have the same PASS/FAIL
  *counts* while different fixtures flipped in opposite directions (fixture A: PASS→FAIL,
  fixture B: FAIL→PASS), which nets to the same set but is a real behavior change. The equality
  test is over the *keyed mapping*, so any such swap is caught.
- **Key coverage is part of equality.** The key *sets* must match too: a fixture that appears in
  one run and not the other (dropped or newly emitted) is a mismatch, even if every shared key
  agrees.
- **Frozen.** Faithfulness verdicts are frozen: they are compared for exact equality and are never
  loosened, re-thresholded, or waived to make a change pass.

### 1.3 SHA-256 artifact-hash match for deterministic artifacts

Every artifact declared **deterministic** (i.e. expected to be byte-identical across runs of the
same inputs — manifests, audit bundles, canonicalized report bodies, and any other artifact on the
deterministic-artifact list) must have an identical **SHA-256** hash before and after the change.

- The set of deterministic artifacts is enumerated explicitly in the oracle's manifest. An artifact
  is on this list only if it is genuinely deterministic under frozen inputs; artifacts with legitimate
  nondeterminism (timestamps, run ids, unordered-but-bounded fields) are either canonicalized before
  hashing or are NOT on the deterministic list and are governed by §1.1's bounded-measure treatment
  instead.
- A hash mismatch on a deterministic artifact is a regression (§2), full stop — deterministic means
  deterministic.

---

## 2. Regression vs. noise

The distinction is declared here so it cannot be argued after the fact.

### REGRESSION — the change is NOT behavior-preserving. Blocks.

Any one of:

- **RACE out of band:** the after-change RACE falls outside the declared equivalence band on *any*
  of the N repeats.
- **Faithfulness verdict flip:** *any* per-fixture faithfulness verdict differs from baseline —
  a PASS↔FAIL flip on any `fixture_id`, or a change in the key set (dropped/added fixture).
- **Deterministic-artifact hash mismatch:** *any* SHA-256 on the deterministic-artifact list
  differs from baseline.

A regression is a hard fail. The change is not "same." It is either reverted, or re-classified as an
intentional behavior change and taken through the acceptance path with an explicit declared delta.

### NOISE — tolerated, does not block.

Only:

- **RACE jitter within the band** on non-deterministic-but-bounded measures: run-to-run RACE
  variation that stays inside the declared equivalence band across the N repeats. This is the
  expected residual variance of a bounded stochastic measure and is *not* evidence of a change.

Noise is confined to the RACE band. There is **no noise category for faithfulness verdicts** (they
must be exact) and **no noise category for deterministic-artifact hashes** (they must be identical).
Nondeterminism there is not noise — it is either a bug or an artifact that was mis-declared as
deterministic, and either way it is a BLOCKING STOP under §3, not something to wave through.

---

## 3. Governing rule — the arbiters are never quarantined

The RACE score and the faithfulness verdicts are the arbiters of "same." They are **never
quarantined, excluded, waived, or down-weighted** to let a change proceed.

- If RACE **cannot be characterized within a stable band** — the run-to-run spread is too wide to
  fit a defensible band, or repeats disagree about in/out-of-band — that is a **BLOCKING STOP**.
  The correct response is to **investigate the variance** (find and pin the nondeterminism source),
  not to widen the band until the change passes and not to proceed "for now."
- If a **faithfulness verdict cannot be reproduced stably** across repeats on the same fixture, that
  too is a BLOCKING STOP — investigate, do not quarantine the fixture.
- "Quarantining" the governing measures — marking them flaky/known-bad and proceeding without them —
  is explicitly prohibited. A change that cannot be evaluated by the arbiters has not been shown to
  be behavior-preserving, and "not shown" resolves to **stop**, never to **proceed**.

The asymmetry is deliberate: an uncharacterizable arbiter blocks; it never defaults to green.

---

## 4. The equivalence band value

Equivalence band = 0 (byte-exact): the oracle is a deterministic cassette replay; "same" means the
canonical artifact SHA-256 equals the golden
`9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98` exactly, and both controls (THIN
positive, SATURATED negative) pass. Any SHA mismatch or cassette MISS is a regression.

---

## 5. Procedure (summary)

1. Freeze inputs on the deterministic oracle; enumerate the deterministic-artifact list.
2. Run baseline N ≥ 3×. Record RACE per repeat, the per-fixture `verdict_map`, and SHA-256 for each
   deterministic artifact.
3. (Once) Run the no-change characterization to measure intrinsic spread; fill §4's band.
4. Apply the change. Run after N ≥ 3×. Record the same three families.
5. Evaluate: RACE within band on every repeat (§1.1) AND `verdict_map` keyed-equal (§1.2) AND all
   deterministic SHA-256 identical (§1.3).
6. All three hold → **same** (proceed). Any fail → **regression** (§2): revert or re-classify.
   Arbiter uncharacterizable → **BLOCKING STOP** (§3): investigate variance.
