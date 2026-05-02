M-D10 phase 1 v3 review (commit a85812f).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round count progression: R1=3 → R2=1 (converging fast).

Round 2 (commit de6b987) PARTIAL had 1 HIGH finding: v1
schema migration path missing. Codex reproduced
`OperationalError: no such column: cache_key` opening a v1 DB
with the new store.

## What changed in v3

`src/polaris_graph/audit_ir/freshness_monitor.py`:
  - New `_upgrade_v1_to_v2(conn)` static method runs before
    main schema script
  - Detection: table exists + no `cache_key` column
  - Migration: rename old → drop old indexes → create v2
    schema → walk old rows + compute canonical cache_key →
    insert into v2 → drop renamed old table
  - Uncanonicalizable v1 rows tagged
    `migration_failed:<url>` (no silent drop)
  - Idempotent (re-running on migrated DB is no-op)

`tests/polaris_graph/test_md10_freshness_monitor.py`:
  - 34 tests (was 31). New:
    * test_v1_to_v2_schema_migration_backfills_cache_key
      (full hand-built v1 schema, 2 rows, post-migration
      verification of canonical keys + EoC acceptance)
    * test_v1_to_v2_migration_idempotent
    * test_v1_to_v2_migration_handles_uncanonicalizable_v1_row

## Your job

GREEN-LOCK or PARTIAL.

1. **Round 2 fix integration**:
   - [ ] migration runs before schema-create on v1 DBs
   - [ ] cache_key backfilled from source_url canonicalization
   - [ ] CHECK constraint extended to accept EoC after migration
   - [ ] uncanonicalizable rows preserved (tagged, not dropped)
   - [ ] idempotent

2. **Stop criterion**: GREEN-lock if remaining findings are
   minor. PARTIAL only if you find:
     (a) Migration corrupts or loses data
     (b) Migration fails on a realistic v1 row I missed
     (c) v3 introduces any regression in v2 functionality

3. **Phase 2 readiness**: with substrate + migration stable,
   can real Crossref/PubMed detectors layer on cleanly?

## Output

`outputs/codex_findings/md10_phase1_v3_review/findings.md`:

```markdown
# Codex round 3 — M-D10 phase 1 v3 (commit a85812f)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 2 fix integration
- [x/no] migration runs on v1 DBs
- [x/no] cache_key backfilled
- [x/no] CHECK constraint extended
- [x/no] uncanonicalizable rows preserved
- [x/no] idempotent

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D10 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
