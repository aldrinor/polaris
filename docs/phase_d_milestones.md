# Phase D Milestone Breakdown — Top-Tier Feature Parity

**Status**: planning draft 2026-04-27 (Phase C just locked — task #41)
**Source**: `outputs/codex_findings/v30_final_plan/FINAL_PLAN.md` Phase D section
**Window**: T+24 to T+52 weeks from FINAL_PLAN start
**Parent task**: #42 (still pending)

This document breaks the FINAL_PLAN's 6 Phase D deliverables into proposed implementation milestones (M-D1 through M-D14, named to avoid collision with Phase C's M-1..M-27 + M-NEW).

---

## Goal

Achieve user-visible feature parity with the best internet research products (ChatGPT DR / Gemini DR / Perplexity / NotebookLM / Manus) **while preserving the audit-grade moat established in Phase C**. The audit lane stays canonical; Phase D adds capability without compromising provenance.

---

## Deliverables (FINAL_PLAN Phase D)

| # | Deliverable | Risk | Effort estimate |
|---|---|---|---:|
| 1 | Semi-to-near-automated contract induction | **Highest** | 60-90 ed |
| 2 | Any-question clinical intake | High | 25-40 ed |
| 3 | Faster audit path | Medium | 20-35 ed |
| 4 | Enterprise governance | Medium | 30-50 ed |
| 5 | Distribution + collaboration | Low | 25-40 ed |
| 6 | Carefully-scoped derivative artifacts | Medium-trap | 20-35 ed |

Total: **180-290 eng days** = ~9-14 months for a small strong team. Matches FINAL_PLAN's 24-52 week window. Sequential ordering important for the highest-risk item (auto-induction).

---

## Proposed milestones

### Strand 1: Auto-induction (Deliverable 1) — HIGHEST RISK

The hardest single thing in Phase D. Codex pass-2 explicitly flagged this as needing **mandatory human review** until precision proves out.

- **M-D1: Auto-induction precision benchmark + abstain criterion**
  Build the validation set first. Pick 100-200 historic queries that already have curator-reviewed contracts (the Phase C output). The induction system's job is to reproduce them.
  - Define precision as: induced_contract.match_score(curator_contract) ≥ τ
  - Define abstain trigger: induction_confidence < α → fall back to operator review queue (Phase C's M-23)
  - **Acceptance**: precision ≥ 80% on validation set with ≤ 5% silent disagreement (where induced contract differs from curator's but doesn't abstain)

- **M-D2: Induction model — minimal viable**
  Rule-based (keyword + ontology-match) FIRST. LLM-augmented inductor SECOND. Resist the urge to start LLM-only.
  - Inputs: research question + workspace docs (if any) + template router shortlist (Phase C M-20)
  - Output: candidate `report_contract` (M-54 schema) + confidence + abstain decision

- **M-D3: Induction → operator-review pipeline**
  Even when the inductor produces a contract, route to human review for the first 6 months. UI is M-23's queue + a "modified contract" diff view.
  - Audit log: which contracts curator accepted as-induced, modified, rejected
  - This data trains the next iteration of M-D2

- **M-D4: Induction confidence calibration + automated trust gate**
  After 6 months of M-D3 telemetry, calibrate when induction can ship without human review. The gate is per-template-class, not per-query.
  - Acceptance: at least 1 template class auto-confirms with ≥ 95% precision against curator labels

### Strand 2: Any-question intake (Deliverable 2)

- **M-D5: Confidence-gated template matching**
  Extension of Phase C M-20 (template router scaling). When the router's top-1 match has low confidence, emit "I can't audit this question yet" with a fallback path (operator queue or user reformulation prompt).
  - **Reuses**: M-20 router + M-23 operator queue
  - **New**: scope-eligibility classifier (in-scope clinical, in-scope drug-class, out-of-scope)

- **M-D6: Cross-domain expansion (proven)**
  Push beyond clinical to ≥2 non-clinical domains. Codex M-62 in V30 already used a policy template as the generalization proof. Phase D builds 2 more.
  - Candidates: cybersecurity policy, pharmacovigilance, industrial materials
  - **Acceptance**: 1 audit-grade run completed end-to-end on each non-clinical domain with strict_verify GREEN

### Strand 3: Faster audit (Deliverable 3)

- **M-D7: Aggressive caching layer**
  Source-fetch cache (CrossRef/Unpaywall/PubMed responses keyed by DOI/PMID) — already partially in M-21 (workspace memory). Extend to system-wide content cache with TTL.
  - **Acceptance**: same-DOI re-runs save ≥ 80% retrieval time

- **M-D8: Parallel retrieval**
  Currently retrieval is mostly sequential per slot. Parallel-fetch slots that don't share dependencies. Watch for rate-limit collision with CrossRef/PubMed.
  - **Acceptance**: p90 audit time ≤ 60 min on common questions (from current ~145 min)

### Strand 4: Enterprise governance (Deliverable 4)

- **M-D9: Regression lab**
  Continuous integration of the V27 baseline tests + new BEAT-BOTH dimensions. Every code change runs against the validation set; regressions block merge.
  - **Reuses**: existing pytest infrastructure
  - **New**: BEAT-BOTH dimension scoring as part of CI

- **M-D10: Citation freshness monitoring**
  Daemon that re-fetches cited DOIs/PMIDs and alerts when sources are retracted, expressions of concern issued, or guidance documents superseded.
  - **Acceptance**: alert latency ≤ 24h after source change detected

- **M-D11: Model + version pinning**
  Every audit bundle (Phase C M-16) records exact model versions, prompt versions, retrieval-source versions. Phase D adds re-run-from-pin capability.

- **M-D12: Formal SOC2 program**
  Phase C shipped pilot-grade SOC2 readiness (M-19). Phase D engages auditors and gets the certificate.

### Strand 5: Distribution (Deliverable 5)

- **M-D13: Self-serve onboarding + collaboration**
  Buyer-facing packaging:
  - Self-serve trials WHERE SAFE (i.e., for low-risk template classes with auto-confirmed induction)
  - Comments + shared workspaces (multi-user editing of corpus + contracts, **not** runs)
  - Audit-bundle sharing with permission control (Phase C M-15a/b auth)

### Strand 6: Carefully-scoped derivatives (Deliverable 6)

- **M-D14: Constrained derivatives** (LATE in Phase D, gated on audit-lane proven in C)
  - Evidence poster (infographic) — constrained: only verified structured facts may render; layout is templated, no LLM prose generation
  - Chaptered transcript + show notes — only as derivative of audit bundle, never as canonical
  - Living-wiki workspace synthesis (full WikiLLM form)

  **Trap to avoid**: any of these becoming the canonical surface. Audit graph IR + Evidence Inspector remain canonical; M-D14 outputs are projections with back-links.

---

## Acceptance criteria (FINAL_PLAN)

- Auto-induction precision ≥ X% on validation set with human-review fallback (M-D4)
- Faster audit p90 ≤ 60 min on common questions (M-D8)
- Cross-domain expansion proven on at least 2 non-clinical domains (M-D6)
- Formal SOC2 in progress (M-D12)

---

## Sequencing recommendation

**Quarter 1** (T+24 to T+36 weeks): M-D1, M-D2, M-D3, M-D5, M-D7
- Build the auto-induction validation harness FIRST. Then a minimum viable inductor. Then route through operator review. In parallel: faster audit caching. Total: ~3-4 months.

**Quarter 2** (T+36 to T+44 weeks): M-D4, M-D6, M-D8, M-D9
- Calibrate auto-induction. Prove cross-domain. Parallel retrieval. Regression lab. Total: ~2 months.

**Quarter 3** (T+44 to T+52 weeks): M-D10, M-D11, M-D12, M-D13, M-D14
- Governance + distribution + derivatives. SOC2 audit kicks off here. Total: ~2 months.

---

## Risks (carry forward from FINAL_PLAN risk register)

- **Risk #13**: query-to-template misrouting / unsupported-query overclaim. M-D5 must NOT silently route an out-of-scope question into a template — must emit "I can't audit this" explicitly.
- **Auto-induction precision below threshold**: M-D2 may not reach 80% precision. M-D3's human-review fallback is the safety net; budget for the possibility that auto-confirmation never proves out and human review remains in the loop forever.
- **Cross-domain false start**: M-D6's non-clinical domains (cybersecurity, pharmacovigilance, materials) may need their own retrieval back-ends (PubMed and CrossRef are clinical-tilted). Budget retrieval-adapter work in M-D6's effort estimate.

---

## Out of scope for Phase D

- **Open-internet free tier**: still pilot/workspace tier per pricing lock (Phase C M-27). Even Phase D self-serve trials are gated.
- **Real-time collaborative authoring**: workspace memory shared yes; live cursor/typing no.
- **Multi-language UI**: English-only stays. Add as Phase E if demanded.
- **Mobile app**: web-only stays. Add as Phase E if demanded.

---

## Next step

Get user sign-off on this milestone breakdown before launching M-D1 (auto-induction precision benchmark). Phase D is the longest, riskiest phase; better to verify the strands are right than to start building and then re-plan mid-flight.
