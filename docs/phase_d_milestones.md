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

Total: **180-290 eng days** of engineering effort, fitting inside FINAL_PLAN's 24-52 week (28-week) window when staffed by a 2+ engineer team. The wall-clock duration is dominated NOT by engineering throughput but by two concurrent calendar-latency cycles: M-D4 telemetry accumulation (≥6 months of M-D3 operator-review feedback before the trust gate calibrates) and M-D12 SOC2 audit cycle (external auditor lead time). Sequencing is critical for the highest-risk item (auto-induction). See "Sequencing recommendation" section below for the corrected framing.

---

## Proposed milestones

### Strand 1: Auto-induction (Deliverable 1) — HIGHEST RISK

The hardest single thing in Phase D. Codex pass-2 explicitly flagged this as needing **mandatory human review** until precision proves out.

- **M-D1: Auto-induction precision benchmark + abstain criterion** (revised per Codex review)
  Build the validation set first. Pick 100-200 historic queries that already have curator-reviewed contracts (the Phase C output). The induction system's job is to reproduce them.
  - Define precision as: induced_contract.match_score(curator_contract) ≥ τ
  - Define abstain trigger: induction_confidence < α → fall back to operator review queue (Phase C's M-23)
  - **Codex correction**: validation set must include AMBIGUOUS queries (intent unclear) and OUT-OF-SCOPE queries (not clinical, or not in supported template space) as negatives — the failure mode is silent misframing, not just low contract-match score. Measure abstain precision (correct abstains / all abstains) AND abstain recall (correct abstains / queries that should abstain) AND operator-review load (queries routed to humans / total).
  - **Acceptance**: precision ≥ 80% on in-scope validation set with ≤ 5% silent disagreement; abstain recall ≥ 95% on out-of-scope; operator-review load ≤ 30% of total queries.

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

- **M-D6: Cross-domain expansion (proven)** (revised per Codex review — depends on M-D5 + new domain retrieval adapters, NOT on M-D2 inductor or M-D4 trust gate)
  Push beyond clinical to ≥2 non-clinical domains. Codex M-62 in V30 already used a policy template as the generalization proof. Phase D builds 2 more.
  - Candidates: cybersecurity policy, pharmacovigilance, industrial materials
  - **Required**: domain retrieval adapters (CrossRef + PubMed are clinical-tilted; cybersecurity may need NIST/MITRE, pharmacovigilance may need FAERS/EudraVigilance, materials may need ASTM/Web of Science). M-D6 effort budget should include adapter work.
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

- **M-D12: Formal SOC2 program in progress** (revised per Codex review — FINAL_PLAN says "in progress" not "certificate")
  Phase C shipped pilot-grade SOC2 readiness (M-19). Phase D engages auditors and starts the audit cycle. The certificate itself depends on external auditor lead time and is calendar-dominated; Phase D's commitment is "audit cycle initiated and progressing on track", not certificate-in-hand.

### Strand 5: Distribution (Deliverable 5)

- **M-D13: Self-serve onboarding + collaboration**
  Buyer-facing packaging:
  - Self-serve trials WHERE SAFE (i.e., for low-risk template classes with auto-confirmed induction)
  - Comments + shared workspaces (multi-user editing of corpus + contracts, **not** runs)
  - Audit-bundle sharing with permission control (Phase C M-15a/b auth)

### Strand 6: Carefully-scoped derivatives (Deliverable 6)

- **M-D14: Constrained derivatives** (LATE in Phase D, gated on audit-lane proven in C)

  Universal constraints (apply to ALL three derivative types per Codex correction):
  - Composition strictly DOWNSTREAM of verification — derivatives can only project verified structured facts, never invent prose
  - Every rendered element holds back-link to claim ID + evidence ID
  - No uncited connective tissue (transitions, "as noted above" type prose) — only renderable from already-approved content
  - No derivative becomes an editable source artifact (one-way projection)
  - Each derivative remains navigable BACK to Evidence Inspector

  Per-derivative items:
  - Evidence poster (infographic) — templated layout, no LLM prose generation in poster body
  - Chaptered transcript + show notes — derivative of audit bundle, never canonical
  - Living-wiki workspace synthesis (full WikiLLM form) — must NOT pull from global system memory; workspace memory only (closes Risk #6 cross-contamination per Codex review)

  **Show notes audio** (FINAL_PLAN sub-item): explicitly DESCOPED at this milestone — defer to a Phase E if user demand materializes. Recording the descope explicitly per Codex correction (FINAL_PLAN listed it; the milestone breakdown should not silently drop it).

  **Trap to avoid**: any derivative becoming the canonical surface. Audit graph IR + Evidence Inspector remain canonical; M-D14 outputs are projections with back-links.

---

## Acceptance criteria (FINAL_PLAN)

- Auto-induction precision ≥ X% on validation set with human-review fallback (M-D4)
- Faster audit p90 ≤ 60 min on common questions (M-D8)
- Cross-domain expansion proven on at least 2 non-clinical domains (M-D6)
- Formal SOC2 in progress (M-D12)

---

## Sequencing recommendation (revised per Codex review)

**Quarter 1** (T+24 to T+36 weeks): M-D1, M-D2, M-D3, M-D5, M-D7, M-D9
- Build the auto-induction validation harness FIRST. Then a minimum viable inductor. Then route through operator review. In parallel: faster audit caching + regression lab (Codex correction: M-D9 belongs here as the harness for everything else, not Q2).

**Quarter 2** (T+36 to T+44 weeks): M-D6, M-D8, M-D11, telemetry-gathering-for-M-D4
- Cross-domain proofs (depends on M-D5 router + new domain retrieval adapters per Codex correction — NOT on M-D2/M-D4). Parallel retrieval. Model/version pinning. M-D3 telemetry continues accumulating; M-D4 trust-gate decision deferred.

**Quarter 3** (T+44 to T+52 weeks): M-D4, M-D10, M-D12, M-D13, M-D14
- Auto-induction trust gate (now late Q3 because it needs ~6 months of M-D3 operator-review telemetry per Codex correction). Citation freshness daemon. SOC2 audit kicks off (FINAL_PLAN says "in progress" not "certificate" — corrected from M-D12 acceptance). Distribution. Derivatives.

**Calendar-latency reality check (Codex correction):** 180-290 ed inside 28 weeks needs 2+ engineers, NOT a single contributor. The schedule risk isn't engineering throughput — it's M-D4 telemetry accumulation (6 months minimum) and M-D12 SOC2 audit cycle (external auditor lead time). "9-14 months wall-clock" earlier in this doc was the wrong framing; treat the 28-week window as the engineering-effort window, with telemetry/audit cycles overlaid as concurrent calendar latency.

---

## Risks (carry forward from FINAL_PLAN risk register)

- **Risk #13**: query-to-template misrouting / unsupported-query overclaim. M-D5 must NOT silently route an out-of-scope question into a template — must emit "I can't audit this" explicitly.
- **Risk #7** (carried forward per Codex review): retrieval rate-limit / parser breakage. Activated by M-D6 (new domain adapters), M-D7 (cache TTL invalidation), M-D8 (parallel retrieval triggers tighter rate limits), M-D14 (poster/wiki derivatives may re-fetch). Mitigation: explicit rate-limit budget per domain + parser health checks + circuit breaker on consecutive parser failures.
- **Risk #8** (carried forward per Codex review): reference-binding silent regression. The audit graph IR's claim ID ↔ evidence ID ↔ source span chain can drift silently if any layer mutates. M-D14's living-wiki composition is the highest-risk new entrant. Mitigation: every Phase D milestone that creates new outputs (M-D6, M-D8, M-D14) must include a reference-binding-integrity test in M-D9's regression lab.
- **Risk #6** (carried forward per Codex review): hidden global-memory contamination. M-D14's living-wiki form CANNOT synthesize beyond user-visible workspace memory. Constraint added explicitly to the M-D14 universal constraints above; M-D9's regression lab must include a memory-isolation test that proves the wiki output cannot be influenced by global memory state.
- **Auto-induction precision below threshold**: M-D2 may not reach 80% precision. M-D3's human-review fallback is the safety net; budget for the possibility that auto-confirmation never proves out and human review remains in the loop forever.
- **Cross-domain false start**: M-D6's non-clinical domains (cybersecurity, pharmacovigilance, materials) may need their own retrieval back-ends (PubMed and CrossRef are clinical-tilted). Budget retrieval-adapter work in M-D6's effort estimate.
- **M-D4 telemetry latency** (Codex review correction): the auto-induction trust gate requires ≥6 months of M-D3 operator-review feedback before it can be calibrated. Don't sequence M-D4 in Q2; it must be Q3 or later.

---

## Out of scope for Phase D

- **Open-internet free tier**: still pilot/workspace tier per pricing lock (Phase C M-27). Even Phase D self-serve trials are gated.
- **Real-time collaborative authoring**: workspace memory shared yes; live cursor/typing no.
- **Multi-language UI**: English-only stays. Add as Phase E if demanded.
- **Mobile app**: web-only stays. Add as Phase E if demanded.

---

## Next step

Get user sign-off on this milestone breakdown before launching M-D1 (auto-induction precision benchmark). Phase D is the longest, riskiest phase; better to verify the strands are right than to start building and then re-plan mid-flight.
