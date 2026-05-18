# Codex ARCHITECTURE consult — I-rdy-008 / GH #504 slice 8: how does charts migrate off golden fixtures when it is EvidenceContract-coupled?

This is an **architecture-decision consult**, not a brief/diff review. One
question: **slice 8 implements charts-for-live-runs HOW?** Rule on the two
options in §5. Do NOT produce a line-by-line implementation plan.

## 0. Why you are being asked

A prior Codex SCOPE consult (`.codex/I-rdy-008/slice8_scope_consult_verdict.txt`,
Option A) settled that #504's only residual surface is **charts**: slice 8 =
"migrate `GET /runs/{id}/charts/{type}` off `_GOLDEN_RUN_INDEX` onto
`run_store`/`artifact_dir`," then #504 closes. That verdict was made WITHOUT
seeing `charts.py`'s internals. Grounding `charts.py` for the slice-8
implementation surfaced a coupling the scope consult could not have known —
it changes how (or whether) slice 8 is implementable. Per the project rule,
architecture decisions go to Codex, not the operator; hence this consult.

## 1. The coupling (grounded at polaris HEAD 869ee795)

`src/polaris_v6/api/charts.py` (full, 32 lines):
```python
from polaris_v6.api.bundle import _GOLDEN_RUN_INDEX, _FIXTURE_DIR
from polaris_v6.charts.from_bundle import chart_from_bundle
from polaris_v6.schemas.evidence_contract import EvidenceContract

@router.get("/{run_id}/charts/{chart_type}")
def get_chart(run_id, chart_type):
    fixture_name = _GOLDEN_RUN_INDEX.get(run_id)        # golden-only
    if fixture_name is None: raise HTTPException(404, ...)
    raw = json.loads((_FIXTURE_DIR / fixture_name).read_text())
    bundle = EvidenceContract.model_validate(raw)        # <-- needs an EvidenceContract
    spec = chart_from_bundle(bundle=bundle, chart_type=chart_type)
    return spec
```

So `charts.py` produces a Vega-Lite spec from an **`EvidenceContract`**, via
`chart_from_bundle`. The golden path reads the `EvidenceContract` straight
out of a fixture file. To serve a live run, `charts.py` needs an
`EvidenceContract` *for that run*.

## 2. The blocker

**There is no `artifact_dir → EvidenceContract` producer anywhere in the
codebase.** I grepped every `EvidenceContract` reference under
`src/polaris_v6/`: the producers/consumers are the schema, the four
golden-fixture API modules (`bundle`/`charts`/`compare`/`followup`), and the
`compare`/`followup` business logic — none builds an `EvidenceContract` from
a live run's `artifact_dir`. `src/polaris_v6/api/artifact_to_slice_chain.py`
(the slice-7a bridge) produces an **`AuditIR`**, NOT an `EvidenceContract`.

**Producing an `EvidenceContract` from `artifact_dir` is exactly issue
#544's scope** — #544 (I-rdy-014c) verbatim: *"`GET /runs/{run_id}/bundle`
currently serves only `_GOLDEN_RUN_INDEX` fixtures... Bridge the bundle
endpoint to serve a real run from its run_store `artifact_dir`."* #544 is
**operator-excluded** from this autonomous loop (Phase-3 / #510-dependent).
So slice 8 cannot legitimately build that bridge — that is #544's work.

## 3. What IS available for a live run

The slice-7a inspector route resolves `run_store → artifact_dir →
load_audit_ir(artifact_dir) → AuditIR`. The `AuditIR` is fully available for
any live completed run. But its shape differs from `EvidenceContract`:

- `chart_from_bundle`'s **forest_plot** maps each `EvidenceContract`
  `frame_coverage` entry to a point with `estimate = f.coverage_percent /
  100.0`, `ci_low/ci_high = (coverage_percent ± 5)/100`.
- **AuditIR has no `coverage_percent`.** `FrameCoverageEntry`
  (`loader.py:163`) carries `status: str` (pass/partial/frame_gap), `slot_id`,
  `entity_id`, etc. — no per-entity percentage. `FrameCoverageReport`
  (`loader.py:191`) carries `pass_count` / `partial_count` /
  `frame_gap_count` / `total_entities` / `total_slots` — report-level
  counts, not per-entity scalars.
- So a `chart_from_audit_ir` cannot be a field-rename of `chart_from_bundle`
  — the forest_plot's numeric basis (`coverage_percent`) does not exist in
  AuditIR; the derivation must be **redesigned** (e.g. status→numeric
  mapping, or report-level pass/partial/gap counts as the chart input).
  `comparison_table` and `timeline` likely have analogous shape gaps.

## 4. Reject up front (do NOT pick this)

**Building an `artifact_dir → EvidenceContract` adapter inside slice 8.**
That is #544's scope verbatim; folding it under #504 would have slice 8 do
operator-excluded work. Not an option.

## 5. The decision — rule (a) vs (c)

- **Option A — `chart_from_audit_ir`.** Slice 8 = `charts.py` resolves
  `run_store → artifact_dir → load_audit_ir()` (mirroring the slice-7a
  inspector route, reusing/sharing `_resolve_completed_artifact_dir`), and a
  **new `chart_from_audit_ir`** derives the 3 Vega-Lite chart types from the
  `AuditIR` — a genuine derivation redesign (no `coverage_percent`; map
  `status`/counts → chart inputs). `chart_from_bundle` stays for the golden
  path or is replaced. Self-contained; no #544 dependency; #504 closes after
  slice 8 as the scope consult intended. Cost: real chart-redesign work +
  the demo charts change visual character (status-based, not
  percentage-based).
- **Option C — rescope charts; close #504 on the Inspector.** Charts cannot
  be migrated without either #544's `EvidenceContract` bridge or an AuditIR
  chart-redesign; if the redesign is judged out-of-character for a
  "wire-live-runs" slice, charts is split into a NEW dedicated follow-up
  issue that **depends on #544** (it can reuse #544's `EvidenceContract`
  bridge and keep `chart_from_bundle` unchanged). #504 then closes **now**
  on the completed Inspector work (slices 1-7c) — the operator already
  carved #544/#532/#542/#543 out of #504, which structurally means #504 was
  always going to close on less than its 7 originally-listed surfaces;
  charts joining that carve-out set is consistent with the operator's
  decomposition, NOT a regression. (This option is the operator's
  scope-ordering structure made explicit — not Codex blocking #504.)

Tie-breaker guidance: Option A is right IF deriving the 3 charts from
`AuditIR` yields honest, non-degenerate visuals without inventing numbers
(no fabricated `coverage_percent`). Option C is right IF an honest AuditIR
chart derivation would require synthesizing quantities AuditIR does not
contain — in a clinical-audit product, a chart must not display invented
magnitudes. Weigh that explicitly.

## 6. Output schema

```yaml
verdict: APPROVE            # APPROVE = ruling made
chosen_option: A | C
slice_8_scope: <one line — exactly what slice 8 builds>
chart_from_audit_ir_viable: <yes/no — can the 3 charts derive honestly from AuditIR without inventing magnitudes?>
close_504: <"after slice 8" | "now, charts → new follow-up issue depending on #544">
new_followup_issue: <if Option C: one-line title for the charts follow-up issue, else "none">
rationale: <2-5 lines — especially the honest-visual / no-invented-magnitude judgment>
remaining_blockers_for_execution: [...]
```
