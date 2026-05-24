# POLARIS — S-Tier Experience Plan v2 (I-ux-001 / #872)

**For:** Codex UNCAPPED review (iter 2). Rebuilt to address every iter-1 finding (`.codex/I-ux-001/codex_plan_verdict_iter1.txt`).
**Grounded in:** live running system (viewed `web/p2shots/audit/{01_home,02_intake,03_inspector}.png`), frontier-product research, and Codex iter-1's online cross-check.
**Decision authority:** Codex. Operator not consulted (full authorization 2026-05-24).

**What changed v1→v2 (per iter-1):** (a) moat re-stated — NOT "claims tied to sources" (Elicit/Scite/Consensus already do exact-quote citation) but **signed + independently-evaluated + per-sentence + offline-verifiable receipt + clinical-grade certainty**; (b) reframed from 8 routes → **one verified-brief workspace** (artifact-centric); (c) hero upgraded to a guided **"challenge any sentence"** chain-of-custody replay; (d) NEW **clinical evidence-quality (GRADE-like) layer**; (e) #871 moved to PARALLEL (not a hero blocker); (f) concrete component/motion/responsive/failure-state specs, offline-verify UX, counter-positioning table, interaction acceptance tests, PM demo script.

---

## 0. North Star (sharpened)

> **POLARIS is a verified-brief workspace: challenge any sentence and it proves itself — an independent evaluator's verdict, the resolved source span, a clinical-certainty read, and a signature you can verify offline.**

The moat is NOT "we cite sources" (competitors do that). The moat is the **chain of custody**: every sentence is (1) checked by a *different model family* than wrote it, (2) bound to a primary-source span, (3) graded for *clinical decision-safety* (not just textual support), and (4) sealed in a **signed bundle a third party can verify offline, with no POLARIS server**. No competitor ships that. The whole experience exists to make that chain *visible, interactive, and unforgettable*.

## 1. Honest competitor counter-positioning (what they do BETTER → how POLARIS answers)

| Competitor | What they genuinely do well | POLARIS's honest answer |
|---|---|---|
| **OpenEvidence** | Physician trust, point-of-care speed, daily habit; source-constrained | We're not point-of-care; we're the *defensible-decision* tool — independently-evaluated + signed + offline-verifiable, for a reviewer who must justify a call. |
| **ChatGPT / Gemini DR** | Editable plans, visible progress, polished visual reports, follow-up | We match plan+progress+follow-up, and add the one thing they can't: a per-sentence verdict from an independent family + a signed receipt. Length is their liability; provability is our advantage. |
| **Elicit** | Structured extraction tables; each cell quotes its source | We're a narrative brief (a policy reviewer reads prose, not a spreadsheet) where every sentence is independently verified + signed. |
| **Scite / Consensus** | Citation context/classification; evidence meter; claim/evidence tables | They grade the *literature's* agreement; we grade *our own generated sentence* against its span with an independent verdict + clinical-safety read. |
| **Perplexity (Spaces/Comet)** | Compounding workspaces; agentic tasks/browser | Our compounding surface is the topic knowledge-graph; our "agentic" is bounded + on-the-record (auditable), not open autonomy. |
| **Manus / Genspark** | Visible autonomous multi-tool execution ("wow") | We show agentic *rigor* (which guideline, which RCT, why rejected), not spectacle — because every step must be provable. |
| **FutureHouse** | Exposes agent reasoning trace for trust | We expose reasoning AND bind it to a signed, independently-evaluated, offline-verifiable receipt. |

*Defensible uniqueness, one line: signed + two-family-evaluated + per-sentence + clinical-grade + offline-verifiable. That is the visible product.*

## 2. The flagship artifact: ONE verified-brief workspace (artifact-centric, not route-centric)

iter-1 P0: the journey "still reads like 8 routes." Fix: there is **one object — the Verified Brief** — and the "pages" are *views/panels of that one object*, with a persistent mental model and shared chrome:
- **The Brief** (the artifact) contains: the prose report · the evidence set · the per-sentence proof chain · the clinical-certainty layer · the contradiction/follow-up graph · the signed receipt.
- **Views of the brief:** Read (report) · Challenge (proof replay) · Evidence (sources) · Map (graph) · Receipt (signed bundle / offline verify). One persistent header (the brief's identity + provenance verdict) across all views; switching views never loses the user's place or the claim they're inspecting.
- **Producing a brief:** Ask → Plan → Run → (brief opens). **Monitoring/tools** (dashboard, source-review, upload, memory, benchmark, contracts, pin-replay) are subordinate utilities, visually distinct from the brief workspace.
- A claim selected in Read stays selected in Challenge, Evidence, and Map. The artifact is the spine.

## 3. Product-direction decisions (confirmed + extended)

Confirmed by Codex iter-1 (do NOT pivot to chat):
- **Brief-first**, one-shot audit-grade artifact. **Claim-anchored follow-ups** (explicit actions, §6). **Compounding knowledge-graph** as the return surface (§9). **Bounded, on-the-record agentic rigor** (§8), not open autonomy.
- **NEW — clinical evidence-quality layer (§5)** is now a first-class product pillar, not an afterthought. Span-support ≠ decision-safety.

## 4. THE HERO — "Challenge any sentence" (chain-of-custody proof replay)

The single make-or-break interaction. Must be unforgettable, keyboard-first, mobile-real, instant.

**Resting state:** the brief reads as a clean clinical document. Each sentence carries a quiet verdict affordance (hairline tint by verdict color; a small chevron on focus — not noisy inline chips).

**Challenge a sentence** (click / tap / `J`-`K` to move, `Enter` to challenge):
A guided 4-beat reveal in a docked proof panel (desktop: right rail; mobile: bottom sheet):
1. **Claim** — the sentence lifts/echoes into the panel.
2. **Verdict** — the independent evaluator's verdict animates in: VERIFIED / PARTIAL / UNSUPPORTED, **with the evaluator family named** ("checked by an independent model family, not the writer") and the specific check (numeric match, ≥2 content-word overlap, span bounds).
3. **Source** — the primary-source span resolves: the source card settles, the exact span highlights (phrase-grouped, margin-annotated — not pink word tiles), with journal · year · DOI · tier · *why this source was selected*.
4. **Signature** — a human-readable chain-of-custody line: "This claim + span are sealed in bundle `…`, signed, verifiable offline." One click → Receipt view.

**At-a-glance brief verdict header (full provenance, not shallow counts):** claims (n) · verified / partial / unsupported (with unsupported *reasons*) · **independent-family result** · **signature state** · adequacy (tier mix: T1/T2/T3) · timestamp · model + version identity. A compact "provenance strip" always visible.

**Performance budget:** time-to-first-proof < 400ms from challenge; span highlight < 150ms; claim-to-claim switch < 120ms. Motion `prefers-reduced-motion`: instant state swap, no animation.

**Mobile/tablet:** tap a sentence → bottom-sheet proof panel; swipe between the 4 beats; no hover dependency anywhere.

**Home teaser:** a real verified claim from the existing real signed bundle, with a single "Challenge this sentence" that runs beats 1→4 inline — the 8-second "I've never seen research I could check like this" moment.

## 5. Clinical evidence-quality layer (NEW — iter-1 P0)

A senior reviewer needs *decision-safety*, not just "the sentence matches a span." Each claim and the brief carry:
- **Certainty** (GRADE-style: high/moderate/low/very-low) with the downgrade reasons (risk of bias, imprecision, indirectness, inconsistency, publication bias).
- **Evidence hierarchy / study type** per source: RCT vs guideline vs observational vs review (this is what #817 was about) — visibly distinguished.
- **Applicability / population fit** — does the evidence's population match the question's? Flag mismatch.
- **Harms / safety** surfaced alongside efficacy, never buried.
- **Conflict handling** — contradictory sources shown as a contradiction, with both sides + the contradiction panel (#749 exists).
- **Refusal/abort as a feature** — "the evidence base is inadequate to answer safely" is a *first-class, dignified* outcome, not an error page.

This layer is what makes POLARIS safe for a PM-office decision and is itself differentiating (no competitor grades its *own generated claim* for clinical certainty).

## 6. The journey (views of the one artifact) + failure-state design

land → ask → plan → run → **brief workspace opens** → challenge / follow-up → map → receipt. Each step's emotional beat per v1 §3, now with **designed failure states** (iter-1 missing-entirely):
- **Inadequate corpus** (#871 class): a dignified "we won't answer what the evidence can't support" screen — shows what was searched, why it fell short, and what would make it answerable. NOT a stack trace.
- **Partial evidence:** brief renders with explicit gaps marked.
- **Contradictory sources:** contradiction panel foregrounded.
- **Unsigned / signature-missing bundle:** clear, human-readable trust warning (never silent).

**Follow-up (claim-anchored, explicit UI — iter-1 P1):** from any challenged sentence: "Ask about this sentence" · "Challenge this source" · "Compare against guideline" · "Find contradicting evidence" — each preserves provenance and opens a new verified sub-answer.

## 7. Intake redesign (structural — iter-1 P1)

Not "fill empty space with a teaser." Rebuild as a **pre-flight that earns trust before spending a run:** big confident question field → **live scope interpretation** (how POLARIS reads the question, in plain clinical language) → **evidence-availability preview** (roughly what tiers/sources exist for this) → **source-policy summary** (what it will/won't include) → plain-language "here's what you'll get / what we won't claim." De-jargon entirely (no "refusal-bait", "PICO axis", bare "scope").

## 8. Plan review = source-strategy control surface (iter-1 P1)

Editable before any token spent: primary studies vs guidelines weighting · date range · **Canadian relevance** · endpoints of interest · explicit exclusions · minimum adequacy threshold. The Gemini-DR "editable plan" pattern, but clinical and provenance-aware.

## 9. Run progress = real evidence decisions, not theatre (iter-1 P1)

The legible rigor feed shows actual decisions: sources searched · sources **rejected (with reason)** · tier counts accumulating · adequacy gate (pass/fail against threshold) · generation · **per-sentence evaluator pass/fail** · recovery path on failure. Motion communicates state (Vercel status model), never decorates. Honest on abort.

## 10. Knowledge graph with a JOB (iter-1 P1)

Not a generic node cloud. Concrete jobs: **contradiction map** (which claims/sources conflict) · **treatment/effect timeline** · **source lineage** (what cites what) · **guideline links** · **follow-up paths** (where you branched). Compounds across runs in a topic = the return surface. Legible, navigable, mobile-real.

## 11. Receipt = guided offline-verify UX (iter-1 P0/P1)

Not a manifest dump. A **"verify this brief offline" guided flow**: download the signed bundle → human-readable receipt (what's sealed, by whom, when, two-family identities) → step-by-step "how your counsel verifies this with no POLARIS server" (the offline inspector #631) → the bundle hash + signature presented as *trust*, with hashes/IDs behind progressive disclosure under a plain-language trust summary.

## 12. Visual & motion system (concrete — iter-1 P0/P1)

Keep warm-editorial base + brand red `#c8102e` (LOCKED). Raise to Linear/Stripe/Vercel craft with **concrete specs** (the v1 hand-waving was the finding):
- **Type:** Geist; explicit scale (display 48/40, h1 32, h2 24, h3 20, body-lg 18, body 16, caption 14, mono 13) with line-heights + measure (62–72ch for brief prose).
- **Color = meaning only:** verdict palette (`--verified`/`--partial`(amber)/`--unsupported`(red)/`--refusal`); brand red = primary action + identity only; near-monochrome ground.
- **Density modes:** comfortable (reading) vs compact (evidence/dashboard tables) — explicit per surface.
- **Components (spec each: all six states + responsive + a11y):** verdict chip, source card (journal/year/DOI/tier/why-selected), proof panel, provenance strip, claim sentence, contradiction panel, certainty badge, run-progress row, empty/loading/error (stable skeletons, no dead ends — Vercel guideline), command bar (keyboard-first proof nav, Raycast-style).
- **Motion storyboards (exact what/why/when + reduced-motion equivalent):** (a) proof reveal 4-beat; (b) run-progress row advance; (c) source-card settle + span highlight; (d) verdict-header count change (count-up); (e) view transitions; (f) empty→content. Durations 120/200/320ms, `ease-standard`; all reduced-motion safe (instant swaps).
- **De-jargon trust language:** "two-family invariant"→"checked by an independent model family"; "Signature missing"→"⚠ This bundle is not signed — trust not established"; "POOL ID"→"Evidence set".
- **Maple-leaf mark:** production spec — crisp SVG (not dot-cloud), size/contrast rules, appears at sovereignty/identity beats only.
- **Trust material** lives in the proof surface + transparency page, not buried in the footer. "Canadian-hosted" gets an accessible disclosure distinguishing hosting/data (Canada) from US-routed LLM inference (disclosed).

## 13. Per-page targets — naming the structural REBUILDS (iter-1 P1)

| Surface | Now | Verdict | Scope |
|---|---|---|---|
| Home | B− | rebuild proof showcase | premium span render + inline "challenge" teaser; replace generic trio with concrete proof metrics + signed-receipt story |
| Intake | B− | **structural rebuild** (§7) | live scope interpretation + evidence preview + source policy |
| Plan | B | extend (§8) | source-strategy controls |
| Run progress | B | rebuild (§9) | real evidence decisions feed |
| Report = Proof Replay (hero) | B/B+ | **structural rebuild** (§4) | challenge-any-sentence chain-of-custody + clinical layer + provenance header |
| Inspector | B/B+ | **structural rebuild** | progressive-disclosure trust summary over hashes; same hero replay |
| Compare / follow-up | B | extend (§6) | explicit claim-anchored actions |
| Knowledge graph | B | **structural rebuild** (§10) | give it a job |
| Export/Receipt | B | **structural rebuild** (§11) | guided offline-verify flow |
| Source-review, dashboard, memory, benchmark, upload, contracts, pin-replay, sign-in | C–B | polish to system | subordinate; consistent components + motion + de-jargon |

## 14. Execution sequence (iter-1: prototype before code; #871 parallel)

1. **Design + motion foundation** + **Figma/motion prototype of the hero** (proof replay 4-beat) BEFORE implementation. Codex reviews the prototype (`-i`).
2. **Component system** (verdict chip, source card, proof panel, provenance strip, certainty badge, command bar, states) to spec.
3. **The hero** (Report/Inspector + Home teaser) — built against the **existing real signed bundle** (do NOT wait on #871).
4. **Clinical evidence-quality layer** woven into hero + report.
5. **Journey views** in flow order: Intake → Plan → Run-progress → Brief workspace → Follow-up/Compare → Map → Receipt, each with failure states.
6. **Supporting surfaces** to the system.
7. **#871 in PARALLEL** as a reliability blocker (hard prerequisite for the *live Carney demo*, not for building the proof experience).
8. **PM/policy demo script** (not just clinical curiosity) — the narrated walkthrough for the gift.

Each page: issue → brief → Codex brief review → build → **Codex 16-dim visual audit (`codex exec -i`, desktop+tablet+mobile matrix)** → Codex diff review → merge → redeploy → screenshot-verify LIVE → close.

## 15. Definition of S-tier + interaction acceptance (iter-1)

A surface is S-tier only when: (a) Codex 16-dim visual audit PASS via `codex exec -i` on desktop+tablet+mobile; (b) alive (motion storyboards implemented, all six microstates, reduced-motion safe); (c) zero internal jargon in user-facing copy; (d) WCAG 2.2 AA (axe 0) + keyboard-first proof nav; (e) coheres with the one-artifact model; (f) **interaction acceptance tests pass** (Playwright traces/videos, NOT just screenshots): time-to-first-proof < 400ms, time-to-verify-one-claim, full keyboard path, mobile tap path, reduced-motion path; (g) verified LIVE post-redeploy.

The initiative is done when every surface clears that bar, the verified-brief workspace feels like one artifact, the clinical-quality layer is present, the offline-verify flow works, and a real end-to-end run produces a real verified brief that renders through the hero (with #871 fixed for the live demo).

---
*Codex iter 2: verify v2 against your iter-1 findings (do not trust these change-claims — read the plan). Re-cross-check online. APPROVE only if this, executed faithfully, is frontier-beating + unforgettable + clinical-grade. Uncapped.*
