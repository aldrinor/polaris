# Codex v4 review brief — final iteration before user accepts plan

**Model expectation:** gpt-5.5, xhigh reasoning. Continuing adversarial product review.

**Context:** v3 received YELLOW from you. Your single most important finding was: *"The evaluator must own correctness judgment for adversarial real inputs, including rejecting the corpus and expected outcomes."* Plus 12 specific items across A/B/C/D/E/F. v4 attempts to address all of them.

**Your role:** stress-test v4 specifically against your prior findings. Did v4 close the YELLOW or paper over it? Is the plan now GREEN-eligible (sprint-startable conditional on blockers, with phantom-completion risk reduced to acceptable)?

**Word budget:** ~1200 words. No code. No new milestones.

---

## What v4 changed (per your v3 findings)

Read `docs/shippable_plan_v4_draft.md`. Specific changes vs v3:

1. **Corpus ownership reversed.** Plan-authored corpus is now explicitly a starter set; Layer 3 evaluator must replace ≥50% with their own real-buyer inputs in week 1; evaluator has authority to reject "Expected outcome" lines as wrong. Failure to do so means Sprint 1 has not legitimately started.

2. **"Domain-literate" → "buyer-workflow-literate."** Must have personally done the buyer's actual workflow.

3. **Sprint 3 overload fixed.** Flow 5 (deployment) moves to Sprint 2 in parallel with Flow 3+4. Sprint 3 = walkthroughs only. Sprint 4 = buffer.

4. **"Run anyway" backdoor closed.** Persistent banner during run, friction step ("type 'I understand'"), permanent watermark on report and bundle, filename includes `_lowconfidence_`.

5. **Embedded spans legal review.** Default to summarized spans (≤500 chars); full text only with license check passed; legal review of bundle contents required before Sprint 2 ends.

6. **Marketing copy fixed.** "Audit-traceable, refusal-aware, locally deployable" replaces "visible reasoning at every step." MVP is post-hoc auditability, not live reasoning.

7. **Corpus expanded** — 22 input classes (was 11) including DOI/PMID, PDFs, malformed tables, prompt injection, jurisdiction-specific, misspelled drugs, freshness-sensitive, follow-ups, private corpus references, auth/session expiry, unsupported-but-plausible templates. 17 content classes (was 9) including non-numeric contradictions, guideline-vs-trial, retracted sources, freshness conflicts, duplicated source families, table/figure evidence, no-evidence-but-important claims, jurisdictional disagreements.

8. **Async raw-recording review.** Named release-authority reviewer reviews raw recordings asynchronously; pass/fail not delegated to evaluator's verbal summary.

9. **Heading match:** "Five user flows" (not "Four").

10. **"Try in 6 months" promise removed.** Replaced with "no source-refresh cadence currently exists."

11. **Evaluator hours:** 30-50h across 4 sprints (was 10-20h).

12. **Blockers expanded** to 10 (was 4): added source-text redistribution rights, support ownership, email infrastructure, model/retrieval budget, security posture, first 3 templates locked.

13. **Sentence clickability tightened.** "Every claim sentence" replaced with "every sentence carrying a claim that strict_verify gated"; tables/headings/summaries explicitly NOT claimable. Synthesis claims (no direct evidence span) get `⚠ synthesis — no direct span` badge. Retracted, stale, low-confidence all visibly badged.

## What I (Codex) want you to attack in v4

### A. Did v4 close your v3 YELLOW findings?

For each of your v3 findings (corpus ownership, domain-literate escape hatch, Sprint 3 overload, run-anyway backdoor, embedded spans IP, marketing mismatch, missing input classes, missing content classes, missing blockers, evaluator hours, async review, heading mismatch, "try in 6 months" promise, sentence clickability slipperiness):

- Closed
- Partial (specify what gap remains)
- Reopened (specify the new version of the same problem)
- Not addressed

### B. Where does phantom completion still hide in v4?

Specifically:
1. Corpus ownership: "evaluator must replace ≥50% with their own inputs" — what if the evaluator can't or doesn't? Is there enforcement, or is this another "should" that collapses?
2. Buyer-workflow literacy: how is this verified before contracting? Who fails the candidate?
3. Async raw-recording review: who is the named release-authority reviewer? If the user themselves does it, is that real independence, or another self-loop?
4. Sprint 2 doing 3 flows + legal review in parallel: is this honestly schedulable in 4 weeks, or does it just move the overload from Sprint 3 to Sprint 2?
5. The "Run anyway" friction step: does typing "I understand" actually deter, or does it become muscle memory after 2 uses?

### C. Has v4 introduced new failure modes?

1. The 22-input × 17-content corpus is now ~40 test cases per flow, with 3 walkthroughs each = 120 walkthrough-cases. Is this realistic in the time/budget allocated?
2. Sprint 2 now has Flow 3 + Flow 4 + Flow 5 + legal review + 3-evaluator walkthrough. What's the most likely casualty under deadline pressure?
3. Async raw-recording review by user adds a serial dependency: nothing ships until the user finishes reviewing. If the user is busy, sprints stall. How should the plan handle the user being unavailable?
4. The expanded blockers (10 items) — does this give the user a credible go/no-go decision, or does it just push the plan further into "paper only" territory?

### D. Time/cost realism

V4 says 12 weeks honest, 8 optimistic. With:
- 22-input corpus, evaluator ≥50% replacement
- 17 content classes for Flow 3
- 3 evaluators × 5 flows × 3 walkthroughs = 45 walkthrough sessions
- Async raw-recording review on every walkthrough
- Legal review on bundle
- Sprint 2 parallel flows + deployment

Is 12 weeks credible? What pushes it past 12?

What's the realistic budget for evaluator hours at 30-50h × 3 evaluators = 90-150h total at $200-500/hr = $18k-$75k just on evaluators?

### E. The big-picture verdict

1. **Is v4 GREEN-eligible** (sprint-startable conditional on blockers, phantom-completion risk acceptable)? Or still YELLOW?
2. **Odds of usable 8-12 week pilot** assuming blockers resolved? V3 was 55-60%. Has v4 improved this?
3. **Single most important remaining fix** — is there one finding that, if not addressed, will produce another BPEI in 90 days?
4. **Is the plan at a stopping point** for iteration? V3 → v4 was a real iteration. Is v4 → v5 worth it, or has marginal value of further plan iteration dropped below the marginal value of starting Sprint 1 (with blockers resolved)?

### F. Final structural question

If you were the user reading this plan, would you accept it? Specifically:

1. Is there enough specificity to act on, or does it still feel like a list of intentions?
2. Are the blockers actionable, or do they require the user to do work the user shouldn't have to do (e.g., redistribute legal counsel time)?
3. What single line in v4 would you change to make it more accept-able vs more defer-able?

## Output structure

- A through F: numbered. Quote v4 specifically when attacking.
- Final paragraph: GREEN / YELLOW / RED verdict with one-sentence reason and an accept/iterate-once-more/reject recommendation for the user.

## Constraints

- Brutal as before.
- If your verdict is "v4 is sprint-startable, accept and proceed with blockers," say that.
- If "v4 is still not ready, iterate again," say that with specifics.
- Don't soften.

The user is reading your verdict. They will use it to decide whether to accept v4 + answer blockers, or ask for another revision.
