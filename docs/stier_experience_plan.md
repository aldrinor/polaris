# POLARIS — S-Tier Experience Plan v3 (I-ux-001 / #872)

**For:** Codex UNCAPPED review (iter 3). Rebuilt to address iter-2 (`codex_plan_verdict_iter2.txt`): iter-2 said direction is right; blockers were the clinical-safety method, regulatory/intended-use posture, and verifier-trust honesty.
**Decision authority:** Codex. Operator not consulted (full authorization 2026-05-24).

**v2→v3 changes (per iter-2):** (a) **two judgments separated everywhere** — *textual faithfulness* (sentence↔span, two-family-checked) vs *evidence strength / decision-safety* (outcome-level); (b) clinical layer rebuilt as a **real outcome-level Summary-of-Findings** (GRADE done correctly, not per-sentence) with abstention thresholds; (c) NEW **intended-use / regulatory posture + honest-limits** section (Health Canada/FDA/MHRA transparency principles; explicitly NON-device decision-support); (d) **verifier-trust honesty** — two-family stated with measured reliability + a "what this cannot prove" panel; (e) **anti-cherry-picking** source controls (locked defaults, receipt-logged deviations, sensitivity runs); (f) **execution-safe** offline verify (key identity/authority/rotation/revocation/pass-fail); (g) concrete **90-second PM demo script**; (h) Canadian source policy + assistive-tech accessibility testing.

---

## 0. North Star (sharpened — two judgments)

> **POLARIS is a verified-brief workspace that separates two questions a decision-maker must never confuse: "is this sentence faithful to its source?" and "is the evidence strong enough to act on?" — answers both, abstains when it can't, and seals the whole thing in a signature you can verify offline.**

The moat = **the chain of custody + the honesty of two separate judgments**: (1) *faithfulness* — every sentence bound to a primary-source span and cross-checked by a *different model family* than wrote it; (2) *evidence strength* — an outcome-level certainty read (GRADE-style) with harms, applicability, and downgrade reasons; sealed in a **signed bundle verifiable offline with no POLARIS server**, with explicit limits on what the verification does and does not prove. No competitor ships that combination — and crucially, none separates faithfulness from decision-safety, the exact confusion that is *lethal in clinical context*.

## 1. Honest competitor counter-positioning (what they do BETTER → our answer)

| Competitor | Does well | POLARIS's honest answer |
|---|---|---|
| **OpenEvidence** | Physician trust, point-of-care speed, daily habit, source-constrained | Not point-of-care; the *defensible-decision* tool — two judgments + signed + offline-verifiable, for a reviewer who must justify a call. |
| **ChatGPT / Gemini DR** | Editable plans, visible progress, polished reports, follow-up | Match those; add per-sentence independent verdict + evidence-strength read + signed receipt. Length is their liability; provability+honesty is ours. |
| **Elicit** | Structured extraction tables; cells quote sources | A narrative clinical brief (policy reviewers read prose) where every sentence is independently faithfulness-checked AND the evidence is graded. |
| **Scite / Consensus** | Citation context/classification; evidence meter; tables | They grade the *literature's* agreement; we grade *our own generated sentence's* faithfulness AND the evidence strength, separately. |
| **Perplexity (Spaces/Comet)** | Compounding workspaces; agentic tasks/browser | Compounding = topic knowledge-graph; "agentic" = bounded + on-the-record (auditable), not open autonomy. |
| **Manus / Genspark** | Visible autonomous multi-tool execution ("wow") | Show agentic *rigor* (which guideline, which RCT, why rejected), not spectacle — every step provable. |
| **FutureHouse** | Exposes agent reasoning trace | Reasoning AND a signed, independently-checked, offline-verifiable receipt with stated limits. |

*One line: signed + two-family-checked + per-sentence faithfulness + outcome-level evidence-strength + offline-verifiable + honest about its limits.*

## 2. The flagship artifact: ONE verified-brief workspace (artifact-centric)

One object — **the Verified Brief** — with views, not 8 routes. It contains: prose report · evidence set · per-sentence faithfulness chain · outcome-level evidence-strength layer · contradiction/follow-up graph · signed receipt. **Views:** Read · Challenge · Evidence · Map · Receipt. One persistent header (brief identity + dual-provenance verdict) across views; a claim selected in one view stays selected in all. Producing a brief: Ask → Plan → Run → (brief opens). Monitoring/tools (dashboard, source-review, upload, memory, benchmark, contracts, pin-replay) are subordinate utilities.

## 3. Product-direction decisions (confirmed)

Brief-first one-shot artifact; claim-anchored follow-ups; compounding knowledge-graph as return surface; bounded on-the-record agentic rigor. NOT chat (confirmed iter-1/2). The clinical evidence-strength layer (§5) and intended-use posture (§6) are now first-class pillars.

## 4. THE HERO — "Challenge any sentence" (two judgments, chain-of-custody)

The make-or-break interaction. Keyboard-first, mobile-real, instant. Crucially it shows **two distinct judgments**, never blurred.

**Resting state:** clean clinical document; each sentence a quiet faithfulness affordance (hairline tint), plus a small evidence-strength marker (certainty dot) — visually distinct so the two are never confused.

**Challenge a sentence** (click / tap / `J`/`K` move, `Enter` challenge) → docked proof panel (desktop right rail; mobile bottom sheet), guided beats:
1. **Claim** — the sentence echoes into the panel.
2. **Faithfulness verdict** — VERIFIED / PARTIAL / UNSUPPORTED, *labeled as "Is this sentence faithful to the source?"*, naming the independent evaluator family + the deterministic checks (numeric match, ≥2 content-word overlap, span bounds). 
3. **Evidence strength** — a *separately labeled* read: "How strong is the underlying evidence?" — certainty (high/moderate/low/very-low) + the dominant downgrade reason + study type (RCT/guideline/observational) + population/applicability fit. Links to the outcome-level Summary of Findings (§5).
4. **Source** — span resolves (phrase-grouped, margin-annotated; journal · year · DOI · tier · why selected).
5. **Signature** — human-readable chain-of-custody: sealed in bundle `…`, signed by `<authority>`, verifiable offline → Receipt view.
6. **"What this does NOT prove"** — an always-available affordance: faithfulness ≠ correctness of the source; independent-family check ≠ clinical validation; certainty is decision-support input, not a formal guideline.

**Dual-provenance header (full):** claims (n) · faithful: verified/partial/unsupported (+reasons) · independent-family result · **evidence-strength mix** (high/mod/low/very-low counts) · adequacy + tier mix (T1/T2/T3) · signature state · timestamp · model+version. Always-visible provenance strip.

**Perf budget:** time-to-first-proof <400ms; span highlight <150ms; claim switch <120ms. `prefers-reduced-motion`: instant swaps.

**Home teaser:** a real verified claim from the existing real signed bundle; one "Challenge this sentence" runs beats 1→6 inline — the 8-second "I've never seen research I could check *and* gauge like this" moment.

## 5. Clinical evidence-strength layer — done correctly (iter-2 P0)

GRADE certainty is **outcome-level across a body of evidence**, NOT per-sentence. So:
- **Summary of Findings (SoF), per OUTCOME** (e.g. "HbA1c reduction", "serious adverse events"): absolute + relative effect with CI, number of studies/participants, study designs, and **certainty (high/moderate/low/very-low)** with explicit **downgrade domains** (risk of bias, inconsistency, indirectness, imprecision, publication bias) and any upgrade (large effect, dose-response).
- **Harms surfaced alongside efficacy**, never buried; **applicability/population fit** (incl. Canadian relevance) flagged on mismatch; **evidence hierarchy** (RCT vs guideline vs observational) visibly distinguished (this is what #817 addressed in retrieval).
- **Honest scope of automation:** POLARIS *surfaces the inputs* to a GRADE assessment and presents a structured SoF view + a per-claim certainty read **when supportable**; it does NOT claim to replace a formal GRADE appraisal by the reviewer. Labeled as decision-support input.
- **Abstention thresholds:** below a defined adequacy/certainty floor, POLARIS abstains ("the evidence base cannot support a safe answer") — a dignified first-class outcome, not an error (the #871 class).
- **Decision context (EtD-aware, lightweight):** where relevant, note benefits/harms balance and values/applicability caveats so a sentence that is *faithful* is never mistaken for *sufficient to act on*.

## 6. Intended-use, regulatory posture & honest limits (NEW — iter-2 P0)

A standing, visible **intended-use statement** (on the brief, the receipt, and /transparency):
- **Intended user:** senior policy/clinical reviewers in an institutional setting (e.g. a PM's office) for *research decision-support*.
- **Intended use:** produce auditable, source-bound evidence briefs to *inform* expert review.
- **NOT intended:** point-of-care diagnosis/treatment, a medical device / regulated clinical decision support, or a substitute for clinician/expert judgment. **Non-reliance language** explicit.
- **Knowns/unknowns + data quality:** what sources were and were not searched, recency, and the limits of automated retrieval/extraction.
- **Evaluator validation posture:** the two-family check is an *independence/consistency* mechanism with measured reliability and stated limits (§7) — not regulatory validation.
- **Canadian-population applicability** explicitly addressed.
- Designed to the **Health Canada/FDA/MHRA transparency guiding principles** (clear intended use, the logic/basis of outputs, validation, independent review of the basis) — adopting the *principles* for trust, while clearly positioned as a non-device research tool.

## 7. Verifier-trust honesty (iter-2 P1)

Present the verification truthfully so "two-family" never becomes a new overclaim:
- **Deterministic checks** (numeric match, span bounds, content-word overlap) shown as *mechanical* facts.
- **Two-family independent check** shown as an *independence/consistency* signal with **measured reliability** (evaluator accuracy/agreement metrics, calibration examples) and **disagreement handling** (what happens when families disagree).
- **A persistent "what this verifier cannot prove" panel:** faithfulness ≠ source correctness; independence ≠ clinical validation; absence of contradiction ≠ completeness.

## 8. Intake → Plan: source strategy with anti-cherry-picking guardrails (iter-2 P1)

- **Intake** = a pre-flight that earns trust: confident question field → live scope interpretation (plain clinical language) → evidence-availability preview → source-policy summary → "what you'll get / won't claim." De-jargoned.
- **Plan = controlled, not gameable:** editable controls (primary vs guidelines, date range, **Canadian relevance**, endpoints, exclusions, min adequacy) **but with LOCKED conservative defaults**; **every deviation from default is visible and recorded in the receipt**; offer **sensitivity runs** (does the conclusion survive stricter inclusion?); all inclusion/exclusion logged. Cherry-picking is structurally discouraged and always on the record.
- **Canadian clinical source policy (explicit):** CADTH, Health Canada labels/advisories, Canadian guidelines where available; define when non-Canadian evidence (NICE/FDA/EMA/WHO/Cochrane) is acceptable and how it's flagged for applicability.

## 9. Run progress = real evidence decisions (iter-1 P1)

Legible rigor feed of actual decisions: sources searched · rejected (with reason) · tier counts · adequacy gate vs threshold · generation · per-sentence faithfulness pass/fail · recovery path. Motion communicates state (Vercel model), never decorates. Honest abort.

## 10. Knowledge graph with a JOB (iter-1 P1)

Concrete jobs: contradiction map · treatment/effect timeline · source lineage · guideline links · follow-up paths. Compounds across runs in a topic = return surface. Legible, navigable, mobile-real.

## 11. Receipt = execution-safe offline-verify UX (iter-2 P1)

A guided "verify this brief offline" flow, execution-safe:
- **Human-readable receipt:** what's sealed, by whom, when, the two-family identities, the intended-use statement.
- **Key/signature semantics:** signing **key identity + signing authority**, key **rotation/revocation** state, explicit **pass/fail** states, and clear **"signature missing / not established"** copy (never silent).
- **Dry-run verifier path:** the exact steps + the offline inspector (#631) + a CLI verifier script path so a third party verifies with no POLARIS server.
- Hashes/IDs behind progressive disclosure under a plain-language trust summary.

## 12. Visual & motion system (concrete — iter-1/2)

Warm-editorial base + brand red `#c8102e` (LOCKED) → Linear/Stripe/Vercel craft:
- **Type:** Geist; scale display 48/40, h1 32, h2 24, h3 20, body-lg 18, body 16, caption 14, mono 13; measure 62–72ch for prose.
- **Color = meaning:** **two distinct visual languages** — faithfulness verdict palette (`--verified`/`--partial`/`--unsupported`) and evidence-strength (certainty) scale, never the same swatch (so the two judgments read as different). Brand red = primary action + identity only.
- **Density modes:** comfortable (reading) vs compact (evidence/SoF tables).
- **Components (each: six states + responsive + a11y):** faithfulness chip, certainty badge, source card (journal/year/DOI/tier/why), proof panel (6 beats), dual-provenance strip, SoF table row, contradiction panel, run-progress row, "what-this-can't-prove" panel, intended-use banner, empty/loading/error (stable skeletons, no dead ends), command bar (keyboard-first nav, Raycast-style).
- **Motion storyboards (frame-level what/why/when + reduced-motion equivalent):** (a) 6-beat proof reveal — frame timing per beat; (b) run-progress advance; (c) source settle + phrase-grouped highlight; (d) provenance count-up; (e) view transitions; (f) empty→content. Durations 120/200/320ms, `ease-standard`; motion communicates state, never ornamental.
- **De-jargon trust copy:** "two-family invariant"→"checked by an independent model family"; "Signature missing"→"⚠ Not signed — trust not established"; "POOL ID"→"Evidence set".
- **Maple-leaf:** crisp SVG production spec (size/contrast/placement), sovereignty beats only. **"Canadian-hosted"** accessible disclosure distinguishing hosting/data (Canada) from US-routed LLM inference.
- **Trust material** lives in the proof surface + /transparency + intended-use banner, not the footer.

## 13. Per-page targets (naming structural rebuilds)

| Surface | Now | Verdict | Scope |
|---|---|---|---|
| Home | B− | rebuild showcase | premium span + inline "challenge" teaser (6 beats); concrete proof metrics + signed-receipt + intended-use line |
| Intake | B− | **structural rebuild** (§8) | scope interpretation + evidence preview + source policy |
| Plan | B | rebuild (§8) | controlled source strategy, locked defaults, receipt-logged deviations |
| Run progress | B | rebuild (§9) | real evidence-decision feed |
| Report = Proof Replay (hero) | B/B+ | **structural rebuild** (§4,§5) | two-judgment chain-of-custody + SoF + dual-provenance header |
| Inspector | B/B+ | **structural rebuild** (§7,§11) | progressive-disclosure trust summary; same hero + verifier-honesty |
| Compare / follow-up | B | extend (§4 follow-ups) | explicit claim-anchored actions |
| Knowledge graph | B | **structural rebuild** (§10) | give it a job |
| Export/Receipt | B | **structural rebuild** (§11) | execution-safe offline-verify |
| Source-review, dashboard, memory, benchmark, upload, contracts, pin-replay, sign-in | C–B | polish to system | subordinate; consistent components + motion + de-jargon |

## 14. Execution sequence + the actual PM demo script (iter-1/2)

1. Design + motion foundation + **Figma/motion prototype of the hero** (6-beat) BEFORE code; Codex reviews the prototype (`-i`).
2. Component system to spec (incl. SoF row, certainty badge, what-can't-prove panel, intended-use banner).
3. **Hero** (Report/Inspector + Home teaser) against the **existing real signed bundle** (do NOT wait on #871).
4. **Clinical evidence-strength layer + intended-use posture + verifier-honesty** woven in.
5. **Journey views** in flow order, each with failure states (inadequate/partial/contradictory/unsigned).
6. Supporting surfaces to the system.
7. **#871 in PARALLEL** (reliability blocker for the *live* demo, not for building the experience).
8. **PM/policy 90-second demo script** (concrete):
   - 0:00 Land → "challenge this sentence" on a real verified claim (faithfulness ✓ + evidence-strength read).
   - 0:25 Show one **PARTIAL/UNSUPPORTED** claim — POLARIS is honest about what it can't support.
   - 0:45 Show one **inadequacy refusal** — "the evidence can't safely answer this" as a feature.
   - 1:05 Open the **Summary of Findings** for an outcome (certainty + harms + applicability).
   - 1:25 **Offline receipt handoff** — "your counsel verifies this with no POLARIS server."

Each page: issue → brief → Codex brief review → build → Codex 16-dim visual audit (`codex exec -i`, desktop+tablet+mobile) → Codex diff review → merge → redeploy → screenshot-verify LIVE → close.

## 15. Definition of S-tier + acceptance (iter-1/2)

S-tier per surface: (a) Codex 16-dim visual audit PASS via `codex exec -i` (desktop+tablet+mobile); (b) alive (motion storyboards implemented, six microstates, reduced-motion safe); (c) zero internal jargon; (d) WCAG 2.2 AA — **axe 0 AND real assistive-tech testing** (screen reader + keyboard), per Canada Digital Standards + WCAG 2.2; (e) coheres with the one-artifact, two-judgment model; (f) **interaction acceptance tests** (Playwright traces/videos): time-to-first-proof <400ms, time-to-verify-one-claim, keyboard path, mobile tap path, reduced-motion path; (g) the **two judgments are never visually conflated** and the "what this can't prove" + intended-use statements are present; (h) verified LIVE post-redeploy.

Initiative done when: every surface clears the bar; the workspace reads as one artifact; faithfulness and evidence-strength are cleanly separated and honest; intended-use + verifier limits are explicit; offline-verify works execution-safe; and a real end-to-end run produces a real verified brief through the hero (#871 fixed for the live demo).

---
*Codex iter 3: verify v3 against iter-2 P0/P1 (don't trust change-claims — read the plan). Re-cross-check online (esp. GRADE/SoF method + Health Canada/FDA transparency). APPROVE only if frontier-beating, unforgettable, clinical-SAFE, honest, and one coherent artifact. Uncapped.*
