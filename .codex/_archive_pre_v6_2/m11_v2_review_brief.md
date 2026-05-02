M-11 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-11 v1 verdict: PARTIAL with 3 High + 2 Medium + 1 Low:

1. HIGH: filename used raw → path traversal + absolute-path escape
2. HIGH: bounded enforcement non-atomic (autocommit + COUNT/INSERT
   in separate statements → cap oversubscription under concurrency)
3. HIGH: parser_status UPDATE didn't gate on deleted_at IS NULL →
   delete/transition race could mutate deleted rows
4. MED: insert_chunks() ignored deleted_at → in-flight parses could
   append chunks to deleted uploads
5. MED: TextParser claimed any text/* MIME → CSV/TSV silently
   stored as TextSpan
6. LOW: from_dict() only validated arity, not types/shape

All 6 integrated in v2 (commit 0e2e7d5).

## What changed

**Path traversal (HIGH 1)**:
- `inspector_router._sanitize_upload_filename`: reduces filename
  to basename. Neutralizes:
    - "../" / "..\\" (path traversal)
    - "/etc/passwd", "C:/abs.txt", "C:\\abs.txt" (absolute paths)
    - "subdir/name.txt" (nested paths)
    - "clean\x00.txt" / "clean%00.txt" (NUL byte injection,
      literal + URL-encoded form)
    - mixed separators ("foo/bar\\baz.txt")
    - dot-only / empty
- Defense-in-depth: after constructing the storage path, resolves
  it and verifies via `Path.relative_to(workspace_root_resolved)`
  that it's inside the workspace root. Refuses + soft-deletes the
  reservation if not (e.g. symlink-redirect attack).

**Bounded race (HIGH 2)**:
- `workspace_store.upload_file`: now wraps workspace lookup +
  count + insert in `BEGIN IMMEDIATE` transaction. SQLite
  IMMEDIATE acquires the write lock at BEGIN, so a second thread's
  BEGIN IMMEDIATE blocks until the first commits. Test:
  `test_bounded_enforcement_is_atomic_under_concurrency` runs
  two threads on max_docs=1; asserts exactly one BoundedError.

**Delete/transition race (HIGH 3)**:
- `workspace_store.transition_parser_status`: UPDATE now includes
  `AND deleted_at IS NULL`. Pre-read still happens for the
  user-facing error message; the atomic UPDATE gates on the live
  state regardless.

**insert_chunks gate (MED 4)**:
- `workspace_store.insert_chunks`: pre-check + BEGIN IMMEDIATE
  transaction with sub-select on `deleted_at IS NULL` before the
  executemany. Atomic relative to a concurrent soft-delete.

**TextParser narrowing (MED 5)**:
- `parser_runner.TextParser.can_handle`: now uses an explicit
  allowlist:
    MIMEs: text/plain, text/markdown, text/x-markdown
    Extensions: .txt, .md, .text
  text/csv, text/tab-separated-values, text/html, text/anything
  no longer claim. Phase B routes them to status='pending' until
  Phase C ships a SheetParser.

**Provenance validation (LOW 6)**:
- `provenance._validate`: per-variant type/shape checks. TextSpan/
  PdfSpan offsets non-negative ints with start ≤ end; PdfSpan.page
  ≥ 1; SheetCell.sheet/cell_range non-empty strings; SlideRegion.
  bbox 4-tuple of numerics or None; Timecode.start_s/end_s numeric
  with start ≥ 0 and start ≤ end; upload_id non-empty across all.

**Layering cleanup**:
- `workspace_store.update_storage_path`: new store-owned API for
  the post-insert path update. Replaces the inspector_router
  layering violation that reached into `store._connect()`.

Tests: 32 new (10 path-traversal + 9 provenance validation +
3 race + 4 store API + 2 parser narrowing + 4 misc). M-11 module
62 → 94. Phase B suite 289 → 321 green.

## Your job

Final verdict on M-11. GREEN / PARTIAL / DISAGREE.

Quick verification — please probe:
1. Path traversal: any filename pattern that escapes the workspace
   root after sanitization?
2. Bounded race: is BEGIN IMMEDIATE sufficient, or is there still
   a window where two threads can both clear the cap check?
3. Delete races: any other table operation (transition,
   insert_chunks, update_storage_path, soft_delete itself) that
   could let a deleted row be mutated?
4. TextParser narrowing: any plain-text-like MIME we should still
   accept that's missing from the allowlist?
5. Provenance validation: any field we missed?
6. Anything else you see.

If GREEN, M-11 is locked and Phase B can proceed to M-12
(Question-Bound Corpus Brief).

## Output

Write to `outputs/codex_findings/m11_v2_review/findings.md`:

```markdown
# Codex re-review of M-11 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] Path traversal blocked
- [x/no] Bounded enforcement now atomic
- [x/no] Delete/transition race closed
- [x/no] Delete/insert_chunks race closed
- [x/no] TextParser narrowed (no CSV/TSV silent absorption)
- [x/no] Provenance validation tightened

## New issues
none / list

## Final word
GREEN to lock M-11 + proceed to M-12 / PARTIAL with edits.
```

Be terse. Under 100 lines.
