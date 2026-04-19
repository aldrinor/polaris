---
verdict: NOT_READY
pass: 2
commit: ddcd1d4ad001130aa269a720d17c0dc883e624c2
closed_confirmed: [B-101, B-100, M-203, M-205, M-201, M-202_MVP, M-206, N-301, M-207, M-204, M-208_decision]
deferred_accepted: [B-102, R7b]
new_blockers: 2
new_mediums: 1
new_minors: 1
rationale: |
  Pipeline A's R1/R3-R10 fixes are mostly substantive and backed by regression tests that target the prior failure modes, but the product is not release-ready because B-102 remains open: the default UI/Docker serve path still dispatches to legacy v1/v2/v3 graphs, not the hardened pipeline-A contract. I also found a new concurrency blocker in the R8/R11 ambient run-id/cost implementation: module-level state is shared across concurrent run_one_query tasks, so one run can tag/cost another run's LLM calls. R7's MVP predicate expansion is real, and R7b is honestly deferred; R12 is a documented retire decision rather than a full code removal.
---

## 1. Closed-fix substantivity review

| Bug | Verdict | Evidence |
|---|---|---|
| B-101 manifest status | CLOSED substantive | `scripts/run_honest_sweep_r3.py:80-137` defines a unified manifest taxonomy and maps legacy summary statuses; all manifest write branches now include `status` (`:432-452`, `:485-505`, `:696-717`, `:778-796`, `:909-931`, `:1121-1184`, `:1208-1224`). `tests/polaris_graph/test_manifest_contract.py` AST-checks all manifest writes and would fail on the old missing-success-status path. |
| B-100 scope gate | CLOSED substantive for pipeline A | `src/polaris_graph/nodes/scope_gate.py:324-338` hard-rejects unsupported domains, and `:450-453` hard-rejects fully unscoped clinical PICO. `scripts/run_honest_sweep_r3.py:402-452` aborts before retrieval with `abort_scope_rejected`. Tests assert both node decisions and orchestrator ordering. |
| M-203 outline collapse | CLOSED substantive | `src/polaris_graph/generator/multi_section_generator.py:155-254` validates section count, overlap, and unknown evidence IDs; `:256-287` builds a deterministic fallback; `:793-911` propagates fallback telemetry. Tests cover invalid plans, retry/fallback telemetry, and status mapping to `partial_outline_fallback`. |
| M-205 evaluator gate | CLOSED substantive | `src/polaris_graph/evaluator/evaluator_gate.py:80-228` converts deterministic PT08/PT11/PT12 failures and critical Qwen axes into structured gate classes; `scripts/run_honest_sweep_r3.py:1083-1130` records that gate in the manifest and selects abort/partial statuses. Tests exercise invalid citation markers, missing contradiction disclosure, Qwen critical axes, parse-unavailable behavior, and orchestrator source wiring. |
| M-201 evidence selector | CLOSED substantive | `src/polaris_graph/retrieval/evidence_selector.py:96-273` replaces raw prefix slicing with tier-joined, relevance-ranked, quota-balanced selection and telemetry. Tests would fail against prefix slicing because high-tier late-arriving evidence must be selected and selected tier counts are asserted. |
| M-202 contradiction coverage MVP | CLOSED substantive, limited | `src/polaris_graph/retrieval/contradiction_detector.py:93-165` adds AF anticoagulation, tech, policy, and due-diligence predicate sets; `extract_numeric_claims(..., domain=...)` routes through them at `:484-502`. Probe result: predicate counts are `clinical=42`, `tech=15`, `policy=8`, `due_diligence=9`; AF examples extracted `systemic embolism=21.0` and `major bleeding=3.1`. R7b remains deferred. |
| M-206 / N-301 cost ledger | PARTIAL substantive, new blocker below | Per-run ledger filtering is substantive: `scripts/run_honest_sweep_r3.py:152-183` writes `<run_dir>/cost_ledger.jsonl` filtered by `session_id`, and `:1230-1238` runs it in teardown. N-301's ambient fallback is substantive for serial runs (`openrouter_client.py:68-81`, `:771`), but it introduces a concurrency bug listed in section 4. |
| M-207 invariant audit | CLOSED as coverage | Commit `3c772a5` adds `tests/polaris_graph/test_m207_invariant_coverage.py` with reachability/contract tests for B1-B5 and R1-R5 invariants. This is test-only by design, but it is not cosmetic: the tests inspect live helpers and orchestrator source, and several would fail if the audited branches disappeared. |
| M-204 limitations verifier | CLOSED substantive, imperfect | `src/polaris_graph/generator/provenance_generator.py:725-785` now rejects limitations sentences whose numbers do not appear in telemetry, and `strict_verify(..., telemetry_block=...)` calls it at `:829-831`. Tests cover fabricated `3%` vs telemetry `9%`. A metric-association false positive remains; see section 4. |
| M-208 pipeline C retire | CLOSED as decision/staged | `ddcd1d4` is documentation only, but it honestly records a retire decision in `src/orchestration/FROZEN_SINCE_2026-03-16.md:29-68`. The user-facing Docker `research` path already refuses pipeline C in `scripts/docker_entrypoint.sh:37-58` from earlier commit `6a0a041`. Full archive/removal is explicitly deferred. |

## 2. Deferral honesty review

### B-102 UI hardening

Deferral is honest and still release-blocking. `scripts/live_server.py:549-556` still routes `PG_GRAPH_VERSION=v3` to `graph_v3`, `PG_V2_ENABLED=1` to `graph_v2`, and default to `graph`; there is no `graph_v4` branch. Docker default `CMD ["serve"]` in `Dockerfile:48` enters `scripts/docker_entrypoint.sh:22-25`, which starts `scripts.live_server:app`, so the default product path still uses the un-hardened graph dispatch.

No silent back-porting found. `rg` found no `build_and_run_v4` or `src/polaris_graph/graph_v4.py`; `docs/todo_list.md:31-47` still lists R2a-R2h as open, including opt-in v4 dispatch, default flip, integration tests, and legacy deprecation/parameterization.

### R7b contradiction redesign

Deferral is honest. The MVP expansion is real, but the full Codex §4 redesign is not present: no YAML predicate/profile loader and no generic per-row multi-claim mining. Current behavior still normalizes one predicate per quote via `_normalize_predicate()` and only extracts values matching the existing verb/window rules.

AF reproducer coverage is improved for matching verb patterns. Probe:

```text
clinical predicates: 42
tech predicates: 15
policy predicates: 8
due_diligence predicates: 9
Apixaban reduced stroke or systemic embolism by 21% -> systemic embolism 21.0
Dabigatran achieved a major bleeding rate of 3.1% -> major bleeding 3.1
```

## 3. Regression scan

B1-B5 invariants still have direct tests in `tests/polaris_graph/` and no obvious regressions in the edited paths. The full suite could not complete in this sandbox because pytest temp directories under both `%LOCALAPPDATA%\Temp` and workspace `.tmp` hit Windows `PermissionError`, but 366 tests passed before temp-fixture setup failures. The failures were filesystem ACL errors, not assertion failures in the audited logic.

The 13-status taxonomy does not appear to introduce a silent success path: unknown summary labels map to `error_unexpected`, and manifest status prefix tests cover `success`, `partial_*`, `abort_*`, and `error_*`. Evaluator gate parse failure remains advisory by design (`advisory_unavailable`) and is recorded in `manifest.evaluator_gate`; I did not classify that as a new defect.

Evidence selector quota math does not under-fill tiny pools: when `len(evidence_rows) <= max_rows`, it returns all rows at `evidence_selector.py:174-182`, and the under-allocation loop at `:230-238` fills remaining capacity when possible.

## 4. New defects

### B-201: concurrent runs stomp ambient run id and cost state

Severity: blocker

Files:
- `src/polaris_graph/llm/openrouter_client.py:60-104`
- `src/polaris_graph/llm/openrouter_client.py:68-81`
- `src/polaris_graph/llm/openrouter_client.py:771`
- `scripts/run_honest_sweep_r3.py:350-362`
- `scripts/run_honest_sweep_r3.py:1230-1238`

`run_one_query()` is async, but `reset_run_cost()`, `_RUN_COST_USD`, and `_CURRENT_RUN_ID` are module-level globals. If two runs execute via `asyncio.gather`, the later run overwrites the earlier run's ambient id before downstream `OpenRouterClient()` construction. The same process-global cost accumulator can also reset or aggregate the wrong run's spend.

Reproducer:

```python
import asyncio
from src.polaris_graph.llm.openrouter_client import set_current_run_id, current_run_id, OpenRouterClient

async def run_a():
    set_current_run_id("run_A")
    await asyncio.sleep(0.05)
    return ("A", current_run_id(), OpenRouterClient(api_key="dummy", model="m").usage.session_id)

async def run_b():
    await asyncio.sleep(0.01)
    set_current_run_id("run_B")
    await asyncio.sleep(0.08)
    return ("B", current_run_id(), OpenRouterClient(api_key="dummy", model="m").usage.session_id)

async def main():
    return await asyncio.gather(run_a(), run_b())

print(asyncio.run(main()))
```

Observed equivalent output:

```text
[('A', 'run_B', 'run_B'), ('B', 'run_B', 'run_B')]
```

Expected: run A's client should be tagged `run_A`. Use `contextvars.ContextVar` for ambient run id and a per-run cost map/context rather than process-global scalars, or thread explicit `session_id`/cost accounting through the async call graph.

### B-102: UI/Docker default still un-hardened

Severity: blocker

This is the expected carried blocker, not a newly introduced bug. See section 2. It prevents a `READY` verdict under the anti-circle-jerk rules.

### M-209: limitations verifier matches unrelated telemetry numbers

Severity: medium

File: `src/polaris_graph/generator/provenance_generator.py:725-774`

The verifier checks only whether each numeric literal appears anywhere in the telemetry block with digit boundaries. It does not bind the number to a telemetry metric key. A fabricated limitation can pass if the same number appears in unrelated telemetry.

Reproducer:

```python
from src.polaris_graph.generator.provenance_generator import verify_limitations_sentence_against_telemetry

v = verify_limitations_sentence_against_telemetry(
    "Limitations: T-cell count of 500 was underrepresented.",
    "http_status: 500\ntier_distribution:\n  T1: 9%\n",
)
print(v.is_verified, v.failure_reasons)
```

Observed:

```text
True []
```

Expected: reject, or require numeric claims to match an allowed telemetry metric/label context rather than any occurrence of `500`.

### N-302: evidence selector can over-fill when max_rows is below high-value tier floors

Severity: minor

File: `src/polaris_graph/retrieval/evidence_selector.py:198-227`

Not the under-fill failure requested, but a related edge case: high-value floors preserve one T1/T2/T3 slot each even when `max_rows < 3`, and the over-allocation loop refuses to deduct below those floors. With four rows and `max_rows=2`, selected rows count is 3.

Reproducer:

```python
from src.polaris_graph.retrieval.evidence_selector import select_evidence_for_generation

rows = [
    {"evidence_id": t, "source_url": t, "statement": "x y z", "tier": t}
    for t in ["T1", "T2", "T3", "T7"]
]
res = select_evidence_for_generation(
    research_question="x", protocol=None, classified_sources=[],
    evidence_rows=rows, max_rows=2,
)
print(len(res.selected_rows), [r["tier"] for r in res.selected_rows])
```

Observed:

```text
3 ['T1', 'T2', 'T3']
```

Production currently appears to use larger caps, so this is minor unless callers expose very small `max_rows`.

## 5. Final verdict and release guidance

Verdict: NOT_READY.

Release guidance:

1. Do not ship the default UI/Docker `serve` path as production-hardened until R2a-R2h lands and the default dispatch is `graph_v4` or equivalent.
2. Fix ambient run id and run cost accounting before allowing concurrent `run_one_query()` execution in-process.
3. Tighten limitations telemetry verification so numbers are associated with the intended telemetry metric, not merely present anywhere in the block.
4. Optionally clamp evidence selector output to `max_rows` after high-value floors, or reject `max_rows < len(present_hv_floors)` explicitly.

Pipeline A can still be used for limited serial sweeps with the known caveat that the UI path is not hardened and R7b's generic contradiction mining is not implemented.
