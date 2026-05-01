# Codex strategic review brief

**Model expectation:** gpt-5.5, xhigh reasoning. This is a strategic / product review, not a code review. Use the full reasoning budget.

**Your role:** adversarial strategic reviewer. Assume I (Claude) am overoptimistic and producing a phantom-clarity narrative. Find what's wrong with my framing, my current-state audit, and my proposed planning method. Propose framings or methods I have missed.

**Word budget for response:** ~1500 words. No code.

---

## Context: what just failed

POLARIS shipped v1.1 with "5 of 7 BEAT-BOTH dimensions" against ChatGPT DR + Gemini DR on a single curated query (tirzepatide for T2D). 113 engineering milestones marked completed across multiple sprints, all of which YOU (Codex) GREEN-signed during 4 plan-review rounds and dozens of milestone reviews.

The user then typed `"What is BPEI"` into the live dashboard. POLARIS:
- Scope gate accepted it (`domain=custom`)
- Sent literal string to Serper + Semantic Scholar
- Retrieved 4 sources mixing two unrelated meanings: Blepharophimosis-Ptosis-Epicanthus inversus syndrome (a genetic eye disorder) AND Bascom Palmer Eye Institute (an eye hospital)
- Was about to synthesize a confused, multi-topic report that would have passed `strict_verify` (per-sentence evidence binding) while being useless to the user

The user then audited the UI against the 113 "completed" milestones. Most milestones shipped backend code + HTTP endpoints + tests, but **never built a UI surface**. Concretely: M-23 (review queue), M-NEW (billing), M-25 (Drive sync), M-26 (contracts), M-24 (support), M-LIVE-3 (operator dashboard), M-D11 (pin replay), M-22 (slide deck), M-16 (run diff), M-17 (citation health), M-18 (regression alerts) — all have backend endpoints but **zero browser-reachable UI**. Plus the scope gate accepts off-scope queries instead of rejecting them. Plus the templates catalog has 3 entries (M-20 said "scaling 50-100 templates"; reality: 3).

The user said: "our plan is shit, right?"

I told them: the plan wasn't badly written, it was correctly written for the wrong question. It scoped milestones as "code passes tests" not "a user can do X." Codex reviewed against milestone definitions, which were code-level. Codex couldn't open a browser. The blind spot was structural, not careless. I take responsibility for accepting the milestone definitions as adequate when they weren't, and for letting "engineering substrate complete" become "product shippable" in my framing.

## What the user wants now

Quote: *"I want to see the plan in between, pls also work it out with codex, ask codex to help you to improve the plan, and then give me the true plan to move forwards. Strong audit visually, e2e, lively, plus pass all codex deep review."*

Translation: a real plan from today's state to "shippable" with the audit story visible in UI, end-to-end in a browser, live progress, and review-resistant.

## Three framings I am presenting to the user

| Framing | What customer does | What POLARIS does | UI work | Substrate work | Time-to-pilot |
|---|---|---|---|---|---|
| **A. Audit-as-a-service** | Brings own draft, paste/upload | Per-sentence verification against retrieved primary sources | Moderate | None new — strict_verify exists | ~3-4 weeks |
| **B. Curated research-as-a-service** | Picks from whitelist, parameterizes | Runs pipeline within a known-good template, rejects out-of-scope | Heavy | Light (OOS hardening, ~3 → ~10 templates) | ~6-8 weeks |
| **C. General research tool** | Types any question | Disambiguates, scopes, retrieves, synthesizes, verifies | Heaviest | Heaviest (query-understanding layer doesn't exist) | ~3-6 months |

My honest read: A is most defensible because input is already a sentence-level claim, BPEI failure mode doesn't exist, ~70% of engineering done. B is what the existing plan was implicitly trying to be but never enforced OOS rejection. C is what the BEAT-BOTH benchmarking implied we were doing but the audit moat doesn't save us — relevance is the bottleneck, not faithfulness, and ChatGPT DR / Gemini DR are racing on the same axis with bigger teams.

I told the user A → B is my advised path, but I'm not picking for them.

## Proposed planning method

**(i) Items are user flows, not code modules.** Every item takes the form: *"User X clicks Y in browser, sees Z, within N seconds. Verified by recorded walkthrough."* If an item can't be written that way, it doesn't go in.

**(ii) Three review layers; Codex GREEN is not the ship gate.**
- Layer 1: Codex code review (existing)
- Layer 2: Codex user-perspective review (new): "for each user flow, enumerate inputs that break it; find acceptance criteria only a developer could verify; adversarially propose user actions not covered"
- Layer 3: Human browser walkthrough (new, non-negotiable): the user or a QA proxy runs each flow end-to-end at end-of-milestone. Recorded. **Codex GREEN + walkthrough = done. Codex GREEN alone ≠ done.**

**(iii) Hard scope cap: 5-10 user flows total. One-page plan.** 113 milestones diluted scrutiny. If picked framing requires >10 flows, framing is too big.

**Anti-patterns refused even if asked:** "iterate until Codex GREEN" (failure mode), "backend exists = done" (phantom completion), "while we're at it" (scope creep), "re-enter the autoloop" (converges on Codex-passable code, wrong target).

## Current-state user-flow audit (browser-reachable yes/no)

| Flow | Browser? | Reality |
|---|---|---|
| Type clinical-template query → see verified report | ⚠️ Partial | Pipeline runs, but `/inspector` opens for 1 canned slug only |
| Off-scope query → clear rejection / help | ❌ | BPEI failure: accepts anything, garbage retrieval |
| Browse past runs | ❌ | API only |
| Click sentence → see evidence span | ✅ | Canned slug only |
| Contradiction matrix / frame coverage / methods / tier mix | ✅ | Canned slug only |
| Live progress while running | ❌ | SSE exists, no renderer |
| Run diff (compare two) | ❌ | API only |
| Audit-bundle export (zip) | ❌ | API only, no button |
| Citation health / regression alerts / operator dashboard | ❌ | API only |
| Operator review queue | ❌ | API only |
| Sign in / org / API keys / billing | ⚠️ | Sign-In button exists; rest is API-only |
| Slide deck / Drive / contracts / support | ❌ | API only |
| Templates: see what's supported | ⚠️ | API only, 3 templates not 50 |
| Out-of-scope rejection | ❌ | Scope gate too permissive |

## What I need from you (Codex), by section

**On the three framings (A / B / C):**
1. Stress-test my analysis. What did I miss in trade-offs?
2. Is there a 4th framing or hybrid I haven't named that would be smarter? E.g., A as a wedge into B, or B narrowed to one vertical, or A + manual analyst service.
3. Is "A → B sequencing" my recommended path actually wise, or am I doing engineer-think (smallest scope = smallest risk) when the right answer is product-think (which framing matches a buyer)?
4. What buyer/persona is each framing for, concretely? Have I conflated them?

**On the current-state audit:**
5. What flows did I miss in the audit? What latent capabilities exist in the codebase I haven't surfaced as user flows?
6. The BEAT-BOTH benchmark is on n=1 query. How would you size the generalization risk for each framing?

**On the planning method:**
7. The 3-layer review with mandatory human walkthrough — does it actually close the BPEI-class blind spot, or am I just adding ceremony? Be specific about what would still slip through.
8. Scope cap of 5-10 flows fitting on one page — is this the right number or is it arbitrary? What's the actual constraint?
9. "User-flow-level done" — am I missing failure modes inside that definition? E.g., flow works on happy path but breaks on common errors; flow works for the developer but not for a non-developer; flow technically works but is unusable. How would you write the criteria so these don't slip through?

**Adversarial / blindspot:**
10. If you were the most hostile reviewer of MY framing, my audit, and my method — what would you attack? What does the BPEI failure imply about my judgment that I am still not seeing?
11. Is there evidence in the conversation that I am about to repeat the same error in a new shape? E.g., am I creating a new "phantom" by promising user-flow-level discipline that I will then quietly relax under deadline pressure?
12. What's the single most important thing to tell the user that I'm not telling them?

**On asking the user to pick A / B / C:**
13. Is the choice well-formed for them? Or am I asking them to make a decision they don't have the inputs for? What inputs do they need that I haven't given them?
14. What information would you need from the user before recommending one framing, that I haven't asked for?

## Constraints on your response

- No code. No new milestones.
- Adversarial framing throughout. Assume I'm wrong about something important.
- Be concrete: name the specific failure modes, don't generalize.
- If you think the right answer is "stop and pick a different question entirely," say that.
- Word budget ~1500. Don't pad.
- Output structure: numbered responses to my 14 questions, then a final "the one thing I'd tell the user" paragraph.

The goal is to produce a strategic review the user can read and decide on. Not a plan yet. The plan comes after the user picks the framing and we've absorbed your critique.
