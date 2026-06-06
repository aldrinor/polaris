# FX-10 §-1.1 audit — completeness NOT_APPLICABLE 3VL state (I-ready-017 #1115)

**Standard:** §-1.1 on the REAL held drb_72 `manifest.completeness` +
`completeness.json` (`outputs/audits/I-ready-017/run_artifacts/`).

## The bug (real artifact)
`manifest.completeness` = `{"covered_fraction": 1.0, "total_applicable": 0,
"total_covered": 0, "uncovered_topic_ids": []}` — a **bare vacuous 1.0 presented as
complete**, with NO state field. The run was ON-mode (research-planner; no domain
checklist applied), so nothing was actually checked, yet the manifest reads "100%".
A check whose precondition is unmet is N/A, not a pass (SQL 3VL: an empty applicable
set is UNKNOWN/NULL, never TRUE).

## The fix, replayed on the SAME real report (no spend)
Rebuilt the `CompletenessReport` from the real values and read the new property:
`total_applicable=0 → completeness_state='not_applicable'`, `covered_fraction=1.0`
(numeric unchanged — consumers compare it without TypeError). **Audit verdict: PASS** —
the vacuous 1.0 is now disambiguated as `not_applicable` rather than masquerading as a
measured 100%.

## Fix legs
1. `completeness_checker.py`: new `completeness_state` property → `'not_applicable'` if
   `total_applicable==0` else `'measured'`. `covered_fraction` stays numeric.
2. `run_honest_sweep_r3.py`: `completeness.json` + both `manifest.completeness` blocks now
   carry `completeness_state` (+ `notes` on the success manifest). ON-mode neutral report
   tagged `notes=['no_checklist_loaded']`.
3. `evaluator_gate.py:184`: `comp_thin` now requires `completeness_state=='measured'` — a
   not_applicable completeness is ADVISORY (never flagged as thin coverage). Robust even
   if a future not_applicable carried a low numeric; covered_fraction stays numeric so the
   comparison never TypeErrors.

## Consumer-safety proof (real gate, behavioral)
`test_fx10_completeness_state_iready017` drives the actual `compute_evaluator_gate`: a
judge flagging `completeness=needs_revision` + a **not_applicable** report → NO
`judge_completeness_needs_revision` reason (advisory-skip, no TypeError); the same judge +
a **measured 0.3** report → IS flagged. So not_applicable is advisory while a genuine thin
coverage still blocks.

## Faithfulness-safe
Honesty fix (don't claim 100% complete when nothing was checked). No
grounding/strict_verify/4-role change; covered_fraction stays numeric; the manifest key
shape only gains additive fields.

## Offline smoke
`pytest test_fx10_completeness_state_iready017.py test_completeness_r6_gap3.py
test_m205_evaluator_gate.py` → **27 passed** (4 FX-10 + 23 regression). All 3 modified
files parse.

---

## iter-2 (Codex iter-1 RC: 1 P1 + 1 P2 → fixed)

**P1 (CI blocker):** `test_research_planner_phase1.py:708` is a source-sentinel that
string-matched the old ON-mode construction `CompletenessReport(domain=q["domain"])`,
which FX-10 rewrote to carry `notes=["no_checklist_loaded"]`. **FIXED:** the sentinel now
asserts `CompletenessReport(` AND `no_checklist_loaded` are present (legitimate contract
update — the neutral report now tags itself not_applicable). Test passes.

**P2 (consumer-facing honesty residual):** `audit_ir/loader.py:_parse_completeness_percent`
maps any `covered_fraction: 1.0` → `100.0` and ignored `completeness_state`, so an
AuditIR/API consumer could still present a not_applicable manifest as 100% complete.
**FIXED:** added a `completeness_state` field to the `RunManifest` AuditIR dataclass
(defaulted last → existing constructors unaffected) + `_parse_completeness_state()` that
prefers the explicit manifest field and falls back to inferring not_applicable from
`total_applicable==0` for pre-FX-10 manifests. covered_fraction stays numeric; the state
is the honesty signal.

**Offline smoke:** 58 tests pass (6 FX-10 incl. 2 new loader tests + audit_ir loader
regression). Plus the P1 sentinel + all 5 RunManifest-constructor test files (129 in the
broader run). loader.py parses.
