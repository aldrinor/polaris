# Codex review brief — v5.1 redline verification

**Model expectation:** gpt-5.5, xhigh reasoning. Verification pass on the v5 redline.

**Your role:** verify v5.1 actually addressed all your v5 RED findings, did NOT introduce new failure modes, and is now sprint-startable. Be the loyal reviewer the user described — find what's still wrong.

**Word budget:** ~1500 words. No code.

---

## Context

You returned **RED** on v5 with 17 specific issues. v5.1 is the surgical redline you recommended (not a full v6). Read `docs/carney_delivery_plan_v5_1_redline.md` first.

## What changed in v5.1

Brief summary of fixes:

1. **Hardware claims pinned** — V4 Pro on H200 capped at 800K context with 8 GPU; full 1M needs 16 GPU. Phase 0 task 0.6 commits choice (FP4 8-GPU OR FP8 16-GPU).
2. **Engine choice fixed** — Phase 0 SGLang vs vLLM bakeoff with measured criteria; ONE engine frozen, no fallback.
3. **Gemma 4 verified in Phase 0** — official model card + license + serving recipe required before Phase 1.
4. **shadcn/ui license corrected** — MIT (not Apache 2.0).
5. **FastAPI version corrected** — 0.136.x (not 0.98+).
6. **ARQ replaced with Dramatiq** — ARQ is maintenance-only; Dramatiq is async-friendly + actively maintained + supports cancel/retry/scheduling/durable state.
7. **OTel GenAI semconv corrected** — status Development, used as opt-in with `gen_ai.experimental=true` flag, version-pinned.
8. **MiroThinker** — architecture-only adoption, no fork, license scan first.
9. **Codex Red-Team Checklist** added (fixed independent of Claude's brief): diff, tests, recordings, trace IDs, corpus outputs, doc manifest.
10. **Doc updates as structured manifest JSON** (task_id, changed_files, test_commands, artifacts, recordings, trace_ids, open_bugs, evidence_links) — not prose-only.
11. **Escalation rules refined**: same P1 twice = escalate; changed acceptance criterion = RED; >150% estimate = escalate.
12. **Layer 3 walkthroughs within 48h of any user-flow task GREEN** — not just end-of-phase.
13. **Phase 0 timing** — 5-8 business days (was 3 calendar days).
14. **Ambiguity detector scoped narrow** — retrieval-clustering + 50-term locked corpus.
15. **Task 1.4 → Evidence Contract Gate (THE ONE FIX you specified)** — full schema spec, blocks all Phase 2 crown jewel work until GREEN. Schema includes claims with `ungated` flag, evidence_spans with retrieval_trace, sources with admissibility_decision, contradictions with PT08 disclosure, frame_coverage with gap_reason, refusal with gate/threshold/actual/unblock_action, trace_id, bundle_ref.
16. **Phase 2 split** — Task 2.6 → 4 sub-tasks (sandbox/provenance/reproducibility/UI); Task 2.7 → 2 sub-tasks (bundle/legal). Phase 2 timeline 4→5 weeks.
17. **Task 2.9 UX contract** — must answer 5 specific user questions visibly, raw event log not acceptable.
18. **Phase 3 evaluator hours realistic** — 1,200 scoring decisions = 100-150 hours = $25k.
19. **OVH Canada BHS H200 verification moved to Phase 0** (was Phase 4).
20. **Phase 4.5 buffer week added** — total 14 weeks (was 13).
21. **Budget revised** — $112k total (was $45k). Concentrated in Phase 3-5 evaluator/compute.
22. **Sycophancy + refusal CI from Week 1** — paired-prompt suite (neutral/leading/opposite-frame) running on every commit.

## What I want you to verify

### Verification checks

For each of your v5 findings, evaluate v5.1's fix:
- Closed (adequately addressed)
- Partial (gap remaining; specify)
- Reopened (revision introduces new version of same problem)
- Unaddressed (still a finding)

Specific items to check:
1. Did the hardware redline correctly capture the FP4-8GPU vs FP8-16GPU trade-off?
2. Is "Phase 0 bakeoff choosing one engine" actually enforceable, or could it slip?
3. Is the Evidence Contract Gate spec rigorous enough to prevent vague crown-jewel UI work in Phase 2?
4. Is the Codex Red-Team Checklist + structured doc manifest enough to prevent ceremony?
5. Are the escalation rules ("same P1 twice", ">150% estimate", changed-criterion = RED) implementable in practice or hand-wavy?
6. Does the Phase 2 split (11 → 14 tasks, 4 → 5 weeks) actually fit, or is it still overpacked?
7. Is Task 2.9's "5 user questions visible" UX contract enough to prevent telemetry-dump phantom?
8. Is the Phase 3 evaluator-hours math now realistic at 100-150 hours / $25k?
9. Is moving OVH Canada BHS H200 verification to Phase 0 sufficient, or is the backup path (DRAC, Bell, etc.) too unspecified?
10. Is Phase 4.5 buffer enough, or does Phase 5 still risk no-buffer collapse?
11. Does the budget at $112k now match reality?

### New failure modes introduced?

The v5.1 redline added 22 changes. Find anywhere a fix introduces a new failure:
- Did splitting Task 2.6 into 4 sub-tasks create coordination overhead?
- Does the structured doc manifest become its own ceremony?
- Does Dramatiq vs Celery decision risk being made wrong?
- Does the sycophancy CI suite require its own maintenance overhead I didn't budget?
- Does Phase 0 with 10 tasks become a planning-fest before any product code?

### Phantom completion residue

Check the redline still has phantom-completion vulnerabilities:
1. "Phase 0 cannot end until all 10 tasks GREEN" — same risk as v3/v4 of "GREEN" being undefined per task. Required fix?
2. "Layer 3 walkthrough within 48h of user-flow task GREEN" — who enforces if 48h elapses with no walkthrough? What's the consequence?
3. "Codex Red-Team Checklist" — is the checklist itself defined in v5.1 well enough, or does it need its own document?

### Big picture — odds and final verdict

Your v5 odds: 40-45% as-written, 65-70% with redline.
v5.1 IS the redline. Final odds estimate?

Verdict options:
- **GREEN**: v5.1 is sprint-startable conditional on user committing budget + blockers. Phase 0 begins.
- **YELLOW**: small further redline needed (specify which lines), then start.
- **RED**: still not safe to start; identify the structural issue.

## Output structure

- A. Per-finding verification (closed/partial/reopened/unaddressed for each of v5's 17+ findings)
- B. New failure modes
- C. Phantom completion residue
- D. Budget realism check
- E. The single most important remaining issue (or "none, GREEN")
- F. Verdict + recommendation

## Constraints

- Brutal as before.
- If GREEN: state explicitly so we can commit blockers and start Phase 0.
- If YELLOW: name specific lines to fix.
- If RED: name the structural issue and what would need to change.
- Don't soften.

The user is reading your response and will use it to decide whether to commit budget + blockers and start Phase 0 tomorrow.
