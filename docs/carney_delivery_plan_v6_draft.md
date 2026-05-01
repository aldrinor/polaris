# POLARIS Carney Delivery Plan v6 — substrate-aware, frontier-comparable

**Status:** v6 DRAFT — anchored on actual codebase audit, not greenfield assumption.
**Date:** 2026-05-01.
**Supersedes:** all earlier plan versions including FINAL+5.
**Mission:** From today to a working sovereign Canadian deep research AI delivered to Mark Carney that **matches or beats ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR** on every user-facing function and feature.

---

## Anchor: codebase audit

Read `docs/substrate_audit_2026-05-01.md` first. Headline: 270 Python files, 47 audit_ir modules, 123 routes, 113 completed milestones. **~80% of frontier-product capabilities are already built; not exposed in modern UI.**

Genuinely-missing builds (not greenfield, but real new work):
1. Modern Next.js 15 + React 19 + shadcn/ui frontend that surfaces existing endpoints
2. Sovereign vLLM cluster running DeepSeek V4 (replace OpenRouter cognition path)
3. Ambiguity detector for BPEI-class queries
4. Anti-sycophancy CI suite (paired-prompt evaluation per ELEPHANT/SycEval methodology)
5. Evidence Contract Gate (canonical JSON schema for run artifact)
6. Live citation overlay (Perplexity-grade hover-tooltip with quote)
7. Inline visual rendering (Vega-Lite consuming `smart_art_generator.py` output)
8. Conversational follow-up on completed reports
9. Side-by-side compare two reports
10. 5 new templates (defense, climate, AI sovereignty, Canada-US, workforce) — content work

Plus operational hardening:
- Sovereignty enforcement (code-level data classification + provider routing)
- Hardware Path A/B/C selection + on-demand spin-up
- Mandatory paid sample evaluator for Phase 3
- Exhaustive Playwright e2e + visual testing per feature
- Per-task Codex Red-Team review

## North star, sharpened

POLARIS Canada must:

| Dimension | Bar | How POLARIS clears it |
|---|---|---|
| Audit-traceability | Better than incumbents (they handwave) | Per-sentence strict_verify + click-to-evidence + Evidence Contract |
| Refusal honesty | Better than incumbents (they don't refuse cleanly) | Explicit refusal-with-explanation; ambiguity disambiguation |
| Contradiction surfacing | Better (incumbents average them away) | PT08 disclosure + navigable contradiction badges |
| Sovereignty | Only POLARIS can claim this | Cognition on Canadian hardware; code-enforced data classification |
| Anti-sycophancy | Match or beat (incumbents are 48% sycophantic per ELEPHANT) | Paired-prompt CI suite; reframe-as-question pre-prompt mitigation |
| Document upload | Match | M-11 substrate + drag-drop UI + grounding flow |
| Inline charts/tables | Match | smart_art_generator.py + Vega-Lite renderer |
| Live citation tracing | Match Perplexity (gold standard) | Hover-tooltip with quote + tier + retrieval timestamp |
| Conversational follow-up | Match | Follow-up agent + parent-context preservation |
| Multi-jurisdiction comparison | Match | M-14 substrate + side-by-side UI |
| Knowledge snowballing | Match | evidence_deepener.py + visualize as graph |
| Memory across sessions | Match | M-21 substrate + memory UI surface |
| Reproducibility | Better (incumbents have none) | Pin replay UI |
| Speed | Match (5-10 min per query) | Existing pipeline + warm pool |
| UI polish | Match (frontier-grade) | Next.js 15 + React 19 + shadcn/ui + Tailwind v4 |

**No "half-ass" features. Every feature meets or beats incumbent.**

## 15 user-visible feature areas (each with match-or-beat acceptance)

Each feature below has: substrate status, what to build, best-practice reference, and Playwright+AI test matrix.

### F1 — Scope discovery + template browse

**Substrate**: `template_catalog.py`, `template_classifier.py`, scope examples per template.
**New build**: Next.js landing page with 8 template cards (3 active + 5 to-build) with scope summaries, in-scope examples, out-of-scope examples; live template-suggestion as user types.
**Best practice**: shadcn/ui Card + Command palette + `react-hotkeys-hook` for keyboard nav.
**Tests** (Playwright + AI agents):
- Visual: card grid renders at 1920px, 1024px, 768px, 375px (4 viewport screenshots)
- Functional: type "tirzepatide" → clinical drug audit suggested within 200ms
- Adversarial: type "BPEI" → no false-positive template match shown
- Accessibility: WCAG-AA compliance via axe-core
- Multi-tab: open in 3 tabs, type different queries, no state pollution
**Match-or-beat bar**: cleaner than ChatGPT (has no template browse), comparable to Gemini's Gem gallery.

### F2 — Query input with disambiguation modal

**Substrate (HONEST per Codex review)**: candidate acquisition (`live_retriever.py`) and embedding similarity (`pooled_embedder.py`, `prefetch_offtopic_filter.py`) exist; scope_classifier_llm.py exists. **Primary-entity clustering / HDBSCAN path / disambiguation API are NEW backend builds.** spaCy is NOT installed; if NER needed, must be added to requirements.
**New build**: ambiguity detector (cluster top-K retrieval candidates by primary entity; if >1 cluster above threshold → disambiguation modal). Modal shows candidate meanings with one-line description per candidate. User picks → query proceeds with disambiguation tag.
**Best practice**: Diversify-then-Verify pipeline (Agentic Verification, ICLR 2025); HDBSCAN clustering on candidate embeddings; LLM labels each cluster with its primary entity.
**Tests**:
- Visual: modal renders with 2 candidates, 3 candidates, 5 candidates
- Functional: "What is BPEI?" → disambiguation modal appears with at least syndrome / institute / chemical
- Adversarial: "tirzepatide" → no false disambiguation (single primary entity)
- Edge: query in French → handled or refused; PDF dropped → routed to upload
- Recording: 3 fresh-state evaluator walkthroughs through 22-input adversarial corpus
**Match-or-beat bar**: ChatGPT/Gemini both fail BPEI silently. POLARIS detects and asks.

### F3 — Document upload + grounding

**Substrate (HONEST per Codex review)**:
- DocumentIngester parses locally (real); LocalDocumentRAG chunks/embeds/queries (real)
- 10+ existing API endpoints
- **CRITICAL GAP**: production `graph_v4.py:149` accepts `document_ids` parameter but DOES NOT USE IT. v1 path wires docs into state; v4 (the live default) ignores them. Uploaded-doc evidence is NOT actually grounding anything in the production pipeline today.
- **CLIENT classification + router enforcement + external-provider redaction are NEW backend tasks**, not "just a CI test"

**New build**: (a) backend wiring of document_ids into graph_v4 evidence pool — this is the biggest hidden work in the plan; (b) drag-drop upload zone; (c) per-file parse status; (d) doc preview with chunk highlights; (e) "use these docs as evidence" toggle; (f) data classification taxonomy + sovereignty router (new code, not just config).
**Best practice**: shadcn/ui dropzone + react-dropzone + uploadthing for streaming; PDF.js for in-browser preview with span coordinates.
**Sovereignty enforcement**: uploaded docs tagged `CLIENT` classification → router blocks any external API processing of these docs. CI test proves blocking.
**Tests**:
- Visual: drag a 50MB PDF → progress bar visible, parsed chunks list appears
- Functional: upload PDF → query references its content → strict_verify cites span with page+coordinate
- Adversarial: 100MB file (over limit), 0-byte file, malformed PDF, password-protected PDF, image-only PDF (OCR), Word doc, plain text, EPUB
- Sovereignty test: attempt to send CLIENT-tagged doc to DeepSeek API → router blocks → CI fail if not blocked
- Recording: walkthrough of "upload my draft regulation, ask POLARIS to fact-check it"
**Match-or-beat bar**: matches ChatGPT/Gemini upload; beats them on sovereignty (their uploads leave Canadian jurisdiction).

### F4 — Live audit run with reasoning visibility

**Substrate**: M-13 progress_surfaces.py, job_queue.py, /jobs/{id}/stream SSE, checkpoint_manager.py.
**New build**: live progress UI consuming SSE. Must answer 5 specific user questions visibly:
1. What was searched? (query reformulations + retrieval candidates appearing)
2. What was rejected? (sources dropped + reasons inline)
3. What changed the answer? (synthesis decisions, regeneration triggers)
4. What contradiction exists? (contradiction-detection events as they fire)
5. What evidence supports each claim? (per-sentence verify decisions)
**Best practice**: SSE EventSource with reconnect/backoff; React Suspense for streaming; render each event-type as dedicated UI affordance, not raw log.
**Tests**:
- Visual: full-run recording 5-10min — every event appears within 1s of server emit
- Functional: SSE connection drops mid-run → reconnects automatically; state preserved
- Multi-tab: open same run in 2 tabs → both update independently; cancel in one cancels for both
- Adversarial: 80% source fetch failure → UI shows partial-evidence warning; strict_verify drops every sentence → UI shows zero-verified abort with cause
- Recording: walkthrough on 200-sentence run; latency stays <1s on hover/click
**Match-or-beat bar**: BEATS incumbents (they show only spinner). POLARIS shows reasoning live.

### F5 — Report inspection with click-through audit

**Substrate**: provenance.py + verifier_v2.py + Inspector view 1 (M-3); /api/inspector/runs/{slug}/report.md.
**New build**: every claim sentence in report is hover-highlight-able + clickable. Click → Inspector pane (right side, 40% width) with:
- Source span highlighted in source context
- Source URL, tier (T1-T7) with rationale, retrieval trace
- Two-family evaluator agreement signal
- Multi-span support (claims with N spans show all N)
- Synthesis-claim badge (no direct span) when applicable
- Retracted-source badge, stale (>2y) badge
**Best practice**: shadcn/ui Sheet for Inspector pane; intersection observer for hover-highlight; debounced for performance on long reports.
**Tests**:
- Visual: 50, 100, 200, 500-sentence report — all sentences clickable; latency <1s
- Functional: every user-visible factual assertion (regardless of container — prose, table cell, summary bullet, limitation, caption, heading) is gated-and-clickable OR visibly marked `ungated — no accepted evidence span`
- Adversarial: paywalled span (text in bundle, URL marked unavailable); multi-span claim shows all N; T1-vs-T1 conflict shows both with sample sizes
- Empty state: report with zero contradictions → empty-state copy "no contradictions detected"
- AI agent test: independent agent navigates 10 random sentences → confirms each opens evidence within 1s
**Match-or-beat bar**: BEATS Perplexity (POLARIS adds tier + multi-span + evaluator-disagreement signal Perplexity doesn't have).

### F6 — Live citation overlay (MVP, not Perplexity-grade)

**Substrate (HONEST per Codex)**: same as F5 IS NOT enough. Hover-overlay needs **token/span indexing, typed numeric cross-reference, caching, mobile affordances, edge-position behavior** — all new.
**Scope adjusted**: F6 in Phase 2 is **basic hover-card MVP** (hover sentence → tooltip with source title + tier + click-for-detail), NOT full Perplexity polish. Perplexity-grade typed-number-cross-ref + entity hover lifted to **post-handover v2.5**.
**New build (v6)**: basic hover-card with debounced rendering + edge-aware positioning + mobile tap-to-show fallback.
**Best practice**: shadcn.io InlineCitation component (`https://www.shadcn.io/ai/inline-citation`); typed number cross-ref (year vs p-value vs sample-size vs percentage handled differently).
**Tests**:
- Visual: hover a percentage → tooltip with quote + tier + timestamp
- Functional: hover same percentage 100 times → tooltip renders consistently <100ms
- Edge: tooltip near viewport edge → repositions; long quote → truncates with "more"; mobile (no hover) → tap-to-show
- Multi-source claim: tooltip shows count "5 sources" → click opens cross-ref panel with all 5
**Match-or-beat bar**: matches Perplexity; beats ChatGPT/Gemini (they don't have hover-quote).

### F7 — Frame coverage as lead

**Substrate**: M-12 corpus_brief.py + frame_manifest.py + corpus_retriever.py. `/api/inspector/runs/{slug}/...` endpoints.
**New build**: top-of-report panel rendered ABOVE-the-fold. "Got 14 of 15 contract-required entities. 1 gap: [name], reason: [paywalled / no OA / source-tier ineligible / etc.]." Each gap is clickable → opens detail panel with "what would unblock this" action.
**Best practice**: shadcn/ui Alert + Progress; gap-reason taxonomy frozen as enum.
**Tests**:
- Visual: 15-entity contract with 14 populated, 1 gap → panel shows correct count + gap detail
- Functional: every gap reason has a documented unblock action; user can copy gap details to clipboard
- Adversarial: 0/15 (all gaps), 15/15 (no gaps), 1/15 (almost all gaps) — panel renders correctly each
**Match-or-beat bar**: BEATS incumbents (they show "complete answer" without disclosing gaps). Frame coverage is unique to POLARIS.

### F8 — Contradiction navigation

**Substrate**: contradiction_detector.py + contradiction_hedging.py + Inspector view 2 (M-4). `contradictions.json` artifact.
**New build**: every flagged contradiction has inline badge `⚠ N sources disagree` in body. Click → side pane with all sides + tiers + sample sizes + hedge language POLARIS used + per-flag PT08 enumeration.
**Best practice**: shadcn/ui Badge + Sheet; non-numeric contradiction support (e.g., "is approved" vs "is not approved"); guideline-vs-trial conflicts; jurisdictional disagreements.
**Tests**:
- Visual: 0 contradictions, 5 contradictions, 50 contradictions — UI handles each
- Functional: T1-vs-T1 conflict (no false hierarchy); multi-claim contradiction (one flag spans 5 sentences)
- Adversarial: contradicting paragraphs (e.g., "X is safe" + "X is dangerous" same source) → flagged
**Match-or-beat bar**: BEATS incumbents (they suppress contradictions; POLARIS surfaces).

### F9 — Two-family disagreement signal

**Substrate**: openrouter_client.check_family_segregation + verifier_v2 + qwen_judge_output.json.
**New build**: when generator and evaluator disagree on a claim, claim shows `⚠ Internal evaluator flagged this` badge. Click → side pane shows the disagreement detail (generator's reading vs evaluator's reading + which evidence each cited).
**Best practice**: dual-evaluator consensus pattern (MiroThinker Local Verifier inspiration).
**Tests**: visual, functional, edge (no disagreements, all disagreements), recording.
**Match-or-beat bar**: UNIQUE to POLARIS — incumbents don't run two-family.

### F10 — Inline visual generation (charts, tables, infographics)

**Substrate (HONEST per Codex)**:
- `smart_art_generator.py:243` generates **Mermaid diagrams**, NOT Vega-Lite chart specs
- `data_analyzer.py` has Matplotlib/base64 PNG (LLM-scripted, often gated off)
- code_executor.py + analysis_notebook.py + pdf_table_extractor.py exist
- **Vega-Lite spec generation, chart provenance, click-through-to-source-data, infographic generation are ALL new builds.**
**Scope adjusted**: claim is "audit-traceable charts/tables FIRST" not "full visual parity with Gemini." Gemini Ultra has interactive simulators; POLARIS won't match that in v1.
**New build**: Vega-Lite renderer for forest plot + comparison table + timeline (3 chart types, not 6); auto-generated table when comparing N entities; chart provenance schema; click-through-to-source-data. Mermaid for diagrams (substrate exists). Matplotlib PNG fallback for complex visuals (substrate exists, gate it on).
**Best practice**: react-vega + Vega-Lite v5; chart provenance schema (every chart cites source data via Evidence Contract spans); chart code + data snapshot stored in audit bundle.
**Tests**:
- Visual: 6 chart types render correctly at 4 viewports
- Functional: chart click → opens source data; chart code visible (transparency)
- Sovereignty: charts execute in sandboxed Python (no-egress, resource-capped)
- Recording: walkthrough of "compare tirzepatide vs semaglutide" → table auto-generated with citations
**Match-or-beat bar**: matches Gemini DR; beats ChatGPT (which sometimes only shows charts in download). POLARIS charts are audit-traceable to source data.

### F11 — Report-scoped auditable follow-up

**Substrate (HONEST per Codex)**: `campaign_store` is persistence only; `session_feedback` is search-strategy feedback only; `workspace_memory` is keyword retrieval only. **These are storage and memory primitives, NOT a follow-up agent.** The follow-up agent itself is a new build.
**Scope adjusted**: claim is "report-scoped auditable follow-up" not "matches ChatGPT conversational fluidity." ChatGPT memory + chat-history reference is best-in-class; POLARIS beats on traceability per follow-up, not on fluid multi-turn conversation.
**New build**: follow-up agent with parent-run-context preservation, append-to-existing-report rendering, Evidence Contract inheritance, refusal handling for out-of-scope follow-ups.
**Best practice**: agent context-window management (CLAUDE.md memory says 1M context = use it); follow-up Evidence Contract inherits parent's accepted-source pool.
**Tests**:
- Visual: follow-up appended below original report with clear separator
- Functional: follow-up references claims from parent; no re-running of parent retrieval
- Adversarial: follow-up question that's actually out-of-scope → refusal-with-explanation
- Multi-turn: 5 sequential follow-ups → each grounded correctly
**Match-or-beat bar**: BEATS incumbents on auditable follow-up (every follow-up is its own auditable run with Evidence Contract). Does NOT claim to match ChatGPT's general conversational fluidity in v1; that's a v2.5 stretch. POLARIS's differentiator is per-follow-up traceability, not multi-turn polish.

### F12 — Side-by-side compare two reports

**Substrate**: run_diff.py + Inspector compare endpoint.
**New build**: pick any two completed runs → split-screen view; differences highlighted (claims agree, disagree, evidence-pool overlap/diverge).
**Best practice**: shadcn/ui ResizablePanels; claim-level diff algorithm (more nuanced than pin-replay's metadata diff).
**Tests**: visual at all viewports; functional (different jurisdictions, same query — show jurisdictional differences); recording.
**Match-or-beat bar**: UNIQUE to POLARIS — incumbents don't have this.

### F13 — Pin replay / "what changed since last run"

**Substrate**: pin_replay.py + pin_trends.py + model_pin.py + regression_alerts.py + regression_lab.py.
**New build**: pin replay UI showing same query re-run on different dates; diff visualization highlighting new/retracted/changed sources; regression alerts inline.
**Best practice**: time-series visualization (Vega-Lite); diff as side-panel.
**Tests**: visual, functional (re-run after 1 day / 1 week / 1 month), adversarial (source retraction during replay).
**Match-or-beat bar**: UNIQUE to POLARIS.

### F14 — Auditable research memory (NOT general ChatGPT memory)

**Substrate (HONEST per Codex)**:
- `local_document_rag.py` is real RAG with chunk/embed/query
- `chroma_client.py` exists, ChromaDB initialized at server start
- BUT `workspace_memory.py` is deterministic keyword/Jaccard v1, **NOT Chroma-backed semantic memory**
- Migration of workspace_memory to Chroma + memory controls UI + automatic save policy + searchable past runs + deletion + cited recall = ALL new build

**Scope adjusted**: match-or-beat bar is **"beats incumbents on auditable research memory"**, NOT "matches ChatGPT memory." ChatGPT memory's cross-conversation behavior without manual artifact management is not the v1 target. POLARIS adds research-specific cited recall + deletion + searchable past runs — these are differentiators.
**New build**: memory page with explicit controls (save / pin / forget); migrate workspace_memory to Chroma semantic; cross-session surfacing ("you researched X last week"); memory-as-corpus for new queries; cited recall (when memory contributes to current run, surface which past run + which claim).

### F15 — Audit bundle export with embedded source spans

**Substrate**: serializer.py + slide_deck.py + audit-bundle.zip endpoint.
**New build**: button in report header; preview pane lists contents; generates standalone-verifiable zip including: report.md + bibliography.json + evidence_pool.json (with extracted span text ≤500 chars per Codex redline) + manifest.json + frame_coverage.json + verification_details.json + contradictions.json + decision_telemetry.json + methodology.md + reviewer README.
**Best practice**: standalone reproducibility (third-party with no POLARIS access can verify any claim); license-cleared embedding; bundle progress + size warning if >100MB.
**Tests**:
- Functional: third-party tester (no POLARIS access) traces randomly-selected claim back to source span text in <5min, no instruction beyond README
- Adversarial: paywalled source (span text in bundle, URL marked unavailable); 500MB bundle (resumable download); partial/aborted run (bundle marked PARTIAL)
- Sovereignty: legal-cleared spans only; CI test proves no copyrighted spans included without license check
**Match-or-beat bar**: UNIQUE to POLARIS — incumbents don't ship audit bundles.

## Phase plan — 16 weeks, May 1 → Aug 22

Realistic given 15 features each requiring exhaustive testing.

### Phase 0 — Foundation (8 business days, May 1-12)
Same 10 tasks as v5, plus:
- 0.11: Substrate audit verification (this doc) reviewed by Codex
- 0.12: Anti-sycophancy CI suite scaffold (paired prompts neutral/leading/opposite-frame)

### Phase 1 — BPEI spine + Evidence Contract Gate (3 weeks, May 13-31)
F1, F2, F3 (upload), F15 (audit bundle), Evidence Contract Gate (Task 1.4 from v5.1).

### Phase 2A — Core inspection (3 weeks, June 1 - June 21)
F4 (live audit), F5 (report inspection), F7 (frame coverage), F8 (contradictions), F9 (two-family) — features that primarily surface existing substrate.
Templates 4-5 added in parallel content workstream (defense, climate).

### Phase 2B — Visualization + memory + replay (3 weeks, June 22 - July 12)
F6 (citation overlay MVP), F10 (charts/tables — 3 chart types), F13 (pin replay), F14 (auditable memory) — features with substantial new build.

### Phase 2C — UI polish + integration (1 week, July 13 - July 19)
Cross-feature integration testing; visual regression; mobile/Safari/cross-browser; performance optimization.

### Phase 3 — Follow-up + benchmark (3 weeks, July 20 - Aug 9)
F11 (auditable follow-up), F12 (side-by-side compare), Templates 6-8 added (AI sovereignty, Canada-US, workforce).
Benchmark proof package: 50 questions × 4 systems × 6 dimensions, paid sample evaluator scoring (mandatory).

### Phase 4 — Sovereign migration (2 weeks, Aug 10 - Aug 23)
Replace OpenRouter cognition path with Canadian sovereign vLLM cluster. Validate quality unchanged.

### Phase 4.5 — Buffer (1 week, Aug 24-30)
Migration findings, regression fixes, restored buffer per Codex.

### Phase 5 — Carney handover (1 week, Aug 31 - Sep 6)
Final walkthrough + Codex sweep + handover package + execute.

**Total: 18 weeks (May 1 → Sep 6).** Was 16 in v6 draft; Codex flagged Phase 2 as "fantasy"; split into 2A/2B/2C added 2 weeks of honest scope.

## Testing matrix — exhaustive per feature (expanded per Codex review)

Every feature passes ALL of these gates:

| Test type | Tool | Pass criteria |
|---|---|---|
| Unit tests | pytest | 100% of new code covered |
| Integration tests | pytest + httpx | Every endpoint tested with mocked + real LLM |
| Artifact contract / schema versioning | jsonschema validator | Evidence Contract artifacts validate; version migration tested |
| Visual regression | Playwright + percy.io | 4 viewports (1920/1024/768/375), 0 unintended pixel diffs |
| E2E happy path | Playwright | Fresh-account walkthrough recorded |
| E2E adversarial | Playwright + Test Agent (mandatory supplemental, NOT primary gate) | 22-input + 17-content adversarial corpus |
| Cross-browser | Playwright (Chromium, Firefox, WebKit/Safari) | All pass |
| Accessibility | axe-core | WCAG-AA pass |
| Multi-tab safety | Playwright (parallel contexts) | No state pollution; cancel in one cancels for both |
| Network resilience | Playwright (offline mode + slow-3G) | Graceful degradation; reconnect; no white screen |
| Streaming SSE ordering / backpressure | Playwright EventSource consumer | Events arrive in order; backpressure handled |
| Cancellation / resume | Playwright | Cancel in <5s; resume on refresh from checkpoint |
| Performance | Playwright + Lighthouse | Core Web Vitals green; LCP <2.5s; INP <200ms; long-report (200+ sentences) hover-latency <100ms |
| Security | Playwright Security Agent + standard tools | XSS, CSRF, injection, prompt-injection in user docs |
| Tenant isolation + data deletion | pytest + Playwright | Org A cannot see Org B; deletion is real (no log residue) |
| Privacy / log redaction | grep-based audit on log fixtures | No PII / no source-content-leakage in logs |
| Sovereignty (data classification routing) | CI test on `sovereign_router.py` | All non-PUBLIC_SYNTHETIC classifications blocked from external API |
| Migration tests | DB migration on copy of prod data | Rollback works; no data loss |
| LLM quality gates | Eval set per template (15 questions) | Citation precision/recall ≥ baseline |
| Semantic chart correctness | Pytest + Vega-Lite spec validation | Chart data matches Evidence Contract spans |
| Anti-sycophancy | Paired-prompt CI per ELEPHANT methodology | Stance delta <5% on 20 paired prompts; nightly full eval |
| Codex code review | Codex Red-Team Checklist | GREEN per task |
| Layer 3 walkthrough | Product-owner (user) + paid sample evaluator (Phase 3) | Recorded fresh-state, async-reviewed |
| Fixture governance + flake budget | Test infra discipline | Flake rate <2%; fixtures versioned and refreshed quarterly |

## Codex loop discipline (unchanged from FINAL+5)

Same per-task workflow + escalation rules + structured manifest + Codex Red-Team Checklist. See `.codex/codex_red_team_checklist.md`.

## Realistic budget — external cash ceiling

Per-feature exhaustive testing adds compute and evaluator hours. Honest revision:

| Category | Estimate |
|---|---|
| **Build phase compute + API** (Phases 0-2, ~7 weeks) | $1-2k |
| **Benchmark phase** (Phase 3): API + competitor subscriptions + self-hosted validation | $7-12k |
| **Sovereign migration + Carney demo** (Phases 4-5): on-demand Canadian cluster | $8-18k |
| **Mandatory paid sample evaluator** (Phase 3 + walkthroughs in Phases 1-2) | $5-12k |
| **Visual regression + Playwright cloud (BrowserStack/Percy)** | $1-2k |
| **Non-compute** (legal review for bundle, handover prep, sourcing/admin) | $5-12k |
| **20% contingency** | $5-12k |
| **TOTAL external cash ceiling** | **~$32-70k** |

**Expected delivery band: $40-60k.** EXCLUDES user/Codex/internal labor.

## Blockers — same 10 from v5 + 1 new

1-10: same as v5 (all answered)
11: **NEW — paid sample evaluator sourcing initiated by end of Phase 0** (was already mandatory in FINAL+5)

## What changed from FINAL+5

- **Anchored on real audit, not greenfield** — most engineering reframed as "expose substrate" not "build from scratch"
- **15 features documented with substrate status + best-practice references + exhaustive test matrices** (not 5 flows + 10 jewels)
- **Match-or-beat bar specified per feature** (not generic "frontier-comparable")
- **Document upload + grounding** elevated to F3 (not deferred)
- **Inline visuals** elevated to F10 with Vega-Lite + chart provenance (not buried in audit bundle)
- **Live citation overlay** elevated to F6 with Perplexity-grade hover-tooltip
- **Conversational follow-up** elevated to F11 (was deferred)
- **Side-by-side compare** elevated to F12
- **Memory across sessions** elevated to F14
- **Pin replay** elevated to F13 (was deferred)
- **Timeline 14 → 16 weeks** (more realistic for 15 features each with exhaustive testing)
- **Budget $26-58k → $32-70k** (Playwright infrastructure + walkthrough hours per feature)

## Honest framing

POLARIS substrate is ~80% of frontier-product capability already. The build is 15 weeks of exposing existing capability + 1 week of buffer + handover. Each feature must match-or-beat ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR. No half-ass. Each feature has Playwright + Test Agent + accessibility + sovereignty + anti-sycophancy testing, recorded.

---

**Next step**: send v6 to Codex for review.
