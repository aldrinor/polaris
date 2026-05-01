# Codex final verification — Carney Delivery Plan FINAL

**Model:** gpt-5.5, xhigh reasoning. Final verification pass.

**Your role:** loyal reviewer. The user wants this plan to be sprint-startable with zero deviation. Find anything still wrong; if nothing structural remains, return GREEN.

**Word budget:** ~1200 words.

---

## Trajectory

- v5 (May 1): RED — 17 findings
- v5.1 (May 1): YELLOW — surgical redline, residuals on hardware/checklist/per-task GREEN
- v5.2 (May 1): redline applied — Codex Red-Team Checklist + task acceptance matrix created, hardware path made decision-gated, OVH backup paths made executable
- **FINAL (May 1, this version)**: consolidates v5/v5.1/v5.2 + integrates all user decisions

## What changed from v5.2 to FINAL

User-driven decisions that locked or shifted scope:

1. **Templates: 3 → 8** — covering all 7 of Carney's officially-named priorities (verified May 2026 search) + healthcare baseline
   - Existing: clinical_tirzepatide_t2dm
   - New: trade & tariff impact / housing & productivity / defense & Arctic / climate & energy / AI & tech sovereignty / Canada-US partnership / skilled trades & workforce
   - Templates 1-3 lock Phase 0; templates 4-8 added incrementally Phases 2-3 (1-2 weeks content work each)

2. **Layer 3 evaluator: paid contractor → user during build phase** — Carney's office is final acceptance gate. User has authority + domain literacy + budget control. Codex's preference (paid independent reviewer) overridden by user choice. Optional: 1 paid sample evaluator for Phase 3 benchmark legitimacy ($3-8k).

3. **Build phase compute: self-host → DeepSeek API for V4 Pro testing** — sovereignty deferred to benchmark+demo phases when handling real Canadian data. Build queries are synthetic/public, no sovereignty concern. Saves ~$10-20k.

4. **On-demand spin-up everywhere** — no always-on cluster except Phase 5 warm pool. Saves ~$30-35k. GPUs OFF by default.

5. **Budget revised**: $170-210k → **$25-55k realistic ceiling** (expected midpoint ~$35-40k)

6. **Phase 1 task added: Sycophancy + refusal CI suite** (Task 1.6) — paired-prompt evaluations (neutral/leading/opposite-frame) in CI from Week 1. Operationalizes "non-sycophantic" claim.

## What stayed from v5.2

- Tech stack (DeepSeek V4 family + Gemma 4 + SGLang/vLLM bakeoff + Next.js 15/React 19/shadcn-ui-MIT/Tailwind v4 + FastAPI 0.136.x + Pydantic v2 + Dramatiq + OpenTelemetry semconv 1.30.0-dev pinned)
- Codex Red-Team Checklist (`.codex/codex_red_team_checklist.md`) — fixed adversarial checklist independent of Claude's task brief
- Per-task acceptance matrix (`docs/task_acceptance_matrix.yaml`)
- Evidence Contract Gate (Task 1.4) blocks Phase 2 crown jewel work
- 14-week timeline with Phase 4.5 buffer
- Hardware Path A/B/C decision in Phase 0 (default C)
- OVH BHS H200 verification as Phase 0 hard gate with executable backup procurement
- Per-task documentation manifest schema
- Escalation rules (same P1 twice = escalate; mid-task criterion change = RED; 48h no walkthrough = BLOCKED)

## What I want you to verify

### A. Are user decisions correctly integrated?

For each decision (templates, Layer 3, build-phase API, on-demand, budget):
- Coherent with rest of plan?
- Risk reintroduced where v5.2 had closed?
- New phantom-completion vulnerability?

### B. Is the budget realistic for the scope?

The plan says $25-55k for 14 weeks of work resulting in:
- 8 templates × full content design + eval sets
- All 10 crown jewels surfaced in browser
- 50-question benchmark across 4 systems × 6 dimensions = 1,200 scoring decisions (most done by user, optionally 1 paid sample for legitimacy)
- Sovereign Canadian deployment migration + Carney demo period
- Full handover package

Is $25-55k credible for this scope, or did the user-driven cuts (no paid evaluators, build-phase API, on-demand) push it past the point where quality risk emerges?

### C. Is "user as Layer 3" honestly defensible?

Codex previously said paid independent evaluator was non-negotiable. User chose otherwise. Three concerns:
1. Independence: user has commercial interest in shipping; can they fairly fail their own walkthroughs?
2. Coverage: 8 templates × multiple flows × adversarial inputs = a lot of walkthrough hours; can user genuinely do this volume?
3. Audit-trail credibility: when Carney's office asks "who validated this works?", "the builder validated themselves" weakens the proof package. Is this a real risk for the handover credibility?

If concerns are real: should plan add a mandatory "1 paid sample evaluator for Phase 3 benchmark" as non-negotiable, not optional?

### D. Phantom completion residue

Specific items that may still hide phantom completion:
1. "On-demand spin-up everywhere" — under deadline pressure, easier to just leave it on. Mitigation in plan?
2. "Templates 4-8 added incrementally Phases 2-3" — sounds light but each template needs scope/examples/source policy/eval set. 5 templates × 1-2 weeks = 5-10 weeks; doesn't fit Phases 2-3. Realistic?
3. "Build phase API" — is the boundary "synthetic/public dev queries OK on API; real Canadian data NEVER on API" clearly enforceable in code, or does sensitive data leak to API by accident?

### E. Final verdict

- **GREEN**: plan is sprint-startable; Phase 0 begins; auto-loop runs through Phase 5
- **YELLOW**: small specific redlines needed before start (name them)
- **RED**: structural issue requiring revision (name it)

User's instruction is "no deviation, no fallback during execution." If GREEN, this plan executes without further mid-build re-planning. So GREEN must mean "I genuinely believe this can be built as-written without surprise rework."

## Output structure

- A through D: numbered specific responses, quote plan when attacking
- E: GREEN / YELLOW / RED with specific recommendation
- Final paragraph: odds estimate (was 60-65% on v5.1, 68-72% with v5.2 redline)

## Constraints

- Brutal honesty.
- If GREEN: state it explicitly so user can commit and start.
- If YELLOW: name surgical redline lines.
- If RED: name structural issue.
- Don't soften.
