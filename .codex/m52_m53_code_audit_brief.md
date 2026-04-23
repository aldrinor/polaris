M-52 + M-53 code audit — V29 Strategy β cycle 1, items 2 and 3 of 3.

## Commits

- M-52: `0ac24cb` PL: M-52 — generator-side pull from live_corpus (V29-b)
- M-53: `332265b` PL: M-53 — per-anchor custody telemetry + M-49 V29 assertion (V29-c)

## Plan reference

`outputs/audits/v28/fix_plan_v29.md` M-52 + M-53. Your pass-1 plan
review CONDITIONAL-no-blockers at
`outputs/codex_findings/v29_fix_plan_review_pass1/findings.md`.

Revisions #4-7 woven in — confirm they're correctly applied.

## M-52 changes

`src/polaris_graph/generator/multi_section_generator.py`:

New function `_m52_pull_from_live_corpus(evidence_pool, live_corpus,
primary_trial_anchors)`:
- Scans live_corpus for anchor-matched primaries not in evidence_pool
- Pulls row into evidence_pool (in-place mutation)
- **Revision #4** ev_id strategy:
  - Preserve live-corpus `evidence_id` when present and not
    colliding with a different row already in pool
  - Fallback `ev_from_corpus_{anchor_slug}_{n}` for
    missing/collisions
  - Skip entirely if canonical content key already in pool (same
    row under some id)
- **Revision #5** mutation contract:
  - Required fields: direct_quote, tier, source_url-or-url
  - Missing any → skip (fail-loud, not silent)
  - Title fallback from statement/source_title when title absent
    (M-48 live-row schema)

Wired into `generate_multi_section_report` via new `live_corpus`
param (backwards-compat None default). Orchestrator passes
`retrieval.evidence_rows`.

M-52 pulls logged into `m44_injection_log` with
`action="injected_from_corpus"` so
`m44_primary_citation_telemetry.json` surfaces the corpus-pull
path.

## M-53 changes

`src/polaris_graph/generator/multi_section_generator.py`:

New function `_m53_compute_primary_custody_log(...)` computed AFTER
bibliography + section results finalize.

**Revision #6** 9-field schema per anchor:
- anchor
- found_in_live_corpus (bool)
- found_ev_id (str)
- selected_into_pool (bool)
- injected_into_section (str | None)
- direct_quote_chars (int)
- direct_quote_adequate (bool; ≥100 chars)
- cited_in_verified_prose (bool)
- citation_count (int)

**Revision #7** computation:
- `selected_into_pool`: canonical `_m42e_detect_primary_for_anchor`
  scan of `evidence_pool` (not dict-key membership)
- `cited_in_verified_prose`: uses ev_id → biblio_num mapping built
  from `global_biblio` (finalized bibliography); regex-counts
  `[biblio_num]` across `section_results[].verified_text`
- `injected_into_section`: derived from `m44_injection_log` action
  types (injected / already_present / swap_in_for_* /
  injected_from_corpus)

New MultiSectionResult field `v29_primary_custody_log`.
Orchestrator writes `v29_primary_custody.json`.

M-49 extension in `test_m49_v28_preservation.py`:
- `TestM53V29PrimaryCustody::test_all_anchors_cited_in_verified_prose`
  fails V29 sweep if any configured anchor has
  `cited_in_verified_prose=false`, with per-anchor failure-reason
  diagnostic (which custody step broke)
- `test_custody_log_has_required_9_fields` schema assertion

## Tests

- `tests/polaris_graph/test_m52_generator_corpus_injection.py` — 14 tests
- `tests/polaris_graph/test_m53_custody_telemetry.py` — 10 tests
- 35/35 combined M-51/52/53 regression; 1086/1088 total (2 pre-
  existing unrelated failures: M-201 stale label, M-42 NICE V26-era)

## What to audit

**M-52**:
1. ev_id preservation logic: evidence_id present + no collision →
   preserved; absent OR collision → prefixed fallback with suffix
   uniqueness. Any edge case missed?
2. Mutation contract: all rows that reach `evidence_pool` satisfy
   strict_verify field contract (direct_quote + tier + url)?
3. Canonical content-key detection correctly distinguishes "same
   row, new id" (skip) from "different row, same id" (fallback)?
4. Backwards-compat: live_corpus=None = no-op at call sites?

**M-53**:
5. 9-field schema complete?
6. `selected_into_pool` uses anchor-detection over evidence_pool,
   not dict-key lookup?
7. `cited_in_verified_prose` uses finalized bibliography
   numbering? (Confirmed computed AFTER `global_biblio` in my code.)
8. `injected_into_section` correctly handles pool-level
   (injected_from_corpus) as None (no specific section)?
9. M-49 extension fails the sweep with precise
   per-anchor diagnostic when any anchor fails custody?

## Strategic context reminder

Your pass-1 plan review:
> "The only V29-blocking completeness requirement is the M-53
> integration gate: the sweep must persist v29_primary_custody.json,
> and M-49 must fail if configured anchors that are found and
> quote-adequate do not become cited in verified prose."

Both gates implemented. Please confirm they're correctly wired.

## Output

Write verdict to
`outputs/codex_findings/m52_m53_code_audit/findings.md`.

On READY / CONDITIONAL-no-blockers: Claude proceeds to V29 sweep
launch (task #16). On any BLOCKER: surface immediately.
