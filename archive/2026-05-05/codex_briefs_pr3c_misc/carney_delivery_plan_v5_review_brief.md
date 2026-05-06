# Codex review brief — Carney Delivery Plan v5

**Model expectation:** gpt-5.5, xhigh reasoning. This is the most important review yet.

**Your role:** loyal adversarial reviewer of the comprehensive plan. The user has explicitly asked Codex to be the disciplined gate at every task — your job is to find what's wrong with the plan now, before execution starts. Once execution starts, you'll review every task. So this plan review needs to leave nothing missing.

**Word budget:** ~2500 words. No code.

---

## What the user asked for

Direct quote: *"work it out with codex, and give me a complete and full plan, from today, to the point that we can deliver to Mark Carney, I hope Claude and Codex can form a highly efficient and effective loop to help each others, to work out the plan, then build it according to the plan, for everything... I want Codex can be your loyal reviewer, to help you to pick up all problem on the early stage for every single task, and keep the auto loop moving, until full build... I don't want to have diveration and fallback during execution, all doc like task, todo, handover, memory, plan, directory shall be updated after every single task completed, and also Github."*

The user explicitly wants:
1. Complete plan from today (May 1, 2026) to Carney handover
2. Latest-practices grounding (we just searched May 2026 best practices)
3. Tight Codex↔Claude loop, with Codex catching every issue at every task
4. Auto-loop progression — no human intervention except hard stops
5. Mandatory doc updates per task (todo, handover, memory, plan, directory + GitHub)
6. No deviation, no fallback during execution

## What I built

Read `docs/carney_delivery_plan_v5_draft.md` first.

Brief summary:
- **Tech stack** anchored to May 2026 research: Next.js 15 + React 19 + shadcn/ui + Tailwind v4 frontend; FastAPI + ARQ + Redis backend; SGLang serving DeepSeek V4 Pro (8× H200 cluster) + Gemma 4 31B (1× H100); MiroThinker-style verification-centric agent (Local + Global verifier); OpenTelemetry distributed tracing
- **All 10 crown jewels** in scope (not 4-flow MVP)
- **5 phases** over 13 weeks (May 1 → July 26): Foundation (3 days) → BPEI spine (3 weeks) → Crown jewels (4 weeks) → Benchmark proof (3 weeks) → Sovereign deployment (2 weeks) → Carney handover (1 week)
- **Per-task Codex loop** with mandatory doc updates and GitHub workflow
- **Layer 3 evaluator** real Canadian buyer-workflow-literate person with fail authority
- **Hardware**: Vast.ai US for build phase, OVH Canada Beauharnois H200 confirmed available for sovereign demo
- **Total budget**: ~$45k for 13 weeks (compute + evaluators + legal + ops)

## What I want you to attack — by section

### A. Tech stack realism (is the May 2026 research correctly applied?)

I anchored to research findings on:
- **DeepSeek V4 Pro**: 1.6T MoE, 49B active, MIT, requires ~960 GB mixed-precision = **8× H200 cluster**
- **SGLang as default**: 29% throughput advantage on H100, used by xAI Grok 3, Microsoft, LinkedIn
- **Gemma 4 31B**: Apache 2.0, beats Llama 4 Scout by 10pts on GPQA Diamond
- **Next.js 15 + React 19**: Server Components, Server Actions, 40% Core Web Vitals improvement
- **shadcn/ui + Tailwind v4**: dominant 2026 UI stack; vendored components no lock-in
- **MiroThinker-H1**: 88.2 BrowseComp (vs GPT-5.5 Pro 90.1) using Local + Global verifiers
- **ARQ + Redis** over Celery (async-first)
- **OpenTelemetry GenAI semantic conventions** (stable early 2026)

Questions:
1. For each stack choice, identify any overlooked alternative or risk: e.g., is there a 2026 release I missed? Does the V4 Pro hardware footprint estimate match reality? Is SGLang v0.3.x stable enough for production deployment?
2. The plan keeps existing POLARIS Python substrate but rebuilds frontend in Next.js. Is this the right port boundary, or should we also migrate backend to a more modern Python framework?
3. The plan adopts MiroThinker's verification pattern but doesn't say whether to fork MiroThinker code or just reuse the architecture pattern. What's the right call given license + maintenance trade-offs?

### B. Loop discipline — is it actually enforceable?

The plan defines:
- Per-task Codex review with GREEN/YELLOW/RED verdict
- YELLOW = fix before next task, max 3 cycles before escalation
- RED = full halt, escalate to user
- Mandatory doc updates (todo, file_directory, plan, session_log, restart_instructions, handover, memory + GitHub commit/PR)
- Codex review checks doc updates as part of verdict

Questions:
1. The "no deviation, no fallback" rule + auto-loop progression risks Codex becoming a bottleneck or rubber stamp under deadline pressure. How would you enforce that Codex review is genuinely adversarial each cycle, not formulaic?
2. "Max 3 YELLOW cycles before escalation" — is 3 the right number? Could be too lenient (stuck in fix loops) or too strict (escalating on minor things). What's a better stopping rule?
3. The plan says Layer 3 walkthroughs happen at end-of-phase. The previous v4 review pointed out that's too late — week 5+ is too late for first human contact. Plan v5 schedules walkthroughs at end of Phase 1 (Week 3) and end of Phase 2 (Week 7). Is this enough? Or should Layer 3 walkthrough happen on every task that touches a user flow, not just end-of-phase?
4. Documentation discipline: the plan says "Codex review checks doc updates as part of the verdict." Concretely, what does Codex inspect? File diff? Specific keywords? How do we prevent doc updates from becoming theater?

### C. Phase-by-phase risk hunt

Phase 0 (Days 1-3): blockers + MiroThinker analysis + dev cluster + frontend scaffold + OpenTelemetry. Five tasks in 3 days.
- Q: Is this actually 3 days of work, or 5+ days of work compressed?
- Q: What's the most likely thing to slip in Phase 0?

Phase 1 (Weeks 1-3): scope discovery + ambiguity detector + refusal view + minimum viable report rendering + job queue + walkthrough. Six tasks in 3 weeks.
- Q: The ambiguity detector is NEW substrate (didn't exist in POLARIS). Realistic to design + build + tune + integrate in Week 1 alongside Flow 1?
- Q: "Minimum viable report rendering" is the same hand-wave as v3/v4. What's the concrete spec? If it's not concrete, this task carries the "Sprint 1 dead-end" risk again.

Phase 2 (Weeks 4-7): 11 tasks (10 crown jewels + walkthrough) in 4 weeks. ~2.5 tasks per week.
- Q: Each crown jewel surfacing is non-trivial UI work. Tasks 2.6 (Python execution + chart rendering) and 2.7 (audit bundle + legal review) are particularly heavy. Are they really one-task-each?
- Q: Task 2.9 (live audit run UI consuming SSE) — Codex previously warned this would degrade into a telemetry dump under deadline pressure. Did the plan address that, or just rebrand?

Phase 3 (Weeks 8-10): 50-question benchmark, run on 4 systems, 6-dimension scoring, sycophancy stress-test, leaderboard run, proof package. Six tasks in 3 weeks.
- Q: 50 questions × 4 systems = 200 runs. At ~10 min each = 33 hours of compute + scoring time. Realistic in Phase 3 alone, with evaluator scoring time included?
- Q: "Sycophancy stress-test" is a clean concept but the test design is hard. How would you operationalize it?

Phase 4 (Weeks 11-12): OVH Canada migration + auto-scale + benchmark re-run. Five tasks in 2 weeks.
- Q: Sovereign hardware migration is famously painful. fp8 quality differences, batching tuning, network config, KV cache sizing. Realistic in 2 weeks?
- Q: If OVH Canada doesn't actually have 8× H200 inventory in BHS when needed, what's the contingency? Plan v5 doesn't specify.

Phase 5 (Week 13): final walkthrough + Codex sweep + handover package + execute handover. Four tasks in 1 week.
- Q: If anything fails in this last week, there's zero buffer. v4 had a "Sprint 4 buffer" — v5 does not. Should we restore it?

### D. Phantom completion — where's it hiding in v5?

Each prior plan version had phantom completion lurking. Find it in v5.

Specifically:
1. Acceptance criteria: "all input classes pass: supported, unsupported, ambiguous, failing." Same potentially-vacuous condition as before. How tightened?
2. "Codex review checks doc updates as part of the verdict" — tells the verifier to verify itself. Is this circular?
3. "Auto-resume when conditions clear" — risk of conditions appearing-clear without being-clear (e.g., evaluator says fine but recording shows a real issue). Mitigation?
4. The 10 crown jewels are surfaced via 11 tasks in Phase 2. The risk: one of them — likely the live audit, the Python execution charts, or the source admissibility tree — quietly becomes a hand-wave under pressure. Which is most likely to phantom-complete and how to defend against it?

### E. Budget and timeline

Total budget $45k for 13 weeks. The biggest line items:
- Phase 4: $9k (sovereign cluster migration + validation, including 8× H200 OVH Canada at high $/hr)
- Phase 3: $10k (benchmark scoring evaluator hours)
- Evaluator hours total: $24k (across 13 weeks, ~$1850/week)

Questions:
1. $24k for evaluator hours across 13 weeks at $200-500/hr = 50-120 hours total. Is that enough for 3 evaluators × multiple walkthroughs × 50-question scoring? My math says it's tight.
2. The plan doesn't include any sales/relationship cost for getting Layer 3 evaluators contracted. Realistic cost of finding + contracting + onboarding 3 buyer-workflow-literate Canadian evaluators?
3. Sovereign hardware compute on OVH Canada: estimated $5k for migration + validation (Phase 4) + $3k for Carney demo (Phase 5). 8× H200 at OVH Canada pricing — is this realistic? OVH H100 is $4.05/hr; H200 typically 1.5-2× H100. So 8× H200 ≈ $50-65/hr × 24/7 for two weeks = $17-22k. Plan budget significantly underestimates Phase 4-5 compute.

### F. The two unknowns I haven't resolved

1. **OVH Canada H200 actual availability in BHS region**: their public page says H200 is available, but doesn't break down by region. If BHS has H100 only, the sovereign deployment compute is different (cost + capability).
2. **MiroThinker license + adoption strategy**: I propose adopting MiroThinker's verification architecture but didn't specify whether we fork their code, build our own from the architecture pattern, or use their hosted model variant. Each has different IP and operational implications.

How would you resolve these in the plan, vs leave them as Phase 0 verifications?

### G. Hostile big-picture attack

After section-by-section: step back.

1. If Carney's office actually receives this in 13 weeks, what's the most likely failure they'd encounter on first day-of-handover use?
2. The 4-step Codex iteration on plans v2 → v3 → v4 → v4-final → v5 could itself be a phantom (each round refining the plan rather than starting work). Is v5 the start point, or do we need v6?
3. The "non-sycophancy / refusal honesty" pitch is the differentiator. Is it actually delivered in v5, or is it just claimed in north-star copy?
4. Identify the SINGLE highest-risk task in the plan that, if it slips, cascades into delivery failure.
5. If you had to bet on whether v5 produces a Carney-deliverable in 13 weeks, what odds? V4 was 60-65%/70%-with-redline. What's v5?

### H. The single most important fix

After all the above: name the one thing in v5 that, if not corrected before Phase 0 starts, will produce another phantom completion or BPEI moment by week 8.

## Output structure

- A through G: numbered specific responses, with quotes from the plan when attacking
- H: the one fix
- Final paragraph: GREEN / YELLOW / RED verdict with concrete next-step recommendation

## Constraints

- Brutal as before. The user explicitly wants Codex to be loyal AND adversarial — both at once.
- If your verdict is "v5 is sprint-startable on these conditions," say it.
- If "v5 needs surgical redline (no full v6)," specify which lines.
- If "v5 still has structural issues requiring v6," specify what changes.
- Don't soften.

The user is reading your verdict and will use it to decide whether to start Phase 0 tomorrow.
