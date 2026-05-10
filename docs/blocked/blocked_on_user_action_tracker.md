# Blocked-on-user-action tracker

**Status as of 2026-05-10.** Single tracker for 15 GitHub issues that
cannot land via autonomous Claude-Codex protocol because they need
user procurement, hardware delivery, sovereign-migration validation,
or final-phase deliverables that depend on a finished pipeline:
7 Phase 0 hardware/license + 4 sovereign migration + 1 buffer +
3 handover.

Per CLAUDE.md §-1.2 standard debug workflow: rather than ship synthetic
placeholder PRs, this tracker captures **what's needed from user**,
**what Claude has already scaffolded**, and **exit criteria** for
each. When user provides the unblocking action, the tracker points
to the next concrete step.

---

## Phase 0 — Hardware procurement (7 issues)

### I-phase0-003 (#85): Vast.ai US dev cluster operational

**Needed from user:** account credentials + budget commit. Carney v6.2
Phase 0 Task 0.3.

**Already scaffolded by Claude:** none yet — bootstrap script will
ship as a follow-up PR once user provides credentials.

**Exit criteria:** ssh into cluster + run nvidia-smi + see GPU.

### I-phase0-005 (#86): Backend modernization + Dramatiq queue

**Needed from user:** dev cluster credentials (depends on I-phase0-003).

**Already scaffolded by Claude:** Dramatiq queue substrate landed in
prior work; acceptance test exists at `tests/v6/test_dramatiq_queue.py`.

**Exit criteria:** `pytest tests/v6/test_dramatiq_queue.py --live`
passes against the dev cluster.

### I-phase0-006 (#87): DeepSeek V4 hardware Path A/B/C decision

**Needed from user:** decision among:
- **Path A:** OVH Canada BHS H200 (8x H200, full sovereign)
- **Path B:** Vast.ai burst (US/EU jurisdiction)
- **Path C:** Nebius EU (mid-cost, EU jurisdiction)

Per memory `feedback_no_cost_mentions.md`: rank by quality bench
(HHEM, MMLU, RAG-faithfulness, family diversity), drop cost columns
unless user asks.

**Already scaffolded by Claude:** None — pure user decision; Claude
will implement deployment scripts targeting whichever path is chosen.

**Exit criteria:** decision logged in `state/polaris_restart/hardware_decision.md`.

### I-phase0-007 (#88): SGLang vs vLLM bakeoff

**Needed from user:** approval to spend ~$50 on bakeoff (deploy both,
benchmark same model on both, pick winner).

**Already scaffolded:** harness pattern (`scripts/aggregate_beat_both_runs.py`
adapts; bakeoff is a wrapper that runs both inference engines on
the goldset).

**Exit criteria:** winner selected + recorded in `state/polaris_restart/inference_engine_decision.md`.

### I-phase0-008 (#89): Gemma 4 31B technical verification

**Needed from user:** download + spin up locally (40GB VRAM minimum)
OR depend on hardware procurement (I-phase0-009).

**Already scaffolded by Claude:** `scripts/run_entailment_fpr_audit.py`
(I-bug-101 PR) is ready to invoke against any local Gemma 4 endpoint.

**Exit criteria:** FPR audit produces same verdict distribution as
OpenRouter Gemma 4 31B (within 5% drift).

### I-phase0-009 (#90): OVH Canada BHS H200 invoice + provisioning (HARD GATE)

**Needed from user:** **BLOCKING** for sovereign migration (I-sov-*)
and Carney Phase 4. Carney v6.2 Phase 0 Task 0.9.
- OVH account creation + verification
- Sovereign-Canada region selection (BHS-1)
- 8x H200 GPU server provisioning
- Invoice acceptance
- Network / VPN setup

**Already scaffolded by Claude:** None — pure procurement; deployment
scripts will follow once hardware exists.

**Exit criteria:** `ssh root@bhs-h200-1.polaris-sovereign.ca` succeeds.

### I-phase0-010 (#91): Gemma 4 31B license sign-off

**Needed from user:** legal review of Gemma 4 license (Apache 2.0 +
Gemma Use Policy) for Carney delivery scope. Per memory
`v6_phase_0_errata_otel_gemma.md`: LOW severity for Carney scope but
needs explicit sign-off for sovereign deployment.

**Already scaffolded by Claude:** None — pure legal review.

**Exit criteria:** sign-off logged in `docs/legal/gemma_license_review.md`.

---

## Sovereign migration (4 issues — depend on I-phase0-009)

### I-sov-001 (#199): Replace OpenRouter with sovereign vLLM

**Needed from user:** I-phase0-009 (OVH H200 provisioning) complete.

**Already scaffolded by Claude:** entailment_judge.py (I-bug-099) +
cost-tracking via openrouter_client (I-bug-100); sovereign vLLM swap
is changing the endpoint URL + updating model name in
`_DEFAULT_ENTAILMENT_MODEL` and `OPENROUTER_DEFAULT_MODEL` env vars.

**Exit criteria:** smoke run with PG_ENTAILMENT_ENDPOINT pointing
at the OVH cluster passes 4/4 audit-derived cases (same as I-bug-094
canary did against OpenRouter).

### I-sov-002 (#200): Validate quality unchanged on sovereign topology

**Needed from user:** I-sov-001 complete.

**Already scaffolded by Claude:** `scripts/run_line_by_line_audit.py`
(I-bakeoff-A-001 PR) is ready to run on sovereign output.

**Exit criteria:** verdict-count delta < 5% across all 5 Carney
goldset questions when comparing sovereign vs OpenRouter baseline
via line-by-line audit per CLAUDE.md §-1.1.

### I-sov-003 (#201): Re-run F-INT regression suite on sovereign topology

**Needed from user:** I-sov-001 + I-sov-002 complete.

**Already scaffolded by Claude:** F-INT integration suite exists at
`tests/integration/`; cost-ledger plumbing landed via I-bug-100.

**Exit criteria:** all F-INT tests pass + cost-ledger entries write
correctly via I-bug-100 plumbing.

### I-sov-004 (#202): Two-family segregation re-verification

**Needed from user:** I-sov-001 complete.

**Already scaffolded by Claude:** `check_family_segregation` enforced
in `_EntailmentJudge.__init__` (entailment_judge.py); just need to
re-run with sovereign endpoint config.

**Exit criteria:** `_EntailmentJudge.__init__` succeeds on the
sovereign config (DeepSeek V4 generator + Gemma 4 31B evaluator,
both on OVH) without raising RuntimeError.

---

## Phase 4.5 buffer (1 issue)

### I-buf-001 (#203): Migration findings + regression fixes

**Needed from user:** I-sov-001 through I-sov-004 complete.

**Already scaffolded by Claude:** None (regression fixes are
condition-dependent — no scope until sovereign migration surfaces
findings).

**Exit criteria:** all sovereign-introduced regressions fixed; F-INT
green; line-by-line audit ACCEPT verdict on Carney goldset.

---

## Phase 5 handover (3 issues)

### I-hand-001 (#204): Final walkthrough + Codex sweep

**Needed from user:** I-buf-001 done.

**Already scaffolded by Claude:** All deliverables shipped (20 PRs
this autonomous session: I-bug-093 through I-bench-002 + I-tpl-006/7/8
+ I-decompose-001 + I-doc-001/002 + standards in CLAUDE.md §-1).
Codex sweep just runs against the full repo.

**Exit criteria:** Codex APPROVE on `Carney delivery readiness checklist`.

### I-hand-002 (#205): Handover package

**Needed from user:** I-hand-001 done.

**Already scaffolded by Claude:** Documentation surface exists across
docs/runbook.md, docs/file_directory.md, audit-bundle export
procedures (I-f15-* series), license disclosures pending procurement
review.

**Exit criteria:** Carney's office can independently reproduce a
research run end-to-end from the handover package alone.

### I-hand-003 (#206): Carney office demo

**Needed from user:** I-hand-002 done + scheduling with Carney team.

**Already scaffolded by Claude:** Pipeline ready end-to-end (BPEI →
retrieval → generation → strict_verify → bundle export → line-by-line
audit). Live demo just runs the pipeline against a Carney-priority
question.

**Exit criteria:** Carney's research team signs off on production
readiness; POLARIS deemed delivered.

---

## What Claude WILL do without further user action

If the user provides any of the unblocking signals above (e.g., OVH
provisioning email, Vast.ai credentials, Gemma license sign-off),
Claude can immediately resume the dependent issue chain. The next
concrete step is documented in each section's "Exit criteria" line.

**Deliverables already shipped that unblock these tasks:**
- `scripts/run_line_by_line_audit.py` (I-bakeoff-A-001) → used by I-sov-002
- `scripts/run_entailment_fpr_audit.py` (I-bug-101) → used by I-phase0-008
- `scripts/run_paid_evaluator_scoring.py` (I-bench-002) → used in handover audit
- `scripts/aggregate_beat_both_runs.py` (I-bug-107) → used by I-sov-003 regression
- `polaris_graph.llm.entailment_judge` (I-bug-099 + I-bug-100) → used by I-sov-001
- `polaris_graph.decomposer` (I-decompose-001) → available for complex Carney questions
- `config/scope_templates/{ai_sovereignty,canada_us,workforce}.yaml` (I-tpl-006/7/8) → ready for Carney research questions

This tracker is the SINGLE source of truth for blocked-on-user-action
state. When state changes, update this file rather than scattering
status across 11 individual issue threads.
