# Codex strategic plan: V30 Phase-2 → top-tier internet product

## Honest distance assessment

Main disagreement with the current framing: the distribution layer is not starting from zero. The repo already has an active FastAPI app, custom query intake, SSE streaming, history, campaigns, exports, optional auth, and a pipeline-A-backed `graph_v4` bridge. The hard gap is not "build SaaS plumbing from scratch"; it is "make V30 Phase-2 the first-class product path, add concurrency, and package it safely."

Main counterpoint in the other direction: that does **not** mean the internet-facing product is almost done. The current web surface still has a single-run lock, long-run defaults (`standard=120 minutes`), and a different execution contract than the canonical V30 Phase-2 artifact. The commercialization gap is narrower than greenfield SaaS, but deeper than frontend polish.

| Ship grade | Honest ETA from 2026-04-26 | What it really means |
|---|---:|---|
| Demo-grade internet ship | 1-2 weeks | Public or invite-only web deployment for supported templates, audit-grade preview messaging, strong result viewer, weak custom coverage |
| Beta-grade ship | 4-8 weeks | Narrow clinical beta with custom query intake, curated template routing, dual-lane preview/audit UX, basic auth/workspaces, multi-worker backend |
| Production-grade vertical product | 12-24 weeks | Clinical evidence product for regulated teams: V34 regulatory closure, 50-100 templates, billing, versioning, run diff, concurrency, operational support |
| Top-tier parity with ChatGPT DR / Gemini DR / Perplexity Pro | 24-52 weeks | Any-question intake, fast preview, broad template coverage, semi-automated induction, enterprise governance, strong distribution |

If you try to jump directly to "any clinical question" and commodity DR positioning now, these estimates slip badly. If you stay clinical-first, curated-first, and reuse the current web stack, they are realistic.

## Recommended sequencing

### Phase A — Demo-grade (T+0 to T+2 weeks)

Scope: internet-facing `AUDIT_GRADE_PREVIEW` for a narrow supported set of clinical templates. This is a productized proof, not full parity and not "any question."

Deliverables:
- Deploy the existing web stack as the public entry point and make the V30 artifact the canonical rendered result, not an offline markdown buried in `outputs/`.
- Add a V30-native result viewer: rendered report, inline citation hover, contradiction panel, methods/manifest panel, export buttons, run metadata.
- Keep the existing async job model and SSE stream, but relabel the UX honestly: `Preview`, `Audit lane`, `Estimated completion`, `Known limitations`.
- Add a minimal operator workflow for `human_gap_tasks.json` so incomplete slots have an explicit path to completion.
- Publish a supported-scope page: exactly which templates/questions are supported, what is not, and why.

Blockers:
- V30 Phase-2 is not yet the first-class UI contract; the current web product is broader but different.
- `PipelineRunner` is single-concurrency, which is not internet-scale even for a demo.
- Query intake exists, but query-to-template routing does not.

### Phase B — Beta (T+2 to T+8 weeks)

Scope: narrow clinical beta with custom queries, but only inside a curated template library and with a dual-lane UX.

Deliverables:
- `Preview lane` in 5-10 minutes: deterministic fetch, abstract/metadata-first synthesis, strong citation traceability, explicit "not final audit artifact" labeling.
- `Audit lane` in the background: full V30/V34-class artifact with strict-verify, contradiction disclosure, and complete exports.
- Curated template router: 10-20 clinical templates with query matching, confidence scoring, and operator-review fallback for low-confidence matches.
- Workspace auth, run history, saved reports, cost preview, budget guard, and lightweight versioning.
- Multi-query campaigns and exports should reuse the existing campaign/export primitives instead of being rebuilt.
- Replace the single-run lock with a real queue and 3-5 concurrent audit jobs plus 10+ previews.

Blockers:
- Template library throughput, not model cost, becomes the dominant bottleneck.
- Preview quality needs its own benchmark; otherwise it will be judged against the wrong artifact.
- PHI and clinical-use guardrails must be in place before beta access broadens.

### Phase C — Production (T+8 to T+24 weeks)

Scope: production-grade vertical product for regulated clinical evidence work, not commodity general-purpose deep research.

Deliverables:
- Close the remaining regulatory synthesis gap with V34/M-73-class cross-jurisdiction comparison.
- Expand to 50-100 templates covering the high-value clinical wedge: therapeutics, comparators, safety/regulatory, pivotal-trial evidence, population subgroup questions.
- Add semi-automated contract drafting that always routes through human approval before a new template becomes customer-facing.
- Ship proper workspace isolation, org-level RBAC, billing, quotas, audit bundle export, run diff, regression alerts, citation health checks, and support tooling.
- Scale concurrency, caching, and observability so the system can handle meaningful pilot traffic without manual babysitting.
- Formalize security/compliance posture for customer procurement: audit trail, retention, access controls, vendor list, incident response, deployment options.

Blockers:
- Curator operations and QA will outrun engineering if template creation stays ad hoc.
- Regulatory/compliance review becomes a launch dependency once you sell into pharma, biotech, provider, or government workflows.
- A clinical product with weak regulatory synthesis is acceptable as beta; it is not acceptable as a production claim if regulatory teams are the buyer.

### Phase D — Top-tier feature parity (T+24 to T+52 weeks)

Scope: parity with the best internet research products on user-visible capability, while preserving the audit-grade moat.

Deliverables:
- Semi-automated to near-automated contract induction with measurable precision, abstain/fallback behavior, and human review loops.
- Any-question clinical intake with confidence-gated template matching, operator fallback, and eventually cross-domain expansion.
- Faster preview path: target under 5 minutes on supported/common questions; faster audit path through aggressive caching and parallel retrieval.
- Enterprise governance layer: regression lab, citation freshness monitoring, model/version pinning, formal SOC2 program, strong incident and change management.
- Distribution product work: onboarding, self-serve trials where safe, collaboration, comments, shared workspaces, and clearer buyer-facing packaging.

Blockers:
- Auto-induction is the hardest research problem in the roadmap and the easiest place to destroy trust.
- Distribution is still an incumbent advantage even if the engine becomes top-tier.
- Cross-domain expansion before the clinical wedge stabilizes will dilute the brand and overload curation.

## Critical decisions (Codex's recommended call)

1. Speed: build **both**, but sequence them asymmetrically. The fast preview lane is more important for acquisition and user trust because an internet product needs time-to-first-value in minutes, not hours. Parallel full sweeps matter more for monetization and scale. Do **not** try to collapse the audit lane to 5-10 minutes before shipping; ship a separate preview artifact and let the full audit artifact land later.

2. Topic coverage: use a **hybrid**, but curated-first. V1/V2 should run on a curated template library. Phase C should add contract drafting with mandatory human approval. Fully autonomous induction is a Phase D problem; doing it earlier invites exactly the hallucinated-anchor failure mode that V30 was built to remove.

3. Speed/quality tradeoff: never dilute the audit lane to chase preview latency. The fast path will regress `Regulatory` first, then `Claim-frames`, then contradiction completeness and cross-trial synthesis. It can still preserve a lot of citation hygiene if you bind to abstracts/metadata, but it is not the canonical artifact. Market it as `Preview`, not as the final audit product.

4. Topic narrowness: ship **clinical-only V1**. Not single-slug forever, but clinical-only as the commercial wedge. That is where the current moat is strongest and where regulated buyers actually care about provenance, contradiction disclosure, and T1 source discipline. Use non-clinical tests to prove architecture generality, not to split go-to-market focus.

5. Pricing/positioning: compete as **audit-grade research for regulated or high-consequence work**, not as commodity DR. A $20/month tier is a trap against ChatGPT and Perplexity. Even $200/month may be too low once the buyer is a team and the value is analyst hours saved plus procurement-grade evidence traceability. Start with workspace or pilot pricing; add a lower self-serve analyst tier later if the workflow stabilizes.

6. 1 LB Regulatory gap: do **not** block beta on it, but do block broad production claims on it. Ship now as `audit-grade preview` or `clinical evidence brief` if you want internet presence. Do **not** claim top-tier regulated clinical synthesis until V34 closes cross-jurisdiction regulatory comparison.

7. Trust/safety: do not start with medical-license verification; start with **intended-use discipline**. Default to no PHI, no EHR ingestion, no patient-specific diagnosis/treatment directives, no patient/caregiver-facing mode, no time-critical use, and explicit professional-use attestation for clinical workspaces. Keep the product positioned as a research support tool whose basis can be independently reviewed. If you later accept ePHI for covered entities, BAAs, risk analysis, minimum-necessary controls, and enterprise security commitments become mandatory. Relevant official guidance for this boundary: FDA CDS guidance and policy navigator, and HHS HIPAA covered-entity / cloud-BAA guidance.

8. Compute infra: start with a **simple durable control plane**, not a microservice science project. Use FastAPI as the API tier, Postgres for run/workspace metadata, Redis or equivalent for queueing, object storage for run artifacts, and separate worker pools for `preview` and `audit` jobs. Add a content-addressed cache keyed by DOI/PMID/URL plus parser version, per-domain rate limiting, checkpointed retries, and streaming event fan-out. Only move to step-level orchestration if whole-job workers actually become the bottleneck.

## What V30 Phase-2 already wins on (don't lose)

- Claim-level traceability: inline citations and strict-verify provenance are the clearest moat in the set.
- Contradiction disclosure: explicit, machine-auditable disagreement surfacing is a real product differentiator, not just an internal audit trick.
- Source-discipline and calibration: T1-first sourcing and low-hype language are unusually valuable in regulated settings.
- Honest gap rendering: V30 fails loudly and discloses missing coverage instead of smoothing over it.
- Reproducibility and cost-efficiency: the current core is cheap enough that product pricing should be driven by trust and workflow value, not raw inference cost.
- Audit trail potential: the repo already contains the bones of compliance-facing documentation, exports, and event logs.
- Sovereign / enterprise posture: on-prem, audit bundle, and controlled deployment are stronger long-term moats than a generic chat UX.

## What V30 Phase-2 must add to compete

- A fast preview lane that gives useful signal in minutes.
- Query-to-template routing and a scalable template-creation workflow.
- A V30-native result viewer that exposes citations, contradictions, methods, and provenance cleanly.
- Real multi-run concurrency and durable background processing.
- Saved history, run diff, versioning, and workspace collaboration.
- Pricing, quotas, billing, and admin controls.
- Policy guardrails for clinical use, PHI avoidance, and intended-use messaging.
- Operations: monitoring, regression detection, retry handling, citation-health checks, customer support flows.

Many "table stakes" are not absent; they are present in partial form and need to be hardened around the V30 path:

| Capability | Current repo state | Real work left |
|---|---|---|
| Custom query intake | Exists in web API | Needs template routing and safe scope narrowing |
| Streaming | SSE exists | Needs V30-native phase/ETA semantics |
| Result viewer | Exists broadly | Needs V30 artifact fidelity and provenance UX |
| Exports | PDF/HTML/DOCX exist in part | Need audit-bundle polish and reliability |
| Campaigns/batch | Exists in part | Needs queue-backed concurrency and product framing |
| Auth/history | Exists in part | Needs workspace isolation, RBAC, and procurement-ready posture |

## Realistic competitive positioning at each phase

- Phase A: beats nobody on breadth or latency. It does beat everyone on auditable citation discipline for a narrow canned clinical demo. This is investor/demo/pilot material, not a general market launch.
- Phase B: can beat Perplexity on rigor for supported clinical questions and can beat Gemini on citation discipline and contradiction handling. It still loses to ChatGPT on breadth, polish, and any-topic flexibility.
- Phase C: can beat Perplexity and Gemini for regulated clinical evidence workflows and becomes defensibly competitive with ChatGPT for bounded, audit-grade use cases. It still loses to ChatGPT on universal breadth and mass-market convenience.
- Phase D: can beat all three on regulated, provenance-heavy research if induction, speed, and governance land. It may still trail on mainstream consumer distribution even if product quality reaches parity.

## Risk factors

- Technical risk: auto-contract induction hallucinating anchors or pivotal studies is the single easiest way to erase the trust moat.
- Product risk: confusing `Preview` and `Audit` artifacts will create user disappointment and internal metric noise.
- Retrieval risk: 300-500 fetches per run at scale create rate-limit, parser-breakage, and licensing headaches long before LLM cost becomes the issue.
- Regression risk: summary tables, reference binding, and slot integrity can silently degrade unless they get dedicated product tests.
- Market risk: a commodity DR positioning will force comparison on the incumbents' strongest axis, which is speed plus distribution.
- Regulatory risk: careless marketing language can pull the product toward medical-device scrutiny even if the core workflow is closer to non-device CDS or research support.
- Privacy risk: once customers expect document uploads, PHI creep is likely unless the product blocks or strictly gates it.
- Operations risk: template-library expansion is an editorial/QA system, not just an engineering backlog.

## Recommended starting bundle

Ship a **clinical-only beta bundle** first. Do not include auto-induction, cross-domain expansion, or commodity consumer pricing in the first launch.

Bundle contents:
- 10-20 curated clinical templates covering a coherent wedge.
- Dual-lane execution: `Preview` plus `Audit`.
- V30-native viewer with citations, contradiction panel, methods, and exports.
- Workspace auth, run history, batch campaigns, budget guard, and operator workflow for gaps.
- Queue-backed concurrency and a shared content cache.
- Clinical-use policy layer: intended-use statement, PHI warning/block, professional attestation, no patient-facing mode.

Concrete acceptance criteria:
- Preview returns a source-backed artifact in `<=10 minutes` for supported templates.
- Audit runs complete in `<=150 minutes p90` on the same supported set, with explicit progress streaming.
- At least `3` concurrent audit runs and `10` concurrent previews can execute without manual intervention.
- Every audit result exposes inline citations, contradiction disclosures, methods disclosure, and exportable audit artifacts.
- Unmatched or low-confidence custom queries are routed to `template review required` rather than silently forced through the wrong contract.
- Clinical mode rejects or warns on likely PHI inputs and never markets outputs as patient-specific diagnosis or treatment advice.

## Official trust/safety references

- FDA Clinical Decision Support Software guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
- FDA CDS FAQ / four non-device criteria summary: https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs
- FDA Digital Health Policy Navigator, CDS step: https://www.fda.gov/medical-devices/digital-health-center-excellence/step-6-software-function-intended-provide-clinical-decision-support
- HHS covered entities and business associates: https://www.hhs.gov/hipaa/for-professionals/covered-entities/index.html
- HHS cloud/ePHI and BAA guidance: https://www.hhs.gov/hipaa/for-professionals/faq/2075/may-a-hipaa-covered-entity-or-business-associate-use-cloud-service-to-store-or-process-ephi/index.html
- HHS de-identification guidance: https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html
