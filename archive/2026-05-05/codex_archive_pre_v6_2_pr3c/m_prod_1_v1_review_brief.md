# Codex round 1 — M-PROD-1 v1 (SOC2 dry-run audit + remediation)

## Pre-flight
- Branch: `polaris`
- Commit: `373b1ac`
- Brief format: lean autoloop V3

## Scope
Phase H first milestone per FINAL_PLAN. Automated SOC2 evidence
gap detection: walks the SOC2 evidence map, validates each
referenced artifact, surfaces gaps.

## Tool hints
- Read: `scripts/run_m_prod_1_soc2_dry_run.py` (full file, ~190 lines)
- Read: `docs/compliance/soc2_evidence_map.md` (~186 lines)
- Run: `python scripts/run_m_prod_1_soc2_dry_run.py`
  → expect 21/21 intact, exit_code=0
- Smoke output: `outputs/m_prod_1_soc2/manifest.json`

## Acceptance bar
1. **Audit script exists + runs cleanly.** Exits rc=0 when no
   gaps; rc=1 when gaps found.
2. **Path extraction correctness.** Regex captures all
   backtick-quoted file/dir references in the SOC2 doc (paths,
   not just identifiers in prose).
3. **Glob support.** References containing `{var}` placeholders
   resolve via glob matching.
4. **Dedup correctness.** Inline filename references (e.g.
   `pg_batch_progress.sqlite`) deduped against qualified path
   references (e.g. `state/pg_batch_progress.sqlite`) when the
   former is a basename of the latter.
5. **Evidence remediation correctness.** The 4 originally-
   surfaced gaps (preflight, live_server, last_pointer,
   progress_ledger) are correctly remediated in the SOC2 doc
   to reflect current paths.
6. **Manifest output.** `outputs/m_prod_1_soc2/manifest.json`
   contains intact list, gaps list, counts, intact_fraction.

## Severity rubric
- **P0** — production-breaker: audit falsely passes with real
  gaps; audit falsely fails with no gaps; remediation
  references nonexistent paths
- **P1** — phase-rework: acceptance criterion not met
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly — do not manufacture findings.
- Run the audit yourself, verify 21/21 intact + manifest written.
- Spot-check the 4 remediated SOC2 references actually point
  to current artifacts (resolve them on disk).
- Try synthetic gap injection: temporarily rename a referenced
  file, confirm audit catches it, restore.

## Skepticism gate
List which files you read + line ranges + whether you actually
ran the audit + whether you tested gap detection.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- Speculative concerns about code that does not exist
- Path-extraction regex edge cases that don't manifest in
  practice
- Suggestions for "additional audit features" beyond v1 scope

## Verdict format
```
## Files scanned
## Acceptance bar verification
## Findings
### P0 (blocking)
### P1 (blocking)
### deferred_polish (P2/P3, non-blocking)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 1 of 5 hard cap.
