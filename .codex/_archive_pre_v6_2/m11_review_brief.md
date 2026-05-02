M-11 bounded upload + workspace data model — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-10 GREEN-locked after 8 review rounds. M-11 is the bounded-
upload foundation per FINAL_PLAN feature #5: workspaces hold
10-50 persistent docs, with page/sheet/slide/timecode provenance
(NOT just char offsets), parser status state machine, bounded
enforcement, soft-delete with audit trail.

The dominant Phase B risk is **provenance integrity** — every
chunk in M-12's Question-Bound Corpus Brief must trace back to a
precise location in the source upload. The schema is
load-bearing: M-12's claim IDs reference these provenance
records, and we cannot refactor the schema after M-12 lands
without breaking citations. So the schema accepts all 5 variants
(TextSpan / PdfSpan / SheetCell / SlideRegion / Timecode) from
day 1, even though Phase B only emits TextSpan + (stub) PdfSpan.

## What landed (commit 778182f)

**`src/polaris_graph/audit_ir/provenance.py`** (~150 lines):
- 5 frozen dataclass variants. Each carries `upload_id` + a
  `kind` ClassVar for serialization.
- `to_dict()` / `from_dict()` round-trip via JSON. SlideRegion's
  bbox tuple is restored from list after JSON round-trip.
- `from_dict` raises ValueError on unknown / malformed kind.

**`src/polaris_graph/audit_ir/workspace_store.py`** (~330 lines):
- `WorkspaceStore` mirrors M-8 JobQueue patterns: SQLite WAL,
  per-call connections, FK on, atomic transitions.
- Tables: workspaces, uploads, upload_chunks. Indexed on
  workspace_id + parser_status.
- `ALLOWED_PARSER_TRANSITIONS`: pending → parsing → parsed/failed
  (terminal). Soft-delete via `deleted_at` blocks further
  transitions but preserves the row.
- `upload_file()` enforces `max_docs` cap atomically and raises
  `BoundedError` (LAW II — fails loud, no silent truncation).
  Cap is env-configurable via `PG_WORKSPACE_MAX_DOCS` (default
  50) per LAW VI; garbage values fall back to default.
- `transition_parser_status()` uses UPDATE..WHERE..AND
  parser_status=X for atomicity (rejects concurrent transitions).
- `insert_chunks()` / `list_chunks()` for parsed content + JSON
  provenance.

**`src/polaris_graph/audit_ir/parser_runner.py`** (~170 lines):
- `ParserRunner` ABC: `can_handle(filename, content_type)` +
  `parse(upload_id, storage_path) -> ParseResult`.
- `TextParser` (Phase B real impl): chunks plain text into
  TextSpan-tagged pieces. Chunk size env-configurable
  (`PG_TEXT_CHUNK_CHARS`, default 1500). Empty file → 0 chunks.
  Missing file → ParserError. Handles .txt / .md / text/* MIME.
- `PdfParser` (Phase B stub): fails loud with "not yet supported"
  rather than silently returning an empty parse. Reserves PdfSpan
  in the schema without pulling PyMuPDF.
- `select_parser()` returns first runner that claims it can
  handle the upload, or None.

**`inspector_router.py`** — 8 new endpoints:
  POST   /api/inspector/workspaces                 (create)
  GET    /api/inspector/workspaces                 (list)
  GET    /api/inspector/workspaces/{ws_id}         (get)
  POST   /api/inspector/workspaces/{ws_id}/uploads (multipart)
  GET    /api/inspector/workspaces/{ws_id}/uploads (list)
  GET    /api/inspector/uploads/{upload_id}        (get)
  DELETE /api/inspector/uploads/{upload_id}        (soft-delete)
  GET    /api/inspector/uploads/{upload_id}/chunks (parsed)

Upload pipeline: bounded check FIRST (before disk write), reserve
row to get upload_id, write bytes to `<state>/<workspace>/<upload>/
<filename>`, then sync-parse via `select_parser()`. Bounded
violation returns 409, unknown workspace 404.

**Tests: 62 new (12 provenance + 23 workspace_store + 13 parser
+ 14 API). Phase B suite 227 → 289.**

## Anti-scope (deferred — please do NOT push back on these)

- Filter modes (uploaded-only / web-only / blended) — M-12 owns
  retrieval over uploads.
- Real PDF/sheet/slide/audio parsers — Phase C M-11.5. The schema
  reserves the variants; only TextSpan is emitted now.
- Async parsing job — Phase C. PdfParser stubs out the slow path.
- ACL / RBAC beyond workspace_id scoping — Phase C.

## Your job

Code review for M-11. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Provenance schema completeness.** Will M-12's Corpus Brief
   citation needs land cleanly on this schema, or will it need a
   migration? Specifically: will a citation like "Smith et al.
   2023, Table 2" deserialize as SheetCell, PdfSpan, or something
   else?

2. **State machine correctness.** ALLOWED_PARSER_TRANSITIONS
   covers pending → parsing → parsed/failed. Is anything
   missing? Should soft-delete from terminal states be allowed
   (currently any state is soft-delete-able)?

3. **Bounded enforcement atomicity.** The COUNT happens in the
   same connection as the INSERT but not in an explicit
   transaction. Race condition where two concurrent uploads both
   see (max_docs - 1) and proceed?

4. **Storage path security.** `<state>/<workspace>/<upload>/
   <filename>` — does an attacker with workspace access bypass
   path containment via `..` or absolute paths in `filename`?

5. **PdfParser fail-loud.** Currently raises ParserError → status
   becomes failed. Acceptable? Or should we route PDFs to status
   `pending` with a "parser pending implementation" message so
   they don't look like data corruption?

6. **upload_to_workspace() reaches into store._connect()** to
   update storage_path post-insert. That's a layering violation;
   the store should expose a method. Acceptable for Phase B or
   refactor?

7. **TextParser chunking is naive** (fixed N chars). Will mid-
   sentence boundaries cause issues for M-12 retrieval?

8. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m11_review/findings.md`:

```markdown
# Codex review of M-11

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Provenance schema readiness for M-12
Does the schema cover M-12 needs without migration?

## Recommended changes
If PARTIAL.

## M-12 readiness
Is the workspace + chunk infrastructure ready for the
Question-Bound Corpus Brief?

## Final word
GREEN to lock M-11 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines.
