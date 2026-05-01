# Codex adversarial review brief — Shippable plan v2

**Model expectation:** gpt-5.5, xhigh reasoning. Adversarial product review, NOT code review.

**Your role:** find what's broken in this plan before it ships. Specifically: find phantom-completion sneaking back in, find user-flow gaps, find acceptance criteria only a developer can verify, find inputs that break each flow, find sequencing risks. Be hostile.

**Word budget for response:** ~2000 words. No code. No new milestones (we have enough of those already).

---

## Why you (Codex) are being consulted on this

You GREEN-signed the previous plan 4 rounds. The user typed "What is BPEI" into the resulting product and it failed in 30 seconds. The post-mortem found that the plan's "completion" criteria were code-level (tests pass, endpoints exist), so 15-20 advertised features have backend code but no UI surface. Codex code review couldn't catch that — Codex can't open a browser. The plan was technically rigorous and product-naive.

This new plan tries to solve that. **Your job is to attack it.** Find where the same failure mode is hiding in new clothing. If you GREEN-sign this plan and it produces another BPEI, the failure is on both of us, not just the planner.

## What the plan is

POLARIS will be repositioned as a deep research agent with **reasoning visible at every step**, deployed locally for sovereign buyers. The substrate exists; the visibility doesn't. The plan ships 6 user flows that surface POLARIS's distinctive decisions to the user. Anti-pattern explicit: backend-exists ≠ shipped.

Full plan is in `docs/shippable_plan_v2_draft.md`. Read it first. Six flows:

1. **Scope discovery** — landing page shows what POLARIS can/can't answer (BPEI prevention)
2. **Scope/refusal/disambiguation** — query goes through gate; clear-match / ambiguous / out-of-scope / insufficient-corpus all get explicit, human-readable outcomes
3. **Live audit run** — user watches POLARIS think (search candidates, tier classification, evidence pool, per-sentence verify, contradictions detected) in real-time
4. **Report inspection** — frame coverage as lead, every claim clickable to its evidence span, two-family disagreement surfaced
5. **Contradiction navigation** — every conflict has a navigable badge with all sides + tiers + hedge language
6. **Audit bundle export** — single button, complete offline-verifiable zip

Three review layers: Codex code review, **Codex user-flow adversarial review (you, this brief)**, mandatory human browser walkthrough. Codex GREEN is no longer the ship gate.

## What I need you to attack, by section

### A. Phantom-completion check

The previous plan's failure was that "M-23 reviews_store.py + endpoints + tests" got marked done while no human could reach the queue. Each flow in this plan claims to fix that with stricter acceptance criteria. **Stress-test those criteria.**

1. For each flow's acceptance criteria: which lines could a developer mark complete while a non-developer in a fresh browser session experiences a broken or unusable flow? Be specific — quote the criterion, then describe the failure mode that slips through.
2. Identify any acceptance criterion that is "passes when X works" without specifying who tests, on what state, with what inputs. These are the cracks phantom completion grows in.
3. The plan says "user sign-off" is required as Layer 3. Without a defined "user" (single buyer? team? proxy?), this could collapse to "Claude says it works." Identify how to specify Layer 3 such that it's a real gate, not a rubber stamp.

### B. Per-flow input-class adversarial enumeration

For each of the 6 flows, enumerate at least 3 inputs / user actions that:
- Are realistic things real users would do (not contrived edge cases)
- Are NOT covered by the current acceptance criteria
- Would expose the flow as broken or unusable

Examples to seed your thinking (not exhaustive):
- Flow 1: user copy-pastes a paragraph instead of a question; user types a question that's 10 words; user types in a non-English language; user has JS disabled
- Flow 2: user asks ambiguous query but both meanings are in-scope; user asks a question where the template confidence is 49% (just below threshold); user appeals an out-of-scope refusal — is there a path?
- Flow 3: SSE connection drops mid-run; user opens the run in two tabs; source fetches return 80% before timeout; strict_verify drops every sentence (zero-verified abort) — what does the live UI show?
- Flow 4: report has 200 sentences (latency on hover-highlight); report has zero contradictions; user clicks an evidence span that points to a paywalled source the user can't actually read
- Flow 5: 0 contradictions; 50 contradictions; contradictions where the conflict is between two T1 sources (no tier hierarchy disambiguates)
- Flow 6: bundle is 500MB; user wants to redact the bundle for legal; user wants to share with someone without a POLARIS account — does the bundle work standalone?

For each enumerated gap, propose: does the plan need a new acceptance criterion, a new flow, a new flag, or is it acceptable to defer (and if defer, document why).

### C. Sequencing and dependency risks

The plan sequences Flows 1+2+6 first (BPEI spine), then 3+4+5 (visibility), then walkthrough. Attack this:

1. Are 1+2+6 genuinely independently testable, or does Flow 2 (refusal) require Flow 4 (some report rendering) to demonstrate "what would have happened"? Find hidden dependencies.
2. Flow 3 (live audit) depends on the run actually progressing through all stages. If Flow 2 rejects most queries (the BPEI fix), Flow 3 may rarely execute end-to-end during testing. Is there a sequencing problem?
3. The plan estimates 5 weeks. What's the most optimistic and most pessimistic realistic estimate? What buffer should be assumed for adversarial walkthrough findings that require rebuilds?
4. The plan says "out of band: 4 decisions still needed from user (buyer segment, hardware target, deadline, walkthrough proxy)." Which of these, if not answered, would cause the plan to go off the rails by week 2?

### D. Crown-jewel completeness

The plan claims to surface 7 crown jewels (visible reasoning, refusal-with-explanation, click-through audit, navigable contradictions, frame coverage as lead, two-family disagreement, provenance bundle). Out-of-scope explicitly: pin replay, Python charts, Q&A, freshness alerts, multi-jurisdiction view, etc.

1. Of the deferred items, which (if any) is actually load-bearing for the buyer story and shouldn't be deferred? Argue for inclusion if so.
2. Of the 7 included, which is most likely to be poorly executed under deadline pressure and degrade silently into "kind of works"? Which crown jewel needs the most defensive acceptance criteria to prevent dilution?
3. The plan does NOT include the Python-execution-with-charts flow (the "biggest advantage" per project memory). Should it? Or is the deferral defensible? Make the case both ways.

### E. The Layer 3 (human walkthrough) reality check

This is the new gate. It only works if it's real.

1. What's the failure mode where Layer 3 becomes ceremony — a curated walkthrough that happens to pass — and stops catching the BPEI-class issues it's meant to prevent? Be concrete about how this happens.
2. The plan says "non-developer evaluator." Without that role being specifically named (and someone hired/assigned), the walkthrough may default to the user themselves or to me (Claude), neither of which is independent. Propose a specific, enforceable definition.
3. What's the minimum number of independent walkthroughs per flow before "shipped" is honest? 1 is too few. 100 is theater. What's the right number and on what cadence?

### F. Hostile big-picture attack

After the section-by-section attack, step back:

1. What is this plan still missing that, if I asked you in 6 months "why didn't this ship a usable product," you would point to right now?
2. The plan's vision is "reasoning visible at every step." Is the implied UX actually achievable in the time budget, or is the plan secretly promising months of design work in 5 weeks of engineering?
3. Is there a different, simpler structure to this plan that would ship something usable faster, even at the cost of crown jewels? E.g., "ship Flow 6 (audit bundle) and Flow 4 (click-through inspection) as a paid product on day 1; defer the rest." Argue for or against simplification.
4. Is there evidence in the plan that I (Claude) am about to overcommit again? E.g., promising 6 flows when 3 would actually ship cleanly? Identify the concrete signs.
5. Is the buyer segment (sovereign deep research) realistic for a 5-week pilot timeline, or is the buyer too slow-moving to validate within that timeframe? What would make this work, what would make it fail?

### G. The single most useful adversarial finding

After all the above: name the single most important thing in this plan that, if not fixed, will produce another BPEI moment in 60 days.

## Output structure

- A through F: numbered responses. Concrete. Specific. Quote the plan when attacking it.
- G: the one finding.
- Optional final paragraph: any structural observation about my (Claude's) judgment that is still off after this conversation.

## Constraints

- Be brutal. Assume Claude is overoptimistic and the plan is underspecified.
- Prefer specific over general. "The acceptance criterion in Flow 4 saying 'works for any user-submitted run' could pass with a single tested run by a developer" beats "the criteria are vague."
- No code. No new milestones. No GREEN-signing. Just the attack.
- If your honest verdict is "this plan is not ready and these are the blockers," say so. Don't hedge for politeness.

The user explicitly asked for this loop. They want the result, not a polished consensus. Bring the result.
