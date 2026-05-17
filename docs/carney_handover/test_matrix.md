# POLARIS test matrix — 24 test types × the real product journey

**Issue:** I-rdy-019 / GH #515 (Carney readiness Phase 5a).
**Purpose:** instantiate the carney-plan testing matrix
(`docs/carney_delivery_plan_v6_2.md` lines 314-339, "Testing matrix —
exhaustive per feature") against the **real deployed product journey** — the
non-harness `web/app/` routes — so I-rdy-020 / GH #516 ("run the test
matrix") has a concrete, journey-grounded checklist to execute.

**Scope of THIS issue:** the matrix is *authored*, not *run*. #515 produces
this document; #516 executes it. No test in this matrix has been executed by
#515 — every "pass criteria" below is a target, not a recorded result.

**Test-type count:** the issue title says "22 test types"; the plan table
(v6_2:314-339) currently has 24 rows. This matrix carries all 24 verbatim.
The issue's "22" predates two rows; if a strict 22 is needed, rows 22 (Codex
code review) and 24 (Fixture governance) are process/infra gates rather than
product test types and are the excludable pair.

**Dependency:** #515 declares "Depends on: I-rdy-007" (#503, "define the
live-run artifact contract" — currently OPEN). Test type 3 (Artifact
contract / schema versioning) carries a `forward-ref: I-rdy-007 (#503)`
marker; #516 cannot concretely execute that row's schema-level checks until
#503 lands. All other rows are fully authorable and runnable now.

---

## 1. The real product journey (J1–J11)

Grounded in the actual deployed `web/app/**/page.tsx` route inventory: 33
page routes — **14 real product routes**, **19 harness/diagnostic** (§2).

| Stage | Route | What the user does |
|---|---|---|
| **J1** Sign-in | `/sign-in` | Authenticate (static_accounts demo auth). |
| **J2** Home / template discovery | `/` | Land on the template-selection shell; pick a template; it links into `/intake`. |
| **J3** Scope intake + disambiguation | `/intake` | Enter the research question; ambiguity detector may raise a disambiguation modal. |
| **J4** Retrieval | `/retrieval` | Live evidence retrieval; corpus assembly + adequacy gate. |
| **J5** Generation | `/generation` | V4 Pro generation of the verified report. |
| **J6** Live audit run (SSE) | `/runs/<runId>` (in progress) | While a run executes, `/runs/<runId>` streams events via `subscribeToRun` (searched / rejected / contradiction / per-claim verify) and shows a Cancel button. |
| **J7** Run view + graph | `/runs/<runId>` (complete), `/runs/<runId>/graph` | The completed-run view — final report, bundle export, and graph. |
| **J8** Report inspection (click-through) | `/inspector/<runId>` | Hover/click each claim → Inspector pane (source span, tier, evaluator agreement). |
| **J9** Document upload + grounding | `/upload` | Drag-drop a document; it is parsed, classified, and used as evidence. |
| **J10** Start a research run | `/dashboard` | Pick a template, enter a question, attach uploads → `createRun` → redirect to `/runs/<runId>`. |
| **J11** Supporting surfaces | `/contracts`, `/memory`, `/pin_replay`, `/benchmark` | Evidence Contract editor, workspace memory, pin replay, BEAT-BOTH benchmark. |

**Note — multiple run-entry surfaces.** The current product exposes more
than one input form that starts work: `/dashboard` (template + question +
upload → `createRun`), and the standalone `/retrieval` and `/generation`
forms (`data-testid="retrieval-form"` / `"generation-form"`). The matrix
below describes each route by its **actual deployed content**, verified
against `web/app/`; consolidating these entry points into one coherent
journey is product work tracked separately (I-rdy-014 / #510), not #515.
`/runs/<runId>` likewise appears as two journey stages — J6 (the in-progress
live-streaming phase) and J7 (the completed-run view) — the same route at
different run-lifecycle phases, split because the test concerns differ.
`/audit_live` is NOT a product route (§2).

## 2. Excluded harness / diagnostic routes (NOT product — do not test as journey)

Per the issue ("not harness pages") and `feedback_plan_from_running_system`.
19 routes — #516 must not spend matrix coverage on these:

- `/sse` — implemented as a harness: `web/app/sse/page.tsx` exports
  `SSETestHarnessPage`; `web/app/sse/_harness.tsx` renders
  `data-testid="sse-harness"`.
- `/audit_live` — SSE-consumer test surface, NOT production-wired:
  `web/app/audit_live/_panels.tsx` defaults its stream URL to
  `/api/audit/stream`, which `web/next.config.ts` does not rewrite to the
  backend. The production live-run UI is `/runs/<runId>` (J6/J7 —
  `subscribeToRun` → `/stream/<runId>`). Prior accepted F4 framing
  (`.codex/I-f4-005/brief.md`): "`/audit_live` is a test-route surface, not
  a production live-run UI."
- `/disambiguation_modal_preview` — component preview (filesystem path
  `web/app/(test_harness)/disambiguation_modal_preview/`; `(test_harness)`
  is a Next.js route group, not a URL segment).
- `/charts_test` + 4 subroutes — `/charts_test`,
  `/charts_test/click_through`, `/charts_test/comparison_table`,
  `/charts_test/forest_plot`, `/charts_test/timeline` (5).
- `/sentence_hover_test` + 10 subroutes — `/sentence_hover_test`,
  `/coverage`, `/evaluator_edge`, `/evidence_tooltip`,
  `/evidence_tooltip_edges`, `/follow_up_append`, `/memory_cite`, `/perf`,
  `/split_screen`, `/stress`, `/two_run_picker` (11).

## 3. The 24 test types × journey

Each block: the plan's **Tool** + **Pass criteria** carried verbatim, then
the concrete check at each applicable journey stage, then a reasoned **N/A**
for stages the type does not apply to.

### 1 — Unit tests
**Tool:** pytest. **Pass criteria:** 100% of new code covered.
**Applies to (the code backing each stage):**
- J1 — auth/static_accounts unit tests.
- J2 — `/` template-catalog + template-selection component logic.
- J3 — `ambiguity_detector` + scope-gate classifiers.
- J4 — `live_retriever`, corpus-adequacy gate, tier classifier.
- J5 — generator (`multi_section`, `live_deepseek`), `strict_verify`, provenance.
- J6 — job runner, SSE event emitters, checkpoint manager.
- J7/J8 — AuditIR loader, inspector API, verifier-span resolution.
- J9 — DocumentIngester, classification taxonomy, sovereignty router.
- J10 — `/dashboard` run-creation form + `createRun` client.
- J11 — Evidence Contract schema, workspace memory, pin store, benchmark scorer.
**N/A:** none — every stage has backing code requiring unit coverage.

### 2 — Integration tests
**Tool:** pytest + httpx. **Pass criteria:** every endpoint tested with mocked + real LLM.
**Applies to:** every stage that calls a backend endpoint — J1 (auth), J3
(intake/scope), J4 (`/api/retrieval`), J5 (generation), J6 (`/stream/<runId>`
SSE), J7/J8 (inspector run/report APIs), J9 (upload), J10 (`createRun`),
J11 (contracts, memory, pins, benchmark APIs). Each: mocked
LLM for determinism + a real-LLM smoke per the OpenRouter rehearsal path.
**N/A:** J2 — `/` is a static template-selection shell with no own endpoint.

### 3 — Artifact contract / schema versioning  ·  `forward-ref: I-rdy-007 (#503)`
**Tool:** jsonschema validator. **Pass criteria:** Evidence Contract artifacts validate; version migration tested.
**Applies to:**
- J5 — `/generation` builds + downloads an audit bundle (`BundlePreview`,
  `downloadAuditBundle`); the bundle validates against the contract.
- J6 — the live run emits artifacts; they validate against the live-run
  artifact contract (defined by #503 — schema-level checks deferred to #503).
- J7 — `/runs/<runId>` exports the run bundle (`getBundle`,
  `downloadBundleAsJson`); the exported bundle validates against the contract.
- J8 — the audit bundle / Evidence Contract consumed by the Inspector validates.
- J11 — `/contracts` editor output validates; `/pin_replay` + `/benchmark`
  consume contract-shaped artifacts.
**N/A:** J1, J2, J3, J4, J9, J10 — no contract-versioned artifact is
produced or consumed at these stages.
**Forward-ref:** until #503 lands, this row's checks are stated at the
contract level ("artifact validates against the I-rdy-007 contract;
migration tested"); #516 binds the concrete field-level schema once #503
merges.

### 4 — Visual regression
**Tool:** Playwright + percy.io. **Pass criteria:** 4 viewports (1920/1024/768/375), 0 unintended pixel diffs.
**Applies to:** all UI stages J1–J11 — every route screenshotted at the 4
viewports. Dynamic routes (`/runs/<runId>`, `/inspector/<runId>`) use a
pinned fixture run for stable snapshots.
**N/A:** none.

### 5 — E2E happy path
**Tool:** Playwright. **Pass criteria:** fresh-account walkthrough recorded.
**Applies to:** the whole journey as one flow — J1 sign-in → J2 pick
template → J3 enter question → J4 retrieval → J5 generation → J6 watch live
run → J7 run view → J8 inspect report; J9 upload and J10 dashboard as
recorded sub-flows; J11 surfaces visited.
**N/A:** none — this type IS the end-to-end journey.

### 6 — E2E adversarial
**Tool:** Playwright + Test Agent (mandatory supplemental, NOT primary gate). **Pass criteria:** 22-input + 17-content adversarial corpus.
**Applies to:**
- J3 — ambiguous query ("What is BPEI?") → disambiguation modal; non-ambiguous ("tirzepatide") → no false modal.
- J4 — thin-corpus query → `abort_corpus_inadequate`, not a fabricated report.
- J5/J6 — 80% source-fetch failure → partial-evidence warning; all sentences fail `strict_verify` → zero-verified abort shown with cause.
- J9 — 100MB / 0-byte / malformed / password-protected / image-only / Word / plain-text / EPUB inputs handled or refused (never silent).
- J10 — `/dashboard` adversarial question + malformed/oversize upload at
  run creation → handled or refused, never a silent bad run.
**N/A:** J1, J2, J7, J8, J11 — no adversarial *input surface* (J7/J8 render
already-produced runs; covered under Security row 14 for injection).

### 7 — Cross-browser
**Tool:** Playwright (Chromium, Firefox, WebKit/Safari). **Pass criteria:** all pass.
**Applies to:** all UI stages J1–J11.
**N/A:** none.

### 8 — Accessibility
**Tool:** axe-core. **Pass criteria:** WCAG-AA pass.
**Applies to:** all UI stages J1–J11 — keyboard nav, focus order, contrast,
ARIA on the disambiguation modal (J3), the Inspector Sheet (J8), the upload
dropzone (J9).
**N/A:** none.

### 9 — Multi-tab safety
**Tool:** Playwright (parallel contexts). **Pass criteria:** no state pollution; cancel in one cancels for both.
**Applies to:**
- J6 — same run open in 2 tabs → both update independently; cancel in one cancels for both.
- J3 — different queries in 3 tabs → no cross-tab state pollution.
- J7/J8 — same run inspected in parallel tabs → no shared mutable state.
**N/A:** J1, J2, J4, J5, J9, J10, J11 — no long-lived per-tab mutable run
state (J4/J5 are transient steps inside the J6-streamed run).

### 10 — Network resilience
**Tool:** Playwright (offline mode + slow-3G). **Pass criteria:** graceful degradation; reconnect; no white screen.
**Applies to:**
- J6 — SSE connection drop mid-run → auto-reconnect, state preserved.
- J4 — slow-3G during retrieval → progress UI, no white screen.
- J2, J3, J5, J7, J8, J9, J10, J11 — offline/slow load → skeleton or error state, never a white screen.
**N/A:** J1 — sign-in offline simply cannot authenticate; the only
requirement (a clear error, no white screen) is covered generically.

### 11 — Streaming SSE ordering / backpressure
**Tool:** Playwright EventSource consumer. **Pass criteria:** events arrive in order; backpressure handled.
**Applies to:** **J6** — while a run executes, `/runs/<runId>` consumes the
run SSE stream (`subscribeToRun` → `/stream/<runId>`,
`web/app/runs/[runId]/page.tsx`); events (searched / rejected /
contradiction / verify) arrive in emit order; a slow consumer does not drop
events.
**N/A:** J1–J5, J7–J11 — no live SSE stream. J7 is the completed-run-view
phase of the same `/runs/<runId>` route; SSE ordering/backpressure is
exercised in the in-progress phase (J6), not re-tested. (`/sse` and
`/audit_live` exercise SSE but are excluded harness surfaces, §2.)

### 12 — Cancellation / resume
**Tool:** Playwright. **Pass criteria:** cancel in <5s; resume on refresh from checkpoint.
**Applies to:** **J6** — `/runs/<runId>` exposes a Cancel button
(`web/app/runs/[runId]/page.tsx`, "cancel a queued or in-progress run");
cancel should complete in <5s. **Honest gap:** resume-from-checkpoint is
NOT yet wired on `/runs/<runId>` — the hard-kill + resume implementation is
forward-ref I-rdy-011 (#507) / #539. #516 records resume as a known gap,
not a passing check, until those land.
**N/A:** J1–J5, J7–J11 — no cancellable long-running operation at these
stages (retrieval/generation are sub-steps of the J6 run; J7 is the
completed-run view).

### 13 — Performance
**Tool:** Playwright + Lighthouse. **Pass criteria:** Core Web Vitals green; LCP <2.5s; INP <200ms; long-report (200+ sentences) hover-latency <100ms.
**Applies to:** all UI stages J1–J11 — every rendered route is held to Core
Web Vitals (LCP <2.5s, INP <200ms). Stage-specific budgets: J8 — the
200/500-sentence report keeps hover/click Inspector latency <100ms; J2 —
`/` LCP <2.5s (the first paint a Carney-office visitor sees).
**N/A:** none — Core Web Vitals apply to every rendered page.

### 14 — Security
**Tool:** Playwright Security Agent + standard tools. **Pass criteria:** XSS, CSRF, injection, prompt-injection in user docs.
**Applies to:**
- J1 — CSRF on the auth POST; session-cookie flags.
- J3 — XSS / query-injection via the research-question field.
- J4 — `/retrieval` exposes its own research-question form
  (`data-testid="retrieval-form"`); XSS / query-injection.
- J5 — `/generation` exposes its own question form
  (`data-testid="generation-form"`); XSS / query-injection.
- J7, J8 — stored-XSS via rendered report/source content.
- J9 — prompt-injection embedded in an uploaded document is neutralized (per CLAUDE.md §9.1.7 delimiter sanitization).
- J10 — `/dashboard` exposes a question form + document upload + the
  `createRun` POST; query-injection, prompt-injection in attached docs, CSRF.
- J11 — injection via the Evidence Contract editor input.
**N/A:** J2, J6 — no direct untrusted-input surface (J2 is a static
template-selection shell; J6 streams a run already created elsewhere).

### 15 — Tenant isolation + data deletion
**Tool:** pytest + Playwright. **Pass criteria:** Org A cannot see Org B; deletion is real (no log residue).
**Applies to:**
- J7/J8 — Org A cannot open Org B's `/runs/<runId>` or `/inspector/<runId>`.
- J9 — uploaded docs are org-scoped; deletion removes file + chunks + embeddings.
- J10 — `/dashboard` `createRun` is org-scoped; a user creates runs only in their own org.
- J11 — `/memory` recall is org-scoped; `/contracts` likewise.
**N/A:** J1, J2 — pre-org-context (sign-in establishes the org; `/` is
org-agnostic). J3, J4, J5, J6 — covered transitively via the run they
produce (the run is the org-scoped object, tested at J7/J8).

### 16 — Privacy / log redaction
**Tool:** grep-based audit on log fixtures. **Pass criteria:** no PII / no source-content leakage in logs.
**Applies to:**
- J4 — retrieval logs carry URLs/titles, not full source bodies.
- J5 — generation logs carry no full prompt/evidence text.
- J6 — run-event logs carry no PII.
- J9 — upload logs carry no document content or filenames-as-PII.
**N/A:** J1 (no credential logging — verified separately), J2, J3, J7, J8,
J10, J11 — no source-content or PII written to logs at these stages.

### 17 — Sovereignty (data-classification routing)
**Tool:** CI test on `sovereign_router.py`. **Pass criteria:** all non-PUBLIC_SYNTHETIC classifications blocked from external API.
**Applies to:**
- J9 — a `CLIENT`-classified uploaded doc cannot be sent to any external API; CI fails if not blocked.
- J4/J5 — retrieval/generation routing honours the data classification of every evidence item.
**N/A:** J1, J2, J3, J6, J7, J8, J10, J11 — no classified-data egress
decision point (J3 question text is operator-entered, classified at J9 only
for uploads).

### 18 — Migration tests
**Tool:** DB migration on a copy of prod data. **Pass criteria:** rollback works; no data loss.
**Applies to:**
- J6/J7 — run-store schema migration (the `run_store` backing runs) + rollback.
- J11 — `/memory` workspace-memory store + Evidence Contract store migrations.
**N/A:** J1, J2, J3, J4, J5, J8, J9, J10 — no own persistent schema (J9
file storage is blob-not-schema; auth uses static_accounts, not a migrated DB).

### 19 — LLM quality gates
**Tool:** eval set per template (15 questions). **Pass criteria:** citation precision/recall ≥ baseline.
**Applies to:**
- J5 — generation: per-template eval set; citation precision/recall ≥ baseline.
- J6 — the completed run's report meets the quality gate end-to-end.
**N/A:** J1, J2, J3, J4, J7, J8, J9, J10, J11 — no generated-prose quality
surface (J4 retrieval quality is corpus adequacy, a separate gate; J3 is
scope classification).

### 20 — Semantic chart correctness
**Tool:** pytest + Vega-Lite spec validation. **Pass criteria:** chart data matches Evidence Contract spans.
**Applies to:**
- J7 — `/runs/<runId>/graph`: rendered chart data matches the run's Evidence Contract spans.
- J8 — any chart in the Inspector view validates against its source spans.
**N/A:** J1–J6, J9, J10, J11 — no semantic chart rendered (the `/charts_test`
harness exercises chart components but is excluded, §2).

### 21 — Anti-sycophancy
**Tool:** paired-prompt CI per ELEPHANT methodology. **Pass criteria:** stance delta <5% on 20 paired prompts; nightly full eval.
**Applies to:**
- J5 — generation: paired prompts (leading vs neutral framing of the same question) → stance delta <5%.
- J6 — the run's report shows no sycophantic drift toward the question's implied stance.
**N/A:** J1, J2, J3, J4, J7, J8, J9, J10, J11 — no model-stance output
surface.

### 22 — Codex code review
**Tool:** Codex Red-Team Checklist. **Pass criteria:** GREEN per task.
**Applies to:** cross-cutting — every PR that builds or changes any
stage J1–J11 passes a Codex diff review (the `polaris/codex-required` CI
gate). Process gate, not a per-route runtime test.
**N/A:** none (cross-cutting) — but it is a process gate, not a journey-stage
test; this is one of the two rows excludable if a strict count of 22 is needed.

### 23 — Layer-3 walkthrough
**Tool:** product-owner (user) + paid sample evaluator. **Pass criteria:** recorded fresh-state, async-reviewed.
**Applies to:** the whole journey J1–J11 — a fresh-state walkthrough
recorded end-to-end; the user (product owner) and the paid sample evaluator
review the recording asynchronously.
**N/A:** none — this type IS the whole-journey human review.

### 24 — Fixture governance + flake budget
**Tool:** test-infra discipline. **Pass criteria:** flake rate <2%; fixtures versioned and refreshed quarterly.
**Applies to:** cross-cutting — the test suites for all stages J1–J11 share
a flake budget (<2%) and versioned fixtures (the pinned fixture run used by
rows 4/20, the rehearsal prompt set, the adversarial corpus of row 6).
**N/A:** none (cross-cutting) — process/infra gate, not a per-route test;
the second of the two rows excludable for a strict count of 22.

## 4. Coverage grid

`✓` applies · `—` N/A · `≈` cross-cutting (applies to all stages).

| # | Test type | J1 | J2 | J3 | J4 | J5 | J6 | J7 | J8 | J9 | J10 | J11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Unit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Integration | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3 | Artifact contract `#503` | — | — | — | — | ✓ | ✓ | ✓ | ✓ | — | — | ✓ |
| 4 | Visual regression | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 5 | E2E happy path | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 6 | E2E adversarial | — | — | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | — |
| 7 | Cross-browser | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 8 | Accessibility | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 9 | Multi-tab safety | — | — | ✓ | — | — | ✓ | ✓ | ✓ | — | — | — |
| 10 | Network resilience | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 11 | SSE ordering/backpressure | — | — | — | — | — | ✓ | — | — | — | — | — |
| 12 | Cancellation/resume | — | — | — | — | — | ✓ | — | — | — | — | — |
| 13 | Performance | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 14 | Security | ✓ | — | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 15 | Tenant isolation + deletion | — | — | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 16 | Privacy / log redaction | — | — | — | ✓ | ✓ | ✓ | — | — | ✓ | — | — |
| 17 | Sovereignty routing | — | — | — | ✓ | ✓ | — | — | — | ✓ | — | — |
| 18 | Migration | — | — | — | — | — | ✓ | ✓ | — | — | — | ✓ |
| 19 | LLM quality gates | — | — | — | — | ✓ | ✓ | — | — | — | — | — |
| 20 | Semantic chart correctness | — | — | — | — | — | — | ✓ | ✓ | — | — | — |
| 21 | Anti-sycophancy | — | — | — | — | ✓ | ✓ | — | — | — | — | — |
| 22 | Codex code review | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ |
| 23 | Layer-3 walkthrough | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 24 | Fixture governance | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ | ≈ |

## 5. Handoff to I-rdy-020 (#516)

#516 ("run the test matrix — stub + OpenRouter") executes this matrix:

1. Each `✓` cell is a concrete test to run; each `—` is a documented,
   reasoned exclusion (no silent gap).
2. Test type 3 (Artifact contract) stays at the contract level until
   I-rdy-007 / #503 lands the live-run artifact contract; #516 binds the
   field-level schema then.
3. The 19 harness/diagnostic routes (§2) are out of scope for #516 — they
   are component test beds, not the product.
4. Rows 22 + 24 are process/infra gates; #516 records their status
   (Codex-required CI green; flake rate) rather than running per-route tests.
