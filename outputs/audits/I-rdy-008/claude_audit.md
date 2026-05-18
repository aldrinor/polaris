# Claude architect audit — I-rdy-008 (#504) slice 8

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 8 of #504** — the FINAL slice. Two Codex consults settled it:
the scope consult (`.codex/I-rdy-008/slice8_scope_consult_verdict.txt`,
Option A — #504's residual is charts) and the charts architecture consult
(`.codex/I-rdy-008/slice8_charts_arch_consult_verdict.txt`, Option A —
migrate charts to run_store/AuditIR with a new `chart_from_audit_ir`).
**Branch:** `bot/I-rdy-008-slice8` off `polaris` HEAD `869ee795`.
**Commit 1:** `e6eaa297`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review APPROVE iter 2
(iter-1 2×P1 fixed; 3 P2 baked in).

## 1. What shipped

The charts route is migrated off the golden-fixture-only `_GOLDEN_RUN_INDEX`
onto the same `run_store → artifact_dir → load_audit_ir()` path the
inspector routes use, with a new AuditIR-native chart derivation.

- **`src/polaris_v6/api/run_resolver.py`** (new) — `resolve_completed_
  artifact_dir(run_id)`, the run_store → artifact_dir resolver, extracted
  verbatim from `inspector.py`'s slice-7a `_resolve_completed_artifact_dir`
  (renamed public; same 404/409/422 taxonomy + detail strings).
- **`src/polaris_v6/api/inspector.py`** — imports the resolver from
  `run_resolver.py`; the local def + the now-unused `run_store` import are
  removed. Behavior-preserving.
- **`src/polaris_v6/charts/from_audit_ir.py`** (new) — `chart_from_audit_ir`
  derives the 3 Vega-Lite chart types from AuditIR-native quantities.
- **`src/polaris_v6/api/charts.py`** — `get_chart` rewritten onto
  run_store/AuditIR; the `_GOLDEN_RUN_INDEX` / `_FIXTURE_DIR` /
  `EvidenceContract` / `chart_from_bundle` imports dropped.
- **`tests/v6/_audit_ir_fixtures.py`** (new) — shared seeded-run_store +
  AuditIR-loadable artifact_dir helpers.
- **`tests/v6/test_api_charts.py`** — rewritten onto a seeded isolated
  run_store.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — the two HARD CONSTRAINTS (brief §3, P0 criteria).** (1) No
  `artifact_dir → EvidenceContract` adapter: `from_audit_ir.py` imports only
  `AuditIR`/`ContradictionCluster` from the loader + `spec_builder`; no
  `EvidenceContract` reference anywhere in the slice's `src/` changes.
  (2) No fabricated magnitude: `from_audit_ir.py` has no `coverage_percent`;
  the forest-plot `ci_low`/`ci_high` carry `min`/`max` of the actual
  `claims[].value` the sources reported (the title states "bar = min–max
  across disagreeing sources"); the section-rate `estimate` is a genuine
  `kept_count / total_in`; the timeline `value` is a 1-based report
  position. No invented numbers, no band labeled "95% CI".
- **VERIFIED — P1-1 (seeded run_store).** `test_api_charts.py`'s `client`
  fixture sets `POLARIS_V6_RUN_DB` before `create_app()` + `run_store
  .init_db()`, mirroring `test_inspector_route.py`; every chart test seeds
  its own completed run via `seed_completed_run` and targets that run_id —
  no `golden_*` ID is used. Confirmed: `pytest tests/v6/test_api_charts.py`
  is green against the default (empty) DB because each test seeds.
- **VERIFIED — P1-2 (zero-denominator guard).** `_forest_plot`'s
  section-rate fallback filters `if section.total_in > 0`, so a section
  whose `total_in` defaulted to 0 is skipped before any `kept_count /
  total_in`. `test_forest_plot_zero_total_in_section_does_not_500` seeds
  exactly that section and asserts 200 + the `(no data)` placeholder — not
  a 500.
- **VERIFIED — P2s baked in.** (a) Shared helpers live in a new
  `tests/v6/_audit_ir_fixtures.py`, not a cross-import from
  `test_inspector_route.py`. (b) `_timeline` skips zero-token sentences
  (`if not sentence.tokens: continue`) — no `claim_id` is placed in the
  `evidence_id` field. (c) `_cluster_label` is `subject or predicate or
  f"cluster-{cluster_id}"` — never blank.
- **VERIFIED — resolver extraction is behavior-preserving.** The 15
  `test_inspector_route.py` tests (slice-1 + slice-7a, covering all
  404/409/422 cases) still pass with `inspector.py` importing the resolver
  from `run_resolver.py` — proof the extraction changed no behavior.
- **VERIFIED — no shared-surface breakage.** `compare.py` + `followup.py`
  import `_GOLDEN_RUN_INDEX`/`_FIXTURE_DIR` from `bundle.py` (not
  `charts.py`); `bundle.py` is untouched, so they are unaffected. `charts.py`
  simply stops importing those symbols.
- **VERIFIED — fail-loud resolution taxonomy.** `get_chart` resolves via
  `resolve_completed_artifact_dir` (unknown 404 / not-completed 409 /
  abort 422 / missing dir 404) then catches the loader exceptions → 422.
  `test_unknown_run_returns_404` + `test_abort_run_returns_422` confirm.
  Unknown `chart_type` → 422 via the `ChartType` Literal
  (`test_unknown_chart_type_returns_422`).
- **VERIFIED — scope.** `src/` changes: `run_resolver.py`, `inspector.py`,
  `from_audit_ir.py`, `charts.py`. `tests/` changes: `_audit_ir_fixtures.py`,
  `test_api_charts.py`. No `web/` change (the ChartTab consumes the
  Vega-Lite spec shape, kept stable by `spec_builder`). `chart_from_bundle`
  / `from_bundle.py` left in place (brief §6.2 — dead-code sweep is a
  separate hygiene follow-up).

## 3. Smoke

`ast.parse` — all 6 changed/new `.py` files clean. `PYTHONPATH='src;.'
pytest tests/v6/test_api_charts.py tests/v6/test_inspector_route.py` —
**26 passed** (11 new charts tests + 15 inspector regression). No `web/`
change → no web smoke.

## 4. Codex iteration trail

- Scope consult — #504 residual = charts.
- Charts arch consult — Option A: run_store/AuditIR + `chart_from_audit_ir`.
- Brief iter 1 REQUEST_CHANGES — P1-1 (unseeded run_store), P1-2
  (zero-denominator). Brief iter 2 APPROVE — both fixed; 3 P2 baked in.

## 5. Scope + residuals

Slice 8 is #504's final slice — after merge, #504 closes. **Diff size:** the
canonical code diff is ~635 LOC, larger than a typical slice because the
arch consult mandated a *new* derivation module (`from_audit_ir.py`, 196
lines) plus a full seeded test rewrite (`test_api_charts.py` + the shared
fixtures module); the Codex brief review APPROVE'd the plan at exactly this
scope, so the size is intrinsic to the approved architecture, not sprawl.
`chart_from_bundle`/`from_bundle.py` are now unreferenced — a dead-code
sweep is a deliberate out-of-scope follow-up (brief §6.2). The accepted
`evidence_pool.json` golden-fixture residual from slice 7c is unrelated to
charts and unaffected.

## 6. Verdict

Faithful to the APPROVE'd brief and both Codex consults: the charts route
serves any completed run (golden or live) via run_store/AuditIR; the 3
chart types derive only from AuditIR-native quantities with no fabricated
magnitude and no pseudo-CI; the resolver extraction is behavior-preserving
(15 inspector tests green); both brief P1s and all 3 P2s are addressed;
ast.parse + 26/26 pytest green. Ready for Codex diff review.
