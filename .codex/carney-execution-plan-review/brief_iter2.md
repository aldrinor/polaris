# Codex review iter 2 — POLARIS Carney execution plan v2

**Type:** PLANNING REVIEW, iter 2 of 5. You reviewed v1 and returned
REQUEST_CHANGES. Claude revised the plan to v2, applying every item in your
`recommended_changes`. Verify v2 is now correct and executable.

## §0. Front-load. Single round mindset. Reserve P0/P1 for real plan defects.

## §0.1 OPERATOR-LOCKED — constraints, do NOT reopen:
- Generator = DeepSeek V4 Pro (1.6T MoE); Evaluator = Gemma 4 31B; 1 concurrent session.
- Canadian sovereign GPU only (no OVH-Canada Hopper; no France; no US).
- Architecture = deployed v6 stack. No rewrites. "BPEI" banned (rename to ambiguity_detector).
- Demo: single venue, PM Carney, flexible June date. No new features beyond docs/carney_delivery_plan_v6_2.md.

## §1. What changed v1 → v2 (your iter-1 recommended_changes, all applied)
- Phase 0 split into 0A (lock constraints) + 0B (pin verified statuses after Phase 1).
- Phase 1 expanded to verify schedule-affecting P1s (cancel/resume, memory, sovereignty/log-redaction call sites, bundle signing, hardening states).
- Phase 3 step 4 rewritten as a live-run artifact contract; step 5 requires live run IDs for inspector/charts/follow-up/compare/pin-replay/memory/bundle. Added explicit Phase 3 issues: ambiguity_detector product wiring, artifact-contract mapping, cancellation/resume implementation, durable workspace memory, live pin replay, 1-concurrent-session queue/rejection UX.
- New parallel "Workstream L" — no-GPU demo logistics (TLS, backup, legal notice, source cache, runbook+owner, fallback prep, GPG/clean-machine criteria) starting after Phase 2.
- Phase 4 adds the OpenRouter evidence package; exit reworded to "non-sovereign rehearsal path passes" (no longer "complete product works").
- Phase 5 restructured staged: 5a author during Phase 3 / 5b run after 3-4 / 5c sovereign regression after Phase 7.
- Phase 7 expanded to full sovereign regression (LLM path, egress, log redaction, GPG signing + clean-machine verify, two-family re-verify, key removal).
- Estimates revised: Phase 3 = 12-18 working days; Claude-side total optimistic ~3.5wk / conservative 4-5wk; late-June/early-July risk called out.
- Factual overclaims fixed: "no GPU" reworded to "buildable/prevalidatable without GPU, final sovereign gates close after cutover"; one-env-var swap marked "to be verified."

## §2. Review `state/carney_demo_execution_plan_2026_05_15.md` (v2). Confirm:
1. Every iter-1 recommended_change is correctly incorporated.
2. No NEW sequencing/coverage/GPU-split error introduced by the revision.
3. The plan is now executable as written.
4. Any residual P0/P1 plan defect.

## §3. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
iter1_changes_correctly_applied: yes | no | partial
residual_defects: [...]
new_issues_introduced: [...]
verdict_reasoning: <text>
```
