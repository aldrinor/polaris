# Codex DIFF review — I-rdy-008 / GH #504 slice 8: charts route → run_store + chart_from_audit_ir

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #504 **slice 8** — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-008/` and `outputs/audits/I-rdy-008/` (canonical
diff in `.codex/I-rdy-008/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-008/brief.md` (brief APPROVE iter 2;
0 P0/P1; 3 P2 baked in). Slice 8 is #504's FINAL slice — #504 closes after
it merges.

**6 code files** (+ `state/polaris_restart/iteration_trajectory.md` process
metadata): `src/polaris_v6/api/run_resolver.py` (new),
`src/polaris_v6/api/inspector.py`, `src/polaris_v6/charts/from_audit_ir.py`
(new), `src/polaris_v6/api/charts.py`, `tests/v6/_audit_ir_fixtures.py`
(new), `tests/v6/test_api_charts.py`.

## 2. The change

Two prior Codex consults settled slice 8: the scope consult ruled #504's
only residual surface is charts; the charts architecture consult (Option A)
ruled that — because `charts.py` was `EvidenceContract`-coupled and the
`artifact_dir → EvidenceContract` bridge is #544's operator-excluded scope —
charts must resolve `run_store → artifact_dir → load_audit_ir()` and derive
the Vega-Lite specs from AuditIR-native quantities via a new
`chart_from_audit_ir`.

- **`run_resolver.py`** (new) — `resolve_completed_artifact_dir(run_id)`,
  the run_store → artifact_dir resolver, extracted from `inspector.py`'s
  slice-7a `_resolve_completed_artifact_dir` (renamed public; same
  404/409/422 taxonomy + detail strings).
- **`inspector.py`** — imports the resolver from `run_resolver.py`; local
  def + now-unused `run_store` import removed.
- **`from_audit_ir.py`** (new) — `chart_from_audit_ir(*, ir, chart_type)`:
  - forest_plot ← contradiction value spreads: per `ContradictionCluster`,
    `estimate` = mean of `claims[].value`, `ci_low`/`ci_high` = min/max of
    those values (real reported numbers, not a statistical CI). Fallback
    when no contradictions: per-section `kept_count / total_in` rate,
    skipping `total_in <= 0` sections. Empty → `(no data)` placeholder.
  - comparison_table ← `bibliography` source-tier counts.
  - timeline ← report-order cited verified sentences (zero-token sentences
    skipped).
- **`charts.py`** — `get_chart` rewritten onto run_store/AuditIR; the
  `_GOLDEN_RUN_INDEX` / `EvidenceContract` / `chart_from_bundle` imports
  dropped.
- **`_audit_ir_fixtures.py`** (new) + **`test_api_charts.py`** (rewritten) —
  the chart tests seed an isolated run_store (the default DB has no
  `golden_*` rows).

## 3. Verify

1. **Hard constraint 1 — no `artifact_dir → EvidenceContract`.** Confirm
   `from_audit_ir.py` (and the slice's `src/` changes) contain no
   `EvidenceContract` reference and build no bundle from `artifact_dir` —
   that is #544's excluded scope.
2. **Hard constraint 2 — no fabricated magnitude.** Confirm no
   `coverage_percent` and no statistical CI is invented: the forest-plot
   `ci_low`/`ci_high` are `min`/`max` of real `claims[].value`; the
   section-rate `estimate` is a true `kept_count / total_in`; the timeline
   `value` is a 1-based position. The forest-plot title states the
   point=mean / bar=min–max meaning.
3. **Zero-denominator guard.** `_forest_plot`'s section-rate fallback
   filters `if section.total_in > 0` (the loader defaults a missing
   `total_in` to 0). Confirm no `kept_count / total_in` path can divide by
   zero, and `test_forest_plot_zero_total_in_section_does_not_500` proves
   a 200 (not 500).
4. **Resolver extraction is behavior-preserving.** `run_resolver.py`'s
   `resolve_completed_artifact_dir` is byte-equivalent logic to the old
   `inspector.py` `_resolve_completed_artifact_dir` (same status codes +
   detail strings). The 15 `test_inspector_route.py` tests still pass.
5. **Resolution taxonomy.** `get_chart` → unknown 404 / not-completed 409 /
   abort 422 / missing dir 404 / unloadable AuditIR 422; unknown
   `chart_type` → 422 via the `ChartType` Literal.
6. **Tests seed their own run_store.** `test_api_charts.py` sets
   `POLARIS_V6_RUN_DB` before `create_app()` and seeds each run; no
   `golden_*` ID is assumed present.
7. **Scope.** Only the 6 files. No `web/` change. No `bundle.py` /
   `compare.py` / `followup.py` change. `chart_from_bundle` / `from_bundle.py`
   left in place (brief §6.2 — dead-code sweep deferred).

## 4. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/bundle.py` — keeps `_GOLDEN_RUN_INDEX`/`_FIXTURE_DIR`;
  NOT modified. `compare.py`/`followup.py` import them from here; unaffected.
- `src/polaris_v6/charts/spec_builder.py` — the Vega-Lite `build_*`
  builders + `ForestPlotPoint`/`ComparisonRow`/`TimelinePoint`; reused
  as-is; NOT modified.
- `src/polaris_v6/api/app.py` — mounts the charts router; the route path
  `/runs/{run_id}/charts/{chart_type}` is unchanged; NOT modified.
- `src/polaris_graph/audit_ir/loader.py` — `AuditIR` / `ContradictionCluster`
  / `BibliographyEntry` / `ReportSection` shapes consumed; NOT modified.
- `tests/v6/test_inspector_route.py` — keeps its own local helpers
  (untouched — its 15 tests confirm the resolver extraction).

## 5. Smoke state

`ast.parse` — all 6 files clean. `PYTHONPATH='src;.' pytest
tests/v6/test_api_charts.py tests/v6/test_inspector_route.py` —
**26 passed** (11 new charts + 15 inspector regression). No `web/` change.

## 6. Diff size note

The canonical code diff is ~635 LOC — above a typical slice — because the
charts arch consult mandated a *new* `chart_from_audit_ir` derivation
module (196 lines) plus a full seeded test rewrite. The brief was
Codex-APPROVE'd at exactly this scope; the size is intrinsic to the
approved architecture, not unfocused sprawl. Flag only if a file is
genuinely doing unrelated work.

## 7. Required output schema (§8.3.9)

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
