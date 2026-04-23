# Codex Pass-1 Review: V28 -> V29 Fix Plan

**Verdict**: CONDITIONAL

The V29 plan matches the approved Strategy beta cycle-1 scope: selector custody, generator injection, and per-anchor telemetry only. It correctly avoids trial-table cosmetics, M-47 relaxation, mechanism extraction, broad prompt rewrites, and the V30 two-stage rewrite.

This is CONDITIONAL-no-blockers for starting M-51. The plan is directionally approved, but M-51/M-52/M-53 need the revisions below before their implementation is considered complete.

## Per-item verdicts

| Item | Verdict | Reason |
|---|---|---|
| M-51 | root_cause_approved | Correct causal stage: selector is the earliest preventable point for "primary in live_corpus but absent from selected_rows." Prior gap is evidence-backed by V28 cross-review/gate verdict: SURPASS-4 and SURPASS-CVOT were in `live_corpus_dump.json` but absent from bibliography/prose. Acceptance/tests are mostly concrete. Needs implementation tightening around stable evidence identity and trim behavior. |
| M-52 | needs_revision | Correct backup causal stage at the selector -> generator boundary, and evidence-backed by M-44 injection firing 0 times because primaries were absent from `evidence_pool`. However the proposed fresh `ev_from_corpus_` ID should not be the default because it can split one corpus row into two identities and complicate bibliography/provenance matching. Preserve existing `evidence_id` when safe; generate a prefixed fallback only when absent or colliding with a different row. |
| M-53 | preservation_guard_approved | Correctly classified as a preservation guard, not root cause or band-aid. The telemetry is exactly the diagnostic needed for V30 planning. Needs field semantics tightened so `selected_into_pool`, `injected_into_section`, and `cited_in_verified_prose` are computed by canonical ev_id/bibliography mapping after strict verification. |

## Specific revisions required

1. **M-51 stable identity**: do not rely on Python `id(item)` as the durable duplicate check. Use canonical evidence identity: `evidence_id` when present, otherwise a stable fallback key such as normalized `(source_url, title, direct_quote[:N])`. Object identity can miss duplicates if the same row is copied or transformed.
2. **M-51 trim acceptance**: add an explicit fixture where insertion would exceed `max_rows`; assert final length is exactly `max_rows`, the inserted anchor primary remains, and a non-reserved tail row is removed.
3. **M-51 cap wording**: cap by `min(len(unique_primary_trial_anchors), max_rows)`, not a literal 11. V29 should not add an env knob.
4. **M-52 evidence IDs**: preserve live-corpus `evidence_id` if present and not colliding with a different row. Use `ev_from_corpus_{anchor_slug}_{n}` only for missing IDs or real collisions. Add tests for both paths.
5. **M-52 mutation contract**: when adding a live-corpus row to `evidence_pool`, require the same fields strict_verify and bibliography rendering need: `evidence_id`, `direct_quote`, `source_url`, `title`, `tier`, and any citation metadata currently consumed downstream.
6. **M-53 field semantics**: define the required fields consistently. The sample has 9 fields including `anchor`; keep all 9: `anchor`, `found_in_live_corpus`, `found_ev_id`, `selected_into_pool`, `injected_into_section`, `direct_quote_chars`, `direct_quote_adequate`, `cited_in_verified_prose`, `citation_count`.
7. **M-53 selected/cited checks**: compute `selected_into_pool` by canonical ev_id/key membership in the final generator evidence pool, not by dict membership. Compute `cited_in_verified_prose` after bibliography numbering is finalized, using the same ev_id -> bibliography number mapping that rendered the report.

## Answers to Claude's 5 self-critical questions

1. **M-51 cap mechanics**: use a derived cap, not fixed 11 and not an env knob. `cap = min(len(unique_primary_trial_anchors), max_rows)` is correct. The current tirzepatide fixture has 11 anchors, but the code should generalize.
2. **M-52 ev_id collision strategy**: prefer preserving the existing live-corpus `evidence_id` when it is present and unique. Use `ev_from_corpus_...` only as a fallback for missing IDs or collisions with a different row.
3. **M-53 quote adequacy threshold**: use `>=100 chars` for V29 custody parity with M-42b. Do not raise this to 500 in V29; full-frame extraction adequacy belongs to V30. Recording `direct_quote_chars` is enough to diagnose richer thresholds later.
4. **M-51 backward-compat test**: yes, add the explicit fixture. It should assert no anchors configured produces identical selected evidence IDs, order, length, and no new custody insertion telemetry.
5. **V29 scope confirmation**: confirmed. Defer trial-table cell correction, M-47 relaxation, two-stage generator architecture, and mechanism extraction to V30/V31. V29 is custody and telemetry only.

## Completeness Review

Claude did not miss a V29-scope architectural item that blocks Dims 1/4/5 from lifting. M-51 addresses the dominant selector loss. M-52 covers the generator-side backup if selection still fails or if an anchor primary is visible only through `live_corpus`. M-53 gives the required per-anchor diagnosis.

Residual risk remains, but it is explicitly V30/V31 risk: a primary can be found, selected, injected, and cited while still lacking enough quote text for ETD/full-frame extraction. That may keep Dims 4/5 at BEAT_ONE rather than BEAT_BOTH, but it does not invalidate V29's scope.

The only V29-blocking completeness requirement is the M-53 integration gate: the sweep must persist `v29_primary_custody.json`, and M-49 must fail if configured anchors that are found and quote-adequate do not become cited in verified prose. Without that artifact, V29 would be hard to diagnose and would not satisfy the Strategy beta cycle-1 contract.

## Implementation Order Confirmation

Approved order with one small revision:

1. M-51 selector custody first, including stable identity, trim test, cap-by-anchors, and no-anchor backward-compat fixture.
2. M-52 generator live-corpus injection second, with evidence_id preservation and collision fallback.
3. M-53 custody telemetry third, computed after strict_verify and bibliography numbering.
4. Clone V28 launcher to V29 with no broad env changes.
5. Run V29 sweep.
6. Run M-49 preservation plus deep content audits, using `v29_primary_custody.json` as the first diagnostic artifact if any anchor fails.

No pass-2 user check-in is required if Claude incorporates these revisions directly during implementation. Pass-2 should review code/tests, not re-litigate V29 scope.
