# Claude architect audit — I-snowball-002 (GH#448)

**PR:** #456
**Branch:** `bot/I-snowball-002-graph-endpoint`
**HEAD:** `98d9ac76a70cea122bed6413b3578668ca3d88a7`
**Base:** `f7441b3ceea0e1b24cb71ec3f9bf1f9d6bd85b79` (polaris)
**Canonical PR diff SHA256:** `652fefbabd0c6cf5b42dd848dc97d80eed4e3e95713ff671dee3ee8f91cbecd6`

## Acceptance criteria verification (per GH#448 issue body)

| Criterion | Status | Evidence |
|---|---|---|
| `GET /api/runs/{run_id}/graph` returns `GraphPayload` JSON | ✓ | `src/polaris_graph/api/graph_route.py:230` route; canonical V30 200 OK verified by Codex iter-2 |
| Server-side fcose pre-layout (`randomize:false,quality:'proof',animate:false`) | ✗ DROPPED per DECISION.md Option B | Per `.codex/I-snowball-001/DECISION.md` iter-3+4: client Web Worker computes positions; server returns elements + hash only. Codex APPROVE'd this scope reduction. |
| `position` at element top-level (NOT inside `data`) | ✓ | `graph_route.py:54-56` (ClaimNode has `position: Position \| None` at element-top) |
| `layout_meta` schema | ✗ DROPPED (no server positions in v1) | Will re-add when Option A server-side pre-layout lands (post-handover stretch) |
| Deterministic byte-equal output | ✓ | `test_deterministic_byte_equal` passes; Codex iter-2 reproduced hash `67aaf82314a4` |
| LOC ≤200 | ✗ 249 LOC | Codex flagged P2 non-blocker. Splittable into `graph_models.py` + `graph_route.py` as follow-up if strict cap. |

## §-1.1 line-by-line builder verification

| Plan element | Implementation | Verified |
|---|---|---|
| Source nodes from `BibliographyEntry` | `graph_route.py:122-130` | ✓ tier validated against `_VALID_TIERS`, label clamped to 200 chars |
| Fallback source nodes for missing evidence_ids | `:144-149` | ✓ canonical V30: 97 unique stubs created (Codex iter-2 reproduced) |
| Section nodes from `verified_report.sections` | `:153-158` | ✓ |
| Frame nodes from `frame_coverage.entries` | `:161-167` | ✓ `_normalize_frame_status` maps `fail_*` → `fail` |
| Sentence nodes (verified-only) | `:171-177` | ✓ `if not sent.is_verified: continue` line 174 |
| section_member edges | `:179-184` | ✓ one per verified sentence |
| cites edges (with ordinal disambiguation) | `:186-194` | ✓ ID format `cite:{claim_id}:{ord}:{evidence_id}` prevents collision when same source cited twice |
| contradicts edges (pairwise within cluster) | `:197-205` | ✓ self-contradiction skipped (`evidence_ids ≥ 2 required`) |
| Canonical hash (positions stripped, lists sorted by id) | `:208-216` | ✓ `json.dumps(sort_keys=True, separators=(',',':'))` |
| GraphDiagnostics with bibliography/fallback/missing counts | `:218-224` | ✓ Canonical V30: 26 / 97 / 98 (Codex iter-2 reproduced exactly) |

## Route handler verification

| Behavior | Implementation | Verified |
|---|---|---|
| 404 on missing run_id | `:240-242` | `test_404_for_missing_run` PASS |
| 422 on AuditIR load failure | `:243-246` | `test_422_on_audit_ir_load_failure` PASS |
| Lazy import (hermetic startup) | `:236-238` | Codex diff iter-2 confirmed |
| Mounted in `polaris_v6.api.app` with `prefix="/api"` | `app.py:165` | `test_graph_route_mounted_in_create_app` PASS |

## Crown jewel invariants (CLAUDE.md §9.1)

| Invariant | Touched? | Note |
|---|---|---|
| Two-family evaluator | NO | this PR is read-only on AuditIR output; doesn't touch generator/evaluator |
| Provenance tokens | READ-ONLY | builder reads `EvidenceSpanToken` to derive cites edges; no token mutation |
| Strict verify | NOT REACHED | endpoint is post-verification; reads `is_verified=True` sentences only |
| Zero-verified abort | NOT REACHED | endpoint doesn't run pipeline |
| Corpus approval enforcement | NOT REACHED | post-completion read-only surface |
| Budget cap | NO LLM CALLS | endpoint is pure-Python transform |
| Delimiter sanitization | NO PROMPT WRAPPING | no LLM in this path |

**No crown jewel surface touched.** Endpoint is a read-only projection of `AuditIR`.

## Regression risk

- **89/89** `tests/polaris_graph/api/` regression suite passes locally
- App mount change (`+3 lines` in `app.py`) is additive; no existing route altered
- Lazy import inside route handler isolates startup from audit_ir module load

## Codex review trajectory

- Brief: APPROVE iter 5/5 (`.codex/I-snowball-002/codex_brief_verdict.txt`)
- Diff: APPROVE iter 3/5 (`.codex/I-snowball-002/codex_diff_audit.txt`)
- All errors caught + fixed before merge per `.codex/I-snowball-002/codex_*_iter_*.txt` trail

## Verdict

**SHIP.** Substrate landed cleanly; Codex APPROVE on both gates; canonical V30 reproduces expected counts; no regressions; no crown jewel touched.

Follow-up issues (not blocking):
- Optional: split `graph_route.py` into `graph_models.py` + `graph_route.py` if 200-LOC cap is hardened
- I-snowball-003a (frontend `<ClaimGraph>` component) starts after merge
