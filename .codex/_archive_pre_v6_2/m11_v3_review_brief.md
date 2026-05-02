M-11 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-11 v2 verdict: PARTIAL. 1 MED + 2 LOW remained:
1. MED: update_storage_path() didn't check rowcount
2. LOW: TextParser exact-matched MIME (rejected "text/plain; charset=utf-8")
3. LOW: provenance numeric validation accepted booleans

All 3 integrated in v3 (commit 5f71acb).

## What changed in v3

`workspace_store.update_storage_path`:
- Now checks `cur.rowcount` after the UPDATE; raises
  WorkspaceStateError if 0 (concurrent soft-delete won the race
  between pre-read and UPDATE).

`inspector_router.upload_to_workspace`:
- Catches WorkspaceStateError from update_storage_path; calls
  `storage_path.unlink(missing_ok=True)` to clean up the bytes,
  then re-raises as 409. No orphaned files for deleted uploads.

`parser_runner.TextParser.can_handle`:
- Splits content_type on ";" and lowercases the base before the
  allowlist comparison.
- Accepts: "text/plain; charset=utf-8", "text/plain;charset=ascii",
  "TEXT/PLAIN; CHARSET=UTF-8", "text/markdown; charset=utf-8",
  "text/x-markdown ; charset=us-ascii".

`provenance._validate`:
- New `_is_strict_int` / `_is_strict_number` helpers reject `bool`
  explicitly (Python's bool is an int subclass — isinstance(True, int)
  is True, which let `{"page": true}` deserialize as page=1).
- All 5 variants use the strict checks.

Tests: 12 new (5 charset MIME variants + 6 bool-rejection +
1 storage_path race rowcount).

M-11 module 94 → 106. Phase B suite 321 → 333 green.

## Your job

Final verdict on M-11. GREEN / PARTIAL / DISAGREE.

If GREEN, M-11 is locked and Phase B can proceed to M-12
(Question-Bound Corpus Brief).

## Output

Write to `outputs/codex_findings/m11_v3_review/findings.md`:

```markdown
# Codex final review of M-11 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] update_storage_path checks rowcount + cleans up orphaned bytes
- [x/no] TextParser handles parameterized MIMEs
- [x/no] Provenance validation rejects bool

## Final word
GREEN to lock M-11 + proceed to M-12 / PARTIAL with edits.
```

Be terse. Under 60 lines.
