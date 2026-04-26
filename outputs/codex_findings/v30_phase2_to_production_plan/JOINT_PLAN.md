# V30 Phase-2 → Internet-Facing Top-Tier Player — JOINT PLAN

**Date:** 2026-04-26
**Source documents:**
- Claude framing (initial): demo 2wks / beta 6-8wks / prod 4-6mo / top-tier 9-12mo
- Codex strategic plan: `outputs/codex_findings/v30_phase2_to_production_plan/findings.md`
- User wishlist (35 + 32 primary sources): `outputs/codex_findings/v30_real_user_wishlist/SYNTHESIS.md`

This document is the joint Claude+Codex reconciliation.

---

## TL;DR

**Phase ETAs (joint):**

| Grade | Joint ETA | Claude said | Codex said | Diff |
|---|---:|---:|---:|---|
| Demo | 1-2 weeks | 2 weeks | 1-2 weeks | agree |
| Beta | 4-8 weeks | 6-8 weeks | 4-8 weeks | Codex earlier floor |
| Production | 12-24 weeks | 16-24 weeks | 12-24 weeks | Codex earlier floor |
| Top-tier | 24-52 weeks | 36-48 weeks | 24-52 weeks | Codex wider range |

**Two structural disagreements with my original framing, both Codex-correct:**

1. **Distribution layer is NOT starting from zero.** The repo already has FastAPI app, custom query intake, SSE streaming, history, campaigns, exports, optional auth, and a `graph_v4` bridge. The work is "make V30 Phase-2 the first-class product path + add concurrency + package safely," not "build SaaS plumbing." This pulls Phase B floor down to 4 weeks.

2. **Dual-lane is non-negotiable.** I proposed fast-path-preview OR parallel-batch OR both. Codex says **both, sequenced asymmetrically**, and crucially: **never dilute the audit lane to chase preview latency.** Preview is for acquisition, audit is for monetization. They are distinct artifacts with distinct quality bars.

**One sharper-than-Claude call:** $20/mo is a trap. Even $200/mo may be too low. Start with workspace/pilot pricing for regulated buyers; add a self-serve analyst tier later if the workflow stabilizes.

---

## Phase sequencing (joint)

### Phase A — Demo-grade (T+0 to T+2 weeks)

**Scope:** internet-facing `AUDIT_GRADE_PREVIEW` for narrow supported clinical templates. Productized proof, not full parity, not "any question."

**Deliverables:**
- Make V30 artifact the canonical rendered UI result (not offline markdown buried in `outputs/`).
- V30-native result viewer: rendered report + inline citation hover + contradiction panel + methods/manifest panel + export buttons + run metadata.
- Honest UX labeling: `Preview`, `Audit lane`, `Estimated completion`, `Known limitations`.
- Minimal operator workflow for `human_gap_tasks.json`.
- Public supported-scope page: which templates supported, what's not, why.

**Wishlist integration (from real user research):**
- Wish #4 (citation-preserving export): include in Phase A — PDF/DOCX/BibTeX/RIS at minimum.
- Wish #1 (real citations): V30 already does this; surface it loudly in viewer UX.
- Wish #19 (contradiction disclosure): V30 already runs 14 clusters in run-14; first-class artifact in Phase A.

**Blockers:**
- V30 Phase-2 is not yet the first-class UI contract.
- `PipelineRunner` is single-concurrency — even a demo will hit this fast.
- Query-to-template routing does not exist; queries map to specific templates manually.

**Acceptance criteria (Phase A ship):**
- 3-5 supported clinical templates render via V30 path
- Result viewer shows citations, contradictions, methods, exports
- Pre-flight cost preview before run starts (real user wishlist top-7 demand)
- Operator can resolve gap tasks from UI

---

### Phase B — Beta (T+2 to T+8 weeks)

**Scope:** narrow clinical beta with custom queries, but only inside curated template library, with dual-lane UX.

**Deliverables:**
- **Preview lane** (≤10 min): deterministic fetch + abstract/metadata-first synthesis + strong citation traceability + explicit "not final audit" labeling.
- **Audit lane** (≤150 min p90): full V30/V34-class artifact with strict-verify, contradiction disclosure, complete exports.
- Curated template router: 10-20 clinical templates with query matching + confidence scoring + operator-review fallback.
- Workspace auth, run history, saved reports, cost preview, budget guard, lightweight versioning.
- Multi-query campaigns + exports reuse existing campaign primitives.
- Replace single-run lock with real queue: 3-5 concurrent audit jobs + 10+ previews.

**Wishlist integration:**
- Wish #2 (pause/cancel/redirect mid-run): SHIP IN PHASE B — biggest unspoken user pain.
- Wish #8 (durable long-running jobs / resume): ship as part of queue work.
- Wish #5 (source organization: search/folders/tags): basic version.
- Wish #16 (structured tables / CSV/XLSX export): ship.
- Wish #7 (cost transparency BEFORE the run): already in Phase A.
- Wish #11 (source-tier control / hard floors): ship as filter.

**Blockers:**
- Template library throughput becomes dominant bottleneck (not model cost).
- Preview quality needs its own benchmark — otherwise judged against wrong artifact.
- PHI / clinical-use guardrails must be in place before beta access broadens.

**Acceptance criteria (Phase B ship):**
- Preview ≤10 min for supported templates
- Audit ≤150 min p90 on same supported set
- 3+ concurrent audit + 10+ concurrent preview without manual babysitting
- Every audit result: inline citations + contradiction disclosure + methods + exports
- Low-confidence queries route to "template review required" not silent wrong-contract
- Clinical mode rejects/warns on PHI inputs

---

### Phase C — Production (T+8 to T+24 weeks)

**Scope:** production-grade vertical product for regulated clinical evidence work. NOT commodity general-purpose deep research.

**Deliverables:**
- Close 1 LB Regulatory: V34/M-73 cross-jurisdiction comparison.
- Expand to 50-100 templates covering high-value clinical wedge: therapeutics, comparators, safety/regulatory, pivotal-trial evidence, population subgroup questions.
- Semi-automated contract drafting with mandatory human approval before customer-facing.
- Workspace isolation, org-level RBAC, billing, quotas, audit bundle export, run diff, regression alerts, citation health checks, support tooling.
- Scale concurrency, caching, observability for meaningful pilot traffic.
- Formalize security/compliance posture: audit trail, retention, access controls, vendor list, incident response, deployment options.

**Wishlist integration:**
- Wish #9 (internal corpus connectors): narrow, curated — Drive/SharePoint/Confluence folder sync, approved-only.
- Wish #14 (shared workspaces + RBAC): full version.
- Wish #15 (notes/comments/annotations): for review/approval workflow.
- Wish #18 (cross-workspace memory): retrieval-only, USER-VISIBLE, DELETABLE (per Codex's user-wishlist plan finding — silent latent memory is a TRAP).
- "Human review queue" wedge feature ships in this phase.

**Blockers:**
- Curator operations + QA outrun engineering if template creation stays ad hoc.
- Regulatory/compliance review becomes a launch dependency.
- A clinical product with weak regulatory synthesis is acceptable as beta but not as a production claim.

**Acceptance criteria (Phase C ship):**
- 50+ templates live
- V34 cross-jurisdiction synthesis closes 1 LB → BEAT-BOTH eligible
- Org-level RBAC + audit bundle export
- Pilot-grade SOC2 readiness (procurement-friendly, not formally certified)
- Customer support flow active

---

### Phase D — Top-tier feature parity (T+24 to T+52 weeks)

**Scope:** parity with the best internet research products on user-visible capability while preserving the audit-grade moat.

**Deliverables:**
- Semi-to-near-automated contract induction with measurable precision + abstain/fallback + human review loops.
- Any-question clinical intake with confidence-gated template matching, operator fallback, eventual cross-domain expansion.
- Faster preview path: <5 min on common questions.
- Faster audit path through aggressive caching + parallel retrieval.
- Enterprise governance: regression lab, citation freshness monitoring, model/version pinning, formal SOC2 program.
- Distribution: onboarding, self-serve trials where safe, collaboration, comments, shared workspaces, buyer-facing packaging.

**Wishlist integration (Phase D / explicitly NOT earlier):**
- 1-click slide deck (Codex calls Phase C late, joint = Phase D for polished version).
- Audio/video overview — TRAP feature; ship cautiously, only as derivative of approved audit artifact, with chaptered transcript + show notes carrying citations.
- Infographic generation — TRAP feature; only as constrained "evidence poster" from already-verified structured facts.
- WikiLLM-class living corpus wiki (the unconstrained version) — Phase D.
- 300-500 PDF/session ingestion — Phase D or separate product.

**Blockers:**
- Auto-induction is the hardest research problem in the roadmap and the easiest place to destroy trust.
- Distribution remains incumbent advantage even if engine reaches parity.
- Cross-domain expansion before clinical wedge stabilizes will dilute brand and overload curation.

---

## Critical-decision verdicts (joint)

These are Claude's 8 strategic questions with Codex's verdicts and the joint final call.

### Decision 1 — Speed: fast-path preview vs parallel-batch vs both?

**Verdict: BOTH, sequenced asymmetrically.**
- Preview lane (≤10 min): for acquisition, time-to-first-value, user trust on first use.
- Audit lane (≤150 min p90): for monetization, regulated-buyer evidence-grade output.
- **NEVER collapse audit to preview latency.** Preview lane and audit lane are distinct artifacts with distinct quality bars.
- Preview ships in Phase B. Don't try to make audit fast in Phase A.

### Decision 2 — Topic coverage: auto-induction vs curated library vs hybrid?

**Verdict: HYBRID, CURATED-FIRST.**
- V1/V2 (Phase A/B): curated template library only.
- Phase C: contract drafting with mandatory human approval.
- Fully autonomous induction: Phase D problem. Earlier = invites the SURPASS-2 wrong-PMID hallucinated-anchor failure that V30 was specifically built to remove.

### Decision 3 — Speed/quality tradeoff: which dimensions regress in fast-path?

**Verdict: in this order — Regulatory → Claim-frames → Contradictions → Cross-trial.**
- Fast path can preserve substantial citation hygiene if bound to abstracts/metadata.
- It is not the canonical artifact.
- Market it as `Preview`, never as final audit product.
- Confusion between Preview and Audit is the #1 product risk.

### Decision 4 — Topic narrowness: clinical-only V1 vs multi-domain?

**Verdict: CLINICAL-ONLY V1.**
- Not single-slug forever, but clinical-only as the commercial wedge.
- That's where the moat is strongest and where regulated buyers actually care about provenance, contradiction disclosure, T1 source discipline.
- Use non-clinical tests to prove architecture generality, NOT to split go-to-market focus.

### Decision 5 — Pricing/positioning: audit-grade niche vs commodity DR?

**Verdict: AUDIT-GRADE FOR REGULATED OR HIGH-CONSEQUENCE WORK.**
- $20/mo is a trap against ChatGPT and Perplexity.
- Even $200/mo may be too low once buyer is a team and value = analyst hours saved + procurement-grade evidence traceability.
- **Start with workspace/pilot pricing.** Add lower self-serve analyst tier later if workflow stabilizes.
- Do not compete on cheap unlimited runs — wrong axis for evidence-grade clinical reporting.

### Decision 6 — 1 LB Regulatory gap: ship now vs block on V34?

**Verdict: SHIP NOW AS BETA / BLOCK PRODUCTION CLAIMS ON V34.**
- Phase A/B label: `audit-grade preview` or `clinical evidence brief`.
- Phase C: do NOT claim top-tier regulated clinical synthesis until V34/M-73 closes cross-jurisdiction comparison.
- This unlocks internet presence without overpromising.

### Decision 7 — Trust/safety: HIPAA / disclaimers / professional gating?

**Verdict: INTENDED-USE DISCIPLINE FIRST. NOT MEDICAL-LICENSE VERIFICATION.**
- Default settings:
  - No PHI ingestion
  - No EHR integration
  - No patient-specific diagnosis or treatment directives
  - No patient/caregiver-facing mode
  - No time-critical use
  - Explicit professional-use attestation for clinical workspaces
- Position as research support tool whose basis can be independently reviewed.
- If later accepting ePHI: BAAs + risk analysis + minimum-necessary controls + enterprise security commitments become mandatory.
- Reference guidance:
  - FDA CDS guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
  - FDA CDS FAQ (four non-device criteria): https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs
  - HHS covered entities: https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html
  - HHS cloud/ePHI/BAA: https://www.hhs.gov/hipaa/for-professionals/faq/2075/may-a-hipaa-covered-entity-or-business-associate-use-cloud-service-to-store-or-process-ephi/index.html

### Decision 8 — Compute infra: worker architecture for N concurrent sweeps?

**Verdict: SIMPLE DURABLE CONTROL PLANE. NOT MICROSERVICE SCIENCE PROJECT.**
- FastAPI for API tier
- Postgres for run/workspace metadata
- Redis (or equivalent) for queueing
- Object storage for run artifacts
- **Separate worker pools for `preview` and `audit` jobs**
- Content-addressed cache keyed by DOI/PMID/URL + parser version
- Per-domain rate limiting
- Checkpointed retries
- Streaming event fan-out
- Move to step-level orchestration ONLY if whole-job workers actually become bottleneck.

---

## Recommended starting bundle (clinical-only beta)

Ship this bundle as Phase A → Phase B over 4-8 weeks.

### Engine layer (V30 already does most of this — protect it)
- Inline citation traceability (V30 = unique vs ChatGPT DR / Gemini DR / Perplexity)
- Contradiction disclosure (V30 = unique)
- Source-discipline + T1 calibration
- Honest gap rendering
- Reproducibility + cost-efficiency ($0.0074/query)

### Product layer (NEW work — joint with wishlist wedge bundle)
1. V30-native result viewer (rendered report + citation hover + contradiction panel + methods + exports)
2. Citation-preserving export stack: PDF/DOCX/BibTeX/RIS/structured-bibliography-JSON
3. Structured evidence tables + CSV/XLSX export
4. Contradiction matrix as first-class artifact
5. Pre-flight cost + time + source-count estimate
6. Pause / cancel / save-state mid-run (top-2 unspoken wishlist demand)
7. Async resilient jobs: checkpoint, resume, durable manifests
8. Page/span citation drill-down UI
9. Locked evidence scopes + hard source-tier + jurisdiction filters
10. Domain templates: 10-20 high-value clinical (label compare, payer evidence memo, trial-summary brief, evidence landscape, indication-specific)

### Infra layer (NEW work)
- FastAPI + Postgres + Redis + object storage
- Separate `preview` and `audit` worker pools
- Content-addressed cache (DOI/PMID/URL + parser version)
- Per-domain rate limiting
- Concurrent capacity: 3+ audit + 10+ preview

### Policy layer (NEW work)
- Intended-use statement
- PHI warning/block
- Professional-use attestation for clinical workspaces
- "No patient-facing mode" guardrail
- Supported-scope page (what works, what doesn't)

### Explicitly NOT in starting bundle
- Polished slide deck (Phase C late)
- Audio/video overview (Phase D, TRAP)
- Infographic polish (Phase D, TRAP)
- 300-500 PDF/session ingestion (Phase D or separate product)
- Free-form WikiLLM (Phase D — needs hard constraints)
- Mobile/CarPlay (out of moat scope)
- Auto-contract induction (Phase D — single biggest risk to moat)
- Cross-domain expansion (Phase D)
- Self-serve $20/mo tier (wrong axis)

---

## Risk register (joint, prioritized)

| # | Risk | Probability | Impact | Phase | Mitigation |
|--:|------|:-----------:|:------:|:-----:|------------|
| 1 | **Auto-contract induction hallucinates anchors / pivotal studies** | High if attempted | Erases trust moat entirely | D | Mandatory human review on every new template until measurable precision proves out. Do NOT attempt before Phase D. |
| 2 | **Preview vs Audit artifact confusion** | High | User disappointment + internal metric noise | B | Distinct UX labeling, distinct URLs, distinct quality bars, distinct pricing tiers. Never co-mingle. |
| 3 | **Retrieval rate-limit / parser breakage / licensing** | Medium-High | Phase B+ blocker | B | Per-domain rate limiting, content-addressed cache, parser-version pinning, license review for each ingest path. |
| 4 | **Summary tables / reference binding silent regression** | Medium | Audit-moat erosion if undetected | B-C | Dedicated product tests (regression lab in Phase C), citation health monitoring, run diff alerts. |
| 5 | **Commodity DR positioning** | Medium-High if marketing slips | Forces wrong-axis comparison | B-D | Position as audit-grade for regulated workflows. Refuse $20/mo tier early. |
| 6 | **Marketing language pulls toward medical-device scrutiny** | Medium | Regulatory exposure | A-D | Intended-use discipline, FDA CDS non-device criteria, professional-use attestation, no patient-specific outputs. |
| 7 | **PHI creep once customers expect uploads** | Medium-High | HIPAA exposure | B-C | Block PHI inputs by default. ePHI requires BAA + enterprise security commitments. |
| 8 | **Template library expansion is editorial/QA, not engineering** | High | Phase C bottleneck | C | Build curator operations team. Template creation workflow is product work, not engineering backlog. |
| 9 | **Single-run concurrency lock** | High | Phase A blocker | A | Replace `PipelineRunner` lock with queue-backed worker pools in Phase A→B. |
| 10 | **Distribution remains incumbent advantage** | Medium | Phase D ceiling | D | Audit-grade moat is defensible; mainstream consumer distribution may always trail. Accept this. |
| 11 | **300-500 PDF/session expectation** | Medium | Pulls into RAG-as-a-service | C-D | Bound to 10-50 docs/workspace in beta. Defer 300+ to Phase D or separate product. |
| 12 | **Audio/video citation invisibility** | High if shipped early | Erases moat | D | Defer to Phase D. Ship only as derivative of approved audit artifact. |

---

## Competitive positioning per phase

| Phase | Beats | Loses to | Defensible position |
|-------|-------|----------|---------------------|
| **A** (demo) | Nobody on breadth or latency. **Beats everyone on auditable citation discipline for narrow canned clinical demo.** | ChatGPT DR / Gemini DR / Perplexity on every consumer dimension | Investor / pilot / select-buyer demo material. Not a market launch. |
| **B** (beta) | Beats Perplexity on rigor for supported clinical questions. Beats Gemini on citation discipline + contradiction handling. | ChatGPT on breadth, polish, any-topic flexibility | Narrow clinical-evidence beta — pharma/biotech R&D, medical writing, regulatory affairs early adopters |
| **C** (production) | Beats Perplexity + Gemini for regulated clinical evidence workflows. Defensibly competitive with ChatGPT for bounded audit-grade use cases. | ChatGPT on universal breadth + mass-market convenience | Production-grade clinical research product for regulated teams |
| **D** (top-tier) | **Beats all three on regulated, provenance-heavy research** if induction + speed + governance land. | Possibly trails on mainstream consumer distribution even at parity quality | Top-tier audit-grade research platform — enterprise + regulated commercial |

**Sustainable competitive advantage at every phase:**
- Inline traceable `[N]` citations (V30 = uniquely strong, competitors at zero)
- Tier-labeled contradiction disclosure (V30 = uniquely strong)
- Strict-verify provenance binding
- T1-anchored bibliography (no PR/promo)
- Frame-coverage manifest
- Hedged-language calibration
- Reproducibility + cost-efficiency

**Persistent gaps to incumbents:**
- Word count / surface depth (ChatGPT DR)
- Cross-jurisdiction synthesis until V34 closes (Phase C)
- Speed (preview lane closes most of this in Phase B; audit always slower)
- Universal breadth / any-topic (clinical-only forever as moat anchor)
- Mainstream distribution (Phase D ceiling)

---

## Joint bottom line

The joint plan is **clinical-first + dual-lane + audit-grade pricing + curated-template-library + simple-durable-infra + intended-use-discipline.**

**ETAs:**
- **Demo (A): 1-2 weeks** — feasible, mostly UX work on existing FastAPI
- **Beta (B): 4-8 weeks** — feasible if dual-lane Preview/Audit + queue-backed concurrency lands
- **Production (C): 12-24 weeks** — depends on V34 closure + curator operations + compliance posture
- **Top-tier (D): 24-52 weeks** — depends on auto-induction quality + distribution + governance

**The wedge bundle for the next 4-8 weeks** = 10 product-layer features above + dual-lane infra + intended-use policy. This is what users have been asking for in forums for years that no incumbent currently ships, AND it amplifies the audit-grade moat instead of diluting it.

**The single biggest call:** $20/mo tier is wrong-axis. Workspace/pilot pricing for regulated buyers is the path. Self-serve analyst tier is a Phase D add, not a launch positioning.

**The single biggest risk:** confusing Preview and Audit artifacts. Distinct UX, distinct URLs, distinct quality bars, distinct pricing tiers. Never co-mingle.
