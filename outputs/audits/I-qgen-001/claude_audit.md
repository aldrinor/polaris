# Claude architect audit — I-qgen-001 (GH #1291): query-gen COVERAGE-ISOLATION harness

**Verdict:** ship. Codex diff gate APPROVE (clean, 0 P0 / 0 P1, iter 4). Brief gate APPROVE.

## What this delivers
The FIRST instance of the standard per-section review (`docs/standard_process_pipeline_section_review.md`):
query generation scored IN ISOLATION on the COVERAGE axis it drives — no e2e, no report, no render.
For a canonical DRB-II task, each query-gen method's queries are retrieved and scored on how many of
the task's required `info_recall` points the (legal) corpus covers. Highest coverage wins; winners
across sections later combine into one full run.

## Architecture review
- **GATE 0 canonical binding** (`gate0_lineage.py`): every benchmark slug binds to the gold question
  by idx — the drb_72 wrong-question failure cannot recur. Fail-loud on any unregistered `drb_*` slug;
  drb_90 (no DRB-II gold) is an explicit, documented exemption, not a silent gap. Wired into the live
  sweep (override + an unregistered-slug guard) AND the resume path (stale wrong-question snapshot is
  refused). This hardens the production sweep, not just the harness.
- **Pure harness** (`qgen_coverage_harness.py`): retrieve()/judge() injected → deterministic + unit
  testable. Blocked-reference enforcement (DRB-II `blocked`) drops the forbidden source before scoring,
  uniformly for every method, so coverage cannot be won by retrieving the prohibited paper. The
  faithfulness engine is UNTOUCHED — this scores coverage only.
- **Method adapters** (`qgen_methods.py`): FloorMethod (real current POLARIS query-gen incl. the
  hand-authored `amplified` set) vs ClosedLoopMethod (frontier coverage-contract + gap re-query;
  decomposes the question itself, never the gold rubrics — no answer-key leakage). Equal query budgets.
- **Runner** (`run_qgen_coverage.py`): real POLARIS retrieval (cached by query+domain+version) + a
  GLM-5.2 coverage judge that judges EVERY chunk (no truncation; fail-loud at a sanity bound). `--real`
  is spend-gated; Claude does not self-authorize spend.

## Honest scope / residual (non-blocking)
- Two methods wired (floor + one closed-loop); the other frontier scaffolds in `brief.md` are drop-in
  adapters still to add — same harness.
- Coverage signal = POLARIS generator-visible evidence (title+statement+grounding span), labeled
  explicitly; switching to full-fetched-body coverage is a one-field change.
- Codex P2s (future-adapter schema-constraint; wire `build_lineage_manifest` into sweep emission) are
  observability hardening, captured as follow-ups — not execution blockers.

## Iteration trajectory (Codex = the only gate)
iter1: 7 P1 (all real) → fixed. iter2: 1 new + 1 continuing P1 (blocked-ref + judge truncation) → fixed.
iter3: 1 P1 — an empirical field-path MISREAD; rebutted with gold-file ground truth (verified 3 ways)
+ loader hardened. iter4: clean APPROVE — Codex re-checked the gold file and confirmed the rebuttal.

## Acceptance
Harness BEHAVIORALLY proven on stubs + real rubrics: closed-loop out-covers floor (ranking fires);
blocked row dropped, blocked-only point stays uncovered; judge fails loud instead of truncating; the
real gold loader returns idx-56's 57 required points + the Salari blocked dict. The actual SCORED run
needs operator spend authorization (`PG_QGEN_AUTHORIZED_SPEND=1`).
