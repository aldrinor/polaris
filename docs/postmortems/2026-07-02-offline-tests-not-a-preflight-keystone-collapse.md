# Postmortem: Offline tests are not a preflight — a stale cache hid three stacked bugs

- **Date:** 2026-07-02
- **Theme:** evaluation
- **Severity:** high (a "sufficient" fix still collapsed to 0 verified on the live re-prove)
- **Evidence:** `keystone_collapse_forensic_consolidated.md` PART 2 / PART 3 (Bug A/B/C, #1217); memory `feedback_offline_tests_not_real_preflight_prove_small_real_run_2026_07_02`

## What happened

The keystone recall fix passed 17 of 17 distiller unit tests offline and looked
sufficient. The live re-prove still collapsed to 0 verified sections. Reading the
live per-rejection trace (`PG_DISTILL_DEBUG`) surfaced three stacked bugs, each
invisible to the layer above it:

- **Bug A — orphaned citation:** the citation marker sat in a separate sentence
  from the claim it supported, so the claim read as uncited.
- **Bug B — paraphrased support_quote:** a paraphrased `support_quote` was
  rejected at the locate step because it was not found verbatim.
- **Bug C — stale cache:** `section_distiller_v2` served pre-fix results from
  cache because the validation logic changed without a `DISTILLER_VERSION` bump,
  so the cache key did not reflect the new logic.

## Root cause

Offline unit tests exercise one layer in isolation and cannot see a stacked
failure or a stale cache. The stale cache is the sharpest instance: because the
tuning knob was not part of the cache key, a real code fix was served old results
and looked like a no-op — a silent false-negative. Only a small real run that
reads the actual live output could show that the fix did not take effect and that
three separate defects were compounding.

## Contributing factors

- 17/17 green offline was read as evidence the pipeline worked, when it only
  proved the distiller module behaved in isolation.
- The three bugs masked one another: fixing any one alone would still show a
  collapse, so a single-layer view could not explain the result.
- The cache key omitted the changed validation logic, so a correct fix produced
  identical (stale) output and looked like it did nothing.

## Lessons (promoted to)

- Offline tests are not a preflight. Prove each fix in a small REAL run that
  reads the actual live output; add the tuning knob to the cache key so logic
  changes bust the cache; unit tests passing is not evidence the pipeline works.
- Promoted to memory:
  `feedback_offline_tests_not_real_preflight_prove_small_real_run_2026_07_02.md`.
- Reinforces the standing rule to read the live per-rejection trace forensically
  rather than trusting an aggregate pass count.
