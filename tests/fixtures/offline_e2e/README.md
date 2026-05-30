# Offline E2E fixtures (I-meta-002 PR-9) — SYNTHETIC, non-benchmark, isolated

**synthetic: true.** Every file in this directory is a SYNTHETIC, non-benchmark
fixture used ONLY by the offline no-spend E2E harness
(`scripts/dr_benchmark/offline_e2e.py` + `tests/dr_benchmark/test_offline_e2e.py`).

These files are NOT real audits, NOT the frozen DR gold rubric, and NOT competitor
answers. They prove the external-scorer SCRIPTS run end to end offline — they do NOT
produce a real score.

Codex P2 #1 (binding): these fixtures are clearly labeled synthetic and live here,
ISOLATED under `tests/fixtures/offline_e2e/`. The harness NEVER reads anything under
`outputs/dr_benchmark/` (gold rubric / freeze pin / competitor answers) and NEVER writes
under `outputs/dr_benchmark/` (scored JSON + final report go to a caller-supplied tmp dir).

Files:
- `synthetic_rubric.json` — a synthetic 1-question (Q75) rubric with a synthetic
  `rubric_sha256` pre-registration-anchor STRING (not a hash of any real rubric). Exists
  only so `score_run`'s stored-field equality (`rubric_doc.rubric_sha256 ==
  ledger.rubric_sha256`) can be exercised offline.
- `synthetic_ledger_claude.json` / `synthetic_ledger_codex.json` — two single-auditor
  ledgers (`auditor: claude` / `auditor: codex`) over the same (system=chatgpt,
  question=Q75, rubric_sha256). They DISAGREE on one claim (claude=VERIFIED vs
  codex=FABRICATED) and one coverage row so `scripts.dr_benchmark.reconcile`'s
  conservative-MAX worse-of-two reconciliation is non-vacuously exercised before
  `score_run.score_one` runs on the reconciled output.

The 4-role-seam leg of the E2E (manifest `four_role_evaluation` + `four_role_claim_audit.json`)
uses NO files here: it runs the REAL seam over the annotated `clinical_tirzepatide_t2dm`
contract (`config/scope_templates/clinical.yaml`) with an INJECTED FAKE RoleTransport and
canned in-memory report objects — see the harness/test for those in-code fixtures.
