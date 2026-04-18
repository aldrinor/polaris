---
target_bug: B-101
scope: orchestration — manifest.status contract
verdict: scoped
exit_paths_identified: 6
unified_taxonomy: [success, partial_thin_corpus, partial_incomplete_corpus, partial_rule_check_warnings, abort_scope_rejected, abort_no_sources, abort_corpus_inadequate, abort_corpus_approval_denied, abort_no_verified_sections, error_unexpected]
tests_required: 6
rationale: |
  `run_one_query` currently has four `manifest.json` write sites, but only the three abort manifests include `status`; the success manifest is written before the later summary-only status calculation. Two additional exits, zero retrieved sources and the broad exception handler, return without any manifest at all. The fix should make `manifest.status` the single authoritative run verdict while preserving `summary["status"]` as backward-compatible sweep telemetry.
---

## 1. Exit path inventory

| Exit path | Line range | Manifest write | Current status behavior | Unified `manifest.status` |
|---|---:|---|---|---|
| Zero retrieved sources | `scripts/run_honest_sweep_r3.py:318-322` | None | Sets only `summary["status"] = "fail_no_sources"` and returns. Downstream readers looking for `manifest.status` get no artifact. | `abort_no_sources` |
| Corpus adequacy abort | `scripts/run_honest_sweep_r3.py:479-531`; write at `:524-527` | Yes | Sets `summary["status"] = "abort_corpus_inadequate"` and writes manifest `"status": "abort_corpus_inadequate"`. | `abort_corpus_inadequate` |
| Corpus approval denied | `scripts/run_honest_sweep_r3.py:557-607`; write at `:600-603` | Yes | Sets `summary["status"] = "abort_corpus_approval_denied"` and writes manifest `"status": "abort_corpus_approval_denied"`. | `abort_corpus_approval_denied` |
| No verified sections | `scripts/run_honest_sweep_r3.py:676-714`; write at `:707-710` | Yes | Sets `summary["status"] = "abort_no_verified_sections"` and writes manifest `"status": "abort_no_verified_sections"`. | `abort_no_verified_sections` |
| Successful report generation | `scripts/run_honest_sweep_r3.py:851-932`; write at `:908-911` | Yes | Manifest omits `status`. Only after the write, `summary["status"]` becomes one of `fail_no_sources`, `fail_no_verified_prose`, `warn_rule_checks`, `ok_thin_corpus`, `ok_incomplete_corpus`, or `ok`. Because earlier guards now return before success, `fail_no_sources` and `fail_no_verified_prose` should be unreachable here. | `success`, `partial_rule_check_warnings`, `partial_thin_corpus`, or `partial_incomplete_corpus` |
| Unexpected exception | `scripts/run_honest_sweep_r3.py:933-941` | None | Sets only `summary["status"] = "error"` and `summary["error"]`; no manifest is written. | `error_unexpected` |

`abort_scope_rejected` is documented in `README.md`, `docs/runbook.md`, and `docs/pipeline_audit_context/03_json_contracts.md`, but no `run_one_query` branch currently emits it. If BUG-B-099 later makes the scope gate enforcing, that new exit must write `manifest.status = "abort_scope_rejected"`.

## 2. Taxonomy reconciliation

| manifest taxonomy | summary taxonomy | resolution |
|---|---|---|
| `success` | `ok` | Emit `manifest.status = "success"`. Keep `summary["status"] = "ok"` for sweep counters. |
| `abort_corpus_approval_denied` | `abort_corpus_approval_denied` | Already aligned. Keep as an authoritative abort status. |
| `abort_no_verified_sections` | `abort_no_verified_sections` | Already aligned. Keep as an authoritative abort status. |
| `abort_corpus_inadequate` | `abort_corpus_inadequate`; formerly confused with later `ok_thin_corpus` degraded success | Keep hard adequacy refusal as `abort_corpus_inadequate`. Map degraded-but-generated adequacy `expand` runs to `partial_thin_corpus`, not abort. |
| `abort_scope_rejected` | None today | Reserve as the scope-gate abort status. It remains unreachable until the scope gate gets an enforcing branch. |
| Not specified today | `fail_no_sources` | Add `abort_no_sources`. This is a deterministic pipeline refusal before corpus adequacy can run, not an unexpected exception. |
| Not specified today | `ok_thin_corpus` | Add `partial_thin_corpus`. A report exists, but the corpus did not meet full accept quality. |
| Not specified today | `ok_incomplete_corpus` | Add `partial_incomplete_corpus`. A report exists, but completeness coverage is below the configured threshold. |
| Not specified today | `warn_rule_checks` | Add `partial_rule_check_warnings`. A report exists, but deterministic evaluator checks found material warning signals. |
| `error_*` | `error` | Emit concrete `error_unexpected` for the current broad exception handler. Future typed failures can add more `error_*` values only when callers need that distinction. |

Unified taxonomy: exactly 10 values for this orchestrator contract:

| Value | Class | Justification |
|---|---|---|
| `success` | success | Full report path with no degraded-quality status selected by the existing summary logic. |
| `partial_thin_corpus` | partial | Existing `ok_thin_corpus` means the run produced a report, but corpus adequacy remained in `expand`, not clean `accept`. |
| `partial_incomplete_corpus` | partial | Existing `ok_incomplete_corpus` means the run produced a report, but checklist coverage is materially incomplete. |
| `partial_rule_check_warnings` | partial | Existing `warn_rule_checks` means the run produced a report with enough deterministic evaluator failures to require caution. |
| `abort_scope_rejected` | abort | Documented scope-gate refusal; keep reserved for the enforcing gate branch. |
| `abort_no_sources` | abort | Retrieval returned zero classified sources, so the pipeline refused to continue before a report could exist. |
| `abort_corpus_inadequate` | abort | Adequacy gate refused synthesis after retrieval/optional expansion. |
| `abort_corpus_approval_denied` | abort | Approval gate refused synthesis over a materially deviating corpus. |
| `abort_no_verified_sections` | abort | Generation ran, but strict verification left zero usable sections. |
| `error_unexpected` | error | Catch-all for unhandled exceptions in `run_one_query`. |

## 3. Fix specification

Make `manifest.status` authoritative and write it before every return from `run_one_query`. Preserve `summary["status"]` as a secondary compatibility/reporting field; do not rename it and do not require old artifact migration.

Per exit path:

| Exit path | Required manifest behavior | Summary behavior |
|---|---|---|
| Zero retrieved sources | Write a minimal manifest with run identity, `status: "abort_no_sources"`, `error: "zero sources retrieved"`, retrieval counters if available, and `cost_usd`. | Keep `summary["status"] = "fail_no_sources"` or optionally also set it to `abort_no_sources` only if sweep counter compatibility is deliberately updated. |
| Corpus adequacy abort | Keep writing `status: "abort_corpus_inadequate"`. Ensure any helper used by all manifests validates the key is present. | Keep current `summary["status"]`. |
| Corpus approval denied | Keep writing `status: "abort_corpus_approval_denied"`. | Keep current `summary["status"]`. |
| No verified sections | Keep writing `status: "abort_no_verified_sections"`. | Keep current `summary["status"]`. |
| Successful report generation | Compute the manifest verdict before constructing/writing the manifest. Map current summary labels as: `ok -> success`, `ok_thin_corpus -> partial_thin_corpus`, `ok_incomplete_corpus -> partial_incomplete_corpus`, `warn_rule_checks -> partial_rule_check_warnings`. Then write the manifest with that `status`. | Keep existing summary labels as-is so current sweep summaries and counters do not break. |
| Unexpected exception | Best-effort write a minimal manifest with run identity, `status: "error_unexpected"`, truncated `error`, `cost_usd`, and the run directory/log context. Avoid masking the original exception if this best-effort manifest write fails. | Keep `summary["status"] = "error"` and `summary["error"]`. |
| Future scope rejection | If scope gate enforcement is added, write `status: "abort_scope_rejected"` plus scope/protocol details and return before retrieval. | Use either `summary["status"] = "abort_scope_rejected"` or a compatibility alias, but manifest remains authoritative. |

Downstream invariants after the fix:

- Every completed `run_one_query` attempt has a `manifest.json` unless the process is killed outside Python before the exception handler can run.
- Every new manifest has a non-empty string `status`.
- Consumers classify the run using `manifest.status` alone: `success`, `partial_*`, `abort_*`, or `error_*`.
- `report.md` shape is inferred from status class: `success` and `partial_*` are research reports; `abort_*` is a pipeline-verdict artifact; `error_*` may have incomplete artifacts.
- `summary["status"]` is secondary sweep telemetry and may retain legacy values such as `ok_thin_corpus`.
- Readers remain backward-compatible by tolerating older manifests that already contain abort statuses and by treating missing `status` in historical artifacts as legacy unknown, not as a reader crash.

## 4. Test specification

| Test | Exercises | Expected assertion |
|---|---|---|
| `test_manifest_contract_success_has_status` | A normal generated-report path where current summary logic would produce `ok`. | `manifest.json` exists; `manifest["status"] == "success"`; `summary["status"] == "ok"`; manifest status is present before the function returns. |
| `test_manifest_contract_partial_status_mapping` | Generated-report paths for `ok_thin_corpus`, `ok_incomplete_corpus`, and `warn_rule_checks` using controlled adequacy/completeness/evaluator fakes. | Parametrized assertions: `ok_thin_corpus -> partial_thin_corpus`, `ok_incomplete_corpus -> partial_incomplete_corpus`, `warn_rule_checks -> partial_rule_check_warnings`; summary keeps the legacy value. |
| `test_manifest_contract_abort_statuses_are_authoritative` | Existing hard-abort paths: corpus inadequate, corpus approval denied, and no verified sections. | For each path, `manifest["status"]` equals the expected `abort_*`, `summary["manifest"]["status"]` matches the file, and `report.md` is a pipeline-verdict artifact. |
| `test_manifest_contract_zero_sources_writes_abort_manifest` | Retrieval returns zero classified sources. | Function returns without synthesis; `manifest.json` exists with `status == "abort_no_sources"` and an explanatory `error`; summary may remain `fail_no_sources`. |
| `test_manifest_contract_exception_writes_error_manifest` | Force an exception after `run_dir`/`run_id` are initialized, for example by making scope/retrieval raise. | `manifest.json` exists with `status == "error_unexpected"` and truncated `error`; returned summary has `status == "error"`. |
| `test_manifest_contract_all_manifest_writes_require_status` | Contract guard for future drift, implemented either as a source/AST check around every `(run_dir / "manifest.json").write_text` site or by monkeypatching manifest writes in parametrized path tests. | Every manifest JSON payload written by `run_one_query` contains `status` in the unified taxonomy; adding a new write site without `status` fails the test. |
