HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — DIFF REVIEW iter 1

GH#448. Branch `bot/I-snowball-002-graph-endpoint`. This commit (`a8d66d20`) implements the brief APPROVE'd by Codex iter 5 (`.codex/I-snowball-002/codex_brief_verdict.txt`).

## Commit summary

```
a8d66d20 I-snowball-002 — GET /api/runs/{run_id}/graph endpoint (GH#448)
4 files changed, 500 insertions(+), 1 deletion(-)
```

- **NEW**: `src/polaris_graph/api/graph_route.py` (210 LOC) — Pydantic models + `build_graph_payload(ir)` + route
- **MOD**: `src/polaris_v6/api/app.py` (+2 lines) — import + `app.include_router(graph_router, prefix="/api")`
- **NEW**: `tests/polaris_graph/api/conftest.py` (90 LOC) — `small_ir` SimpleNamespace fixture
- **NEW**: `tests/polaris_graph/api/test_graph_route.py` (120 LOC) — 9 test cases

All per-file under 200 LOC (CHARTER §3 cap).

## Plan → execution mapping (from brief iter 5)

| Brief stage | Execution result |
|---|---|
| Pydantic models (NodeData, ClaimNode, EdgeData, ClaimEdge, GraphElements, GraphDiagnostics, GraphPayload) | All 7 models present, top-level `position` field on ClaimNode per DECISION.md iter-3 fix |
| Bare `polaris_graph.audit_ir.{registry,loader}` imports (no `src.` prefix) | `graph_route.py` lines 18-19, `app.py` line 51; matches existing slice-router precedent |
| V30 AuditIR input via `find_run_by_id` + `load_audit_ir` | Route lines 209-217 |
| Fallback source nodes for missing evidence_ids with `classes="bibliography_missing"` | Lines 142-148 |
| `GraphDiagnostics` with `bibliography_count`/`fallback_source_count` (unique)/`missing_reference_occurrence_count` (total)/`referenced_unknown_evidence_ids` | Lines 73-77 |
| 2-hop frontier walk semantics DEFERRED to I-snowball-005 (not in this PR) | confirmed not implemented here |
| Self-contradiction skipped (V30 has no concept) | Lines 175-181: sorted set of evidence_ids ≥ 2 required for any pairwise emission |
| Unverified sentences dropped | Line 161: `if not sent.is_verified: continue` |
| FrameCoverageEntry.status `fail_*` → `fail` normalization | `_normalize_frame_status` helper line 92 + applied line 158 |
| Canonical hash (positions stripped, lists sorted by id, sort_keys=True separators=(',', ':')) | Lines 187-194 |
| Mount in `src/polaris_v6/api/app.py` with `prefix="/api"` | Line 165 |

## Sanity tests (Claude pre-ran)

```
$ PYTHONPATH=src python -m pytest tests/polaris_graph/api/test_graph_route.py -x --tb=short
9 passed in 10.35s

$ PYTHONPATH=src python -m pytest tests/polaris_graph/api/ -x --tb=line -q
89 passed in 11.89s   # full api regression suite — no breakage
```

Test breakdown (all PASS):
1. `test_404_for_missing_run`
2. `test_422_on_audit_ir_load_failure`
3. `test_returns_payload_with_diagnostics` — verifies bibliography_count=2, fallback_source_count=1, missing_reference_occurrence_count=1 on fixture
4. `test_no_dangling_edges` — every edge endpoint resolves to a node
5. `test_deterministic_byte_equal` — two consecutive builds → same elements_hash
6. `test_section_member_edges_match_kept_sentences` — 2 kept (dropped sentence excluded)
7. `test_self_contradiction_skipped` — single-evidence_id cluster → 0 contradicts edges
8. `test_frame_status_normalization` — `fail_min_fields` → `fail`
9. `test_graph_route_mounted_in_create_app` — smoke against `create_app()` from app.py

## Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` (BibliographyEntry, ReportSentence.tokens with `evidence_id`/`start`/`end`, ContradictionCluster.claims, FrameCoverageReport.entries) — schema matches builder usage
- `src/polaris_graph/audit_ir/registry.py:179` (`find_run_by_id`) — signature `(run_id: str) -> RunSummary | None`
- `src/polaris_v6/api/app.py:50-51` + `:165` — mount precedent matches new addition
- `tests/polaris_graph/api/*.py` (8 existing test files, 80 cases) — no regressions

## Direct questions for Codex diff review

1. Does the diff implement the brief APPROVE'd at iter 5 verbatim? Any P0/P1 missed?
2. **`tok.evidence_id not in valid_source_ids` defensive guard** (line 172) — should never fire given fallback creation, but it's there. Acceptable as belt-and-suspenders, or remove?
3. **Test fixture uses `SimpleNamespace`** instead of real `AuditIR` dataclass — purely for test brevity (AuditIR has ~30 nested dataclass dependencies). The builder duck-types attribute access. Acceptable, or should the fixture build real AuditIR?
4. **`test_graph_route_mounted_in_create_app` instantiates `create_app()` directly** — this requires all real dependencies to be importable. If create_app fails for reasons unrelated to graph route (e.g., missing env var), this test would fail for the wrong reason. Acceptable in current shape, or restructure to import-only check?
5. **`Exception as exc:` in route handler** (line 215) — broad catch. Codex flagged this in past reviews as too broad; here it's preserved because `load_audit_ir` raises a documented `AuditIRSchemaError(ValueError)` + filesystem errors. Acceptable, or narrow?

## Output schema (terse)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
