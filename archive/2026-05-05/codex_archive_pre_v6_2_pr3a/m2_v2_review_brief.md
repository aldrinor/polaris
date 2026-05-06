M-2 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-2 v1 verdict: PARTIAL with 4 issues. All 4 integrated in v2.

## What changed in v2

1. **Registry scope (HIGH #1+#2 fix):** `_PHASE_A_ALLOWLIST` is now a
   tuple of curated artifact directories. `_build_runs()` validates
   each via `load_audit_ir()` at module import and raises
   `RegistryError` if:
   - Allowlisted directory missing
   - Strict load fails
   - Duplicate run_id across entries
   - Same slug across distinct run_ids
   Phase A allowlist = `(CANONICAL_DEMO_DIR,)` — just run-14.

2. **Routing identity:** `find_run_by_id(run_id)` added alongside
   `find_run_by_slug(slug)`. Slug uniqueness is now an enforced
   invariant of the registry, so slug-based routing is safe.

3. **Trust boundary docstring (MED #3 fix):** inspector_router.py
   docstring now correctly states the trust boundary is
   DEPLOYMENT-LEVEL (controlled-access environment), NOT
   application-level.

4. **Serializer (LOW #4 fix):** `_coerce()` now raises `TypeError`
   on unsupported leaf types with a message pointing at the gap.

## New tests
- test_listed_slugs_are_unique
- test_listed_run_ids_are_unique
- test_every_listed_run_loads_through_strict_loader
- test_find_run_by_id_returns_canonical / unknown
- test_phase_a_registry_returns_only_canonical_demo
- test_serializer_raises_on_unsupported_leaf_type / custom_object
- test_list_to_detail_round_trip_for_every_listed_run

72 -> 81 tests, all green.

## Your job

Quick verification pass. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- Are all 4 fixes integrated correctly?
- Does the registry-init fail-loud behavior actually fail loud (not
  just at request time)?
- Any new issues introduced?
- M-3 ready to consume the IR -> JSON path?

## Output

Write to `outputs/codex_findings/m2_v2_review/findings.md`:

```markdown
# Codex re-review of M-2 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration check
- [x/no] Registry scope (allowlist + load-time validation)
- [x/no] Slug uniqueness invariant + find_run_by_id
- [x/no] Trust boundary docstring corrected
- [x/no] Serializer raises on unsupported leaf

## New issues introduced
none / list

## Final word
GREEN to lock M-2 and proceed to M-3 / STILL-PARTIAL with edits.
```

Be terse. Under 150 lines.
