# POLARIS — S-Tier Experience Plan (I-ux-001 / #872)

**For:** Codex deep review (UNCAPPED, until APPROVE at highest bar) per operator 2026-05-24.
**Grounded in:** the live running system (polarisresearch.ca, screenshots `web/p2shots/audit/*` 2026-05-23 + viewed 2026-05-24), the frontier-product research synthesis (`docs/stier_experience_directive_2026_05_24.md` §4), and the actual route/source inventory.
**Decision authority:** Codex. Every recommendation below is a proposal for Codex to confirm, sharpen, or override with evidence. Claude does not ask the operator.

---

## 0. North Star (one sentence)

> **POLARIS is the only deep-research product where a decision-maker can challenge any sentence and watch it prove itself — instantly, against the primary source, with a signed receipt.**

Everything in the experience exists to deliver that one feeling: *"I can trust this because I can check it, and checking it is delightful."* That is the whitespace no competitor occupies (OpenEvidence constrains sources, Scite classifies citations, Consensus shows a meter, FutureHouse shows reasoning — **none ship a signed, per-sentence-provable bundle**).

## 1. Grounded current-state verdict (what the running system actually is today)

Not docs — the live pixels. Honest picky-user grade:

| Surface | Today | The problem (observed) |
|---|---|---|
| **Home** | B− | Headline is strong ("check, line by line"). But the **proof showcase — our entire differentiator — is the most broken-looking element**: the "exact passage" renders as a dense justified gray block with fragmented highlight runs. The one thing nobody else has, presented as a debug dump. Feature trio below is generic, small, lifeless. |
| **Intake** | B− | ~60% dead white space below a plain card. Static. No preview of the payoff. A picky user sees "a lot of nothing." |
| **Inspector / Proof Replay (centerpiece)** | B/B+ | Bones right (signed-bundle hashes, two-family invariant, claim↔span split, 8 tabs). But reads as a **dense developer tool**, not an "audit every sentence" wow. Span panel cramped; highlight hard to parse; no drama. |
| **Run progress, Compare, Graph, Audit, Source-Review, Dashboard, Memory, Benchmark, Upload, Contracts, Pin-Replay, Sign-in** | C to B | Functional, WCAG-clean (axe 0), but flat hierarchy, inconsistent density, and — across the board — **zero liveliness**. Nothing moves, nothing reveals, nothing feels alive. |
| **Systemic** | — | Flat typographic hierarchy; empty-space discipline absent (intake) or dense (inspector); motion entirely missing; the proof — the hero — looks the *least* premium. |

**Thesis:** the product *bones are correct* — proof-as-hero is the right bet and the pieces exist. The failure is **execution quality + liveliness**. The single highest-leverage move is to make the **proof moment premium and alive** (home demo + inspector), then a systematic craft + motion pass across every page.

## 2. Product-direction decisions (the operator's four questions — answered with evidence)

> Codex: confirm/override each with your own online cross-check.

### Q1 — Prolonged conversation, repeating pipeline, or one-shot brief? → **Brief-first, with claim-anchored follow-up. NOT a general chat.**
- **Evidence:** Elicit's value is explicitly "less like a conversation, more like a structured, verifiable artifact"; ChatGPT/Gemini DR deliver a one-shot brief then allow follow-up; OpenEvidence is fast Q→A for point-of-care. A freeform chat **dilutes per-sentence provability** — every turn would need its own provenance/verdict, and the signed-bundle guarantee weakens.
- **Decision:** the primary artifact is a **one-shot, audit-grade brief**. After delivery, follow-ups are **anchored to a specific claim** (already built, #757) so each answer inherits the provenance model. The "repeat the pipeline" need is met by *running again with a refined plan*, not by chatting.

### Q2 — Branch research → knowledge graph? → **Yes, as the secondary "snowball" / return surface. Not the hero.**
- **Evidence:** Perplexity Spaces accrue memory and get stickier with use; Undermind's depth comes from following citation trails. A graph that **compounds across runs on a policy topic** is a genuine return-driver.
- **Decision:** keep/upgrade the knowledge graph (#758) as the *come-back-tomorrow* surface — it grows as you run more questions in a topic. The proof artifact stays the hero; the graph is the depth/retention layer.

### Q3 — Agentic, continuously-deploying tools (Claude Code / Codex-web style)? → **Yes — but bounded + visible-as-rigor, not unbounded autonomy.**
- **Evidence:** Genspark/Manus impress via visible multi-step execution; FutureHouse exposes the agent's *source-evaluation reasoning* for trust. For a clinical reviewer, the agentic loop must read as **rigor** (which guideline, which RCT, why this source over that), not spectacle.
- **Decision:** the pipeline IS agentic (scope → retrieve → adequacy → generate → verify). Surface it as a **live, legible "rigor feed"** on the run-progress page: each step shows the *evidence decision* it made. An unbounded "do anything" agent would break auditability (every action must be provable), so depth is bounded and every step is on the record. This is our honest, differentiated take on "agentic."

### Q4 — What makes a picky user stay? → **The proof moment + reliability + a compounding topic workspace.**
- **Evidence:** OpenEvidence retention (40%+ of US physicians daily) is built on *reliability* ("it has to work, every time"), not features; Spaces retain via compounding memory; the trust surfaces (citation context, evidence meter, reasoning trace) are what experts return for.
- **Decision:** (a) make the proof interaction *delightful and instant* so the first session creates a "I've never seen research I could check like this" memory; (b) ruthless reliability (no dead-ends — see #871); (c) a topic workspace (graph + run history) that's richer every visit.

## 3. The end-to-end experience (the journey, with the emotional beat at each step)

A real user, start to finish — each step must be S-tier *and* cohere as one experience:

1. **Land (Home)** → *"Wait, I can actually check every sentence?"* A live, real verified claim with a one-click "prove it" reveal that animates the span lighting up in its source. One obvious CTA: **Ask a question**.
2. **Ask (Intake)** → *"It understands what I'm asking and won't waste my time."* Big, confident question field; auto-detected domain; it shows it will confirm scope first. Fill the dead space with a *live preview of what a finished brief looks like* (a thin proof-replay teaser) so the payoff is visible before they commit.
3. **Confirm (Plan review)** → *"I'm in control."* An editable plan (the Gemini-DR pattern) — interpreted question, sources it will use, what it will and won't claim — before a single token is spent.
4. **Watch (Run progress)** → *"This is doing real, rigorous work."* The legible rigor feed: scope ✓ → retrieval (sources found, tiered) → adequacy gate → generation → per-sentence verification, each with the evidence decision visible. Honest about aborts (refusal/inadequate = a *feature*, shown with dignity).
5. **Read (Report = Proof Replay)** → *the hero.* A clean, premium brief. A single at-a-glance **verdict header** (the whole brief's provenance state). Hover/click any sentence → its evidence span lights up beside it with a verdict chip. This is the moment that sells the product.
6. **Interrogate (Follow-up / Compare)** → *"I can push on this."* Claim-anchored follow-ups; compare two runs/claims side by side.
7. **Explore (Knowledge graph)** → *"There's a whole map here, and it grows."* The snowball — claims/sources/contradictions as a navigable, compounding graph.
8. **Take it away (Audit / Export)** → *"I can hand this to my counsel and they can verify it offline."* The signed bundle + manifest + offline inspector. The receipt.

## 4. Information architecture

- **Public:** Home (proof demo) · Transparency · Sign-in. Nav minimal, confident.
- **Authed primary journey:** Ask → Plan → Run → Report(Proof Replay) → Follow-up/Compare → Graph → Export. This is *one continuous flow*, not 8 disconnected routes — the nav and in-page CTAs must make the next step obvious.
- **Authed supporting:** Dashboard (monitoring), Source-Review (set health), Upload (private docs), Memory, Benchmark, Contracts, Pin-Replay. These are *tools*, visually subordinate to the journey.
- Kill internal jargon in user-facing copy (operator flag: "refusal-bait", "PICO axis", "scope" without explanation).

## 5. The hero interaction — Proof Replay (exact spec)

This is the product. It must be flawless and alive on both Home (teaser) and Inspector (full).
- **Resting state:** the brief reads as a clean, authoritative document. Each sentence carries a subtle verdict affordance (a hairline underline tint by verdict color, not noisy chips inline).
- **On hover/focus of a sentence:** the matching evidence span in the source panel **animates to highlight** (≈200ms ease), the source card scrolls/settles to it, and a verdict chip (VERIFIED / PARTIAL / UNSUPPORTED) appears with the tier + source name. Reverse on blur.
- **On click:** pins the pairing; shows the full span in context + the provenance token + "open source" + numeric-match detail.
- **At-a-glance:** a brief-level verdict header (e.g., "18 claims · 16 verified · 2 partial · 0 unsupported") — the Consensus-Meter analog, but per-claim and provable.
- **Motion is meaning:** the highlight reveal *is* the proof happening. This is the single most important place to invest motion craft.
- **Fix now:** the Home showcase span rendering (broken justified gray block) and the Inspector span panel (cramped, dev-tool dense) → premium typographic treatment, generous reading measure, clear highlight, calm color.

## 6. Visual & motion system (concrete — upgrade, don't restart)

Keep the warm-editorial-institutional base (#704) + brand red `#c8102e` (operator-LOCKED). Raise it to the Linear/Stripe craft bar:
- **Type:** one family (Geist). A real scale — display / h1 / h2 / h3 / body-lg / body / caption / mono — with deliberate line-height + measure (60–75ch for brief prose). Hierarchy carried by **type + space**, not color/chrome.
- **Color:** near-monochrome ground + ONE meaning accent. Verdict palette is *semantic only*: `--verified` (green), `--contradiction`/partial (amber), `--unsupported`/`--destructive` (red), `--refusal`. Brand red reserved for primary action + identity. No decorative color.
- **Space:** an 8px rhythm; fix intake's dead space (add the proof teaser / recent briefs); fix inspector density (breathing room in the span panel).
- **Elevation:** designed shadows (`shadow-card`/`-hover`), hairline borders 0.5–1px low-alpha — never default `<hr>`.
- **Microstates:** ALL SIX on every interactive element (default/hover/focus/active/disabled/loading). Keyboard focus rings visible everywhere (WCAG 2.2 AA already at axe-0 — keep it).
- **Motion (the "lively" layer — currently absent, first-class here):** a small motion-token set (durations 120/200/320ms; `ease-standard`). Choreograph: the proof-span reveal; the run-progress rigor feed advancing; verdict chips settling; number count-ups on the verdict header; empty/loading states with character (not bare spinners); page transitions that feel intentional. All `prefers-reduced-motion` safe.
- **Signature:** the maple-leaf sovereign mark must be crisp and confident (operator: current is a "faint low-fidelity dot-cloud"), used sparingly as the sovereignty/identity beat.

## 7. Per-page S-tier targets

> Current grade → target S. Codex sets the exact bar per page at visual-audit time.

| Route | Now | Key moves to S-tier |
|---|---|---|
| `/` Home | B− | Fix the proof showcase (premium span render + animated reveal); tighten the feature trio into one differentiation statement; add life. |
| `/intake` Ask | B− | Kill dead space with a live brief-preview/proof teaser + recent briefs; confident question field; de-jargon copy. |
| `/plan` | B | Editable plan as a real control surface; show what it will/won't claim. |
| `/runs/[id]` Run progress | B | The legible "rigor feed"; honest abort states with dignity; motion on step advance. |
| `/runs/[id]` Report = Proof Replay | B/B+ | The hero §5 — premium document + alive proof reveal + verdict header. |
| `/inspector/[id]` | B/B+ | Same proof-replay craft; calm the dev-tool density; signed-bundle/two-family as a trust beat, not a hash dump. |
| `/compare`, follow-up | B | Claim-anchored, clear left↔right, premium. |
| `/runs/[id]/graph` Knowledge graph | B | The compounding snowball; legible, navigable, alive; mobile-real. |
| `/audit` export | B | The "receipt" — signed package + manifest + offline-inspector handoff, presented as trust not tables. |
| `/source_review`, `/dashboard`, `/memory`, `/benchmark`, `/upload`, `/contracts`, `/pin_replay`, `/sign-in` | C–B | Subordinate-but-crafted; consistent system; de-jargon; microstates + motion. |

## 8. Differentiation thesis (vs each, in one line)

- vs **ChatGPT/Gemini DR:** they give a long prose report you must trust; we give a brief you can *check sentence-by-sentence*, signed.
- vs **OpenEvidence:** they constrain sources for trust; we *prove* each claim against the source and hand you the receipt.
- vs **Scite/Consensus:** they classify/aggregate citations; we verify the *generated sentence* against its span with a verdict.
- vs **Elicit:** they give a structured extraction table; we give a narrative brief where every sentence is independently provable.
- vs **all:** sovereign (Canadian-hosted, disclosed), two-family-verified, and the only one that emits a **signed, offline-verifiable bundle**.

## 9. Execution sequence (after Codex APPROVEs this plan)

Foundation first (system), then hero, then journey, then supporting — each page: issue → brief → Codex brief review → build → **Codex 16-dim visual audit (`codex exec -i`, screenshot matrix)** → Codex diff review → merge → redeploy → screenshot-verify LIVE → close.
1. **Design-system + motion foundation** (type scale, color semantics, motion tokens, microstate primitives, crisp maple leaf).
2. **The hero: Proof Replay** (home showcase + inspector/report) — fix the broken span render; build the animated reveal + verdict header.
3. **Journey pages** in flow order: Intake → Plan → Run-progress → Report → Follow-up/Compare → Graph → Export.
4. **Supporting pages** to the consistent system.
5. **Reliability prerequisite — #871 (corpus_inadequate on real flagship clinical Q):** the hero must be real, not a fixture. A live run currently dead-ends. **Recommendation: Codex sequences #871 as a hard prerequisite for a *real* end-to-end demo** (the proof moment can't be canned for Carney). Flagged for Codex's call.

## 10. Definition of S-tier (acceptance)

A page is S-tier only when: (a) Codex's 16-dimension visual audit PASSes all dims via `codex exec -i` on a desktop+tablet+mobile screenshot matrix; (b) it's alive (purposeful motion, all six microstates, reduced-motion safe); (c) zero internal jargon in user-facing copy; (d) WCAG 2.2 AA (axe 0); (e) it coheres with the system and the adjacent journey steps; (f) verified LIVE on polarisresearch.ca after redeploy. The initiative is done when every page clears that bar and a real end-to-end run produces a real verified brief that renders through the hero.

---
*Codex: review uncapped. Critique product direction (§2), the journey (§3), the hero spec (§5), the visual/motion system (§6), and the sequence (§9). Cross-check current best practice online. Override anything weak. Two consecutive clean APPROVEs from independent context = locked.*
