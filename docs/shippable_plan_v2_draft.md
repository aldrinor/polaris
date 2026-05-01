# POLARIS shippable plan v2 — reasoning visible at every step (DRAFT)

**Status:** Draft for Codex adversarial review. Not yet final. Not yet user-approved.

## North star

For sovereign deep-research buyers (regulatory writers, compliance leads, government analysts, regulated-industry research teams) who need:
- Locally-deployable research (incumbents can't ship on-prem)
- Audit-traceable claims (every sentence cites its evidence span)
- Surfaced contradictions (no averaging-away)
- Honest refusals (refuse on ambiguity, explain why, suggest unblock)
- Reasoning visible at every step (watch POLARIS think, not a spinner)

The product is **a deep research agent that shows its work**. The substrate exists. The visibility doesn't. This plan ships the visibility.

## Six user flows — truly shippable, browser-only, no curl

### Flow 1 — Scope discovery (the BPEI prevention layer)

**User:** lands on dashboard for the first time.
**Outcome:** within 30 seconds, knows what POLARIS can and cannot answer.

**What the user sees:**
- Three templates listed prominently (clinical / oncology / cardio drug audits) with display name, scope summary, 3-5 example queries each
- Out-of-scope examples shown explicitly ("not a fit: supplements, off-label speculation, patient-specific advice")
- Below: query input that **suggests the matching template as the user types**, or warns "no template matches — POLARIS may refuse"

**Acceptance:**
- Fresh account, clean state, no coaching, non-developer evaluator
- Evaluator can correctly predict whether 5 sample queries will be accepted, rejected, or ambiguous before submitting
- Evaluator can describe what POLARIS is for in one sentence after 30s on the page

**Crown jewel surfaced:** "what can I ask?" before failure.
**Substrate:** ✅ `/api/inspector/templates/catalog` (3 templates today)
**Build:** scope discovery panel on dashboard; live template-suggestion as user types.

---

### Flow 2 — Scope gate / refusal / disambiguation

**User:** submits a query.
**Outcome:** sees a correct, explainable outcome for every input class.

**What the user sees, by input class:**
- **Clear template match:** "Routing to clinical drug audit template" → proceeds to Flow 3.
- **Ambiguous acronym/term (BPEI-class):** "Did you mean (a) the syndrome, (b) the institute, (c) the chemical? Pick one or rephrase." This is the BPEI fix — POLARIS detects multiple plausible primary referents in retrieval candidates and asks before synthesizing.
- **Out of scope (e.g., supplements, off-label speculation):** Refusal view explaining: which scope-gate threshold was breached (anchor token count, template confidence, etc.), with the actual numeric values shown, plus suggested alternative templates ("closest matches: X (60% confidence), Y (40% confidence). Refine your question or pick a template explicitly.").
- **Insufficient corpus:** "Cannot answer — only 2 T1 sources available, threshold is 5. Specific gap: no head-to-head trials. Try again in 6 months or supply primary source via private corpus upload."

**Acceptance:**
- For each of 4 input classes (clear match, ambiguous, out-of-scope, insufficient corpus), browser shows the correct outcome on a fresh account, no curl
- Refusal copy is human-readable, not stack-trace-style; non-developer can act on it
- Each refusal names the specific gate, the actual value, the threshold, and a concrete unblock action

**Crown jewel surfaced:** refusal-with-explanation; ambiguity disambiguation.
**Substrate:** ✅ abort statuses; ⚠️ ambiguity detection (NEW — needs candidate-clustering on retrieval results before synthesis).
**Build:** ambiguity detector (cluster retrieval candidates by primary entity; if >1 cluster above threshold, ask); refusal view with thresholds; UI copy by abort type.

---

### Flow 3 — Live audit run

**User:** has a query accepted; watches POLARIS work.
**Outcome:** can describe what POLARIS is doing at any moment, not waiting on a spinner.

**What the user sees, in real-time:**
- **Search phase:** candidates appearing with scores, dropping with reasons ("dropped: failed extraction" / "dropped: T6 review article, T1 alternative available")
- **Tier classification phase:** each accepted source labeled T1-T7 with rationale visible on hover
- **Evidence pool phase:** counter showing "15 spans extracted" and which contract slot each fills
- **Synthesis phase:** sentences appearing one by one with strict_verify decisions ("✓ verified" / "✗ regenerating — claim not supported by span") visible per sentence
- **Contradiction detection:** "⚠ conflict detected: tirzepatide weight loss values range 2.37–16.5%" appearing as it's flagged
- **Two-family check:** "Evaluator agrees" / "⚠ Evaluator disagrees on this claim — flagged" per claim

Every event is timestamped. The user sees POLARIS *think*.

**Acceptance:**
- Streaming UI fed by SSE; no polling
- User on a fresh account watches a 3-minute run end-to-end and can produce a 5-bullet summary of what POLARIS did, without coaching
- If the user refreshes mid-run, state resumes from checkpoint
- If the user clicks Cancel, the run halts within 5 seconds and saves partial state
- Latency from server event to UI render < 1 second

**Crown jewel surfaced:** the visible reasoning process.
**Substrate:** ✅ SSE events, decision telemetry, checkpoints (M-9), per-sentence verify
**Build:** live progress UI consuming SSE; cancel / refresh / resume hooks; per-event UI components.

---

### Flow 4 — Report inspection with frame coverage as lead

**User:** has a completed run; opens the report.
**Outcome:** sees what POLARIS got, what it didn't, and can trace any claim to its source in 2 clicks.

**What the user sees:**
- **Top of report (NEW — frame coverage as lead):** "Got 14 of 15 contract-required entities. 1 gap: SURPASS-CVOT primary endpoint (paywalled, no OA). Click to see gap detail or supply via private corpus."
- **Body:** report renders normally; every claim sentence is subtly highlighted on hover
- **Click any sentence:** side pane opens with:
  - Evidence span highlighted in source context
  - Source URL, tier (T1-T7) with rationale
  - Retrieval trace: which retriever (Serper/S2/Jina), which query, fetch timestamp
  - Two-family evaluator agreement signal
  - Any contradiction flag affecting this claim
- **Click any number** (decimal, percentage): see other values from other sources for the same claim, side-by-side with their tiers

**Acceptance:**
- Frame coverage panel visible above the fold for every report
- Every sentence in the report is clickable; click → evidence pane within 1 second
- Two-family disagreement, when present, is visibly flagged on the claim
- Number cross-reference works for any decimal in the report
- Works for ANY user-submitted run, not just the canned tirzepatide demo

**Crown jewel surfaced:** complete provenance trail visible; gap transparency; two-family signal.
**Substrate:** ✅ provenance tokens, frame coverage manifest, verification_details, two-family scoring
**Build:** Inspector view 1 generalized to user-submitted runs; frame coverage promoted to lead; two-family disagreement surfaced; number cross-ref.

---

### Flow 5 — Contradiction navigation

**User:** sees a report with conflicts.
**Outcome:** can examine each conflict in context, see all sides, see hedging.

**What the user sees:**
- Every contradiction has a badge in the body (`⚠ 3 sources disagree`)
- Click badge → side panel showing:
  - Each source's value, tier, citation marker, evidence span (highlighted)
  - The hedge language POLARIS used in the body (e.g., "estimates range 2.37–16.5%")
  - Per-flag PT08 enumeration
  - "Which source should I trust?" — POLARIS doesn't adjudicate but shows tier hierarchy and sample sizes if available

**Acceptance:**
- Every flagged contradiction in the report has a navigable badge
- All sides visible, with tier and span, in one panel
- Non-developer can articulate why POLARIS hedged after viewing the panel
- Per-flag enumeration matches what's in `contradictions.json`

**Crown jewel surfaced:** contradictions as a feature, not appendix.
**Substrate:** ✅ detector, hedging, view 2 stub
**Build:** badge insertion in body; interactive contradiction panel; cross-link from report sentences.

---

### Flow 6 — Audit bundle export

**User:** finishes a run; needs to deliver to compliance / regulator / customer.
**Outcome:** downloads a complete, offline-verifiable archive.

**What the user sees:**
- "Download audit bundle" button visible on every report page
- Click → preview pane lists what's included:
  - `report.md` (the prose)
  - `bibliography.json` (statements + tiers)
  - `live_corpus_dump.json` (raw evidence pool)
  - `manifest.json` (run summary, gates, statuses)
  - `frame_coverage.json` (entities expected vs got)
  - `verification_details.json` (per-sentence strict_verify results, two-family)
  - `contradictions.json` (per-flag enumeration)
  - `decision_telemetry.json` (every gate decision with timestamp)
  - `methodology.md` (how POLARIS works, for the reviewer)
- Confirm → zip downloads
- A third-party reviewer can independently verify the entire chain from the zip alone, offline

**Acceptance:**
- Button visible without searching, on every report page
- Bundle download works for any user-submitted run
- Third-party tester (no POLARIS access) can open the zip and reproduce the trace from any claim back to its source URL + span
- Bundle includes a `README.md` explaining what each file is for the non-developer reviewer

**Crown jewel surfaced:** provenance as deliverable.
**Substrate:** ✅ `/api/inspector/runs/{slug}/audit-bundle.zip`
**Build:** button + preview + completeness pass + reviewer README.

---

## Acceptance bar (per Codex's tightened "done" definition)

Each flow ships when ALL of these hold:
- Fresh user account, clean state
- Production-like environment (not dev mode)
- No direct API calls; no JWT in browser console
- Real, target-user-supplied inputs (not synthetic curated examples)
- Four input classes pass: supported, unsupported, ambiguous, failing
- Non-developer evaluator can interpret outcomes without coaching
- Time and cost bounds explicit and visible
- Recorded browser walkthrough produced
- Codex code review GREEN (Layer 1)
- Codex user-flow adversarial review: P0/P1 findings addressed (Layer 2)
- User sign-off after walkthrough (Layer 3 — non-negotiable)

**Codex GREEN alone is NOT done. Walkthrough alone is NOT done. Both, plus user sign-off, = done.**

## Three review layers — Codex is one input, not the gate

1. **Layer 1 — Codex code review.** Internal correctness, regression, security. Existing capability.
2. **Layer 2 — Codex user-flow adversarial review (NEW).** For each flow: enumerate inputs that break it; find acceptance criteria only a developer could verify; propose user actions not covered (cancel mid-run, refresh, resume, slow network, source outage, partial result, garbage input, accidental injection, multi-tab use). This is the layer that catches BPEI-class blindspots.
3. **Layer 3 — Human browser walkthrough (NEW, non-negotiable).** End-of-flow validation by non-developer with real adversarial inputs. Recorded session.

## Out of scope — intentionally deferred (NOT crown jewels for v2 ship)

These have substrate; they will not get UI in this plan. Each will sit unbuilt until the 6 flows above are truly shipped:

- Pin replay UI / "what changed since last run"
- Source admissibility decision tree (richer than tier mix view)
- Python execution flow (charts on retrieved data — Gemini-can't-do advantage)
- Q&A on completed report
- Citation freshness alerts
- Comparative multi-jurisdiction side-by-side
- Operator review queue UI (M-23)
- Billing/quota UI (M-NEW)
- Drive connector UI (M-25)
- Slide deck export UI (M-22)
- Contract drafting UI (M-26)
- Support tickets UI (M-24)
- Auth/Org/RBAC management UI (functional Sign In suffices for pilot)
- Pricing page UI (M-27)
- Operator dashboard UI (M-LIVE-3)

If any of these become crown-jewel-blocking, they enter the plan via revision, not by sneaking in mid-build.

## Anti-patterns refused even if asked

- "Just iterate until Codex GREEN" — failure mode that produced phantom completion
- "Backend exists = done" — phantom completion
- "While we're at it..." — scope creep dilutes scrutiny
- "Re-enter the autoloop" — converges on Codex-passable code, the wrong target
- 113-milestone tasking — diluted scrutiny last time

## Sequencing

**Sprint 1 (weeks 1-2): the BPEI prevention spine — Flows 1, 2, 6.**
Discovery + refusal + export. These establish honesty before any in-run polish. If a user can't ask the right thing or get an honest no, the rest doesn't matter.

**Sprint 2 (weeks 3-4): the in-run / inspection visibility — Flows 3, 4, 5.**
Live audit trail + click-through inspection + contradiction navigation. Crown jewels rendered.

**Sprint 3 (week 5): walkthrough + adversarial review across all 6.**
External non-developer drives all flows with adversarial inputs. Recorded. User signs off.

**Total: ~5 weeks of focused engineering, including reviews and walkthroughs.** Estimated. Will revise after Codex review.

## Out-of-band decisions still needed from user

1. Confirm primary buyer segment (pharma R&D? government? legal? — affects which 3 templates we sharpen first)
2. Confirm hardware target for local deployment (sets model size choice for sovereign profile)
3. Pilot deadline (sets sprint pace)
4. Who runs Layer 3 walkthrough (user themselves? designated QA? external pilot customer?)

These do not block plan finalization but block sprint kickoff.

---

**Next step:** send this plan to Codex with an adversarial brief asking them to break it.
