# POLARIS audit bundle — reviewer guide

This `.tar.gz` archive is a self-contained record of one POLARIS clinical-research run. A third party can verify any cited claim in the report against its underlying source without re-fetching from the open web.

## Files

- `manifest.yaml` — bundle inventory (file paths + SHA256 + content_type for each file).
- `manifest.yaml.asc` — GPG signature over `manifest.yaml`.
- `scope_decision.json` — slice 001: the scope-gate verdict for the user's question.
- `evidence_pool.json` — slice 002: the corpus retrieved for the question.
- `verified_report.json` — slice 003: the generated report after strict-verify.
- `metadata.json` — bundle-level metadata (versions, timestamps).
- `REVIEWER_README.md` — this file.
- `sources/<source_id>.txt` — full-text snapshot of every cited source (one file per source).

## Step 1 — verify the GPG signature

```
gpg --verify manifest.yaml.asc manifest.yaml
```

If this fails, the bundle has been tampered with and you should not trust the report.

## Step 2 — verify every file's SHA256

For each `path` listed in `manifest.yaml`'s `files[]` array, compute its SHA256 and compare against the `sha256` field. Any mismatch means the file has been altered after signing.

## Step 3 — random-claim audit (the <5min walkthrough)

1. Open `verified_report.json`.
2. Pick any verified sentence at random (`sections[*].verified_sentences[*]` with `verifier_pass = true`).
3. Read its `provenance_tokens` array. Each token has the form `[#ev:<source_id>:<start>-<end>]` where `start`/`end` are **CHARACTER offsets** into the snapshotted source text.
4. Open `sources/<source_id>.txt` (filename matches the token's `source_id`).
5. Take `text[start:end]` from that file (Python slice semantics — character offsets, not bytes). Confirm the substring relates to the sentence's claim.

## Truncation note

For very large sources (>200 KB), POLARIS truncates the snapshot at a UTF-8 codepoint boundary and appends a notice line: `[POLARIS audit-bundle truncation notice: source text truncated from N to M bytes per MAX_SOURCE_TEXT_BYTES policy.]`. Bundles are guaranteed to NOT ship cited spans that fall past the reachable body — the bundler refuses to build such a bundle (`cited_span_unreachable_after_snapshot`).

## Sovereignty note

POLARIS classifies every source by data-sovereignty tier. Bundles for runs whose corpus contained CLIENT / CAN_REAL / PRIVATE / UNKNOWN classifications were processed only on Canadian-sovereign infrastructure (no external LLM API calls).
