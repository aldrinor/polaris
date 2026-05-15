# Codex review — POLARIS Carney demo execution plan

**Type:** PLANNING REVIEW. Codex already did the readiness gap analysis
(`.codex/carney-readiness-gap-analysis/`). Claude then built a 9-phase
execution plan FROM that gap analysis. The operator asked: "did Codex verify
this plan?" — it has not. This consult is that verification.

## §0. Front-load everything
- Single round. Surface ALL findings now. No drip-feeding.
- Reserve P0/P1 for things that genuinely make the plan wrong or unexecutable.

## §0.1 OPERATOR-LOCKED — constraints, not options. Do NOT reopen:
- Generator = DeepSeek V4 Pro (1.6T MoE); Evaluator = Gemma 4 31B; 1 concurrent session.
- Canadian sovereign GPU only (no OVH-Canada Hopper exists; no France; no US). Vexxhost + ISAIC outreach sent.
- Architecture = deployed v6 stack (redis+api+worker+webui). No rewrites.
- "BPEI" name banned — rename all 407 files to `ambiguity_detector`.
- Demo: single venue, PM Carney's office, flexible June 2026 date.
- Stick to the Carney plan (`docs/carney_delivery_plan_v6_2.md`) — no new features.

## §1. What to review

Read these two files in the repo:
- `state/carney_demo_execution_plan_2026_05_15.md` — the 9-phase plan to verify.
- `state/carney_readiness_gaps_2026_05_15.md` — the gap register the plan is built from (your own prior findings synthesised by Claude).

Cross-reference against `docs/carney_delivery_plan_v6_2.md` (the mission/feature spec) as needed.

## §2. Questions

1. **Coverage:** does the 9-phase plan address EVERY P0 and P1 from the gap analysis? Name any gap finding that the plan does not actually close.
2. **Sequencing:** is the phase order correct? Are there dependency errors — anything sequenced before a thing it depends on, or parallelizable work needlessly serialized?
3. **The GPU-blocked split:** the plan claims Phases 0-5 need no GPU and only Phases 6-9 do. Verify this. Is anything marked "[no GPU]" that actually needs the GPU, or vice versa?
4. **Effort estimates:** Phase 3 (P0 integration) is estimated ~8-12 working days; total Claude-side ~3 weeks. Sane, optimistic, or pessimistic — given the integration work described?
5. **Completeness:** what is MISSING from the plan entirely — a phase, a task, a dependency, a risk, a decision gate that should be there and is not?
6. **The lock doc (Phase 0):** is writing the lock doc first the right move, or should anything precede it?
7. **Realism of the timeline** vs a flexible-June demo.
8. **Anything in the plan that is wrong** — a factual error, a bad assumption, an over-claim.

## §3. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
coverage_gaps: [<gap-analysis P0/P1 items the plan fails to close>]
sequencing_errors: [...]
gpu_split_errors: [...]
effort_estimate_assessment: <text>
missing_from_plan: [...]
factual_errors: [...]
recommended_changes: [<concrete edits to the plan>]
verdict_reasoning: <text>
```

Do NOT propose new features or architecture rewrites. Verify the plan as a plan.
