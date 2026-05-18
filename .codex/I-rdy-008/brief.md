# Codex BRIEF review — I-rdy-008 / GH #504 slice 8: migrate the charts route off golden fixtures onto run_store + a new chart_from_audit_ir derivation

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 8 of #504 — the FINAL slice; the architecture is settled

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI"). Slices
1-7c merged (PR #590-#598) — the Evidence Inspector is fully migrated onto
the AuditIR data path. Two Codex consults this session settled slice 8:
- **Scope consult** (`.codex/I-rdy-008/slice8_scope_consult_verdict.txt`,
  Option A): #504's only residual surface is **charts** —
  pin-replay/follow-up/compare/bundle are carved to #532/#542/#543/#544
  (operator-excluded); memory is already run_store-independent. Slice 8 is
  #504's **final** slice; #504 closes after it merges.
- **Charts architecture consult**
  (`.codex/I-rdy-008/slice8_charts_arch_consult_verdict.txt`, Option A):
  `charts.py` is `EvidenceContract`-coupled and there is NO
  `artifact_dir → EvidenceContract` producer (that is #544's excluded
  scope). Therefore slice 8 = resolve `run_store → artifact_dir →
  load_audit_ir()` and derive the charts from a **new `chart_from_audit_ir`**
  built on AuditIR-native quantities.

This brief is a NORMAL implementation brief — review the plan.

## 1. The problem

`src/polaris_v6/api/charts.py` (full, 32 lines): `GET /runs/{run_id}/
charts/{chart_type}` resolves `run_id` against the hardcoded
`_GOLDEN_RUN_INDEX` (imported from `bundle.py`) → 404 for any non-golden
run; reads the golden `EvidenceContract` fixture; calls
`chart_from_bundle(bundle, chart_type)` → Vega-Lite spec. So the inspector
Charts tab (`web/app/inspector/[runId]/page.tsx` ChartsTab → `getChart()`)
renders only for the 7 golden fixtures, not for live completed runs.

## 2. Grounding (Codex: VERIFY, do not re-discover)

- **The resolver to reuse.** `src/polaris_v6/api/inspector.py:39`
  `_resolve_completed_artifact_dir(run_id) -> Path` (slice-7a) does exactly
  the `run_store.get_run` → 404/409/422 → `artifact_dir` resolution; slice-1
  `get_inspector_run` + slice-7a `get_inspector_run_evidence` both call it.
- **The chart builders to reuse.** `src/polaris_v6/charts/spec_builder.py`
  — `build_forest_plot(title, points, x_label)` / `build_comparison_table
  (title, rows)` / `build_timeline(title, points, period_kind)` consuming
  `ForestPlotPoint(label, estimate, ci_low, ci_high, evidence_id)` /
  `ComparisonRow(entity, metric, value, evidence_id)` / `TimelinePoint
  (period, value, series, evidence_id)`. Vega-Lite layer — UNCHANGED by
  slice 8; `chart_from_audit_ir` feeds it AuditIR-derived inputs.
- **AuditIR has the chartable quantities** (`src/polaris_graph/audit_ir/
  loader.py`): `ContradictionCluster(cluster_id, subject, predicate,
  severity, absolute_difference, claims)` + `ContradictionClaim(evidence_id,
  subject, value: float, unit, source_tier, ...)`; `BibliographyEntry(num,
  evidence_id, statement, tier, url)`; `VerifiedReport(sections,
  sentences_verified, ...)` + `ReportSection(title, kept_count,
  dropped_count, total_in, sentences)` + `ReportSentence(claim_id, section,
  text, tokens, is_verified, ...)`. **AuditIR has NO `coverage_percent`**
  (`FrameCoverageEntry` carries `status: str` only) — the existing
  `chart_from_bundle` `coverage_percent/100.0` math has no AuditIR
  equivalent (this is why the arch consult ruled a redesign, not a port).
- **`chart_from_bundle` is already a "Phase 0/1 stub"** — its own docstring
  says "deterministic synthetic mapping"; e.g. its contradiction forest_plot
  hardcodes `estimate=0.0, ci_low=-1.0, ci_high=1.0` and its timeline uses
  `value=float(idx+1)`. So the existing charts are NOT real magnitudes
  either — slice 8 does not regress honesty, it can improve it.
- **No shared-surface breakage.** `compare.py` + `followup.py` import
  `_GOLDEN_RUN_INDEX`/`_FIXTURE_DIR` from **`bundle.py`** (verified), NOT
  from `charts.py`. `charts.py` losing its own `bundle` import does not
  touch them; `bundle.py` keeps the symbols.

## 3. The two HARD CONSTRAINTS (Codex arch consult — treat as P0 review criteria)

1. **Do NOT build an `artifact_dir → EvidenceContract` adapter.** That is
   #544's operator-excluded scope. Slice 8 derives charts from the
   `AuditIR` only.
2. **Do NOT synthesize per-frame `coverage_percent` or statistical
   confidence intervals from AuditIR `status` fields.** No fabricated
   magnitudes; every numeric shown must be a real AuditIR quantity (a
   count, a rate that is genuinely `kept/total`, or a value a source
   actually reported). No band labeled "95% CI" unless it IS one.

## 4. Plan

### 4.1 `src/polaris_v6/api/run_resolver.py` (new) — extract the shared resolver
Move `_resolve_completed_artifact_dir` out of `inspector.py` into a new
`src/polaris_v6/api/run_resolver.py` (behavior-preserving — same body, same
404/409/422 + detail strings). `inspector.py` imports it from there;
`charts.py` imports it from there. Rationale: two route modules now need
it; a `_`-private cross-route import is worse hygiene than a shared module.
(Scope-boundary call 6.1.)

### 4.2 `src/polaris_v6/charts/from_audit_ir.py` (new) — `chart_from_audit_ir`
`chart_from_audit_ir(*, ir: AuditIR, chart_type: ChartType) -> dict`,
deriving each of the 3 chart types from AuditIR-native quantities and
feeding the existing `spec_builder` builders:

- **forest_plot** ← contradiction value spreads. One `ForestPlotPoint` per
  `ContradictionCluster`: `estimate` = mean of `claims[].value`,
  `ci_low`/`ci_high` = min/max of `claims[].value` — the **real range of
  the values disagreeing sources reported** (not a statistical CI). Pass
  `x_label="Reported value across disagreeing sources"` (honest label —
  the spec_builder default "Effect estimate (95% CI)" would misrepresent).
  `label` = `f"{cluster.subject}"`, `evidence_id` = `claims[0].evidence_id`.
  Title makes the mean/range explicit, e.g. "Contradictions — point = mean
  of reported values, bar = min–max across disagreeing sources" (Codex
  brief iter-1 P2: spec_builder's tooltip field names are `estimate`/
  `ci_low`/`ci_high` and cannot be renamed without touching spec_builder,
  out of scope — the title/x_label carry the honest wording instead).
  Fallback when `ir.contradictions` is empty: one `ForestPlotPoint` per
  `ReportSection` with `estimate = kept_count / total_in` (a genuine
  verification rate 0-1) and `ci_low = ci_high = estimate` (a point, no
  invented band); `x_label="Section verification rate (verified / total)"`.
  **Zero-denominator guard (Codex brief iter-1 P1-2):** `loader.py` accepts
  `ReportSection.total_in == 0` (when `verification_details` omits
  `total_in`), so `kept_count / total_in` would `ZeroDivisionError` → 500.
  Sections with `total_in <= 0` are SKIPPED from the fallback (no honest
  rate exists for them). If every section has `total_in <= 0` (or there are
  no sections), emit the single `(no data)` placeholder point instead.
  Empty-report fallback: a single labelled `(no data)` placeholder point
  (mirrors `chart_from_bundle`'s placeholder pattern — `build_*` raise on
  empty input).
- **comparison_table** ← source-tier mix. Count `ir.bibliography` entries
  per `tier`; one `ComparisonRow` per tier (`entity=f"Tier {tier}"`,
  `metric="source_count"`, `value=<count>`, `evidence_id`=the first
  bibliography `evidence_id` of that tier). Honest counts. Empty-bibliography
  fallback: `(no sources)` placeholder row.
- **timeline** ← report-order sentence series. Iterate
  `ir.verified_report.sections[]` in order, then `.sentences[]`; one
  `TimelinePoint` per sentence (`period=f"step-{n:02d}"`, `value=<1-based
  position>`, `series=<section title>`, `evidence_id`=`sentence.tokens[0]
  .evidence_id` if any else `sentence.claim_id`). This is a positional
  series — `value` is a real ordinal position, not an invented magnitude
  (the same shape `chart_from_bundle`'s timeline already uses). Empty
  fallback: `(no sentences)` placeholder.

### 4.3 `src/polaris_v6/api/charts.py` — rewrite the route
`get_chart` resolves `artifact_dir = _resolve_completed_artifact_dir(run_id)`
→ `ir = load_audit_ir(artifact_dir)` (catching the same loader exceptions
the inspector route catches → 422) → `return chart_from_audit_ir(ir=ir,
chart_type=chart_type)`. Drop the `_GOLDEN_RUN_INDEX`/`_FIXTURE_DIR`/
`EvidenceContract`/`chart_from_bundle` imports. Resolution taxonomy then
matches the inspector route: unknown 404 / not-completed 409 / abort 422 /
missing artifact_dir 404 / unloadable AuditIR 422.

### 4.4 `tests/v6/test_api_charts.py` — rewrite onto a seeded run_store
**Codex brief iter-1 P1-1 (corrected):** the current `test_api_charts.py`
`client` fixture is `TestClient(create_app())` against the DEFAULT
`run_store` — which contains NO `golden_*` rows. After the migration,
`_resolve_completed_artifact_dir("golden_clinical_001")` → `run_store.get_run`
returns `None` → 404; every existing chart test would fail. (The earlier
draft's claim that "the inspector e2e proves golden runs resolve via
run_store" conflated the Playwright CI backend with these unit tests — the
unit tests use the default DB and must seed it themselves.)

Rewrite `test_api_charts.py` to mirror `tests/v6/test_inspector_route.py`:
the `client` fixture sets a temp `POLARIS_V6_RUN_DB` env BEFORE
`create_app()`, calls `run_store.init_db()`, and seeds completed runs
pointing at loadable AuditIR `artifact_dir`s — reuse
`test_inspector_route.py`'s artifact-dir + `_seed_completed` helpers
(import them, or factor a shared `tests/v6/` fixture helper if cleaner —
scope-boundary call 6.5). Seed at least: a run whose AuditIR has
`contradictions` (forest_plot real-spread path), a run with no
contradictions (forest_plot section-rate fallback), a run with a
`total_in == 0` section (the P1-2 zero-denominator guard), a run with a
populated `bibliography` (comparison_table tier mix), and verified-report
sentences (timeline). Tests then target the seeded run_ids — NOT `golden_*`.
Cover: each of the 3 chart types → 200 + the right `polaris_provenance
.chart_type`; unknown run → 404; unknown chart_type (`pie_chart`) → 422;
the `total_in == 0` section does not 500; an `abort_*` run → 422.

## 5. Smoke

`python -c "import ast; ast.parse(...)"` on every changed/new `.py` file
(`run_resolver.py`, `inspector.py`, `charts.py`, `from_audit_ir.py`,
`test_api_charts.py`); `PYTHONPATH='src;.' pytest tests/v6/test_api_charts.py
tests/v6/test_inspector_route.py` (the latter because `inspector.py`'s
resolver import path changes — confirm slice-1/7a inspector tests still
pass). Pre-existing failures (if any) verified identical on clean `polaris`
HEAD via `git stash`. No `web/` change — the ChartsTab consumes the
Vega-Lite spec shape, which `spec_builder` keeps stable.

## 6. Scope-boundary calls (Codex: rule accept / adjust)

- **6.1 — extract `_resolve_completed_artifact_dir` to a new
  `run_resolver.py`** (vs. `charts.py` importing the `_`-private straight
  from `inspector.py`). Recommend ACCEPT the extraction — cleaner shared
  surface, behavior-preserving, ~1 small refactor of `inspector.py`'s
  import.
- **6.2 — `chart_from_bundle` / `from_bundle.py` become dead code** once
  `charts.py` stops importing them (grep: `charts.py` is the only
  importer). Recommend slice 8 LEAVES them in place (do not delete) — a
  focused migration; a dead-code sweep is a separate hygiene follow-up.
  Codex: rule whether leaving dead code is acceptable for this slice or it
  must be deleted here.
- **6.3 — the forest_plot empty-contradictions fallback** (per-section
  verification rate, with the §4.2 `total_in <= 0` skip guard from Codex
  brief iter-1 P1-2). Recommend ACCEPT — keeps the chart meaningful for the
  common no-contradiction run without inventing magnitudes and without the
  zero-division 500.
- **6.4 — charts go fully run_store** (no dual golden/run_store path).
  Recommend ACCEPT — a single run_store path serves any completed run
  (golden or live); a dual path would be dead complexity. The unit tests
  seed their own run_store (§4.4), so no golden-DB dependency remains.
- **6.5 — the seeded-run_store test helpers** (§4.4). Recommend importing
  `test_inspector_route.py`'s existing artifact-dir + `_seed_completed`
  helpers directly (vs. factoring a shared `tests/v6/conftest.py` fixture).
  Codex: rule whether a direct cross-test-module import is acceptable or a
  shared `conftest.py`/helper module is required.

## 7. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/bundle.py` — keeps `_GOLDEN_RUN_INDEX`/`_FIXTURE_DIR`;
  `compare.py` + `followup.py` still import them from here; NOT modified.
- `src/polaris_v6/api/compare.py`, `followup.py` — import from `bundle.py`
  not `charts.py`; unaffected; NOT modified.
- `src/polaris_v6/charts/spec_builder.py` — the Vega-Lite builders;
  reused as-is; NOT modified.
- `src/polaris_v6/api/app.py` — mounts the charts router; the route path is
  unchanged; NOT modified.
- `web/app/inspector/[runId]/page.tsx` ChartsTab + `getChart()` — consume
  the Vega-Lite spec shape (stable via `spec_builder`); NOT modified.

## 8. Output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
