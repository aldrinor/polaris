# Joint plan — POLARIS from today to fully functional online

**Author:** Claude (Opus 4.7), drafting WITH Codex (gpt-5.4 xhigh).
**Date:** 2026-04-29.
**Goal:** end-to-end plan from today to a state where (a) the
production code path consumes every locked substrate, (b) one
fully integrated end-to-end audit run completes against real
LLM/HTTP backends, (c) V_N beats ChatGPT DR + Gemini 3.1 Pro DR
on the 7 BEAT-BOTH dimensions per the user-mandated criterion
in `autoloop_beat_tier1_mandate.md`.

The user has been firm:
- "Just fucking around?" — locked substrates are not product.
- "We still need Codex to help us to review every single thing."
- "Don't forget the previous wish list on the functions that you
  previous gather."

This brief is for Codex to review and (if it agrees) sign as the
canonical plan. Output format spec at the bottom.

---

## A. Where we actually are today (honest audit)

### A.1 What's REAL and INTEGRATED (Phase A/B/C builds, M-1..M-27)

These shipped through the FINAL_PLAN.md GREEN-locked path
(autoloop V2, Codex pass-4 sign-off, 2026-04-26). Each was
imported by production code BEFORE being locked:

- M-1 Audit Graph IR loader (`src/polaris_graph/audit_ir/loader.py`)
- M-2..M-7 Evidence Inspector 5 views (`audit_ir/inspector_router.py`,
  39 FastAPI routes wired into `scripts/live_server.py`:1438)
- M-8..M-9 Job queue + V30 integration with checkpoints
  (`audit_ir/job_queue.py`, `job_runner.py`, `job_worker.py`)
- M-10 Curated template router with confidence gating
- M-11 Bounded upload + workspace data model
- M-12 Question-Bound Corpus Brief (`audit_ir/corpus_brief.py`)
- M-13 Progressive in-run Inspector surfaces (`progress_surfaces.py`)
- M-14 V34 cross-jurisdiction synthesizer
- M-15a/b Auth substrate + retrofit (`auth_middleware.py`,
  `auth_store.py`)
- M-16 Audit bundle export + run diff
- M-17 Citation health checks (`citation_health.py`)
- M-18 Regression alerts (`regression_alerts.py`)
- M-19 Pilot-grade SOC2 readiness
- M-NEW Billing + quotas (`billing_quota_store.py`)
- M-20 Template router scaling (`template_classifier.py`)
- M-21 Retrieval-active workspace memory
- M-22 Cited slide deck export
- M-23 Human review queue (`review_store.py`)
- M-24 Customer support flow
- M-25 Narrow private-corpus sync (`private_corpus_sync.py`)
- M-26 Semi-automated contract drafting (`contract_draft_store.py`)
- M-27 Pricing/positioning copy

Test coverage: 3,278 tests collected; 154 test files in
`tests/polaris_graph/`.

**Verdict on this layer**: production path serves the Evidence
Inspector at `/inspector`, the API at `/api/inspector/*`. The
core wishlist surface (Phase A/B/C) is **already online for
controlled-access**.

### A.2 What's REAL but NOT INTEGRATED (Phase D autoloop V2 plumbing)

These shipped during the recent autoloop session. They have
boundary tests + threat-model docs + Codex review trails. The
production code path (`live_retriever.py`,
`run_honest_sweep_r3.py`, `live_server.py`,
`audit_ir/inspector_router.py`) does **NOT** import them yet.

| ID | Module | Purpose |
|---|---|---|
| M-D1 | (validation set + abstain criterion) | Auto-induction precision benchmark |
| M-D2 phase a/b | `auto_induction/keyword_inductor.py`, `llm_inductor.py` | Inductor v5 + LLM-augmented |
| M-D3 phase 1+2 | `audit_ir/decision_telemetry.py`, `decision_aggregates.py` | Decision recording + aggregation |
| M-D5 phase 1+2 | `audit_ir/scope_classifier.py`, `scope_classifier_llm.py` | Confidence-gated scope + LLM classifier |
| M-D6 phase 1 | `audit_ir/domain_router.py` | Cross-domain routing substrate |
| M-D7 phase 1+2 | `audit_ir/retrieval_cache.py`, `cache_warming.py` | Cache + warming substrate |
| M-D8 phase 1 | `audit_ir/parallel_fetch.py` | Parallel fetch substrate |
| M-D9 phase 1+2 | `audit_ir/regression_lab.py`, `beat_both_scoring.py` | Regression + BEAT-BOTH dimension scoring |
| M-D10 phase 1+2 | `audit_ir/freshness_monitor.py`, `freshness_aggregates.py` | Citation freshness |
| M-D11 phase 1+2+v2 | `audit_ir/model_pin.py`, `pin_replay.py`, `pin_trends.py` | Model pinning + replay + trends |

Total Phase D: 614/614 tests passing in M-D suite. **Zero of
these modules are imported by the production live retrieval /
sweep / server code paths.** They're pure substrate.

### A.3 What's calendar-blocked or out-of-substrate-scope

- **M-D4** (auto-trust gate) — needs ≥6 months of M-D3
  telemetry; substrate ready, gate logic deferred.
- **M-D12** (formal SOC2) — external auditor lead time.
- **M-D6 phase 2** (concrete domain adapters NIST/MITRE/FAERS/
  EudraVigilance/ASTM) — needs API keys + HTTP wiring per
  domain; deferred.
- **OpenRouterScopeAffinityLLM** — concrete LLM-backed impl of
  M-D5 phase 2's `ScopeAffinityLLM` Protocol; substrate has the
  Mock impl only.

### A.4 The user-mandated finish line

Per `autoloop_beat_tier1_mandate.md` (locked memory,
2026-04-20): **From V19 onward, stop criterion is "V_N beats
ChatGPT DR + Gemini 3.1 Pro DR head-to-head on the 7 BEAT-BOTH
dimensions"** (unique_citations, regulatory_coverage,
jurisdictional_precision, claim_frames, structural_depth,
contradiction_handling_grammar, narrative_length).

Competitor outputs are at `state/compare_chatgpt_dr.txt` and
`state/compare_gemini_dr.txt`. M-D9 phase 2 is the BEAT-BOTH
scoring substrate; it has **never been run end-to-end against
the actual competitor extracts**.

---

## B. The previous wishlist (FINAL_PLAN.md, locked GREEN)

`outputs/codex_findings/v30_final_plan/FINAL_PLAN.md` is the
canonical commercialization plan — Claude pass-3 + Codex pass-4
GREEN, 2026-04-26. The wishlist is grounded in 50 primary user
sources from Reddit/HN/GitHub/forums (`SYNTHESIS.md` + Codex's
`findings.md` independently surfaced the same top-12).

Top-20 user wishes (from convergent Codex+Claude primary research):

1. Citations must be real (not fabricated, not collapsed,
   not pointing to wrong passage)
2. Pause/cancel/redirect a long-running deep-research run
3. Don't truncate output mid-run
4. Citation-preserving export (PDF/DOCX/Markdown with provenance)
5. Source organization: search, folders, tags, rename
6. Stop skipping parts of big corpora / pretending fewer sources
7. Quota/cost/credit transparency BEFORE the run starts
8. Durable long-running jobs — don't lose the report or state
9. Internal corpus connectors (Drive/Confluence/Jira/Notion/SharePoint)
10. OCR + image + multimodal ingestion
11. Source-tier control — less SEO sludge, fewer gamed citations
12. BYOK / OpenAI-compatible endpoint / no vendor lock-in
13. Watched folders + auto-sync ingestion
14. Shared workspaces + RBAC for teams
15. Notes / comments / annotations alongside sources
16. Structured table / CSV / XLSX export from research
17. Knowledge-base-specific prompts / templates
18. Cross-notebook / cross-workspace memory (user-visible, deletable)
19. Contradiction disclosure across documents
20. Slide deck / podcast / video / infographic

**Coverage status of Phase A/B/C builds against this list:**
- 1, 4, 11, 19: V30 strict-verify + Evidence Inspector views (M-2..M-7) — DONE
- 2, 3, 8: Job queue + pause/cancel + checkpoints (M-8/M-9) — DONE
- 7: Pre-flight estimate + cost surface — DONE in Phase A
- 5, 11, 14, 15: Workspace + auth + bounded upload (M-11, M-15a/b) — DONE
- 17: Curated template router (M-10, M-20) — DONE
- 16, 20: Tables + slide deck export (M-22) — DONE
- 13, 9: Narrow private-corpus sync (M-25) — DONE
- 6, 10, 12, 18: Partial / explicit gaps remaining

---

## C. Proposed end-to-end plan

The remaining work splits into 4 phases. Each milestone goes
through Claude+Codex cross-review per autoloop V2. Integration
milestones use diff-against-baseline + smoke-evidence Codex
review (not just `pytest`).

### Phase E — Integrate Phase D into production (3-4 weeks)

The honest correction to the recent locked-but-not-imported
problem. Each substrate gets wired into a specific production
call site, with Codex verifying the import + invocation.

**M-INT-1 — Parallel fetch into live_retriever** (3 eng days)
- Wrap existing Serper/SS/DDG clients in `ParallelFetcher`
- Replace serial loop in `live_retriever.py` with
  `parallel_fetch(...)`
- Per-backend rate limits: Serper=10, SS=1, DDG=4
- Codex review: rate-limit compliance preserved, regression
  test on existing 16/16 smoke set, observable speedup

**M-INT-2 — Cache + cache-warming around sweep entry** (3 eng
days)
- Pre-warm `RetrievalCacheStore` on canonical sources before
  sweep dispatch
- Concrete `CacheFetcher` wrapping HTTP
- Hook into `run_honest_sweep_r3.py`
- Codex review: workspace_id propagation, on_fetcher_error
  semantics, no double-fetch on hit

**M-INT-3 — Freshness detector + eviction** (4 eng days)
- Concrete `FreshnessDetector` using Crossref `update-policy`
- Wire `FreshnessAlertStore` into the cache-eviction trigger
- Periodic re-check loop (daemon stub; full daemon = Phase F)
- Codex review: 5-status taxonomy enforced, no false-positive
  evictions on transient unreachable

**M-INT-4 — Decision telemetry on every gate + induction call**
(2 eng days)
- Every `confidence_gated_match` call writes a `DecisionRecord`
- Every keyword/LLM induction call writes one
- Workspace_id always propagated; PII never in
  `proposed_payload`
- Codex review: write doesn't gate the decision (failure to
  write != failure to decide)

**M-INT-5 — OpenRouter-backed ScopeAffinityLLM** (3 eng days)
- Mirror M-D2 phase b's `OpenRouterTemplateAffinityClassifier`
- Plug into `LLMScopeEligibilityClassifier` in production
- Codex review: prompt-injection delimiters intact, cost
  ContextVar propagation, JSON schema enforcement, retry sane

**M-INT-6 — Pin capture + replay CLI** (2 eng days)
- `--capture-pin <path>` flag on sweep writes `ModelPin`
- `--replay-from-pin <path>` flag uses `replay_pin(...)`
- Codex review: env_snapshot doesn't leak secrets, prompt
  SHA-256 verification works end-to-end

**M-INT-7 — Domain router into live retrieval flow** (4 eng
days)
- Wire `route_to_domain` after `confidence_gated_match`
- Concrete `DomainAdapter` for clinical (Crossref + PubMed)
- Codex review: fallback when LLM classifier returns
  UNCERTAIN, adapter-id consistency with dict keys

**Acceptance for Phase E:**
- Every Phase D substrate is imported by at least one
  production module
- A single end-to-end audit run (`run_honest_sweep_r3.py
  --vector tirzepatide_t2dm`) shows non-zero invocation
  counts for each substrate in the run log
- M-D suite remains 614/614; full suite remains green; no
  silent skips

### Phase F — End-to-end live audit + BEAT-BOTH (2-3 weeks)

**M-LIVE-1 — V_N=V19 single-query end-to-end smoke** (3 eng
days)
- One real query against the integrated pipeline
- All telemetry/cache/freshness/pin/domain-routing fire
- Manifest + audit bundle + Inspector views render
- Codex review: artifact completeness vs. M-D9 phase 1
  manifest schema, every substrate's run-log evidence

**M-LIVE-2 — BEAT-BOTH head-to-head against ChatGPT/Gemini DR**
(5 eng days)
- Extract `state/compare_chatgpt_dr.txt` +
  `state/compare_gemini_dr.txt` into manifest shape
- Three `score_run(...)` calls + two `diff_dimension_scores(...)`
- Verdict per dimension: BEAT-BOTH / BEAT-ONE / BEHIND
- Codex review: extraction correctness, dimension scorer
  invocation, verdict math

**M-LIVE-3 — Operator dashboard (Inspector aggregates panel)**
(4 eng days)
- New Inspector view exposing `compute_aggregates`,
  `compute_freshness_aggregates`, `analyze_pin_trends` data
- Workspace-scoped, time-windowed
- Codex review: workspace isolation in UI, rate denominators
  match substrate semantics

**Acceptance for Phase F:**
- `python scripts/run_honest_sweep_r3.py --vector
  tirzepatide_t2dm` runs through the integrated pipeline in
  ≤150 min p90
- BEAT-BOTH verdict published; per-dimension gaps surfaced
- Operator can see telemetry/freshness/pin trends in live
  server UI

### Phase G — Close BEAT-BOTH gaps (4-8 weeks, indeterminate)

The autoloop V2 doesn't stop after Phase F. It changes shape:
each BEAT-BOTH dimension where V_N is BEHIND or BEAT-ONE
becomes a concrete fix milestone. Likely candidates based on
prior BEAT-BOTH attempts (V31, V32, V33):

- **dimension 1 (unique_citations)** — gap = breadth. Fix =
  M-D6 phase 2 concrete domain adapters + M-D7 cache hit-rate
  improvement + parallel fetch concurrency increase.
- **dimension 2 (regulatory_coverage)** — gap = jurisdiction
  count. Fix = V34 cross-jurisdiction synthesizer expansion
  (already started via M-14).
- **dimension 6 (contradiction_handling_grammar)** — historically
  the hardest BEAT-BOTH gap. Fix = synthesizer hedging upgrade
  (M-71/M-72 territory).
- **dimension 7 (narrative_length)** — gap = synthesis capacity.
  Fix = drop-on-verify regen logic + cluster-synthesize tuning.

Each gap → concrete milestone → Claude+Codex review → ship →
re-run BEAT-BOTH → next gap. Stop condition: BEAT-BOTH on all
7 dimensions OR asymptote-stop with documented threat model.

### Phase H — Production hardening + pilot launch (3-4 weeks)

**M-PROD-1 — SOC2 dry-run + remediation** (10 eng days)
- Engage external SOC2 advisor
- Close findings ahead of formal audit (M-D12 unblocks)

**M-PROD-2 — First paying pilot customer** (5 eng days)
- Onboarding flow polish
- Workspace provisioning automation
- Billing integration testing

**M-PROD-3 — Production observability** (5 eng days)
- Sentry / Honeycomb / structured logs
- Dashboards for the M-D3 / M-D10 / M-D11 trends substrates
- Alerting on rate-limit breaches, cost overruns,
  freshness-eviction storms

**M-PROD-4 — Public release notes + supported-scope page**
(2 eng days)

**Acceptance for Phase H:**
- One paying pilot live
- SOC2 readiness pack generated
- Production observability dashboards green for 14 days
- BEAT-BOTH verdict reproducibly GREEN on weekly cadence

---

## D. Honest timeline + risks

**Total ETA:** 12-19 calendar weeks for a small strong team.
Lower bound assumes Codex sandbox cooperates and no
architectural surprises. Upper bound includes BEAT-BOTH
dimension closure (Phase G) which is genuinely indeterminate.

**Key risks:**

1. **BEAT-BOTH dimension 6 (contradiction_handling_grammar)
   may not close cleanly.** This was the historical
   asymptote-stop risk in V31/V32/V33. Mitigation: the M-D9
   phase 2 substrate scores it; we'll see the gap as soon as
   M-LIVE-2 runs. If gap is fundamental, scope-decision pivot
   (BEAT-BOTH to BEAT-ONE positioning) is on the table per
   `autoloop_beat_tier1_mandate.md`.

2. **OpenRouter cost spikes** during M-INT-5 + M-LIVE-2 runs.
   Mitigation: M-NEW billing/quotas already shipped; set hard
   per-day cap; Codex review of M-INT-5 explicitly checks cost
   ContextVar propagation.

3. **Freshness false-positives evict good cache entries.**
   Mitigation: M-INT-3 Codex review checks all 5 statuses
   including UNREACHABLE doesn't evict; daemon stub only,
   real daemon = Phase F.

4. **The "fucking around" critique repeats.** Mitigation: each
   milestone in this plan has an explicit "production import
   check" — Codex grep-verifies the substrate is imported by
   the integration site, not just available. The
   `feedback_substrate_is_not_product.md` memory rule is now
   load-on-startup.

5. **Sandbox cutoffs in Codex review.** Mitigation: continue
   using the verdict-only fallback brief pattern, but per the
   round-3-of-M-D5-phase-2 lesson, verify the FULL stdout.log
   before assuming cutoff.

---

## E. Codex's job in this plan

Every milestone above goes through Claude+Codex cross-review.
Specifically Codex is asked to:

1. **Verify the production-import check.** Each integration
   milestone, Codex grep-verifies the new substrate is
   imported by the named production file.
2. **Run targeted pytest.** No skips, no caveat-locks. If
   sandbox prevents pytest, Codex says so explicitly and the
   lock is provisional.
3. **Diff-against-baseline.** For integration milestones,
   Codex is told what the old code did and verifies the new
   code preserves observable behavior except the deliberate
   change.
4. **Smoke-evidence required.** Integration reviews ask for
   real run output (`run_honest_sweep_r3.py --only <test>`)
   showing the substrate fired.
5. **Rollback flag check.** Each integration ships with a
   `PG_USE_*` env flag that disables the new path. Codex
   verifies the flag actually disables.
6. **Cross-review the BEAT-BOTH verdict.** When Phase F runs
   M-LIVE-2, Codex independently extracts the competitor
   manifests + scores them and compares verdicts with Claude.
   Disagreement → reconcile; agreement → ship.

---

## Codex output requested

This is your turn to review Section A (state audit), Section
B (wishlist coverage), and Section C (proposed plan). I want
your verdict on:

1. **Section A (state audit) — is this honest?** Have I
   miscounted what's REAL vs SUBSTRATE? Anything in my
   "INTEGRATED" list that's actually substrate-only? Anything
   in my "NOT INTEGRATED" list that's already wired in?

2. **Section B (wishlist) — coverage status correct?** Of
   the 20 user wishes, did I correctly mark which are
   DONE/PARTIAL/GAP given current code?

3. **Section C (proposed plan) — sequencing + risks?**
   - Is the Phase E integration order right (parallel_fetch
     first, then cache, then freshness, etc.)?
   - Any milestone missing? Any milestone I shouldn't ship?
   - The 12-19 week ETA — is this honest given a small team
     hitting Codex review on every milestone?
   - Are the 5 named risks the right risks?

4. **Cross-review yourself: would you sign this as the
   canonical roadmap?** If GREEN: explicit YES + final word.
   If PARTIAL: list concrete fixes Claude needs to apply
   before Codex would sign.

Output format:

```
## Verdict
GREEN | PARTIAL | BLOCKED

## State audit (Section A) review
- [Notes on any miscounts]

## Wishlist coverage (Section B) review
- [Notes on any miscoded DONE/PARTIAL/GAP]

## Proposed plan (Section C) review
- [Sequencing critique]
- [Missing or wrong milestones]
- [Timeline reality check]
- [Risk completeness]

## New findings (if any)
[SEVERITY] specific concrete finding

## Final word
[Sign or list fixes needed]
```

Tool hints:
- DO NOT run rg/find — I've already gathered the relevant
  state above.
- DO NOT run pytest — this is a planning review, not a code
  review.
- DO NOT run Python verification scripts that print Unicode.
- Read `outputs/codex_findings/v30_final_plan/FINAL_PLAN.md`
  if you want the prior canonical plan reference.
- Read `memory/autoloop_beat_tier1_mandate.md` for the
  user-mandated stop criterion.

Targeted at 1-2 round convergence. Substantive critique
welcome — this plan is the single most important one in the
project's history; getting the sequencing wrong would burn
weeks.
