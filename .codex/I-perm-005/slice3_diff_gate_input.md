# Codex DIFF review — I-perm-005 (#1199) SLICE 3: runner flip (annotate under PG_ALWAYS_RELEASE)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Reserve P0/P1 for real execution risks. If iter 5 REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this slice does
In `run_honest_sweep_r3.py`'s post-4-role report-vs-verdict block, adds an `elif always_release_enabled():` branch BEFORE the legacy reconcile `else:`. Under PG_ALWAYS_RELEASE it calls `annotate_report_against_verdicts` (KEEP each non-VERIFIED claim + append its confidence marker) instead of `reconcile_report_against_verdicts` (DELETE). Writes the labeled report.md + `claim_confidence.json` + `manifest.report_annotation`. Flag OFF -> the reconcile path is byte-identical.

## Safety properties to verify (P0 class)
1. **OFF byte-identical.** The legacy reconcile `else:` block is UNCHANGED; the new branch only runs when `always_release_enabled()`. Confirm the reconcile path (and the absent/no-op/no-audit-map guards before it) is untouched.
2. **No non-VERIFIED claim ships unlabeled.** The annotate path uses the same fail-closed `ReportRedactionError -> report_redaction_failed` abort as reconcile. A present-but-unpinnable claim aborts, not ships. Confirm the except sets release_allowed=False + report_redaction_failed.
3. **Marker never `high`.** `marker_by_claim` is built with `confidence_bucket(is_verified=False, ...)` for every non-VERIFIED claim -> low / no-source-found only. Confirm is_verified=False is hardcoded (a non-VERIFIED claim can never be labeled high).
4. **Control-flow / scope.** `always_release_enabled` is imported unconditionally earlier in the same function (line ~7142, before this block); confirm it is in scope at the `elif`. The `elif` sits in the `if not non-VERIFIED / report absent / audit_map absent / elif always_release / else reconcile` chain — confirm both annotate + reconcile still require the audit_map and the no-op guards are preserved.

## Claims ledger
| # | Claim | Where | Status |
|---|---|---|---|
| C1 | OFF byte-identical (reconcile path unchanged) | new branch guarded by always_release_enabled(); else: reconcile verbatim | claims-true |
| C2 | non-VERIFIED never ships unlabeled | annotate raises ReportRedactionError -> report_redaction_failed abort | claims-true |
| C3 | marker never high | confidence_bucket(is_verified=False, ...) | claims-true |
| C4 | always_release_enabled in scope | imported ~7142 unconditionally before the block | claims-true |
| C5 | claim_confidence.json + manifest.report_annotation emitted | the else branch writes both | claims-true |

## Smoke evidence (offline, replicating the branch logic)
UNSUPPORTED claim KEPT + `[confidence: low ...]`; VERIFIED neighbor + its [N] byte-identical (one marker total); no-cited-evidence non-VERIFIED -> `no grounded source` marker. Runner py_compiles.

## Files (full diff: `.codex/I-perm-005/slice3_codex_diff.patch`)
- `scripts/run_honest_sweep_r3.py` (+~95): the annotate elif branch + marker assembly + claim_confidence.json.

Review the diff. Confirm C1 (OFF byte-identical) + C2 (fail-closed, never unlabeled) + C3 (never high). Hunt any path where the annotate branch ships a non-VERIFIED claim unlabeled or alters the reconcile path.
