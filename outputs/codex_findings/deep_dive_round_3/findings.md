---
target_bug: B-100
scope: intake scope gate — unreachable abort_scope_rejected
verdict: scoped
direction_chosen: A
invariants_affected:
  - manifest.status remains in the unified taxonomy
  - hard scope rejection must abort before retrieval
  - needs_user_review remains advisory and does not imply rejection
  - protocol.json remains the T+0 audit artifact for the intake decision
tests_required: 5
rationale: |
  The current scope gate records protocol uncertainty but has no semantic branch for rejecting a query, while the orchestrator logs that uncertainty and proceeds into retrieval. The unified taxonomy, README, architecture docs, and runbook already reserve `abort_scope_rejected`, so the intended product contract is a real intake gate rather than advisory-only scope review. Direction A preserves that contract and makes the reject/proceed boundary explicit instead of deleting a useful safety and cost-control outcome.
---

# B-100 Deep Dive: Intake Scope Gate

## 1. Scope Gate Decision Inputs

Actual source reviewed: `src/polaris_graph/nodes/scope_gate.py`.

`run_scope_gate()` accepts these decision inputs:

- `research_question`: required, stored verbatim after stripping.
- `domain`: intended to select one of `clinical`, `policy`, `tech`, or `due_diligence`.
- `user_overrides`: optional overrides for PICO fields, inclusion/exclusion criteria, date range, geography, languages, and excluded sponsors.
- Domain YAML template: loaded from `config/scope_templates/{domain}.yaml`.
- Deterministic clinical PICO heuristics: population/intervention/outcome extraction from regexes.

What currently triggers `needs_user_review=True`:

- Clinical domain only: missing extracted `population`.
- Clinical domain only: missing extracted `intervention`.
- User overrides can clear these conditions by supplying `population` or `intervention`.

Other signals produced today:

- `protocol.json`, via `ProtocolDocument`, containing the research question, domain, PICO fields, criteria, expected tier distribution, date range, geography, languages, excluded sponsors, template used, overrides, `needs_user_review`, and `notes`.
- `protocol_sha256`, computed over the serialized protocol.
- `notes`, which explain missing clinical population/intervention and missing `expected_tier_distribution`.
- Exceptions for invalid local inputs, such as an empty question.

Important behavior:

- Unsupported `domain` is not rejected. It logs a warning and falls back to `clinical`.
- Missing `expected_tier_distribution` adds a note but does not set `needs_user_review=True`.
- There is no `rejected`, `scope_decision`, `rejection_reason`, `out_of_domain`, `harmful`, or `unanswerable` signal.

Semantic split needed:

- **Hard reject**: the pipeline should refuse to spend retrieval/generation budget because the request is outside supported intake scope, cannot produce a meaningful protocol, is unsafe to answer as a research report, or lacks minimum required scope fields that cannot be inferred or overridden.
- **Flag-only review**: the pipeline can still produce an evidence corpus, but a human should verify protocol assumptions before relying on the output. Current examples are weak clinical PICO extraction where enough question/domain context remains to retrieve relevant evidence.

Today, that distinction does not exist. Everything recoverable collapses into `needs_user_review`, and some invalid conditions either raise exceptions or get silently coerced.

## 2. Orchestrator Scope Handling

Actual source reviewed: `scripts/run_honest_sweep_r3.py`.

The orchestrator calls `run_scope_gate()`, converts the returned protocol to a dict, and logs:

```text
[scope] sha256=... needs_review=<bool>
```

It does not read any scope field besides `scope.protocol.needs_user_review`, and that read is log-only. Immediately after the log, it calls `run_live_retrieval(...)`.

I found no code path that emits `abort_scope_rejected`. The value exists only as a reserved taxonomy member in `UNIFIED_STATUS_VALUES` with the comment "reserved for future enforcing scope gate (BUG-B-100)", plus docs/tests references. `_SUMMARY_TO_UNIFIED` also has no legacy status mapping to `abort_scope_rejected`.

The real run evidence matches the code path: `outputs/honest_sweep_r6_validation/clinical/clinical_afib_anticoagulation/run_log.txt` shows `needs_review=True`, followed by retrieval, corpus checks, generation, and final `ok_thin_corpus`.

After the R1 manifest fix, `abort_scope_rejected` is reserved in the unified manifest taxonomy but remains unreachable.

## 3. Direction Chosen

Choose **Direction A — Make the scope gate a real gate**.

Reasoning:

- The architecture and README already describe `scope_gate -> if off-topic -> abort_scope_rejected`.
- The unified taxonomy intentionally reserves `abort_scope_rejected` for B-100 rather than treating it as historical drift.
- A real intake rejection protects correctness and cost: off-domain or impossible questions should not proceed into live retrieval and synthesis.
- Direction B would make the current behavior honest, but it would remove a useful invariant the rest of the pipeline already expects: abort statuses mean the pipeline can refuse to produce misleading reports.

## 4. Implementation Specification

Add explicit decision fields to the protocol/result contract rather than overloading `needs_user_review`.

Recommended fields on `ProtocolDocument`:

- `scope_decision: str`: one of `"proceed"`, `"review"`, `"reject"`.
- `scope_rejected: bool`: convenience boolean for orchestrator gating.
- `scope_rejection_code: Optional[str]`: stable machine-readable reason, only set when rejected.
- `scope_reasons: list[str]`: human-readable reasons for review or rejection.

Keep `needs_user_review` for backward compatibility, but define it as:

- `True` when `scope_decision == "review"`.
- `False` when `scope_decision == "proceed"` or `"reject"` unless the implementation deliberately wants rejection artifacts to also say they need review. Prefer false for rejects to keep the states mutually intelligible.

Rejection logic belongs in `run_scope_gate()` after template load / heuristic extraction / overrides and before assembling `ProtocolDocument`, alongside the existing sanity-check block. The decision block should compute one of three outcomes:

- `reject`: hard stop.
- `review`: proceed, but surface advisory uncertainty.
- `proceed`: no intake concern.

Hard rejection criteria:

- Empty or whitespace-only `research_question`: convert the current `ValueError` behavior into a structured `scope_decision="reject"` where feasible for orchestrator-owned runs, with `scope_rejection_code="empty_question"`.
- Unsupported `domain`: reject with `scope_rejection_code="unsupported_domain"` instead of silently falling back to `clinical`.
- Clinical domain missing both minimum PICO anchors after overrides: reject if neither `population` nor `intervention` can be extracted/provided, because retrieval would be poorly scoped.
- Explicit harmful/off-topic patterns if this project has an existing policy list. If no existing list exists, start conservatively with unsupported domain and minimum-structure failures rather than inventing a broad safety classifier.

Flag-only criteria:

- Clinical question missing exactly one of `population` or `intervention`: set `scope_decision="review"` and preserve the existing note.
- Missing optional clinical `outcome` or `comparator`: flag only, not reject.
- Missing `expected_tier_distribution`: flag only if desired, because corpus adequacy can still run with no reference distribution; do not make this a hard reject unless the downstream gates require tier expectations.

Orchestrator integration in `run_one_query()`:

- Immediately after `run_scope_gate()` and before `run_live_retrieval()`, check `scope.protocol.scope_rejected` or `scope.protocol.scope_decision == "reject"`.
- Log `[ABORT] Scope rejected: <code/reasons>`.
- Write a pipeline-verdict `report.md` explaining the scope rejection and suggested refinement.
- Write `manifest.json` with:
  - `status: "abort_scope_rejected"`
  - run identity fields
  - `protocol_sha256`
  - `scope` object containing decision, rejection code, and reasons
  - `cost_usd` and `budget_cap_usd`
- Set `summary["status"] = "abort_scope_rejected"`, attach the manifest, close the log, and return before retrieval.
- Add `_SUMMARY_TO_UNIFIED["abort_scope_rejected"] = "abort_scope_rejected"` if `summary["status"]` can flow through `to_unified_status()`.

Docs to update:

- Keep `abort_scope_rejected` in `UNIFIED_STATUS_VALUES`.
- Change docs that currently imply the status exists today to say it is emitted when `scope_decision="reject"`.
- Update `docs/pipeline_audit_context/03_json_contracts.md` to remove the "reserved" wording once implemented.

## 5. Test Specification

Required tests: 5.

1. Scope gate rejects unsupported domain:
   - Call `run_scope_gate(..., domain="finance")`.
   - Assert `scope_decision == "reject"`, `scope_rejected is True`, and `scope_rejection_code == "unsupported_domain"`.

2. Scope gate rejects structurally unscoped clinical question:
   - Use a clinical question with neither recognizable population nor intervention and no overrides.
   - Assert rejection rather than `needs_user_review=True`.

3. Scope gate flags but proceeds for partially scoped clinical question:
   - Use a clinical question with exactly one of population/intervention missing.
   - Assert `scope_decision == "review"`, `scope_rejected is False`, and `needs_user_review is True`.

4. Scope gate proceeds for adequately scoped clinical question:
   - Use a clinical query with recognizable population and intervention or explicit overrides.
   - Assert `scope_decision == "proceed"`, `scope_rejected is False`, and `needs_user_review is False`.

5. Orchestrator integration aborts before retrieval:
   - Mock or monkeypatch `run_scope_gate()` to return a rejected protocol.
   - Mock `run_live_retrieval()` and assert it is not called.
   - Assert `manifest.json.status == "abort_scope_rejected"` and `report.md` is a verdict artifact, not a synthesized research report.

Residual contract test:

- Keep `test_manifest_contract_unified_taxonomy_defined` expecting `abort_scope_rejected` in `UNIFIED_STATUS_VALUES`.
- Add or extend a manifest-write contract test so the new scope-abort branch is included in the "every exit path writes manifest.status" invariant.
