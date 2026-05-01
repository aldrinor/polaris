# Codex v3 review brief — did the revision address v2 findings?

**Model expectation:** gpt-5.5, xhigh reasoning. Adversarial product review continuing from v2 review.

**Your role:** stress-test the v3 revision specifically. Did v3 close the v2 findings or paper over them? Did the revisions introduce new failure modes? Where does phantom completion still hide?

**Word budget:** ~1500 words. No code. No new milestones.

---

## Context

You reviewed v2 and gave a "not ready" verdict with the single most important finding:

> *"The plan still has no independent owner for adversarial real inputs and correctness judgment. Until a named target-user/proxy supplies prompts, judges outcomes, and can fail the release, 'correct outcome,' 'works for any user-submitted run,' and 'user sign-off' will collapse back into curated demos."*

You also raised: phantom-completion in 7 specific acceptance criteria, sequencing dependencies (Flow 6 needs Flow 4's report page), 5-week timeline not credible, Flow 3 starvation, false-unblock copy, deployment reality not peripheral, Flow 4 most likely to degrade, and 6 specific overcommitment phrases.

The plan author (Claude) revised to v3 and is sending it back to you. This is iteration 2.

## What changed in v3

Read `docs/shippable_plan_v3_draft.md`. Summary:

1. **Dropped Flow 3 (live audit) and Flow 5 (standalone contradictions) from MVP** per your "stronger pilot" recommendation. Contradictions become click-through badges inside the report view (Flow 3 of v3 = Flow 4 of v2). Live audit explicitly deferred to v2.5 with the simpler "status bar + cancel" in v2.
2. **Added Flow 5: deployment / install / account / sharing reality** per your "deployment reality is load-bearing, not peripheral."
3. **Defined adversarial test corpus** — 11 input classes + 9 content classes. Replaces every "any" with the corpus.
4. **Tightened Layer 3 evaluator** — named individual outside build/plan loop, NOT Claude, NOT Codex, with fail authority; one of (a) named real prospect, (b) paid contractor, (c) internal-non-build employee with recorded sessions.
5. **Walkthrough cadence: 3 per flow at end-of-sprint**, not week-5-only.
6. **Bundle contains source text + spans** (not just URLs); standalone-verifiable per your finding that paywalled URLs break offline verification.
7. **Empty states required** for every flow (zero contradictions, zero gaps, zero disagreements, partial runs, aborted runs).
8. **Multi-span claims, typed numbers** explicitly handled — replaced "any decimal" with typed cross-ref behavior per number kind.
9. **Timeline 8-12 weeks** (not 5), with Sprint 4 as buffer for walkthrough findings (your 30-50% recommendation).
10. **False unblock removed** — Flow 2 refusal copy no longer promises "supply via private corpus upload" when upload UI is out of scope.
11. **Sequencing fix** — Flow 4's audit bundle button explicitly requires Flow 3's report page; both are in Sprint 2 together.
12. **Blockers section** — 4 items the user must answer before Sprint 1 starts; plan acknowledges it's "on paper only" without these.

## What I (Codex) want you to attack in v3

### A. Did v3 close your v2 findings?

For each of your v2 findings, evaluate:
- Closed (the revision adequately addresses the issue)
- Partial (revision moves in the right direction but a gap remains; specify the gap)
- Reopened (revision claims to fix it but introduces a new version of the same problem)
- Not addressed

Specific items to check:
1. "Correct outcome" oracle — does the corpus + Layer 3 evaluator definition close this, or is "correct" still author-defined?
2. "Works for any run" — does the defined corpus close this, or did the corpus just become the new "any"?
3. Flow 4 (now v3 Flow 3) "every sentence clickable" weakness — multi-span and typed numbers added; is the click-through actually robust now?
4. Flow 6 (now v3 Flow 4) "source URL" insufficiency — bundle now contains source text/spans; does that close offline verification?
5. Layer 3 ceremony failure mode — is the new evaluator definition enforceable, or still hand-wavable?
6. Sequencing fix — does collapsing Sprint 1 to "BPEI spine + minimum viable report rendering" actually work, or does Sprint 1 still secretly need Sprint 2 deliverables?
7. Flow 3 starvation — Sprint 1 needs accepted-query test cases that don't exist until Sprint 2's Flow 3 lands. Is this still a problem?
8. 5→8-12 week revision — is the new range credible? What conditions would push it past 12?
9. False unblock — actually removed in copy?

### B. Where does phantom completion STILL hide in v3?

For each of the 4 (was 6) flows, find at least one acceptance criterion that:
- Could be marked complete by a developer running the corpus
- Would still leave a real buyer experiencing a broken flow

Specifically attack the corpus itself:
- Is the corpus complete enough to be a real bench, or is it 11 cherry-picked classes that miss whole categories of real-world input?
- "Layer 3 evaluator brings at least one of their own real questions" — does this corpus-augmentation actually happen, or does it collapse to the canned 11?
- The 9 content classes for Flow 3 (50-sentence, 200-sentence, zero contradictions, etc.) — what content classes are missing?

### C. Layer 3 reality (your #1 finding from v2)

The new definition says: outside build/plan team, NOT Claude, NOT Codex, domain-literate, fail authority.

1. Is this enforceable, or is "domain-literate" the new soft spot?
2. The plan offers 3 sourcing options (named prospect / paid contractor / internal non-build). Which has the highest risk of becoming ceremony, and how?
3. The plan says walkthroughs are "3 per flow at end of sprint, by 3 different evaluators." Is "different evaluators" enforceable, or will it default to the same person three times under deadline pressure?
4. "Recorded session, no live explanations" — is recording enough? Or does the gate need an asynchronous review of the recording by yet another reviewer?

### D. New failure modes introduced by the v3 revisions

Specifically:

1. Adding Flow 5 (deployment reality) added scope, not removed it. Is Sprint 3 doing too much (deployment + adversarial walkthrough across all 4 prior flows + final regression)?
2. The corpus is now load-bearing for every acceptance gate. If the corpus is wrong, every walkthrough silently passes. Who reviews the corpus itself for adversarial completeness, and on what cadence?
3. "Run anyway" path in Flow 2 (for threshold edge / out-of-scope adjacent) — does this create a backdoor that lets buyers bypass the BPEI prevention layer? Is the warning banner enough?
4. Embedding source text/spans in the bundle solves offline verification but raises legal/IP questions (republishing copyrighted source text). Is this a real concern, and how should the plan handle it?
5. The deferral of "live audit" to v2.5 is correct, but Flow 3's static post-hoc inspection may not be enough to demonstrate the "reasoning visible" pitch to buyers in a sales demo. Is the marketing story consistent with the shipping plan?

### E. Sequencing and time

1. The Sprint 1 + 2 + 3 + buffer-Sprint 4 structure — does each sprint have a coherent end-state that an evaluator can validate, or are sprints too dependent on each other?
2. Sprint 3 has Flow 5 (deployment) + 3 walkthroughs across all 4 prior flows + final regression. Is this realistic, or will deployment work bleed into Sprint 4?
3. Sprint 4 is "buffer for walkthrough findings." If walkthrough findings are minor, Sprint 4 is wasted. If they're major (a flow needs to be rebuilt), Sprint 4 isn't enough. How should the plan absorb each case?

### F. The blockers list

The plan says 4 items must be answered by the user before Sprint 1 starts. Sharpen this:

1. Of the 4, which is hardest for the user to answer if they don't already know? What's the lowest-friction path to getting that answer?
2. Are there other blockers the plan hasn't named?
3. If the user can answer 2 of 4 but not the other 2, can Sprint 1 honestly start with adjustments? Or is it 4-of-4-or-don't-start?

### G. The big-picture verdict

After all the above:

1. Is v3 ready to start Sprint 1, conditional on the blockers being resolved? Or are there structural issues that require another revision?
2. If you had to bet on whether v3 ships a usable product in 8-12 weeks (assuming blockers resolved): what odds and on what conditions?
3. What is the SINGLE most important thing that, if not fixed in v3, will produce another BPEI moment in 90 days?
4. What signal in the plan still suggests Claude is overcommitting?

## Output structure

- A through G: numbered specific responses. Quote the v3 plan when attacking.
- Final paragraph: GREEN / YELLOW / RED verdict with one-sentence reason.

## Constraints

- Be brutal. The user explicitly asked for adversarial iteration.
- Quote v3 specifically — don't generalize.
- If your verdict is "v3 is materially better but still needs revision X, Y, Z to be ship-ready," say that with specifics.
- If your verdict is "v3 is ready conditional on blockers," say that.
- Don't soften.

The user is reading your response. They will use it to decide whether the plan is real or another phantom.
