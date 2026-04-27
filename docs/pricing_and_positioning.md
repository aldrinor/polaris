# Pricing & Positioning (M-27 — Phase C, stretch)

**Status:** Operational positioning doc. This is the canonical
external messaging Polaris uses with regulated-buyer prospects
(pharma R&D, biotech, medical writing, regulatory affairs, payer
evidence). It is intentionally NOT consumer-facing copy; the
wedge is "audit-grade clinical evidence for regulated buyers,"
not "another deep-research tool."

This document is operational, not aspirational. It encodes the
FINAL_PLAN pricing locks (refuse $20/mo, refuse "unlimited"
framing) so future product / GTM decisions don't drift.

---

## §1. Positioning anchor

> **While ChatGPT gives you 5,000 words in 5 minutes, V30 gives
> you 2,599 audit-grade words with 112 inline citations in 2
> hours. Pick the one your job depends on.**

This is the marketing line — but the positioning isn't "we're
slower." The positioning is:

> **Polaris is the only deep-research product where every claim
> is bound to an evidence span you can click through to. When
> your audit gets reviewed by FDA, EMA, or your CMO, you
> shouldn't have to manually verify each citation. We do that at
> the pipeline level.**

### What we are
- Audit-grade clinical evidence engine
- Verified-claim-to-source-span binding (the moat)
- Procurement-grade reproducibility (audit bundle export, run
  diff, regression alerts, citation health checks)
- Workspace + pilot-tier pricing for regulated buyers

### What we are NOT
- Not a chatbot
- Not a "research assistant" in the consumer sense
- Not Perplexity / ChatGPT / NotebookLM / Manus / Gemini Deep Research
- Not a $20/mo subscription
- Not a content factory measured by tokens-per-minute

---

## §2. The pricing lock

**Refuse $20/mo tier.** Per FINAL_PLAN risk register #9: a
$20/mo offering forces ChatGPT/Perplexity comparison forever.
The audit-grade moat doesn't translate to consumer-priced
context — the buyer is in the wrong axis.

**Refuse "unlimited" framing.** Forces speed-and-distribution
comparison against incumbents who win on those axes by
construction.

### Pricing tiers (Phase C)

| Tier | Audience | Annual contract | Includes |
|---|---|---|---|
| **Pilot** | Single-team evaluation in regulated org | $30k–$80k | 50 audit runs/mo, 5 workspaces, audit bundle export, 1 reviewer seat, 60-day eval |
| **Startup** | Small biotech / early-stage pharma | $120k–$240k | 500 audit runs/mo, 25 workspaces, V34 cross-jurisdiction, 5 reviewer seats |
| **Production** | Pharma R&D unit / regulatory affairs department | $400k–$900k | 5000 audit runs/mo, 100 workspaces, all features, dedicated CSM, SLA |
| **Enterprise** | Multi-country pharma / large CRO | $1M+ | Custom quotas (-1 = unlimited), SOC2 Type II, named-procurement contract, dedicated infrastructure |

These match `BillingQuotaStore` defaults in
`src/polaris_graph/audit_ir/billing_quota_store.py`. Operator-
overrides go through `assign_plan(quotas_override=...)`.

### Why pilot starts at $30k

Procurement at a regulated buyer treats anything below $25k as
"swipe-the-corp-card" inventory and below $5k as "personal
expense." We want the buyer firmly in the "real procurement
review" lane because it's the only lane where the audit-grade
features differentiate. Sub-$25k offerings make us compete with
ChatGPT Pro ($200/mo) and lose.

### Self-serve analyst tier — DEFER TO PHASE D

A self-serve "analyst" tier is **explicitly deferred to Phase D**
(per FINAL_PLAN). Reasons:
1. The audit-grade workflow needs human review-queue
   participation; self-serve analysts skip this.
2. Self-serve undermines the "regulated buyer, named
   procurement contract" framing.
3. We don't have the Phase D auto-induction precision yet to
   ship analyst-tier safely.

---

## §3. Target buyer profiles (ICP)

### Pharma R&D — Clinical Development
- Title: Director / VP, Clinical Development; Medical Director
- Pain: Internal medical writers + external CROs charge $50k+
  per indication-level evidence dossier, with 2-4 week
  turnarounds and uneven citation quality
- Polaris pitch: "Your medical writers spend 60% of their time
  verifying citations. Polaris does the verification at the
  pipeline level — they review the audit bundle in 30 minutes
  instead of writing one."

### Pharma — Regulatory Affairs
- Title: Sr. Director, Regulatory Strategy; Manager, Reg Ops
- Pain: Cross-jurisdiction evidence reconciliation (FDA vs EMA
  vs MHRA vs PMDA labels disagreeing on indication / safety
  language) is manual, error-prone, and audit-trail-light
- Polaris pitch: "V34 cross-jurisdiction synthesizer surfaces
  every disagreement between FDA / EMA / MHRA / PMDA labels with
  per-claim back-links. The reg-affairs team gets a defensible
  delta document; you get a procurement-grade audit bundle for
  the deviations."

### Payer Evidence / HEOR
- Title: Director, HEOR; Sr. Manager, Market Access
- Pain: Building dossiers for payer formulary committees needs
  evidence audited against published RCTs + meta-analyses, with
  citation-health checks the payer's clinical reviewer trusts
- Polaris pitch: "Every claim in your formulary submission
  back-links to its source span. Your medical reviewer cross-
  checks 3 random citations and signs off — instead of building
  the dossier herself."

### Medical Writing CROs
- Title: Director, Medical Writing; Project Manager
- Pain: Writers spend disproportionate time on citation
  verification, which doesn't scale; senior writers are
  bottleneck even for routine indications
- Polaris pitch: "Your senior writers' bottleneck is citation
  verification, not prose. We let them sign off audit-grade
  drafts in an hour instead of writing them in a week."

### Biotech R&D (early-stage)
- Title: VP, Clinical; Chief Medical Officer
- Pain: Need defensible evidence summaries for board / investor
  decks but lack medical-writer headcount
- Polaris pitch: "Pilot tier: 50 audit-grade dossiers per month,
  $30-80k annual. Cheaper than one external CRO project,
  defensible at FDA pre-IND meetings."

---

## §4. Sales messaging — what to lean into

### Lean into
- **Verified-claim-to-span binding** — the moat. Show the
  Inspector. Show a demo where clicking a citation reveals the
  exact PDF page + character span + tier + parser version.
- **Audit bundle export** — procurement-grade reproducibility.
  SHA-256 manifest, signed INDEX.txt, full IR projection. Show
  how it ships to a regulator unchanged.
- **Run diff + regression alerts** — every re-audit comes with
  an explicit delta vs the prior approved version. Citation
  health checks (M-17) run inside the bundle. Regression alerts
  (M-18) surface when a re-run would silently downgrade the
  evidence base.
- **Contradictions as first-class output** — not hidden in
  footnotes. Tier-labeled disagreement clusters in the
  Inspector view 2.
- **Cross-jurisdiction synthesis (V34 / M-14)** — FDA vs EMA
  vs MHRA per claim, with explicit divergence flags.

### Lean away from
- "Speed" — incumbents are faster. Don't fight there.
- "Coverage breadth" — incumbents cover more topics. We're
  clinical-only V1.
- "Cost per output" — wrong frame. The right frame is "cost per
  audit-defensible claim."

---

## §5. Competitive positioning

### vs ChatGPT / GPT-4 deep research
- They: hallucinated citations, no provenance binding, no
  procurement-grade artifact, $200/mo
- Us: every claim bound to an evidence span, signed audit
  bundle, $30k+ annual contract
- One-liner: "ChatGPT is for first drafts. Polaris is for what
  you put your name on."

### vs Perplexity / NotebookLM
- They: citation-rich but no per-claim verification, no
  contradiction surfacing, no run diff
- Us: per-claim strict-verify, contradiction matrix, regression
  alerts on re-run
- One-liner: "Perplexity gives you links. Polaris tells you
  whether the links actually support the claim."

### vs Manus / Cohere Command R+ / xAI deep research
- They: novel agents, fast-iterating, no regulated-buyer focus
- Us: regulated-buyer-only by design, pilot pricing, SOC2
  pilot-grade readiness
- One-liner: "They're building deep research for everyone.
  We're building it for the people whose job depends on the
  audit."

### vs internal pharma medical-writing teams
- They: deep domain expertise, slow, expensive at scale
- Us: pipeline-level verification, scales without adding
  headcount, the medical writer becomes a reviewer not a
  builder
- One-liner: "Don't replace your medical writers. Free them
  from citation verification."

---

## §6. The scope page

Per FINAL_PLAN risk register #13 (query-to-template misrouting),
the scope page is a real product surface, not just marketing
copy. The router's confidence-gate verdicts surface here:
- **ROUTED** → "We have a template for this. Audit launches."
- **OPERATOR_REVIEW_REQUIRED** → "We need a human to confirm
  scope before this audit launches."
- **UNSUPPORTED** → "This is outside our supported scope. Here
  are the supported templates."

The scope page contains:
1. Every CuratedTemplate's display_name + scope_summary +
   scope_examples (data from `template_catalog.py`)
2. The IN-SCOPE / OUT-OF-SCOPE language for each
3. A clear "if you're not sure, contact your CSM" CTA — does
   NOT auto-route ambiguous queries

This is intentional friction: a customer with an ambiguous query
should hit the scope page, NOT silently get a polished-but-
misframed audit. That's the Risk #13 mitigation.

---

## §7. Anti-patterns to refuse

Per FINAL_PLAN's "what we explicitly will NOT build":

| Refuse | Reason |
|---|---|
| $20/mo tier | Forces commodity DR comparison forever |
| "Unlimited" framing | Forces speed/distribution comparison |
| Auto-contract induction (before Phase D) | Hallucinated anchors = trust catastrophe |
| Silent global memory in audit lane | Hidden prior injection destroys provenance |
| Preview lane / fast-path mode | Best-quality positioning means audit IS the product |
| Broad connector parity (Drive+Slack+Teams+Notion+Jira) | Table-stakes parity, not differentiating; M-25 narrow scope only |
| Mobile / CarPlay UX | Zero moat value for audit-grade clinical wedge |
| Patient-facing mode | FDA CDS non-device criteria require professional-use attestation |
| EHR ingestion | PHI surface area outside Phase A/B/C; deferred |

---

## §8. The core promises (LAW II for marketing)

These must NEVER appear in customer-facing copy:
- "AI-generated [anything]"
- "Hallucination-free"
- "100% accurate"
- "Replaces your medical writer"
- "Faster than [competitor]"

These ARE the canonical promises:
- "Every claim bound to an evidence span"
- "Audit bundle ships unchanged to regulators"
- "Cross-jurisdiction divergence surfaced per claim"
- "Run diff vs your prior approved version"
- "Citation health checks run on every audit"

If a piece of marketing copy can't ground its claim in something
the audit IR itself surfaces (and a customer can click into the
Inspector to verify), don't ship it.

---

## §9. Operational acceptance

This document supersedes earlier pricing/positioning sketches.
It is not a forecast or a proposal — it is the lock. Changes
require an explicit decision logged in `logs/session_log.md`
following the §6 Anti-Degradation Protocol.

Source-of-truth references:
- FINAL_PLAN §"Pricing locked at workspace/pilot tier"
  (outputs/codex_findings/v30_final_plan/FINAL_PLAN.md, line ~XX)
- BillingQuotaStore default tiers
  (src/polaris_graph/audit_ir/billing_quota_store.py)
- Template catalog scope copy
  (src/polaris_graph/audit_ir/template_catalog.py)
- Risk register #13 (query-to-template misrouting)
  (FINAL_PLAN risk table, item 13)
