# Codex consult — POLARIS Carney demo readiness: exhaustive gap analysis

**Type:** PLANNING CONSULT (advisor, not a merge gate). The operator has
explicitly asked Claude and Codex to work "hand in hand" to identify
EVERY missing part before the Mark Carney demo. Claude has repeatedly
produced incomplete readiness plans; the operator is frustrated. Your
job: independently audit, find what Claude still missed, be exhaustive.

---

## §0. Front-load everything (cap directive)

- This is a single-round consult. Surface ALL findings now. No drip-feeding.
- "Don't pick bone from egg" — classify trivia as P3; reserve P0/P1 for
  things that genuinely block a Prime-Minister-grade demo.
- If you are tempted to hold a finding back "for next round" — there is
  no next round. Surface it now.

## §0.1 OPERATOR-LOCKED DECISIONS — these are CONSTRAINTS, not options. Do NOT propose alternatives.

1. **Generator = DeepSeek V4 Pro** (1.6T-param MoE, FP4/FP8). **Evaluator = Gemma 4 31B.** Two-family invariant holds. LOCKED — said 6+ times by operator. Do not suggest a different/smaller model.
2. **1 concurrent session** — operator will limit traffic. LOCKED.
3. **Canadian sovereign GPU** — V4 Pro needs 8× H200 or 12-16× H100. OVH Canada has no such hardware (verified — V100 only, Hopper GPUs are France-only). Operator is contacting Vexxhost (Montréal) + ISAIC (Edmonton). LOCKED constraint — no US providers, no France.
4. **"BPEI" name is banned** — being renamed to `ambiguity_detector` everywhere (407 files). Do not use "BPEI" in your output.
5. **Architecture = the deployed v6 stack** (redis + api + worker + webui via docker-compose.v6.yml). No rewrites. Pipeline B (legacy LangGraph) and Pipeline C (frozen CLI) are NOT in demo scope.
6. **Demo = single venue**, PM Carney's office, flexible date in June 2026, off-peak GPU acceptable.
7. Stick to the canonical Carney plan (`docs/carney_delivery_plan_v6_2.md`) + the completed GitHub issue list. Do not invent new scope. The question is "is what we planned actually DONE and COHERENT," not "what else could we build."

---

## §1. Where we are

- **Orchestrator (CPU box) is LIVE** on OVH BHS5 (Beauharnois, Québec), domain `polarisresearch.ca`. 4 containers healthy: redis, api (FastAPI v6.2.0), worker (Dramatiq), webui (Next.js 16). Auth + transparency endpoint working.
- **Sovereign GPU is NOT secured yet** — generation route returns `400 completion_backend_unavailable` until a Canadian H100/H200 lands. Vexxhost/ISAIC outreach sent today.
- **The waiting period:** operator wants to use the GPU-wait window to test EVERYTHING — all features on, all connected, fully functional — so that when the GPU lands it is a one-env-var swap to go live.
- Claude's proposal for testing the LLM path during the wait: temporarily point the pipeline at **OpenRouter's V4 Pro** (same model, US-hosted, test-only, non-confidential questions, key removed before demo). The sovereign GPU swap is then one endpoint-URL change.

## §2. What the Carney plan says POLARIS must deliver

`docs/carney_delivery_plan_v6_2.md` defines **15 user-visible features**, each with a "match-or-beat ChatGPT 5.5 Pro DR / Gemini 3.1 Pro DR" bar:

- **F1** Scope discovery + template browse (landing page, 8 template cards, live suggestion)
- **F2** Query input with disambiguation modal (ambiguity detector — cluster retrieval candidates, modal if >1 entity cluster)
- **F3** Document upload + grounding (drag-drop, parse status, doc preview, sovereignty router for CLIENT docs)
- **F4** Live audit run with reasoning visibility (SSE — shows what was searched/rejected/changed/contradicted/verified)
- **F5** Report inspection with click-through audit (every claim sentence clickable → Inspector pane with source span, tier, evaluator agreement)
- **F6** Live citation overlay (Perplexity-parity hover-tooltip with quote + tier + multi-source count)
- **F7** Frame coverage as lead (top-of-report panel: "got 14 of 15 entities, 1 gap: [reason]")
- **F8** Contradiction navigation (inline ⚠ badges, side pane with all sides + tiers + sample sizes)
- **F9** Two-family disagreement signal (⚠ when generator + evaluator disagree)
- **F10** Inline visual generation (Vega-Lite — forest plot, comparison table, timeline; chart provenance)
- **F11** Report-scoped auditable follow-up (follow-up agent, parent-context, append rendering, refusal for out-of-scope)
- **F12** Side-by-side compare two reports (split-screen, claim-level diff)
- **F13** Pin replay / "what changed since last run" (re-run same query, diff visualization)
- **F14** Auditable research memory (memory page, save/pin/forget, cited recall)
- **F15** Audit bundle export (standalone-verifiable zip: report + bibliography + evidence pool + manifest + README)

**Cross-cutting capabilities** (north-star table, additional to F1-F15):
Knowledge snowballing (`evidence_deepener.py` + graph viz), anti-sycophancy CI (paired-prompt ELEPHANT methodology), sovereignty enforcement (data classification + provider routing), cross-jurisdiction synthesizer, strict_verify per-sentence provenance, two-family segregation invariant, Evidence Contract Gate, GPG-signed audit bundles.

**8 templates** in `config/scope_templates/`: clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom.

**The plan's testing matrix — 22 test types every feature must pass:**
unit, integration, artifact-schema, visual regression (4 viewports 1920/1024/768/375, Percy), E2E happy path, E2E adversarial, cross-browser (Chromium/Firefox/WebKit), accessibility (axe-core WCAG-AA), multi-tab safety, network resilience (offline/slow-3G), SSE ordering/backpressure, cancellation/resume, performance (Lighthouse, LCP<2.5s, INP<200ms, hover<100ms), security (XSS/CSRF/injection/prompt-injection), tenant isolation + data deletion, privacy/log redaction, sovereignty routing CI, migration tests, LLM quality gates, semantic chart correctness, anti-sycophancy paired-prompt CI, Codex code review.

**Demo logistics** (the "G-series" gap tasks, P0/P1): full sovereign dress rehearsal, T-1 fallback laptop drill, pre-recorded fallback runs, egress lockdown validation, T1 source snapshot cache, venue browser/network test, capacity + cold-start timing, clean-machine bundle verification, live ops runbook, audit calibration, handover package, legal/privacy boundary notice (PIPEDA/Law25).

## §3. Claude's GROUNDED inventory of what actually exists (verify these — don't rediscover)

**Frontend (`web/`, Next.js 16.2.4 + React 19 + Tailwind 4):**
- 33 `page.tsx` routes total. **17 are test-harness pages** — `charts_test/*`, `sentence_hover_test/*` (10 sub-pages), `(test_harness)/*`. Only ~16 are real product routes.
- Product routes: `/`, `/intake`, `/retrieval`, `/generation`, `/audit_live`, `/inspector/[runId]`, `/runs/[runId]`, `/dashboard`, `/memory`, `/pin_replay`, `/benchmark`, `/contracts`, `/upload`, `/sign-in`, `/sse`.
- `web/components/` has ONLY `ui/` with **7 shadcn components**. No shared feature-component library.
- `web/app/layout.tsx` has **NO navigation links** — every page is reached only by typing its URL. There is no global nav, no way to move between features.
- ~75 Playwright e2e specs exist — features were tested individually.

**Backend (v6 API — `src/polaris_v6/api/app.py`):** mounts routers for health, auth, runs, stream(SSE), ambiguity, bundle, scope, upload, charts, followup, compare, memory, templates, transparency + slice001-005 (intake/retrieval/generation/audit-bundle/benchmark) + disambiguation + graph. F10/F11/F12 backends (`charts/spec_builder.py`, `followup/agent.py`, `compare/differ.py`) exist and are mounted.

**Claude's 5 concrete gaps found so far (verify + extend):**
1. **Test-harness vs product blur** — 17/33 routes are scaffolds. F10/F11/F12 appear to have ONLY harness frontends (`charts_test/`, `follow_up_append/` harness, `split_screen/` harness) — no integrated product surface.
2. **No global navigation** — `layout.tsx` has no nav. The demo has no coherent journey; pages are islands.
3. **Frontend/backend template mismatch** — landing page (`web/app/page.tsx`) hardcodes templates `clinical, housing, climate, ai_sovereignty, …` but the backend `config/scope_templates/` has `clinical, policy, tech, due_diligence, ai_sovereignty, canada_us, workforce, custom`. They do not line up.
4. **Features built+tested in isolation, possibly not assembled** — the `bpei_phantom_completion` failure pattern: crown jewels exist in code with test-harness pages but may not be integrated into ONE coherent demo report view (charts + hover-citations + contradiction badges + follow-up box all together in the actual report page).
5. **No verified coherent demo flow** — there is no single tested journey land → pick template → ask → watch run → inspect integrated report → export bundle.

## §4. What Claude is asking Codex

Independently audit POLARIS for Carney-demo readiness. Be exhaustive. Specifically:

**A. Feature completeness.** Of F1-F15 + the cross-cutting capabilities + 8 templates — which are genuinely complete as a *product*, which are only test-harness/substrate, which are missing? Did Claude miss any feature or capability that the Carney plan promised?

**B. Frontend design + coherence.** Is the frontend a coherent, frontier-grade product or a set of disconnected test pages? What is missing for a PM-grade demo: navigation, visual design system, responsive layout, loading/empty/error states, the demo journey itself? Verify Claude's gaps 1-5 and add what Claude missed.

**C. Integration / "well connected."** Are the features actually wired end-to-end (frontend page → API route → pipeline → artifact → back to UI)? Where are the broken seams?

**D. Testing.** Of the plan's 22 test types — which are actually exercised, which are claimed but absent? Is the ~75-spec Playwright suite testing the *product* or the *harness pages*?

**E. Demo logistics.** What demo-day readiness work (G-series) is genuinely required and missing?

**F. What Claude STILL missed.** This is the most important section. Enumerate categories Claude has not named at all.

**G. The lock document.** Claude is about to write `docs/polaris_locked_scope.md` freezing LLM + architecture + features. Is the scope Claude intends to lock actually complete and correct?

## §5. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES   # APPROVE = Claude's readiness picture is complete enough to execute; REQUEST_CHANGES = Claude is still missing material parts
feature_completeness:
  genuinely_complete: [...]
  harness_or_substrate_only: [...]
  missing_or_broken: [...]
  features_claude_missed: [...]
frontend_gaps: [...]          # design, coherence, navigation, demo journey
integration_gaps: [...]       # broken seams between layers
testing_gaps: [...]           # plan test types not actually run
demo_logistics_gaps: [...]
categories_claude_never_named: [...]   # §4.F — the most important
lock_document_corrections: [...]
p0: [...]   # blocks the demo
p1: [...]
p2: [...]
recommended_readiness_sequence: <text — the order Claude should do the work>
reasoning: <full reasoning>
```

Do NOT propose architecture rewrites or new features beyond the Carney plan. The demo is weeks away. The question is completeness and coherence of what was already planned.
