# Joint plan v2 — POLARIS from today to fully functional online

**Author:** Claude (Opus 4.7), drafting WITH Codex (gpt-5.4 xhigh).
**Date:** 2026-04-29.
**Round:** 2 — integrating Codex round-1 PARTIAL fixes.

Codex round-1 identified 5 fix categories. v2 applies all of them:
1. Re-baseline Section A into 3 buckets (integrated / substrate-only / non-code).
2. Correct stale file paths.
3. Downgrade overcoded wishlist items.
4. Add Phase E0 covering missing milestones (M-D1, M-D2, M-D9 classification, unwired Phase C).
5. Move telemetry + pinning earlier; add benchmark-validity + reproducibility risks.

---

## A. Where we actually are today (3-bucket re-baseline)

### A.1 Bucket 1: REAL + INTEGRATED into mounted production path

Verified by Codex: each is invoked by `live_server.py`'s
mounted Inspector router or by the production sweep runner.

| ID | Module | Production hookup |
|---|---|---|
| M-1 | `audit_ir/loader.py` | `inspector_router` `/api/inspector/runs` |
| M-2..M-7 | `audit_ir/inspector_router.py` (39 routes) | `live_server.py:1438` mounts |
| M-8/M-9 | `audit_ir/job_queue.py`, `job_runner.py`, `job_worker.py` | `inspector_router` `/api/inspector/jobs` |
| M-10/M-20 | `audit_ir/template_classifier.py` | `inspector_router` `/api/inspector/templates/route` |
| M-11 | `audit_ir/upload_*` | inspector workspace upload routes |
| M-12 | `audit_ir/corpus_brief.py` | inspector brief routes |
| M-13 | `audit_ir/progress_surfaces.py` | SSE stream wired into job_runner |
| M-14 | V34 cross-jurisdiction synthesizer | sweep/run path |
| M-15a/b | `audit_ir/auth_middleware.py`, `auth_store.py` | mounted on every protected route |
| M-16 | audit-bundle export | inspector `/audit-bundle.zip` route |
| M-17 | `audit_ir/citation_health.py` | inspector health route |
| M-18 | `audit_ir/regression_alerts.py` | inspector regression routes |
| M-21 | retrieval-active workspace memory | inspector workspace routes |
| M-23 | `audit_ir/review_store.py` | inspector review-queue routes |

### A.2 Bucket 2: REAL but SUBSTRATE-ONLY (not yet integrated)

Each module exists with tests + threat-model docs but is NOT
imported by `live_server.py`, `live_retriever.py`, or
`run_honest_sweep_r3.py`. The module's own docstring explicitly
says "endpoints wired separately" or "v2 wires connectors".

**Phase D autoloop V2 substrates** (all substrate-only):

| ID | Module |
|---|---|
| M-D1 | validation set + abstain criterion (no production hookup) |
| M-D2 phase a/b | `auto_induction/keyword_inductor.py`, `llm_inductor.py` |
| M-D3 phase 1+2 | `audit_ir/decision_telemetry.py`, `decision_aggregates.py` |
| M-D5 phase 1+2 | `audit_ir/scope_classifier.py`, `scope_classifier_llm.py` |
| M-D6 phase 1 | `audit_ir/domain_router.py` |
| M-D7 phase 1+2 | `audit_ir/retrieval_cache.py`, `cache_warming.py` |
| M-D8 phase 1 | `audit_ir/parallel_fetch.py` |
| M-D9 phase 1+2 | `audit_ir/regression_lab.py`, `beat_both_scoring.py` |
| M-D10 phase 1+2 | `audit_ir/freshness_monitor.py`, `freshness_aggregates.py` |
| M-D11 phase 1+2+v2 | `audit_ir/model_pin.py`, `pin_replay.py`, `pin_trends.py` |

**Late Phase C modules that are substrate-only despite the
M-1..M-27 milestone marking** (Codex round-1 finding):

| ID | Module | Per its docstring |
|---|---|---|
| M-NEW | `audit_ir/billing_quota_store.py` | "endpoint that wires this in is added separately" |
| M-22 | `audit_ir/slide_deck.py` | "PPTX export … deferred to v2" |
| M-24 | `audit_ir/support_ticket_store.py` | substrate, no endpoints |
| M-25 | `audit_ir/private_corpus_sync.py` | "v2 wires the connectors"; v1 is registry only |
| M-26 | `audit_ir/contract_draft_store.py` | substrate |

**Total substrate-only count:** 16 Phase D + 5 late Phase C = 21 modules.

### A.3 Bucket 3: NON-CODE operational/commercial milestones

Not "integration" — different shape. Listing for completeness.

| ID | What |
|---|---|
| M-19 | Pilot-grade SOC2 readiness (procurement-friendly pack) |
| M-27 | Pricing/positioning copy + scope page |
| (M-D4) | Calendar-blocked: needs ≥6 months M-D3 telemetry |
| (M-D12) | Calendar-blocked: external auditor lead time |

### A.4 The user-mandated finish line

Per `~/.claude/projects/C--POLARIS/memory/autoloop_beat_tier1_mandate.md`
(corrected path; the file lives in user-private memory, not
in the repo `memory/` dir):

**From V19 onward, stop criterion = V_N beats ChatGPT DR +
Gemini 3.1 Pro DR head-to-head on the 7 BEAT-BOTH dimensions:**
unique_citations, regulatory_coverage, jurisdictional_precision,
claim_frames, structural_depth, contradiction_handling_grammar,
narrative_length.

Competitor extracts at `state/compare_chatgpt_dr.txt` and
`state/compare_gemini_dr.txt`. M-D9 phase 2 (BEAT-BOTH scoring
substrate) has **never been run end-to-end against the actual
competitor extracts**.

---

## B. Wishlist coverage (Codex-corrected)

Re-coded per Codex round-1 review. PARTIAL = real surface
exists but not full-coverage; GAP = nothing real yet.

| # | Wish | Status | Gap to close |
|---|---|---|---|
| 1 | Real citations, not fabricated | DONE | (V30 strict-verify + Inspector view 1) |
| 2 | Pause/cancel/redirect mid-run | PARTIAL | Pause/cancel exist; redirect not implemented |
| 3 | Don't truncate output mid-run | DONE | (drop-on-verify guarded) |
| 4 | Citation-preserving export | DONE | (PDF/DOCX/MD with provenance) |
| 5 | Source organization (search/folders/tags/rename) | PARTIAL | Workspace exists; rich org UX missing |
| 6 | Stop skipping parts of corpora | PARTIAL | Frame coverage manifest helps; full coverage gate not yet |
| 7 | Quota/cost transparency before run | PARTIAL | Pre-flight estimate live; M-NEW quota gating not integrated |
| 8 | Durable long-running jobs | DONE | (job queue + checkpoints) |
| 9 | Internal corpus connectors | PARTIAL | Some import surfaces in `live_server.py`; M-25 substrate-only |
| 10 | OCR + image + multimodal ingestion | GAP | Not built |
| 11 | Source-tier control | DONE | (tier mix + Inspector view 5) |
| 12 | BYOK / OpenAI-compatible endpoint | GAP | Not built |
| 13 | Watched folders + auto-sync ingestion | GAP | M-25 v1 is registry only; connectors deferred |
| 14 | Shared workspaces + RBAC | DONE | (M-15a/b auth substrate, RBAC retrofit) |
| 15 | Notes/comments/annotations alongside sources | PARTIAL | Review notes exist; per-source annotations not delivered |
| 16 | Structured table CSV/XLSX export | PARTIAL | Tables in render path; mounted CSV/XLSX export route not found |
| 17 | KB-specific prompts/templates | DONE | (M-10/M-20 template router) |
| 18 | Cross-workspace memory | PARTIAL | Workspace memory live; cross-workspace/global memory not |
| 19 | Contradiction disclosure | DONE | (M-3 contradiction matrix view) |
| 20 | Slide deck / podcast / video / infographic | PARTIAL | M-22 substrate exists; PPTX deferred; podcast/video/infographic absent |

**Coverage tally:** 8 DONE + 9 PARTIAL + 3 GAP. The 12 PARTIAL/GAP
items are the wishlist work still ahead.

---

## C. Proposed plan (corrected sequence + missing milestones)

Phase E now covers EVERY substrate-only module from A.2. Each
milestone goes through Claude+Codex cross-review per autoloop V2.
**Acceptance is "invoked under flag with run-log evidence", not
just "imported"** (Codex round-1 fix).

### Phase E0 — Observability & repro prerequisites (5-6 days)

These come FIRST per Codex round-1 reorder — they're prerequisites
for trustworthy benchmarking later.

**M-INT-0a — Decision telemetry recording** (M-D3 → production)
- Wire `decision_telemetry.record_decision(...)` on every
  scope-gate + induction call site
- Touches: `template_classifier.py`, induction call sites in sweep
- Acceptance: run a sweep, confirm `decision_records.sqlite`
  has rows; flag `PG_RECORD_DECISIONS=0` disables
- Codex review: workspace_id propagated, PII not in proposed_payload

**M-INT-0b — Pin capture on every run** (M-D11 → production)
- Sweep writes a `ModelPin` after every run
- `--replay-from-pin <path>` CLI flag
- Acceptance: `manifest.json` references the captured pin path;
  replay reproduces a fixed test run; flag `PG_CAPTURE_PIN=0`
  disables
- Codex review: env_snapshot doesn't leak secrets, prompt
  SHA-256 verification works

### Phase E1 — Data-plane integration (8-10 days)

**M-INT-1 — Parallel fetch into live_retriever** (3 days)
- Path: `src/polaris_graph/retrieval/live_retriever.py`
- Replace serial loop with `parallel_fetch.parallel_fetch(...)`
- Per-backend rate limits: Serper=10, SS=1, DDG=4
- Flag: `PG_USE_PARALLEL_FETCH=0` disables (rollback)
- Acceptance: run-log shows `ParallelFetchReport` with
  success_count > 0; observable speedup on 16-query smoke
- Codex review: rate limits preserved, regression on existing
  16/16 smoke

**M-INT-2 — Cache + cache-warming around sweep** (3 days)
- Pre-warm `RetrievalCacheStore` on canonical sources before
  sweep dispatch
- Concrete `CacheFetcher` wrapping HTTP
- Hook into `scripts/run_honest_sweep_r3.py`
- Flag: `PG_USE_CACHE_WARMING=0` disables
- Acceptance: 2nd run shows cache-hit count > 0; no double-fetch

**M-INT-3 — Freshness detector + eviction** (4 days)
- Concrete `FreshnessDetector` using Crossref `update-policy`
- Wire `FreshnessAlertStore` into M-D7 cache-eviction trigger
- Periodic re-check loop (daemon stub; full daemon = Phase F)
- Flag: `PG_USE_FRESHNESS_DETECTOR=0` disables
- Acceptance: simulated retracted DOI triggers eviction; UNREACHABLE
  status doesn't evict
- Codex review: 5-status taxonomy enforced

### Phase E2 — Decision-plane integration (6-8 days)

**M-INT-4 — OpenRouter ScopeAffinityLLM** (3 days)
- Concrete `OpenRouterScopeAffinityLLM` mirroring
  `auto_induction.OpenRouterTemplateAffinityClassifier`
- Plug into `LLMScopeEligibilityClassifier` in production
- Flag: `PG_USE_LLM_SCOPE=0` falls back to Mock
- Acceptance: live query gets a real LLM-classified scope verdict;
  cost ContextVar shows non-zero
- Codex review: prompt-injection delimiters intact

**M-INT-5 — Domain router into live retrieval flow** (4 days)
- After `confidence_gated_match` + LLM scope, call `route_to_domain`
- Concrete `DomainAdapter` for clinical (Crossref + PubMed)
- Flag: `PG_USE_DOMAIN_ROUTER=0` disables
- Acceptance: clinical-domain query routes to clinical adapters;
  out-of-scope query rejects pre-fetch
- Codex review: UNCERTAIN-verdict fallback path

### Phase E3 — Auto-induction surfacing (3-4 days, missing milestone per Codex round-1)

**M-INT-6 — Inductor in production gate**
- Wire `auto_induction.LLMAugmentedInductor` (M-D2 phase b)
  into the operator-review queue
- M-D1 validation set runs as a CI test on every release
- Flag: `PG_USE_AUTO_INDUCTION=0` disables (operator-only)
- Acceptance: operator-review queue shows induced contracts;
  precision metric on M-D1 set logged
- Codex review: M-D1 abstain criterion respected; abstain →
  operator review, not silent skip

### Phase E4 — Late Phase C wiring (8-10 days, missing per Codex round-1)

**M-INT-7 — M-NEW billing/quota gating** (3 days)
- Wire `billing_quota_store.check_quota(...)` into the audit-job
  enqueue endpoint + audit-bundle export endpoint + workspace
  creation
- Flag: `PG_ENFORCE_QUOTA=0` disables (dev mode)
- Acceptance: over-quota org's enqueue returns 402; reset_monthly
  works
- Closes wishlist #7 PARTIAL → DONE

**M-INT-8 — M-22 slide deck endpoint** (2 days)
- HTML deck render route in `inspector_router.py`
- PPTX deferred to M-LATE-1 (Phase G+)
- Acceptance: `GET /api/inspector/runs/{slug}/deck.html` renders
- Closes wishlist #20 from PARTIAL toward DONE for HTML deliverable

**M-INT-9 — M-26 contract drafting endpoint** (2 days)
- Wire `contract_draft_store` into review-queue UI
- Acceptance: operator can review drafted contracts in queue

**M-INT-10 — M-25 connector v2** (3 days, narrow scope)
- Drive connector only (Drive is wishlist top-3 reach, others
  are nice-to-have)
- Acceptance: approved Drive folder syncs into bounded upload
- Closes wishlist #9, #13 from PARTIAL toward DONE

### Phase F — End-to-end live audit + BEAT-BOTH (10-13 days)

**M-LIVE-1 — V19 single-query end-to-end smoke** (3 days)
- One real query through the integrated pipeline
- All Phase E substrates fire (verified by run-log)
- Manifest + audit bundle + Inspector views all render
- Codex review: artifact completeness, every substrate
  invocation count > 0

**M-LIVE-2 — BEAT-BOTH head-to-head** (5 days)
- Extract `state/compare_chatgpt_dr.txt` +
  `state/compare_gemini_dr.txt` into manifest shape
  (M-D9 phase 1 manifest schema)
- Three `score_run(...)` calls + two `diff_dimension_scores(...)`
- Per-dimension verdict: BEAT-BOTH / BEAT-ONE / BEHIND
- Codex review:
  - Independently re-extract competitor manifests → does Codex
    agree with our extraction?
  - Cross-check verdict math
  - Risk: extraction normalization can invalidate the verdict
    (Codex round-1 missing-risk callout)

**M-LIVE-3 — Operator dashboard (Inspector aggregates)** (4 days)
- New Inspector view exposing `compute_aggregates`,
  `compute_freshness_aggregates`, `analyze_pin_trends` data
- Codex review: workspace isolation in UI

**M-LIVE-4 — M-D9 regression-lab CI integration** (1 day, missing per Codex round-1)
- M-D9 phase 1 regression check runs as a CI gate on every
  release
- Flag: GREEN/YELLOW pass; RED blocks merge

### Phase G — Close BEAT-BOTH gaps (4-8 weeks, indeterminate)

Each BEAT-BOTH dimension where V_N is BEHIND or BEAT-ONE
becomes a concrete fix milestone. Likely candidates per V31/V32/V33
history:

- **dim 1 (unique_citations)** — fix via M-INT-10 connector
  expansion + parallel-fetch concurrency tuning
- **dim 2 (regulatory_coverage)** — V34 expansion; concrete
  M-D6 phase 2 adapters (FDA + EMA + Health Canada)
- **dim 6 (contradiction_handling_grammar)** — historical
  asymptote-stop risk. Synthesizer hedging upgrade
  (M-71/M-72 territory)
- **dim 7 (narrative_length)** — synthesis capacity tuning

Each gap → milestone → Claude+Codex review → ship → re-run
BEAT-BOTH → next gap. Stop: BEAT-BOTH on all 7 OR asymptote-stop
with documented threat-model boundary.

### Phase H — Production hardening + pilot launch (3-4 weeks)

**M-PROD-1 — SOC2 dry-run + remediation** (10 days)
**M-PROD-2 — First paying pilot customer** (5 days)
**M-PROD-3 — Production observability** (5 days)
**M-PROD-4 — Public release notes + supported-scope page** (2 days)

---

## D. Honest timeline + risks (Codex-corrected)

**Total ETA:** 14-22 calendar weeks (revised UP from 12-19
per Codex round-1 reality check).

Lower bound assumes Codex sandbox cooperates, no architectural
surprises, BEAT-BOTH gaps closeable. Upper bound includes Phase G
indeterminacy + late Phase C wiring expansion.

**Phase ETAs:**

| Phase | Days | Weeks | Outcome |
|---|---:|---:|---|
| E0 (observability) | 5-6 | 1-1.5 | Telemetry + pinning live |
| E1 (data-plane) | 8-10 | 2-2.5 | Parallel + cache + freshness |
| E2 (decision-plane) | 6-8 | 1.5-2 | Real LLM scope + domain router |
| E3 (auto-induction) | 3-4 | 0.5-1 | Inductor in operator queue |
| E4 (Phase C wiring) | 8-10 | 2-2.5 | Billing/deck/contract/connector |
| F (live audit + BEAT-BOTH) | 10-13 | 2-3 | Verdict on tier-1 |
| G (close gaps) | 20-40 | 4-8 | BEAT-BOTH on all 7 dims |
| H (pilot launch) | 22 | 3-4 | One paying pilot live |
| **Total** | **82-113** | **14-22** | **Fully online + tier-1 parity** |

**Key risks (Codex-corrected, 7 risks):**

1. **BEAT-BOTH dimension 6 (contradiction_handling_grammar) may
   not close cleanly.** Historical asymptote risk. Mitigation:
   M-D9 phase 2 substrate scores it; gap visible after M-LIVE-2;
   scope-decision pivot (BEAT-ONE positioning) on the table.

2. **Benchmark validity (Codex round-1 NEW risk).**
   Competitor-extract normalization + scorer misuse can
   invalidate the BEAT-BOTH verdict. Mitigation: M-LIVE-2 has
   Codex independently re-extract competitor manifests + verify
   verdict math. If extractions disagree, reconcile before
   shipping verdict.

3. **Reproducibility/nondeterminism after Phase E (Codex
   round-1 NEW risk).** Parallel fetch + cache + LLM scope +
   domain routing all introduce variance. Mitigation: M-INT-0b
   pin capture lands FIRST in E0 so every run is replayable;
   reproducibility test in CI.

4. **OpenRouter cost spikes** during M-INT-4 + M-LIVE-2.
   Mitigation: M-NEW billing/quotas (M-INT-7) gates production;
   per-day hard cap; cost ContextVar verified by Codex review.

5. **Freshness false-positives evict good cache entries.**
   Mitigation: M-INT-3 Codex review checks UNREACHABLE doesn't
   evict; daemon stub only in Phase F.

6. **The "fucking around" critique repeats.** Mitigation: every
   integration milestone has explicit "imported AND invoked
   under flag AND run-log evidence" acceptance — Codex
   verifies all three. The
   `feedback_substrate_is_not_product.md` memory rule is
   load-on-startup.

7. **Sandbox cutoffs in Codex review.** Mitigation: continue
   verdict-only fallback brief pattern, but verify the FULL
   stdout.log before assuming cutoff (per round-3-of-M-D5p2
   lesson). 4 audit-trail caveat locks this session were
   premature; that pattern doesn't repeat.

---

## E. Codex's job in this plan (unchanged)

Every milestone goes through Claude+Codex cross-review.
Codex specifically:

1. **Verifies production-import + invocation.** Each integration
   milestone, Codex grep-verifies the new substrate is imported
   AND grep-verifies it's actually called from the integration
   site. "Imported but unused" doesn't pass.
2. **Run-log evidence required.** Integration reviews ask for
   real run output (`run_honest_sweep_r3.py --only <test>`)
   showing the substrate fired with non-zero invocation count.
3. **Diff-against-baseline.** For integration milestones, Codex
   is told what the old code did and verifies the new code
   preserves observable behavior except the deliberate change.
4. **Rollback flag check.** Each integration ships with a
   `PG_USE_*` env flag that disables the new path. Codex
   verifies the flag actually disables (not just defaults).
5. **Cross-review the BEAT-BOTH verdict.** When M-LIVE-2 runs,
   Codex independently extracts competitor manifests + scores
   them. Disagreement → reconcile; agreement → ship verdict.
6. **Cost ContextVar propagation check** on every LLM-touching
   integration (M-INT-4, M-INT-6, M-LIVE-2).

---

## Codex output requested for round 2

Sign as the canonical roadmap, or list residual fixes.

Output format:

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-1 fix integration
- [x/ ] Section A re-baselined into 3 buckets
- [x/ ] Stale paths corrected
- [x/ ] Wishlist statuses downgraded per round-1 list
- [x/ ] Phase E0 added covering missing milestones (M-D1, M-D2, M-D9)
- [x/ ] Telemetry + pinning moved to E0 (earliest)
- [x/ ] Benchmark validity + reproducibility risks added

## New findings (if any)
[SEVERITY] specific finding

## Final word
[Sign or list residual fixes]
```

Tool hints:
- DO NOT run rg/find — state already audited.
- DO NOT run pytest — planning review only.
- Round-1 brief at `outputs/codex_findings/full_online_plan_round1/brief.md`
  if you want to compare.
