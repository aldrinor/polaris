# Codex review brief — I-ux-001 S-tier experience PLAN (UNCAPPED)

## 0. ITERATION DIRECTIVE — NO CAP (operator override 2026-05-24)

The operator has explicitly REMOVED the standard §8.3.1 5-iteration cap for THIS plan review:
> "I won't set an iteration cap here — if Codex needs 30 rounds iteration to confirm, just be it. I want top-tier S-level UI experience, not half-ass. Keep iterating until even Codex at its highest requirements would approve."

So:
- Apply your HIGHEST bar. Do not approve a plan that would produce a merely "clean/functional" or B-tier result. Approve only a plan that, executed faithfully, yields a genuinely **frontier-BEATING, S-tier, differentiated** experience.
- Still **front-load all findings** each round (no drip-feed) — there's no penalty for more rounds, but a good review is exhaustive every round.
- "Don't pick bone from egg": classify findings P0/P1/P2/P3 honestly; reserve P0/P1 for real execution risks to the *experience*.
- Cross-check current best practice ONLINE (you have web access): Perplexity (Spaces/Comet), ChatGPT/Gemini Deep Research, OpenEvidence, Elicit, Consensus, Scite, FutureHouse, Genspark/Manus + craft refs (Linear, Stripe, Vercel, Raycast). Decisions must be evidence-based, not from memory.
- Be a PICKY REAL USER (a senior clinical/policy reviewer in a Prime Minister's office). Ask the hard question: *clicking in, what would actually make me go "I've never seen research like this" and come back?* If something is weak or pretend-play, say so. If something needs a complete rebuild, say so.

## 1. What to review

Read these files in the repo:
- **`docs/stier_experience_plan.md`** — THE plan under review.
- `docs/stier_experience_directive_2026_05_24.md` — operator directive + research synthesis (context).

**Attached images (current LIVE state — ground your critique in this reality):**
- `01_home.png` — the home / first impression (note the proof showcase right-panel).
- `02_intake.png` — the Ask page (note the empty space).
- `03_inspector.png` — the centerpiece Proof Replay / signed-bundle inspector.

## 2. HARD CONSTRAINTS (operator-LOCKED — NOT consultable; do not reopen)

- Brand red `#c8102e` is locked. Sovereignty wording is honest: LLM inference currently routes via OpenRouter (US), disclosed at `/transparency`; "Canadian-hosted" framing for hosting/data. Do not propose claiming full LLM sovereignty.
- Per-sentence provability + signed bundle is the CORE differentiator (clinical-safety-critical) — do NOT propose diluting it (e.g. don't propose a freeform chat that breaks provenance). You MAY propose how to make it more compelling.
- Stack: Next.js 16 (App Router, Tailwind v4, Geist). Clinical deep-research domain. Target recipient: PM Carney's office (one-shot gift/demo).
- This is a PLAN review, not code. Don't review code diffs here; review the strategy + design direction.

## 3. Reviewer Independence + Exhaustivity

> **Independence:** verify claims in the plan against the attached screenshots + your own online research, not by trusting the plan's assertions. A claim in the plan that doesn't hold up is a finding.
> **Exhaustivity:** target 15-40 findings on this first scan. Emit ALL of them this round. Don't truncate.

## 4. Acceptance criteria (forced enumeration — one line each in your verdict)

1. **Product direction (§2 of plan):** Is "brief-first + claim-anchored follow-up + compounding knowledge graph + bounded visible-agentic, NOT general chat" the right call for this user/recipient? Or should it lean more conversational / more agentic? Defend with evidence.
2. **End-to-end journey (§3):** Does the 8-step journey cohere as ONE experience? Missing steps? Wrong emotional beats? Friction?
3. **Hero — Proof Replay (§5):** Is the hero interaction spec strong enough to be the "wow"? Is the at-a-glance verdict header right? What would make it unforgettable vs merely nice?
4. **Visual & motion system (§6):** Is the craft bar (type scale, color semantics, motion tokens, microstates) sufficient and concrete enough to hit Linear/Stripe-tier? What's underspecified?
5. **Liveliness:** the operator's repeated demand. Is the motion plan first-class and specific enough, or still hand-wavy?
6. **Per-page targets (§7):** Any page under-scoped? Any "C→S" that's unrealistic without a rebuild the plan doesn't name?
7. **Differentiation (§8):** Do the one-line differentiators actually hold vs each competitor (online-check them)?
8. **Sequence (§9) + #871:** Is the execution order right? Is making #871 (live run aborts corpus_inadequate → no real brief to show) a hard prerequisite correct, or should the hero ship against the existing real signed bundle first?
9. **What's MISSING entirely** that a frontier-beating clinical deep-research experience needs and this plan doesn't mention.

## 5. Output schema

```
## Per-criterion forced enumeration
- Criterion 1 [product direction]: <findings or AGREE + why>.
- ... (all 9)

## Findings (severity-stratified)
### P0 (would make the experience NOT S-tier / fundamentally wrong direction)
- <description + the evidence/source>
### P1 (significant weakness; experience falls short of frontier-beating)
- ...
### P2 / P3 (precision / polish)
- ...

## Missing-entirely
- <things a frontier-beating clinical DR experience needs that the plan omits>

## Verdict
verdict: APPROVE | REQUEST_CHANGES
convergence_call: continue | accept_remaining
APPROVE iff: the plan, executed faithfully, would produce a genuinely frontier-beating S-tier differentiated experience with zero weak spots in product direction, hero, journey, and craft. No iteration cap — hold the highest bar.
```
