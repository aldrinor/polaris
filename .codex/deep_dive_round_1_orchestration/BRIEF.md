# Deep-dive round 1 — Orchestration (BUG-B-101 manifest contract)

You are the independent reviewer for a focused deep-dive on the
orchestration contract defect surfaced in the full-audit scoping pass.

**Target**: `BUG-B-101 — Success manifest lacks "status" key`
(full finding in `outputs/codex_findings/full_audit_pass_1/findings.md` §7).

## The defect, restated

Successful pipeline-A runs emit `manifest.json` without any `"status"`
key. Abort runs do include it. The orchestrator also maintains a
separate, incompatible taxonomy in `summary["status"]` (values like
`ok`, `ok_thin_corpus`, `warn_rule_checks`) that doesn't match the
documented `success | abort_* | error_*` taxonomy.

The documentation (`README.md`, `architecture.md`, `docs/runbook.md`,
`docs/pipeline_audit_context/03_json_contracts.md`) all say
`manifest.status` is authoritative. The code proves them wrong.

Downstream consumers cannot trust `manifest.status` as documented.

## Your mandate (pass 1: scope mapping)

Produce the fix specification, NOT the fix itself. Specifically:

### 1. Enumerate every exit path

Open `scripts/run_honest_sweep_r3.py::run_one_query`. Identify
**every place** a `manifest.json` is written — success, abort, error.
For each, list:
- Line range
- Current status behavior (written into manifest? only into summary?
  omitted entirely?)
- What status value should be written under the unified taxonomy

### 2. Map the two taxonomies

| manifest taxonomy | summary taxonomy | resolution |
|---|---|---|
| `success` (not emitted) | `ok` | ??? |
| `abort_corpus_approval_denied` | ??? | ??? |
| `abort_no_verified_sections` | ??? | ??? |
| `abort_corpus_inadequate` | `ok_thin_corpus`? | ??? |
| (not specified) | `warn_rule_checks` | ??? |
| `error_*` | ??? | ??? |

Fill the table. Propose a unified taxonomy with exactly N values,
enumerated. Justify each value.

### 3. Specify the fix

For each exit path, specify:
- Which unified status value it should emit
- Whether the summary taxonomy should be kept as a SECONDARY field
  or collapsed into the unified one
- What invariants a downstream consumer can rely on

### 4. Specify the regression tests

Identify the concrete tests that, if present today, would have caught
this contract drift. Specify each test's:
- Name (`test_manifest_contract_success_has_status`, etc.)
- What it exercises
- Expected assertion

Plan for at least 4-6 tests covering the full exit-path matrix.

## Output format

Write to `outputs/codex_findings/deep_dive_round_1/findings.md` with
this frontmatter:

```yaml
---
target_bug: B-101
scope: orchestration — manifest.status contract
verdict: scoped | needs_more_info
exit_paths_identified: <int>
unified_taxonomy: [list of status values]
tests_required: <int>
rationale: |
  <2-4 sentences>
---
```

Followed by sections:

- `## 1. Exit path inventory` — the table from step 1
- `## 2. Taxonomy reconciliation` — the table from step 2
- `## 3. Fix specification` — what the code should do at each exit
- `## 4. Test specification` — what tests should exist

## Context bundle

Everything you need is in:

- `docs/pipeline_audit_context/` (0-8 files)
- `outputs/codex_findings/full_audit_pass_1/` (prior findings)
- Source code at HEAD (commit `6a0a041` or later)

Specifically:

- `scripts/run_honest_sweep_r3.py` (lines 500-950) — run_one_query
- `scripts/run_honest_sweep_r3.py` (line 78) — `expected_str_for_abort`
- `scripts/run_honest_sweep_r3.py` (line 90) — `filter_verified_sections`
- `scripts/run_honest_sweep_r3.py` (line 110) — `build_no_verified_sections_abort_body`
- Real artifacts:
  - `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/manifest.json`
    (success, no status key)
  - `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/manifest.json`
    (abort, status key present)

## Constraints on the fix specification

- Must be BACKWARD-COMPATIBLE with existing outputs that DO have a
  status. Readers should never break.
- Must be MINIMALLY INTRUSIVE. Don't propose rewriting the orchestrator.
- Must enable downstream consumers to distinguish success from abort
  from error from partial via `manifest.status` alone.
- Must enable the contract test to catch any future exit path that
  forgets to emit the status.

## What NOT to do

- Do NOT write code. This pass produces the SPEC.
- Do NOT rename `summary["status"]` to something else — leave that
  as-is unless it's part of the reconciliation.
- Do NOT propose a schema migration for existing artifact trees.

## Authentication

OAuth. No API-key burn.

## Expected duration

5-10 minutes. This is a focused mapping exercise, not a full audit.

---

Start:

```
grep -n "manifest.json\|manifest\[\|summary\[\"status\"\]" scripts/run_honest_sweep_r3.py
```

Then trace every `(run_dir / "manifest.json").write_text` and every
`summary["status"] =` assignment. Map them in the table.
