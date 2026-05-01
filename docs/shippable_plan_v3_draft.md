# POLARIS shippable plan v3 — incorporating Codex v2 review findings

**Status:** Revision after Codex v2 review verdict "not ready." Specific findings applied. Re-sending to Codex for v3 review.

**Changes from v2 draft (in plain language):**
- Dropped Flow 3 (live audit spectacle) and Flow 5 (standalone contradictions) from MVP per Codex's "stronger pilot" recommendation. Contradictions become click-through badges inside the report view, not a separate flow. Live audit is deferred to v2.5.
- Added Flow 5: deployment / install / account / sharing reality (Codex flagged this as load-bearing, not peripheral).
- Replaced every "any" with a defined adversarial test corpus.
- Tightened Layer 3 evaluator definition: named individual outside build/plan loop, fresh account, recorded sessions, fail authority.
- Walkthrough cadence: 3 per flow at end-of-sprint, not week-5-only.
- Bundle contains source text + span (not just URL) for offline verifiability.
- Empty states required for every flow.
- Multi-span claims, typed numbers handled explicitly.
- Timeline revised to 8-12 weeks.
- False unblock removed (refusal copy no longer promises out-of-scope UI).

---

## North star (unchanged)

For sovereign deep-research buyers (regulatory writers, compliance leads, government analysts) who need locally-deployable, audit-traceable research where every claim is provable, every contradiction is surfaced, and every refusal is explained.

The product is **a deep research agent that shows its work and refuses what it can't answer**. Substrate exists; visibility doesn't. This plan ships the visibility.

## The defined adversarial test corpus (replaces every "any" in v2)

This corpus is the test bench. Layer 3 walkthroughs use these inputs, NOT curated demo prompts. The corpus is added to before each sprint with new adversarial cases discovered during the prior walkthrough.

**Inputs the system must handle correctly:**

| Class | Example | Expected outcome |
|---|---|---|
| Clear template match | "Efficacy and safety of tirzepatide for T2D" | Routes to clinical drug audit; runs |
| Acronym-only ambiguous (BPEI-class) | "What is BPEI?" | Disambiguation: shows candidate meanings, asks user to pick |
| Multi-intent paragraph | "Tell me about tirzepatide AND ozempic AND any cardiovascular risks" | Either splits into separate runs or refuses with "single-topic only" + suggests how to refine |
| Out-of-scope but adjacent | "Best supplement stack for T2D" | Refusal: "POLARIS does not handle non-regulated interventions; closest match: clinical drug audit (60% confidence)" |
| Out-of-scope and unrelated | "Recipe for sourdough" | Refusal: "Outside POLARIS scope. POLARIS handles: clinical drug audits, regulatory analysis. Browse templates." |
| Threshold edge (49% template confidence) | "GLP-1 mechanism in muscle composition" | Either accept with confidence shown or refuse with explicit threshold value and suggest manual template selection |
| Insufficient corpus | A real obscure drug-condition pair with <5 T1 sources | Refusal: "Need 5 T1 sources, found 2. Specific gap: no head-to-head trials. Try in 6 months." |
| Non-English / mixed | "Eficacia de tirzepatida en DM2" | Either accept (if supported) or refuse with explicit "Spanish not supported in v1; English only." |
| Pasted email with embedded query | A 200-word email asking 3 questions | Detect non-question structure, ask user to extract the actual question |
| Mobile narrow viewport | Same query on 375px width | All flows usable, no overflow, click targets ≥44px |
| JS disabled | Any query | Graceful degradation message, not white screen |

**Corpus targets for content (Flow 4 must handle):**

| Class | Example | Expected behavior |
|---|---|---|
| Standard 50-sentence report | Tirzepatide T2D | All sentences clickable, evidence pane <1s, two-family signal visible |
| Long 200+ sentence report | Multi-trial oncology query | Click-through latency stays <1s, scroll-anchor preserved on click |
| Zero contradictions | Query with consensus | Empty-state copy: "no contradictions detected — sources agreed on all numeric claims" |
| 50+ contradictions | Highly contested topic | Contradiction badges sorted by claim severity; not noise |
| T1 vs T1 conflict | Two equally-tier sources disagree | UI does not adjudicate; shows both with sample sizes / contexts |
| Multi-span claim | Sentence supported by 3 spans | Evidence pane shows all 3 spans, all 3 sources, all 3 tiers |
| Paywalled span | Source URL behind paywall | Bundle includes extracted span text; UI shows "source paywalled — full text unavailable" but span is in bundle |
| Multi-evidence number | "5.2%" cited from 4 sources, range 4.7-5.8% | Click number → cross-reference panel showing all 4 values + tiers |
| Two-family disagreement | Generator says X, evaluator says Y | Visible warning badge on the affected claim |

**This corpus is the test bench. "Works for the test corpus" replaces "works for any run."**

## Four user flows — truly shippable, browser-only

### Flow 1 — Scope discovery (BPEI prevention layer)

**User:** lands on dashboard.
**Outcome:** within 30 seconds knows what POLARIS can and cannot answer for their use case.

**Visible elements:**
- 3 templates with display name, scope summary, 3-5 in-scope examples each, 3 out-of-scope examples each
- Below: query input that **suggests the matching template as the user types** (debounced)
- If no template matches: "no template found — POLARIS may refuse this query. Browse scope or refine."
- If multiple match: shows top 2 with confidence scores
- Mobile: stack layout, all interactive elements ≥44px

**Acceptance:**
- Layer 3 evaluator (defined below) on a fresh account passes the corpus inputs above for Flow 1 — for each, can predict before submitting whether POLARIS will accept, refuse, or ask for disambiguation
- 3 walkthroughs by 3 different evaluators per sprint end
- Empty state: if there are 0 templates available, page shows "POLARIS has no active templates — contact admin"
- All copy passes a "could a non-developer act on this?" review by an evaluator

**Crown jewel:** scope visibility before failure.
**Substrate:** ✅ `/api/inspector/templates/catalog`
**Build:** discovery panel + live template-suggestion + mobile layout + empty state.

---

### Flow 2 — Scope gate, refusal, disambiguation

**User:** submits a query.
**Outcome:** sees a correct, explainable, actionable outcome for every input class.

**Behaviors by input class** (matching the corpus):

| Class | UI behavior |
|---|---|
| Clear match | "Routing to [template name] — running. (Cancel)" → proceeds to Flow 3 |
| Ambiguous acronym | Modal: "Multiple candidate meanings — pick one or rephrase: [(a) syndrome, (b) institute, (c) chemical]" |
| Multi-intent | "Multiple questions detected; POLARIS handles one at a time. Pick: [list of detected sub-questions] or rephrase." |
| Out-of-scope adjacent | "Cannot answer with current templates. Closest match: [template] at 60% confidence. Choose: [Run with this template anyway / Refine query / Browse scope]" |
| Out-of-scope unrelated | "Outside POLARIS scope. POLARIS does: [bulleted scope summary]. [Browse templates]" |
| Threshold edge | "Template confidence 49% (threshold 50%). Choose: [Run anyway / Refine / Cancel]" |
| Insufficient corpus | "Cannot answer — found 2 T1 sources, need 5. Specific gap: [named gap]. [What this means / Try in 6 months / Cancel]" — does NOT promise unavailable upload UI |
| Non-English | "[Language] not supported in v1. [Submit in English / Cancel]" |

**Acceptance:**
- Each class above passes Layer 3 walkthrough by 3 evaluators
- Refusal copy is human-readable; numeric thresholds shown only as supporting detail, not as primary message
- "Run anyway" button preserves user intent and proceeds to Flow 3 with explicit warning banner
- "Refine" preserves the prior query in the input (no retyping)
- Empty states: no UI promises actions that aren't built (no "upload" if upload UI is out of scope)

**Crown jewel:** refusal-with-explanation as a first-class outcome; ambiguity disambiguation.
**Substrate:** ✅ abort statuses (6 distinct); ⚠️ ambiguity detector (NEW — must cluster retrieval candidates by primary entity before synthesis).
**Build:** ambiguity detector; refusal view with class-specific copy; "run anyway" path; "refine" path; multi-intent splitter.

---

### Flow 3 (was Flow 4) — Report inspection with click-through audit

**User:** has a completed run; opens the report.
**Outcome:** can trace any claim to its evidence in 2 clicks; sees gaps, contradictions, two-family disagreements without searching.

**Visible elements:**
- **Top of report (lead, not appendix):** Frame coverage panel — "Got 14 of 15 contract-required entities. 1 gap: SURPASS-CVOT (paywalled, no OA). [What this means / What would unblock]"
- **Body:** report renders with subtle hover-highlight on every claim sentence
- **Click any sentence:** side pane opens (within 1s) showing:
  - All evidence spans for the claim (multi-span support: shows ALL spans, not just one)
  - For each span: source title, URL, tier (T1-T7) with rationale, retrieval trace (which retriever, which query, fetch timestamp), evaluator agreement signal, paywall flag if applicable
- **Click any number:** cross-reference panel showing all values from all sources for the same claim, with tiers — typed by:
  - Percentage (e.g., HbA1c reduction): cross-ref with 95% CI when available
  - Sample size (N): no cross-ref, single source only
  - p-value: shown in context, no cross-ref
  - Year: shown in context, no cross-ref
  - Dose: cross-ref with all dose levels in evidence pool
- **Contradiction badges (replaces v2 Flow 5):** every flagged contradiction has an inline badge `⚠ 3 sources disagree`. Click → opens side pane with all sides, tiers, sample sizes, hedge language POLARIS used. Per-flag PT08 enumeration shown.
- **Two-family disagreement badge:** when generator and evaluator disagree, claim shows `⚠ Internal evaluator flagged this claim`. Click → side pane shows the disagreement detail.

**Acceptance (against the defined corpus):**
- Standard 50-sentence report: all sentences clickable, evidence pane <1s, frame coverage visible above the fold
- 200+ sentence report: latency stays <1s on hover/click; scroll-anchor preserved when side pane opens
- Zero-contradictions report: explicit empty-state copy ("no contradictions detected"), not just absence of badges
- T1-vs-T1 conflict: side pane does NOT adjudicate; shows both with sample sizes/contexts; no false hierarchy implied
- Multi-span claim: side pane shows ALL spans, not just first
- Paywalled span: span text from bundle is shown; UI clearly marks "source full text not retrievable; extracted span shown"
- Multi-evidence number: cross-ref shows all values; if single-source, panel shows "this number cited from 1 source only"
- Two-family disagreement: badge visible; click reveals the specific disagreement
- Layer 3 walkthrough: 3 evaluators independently navigate each corpus class without coaching

**Crown jewels:** complete provenance trail; gap transparency as lead; two-family signal; contradiction navigability.
**Substrate:** ✅ provenance tokens, frame coverage manifest, verification_details, two-family scoring, contradiction detector, hedging
**Build:** generalized Inspector view (works for ANY run in the corpus, not just canned tirzepatide); frame coverage promoted; two-family surfaced; typed number cross-ref; contradiction badges + side pane; multi-span pane; paywalled-span flagged display.

---

### Flow 4 (was Flow 6) — Audit bundle export with embedded source text

**User:** has a completed run; needs to deliver to compliance / regulator / customer.
**Outcome:** downloads a self-contained, offline-verifiable archive.

**Visible elements:**
- "Download audit bundle" button visible above the fold on every report page
- Click → preview pane lists contents:
  - `report.md` — the prose
  - `bibliography.json` — all sources with tiers
  - `evidence_pool.json` — all retrieved spans **with extracted text** (not just URLs)
  - `manifest.json` — run summary, gates, statuses
  - `frame_coverage.json` — entities expected vs got, gap reasons
  - `verification_details.json` — per-sentence strict_verify, two-family scoring
  - `contradictions.json` — per-flag enumeration with side-by-side tiers
  - `decision_telemetry.json` — every gate decision with timestamp
  - `methodology.md` — how POLARIS works, for the reviewer
  - `README.md` — guide for the recipient (non-developer); includes "how to verify any claim from this bundle" walkthrough
- Confirm → zip downloads with progress bar + size warning if >100MB
- Bundle is **standalone**: a recipient with no POLARIS account can open it and trace any claim from the report back to its source span text — even if the source URL is now dead

**Acceptance (against the corpus):**
- Bundle download works for every corpus run, not just curated examples
- Third-party tester (no POLARIS access, fresh laptop) opens the zip and traces a randomly selected claim back to its evidence span text in <5 minutes, with no instruction beyond the README
- Paywalled source: bundle still verifiable because span text is embedded
- 500MB bundle: download progress visible; resumable on connection drop
- Partial run / run aborted: export exists but bundle is clearly marked "PARTIAL — abort_reason: [name]"; bundle is still verifiable for whatever DID complete
- README guides a regulatory reviewer through "verify a claim from this bundle" without prior product training
- Empty state: if a run has no claims (zero-verified abort), bundle still exports but is named `*_aborted_*.zip` and contains the manifest + reason, not a fake report

**Crown jewel:** provenance as deliverable.
**Substrate:** ✅ `/api/inspector/runs/{slug}/audit-bundle.zip`
**Build:** button + preview + completeness pass (embed span text); progress UI; partial-run handling; reviewer README; standalone-verification test.

---

### Flow 5 (NEW per Codex) — Deployment / install / account / sharing reality

**User:** is a sovereign-buyer admin or end-user dealing with the product as software they'll actually run.
**Outcome:** can install POLARIS on their hardware, set up at least one account, share a report bundle, and know how to get help — without contacting the vendor.

**Visible elements:**
- Public docs site reachable at `/docs` showing:
  - Hardware requirements (CPU/GPU/RAM/disk for sovereign profile)
  - Step-by-step install via Docker compose with one tested topology
  - First-run setup: create org, create first user, generate API key, invite second user
  - "Share an audit bundle" guide
  - Support: where to send issues (initially: a real email address, not a TODO)
- In-app: signed-in users can:
  - Sign in with email/password (existing)
  - Invite a teammate via email link (basic — no SAML)
  - Generate an API key (existing endpoint, needs UI)
  - View their own runs only (basic auth scoping)
  - Share a bundle via download URL with expiry (no SaaS-style sharing required)

**Acceptance:**
- Layer 3 evaluator on a NEW machine, with no prior POLARIS context, follows install docs and reaches a working dashboard within 60 minutes
- Same evaluator creates account, runs first query, downloads bundle, shares with a colleague who can open it
- Hardware requirements doc names the specific tested topology; "should work" is not enough — must be "tested on this hardware, this date, this Docker version"
- Support email is a real inbox monitored by a real human

**Crown jewel:** the product is actually deployable, not just demoable.
**Substrate:** ✅ Dockerfile + docker-compose.yml + Helm chart; ✅ auth backend; ⚠️ docs are stale or missing
**Build:** docs site; tested install runbook; UI surface for invite + API key + run-list-scoped-to-user; bundle share URL with expiry.

---

## Acceptance bar (tightened per Codex)

Each flow ships when ALL of these hold:

| Requirement | Definition |
|---|---|
| Fresh state | New account, no cached data, default config |
| Production-like environment | Not dev-mode; runs against real retrieval, real models, real budget |
| No direct API calls | Walkthrough is browser-only; no curl, no JWT in console |
| Defined adversarial corpus | The corpus above; not curated demo prompts |
| All input classes | Supported, unsupported, ambiguous, failing — every class for the flow's input space |
| 3 walkthroughs per flow | At end of sprint, by 3 different evaluators (defined below) |
| Independent evaluator | Layer 3: named individual NOT in build team, NOT in planning loop, NOT Claude, NOT Codex; domain-literate; with formal authority to FAIL the gate |
| Recorded session | Raw screen + audio; no live explanations during recording |
| Codex code review | Layer 1 GREEN |
| Codex user-flow review | Layer 2: P0/P1 findings addressed |
| User sign-off after walkthrough | Final acceptance |

**Codex GREEN alone is NOT done. One walkthrough alone is NOT done. Even all three review layers passing on a curated demo is NOT done — the corpus is the bench.**

## Layer 3 evaluator: enforceable definition (per Codex's #1 finding)

The evaluator must be:

- **Outside** the build team, the planning loop, Claude, and Codex
- **Domain-literate** for the buyer segment (e.g., a regulatory writer, a clinical research operations person, a compliance lead — depending on chosen segment)
- Either:
  - (a) A specific real prospect/buyer with whom we have an active conversation, OR
  - (b) A paid contractor (~$200-500/walkthrough hour, contracted for 10-20h across 3 sprints), OR
  - (c) An internal-but-non-build employee with formal authority and recorded sessions
- Equipped with: fresh account, uncoached inputs from the corpus + at least one of their own real questions, no prior product training beyond the README
- **Formally empowered to fail the gate.** A failed walkthrough means the flow does not ship that sprint. No verbal explanations are accepted post-recording.

**This is the single most important plan input. Without it, the plan is not real.**

## Sequencing — corrected per Codex

**Sprint 1 (weeks 1-3): BPEI spine + report scaffolding.**
Flow 1 (discovery) + Flow 2 (refusal/disambiguation) + minimum viable report rendering for Flow 2's "run anyway" / accepted queries to land on. Flow 3's full inspection NOT in Sprint 1 — only enough rendering to test that accepted queries reach a page.

**Sprint 2 (weeks 4-6): Inspection + audit bundle.**
Flow 3 (report inspection with click-through audit, frame coverage as lead, two-family signal, contradictions, multi-span, typed numbers) + Flow 4 (audit bundle with embedded source text). Sprint 1 walkthrough findings folded in.

**Sprint 3 (weeks 7-9): Deployment reality + adversarial walkthrough across all 4 flows.**
Flow 5 (install, account, share, support) + 3 independent Layer 3 walkthroughs across all flows + final regression.

**Sprint 4 (weeks 10-12): Buffer for adversarial findings.**
Per Codex: walkthrough discoveries can require rebuild; ~30-50% buffer needed. This sprint exists to absorb that without slipping.

**Total: 8-12 weeks of focused engineering** (not 5). Codex range; lower bound is optimistic.

## Live audit (was Flow 3 in v2) — explicitly deferred to v2.5

Per Codex: in 5-12 weeks under deadline pressure, "watch POLARIS think" degrades into a timestamped log dump. That's not the product. Live progress is rendered as a single status bar + cancel button in v2 — not the full streaming reasoning UI. The crown jewel "visible reasoning at every step" is delivered through Flow 3's post-hoc inspection, not in-flight streaming. v2.5 can layer streaming on top once the substrate is honest.

## Out of scope (intentionally deferred — these are NOT v2 ship)

- Pin replay UI / "what changed since last run" (M-D11)
- Source admissibility decision tree (Codex flagged as possibly load-bearing for sovereign buyers — moved to "v2.5 candidate; Layer 3 evaluator confirms whether buyer asks for it")
- Python execution flow (charts on retrieved data)
- Q&A on completed report
- Citation freshness alerts
- Comparative multi-jurisdiction view
- Operator review queue UI
- Billing/quota UI
- Drive connector UI
- Slide deck export UI
- Contract drafting UI
- Support tickets UI
- Operator dashboard UI
- Pricing page UI

## Anti-patterns refused even if asked

- "Just iterate until Codex GREEN"
- "Backend exists = done"
- "While we're at it..."
- "Re-enter the autoloop"
- 113-milestone tasking
- "Works for any run" without a defined corpus
- Layer 3 walkthrough by anyone in the build/planning loop

## Blockers — must be resolved by user before Sprint 1 starts

These cannot be planned around:

1. **Layer 3 evaluator named.** Specific person, contracted/assigned, with fail authority. Without this, Sprint 1 cannot honestly start.
2. **Buyer segment confirmed.** Pharma R&D / government / legal / compliance — affects which 3 templates we sharpen first.
3. **Hardware target for sovereign deployment.** Sets model size for the install runbook.
4. **Pilot deadline.** Decides whether 8-12 weeks fits or whether scope must narrow further.

**If any of these are unanswered, the plan is on paper only.**

---

**Next step:** send to Codex for v3 review, asking specifically: did v3 address the v2 findings? Did revising introduce new failure modes? What's still phantom-completion-vulnerable?
