# Flakiness Policy & Quarantine (Phase 3B / S3)

**Status:** Phase 3B. CI is **report-only** (see `.github/workflows/python_ci.yml`,
`continue-on-error: true`). This document defines the bar a test must clear before
the suite may be ratcheted from report-only to *required*, the absolute rule that
governing tests are never quarantined, and the tracked (currently empty) quarantine
list for non-governing flaky tests.

Nothing in this document changes runtime code. No test is deleted. The quarantine
list below is empty because the 3B characterization sweep produced **no substantiated
multi-run flaky data** (see "Measurement status" below) — reporting node-ids we could
not confirm would be fabrication.

---

## 1. The non-flakiness BAR (report-only → required)

A test — and the suite as a whole — is only considered **stable** when it meets ALL of:

| Criterion | Threshold |
|-----------|-----------|
| Consecutive green CI runs | **K = 10** consecutive runs of the governing CI test command with zero failures for the test |
| Green wall-clock window | **N = 14** days of continuous green on the target branch, no red governing runs |
| Determinism check | 3× consecutive **strictly serial** local runs (`-p no:randomly -p no:cacheprovider`) with identical pass/fail sets |
| Zero governing instability | Every test in the governing list (§3) passes on every one of the K runs — no exceptions |

**Ratchet action:** only after K **and** N are both satisfied may
`continue-on-error: true` be removed from the report-only job (`python_ci.yml`) and the
job be promoted to a required status check. Until then CI **stays report-only**.

### Definition of "flaky"
A test is **flaky** if, across the K-run window (or the 3× serial determinism check),
it fails in **some but not all** runs on unchanged code. A test that fails in **all**
runs is not flaky — it is a **consistent failure** (real debt / regression), tracked
separately and NOT eligible for the flaky-quarantine mechanism.

### Serialization requirement (hard)
The suite is **not safe to run concurrently with itself**. The 3B sweep confirmed that
two overlapping pytest sessions sharing filesystem / temp / port / model state produce a
burst of early failures that are **artifacts of parallel execution, not flakiness**. Any
characterization run used to apply this policy MUST serialize (a single pytest session at
a time). Failures observed under self-concurrency are disqualified as evidence.

---

## 2. ABSOLUTE RULE — governing tests are never quarantined

The **governing measurement** is the oracle RACE / faithfulness / crown-jewel set listed
in §3. These encode the correctness guarantees the product exists to make.

> **If any governing test is unstable, that is a BLOCKING STOP.**
> A governing test is **NEVER** quarantined, `@pytest.mark.flaky`-tagged, skipped, or
> added to the quarantine list. Instability in a governing test halts the ratchet and the
> release — it is a defect to be root-caused and fixed, never suppressed.

Only **non-governing** tests are ever eligible for the tracked quarantine mechanism in §4.

---

## 3. The GOVERNING test set (never quarantined)

- `tests/oracle/test_cassette.py` — oracle acceptance / deterministic record-replay cassette
- `tests/crown_jewels/test_cj_001_two_family_segregation.py`
- `tests/crown_jewels/test_cj_002_provenance_tokens.py`
- `tests/crown_jewels/test_cj_003_strict_verify.py`
- `tests/crown_jewels/test_cj_004_zero_verified_abort.py`
- `tests/crown_jewels/test_cj_005_corpus_approval.py`
- `tests/crown_jewels/test_cj_006_budget_imputation.py`
- `tests/crown_jewels/test_cj_007_delimiter_sanitization.py`
- `tests/crown_jewels/test_cj_008_entailment_correctness.py`
- `tests/polaris_graph/test_fx02_strict_verify_floors_iready017.py`
- `tests/polaris_graph/test_l4_multilingual_strict_verify.py`
- `tests/polaris_graph/test_strict_verify_cleaned_text_integration.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify_entailment.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify_entailment_live.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify_qualifier_retention.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify_telemetry.py`
- `tests/polaris_graph/clinical_generator/test_strict_verify_unknown_mode_warning.py`
- `tests/dr_benchmark/test_lane_b_gen_faithfulness_completeness_beatboth5.py`
- `tests/polaris_graph/test_f07_f04_faithfulness_resume_iarch004.py`
- `tests/polaris_graph/generator/test_breadth_corroborator_faithfulness_iarch007.py`
- `tests/v6/acceptance/test_dramatiq_acceptance.py` — RACE/broker acceptance (needs a live broker; see infra-gating note below)
- `tests/v6/acceptance/test_runs_db_integration.py` — acceptance (needs a live DB; see infra-gating note below)

> **Infra-gating is not quarantine.** The two `tests/v6/acceptance` entries require live
> external infrastructure (a message broker / a database) that the hosted CI runner does
> not provide, so the default CI invocation excludes that directory via
> `--ignore=tests/v6/acceptance`. This is an **environment precondition**, not a stability
> waiver: these tests are still governing, are run in every environment that has the broker
> / DB, and are **never** `@pytest.mark.flaky`-tagged, added to `docs/flaky_quarantine.txt`,
> or excused for instability. If either fails where its infra is present, that is a BLOCKING
> STOP under §2 exactly like any other governing test. The never-quarantine rule (§2) is
> about suppressing *flakiness*; `--ignore` here suppresses nothing about correctness — it
> only declines to run a test whose preconditions are absent.

---

## 4. Quarantine mechanism (non-governing only)

**Current quarantine list: EMPTY.** See `docs/flaky_quarantine.txt`.

When a **non-governing** test is confirmed flaky under the §1 bar (fails in some-but-not-all
serial runs on unchanged code), it is quarantined by **tracking, not deletion**:

1. Add the node-id to `docs/flaky_quarantine.txt` with date, evidence (which runs
   passed/failed), and an owner/issue link.
2. Optionally tag the test `@pytest.mark.flaky` (marker registered in `pytest.ini`; see §5).
   The marker is a **label only** — it does not change collection or selection and does not
   remove the test from any run. Quarantine here means *documented and tracked*, never
   auto-skipped in a way that hides regressions.
3. The test **stays in the suite and keeps running.** Quarantine is a tracking state that
   excludes the test from the ratchet's "must be green" accounting until it is fixed — it
   is never removed from execution and never deleted.

Governing tests (§3) are categorically ineligible for steps 1–3.

---

## 5. Measurement status (3B sweep — honest record)

The 3B characterization sweep did **not** finish within the available window:

- The 3× strictly-serial sweep did not complete. Run 1 was ~70% through when time
  expired; runs 2 and 3 never started. No run emitted a completed pass/fail summary or
  JUnit XML (pytest writes `-rf` and `--junit-xml` only at session end).
- Apparent "completions" (e.g. "9256 passed", "RUN1 END rc=1") were verified **phantom**
  background-task notifications — the referenced processes were still running and no XML
  existed. Ground truth was taken only from `pgrep`, the driver's `serial.log`, and the
  presence of `runN.xml`.
- The slow `tests/polaris_graph` ML tail (retrieval / synthesis / clinical_retrieval / llm
  doing real CPU embedding + NLI inference) plateaus at ~68–70% for minutes while CPU-active
  (~7–8 cores busy, state R) — slow, not hung. A single serial pass over the subset takes
  ~11–13+ min wall.

**Consequence:** `flaky_tests = []` and `consistent_failures = []` are returned **empty
because there is no completed multi-run data to substantiate either**, not because the
suite is proven clean. To finish: let the serial driver complete all 3 runs, then diff the
three `run*.xml` files — node-ids failing in *some but not all* runs are flaky (→ §4
quarantine, non-governing only); node-ids failing in *all 3* are consistent failures
(→ separate debt triage, not quarantine).

### Related findings flagged during the sweep (not flakiness)
- **Collection errors: 35, not 11.** This branch (`chore/review-readiness-3b`) shows 35
  collection ImportErrors in the `tests/unit tests/polaris_graph` subset (verified via
  `--co`), vs. the 11 the task expected. By directory: audit_bundle (10), api (8),
  benchmark (8), unit (6: `test_clarification_agent`, `test_hle_benchmark`, `test_mesh_api`,
  `test_mesh_cli`, `test_mesh_snapshot`, `test_perspective_tracking`), plus
  `audit_ir/test_manifest_augment`, `anti_sycophancy/test_stance_delta`, and top-level
  `test_demo_smoke`. The recent config migration on this branch ("migrate 832 os.getenv
  call sites to central resolve()", "central defaults registry") is a plausible source and
  should be investigated. These are collection errors, **not** flaky tests.

---

## 6. CI scanning (report-only) — see `python_ci.yml`

Supply-chain / hygiene scanning is added to the **report-only** `python-ci` workflow as
`continue-on-error` steps (dependency-hash / `pip check` + `pip-audit`, license scan via
`pip-licenses`, secret scan via `detect-secrets`). These are informational and do **not**
block merges. CI remains report-only until the §1 bar is met. See
`docs/review_readiness/ci_scanning.md` for what each scan covers and how to read its output.
