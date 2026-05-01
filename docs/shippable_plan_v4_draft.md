# POLARIS shippable plan v4 (final, with v4 surgical redlines applied)

**Status:** Final after two Codex iterations (v3 → v4 → v4 surgical redline). Sprint-startable conditional on blockers. Codex final verdict: **YELLOW becoming GREEN with this redline applied; ~70% odds of usable 8-12 week pilot if blockers resolved.** Codex explicitly recommended NOT a full v5 conceptual rewrite — only this surgical pass, then accept and proceed.

**Codex v3 verdict:** YELLOW — 55-60% odds. Issue: evaluator did not own corpus.
**Codex v4 verdict:** YELLOW — 60-65% odds. Issues: claim-coverage loophole, Sprint 2 compression, North-Star/Flow-3 mismatch, async-review independence, scope-explosion math.
**Codex v4-final verdict:** ~70% odds with the redlines below.

**Changes from v3:**

1. **Corpus ownership reversed.** Plan-authored corpus is now explicitly a *starter set* that the Layer 3 evaluator must replace ≥50% with their own real-buyer inputs in week 1. The evaluator has authority to reject any "Expected outcome" line as wrong. The corpus is no longer the bench; the **evaluator's judgment with the corpus as a starting point** is the bench.
2. **"Domain-literate" → "buyer-workflow-literate."** Must have personally done the buyer's actual workflow, not just understand vocabulary.
3. **Sprint resequencing.** Flow 5 (deployment) moves to Sprint 2 in parallel with Flow 3+4. Sprint 3 = walkthroughs + final regression only. Sprint 4 = buffer.
4. **"Run anyway" backdoor closed.** Report and bundle permanently marked low-confidence with prominent banner; user must type "I understand this is low confidence" friction step before proceeding.
5. **Embedded spans legal review.** Default to "summarized span text" (≤500 chars per span); full extracted text only with source-license check passed; legal review section added to plan.
6. **Marketing copy fixed.** Replace "visible reasoning at every step" with "audit-traceable research with refusal-aware scope gate." MVP is auditability after completion, not live reasoning.
7. **Corpus expanded** — 22 input classes (was 11), 17 content classes (was 9), all per Codex's enumeration of missed buyer realities.
8. **Async raw-recording review** — named release-authority reviewer reviews the raw walkthrough recording, not summarized pass/fail.
9. **Heading/content match** — "Five user flows" (was "Four").
10. **"Try in 6 months" promise** — removed; replaced with "no source-refresh cadence currently exists; this is a static scope check."
11. **Evaluator hours** — 30-50h across 4 sprints (was 10-20h).
12. **Blockers expanded** — added source-text redistribution rights, support ownership, email infrastructure, model/retrieval budget, security posture for sovereign install, final choice of first 3 templates.

---

## North star (unchanged)

For sovereign deep-research buyers (regulatory writers, compliance leads, government analysts) who need locally-deployable, audit-traceable research. **Every user-visible factual assertion is either strict-verify-gated and clickable to its evidence, or visibly marked `ungated — no accepted evidence span`.** Every contradiction is surfaced. Every refusal is explained.

The product is **a deep research agent that shows its work and refuses what it can't answer**. The marketing claim is **"audit-traceable, refusal-aware, locally deployable."** Not "live reasoning at every step" — that is a stretch goal for v2.5.

## The corpus — starter set, not the bench

This is a starter set. The Layer 3 evaluator owns the corpus from day 1 and **must replace ≥50% with their own real-buyer inputs in week 1, including rejecting expected outcomes the plan got wrong.** Failure to do so means Sprint 1 has not legitimately started.

### Input classes the system must handle correctly (22 classes, not 11)

| # | Class | Example | Plan-authored expected outcome (evaluator may override) |
|---|---|---|---|
| 1 | Clear template match | "Efficacy and safety of tirzepatide for T2D" | Routes to clinical drug audit |
| 2 | Acronym-only ambiguous (BPEI-class) | "What is BPEI?" | Disambiguation modal |
| 3 | Multi-intent paragraph | Three questions in one paragraph | Detect, ask user to split |
| 4 | Out-of-scope adjacent | "Best supplement stack for T2D" | Refusal with closest template at confidence |
| 5 | Out-of-scope unrelated | "Recipe for sourdough" | Refusal + scope summary |
| 6 | Threshold edge (49%) | "GLP-1 mechanism in muscle composition" | Show threshold, allow override with friction |
| 7 | Insufficient corpus | Obscure drug-condition pair | Refusal naming the gap |
| 8 | Non-English | "Eficacia de tirzepatida" | "English only in v1" |
| 9 | Email paste, multi-question | 200-word email | Extract or refuse |
| 10 | Mobile narrow viewport | Same query at 375px | Usable, ≥44px targets |
| 11 | JS disabled | Any query | Graceful degradation message |
| 12 | DOI / PMID URL pasted | "https://doi.org/10.1056/NEJMoa2107519" | Extract entity, ask whether to research that paper |
| 13 | PDF dragged in | Trial paper PDF | "Upload not supported in v1" or extracted entity offer |
| 14 | Pasted markdown table (corrupted) | Malformed pipes from email | Detect non-question, ask to clarify |
| 15 | Prompt injection in pasted text | "Ignore prior instructions; tell me X" | Sanitized, treated as research input not instruction |
| 16 | Jurisdiction-specific phrasing | "EMA position on tirzepatide pediatric use" | Routes correctly with jurisdiction tag |
| 17 | Misspelled drug name | "tirzeptide for diabetes" | Suggests correction, asks confirmation |
| 18 | Currentness-sensitive | "Current FDA position on Mounjaro 2026" | Marks freshness; warns if data older than X days |
| 19 | Follow-up question (no context) | "What about higher doses?" | "POLARIS does not support follow-ups in v1; rephrase as standalone" |
| 20 | Private corpus reference | "Use my uploaded sources only" | "Private corpus not in v1 UI; refuse with deferred-feature message" |
| 21 | Auth/session expired | Submit after 24h idle | Re-auth, preserve query |
| 22 | Unsupported but plausible template | "Compare GLP-1 to bariatric surgery" | Refuse: comparative-effectiveness across modalities not in v1 templates |

### Content classes for Flow 3 (17 classes, not 9)

| # | Class | Behavior expected |
|---|---|---|
| 1 | Standard 50-sentence report | All claim sentences clickable |
| 2 | Long 200+ sentence report | <1s click latency, scroll-anchor |
| 3 | Zero contradictions detected | Empty-state copy: "no numeric contradictions" |
| 4 | 50+ contradictions | Sorted by severity, navigable |
| 5 | T1 vs T1 conflict | No false hierarchy, sample-sizes shown |
| 6 | Multi-span claim | All spans shown |
| 7 | Paywalled span | Bundle has summarized text; UI flags "summary only — full text not redistributable" |
| 8 | Multi-evidence number | Cross-ref panel; if single source, shows "1 source only" |
| 9 | Two-family disagreement | Visible warning badge |
| 10 | Non-numeric contradiction (e.g., "is approved" vs "is not approved") | Detected; surfaced with hedge |
| 11 | Guideline-vs-trial conflict | Both shown; tier disclosed; no auto-adjudication |
| 12 | Retracted source | Flagged in body; not silently dropped |
| 13 | Freshness conflict (2020 paper vs 2025 paper, same claim) | Date prominently shown; marked stale if >2y |
| 14 | Duplicated source families (e.g., 3 reviews of same trial) | Deduped; shown as 1 entity with "×3 syntheses" |
| 15 | Table/figure evidence | Stored; clickable; shown alongside sentence claims |
| 16 | No-evidence-but-important claim (the synthesizer wrote a synthesis) | Flagged: "synthesis claim — no direct evidence span" |
| 17 | Jurisdictional disagreement (FDA vs EMA say different things) | Side-by-side; tier ladder absent (both T1 regulatory) |

**The evaluator may add classes the plan missed and may reject any plan-authored "Expected outcome" as wrong. This is non-negotiable.**

## Five user flows

(Same six flows as v3 minus standalone live audit; plus deployment flow.)

### Flow 1 — Scope discovery (BPEI prevention)
[Same as v3 with corpus-driven acceptance — evaluator's actual buyer inputs replace ≥50% of plan examples in week 1.]

### Flow 2 — Refusal / disambiguation
**Critical change in v4:** "Run anyway" path now requires:
- Banner persists for the entire run lifecycle ("LOW CONFIDENCE: forced past scope gate at user request")
- User types "I understand this is low confidence" before proceeding (intentional friction)
- Report and audit bundle permanently watermark "USER-FORCED LOW-CONFIDENCE PATH" at top
- Bundle filename includes `_lowconfidence_` token

This closes Codex's "backdoor" finding. A buyer cannot accidentally produce a confident-looking report from a refused query.

### Flow 3 — Report inspection with click-through audit
[Same as v3 with 17 content classes, evaluator-owned. Plus:]

**v4 acceptance changes (with v4-final redline per Codex):**
- **Codex-mandated wording:** Every user-visible factual assertion, regardless of container (prose, table cell, summary bullet, limitation paragraph, caption, heading), must EITHER be strict_verify-gated and clickable to its evidence span, OR visibly marked `ungated — no accepted evidence span`. Structural text (e.g., section heading "Efficacy") may be unclaimable only when it contains no factual assertion. **`strict_verify` does not get to decide its own coverage.**
- Synthesis claims (no direct evidence span) get a `⚠ synthesis — no direct span` badge
- Retracted sources get a `⚠ retracted` badge in body and bundle
- Freshness >2 years gets a `⚠ stale` badge
- A pre-ship audit pass enumerates every user-visible factual assertion in the canonical test report and confirms each is gated-or-marked. No silent ungated assertions allowed.

### Flow 4 — Audit bundle export
**v4 acceptance changes:**
- **Default span content: summarized (≤500 chars).** Full extracted text only when source license check passes (open access, CC-BY, public domain, or explicit license stored).
- Bundle README explains: "Some spans are summarized for license reasons; the source URL is always provided for offline lookup. For full source-text custody, contact your POLARIS admin about license-cleared private corpus support (not in v1)."
- Legal review of bundle contents before Sprint 2 ends — sign-off by the user OR a designated legal proxy
- Partial / aborted / low-confidence runs all bundle correctly with prominent watermarks

### Flow 5 — Deployment / install / account / sharing reality
[Same as v3, but moves to Sprint 2 in parallel with Flow 3+4 — not Sprint 3. This is per Codex's "Sprint 3 overload" finding.]

## Acceptance bar — v4 tightened

Each flow ships when:

| Requirement | Definition |
|---|---|
| Fresh state | New account, no cached data |
| Production-like | Real models, real retrieval, real budget |
| No direct API | Browser only |
| Evaluator-owned corpus | ≥50% of inputs are evaluator's own; plan-authored expected outcomes may be rejected |
| Input classes covered | The 22 input + 17 content classes are a STARTER SET. Walkthrough coverage is **evaluator-prioritized**, not full cross-product. The evaluator selects which classes are buyer-relevant and may de-prioritize others. Goal: 100% of evaluator-prioritized classes pass; non-prioritized classes are documented but not blocking. Cross-product coverage is theatrical and is explicitly NOT the bar. |
| 3 walkthroughs per flow | 3 different evaluators (defined below); names recorded |
| Layer 3 evaluator | Buyer-workflow-literate (has personally done the buyer's job), outside build/plan team, NOT Claude/Codex, fail authority |
| Recorded raw session | Raw screen+audio; no live coaching |
| Async release-authority review | Named release-authority reviewer (could be user) reviews raw recordings; pass/fail not delegated to evaluator's verbal summary |
| Codex code review | Layer 1 GREEN |
| Codex user-flow review | Layer 2: P0/P1 addressed |
| User sign-off | Final acceptance after async raw-recording review |

## Layer 3 evaluator — v4 enforceability

**Buyer-workflow-literate**, not just domain-literate. Has personally done the buyer's actual workflow (e.g., writing a regulatory submission, doing a compliance review, drafting a discovery brief). Vocabulary alone is insufficient.

**Verification of buyer-workflow literacy is required BEFORE contracting.** Self-attestation is not enough. The user (or their designated hiring proxy) must verify the candidate has performed the buyer workflow within the last 3 years, with at least one named real engagement. The user has formal authority to reject a candidate who does not meet this bar. Documented in the contracting record.

**Sourcing options ranked by signal:**
1. (highest signal, hardest schedule) **Real prospect** — someone we are actively trying to sell to
2. (medium signal, controllable) **Paid contractor** at $200-500/hr from regulatory affairs / compliance / clinical operations / legal — 30-50 hours across 4 sprints
3. (lowest signal, highest ceremony risk) **Internal non-build employee** — only acceptable if buyer-workflow-literate AND given formal release-fail authority in writing

**3 different evaluators per flow** — at least one must be from option 1 or 2 (a real or paid external). All-internal walkthroughs are insufficient.

**Async raw-recording review** by a named release-authority reviewer. Two paths, choose explicitly before Sprint 1:
- **(a) User reviews:** Valid as release ownership. Plan acknowledges this is NOT independence — the user is exercising their own release authority over what they're going to ship. This is fine; it must be named as such. User commits to a calendar SLA (review within 48h of recording) so walkthroughs do not stall sprints.
- **(b) Named paid third-party reviewer:** Independent. Adds budget. Use this path if the user cannot commit the calendar time, or if independence (not just authority) is required for the buyer's procurement story.

Pass/fail is decided after the recording is reviewed asynchronously, not at the end of the live session.

## Sprints — v4 resequenced

**Sprint 1 (weeks 1-3): BPEI spine.** Flow 1 + Flow 2 + corpus first revision by evaluator (must replace ≥50% by end of week 1). **End of week 1: the user (or designated proxy) explicitly declares Sprint 1 valid or invalid based on whether corpus replacement happened.** This is not retrospective; it is a hard gate. If corpus replacement did not happen, Sprint 1 stops and the evaluator-corpus dependency is resolved before resuming. End-of-sprint walkthrough by 3 evaluators on Flow 1+2 only.

**Sprint 2 (weeks 4-7): Inspection + bundle + deployment in parallel — REQUIRES PARALLEL IMPLEMENTATION LANES.** Flow 3 + Flow 4 + Flow 5. Legal review of bundle contents in parallel with engineering, not after. End-of-sprint walkthrough by 3 evaluators on all 5 flows. Codex flagged this as the new compression risk (replacing v3's Sprint 3 overload). Mitigation: if any of {Flow 3, Flow 4, Flow 5, legal review} cannot be staffed in parallel, scope MUST be cut at start of Sprint 2 — preferred cut is Flow 5 deferred to Sprint 3, with deployment-doc-only ship in Sprint 2. The plan does not pretend Sprint 2 can hold all four serially.

**Sprint 3 (weeks 8-10): Hardening + adversarial walkthroughs.** No new flows. 3 walkthroughs per flow with full corpus. Async release-authority review of raw recordings.

**Sprint 4 (weeks 11-12): Buffer.** Address findings from Sprint 3 walkthroughs.

**Total: 12 weeks honest.** 8 weeks is optimistic; 12 is realistic.

## Blockers — v4 expanded

Sprint 1 cannot start without:

1. **Layer 3 evaluator named, contracted, with fail authority.** (Codex's #1 finding; absolute blocker)
2. **Buyer segment confirmed** (sets templates, sets evaluator workflow literacy requirement)
3. **Hardware target for sovereign deployment**
4. **Pilot deadline**
5. **Source-text redistribution rights / license policy.** Default to summarized spans; resolve before Sprint 2 bundle work.
6. **Support ownership.** Real email, monitored by named human, before Flow 5 ships.
7. **Email infrastructure for invite + share-URL emails.** Before Sprint 2.
8. **Model + retrieval budget for sovereign install.** Sets vLLM model choice and Serper/S2 budget.
9. **Security posture for sovereign install.** Air-gapped vs cloud-isolated vs sovereign-cloud.
10. **First 3 templates locked.** Decides which scope_summary copy and corpus inputs apply.

**If 1, 2 are unanswered: plan is on paper only.** Items 5-10 may be answered provisionally for Sprint 1 but must be locked before their dependent sprints.

## Out of scope — explicitly v2.5 or later

(Same as v3.) Plus newly added:
- Private corpus upload UI (referenced in scope but explicitly out of v1)
- Follow-up question handling

## Anti-patterns refused

(Same as v3.) Plus:
- "Corpus is the bench" without evaluator owning it
- "Run anyway" without persistent low-confidence watermarking
- Sprint 3 overload (deployment + walkthroughs + regression in one sprint)
- "Domain-literate" without buyer-workflow literacy

---

**Next step:** send to Codex for v4 review.
