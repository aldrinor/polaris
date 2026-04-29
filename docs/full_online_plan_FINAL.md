# POLARIS — Full Plan from Today to Fully Online

**Status:** v4 FINAL — **Claude + Codex GREEN-signed canonical roadmap**
**Date:** 2026-04-29
**Authors:** Claude (Opus 4.7) + Codex (gpt-5.4 xhigh)
**Codex pass-3 verdict (verbatim):** *"Signed as the canonical roadmap. The round-2 HIGH is closed: M-24 is now explicitly integrated in Phase E4, the E4 and total ETA deltas propagate consistently, and the A.2 coverage gap is closed."*

**v4 delta over v3 (Codex round-3 LOW closure):** explicit PG_USE_* rollback flags named for M-INT-8 / M-INT-9 / M-INT-10 / M-INT-11.

**Provenance:** 3 review rounds (round-1 PARTIAL → 2 PARTIAL → 3 GREEN with LOW polish → 4 v4 FINAL with all flags explicit). Briefs + Codex stdout at `outputs/codex_findings/full_online_plan_round{1,2,3}/`.

---

## A. Where we are today (3-bucket re-baseline)

### A.1 Bucket 1 — REAL + INTEGRATED into mounted production path

Verified by Codex grep: each is invoked by `live_server.py`'s mounted Inspector router or by the production sweep runner.

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

### A.2 Bucket 2 — REAL but SUBSTRATE-ONLY (the integration backlog)

21 modules with tests + threat-model docs but NO production import.

**Phase D substrates (16):**

| ID | Module |
|---|---|
| M-D1 | validation set + abstain criterion |
| M-D2 phase a/b | `auto_induction/keyword_inductor.py`, `llm_inductor.py` |
| M-D3 phase 1+2 | `audit_ir/decision_telemetry.py`, `decision_aggregates.py` |
| M-D5 phase 1+2 | `audit_ir/scope_classifier.py`, `scope_classifier_llm.py` |
| M-D6 phase 1 | `audit_ir/domain_router.py` |
| M-D7 phase 1+2 | `audit_ir/retrieval_cache.py`, `cache_warming.py` |
| M-D8 phase 1 | `audit_ir/parallel_fetch.py` |
| M-D9 phase 1+2 | `audit_ir/regression_lab.py`, `beat_both_scoring.py` |
| M-D10 phase 1+2 | `audit_ir/freshness_monitor.py`, `freshness_aggregates.py` |
| M-D11 phase 1+2+v2 | `audit_ir/model_pin.py`, `pin_replay.py`, `pin_trends.py` |

**Late Phase C substrate-only (5):**

| ID | Module | Per its docstring |
|---|---|---|
| M-NEW | `audit_ir/billing_quota_store.py` | "endpoint that wires this in is added separately" |
| M-22 | `audit_ir/slide_deck.py` | "PPTX export deferred to v2" |
| M-24 | `audit_ir/support_ticket_store.py` | substrate, no endpoints |
| M-25 | `audit_ir/private_corpus_sync.py` | "v2 wires the connectors" |
| M-26 | `audit_ir/contract_draft_store.py` | substrate |

### A.3 Bucket 3 — NON-CODE operational/commercial

| ID | What |
|---|---|
| M-19 | Pilot-grade SOC2 readiness pack |
| M-27 | Pricing/positioning copy + scope page |
| M-D4 | Calendar-blocked: needs ≥6 months M-D3 telemetry |
| M-D12 | Calendar-blocked: external auditor lead time |

### A.4 The user-mandated finish line

Per `~/.claude/projects/C--POLARIS/memory/autoloop_beat_tier1_mandate.md`:

**From V19 onward, stop criterion = V_N beats ChatGPT DR + Gemini 3.1 Pro DR head-to-head on the 7 BEAT-BOTH dimensions.** Competitor extracts at `state/compare_chatgpt_dr.txt` and `state/compare_gemini_dr.txt`. Has never run end-to-end against actual extracts.

---

## B. Wishlist coverage (from FINAL_PLAN.md, 50 primary user sources)

| # | Wish | Status | Gap |
|---|---|---|---|
| 1 | Real citations | DONE | — |
| 2 | Pause/cancel/redirect | PARTIAL | redirect not implemented |
| 3 | Don't truncate output | DONE | — |
| 4 | Citation-preserving export | DONE | — |
| 5 | Source organization | PARTIAL | rich org UX missing |
| 6 | Stop skipping corpora parts | PARTIAL | full coverage gate not yet |
| 7 | Quota/cost transparency | PARTIAL | M-NEW not integrated |
| 8 | Durable long-running jobs | DONE | — |
| 9 | Internal corpus connectors | PARTIAL | M-25 substrate-only |
| 10 | OCR/multimodal | GAP | not built |
| 11 | Source-tier control | DONE | — |
| 12 | BYOK/OpenAI-compatible | GAP | not built |
| 13 | Watched folders/auto-sync | GAP | M-25 v1 registry only |
| 14 | Workspaces + RBAC | DONE | — |
| 15 | Notes alongside sources | PARTIAL | per-source annotations missing |
| 16 | CSV/XLSX export | PARTIAL | no mounted route |
| 17 | KB-specific templates | DONE | — |
| 18 | Cross-workspace memory | PARTIAL | global memory not built |
| 19 | Contradiction disclosure | DONE | — |
| 20 | Slide deck/podcast/video | PARTIAL | M-22 substrate; PPTX deferred |

**Tally:** 8 DONE, 9 PARTIAL, 3 GAP. 12 wishlist items still ahead.

---

## C. Phase plan (every A.2 substrate has a named integration milestone)

**Acceptance for every Phase E milestone:** "imported AND invoked under flag AND run-log evidence". Codex grep-verifies the substrate is imported by the named production file AND grep-verifies it's actually called. Each milestone ships with an explicit `PG_USE_*` rollback flag.

### Phase E0 — Observability & repro prerequisites (5-6 days)

**M-INT-0a — Decision telemetry recording** (M-D3 → production)
- Wire `decision_telemetry.record_decision(...)` on every scope-gate + induction call
- Touches: `template_classifier.py`, induction call sites
- Flag: `PG_RECORD_DECISIONS=0` disables
- Acceptance: `decision_records.sqlite` has rows after a sweep
- Codex review: workspace_id propagated, no PII in `proposed_payload`

**M-INT-0b — Pin capture on every run** (M-D11 → production)
- Sweep writes a `ModelPin` after every run
- New CLI flag `--replay-from-pin <path>` uses `replay_pin(...)`
- Flag: `PG_CAPTURE_PIN=0` disables
- Acceptance: `manifest.json` references the captured pin path; replay reproduces a fixed test run
- Codex review: env_snapshot doesn't leak secrets, prompt SHA-256 verification works

### Phase E1 — Data-plane integration (8-10 days)

**M-INT-1 — Parallel fetch into live_retriever** (3 days)
- Path: `src/polaris_graph/retrieval/live_retriever.py`
- Replace serial loop with `parallel_fetch.parallel_fetch(...)`
- Per-backend rate limits: Serper=10, SS=1, DDG=4
- Flag: `PG_USE_PARALLEL_FETCH=0` disables (rollback)
- Acceptance: run-log shows `ParallelFetchReport` with success_count > 0; observable speedup on 16-query smoke
- Codex review: rate-limit compliance preserved, regression on existing 16/16 smoke

**M-INT-2 — Cache + cache-warming around sweep** (3 days)
- Pre-warm `RetrievalCacheStore` on canonical sources before sweep dispatch
- Concrete `CacheFetcher` wrapping HTTP
- Hook into `scripts/run_honest_sweep_r3.py`
- Flag: `PG_USE_CACHE_WARMING=0` disables
- Acceptance: 2nd run shows cache-hit count > 0; no double-fetch
- Codex review: workspace_id propagation, on_fetcher_error="record" semantic

**M-INT-3 — Freshness detector + eviction** (4 days)
- Concrete `FreshnessDetector` using Crossref `update-policy`
- Wire `FreshnessAlertStore` into M-D7 cache-eviction trigger
- Periodic re-check loop (daemon stub; full daemon = Phase F)
- Flag: `PG_USE_FRESHNESS_DETECTOR=0` disables
- Acceptance: simulated retracted DOI triggers eviction; UNREACHABLE doesn't evict
- Codex review: 5-status taxonomy enforced

### Phase E2 — Decision-plane integration (6-8 days)

**M-INT-4 — OpenRouter ScopeAffinityLLM** (3 days)
- Concrete `OpenRouterScopeAffinityLLM` mirroring `auto_induction.OpenRouterTemplateAffinityClassifier`
- Plug into `LLMScopeEligibilityClassifier` in production
- Flag: `PG_USE_LLM_SCOPE=0` falls back to Mock
- Acceptance: live query gets a real LLM-classified scope verdict; cost ContextVar shows non-zero
- Codex review: prompt-injection delimiters intact, JSON schema enforcement, retry/backoff sane

**M-INT-5 — Domain router into live retrieval flow** (4 days)
- After `confidence_gated_match` + LLM scope, call `route_to_domain`
- Concrete `DomainAdapter` for clinical (Crossref + PubMed)
- Flag: `PG_USE_DOMAIN_ROUTER=0` disables
- Acceptance: clinical-domain query routes to clinical adapters; out-of-scope query rejects pre-fetch
- Codex review: UNCERTAIN-verdict fallback path

### Phase E3 — Auto-induction surfacing (3-4 days)

**M-INT-6 — Inductor in production gate** (3-4 days)
- Wire `auto_induction.LLMAugmentedInductor` (M-D2 phase b) into the operator-review queue
- M-D1 validation set runs as a CI test on every release
- Flag: `PG_USE_AUTO_INDUCTION=0` disables (operator-only fallback)
- Acceptance: operator-review queue shows induced contracts; precision metric on M-D1 set logged
- Codex review: M-D1 abstain criterion respected; abstain → operator review (not silent skip)

### Phase E4 — Late Phase C wiring (10-12 days)

**M-INT-7 — M-NEW billing/quota gating** (3 days)
- Wire `billing_quota_store.check_quota(...)` into audit-job enqueue + audit-bundle export + workspace creation
- Flag: `PG_ENFORCE_QUOTA=0` disables (dev mode)
- Acceptance: over-quota org's enqueue returns 402; reset_monthly works
- Closes wishlist #7 PARTIAL → DONE

**M-INT-8 — M-22 slide deck endpoint** (2 days)
- HTML deck render route in `inspector_router.py`
- PPTX deferred to M-LATE-1 (Phase G+)
- Flag: `PG_USE_SLIDE_DECK_EXPORT=0` disables route
- Acceptance: `GET /api/inspector/runs/{slug}/deck.html` renders
- Closes wishlist #20 PARTIAL toward DONE for HTML deliverable

**M-INT-9 — M-26 contract drafting endpoint** (2 days)
- Wire `contract_draft_store` into review-queue UI
- Flag: `PG_USE_CONTRACT_DRAFTING=0` disables route
- Acceptance: operator can review drafted contracts in queue
- Codex review: workspace isolation, audit-trail preservation

**M-INT-10 — M-25 connector v2 (Drive only)** (3 days)
- Drive connector only; SharePoint/Confluence deferred
- Flag: `PG_USE_DRIVE_CONNECTOR=0` disables sync trigger
- Acceptance: approved Drive folder syncs into bounded upload
- Closes wishlist #9, #13 PARTIAL toward DONE

**M-INT-11 — M-24 customer support flow** (2 days)
- Wire `audit_ir/support_ticket_store.py` into inspector router
- Endpoints: `POST /api/inspector/tickets`, `GET /api/inspector/tickets`, `GET /api/inspector/tickets/{ticket_id}`, `POST /api/inspector/tickets/{ticket_id}/comments`
- Flag: `PG_USE_SUPPORT_TICKETS=0` disables routes (404)
- Acceptance: customer creates ticket; operator sees in queue; workspace isolation pinned
- Codex review: workspace_id propagation, no PII in payload by default, SOC2 audit trail intact

### Phase F — End-to-end live audit + BEAT-BOTH (10-13 days)

**M-LIVE-1 — V19 single-query end-to-end smoke** (3 days)
- One real query through the integrated pipeline
- All Phase E substrates fire (verified by run-log)
- Manifest + audit bundle + Inspector views all render
- Codex review: artifact completeness, every substrate's invocation count > 0

**M-LIVE-2 — BEAT-BOTH head-to-head** (5 days)
- Extract `state/compare_chatgpt_dr.txt` + `state/compare_gemini_dr.txt` into M-D9 manifest shape
- Three `score_run(...)` calls + two `diff_dimension_scores(...)` calls
- Per-dimension verdict: BEAT-BOTH / BEAT-ONE / BEHIND
- Codex review:
  - Independently re-extracts competitor manifests; reconcile if disagreement
  - Cross-checks verdict math
  - Risk flagged: extraction normalization can invalidate verdict

**M-LIVE-3 — Operator dashboard (Inspector aggregates)** (4 days)
- New Inspector view exposing `compute_aggregates`, `compute_freshness_aggregates`, `analyze_pin_trends`
- Workspace-scoped, time-windowed
- Codex review: workspace isolation in UI, rate denominators match substrate semantics

**M-LIVE-4 — M-D9 regression-lab CI integration** (1 day)
- M-D9 phase 1 regression check runs as CI gate on every release
- GREEN/YELLOW pass; RED blocks merge

### Phase G — Close BEAT-BOTH gaps (4-8 weeks, indeterminate)

Each dimension where V_N is BEHIND or BEAT-ONE → concrete fix milestone. Likely candidates:

- **dim 1 (unique_citations)** — M-INT-10 connector expansion + parallel-fetch concurrency tuning
- **dim 2 (regulatory_coverage)** — V34 expansion; concrete M-D6 phase 2 adapters (FDA + EMA + Health Canada)
- **dim 6 (contradiction_handling_grammar)** — historical asymptote-stop risk; synthesizer hedging upgrade (M-71/M-72 territory)
- **dim 7 (narrative_length)** — synthesis capacity tuning

Stop: BEAT-BOTH on all 7 OR asymptote-stop with documented threat-model boundary.

### Phase H — Production hardening + pilot launch (3-4 weeks)

- **M-PROD-1 — SOC2 dry-run + remediation** (10 days)
- **M-PROD-2 — First paying pilot customer** (5 days)
- **M-PROD-3 — Production observability** (5 days)
- **M-PROD-4 — Public release notes + supported-scope page** (2 days)

---

## D. Coverage table — every A.2 substrate has a Phase E milestone

| A.2 substrate | Phase E milestone | Rollback flag |
|---|---|---|
| M-D1 validation set | M-INT-6 (E3) | `PG_USE_AUTO_INDUCTION` |
| M-D2 phase a/b inductor | M-INT-6 (E3) | `PG_USE_AUTO_INDUCTION` |
| M-D3 phase 1+2 telemetry | M-INT-0a (E0) | `PG_RECORD_DECISIONS` |
| M-D5 phase 1+2 scope+LLM | M-INT-4 (E2) | `PG_USE_LLM_SCOPE` |
| M-D6 phase 1 domain router | M-INT-5 (E2) | `PG_USE_DOMAIN_ROUTER` |
| M-D7 phase 1+2 cache | M-INT-2 (E1) | `PG_USE_CACHE_WARMING` |
| M-D8 phase 1 parallel fetch | M-INT-1 (E1) | `PG_USE_PARALLEL_FETCH` |
| M-D9 phase 1 regression lab | M-LIVE-4 (F) | (CI gate; flag = green/yellow/red) |
| M-D9 phase 2 BEAT-BOTH | M-LIVE-2 (F) | (review process; not flagged) |
| M-D10 phase 1+2 freshness | M-INT-3 (E1) | `PG_USE_FRESHNESS_DETECTOR` |
| M-D11 phase 1+2+v2 pin/replay | M-INT-0b (E0) + M-LIVE-3 (F) | `PG_CAPTURE_PIN` |
| M-NEW billing/quota | M-INT-7 (E4) | `PG_ENFORCE_QUOTA` |
| M-22 slide deck | M-INT-8 (E4) | `PG_USE_SLIDE_DECK_EXPORT` |
| M-24 support ticket | M-INT-11 (E4) | `PG_USE_SUPPORT_TICKETS` |
| M-25 private corpus sync | M-INT-10 (E4) | `PG_USE_DRIVE_CONNECTOR` |
| M-26 contract drafting | M-INT-9 (E4) | `PG_USE_CONTRACT_DRAFTING` |

**21 substrate modules → 21 integration milestones, each with rollback flag.**

---

## E. Honest timeline

| Phase | Days | Weeks | Outcome |
|---|---:|---:|---|
| E0 (observability) | 5-6 | 1-1.5 | Telemetry + pinning live |
| E1 (data-plane) | 8-10 | 2-2.5 | Parallel + cache + freshness |
| E2 (decision-plane) | 6-8 | 1.5-2 | Real LLM scope + domain router |
| E3 (auto-induction) | 3-4 | 0.5-1 | Inductor in operator queue |
| E4 (Phase C wiring) | 10-12 | 2-2.5 | Billing/deck/contract/connector/support |
| F (live audit + BEAT-BOTH) | 10-13 | 2-3 | Verdict on tier-1 |
| G (close gaps) | 20-40 | 4-8 | BEAT-BOTH on all 7 dims |
| H (pilot launch) | 22 | 3-4 | One paying pilot live |
| **Total** | **84-115** | **14-23** | **Fully online + tier-1 parity** |

Lower bound = Codex sandbox cooperates, no architectural surprises, BEAT-BOTH gaps closeable. Upper bound = Phase G indeterminacy + late Phase C expansion.

---

## F. Risks (7 named)

1. **BEAT-BOTH dimension 6 (contradiction_handling_grammar) may not close cleanly.** Historical asymptote risk per V31/V32/V33. Mitigation: gap visible after M-LIVE-2; scope-decision pivot (BEAT-ONE positioning) on the table.

2. **Benchmark validity.** Competitor-extract normalization + scorer misuse can invalidate the BEAT-BOTH verdict. Mitigation: M-LIVE-2 has Codex independently re-extract competitor manifests + verify verdict math. If extractions disagree, reconcile before shipping verdict.

3. **Reproducibility/nondeterminism after Phase E.** Parallel fetch + cache + LLM scope + domain routing all introduce variance. Mitigation: M-INT-0b pin capture lands FIRST in E0 so every run is replayable; reproducibility test in CI.

4. **OpenRouter cost spikes** during M-INT-4 + M-LIVE-2. Mitigation: M-NEW billing/quotas (M-INT-7) gates production; per-day hard cap; cost ContextVar verified by Codex review.

5. **Freshness false-positives evict good cache entries.** Mitigation: M-INT-3 Codex review checks UNREACHABLE doesn't evict; daemon stub only in Phase F.

6. **The "fucking around" critique repeats.** Mitigation: every integration milestone has explicit "imported AND invoked under flag AND run-log evidence" acceptance — Codex verifies all three. The `feedback_substrate_is_not_product.md` memory rule is load-on-startup.

7. **Sandbox cutoffs in Codex review.** Mitigation: continue verdict-only fallback brief pattern, but verify the FULL stdout.log before assuming cutoff. The 4 audit-trail caveat locks earlier this session were premature; that pattern doesn't repeat.

---

## G. Codex's job in every milestone

1. **Production-import + invocation grep-verify.** Substrate is imported by the named production file AND actually called from it. "Imported but unused" doesn't pass.
2. **Run-log evidence required.** Integration reviews ask for real run output (`run_honest_sweep_r3.py --only <test>`) showing the substrate fired with non-zero invocation count.
3. **Diff-against-baseline.** What did the old code do? What changed? Did anything else change unintentionally?
4. **Rollback flag check.** `PG_USE_*` flag must actually disable the new path (default + override both verified).
5. **Cross-review the BEAT-BOTH verdict.** When M-LIVE-2 runs, Codex independently extracts competitor manifests + scores them. Disagreement → reconcile; agreement → ship.
6. **Cost ContextVar propagation check** on every LLM-touching integration (M-INT-4, M-INT-6, M-LIVE-2).

---

## H. The first move

**M-INT-0a — Decision telemetry recording** is the natural first integration. Highest leverage (every downstream measurement depends on it), smallest blast radius (additive write path; failure to write doesn't gate decisions), and unblocks the M-D4 calendar-blocked auto-trust gate by starting the ≥6-month telemetry accumulator clock today.

Once M-INT-0a is GREEN-locked: M-INT-0b (pinning) → M-INT-1 (parallel fetch) → M-INT-2 (cache) → ... per the phase order above.
