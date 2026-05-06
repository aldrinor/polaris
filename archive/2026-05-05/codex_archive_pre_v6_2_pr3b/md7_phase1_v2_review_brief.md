M-D7 phase 1 v2 review (commit bd9cae4).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round 1 (commit 9201fe7) verdict was PARTIAL with 2 findings:
  1. [HIGH] DOI canonicalization too loose
  2. [HIGH] get() race between SELECT + UPDATE under autocommit

This v2 commit closes both.

## What changed in v2

`src/polaris_graph/audit_ir/retrieval_cache.py`:

1. DOI canonicalization tightened:
   - `_canonicalize_doi`: drops URL fragment (`#abstract`),
     query string (`?utm_source=x`), trailing slash before
     prefix check
   - New `_DOI_FULL_RE` per Crossref + ANSI/NISO Z39.84-2010:
     `^10\.[0-9]{4,9}(?:\.[0-9]+)*/[^\s?#]+$`
   - Strict 4-9 digit registrant (rejects `10.123/foo`)
   - Non-empty suffix without whitespace/?/# chars
   - Strings that fail strict shape fall back to URL
     canonicalization (which itself drops trailing `/`)

2. get() atomicity:
   - Wrapped SELECT + UPDATE in `BEGIN IMMEDIATE` / `COMMIT`
     with try/ROLLBACK on exception
   - BEGIN IMMEDIATE acquires write lock at transaction start
     so no concurrent put()/evict() can interleave between the
     two statements
   - Caller now sees a coherent (payload, last_hit_at) pair

`tests/polaris_graph/test_md7_retrieval_cache.py`: 32 tests
(was 29). New:
  - test_doi_canonicalization_strips_url_decoration
    (6 forms: bare, URL prefix, trailing /, query, fragment,
    doi: scheme, mixed case)
  - test_doi_strict_shape_rejects_near_doi (3 cases:
    short registrant, long registrant, no suffix)
  - test_get_select_update_is_atomic_under_concurrent_put
    (50 writers + 50 readers; SHA-vs-payload mismatch
    detection — would catch the round-1 race)

## Your job

GREEN-LOCK or PARTIAL.

1. **Round 1 fix integration**:
   - [ ] DOI canonicalization handles all URL decorations
   - [ ] DOI shape regex tight enough; near-DOI fallback to URL
   - [ ] get() atomic under concurrent writers

2. **Stop criterion**: GREEN-lock if remaining findings are
   minor (additional URL forms, doc nits, integrity hardening
   that's phase 2 territory). PARTIAL only if you find:
     (a) Foundational bug introduced by v2
     (b) The DOI regex still misses a real-world form
     (c) The BEGIN IMMEDIATE atomicity is incomplete (still
         a race somewhere)
     (d) Cross-workspace isolation broken by v2

3. **Phase 2 readiness**: with v2's DOI canonicalization +
   atomic get(), can honest_pipeline wire-in proceed
   cleanly?

## Output

`outputs/codex_findings/md7_phase1_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D7 phase 1 v2 (commit bd9cae4)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 1 fix integration
- [x/no] DOI canonicalization handles URL decorations
- [x/no] DOI strict shape rejects near-DOI inputs
- [x/no] get() atomic under concurrent writers

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D7 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
