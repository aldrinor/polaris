# V30 Phase-2 → Top-Tier Internet Player — FINAL PLAN

**Date:** 2026-04-26
**Plan version:** v1 (Claude pass-1 of consolidated plan)
**Codex agreement status:** PENDING — sent for review parallel to this commit

**Source documents consolidated:**
- `outputs/codex_findings/v30_phase2_to_production_plan/findings.md` (Codex strategic plan)
- `outputs/codex_findings/v30_phase2_to_production_plan/JOINT_PLAN.md` (Claude+Codex commercialization, audit-only pivot)
- `outputs/codex_findings/v30_user_wishlist_plan/findings.md` (Codex per-wish deep dive)
- `outputs/codex_findings/v30_user_wishlist_plan/JOINT_ANALYSIS.md` pass-2 (Codex-reviewed PARTIAL → 7 fixes integrated)
- `outputs/codex_findings/v30_real_user_wishlist/findings.md` (Codex 35-source primary research)
- `outputs/codex_findings/v30_real_user_wishlist/SYNTHESIS.md` (Claude+Agent 50-source convergence)
- `outputs/codex_findings/v30_joint_analysis_review/findings.md` (Codex review of JOINT_ANALYSIS pass-1)

---

## TL;DR (one page)

**The product:** V30 Phase-2 audit-grade clinical research engine, productized as an internet-facing **AUDIT_GRADE_PREVIEW** with the **Evidence Inspector** as the centerpiece UI.

**The pivots from initial framing:**
1. **Audit-lane only.** Cut the dual-lane Preview+Audit recommendation. Best-quality positioning means the audit artifact IS the product. 2h25m honest, framed as "evidence-grade research" not "deep research."
2. **Evidence Inspector is the UI moat.** Provenance-native split-pane viewer that exposes V30's strict-verify evidence-id-to-span binding for every claim. No competitor (ChatGPT DR / Gemini DR / Perplexity / NotebookLM / Manus) can build this without rebuilding their core.
3. **Progressive audit-native surfaces during the run.** Replace "preview lane" with milestone-driven Inspector state: pre-flight estimate → parse progress → tier mix → frame coverage → contradiction queue → first verified claim cards → final synthesis. Closes the 2h25m blank-stare problem.
4. **Audit graph IR is canonical, not the report.** Evidence Inspector is the primary renderer; everything else (PDF, DOCX, charts, deck, brief) is a derivative projection that retains back-links to claim IDs.
5. **Memory split into 3 layers.** Session memory / workspace memory / global-system memory. Global memory **quarantined from audit lane** by default.
6. **Pricing locked** at workspace/pilot tier for regulated buyers. $20/mo is wrong-axis trap. Even $200/mo may be too low.

**The wedge:** clinical-only V1 → bounded clinical beta → regulated-clinical-evidence production → top-tier parity.

**Phase ETAs:**

| Phase | ETA | Outcome |
|---|---:|---------|
| A Demo | 2-3 wk | Internet-facing AUDIT_GRADE_PREVIEW with Evidence Inspector 5 views |
| B Beta | 7-11 wk | Audit-only beta with progressive Inspector + bounded upload + Question-Bound Corpus Brief + cited charts |
| C Production | 12-24 wk | V34 cross-jurisdiction + 50-100 templates + RBAC + audit bundle export + pilot SOC2 |
| D Top-tier | 24-52 wk | Auto-induction (with mandatory human review) + faster audit + governance + cross-domain |

**Pass-2 realistic Phase B planning number: 70-110 eng days = 7-11 weeks** for a small strong team.

---

## Phase A — Demo-grade (T+0 to T+3 weeks)

**Scope:** Internet-facing `AUDIT_GRADE_PREVIEW` for narrow supported clinical templates with the Evidence Inspector centerpiece. Productized proof, not full parity, not "any question."

**Deliverables:**

1. **V30 artifact = canonical UI result.** Not offline markdown buried in `outputs/`.

2. **Evidence Inspector — 5 views (17-26 eng days):**
   - View 1 — **Report (click-to-inspect)**. Click any `[N]` → split-pane: claim ↔ exact PDF page + char offsets + tier label
   - View 2 — **Contradiction Matrix**. Renders 14 tier-labeled disagreement clusters; filterable by endpoint/population/dose/tier; click row → both sources side-by-side with span highlights
   - View 3 — **Frame Coverage Manifest**. Live `pass=14, partial=0, gap=1` per contract slot; gap rows have operator-action button
   - View 4 — **Methods + Provenance Bundle**. Run hash + model versions + retrieval queries + abort gates + reproducibility hash + one-click PDF audit-bundle export
   - View 5 — **Source Tier Mix**. Visual T1/T2/T3 bar at report header; per-section breakdown; promo-adjective count badge

3. **Pre-flight estimate** (cost + time + source-count) before Run button enables.

4. **Honest UX labeling.** "Evidence-grade research" not "Deep research." Estimated completion ~2h25m. Known limitations.

5. **Citation-preserving export stack** (PDF/DOCX/BibTeX/RIS/bibliography JSON).

6. **Operator workflow** for `human_gap_tasks.json`.

7. **Public supported-scope page**: which templates supported, what's not, why.

**Acceptance criteria:**
- 3-5 supported clinical templates render via V30 path
- All 5 Evidence Inspector views functional
- Click any inline `[N]` citation → split-pane reveals exact span + tier in <500ms
- Contradiction Matrix renders all 14 clusters from run-14 with both-source side-by-side
- Frame Coverage Manifest renders pass/partial/gap status for every contract slot
- One-click export of audit bundle (PDF + manifest + bibliography)
- Operator can resolve gap tasks from UI

---

## Phase B — Beta (T+3 to T+11 weeks)

**Scope:** Narrow clinical beta with custom queries, only inside curated template library. Single audit lane only — no preview lane. Deeper Evidence Inspector with progressive during-run state.

**Deliverables:**

1. **Audit lane only** (≤150 min p90). Full V30/V34-class artifact with strict-verify, contradiction disclosure, complete exports. **NO preview lane.**

2. **Progressive audit-native surfaces during the run** (8-12 eng days, NEW per Codex pass-2):

   | t (min) | Surface |
   |--------:|---------|
   | 0 | Pre-flight scope/cost/time/source-count estimate |
   | 0-2 | Upload/parse progress per document |
   | 2-15 | Live source discovery with tier mix bar filling in |
   | 15-45 | Frame coverage manifest filling in as evidence arrives |
   | 45-90 | Contradiction queue appears before final synthesis |
   | 90-120 | First verified claim cards / evidence cards |
   | 120-145 | Final synthesis + complete Evidence Inspector |

3. **Pause / cancel / save-state mid-run.** Top-2 unspoken wishlist demand. Cancel/pause at any milestone above; resume from checkpoint.

4. **Curated template router** (10-15 eng days). 10-20 clinical templates with query matching + confidence scoring + operator-review fallback for low-confidence queries.

5. **Bounded upload + workspace data model** (25-40 eng days, RAISED per Codex pass-2):
   - 10-50 docs/workspace, persistent
   - Workspace scoping + permissions + retention + deletion semantics
   - Page/sheet/slide/timecode provenance map (NOT just char offsets)
   - Filter modes: uploaded-only / web-only / blended
   - Per-document parser status UX

6. **Question-Bound Corpus Brief** (12-20 eng days, RENAMED from "Workspace Brief" per Codex):
   - Narrow form: answer one user question over a selected corpus, emit cited brief
   - Per-paragraph inline citations OR explicit "insufficient support" labels
   - Dependent on bounded upload landing first
   - **NOT** "Workspace Brief" or "WikiLLM" in product copy — those import wrong expectations

7. **Cited tables + numeric charts + export bundle** (8-15 eng days, core scope):
   - Every chart backed by machine-readable source table with evidence IDs
   - Visuals fail closed when extraction confidence below threshold
   - Mermaid/flow polish = secondary
   - Export image + source table + citation appendix

8. **Passive workspace notes** (5-10 eng days, NEW per Codex split):
   - User pins/saves/bookmarks
   - Does NOT silently steer synthesis
   - Retrieval-active memory remains Phase C

9. **Queue-backed concurrency** (10-15 eng days):
   - 3+ concurrent audit jobs
   - FastAPI + Postgres + Redis + object storage
   - Content-addressed cache keyed by DOI/PMID/URL + parser version
   - Per-domain rate limiting

10. **Workspace auth + run history + budget guard + lightweight versioning.**

11. **Clinical-use policy layer:** intended-use statement, PHI warning/block, professional-use attestation, no patient-facing mode, supported-scope page.

**Pass-2 ETA (Codex review): 70-110 eng days = 7-11 weeks** for a small strong team. Lower range only feasible if wish #1 stays extremely narrow.

**Acceptance criteria:**
- Audit ≤150 min p90 on supported set
- 3+ concurrent audit jobs without manual babysitting
- Every audit result: inline citations + contradiction disclosure + methods + exports
- Evidence Inspector functional across all 5 views with progressive during-run state
- Progressive milestones reachable per the t-table above
- Pause/resume mid-run with no data loss
- Bounded upload: per-doc parse status, page/span provenance, deletion with audit trail
- Question-Bound Corpus Brief: every paragraph cited or "insufficient support"
- Charts fail closed when evidence not numerically extractable
- Low-confidence queries route to "template review required"
- Clinical mode rejects/warns on PHI inputs

---

## Phase C — Production (T+11 to T+24 weeks)

**Scope:** Production-grade vertical product for regulated clinical evidence work. NOT commodity general-purpose deep research.

**Deliverables:**

1. **Close 1 LB Regulatory** via V34/M-73 cross-jurisdiction synthesizer. Unblocks BEAT-BOTH ship.

2. **Expand to 50-100 templates** covering high-value clinical wedge: therapeutics, comparators, safety/regulatory, pivotal-trial evidence, population subgroup questions.

3. **Semi-automated contract drafting** with mandatory human approval before customer-facing.

4. **Retrieval-active workspace memory** (10-18 eng days, Phase C per Codex split):
   - User-visible, attributable, removable
   - Retrieved priors LABELED in Evidence Inspector view 1 as "memory-derived"
   - Workspace boundaries strict; no cross-customer leakage
   - Freshness/staleness rules

5. **Citation-bound slide deck** (12-20 eng days). Better candidate than broader corpus-brief promise if pulled forward to late Phase B.
   - 12-20 slides from verified report + structured data
   - Slide-level citations OR linked appendix slide for every substantive slide
   - Contradictions and limitations survive in main slide or speaker notes
   - Export PPTX + HTML/PDF without breaking references

6. **Org-level RBAC + workspace isolation + billing + quotas + audit bundle export + run diff + regression alerts + citation health checks.**

7. **Narrow private-corpus sync** (Drive/SharePoint/Confluence — approved-only, NOT broad connector parity).

8. **Human review queue** with annotation + approval + version diff for each run.

9. **Pilot-grade SOC2 readiness** (procurement-friendly, not formally certified).

10. **Customer support flow.**

**Acceptance criteria:**
- 50+ templates live
- V34 cross-jurisdiction synthesis closes 1 LB → BEAT-BOTH eligible
- Org-level RBAC + audit bundle export
- Pilot SOC2 readiness
- Memory-derived retrieval explicitly labeled in Inspector
- Human review queue active

---

## Phase D — Top-tier feature parity (T+24 to T+52 weeks)

**Scope:** Parity with the best internet research products on user-visible capability while preserving the audit-grade moat.

**Deliverables:**

1. **Semi-to-near-automated contract induction** with measurable precision + abstain/fallback + human review loops. Highest-risk item — protect via mandatory human review until precision proves out.

2. **Any-question clinical intake** with confidence-gated template matching, operator fallback, eventual cross-domain expansion.

3. **Faster audit path** through aggressive caching + parallel retrieval.

4. **Enterprise governance:** regression lab, citation freshness monitoring, model/version pinning, formal SOC2 program.

5. **Distribution:** onboarding, self-serve trials where safe, collaboration, comments, shared workspaces, buyer-facing packaging.

6. **Carefully-scoped derivative artifacts** (only after audit lane proven):
   - Constrained "evidence poster" infographic (TRAP if unconstrained — only as derivative of verified structured facts)
   - Chaptered transcript + show notes audio (TRAP if unconstrained — never as canonical audit surface)
   - Living-wiki workspace synthesis (Phase D version of WikiLLM, full form)

**Acceptance criteria:**
- Auto-induction precision ≥ X% on validation set with human-review fallback
- Faster audit p90 ≤ 60 min on common questions
- Cross-domain expansion proven on at least 2 non-clinical domains
- Formal SOC2 in progress

---

## The Evidence Inspector — UI centerpiece (canonical renderer)

**Why this is the UI moat:** Every competitor hides the evidence chain. Their UIs are prose-first, sources-as-footer. They cannot expose provenance because they don't have strict-verify evidence-id-to-span binding to expose. V30 has it. The Evidence Inspector is the literal visualization of the moat.

**Codex pass-2 correction:** the Evidence Inspector is not just another renderer — it is the **primary renderer over the canonical audit graph IR**. All other outputs (PDF, DOCX, CSV, charts, brief, deck) are derivative projections that must retain back-links to claim IDs.

**The 30-second demo:**
> *"Watch what happens when I click this citation."* → split-pane reveals exact PDF page + span + tier
> *"Now click 'Contradictions'."* → tier-labeled matrix appears, 14 disagreement clusters, each with both spans
> *"ChatGPT can't show you any of this. Neither can Gemini, Perplexity, NotebookLM, or Manus. The reason isn't UI work — it's that they don't bind claims to spans. We do."*

---

## Audit graph IR — composition architecture (Codex pass-2 correction)

**Recommendation: ONE canonical audit IR, ONE primary renderer (Evidence Inspector), MANY derivative renderers — all with back-links to claim IDs.**

```
audit_graph_ir (canonical, downstream of verification)
├── Stable claim IDs
├── Evidence-span bindings (page/sheet/timecode/parser-version)
├── Contradiction edges (tier-labeled)
├── Frame / contract coverage mappings
├── Artifact element lineage (every chart point, deck bullet, brief
│   paragraph holds back-link to claim ID + evidence ID)
├── Bibliography map
└── Citation-to-span map

PRIMARY renderer:
└── Evidence Inspector (5 views) ← Phase A
    The canonical audit surface. Everything else is derivative.

DERIVATIVE renderers (must retain back-links to claim IDs):
├── markdown report ← Phase A
├── docx ← Phase A
├── pdf audit bundle ← Phase A
├── structured tables (CSV/XLSX) ← Phase B
├── chart pack ← Phase B
├── question-bound corpus brief ← Phase B (narrow form)
├── citation-bound deck (with appendix slides) ← late-B beta or Phase C
├── infographic / evidence poster ← Phase D (constrained)
└── audio script (chaptered transcript) ← Phase D (constrained)
```

**Guardrails (non-negotiable):**
- Composition strictly downstream of verification
- No renderer invents facts
- Every renderer output element retains back-link to claim IDs
- Renderers may only compress, reorder, or visualize already-approved content
- Evidence Inspector is the canonical audit surface — every derivative output must be navigable BACK to inspector views

---

## Memory architecture (Codex pass-2 correction — 3 layers)

| Layer | Phase | Description | Risk |
|-------|:----:|-------------|:----:|
| **Session memory** | exists | ephemeral run state, scratch notes, current query context | low (garbage-collected) |
| **Workspace memory — passive notes** | B | user pins/saves/bookmarks; does NOT steer synthesis | low |
| **Workspace memory — retrieval-active** | C | prior facts retrieved into future runs; LABELED, attributable, removable | high — needs careful UX |
| **Global / system memory** | quarantined | operator-curated priors, product-level memory | severe if leaks into audit lane |

**Critical rule:** Global/system memory is **quarantined from the audit lane by default**. Explicit user opt-in required to consult; clearly labeled as operator-curated when used. Without this quarantine, hidden prior injection becomes a trust catastrophe.

---

## Snowball + upload architecture (7-layer, Codex pass-2 revision)

```
1. Ingestion / parser orchestration
   ├── file upload, URL import, text import
   ├── parse, OCR, transcription, metadata capture
   └── content hashing, dedupe, retry, failure states

2. Document store + provenance map
   ├── workspace-scoped document manifests
   ├── extracted text + page/sheet/slide/timecode offsets
   ├── parser version + artifact retention metadata
   └── per-document permission model

3. Retrieval indexes
   ├── vector index PLUS lexical/doc filters
   ├── persistent workspace collections (NOT session-only)
   └── provenance-preserving chunk IDs

4. Run / session state (ephemeral)
5. Workspace memory (user-visible, user-deletable)
6. Retrieval / synthesis orchestration

7. Governance / auth / retention / audit  ← CROSS-CUTTING (not terminal)
   ├── per-workspace permissioning at every layer
   ├── per-document deletion with audit trail
   ├── PHI gating + intended-use enforcement
   └── audit log of who did what, when, why
```

---

## Critical-decision verdicts (8)

| # | Decision | Verdict |
|--:|----------|---------|
| 1 | Speed (preview vs batch vs both) | **AUDIT-LANE ONLY** (revised from dual-lane). Best-quality positioning means audit IS the product. Progressive in-run surfaces close the time-to-first-value gap. |
| 2 | Topic coverage (induction vs curated vs hybrid) | **HYBRID, curated-first.** Auto-induction = Phase D only. Earlier = SURPASS-2-class hallucinated-anchor failures. |
| 3 | Speed/quality tradeoff | Never dilute audit. Fast-path would regress Regulatory → Claim-frames → Contradictions → Cross-trial. Cut entirely per quality mandate. |
| 4 | Topic narrowness | **Clinical-only V1.** Use non-clinical for arch-generality tests, not GTM split. |
| 5 | Pricing | **Workspace/pilot pricing for regulated buyers.** $20/mo is wrong-axis trap. Even $200/mo may be too low. Self-serve tier = Phase D add. |
| 6 | 1 LB Regulatory | **Ship beta now / block production claims on V34.** Phase A/B label = "audit-grade preview." |
| 7 | Trust/safety | **Intended-use discipline.** No PHI by default, no EHR, no patient-facing mode, professional-use attestation, FDA CDS non-device criteria as anchor. |
| 8 | Compute infra | **Simple durable control plane.** FastAPI + Postgres + Redis + object storage + worker pool. NOT microservices. |

---

## Pricing & positioning lock

**Position:** audit-grade research for regulated/high-consequence work. NOT commodity DR.

**Refuse:**
- $20/mo tier (wrong axis — forces ChatGPT/Perplexity comparison)
- "Unlimited" framing (forces speed-and-distribution comparison)

**Start with:**
- Workspace / pilot pricing for regulated buyers (pharma R&D, biotech, medical writing, regulatory affairs, payer evidence)
- Annual contracts at procurement-grade tiers
- Self-serve analyst tier = Phase D add only, after workflow stabilizes

**Marketing line:** *"While ChatGPT gives you 5,000 words in 5 minutes, V30 gives you 2,599 audit-grade words with 112 inline citations in 2 hours. Pick the one your job depends on."*

---

## Risk register (12 items, prioritized)

| # | Risk | P | Impact | Phase | Mitigation |
|--:|------|:-:|:-:|:-:|------------|
| 1 | Auto-induction hallucinates anchors | High if attempted | Severe | D | Mandatory human review on every new template. NEVER attempt before Phase D. |
| 2 | PHI creep once uploads ship | 70-90% | Severe | B | Block PHI inputs by default. ePHI requires BAA + enterprise security. |
| 3 | Editorial QA throughput becomes bottleneck | 60-80% | High | B-C | Build curator operations team. Template creation is product work, not engineering backlog. |
| 4 | Single-lane 2h25m blank-stare UX gap | 50-70% | High | A-B | Progressive Inspector surfaces during run (closes this). |
| 5 | Uploaded-doc provenance gap | 70-85% | High | B | Page/sheet/slide/timecode provenance map. Char offsets alone = audit-claim hollow. |
| 6 | Hidden global-memory contamination | 30-50% | Severe | B-C | Quarantine global memory from audit lane by default. Explicit opt-in. |
| 7 | Retrieval rate-limit / parser breakage | Medium-High | High | B+ | Per-domain rate limit, content-addressed cache, parser-version pinning. |
| 8 | Summary tables / reference binding silent regression | Medium | High | B-C | Dedicated product tests, citation health monitoring, run diff alerts. |
| 9 | Commodity DR positioning (marketing slip) | Medium-High | High | B-D | Audit-grade-for-regulated positioning. Refuse $20/mo. |
| 10 | Marketing language pulls toward medical-device scrutiny | Medium | High | A-D | FDA CDS non-device criteria, professional-use attestation, no patient-specific outputs. |
| 11 | Single-run concurrency lock | High | High | A | Replace `PipelineRunner` lock with queue-backed worker pools. |
| 12 | Distribution remains incumbent advantage | Medium | High | D | Audit-grade moat is defensible; mainstream consumer distribution may always trail. Accept this. |

---

## Competitive positioning per phase

| Phase | Beats | Loses to | Position |
|---|---|---|---|
| **A** | Nobody on breadth/latency. Beats everyone on auditable citation discipline for narrow canned demo. | All consumer dimensions | Investor / pilot demo material, NOT market launch |
| **B** | Perplexity on rigor for supported clinical Q. Gemini on citation discipline + contradictions. | ChatGPT on breadth, polish, any-topic | Narrow clinical-evidence beta — pharma R&D, medical writing, regulatory affairs early adopters |
| **C** | Perplexity + Gemini for regulated clinical evidence. Defensibly competitive vs ChatGPT for bounded audit-grade. | ChatGPT on universal breadth | Production clinical-research product for regulated teams |
| **D** | All three on regulated, provenance-heavy research (if induction + speed + governance land) | Mainstream consumer distribution (possibly forever) | Top-tier audit-grade research platform |

**Sustainable competitive advantage at every phase:**
- Inline traceable `[N]` citations (V30 unique vs zero in ChatGPT/Gemini/Perplexity)
- Tier-labeled contradiction disclosure (V30 unique)
- Strict-verify provenance binding
- T1-anchored bibliography
- Frame-coverage manifest
- Hedged-language calibration

---

## What we explicitly REFUSE to build

| Refuse | Reason |
|--------|--------|
| Free-form WikiLLM (unconstrained) | Tolerates uncited connective tissue → kills strict-verify discipline |
| 300-500 PDF/session ingestion | Pulls roadmap into RAG-as-a-service territory |
| Polished infographics (Manus/Gemini-class) | NotebookLM/Manus already polished — wrong axis to compete |
| 1-click podcasts/audio (NotebookLM-class) | Strips inline citations → moat becomes invisible |
| Mobile / CarPlay UX | Zero moat value for audit-grade clinical wedge |
| $20/mo tier | Forces commodity DR comparison forever |
| Auto-contract induction (before Phase D) | Hallucinated anchors = trust catastrophe |
| Silent global memory in audit lane | Hidden prior injection destroys provenance |
| Preview lane (fast-path mode) | Best-quality positioning means audit IS the product |
| Broad connector parity (Drive+Slack+Teams+Notion+Confluence+Jira) | Table-stakes parity, not differentiating |

---

## The 7-wish triage (FINAL, pass-2)

| # | Wish | Verdict | Form to ship | Phase | Eng days |
|--:|------|--------:|--------------|:-----:|---------:|
| 1 | WikiLLM | **SHIP NARROW** | "Question-Bound Corpus Brief" (NOT "Workspace Brief") — depends on #2 | B | 12-20 |
| 2 | Massive upload | **SHIP BOUNDED** | 10-50 docs/workspace, persistent, with workspace data model + provenance map | B | 25-40 |
| 3a | Snowball — passive notes | **SHIP** | Pin/save/bookmark; doesn't steer synthesis | B | 5-10 |
| 3b | Snowball — retrieval-active | **DEFER** | User-visible, labeled "memory-derived" in Inspector | C | 10-18 |
| 4 | Chart/table/artifact | **SHIP** | Cited tables + numeric charts + export bundle (core scope) | B | 8-15 |
| 5 | Infographic | **TRAP** | Constrained evidence poster only, if at all | D | 15-25 |
| 6 | 1-click slide deck | **DEFER** | Citation-bound deck with appendix slides | C (better late-B candidate than #1 if slot opens) | 12-20 |
| 7 | 1-click video/audio | **TRAP** | Chaptered transcript + show notes only, if at all | D | 18-30 |

**Real-user research convergence:** Top 5 unspoken wishes (NOT in user's seed message) are higher-value than wishes 5/6/7:
1. Pause/cancel/redirect mid-run
2. Don't truncate output across retries
3. Cost preview BEFORE run starts
4. Page/span citation drill-down
5. Cross-workspace memory user-visible + deletable

All 5 land in Phase A or Phase B.

---

## The next ship — Phase A → B (7-11 weeks total)

**Phase A (2-3 weeks):**
- V30 artifact = canonical UI result
- Evidence Inspector 5 views (17-26 eng days)
- Pre-flight estimate
- Citation-preserving export stack
- Operator workflow for gap tasks
- Public supported-scope page

**Phase B (5-9 weeks after A):**
- Audit-only single lane (no preview)
- Progressive Inspector surfaces during run (8-12 eng days)
- Pause/cancel/save-state mid-run
- Curated template router (10-15 days)
- Bounded upload with workspace data model (25-40 days)
- Question-Bound Corpus Brief (12-20 days)
- Cited tables + numeric charts (8-15 days)
- Passive workspace notes (5-10 days)
- Queue-backed concurrency (10-15 days)
- Workspace auth + run history + budget guard
- Clinical-use policy layer

**Total Phase B eng work: 70-110 eng days = 7-11 weeks for a small strong team.**

---

## Bottom line

The user named 7 wishes. The joint analysis says:
- **Ship 3.5 in bounded forms** (wishes 1, 2, 4, half of 3)
- **Defer 1.5 to Phase C** (wish 6, retrieval-active half of 3)
- **Treat 2 as traps** (wishes 5, 7)
- **Quarantine 1 risk** (silent global memory)

That discipline IS the product.

**Pivots from initial framing (all integrated):**
1. Audit-only single lane (cut preview)
2. Evidence Inspector as canonical primary renderer
3. Progressive in-run audit-native surfaces
4. Audit graph IR canonical (not the report)
5. Memory split into 3 layers with global quarantined
6. Pricing locked at workspace/pilot for regulated buyers

**Phase ETAs (final):** Demo 2-3wk / Beta 7-11wk / Production 12-24wk / Top-tier 24-52wk.

**The biggest call:** quality-first means we refuse to compete on speed, polish, breadth, or commodity pricing. We compete on provenance integrity, made visible through the Evidence Inspector. That is the moat. Every shipped feature must amplify it; every refused feature would have diluted it.

---

## Codex agreement state (HONEST)

| Element | Codex sign-off |
|---------|:--------------:|
| Source strategic plan (`findings.md`) | Codex wrote |
| Source per-wish deep dive (`findings.md`) | Codex wrote |
| Source 35-source primary research (`findings.md`) | Codex wrote |
| `JOINT_PLAN.md` (audit-only pivot) | NOT reviewed |
| `SYNTHESIS.md` (50-source convergence) | NOT reviewed |
| `JOINT_ANALYSIS.md` pass-1 | reviewed → PARTIAL |
| `JOINT_ANALYSIS.md` pass-2 (7 fixes integrated) | NOT re-reviewed |
| **This `FINAL_PLAN.md`** | **Sent for review parallel to commit** |

**Per autoloop V2 protocol, true joint GREEN requires Codex sign-off on this consolidated plan.** Sent for review.
