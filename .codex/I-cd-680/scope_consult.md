# Codex DECISION consult — I-cd-680 scope (PHASE 1)

Operator delegates scope decisions to Codex, highest long-term quality. Decide the scope of #680.

## The fork

#680 as written = a 600-1000 LOC pipeline-A capability extension: thread per-sentence provenance + per-evidence-span char-offsets (span_start/span_end) through run_one_query + the verifier, emit a typed EvidenceContract JSON. Its OWN sequencing note says: "Defer to AFTER the demo. Inspector currently consumes the slice-chain bundle.tar.gz path which is sufficient for Carney delivery. EvidenceContract is a Phase-2 capability."

BUT the 2026-05-20 re-prioritization (your APPROVE) put #680 in PHASE 1 as the foundation that unblocks #542 (follow-up UI) + #543 (compare view), which you flagged as fixture-only (404 on real runs).

## Verified facts (grep, this branch)

- `src/polaris_v6/api/followup.py:24` + `compare.py:18` resolve run_id ONLY via `_GOLDEN_RUN_INDEX` (golden fixtures) → real runs 404. THIS is the #542/#543 blocker.
- `src/polaris_v6/api/bundle.py:89` `GET /runs/{run_id}/bundle.tar.gz` ALREADY resolves real run_id → artifact_dir → signed bundle via run_store (I-cd-020 Option D). Inspector (#631) consumes this and works on real runs.
- So the inspector real-run path EXISTS; only followup + compare are fixture-locked.

## The question

For PHASE 1 (unblock #542/#543 for the demo), is the right scope:

A. **Full #680** — build the 600-1000 LOC EvidenceContract char-offset capability now. (Issue says defer post-demo; LAW II fabrication risk on synthesizing offsets pipeline-A never recorded.)

B. **Minimal real-run resolution** — make followup.py + compare.py resolve real run_id → artifact_dir → the EXISTING slice-chain data (same path bundle.tar.gz uses), so #542/#543 work on real completed runs WITHOUT the full char-offset EvidenceContract. Defer the full EvidenceContract capability (char offsets + per-sentence JSON) to a post-demo Phase-2 issue.

C. Something else.

My engineering read: B. The demo needs followup + compare to WORK on real runs (the operator's PHASE-2 UI goal), not the full Phase-2 EvidenceContract JSON. The full capability is genuinely post-demo per the issue's own note + carries fabrication risk. B unblocks #542/#543 with the data that already exists; A builds 1000 LOC the demo doesn't need + risks LAW II.

Decide A/B/C. If B, confirm the deferred full-capability becomes a new post-demo issue. Highest long-term quality lens.
