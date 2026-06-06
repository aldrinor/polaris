# FX-05 §-1.1 audit — corpus-approval structured authorization (I-ready-017 #1109)

**Standard:** §-1.1 line-by-line on REAL output (not a synthetic fixture). The
input is the held drb_72 run's actual persisted artifact
`outputs/audits/I-ready-017/run_artifacts/corpus_approval.json`.

## The bug, on the real artifact (BUG-06)

| field | held-run value |
|---|---|
| `approved` | **`true`** |
| `user_note` | `"R-3 sweep. Domain=workforce. Auto-approve on sweep."` (50 chars) |
| `report.has_material_deviation` | **`true`** |
| material deviations | T3 −0.35 (below min), T4 +0.217 (above max) — both exceed the 0.15 threshold |
| `report.total_sources` | 145 |

The old `check_auto_approve_allowed(report, user_note)` accepted any note ≥30
chars not in a small trivial-string denylist. The sweep's own 50-char canned
note cleared both checks → a corpus with two material tier deviations
auto-approved and was billed (~$7.86 generator spend). A free-text field is not
a rubber-stamp defense.

## The fix, replayed on the SAME real report (no spend)

Rebuilt the persisted `CorpusDistributionReport` exactly (tier_counts /
tier_fractions / deviations / has_material_deviation) and ran the new gate:

| # | credential supplied | new verdict | why |
|---|---|---|---|
| 1 | the EXACT canned note `"R-3 sweep. Domain=workforce. Auto-approve on sweep."` | **DENY** | a free-text note is not a structured authorization (`AuthorizedSweep`) — fail-closed |
| 2 | none (`PG_AUTHORIZED_SWEEP_APPROVAL` unset → `authorization_from_env()` = `None`) | **DENY** | default-deny on material deviation gates generator spend (§9.1 #5) |
| 3 | `PG_AUTHORIZED_SWEEP_APPROVAL=1` → structured `AuthorizedSweep{authorized_by, authorized_at, flag_source=env}` | **APPROVE** | the one sanctioned override; recorded as a structured, audit-logged block |

**Audit verdict: PASS.** The exact credential that defeated the held run now
denies; the corpus aborts (`abort_corpus_approval_denied`) with zero generator
cost unless an operator sets the explicit flag. This is a spend-gate TIGHTENING
that strengthens §9.1 invariant #5 — not a downgrade.

## Faithfulness-invariant check

No change to provenance / strict_verify / 4-role. FX-05 gates corpus approval
(pre-generation spend), upstream of the faithfulness invariants. The
`authorization` block is additive in `corpus_approval.json` (optional field,
default `None`; backward-compatible — no reader reconstructs the dataclass from
JSON).

## Adjacent-file scan (§-1.2 — checked clean / updated)

- All 4 real callers of `check_auto_approve_allowed` updated to pass
  `authorization_from_env()` (so none keeps the free-text loophole and none
  crashes on the new signature): `scripts/run_honest_sweep_r3.py:2995`,
  `src/polaris_graph/honest_pipeline.py:191`,
  `scripts/run_honest_on_prerebuild_corpus.py:233`,
  `scripts/run_live_honest_cycle.py:178`.
- All 3 test files exercising the gate rewritten to the structured-authorization
  semantics (one used the removed `user_note=` keyword; two encoded the
  loophole): `tests/polaris_graph/test_corpus_approval_gate.py`,
  `tests/polaris_graph/test_b2_corpus_approval_enforcement.py`,
  `tests/crown_jewels/test_cj_005_corpus_approval.py`.
- `tests/polaris_graph/test_m207_invariant_coverage.py` — only asserts the
  symbol is callable; unaffected.
- No JSON reconstruction of `CorpusApprovalDecision` anywhere (grep clean), so
  the new optional `authorization` field is safe.

## Offline smoke

`pytest tests/polaris_graph/test_corpus_approval_gate.py
tests/polaris_graph/test_b2_corpus_approval_enforcement.py
tests/crown_jewels/test_cj_005_corpus_approval.py
tests/polaris_graph/test_m207_invariant_coverage.py` → **33 passed**.

## Q1 (operator/Codex intent)

DEFAULT = `abort_corpus_approval_denied` on any material deviation; the ONLY
sanctioned auto-approve is the structured `PG_AUTHORIZED_SWEEP_APPROVAL` flag.
This HOLDS sweeps that previously auto-approved (e.g. the held drb_72 run). Per
the plan this is intended and honors §9.1 #5. Routed to Codex with
quality-impact framing in the diff-gate brief.

---

## iter-2 (Codex iter-1 RC: 1 P1 + 1 P2 → fixed)

**P1 (real, valid):** the gate returned `approved=False`, but 3 of the 4 callers
computed it and then proceeded into generation/report/evaluator anyway — only
`run_honest_sweep_r3.py` had the `if not approved` abort. So spend still
happened for those 3 (violating §9.1 #5). Fixed: added the
`abort_corpus_approval_denied` short-circuit BEFORE generation to all three:
- `scripts/run_live_honest_cycle.py` — abort before `generate_live_draft` (return 4 + abort report.md).
- `scripts/run_honest_on_prerebuild_corpus.py` — abort before `generate_multi_section_report` (return 4 + abort report.md).
- `src/polaris_graph/honest_pipeline.py` — abort before `strict_verify`/report/evaluator; returns a `PipelineResult(status="abort_corpus_approval_denied", evaluator=None)` + abort report.md + manifest. Consumer `run_honest_full_cycle.py` now guards on `result.status` before using `result.evaluator` (now Optional).

**Behavioral proof (REAL offline `run_honest_pipeline` run, no spend):** a clinical
question over a 10×T5 industry corpus (material deviation) with no flag →
`status=abort_corpus_approval_denied`, `evaluator is None`, `final_report_text==""`,
`report.md` carries the abort verdict and contains NO `## Methods` synthesis. PASS.

**P2 (stale operator text) — fixed in 3 places:** `render_approval_html`
material banner, the module docstring, and the sweep abort artifact in
`run_honest_sweep_r3.py` now all reference the structured
`PG_AUTHORIZED_SWEEP_APPROVAL` credential instead of "provide a substantive note".

**Offline smoke:** 36 tests pass (added 3 abort-before-generation enforcement
tests, one per caller, asserting `if not approved:` precedes the generation call
and returns early). All 4 modified modules import cleanly.
