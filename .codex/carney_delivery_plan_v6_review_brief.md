# Codex review — v6 (substrate-aware, frontier-comparable)

**Model:** gpt-5.5, xhigh reasoning. Adversarial review.

**Word budget:** ~1500 words.

## What changed

User pushed back hard: "I keep telling you to remember our previous journey." I had been planning as if greenfield while ignoring 270 Python files + 47 audit_ir modules + 113 completed milestones. v6 anchors on a real codebase audit (`docs/substrate_audit_2026-05-01.md`).

Read both:
- `docs/substrate_audit_2026-05-01.md` (what's actually built)
- `docs/carney_delivery_plan_v6_draft.md` (the new plan)

Key reframes:
- Most engineering reframed as "expose existing substrate via modern UI" not "build from scratch"
- 15 user-visible feature areas (F1-F15), each with substrate status + new build + best-practice reference + Playwright+AI test matrix
- Match-or-beat bar specified per feature (not generic "frontier-comparable")
- Document upload, inline visuals, live citation overlay, conversational follow-up, side-by-side compare, memory, pin replay all elevated to first-class features (not deferred)
- Anti-sycophancy CI per ELEPHANT/SycEval methodology
- Timeline 14 → 16 weeks; budget $26-58k → $32-70k

## What I want you to attack

### A. Did v6 actually anchor on the audit, or am I still glossing?

For each F1-F15: is the substrate-vs-new-build delineation honest? Specifically:
1. F2 ambiguity detector — is "cluster top-K candidates by primary entity" actually feasible given existing retrieval substrate?
2. F3 document upload — substrate is 11 endpoints + ingester + private_corpus_sync + local_document_rag + workspace_store. Is the "new build" really just UI + sovereignty router, or is more missing?
3. F10 inline visuals — substrate has `smart_art_generator.py`. What does it actually generate today? If nothing renderable, the "new build" is much bigger than just Vega-Lite consumer.
4. F11 conversational follow-up — substrate has campaign_store + session_feedback. Are these enough for the agent? Or do I need a new follow-up agent?
5. F14 memory — `local_document_rag.py` exists. Does it actually do RAG or is it stub?

### B. Is "match-or-beat" actually achievable per feature?

Specifically:
1. F6 live citation overlay (Perplexity-grade) — Perplexity has years of polish on this. Is it realistic in Phase 2 alongside 8 other features?
2. F11 conversational follow-up — ChatGPT's follow-up is best-in-class. POLARIS adding "audit-traceability per follow-up" is the differentiator, but is the base experience matching?
3. F10 inline visuals — Gemini's chart rendering uses Vega-Lite under the hood per public reports. Match is achievable; quality of auto-generation is the question.
4. F14 memory — ChatGPT memory is general; POLARIS memory is research-specific. Is the user-facing experience going to feel competitive?

### C. Phase realism

Phase 2 has 9 features (F4-F10, F13, F14) in 5 weeks. With Playwright + Test Agent + accessibility + visual regression per feature, realistic?

### D. Testing matrix — exhaustive enough?

Per-feature gates: unit, integration, visual regression, e2e happy, e2e adversarial, accessibility, multi-tab, network resilience, performance, security, sovereignty, anti-sycophancy, Codex review, walkthrough.

1. Anything missing from this matrix?
2. Multi-tab safety + network resilience are unusual additions; are they actually critical?
3. AI Test Agent (Playwright Test Agents per BrowserStack 2026 best practices) — should this be mandatory or optional?

### E. Phantom completion residue

Find anywhere in v6 where:
- "Substrate exists, just expose" hides actual missing engineering
- Match-or-beat bar is hand-waved
- Test matrix could be checked off without genuine coverage
- 16-week timeline is fantasy

### F. Final verdict

GREEN / YELLOW / RED. If GREEN: explicit start recommendation. If YELLOW: specific surgical lines. If RED: structural issue.

## Constraints

- Brutal as before. User explicitly wants Codex to be loyal AND adversarial.
- This is the v6 verdict. If GREEN, user commits and we start Phase 0.
- If YELLOW, name surgical redlines.
