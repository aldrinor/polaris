# The Research Planning Gate — Consolidated Design (Opus)

**Consolidates two independent designs** (Sol / GPT-5.6 code-grounded, Fable 5) + a 2026 best-practices digest.
**Date:** 2026-07-16 · **Status:** DESIGN — build only after operator approval; build runs in a workflow, main session monitors.
**Target repo:** `/home/polaris/wt/outline_agent` (champion `bot/outline-agent-box @ df4118a`). Never edit `flywheel/`.

> **The thesis both designers reached independently:** the gate produces ONE durable, typed **research contract**, then COMPILES it into levers the champion pipeline *already exposes but the driver never populates* — retrieval-backend routing (`ResearchFrame`), FS-Researcher query text, and `deliverable_spec`/`scope_spec`. **Scope always ADDS/ROUTES queries at retrieval; it NEVER filters a frozen corpus.** A disclosure-only compliance audit reads the same contract at the end. Faithfulness (`strict_verify`) is untouched.

---

## 1. Non-negotiables (carried from operator rulings)
1. **FAITHFULNESS FROZEN.** No edit to `src/polaris_graph/generator/provenance_generator.py` / `strict_verify` / the drop rule. No new verification pass. A conformance test asserts a clean diff and that every recompose path still traverses the unchanged verifier.
2. **No starvation.** Scope reaches FS-Researcher *query generation* and backend routing BEFORE the first fetch. Any post-fetch filter is a secondary safety net for explicit prohibitions only — never the sole scope mechanism. (The 997→131 filter that tanked RACE 0.4447→0.3264 is the banned anti-pattern.)
3. **Never invent a constraint.** Enforced by TYPE: a hard/binding term requires `origin == explicit` (a real prompt span) or an affirmative user action. Inferred/default terms may only weight, prefer, or route — never hard-gate, exclude, or become a stated requirement.
4. **Priority COVERAGE > INSIGHT > READABILITY.** Length is planning context, never a truncation gate. Required coverage drives the gap ledger. Tone is prose-only.
5. **Fail-open.** Any gate error → empty/degraded contract → every lever reads its current default → byte-identical to today's champion. The gate can only ADD guardrails; it can never abort a run or drop a source.
6. **Reuse, don't rebuild.** Reuse the validated rule-reader (`round1-if-compiler:constraint_extractor.py`), the intake extractors, FS-Researcher, the ResearchFrame router, `deliverable_spec`/`scope_spec`, the outline agent. New code is small and additive.

---

## 2. Architecture (both modes)

```
caller passes mode EXPLICITLY (interactive | autonomous)   ← Sol: never infer mode from terminal/timeout
        │   benchmark driver ALWAYS passes autonomous
        ▼
[1 UNDERSTAND]  deterministic candidate extraction (rule-reader + intake extractors, exact spans)
        ▼
[2 COMPILE]     one structured LLM call → typed ResearchContract (every clause accounted for;
                each term tagged explicit/inferred/user + force hard/prefer/open)
        ▼
[3 VALIDATE+TRIAGE]  deterministic: span/quote equality, no inferred-hard, clause coverage, conflicts
        │                                    │
   INTERACTIVE                          AUTONOMOUS  (benchmark)
   show editable plan + diff            ask nobody, wait for nobody
   ask 0–3 MATERIAL questions           least-restrictive open defaults
   edit / answer / approve  ──┐         disclose assumptions; auto-pin      ← the two modes differ at ONLY this node
        ▼                     └──────────────┬─────────────┘
[4 PLAN+PIN]    2nd structured call → threads, query intents, outline seed, coverage matrix; hash+pin (immutable)
        ▼
[5 PROJECTIONS] same pinned artifact → retrieval | outline | compose | render   (typed per-stage views)
        ▼
[6 COMPLIANCE AUDIT]  term-level SATISFIED/FAILED/UNSATISFIABLE/UNKNOWN, routed to owning stage
                      (disclosure-only; strict_verify untouched)
```

- **Interactive** (real users): ≤3 material questions; editable plan (Gemini-style natural-language edits); retrieval waits for approve/edit/answer/"use best judgment"; never crosses into autonomous on a timeout.
- **Autonomous** (benchmark; `PG_GATE_AUTONOMOUS=1`, the default in `scripts/dr_benchmark/run_gate_b.py`): a pure `contract→contract` function, **no I/O, never blocks**. Every would-ask becomes an open-ended assumption surfaced in report front-matter. *Enforced by a test asserting zero `needs_input` exits with no input channel.* This is the load-bearing mode — without it the gate can't be RACE-scored.

---

## 3. The contract schema (merged)
Adopt **Sol's typed governance skeleton** (it's the more complete one) with **Fable's `Tagged`-provenance discipline** on every term:

- **Envelope:** immutable `PlanningGateArtifact` — `mode`, `state`, `original_prompt`, `contract`, `plan`, `clarification_questions`, `revisions` (JSON-Patch), `contract_sha256`/`plan_sha256`/`artifact_sha256`. Reuse the existing `research_planner.py:serialize_plan_canonical`/`plan_sha256`.
- **Every term = `ContractTerm{value, origin(explicit|user|inferred|policy_default), force(hard|prefer|open), spans[], rationale, enforcement_stages[]}`.** `explicit` requires exact `prompt[start:end]` quote equality. **Hard force is invalid unless origin==explicit/user** (the mechanical no-invention guarantee).
- **Groups:** `ObjectiveSpec` (question, purpose, audience, output_language, depth), `ScopeSpec` (source_types, quality, languages, date, geography/jurisdiction, domains, named_sources, prohibited), `ContentSpec` (required/optional `CoverageRequirement`s incl. comparisons/metrics/counterevidence + entities + breadth/depth), `DeliverableSpec` (kind, sections w/ exact-title & order locks, length, visuals, citation, rhetoric/tone), plus `ambiguities[]`, `assumptions[]`, `conflicts[]`, `complexity`.
- **Plan (separate, adapts to evidence while contract stays pinned):** `threads`, `evidence_needs`, `query_intents` (each carrying its scope term-ids + language/date/source lanes), `outline_seed`, **`coverage_matrix`** (every binding term → owning stage(s) + ≥1 retrieval lane), `budget` (`mandatory_lane_count`, overflow = expand-or-fail, **never silently truncate a mandatory lane**), `stop_conditions` (semantic sufficiency, not a source-count quota).

---

## 4. The understanding engine
A **bounded hybrid**, not one blind call (both agree; digest confirms):
1. **Deterministic candidate pass** — reuse `round1-if-compiler` `constraint_extractor` ⊕ champion `intake_constraint_extractor` (`extract_constraints_regex`, `extract_instruction_slots`, `extract_scope_constraints`). Preserve exact offsets. **Deterministic wins on overlap; LLM fills gaps.** One candidate adapter — one canonical contract, no competing truth sources.
2. **Contract-compiler call** — structured JSON; system prompt forbids marking implications as explicit, forbids inventing date/geo/source/length, requires open/null for unspecified, decomposes compound prompts preserving dependencies, records ambiguities + assumptions + conflicts, returns `clause_coverage` (every operative clause dispositioned). **Raise the current 2,000-token `plan_research` cap** — inadequate for compound contracts (Sol); use provider-resolved max + bounded 2-call structure.
3. **Deterministic validate + triage** — quote equality, no inferred-hard, every candidate represented-or-rejected, every clause dispositioned, conflicts surfaced. One correction retry → else conservative span-verified fallback (raw prompt as objective, explicit rules only, open elsewhere; `compiler_degraded=true`).
4. **Plan-compiler call** — from the *validated contract*: smallest complete thread set (scale to complexity, no fixed quota), every evidence-bearing requirement gets ≥1 mandatory query intent, scope encoded in query intents (hard→query+backend filter, soft→ranking), coverage matrix built, exact headings only from explicit instruction.

Cost: 2 small-model calls (glm-5.2, same as FS query-gen) — negligible vs retrieval+outline.

---

## 5. Per-stage enforcement (merged hook map)

| Stage | What the contract does | Champion hook (verified) |
|---|---|---|
| **Gate entry** | compile/load artifact, require approved/auto_pinned, persist `planning_gate_artifact.json` | new `planning/research_planning_gate.py:run_research_planning_gate`; in `run_honest_sweep_r3.py:run_one_query` replace the raw `plan_research(_clean_question,…)` decision |
| **Retrieval (the no-starvation core)** | `source_types→evidence_needs` routes scholarly backends (S2/OpenAlex) = **GO FIND journals**; scope terms + languages + entities into query TEXT; hard scope → backend-native filter, soft → ranking | `live_retriever.py:run_live_retrieval` (accepts `research_frame`/`protocol`/`amplified_queries`); `fs_researcher_query_gen.py:_plan_expert_facet_queries` + `_multilingual_native_reserve` + `sub_entity_query_expander`; `expert_facet_planner._question_anchor`. **FS branch in `run_one_query` currently passes only `_clean_question` and discards `_research_plan.sub_queries` — fix that.** |
| **Outline (FEED)** | seed required sections + pre-load `required_coverage`/`must_address` as PENDING gaps so the deep-think loop CLOSES contract gaps; thread scope into gap search | `outline_agent.py:run_outline_agent_or_legacy` (already takes `deliverable_spec`/`scope_spec` → `outline_digest.build_requirements_block`). **BUG (both found): `_tool_search_more_evidence` drops `protocol`/`research_frame` → deep-think search runs unscoped. Thread scope through `OutlineWorkspace`.** (accepts `**_ignored` today — clean seam) |
| **Compose** | tone/audience/pov into the section advisory-prose slot (prose only); document_type selects skeleton | `multi_section_generator.py:generate_multi_section_report` (:~3010 seams), `_call_section`, `_select_section_system_prompt`. Length = planning context, never truncation. |
| **Render** | required sections/order, tables from VERIFIED fields only, references dedup by work, length reported | `compose_agentic_report_s3gear329.py:main` assembly — thread specs; keep `_audit_citations`. Mark `retrieval_scope_status` when run on a prebuilt corpus. |
| **Compliance audit** | term-level satisfied/failed/unsatisfiable/unknown + owning stage; deterministic where possible, one cheap judge for semantic coverage | new `planning/contract_compliance.py:audit_contract`, run AFTER assembly ALONGSIDE (never touching) the frozen faithfulness tripwire. Disclosure-only. |

---

## 6. Gate ↔ outline-agent seam: **FEED** (both agree)
Gate replaces the *pre-retrieval* planning call; the outline agent stays the *post-retrieval evidence-aware refiner*. Refactor `run_outline_agent_or_legacy` into `refine_outline_from_seed(seed_outline, contract, retrieval_projection, coverage_matrix, …)` with the legacy path as `seed = supplied_seed or legacy_call_outline(...)`. Seed behavior depends on provenance: explicit/user headings = immutable title+order; gate-proposed headings = stable `section_id` + revisable title, splittable/mergeable only if every binding term stays mapped. **Required topics are coverage obligations, NOT automatically headings** (the round1 mistake). Extend `OutlineWorkspace` with the contract hash + term ledger; validate every `update_outline` against it (reject dropping an explicit lock or the last owner of a binding term). Degrades to exact champion behavior when the contract names no structure.

---

## 7. Ask-vs-assume (merged policy)
Ask **iff uncertain AND consequential**, ≤3, interactive only. Eligible only if: not already answered, ≥2 plausible interpretations remain, the choice materially changes discovery/structure/decision, and open-leaving wastes real research. Autonomous = **zero asks**, least-restrictive open defaults, every assumption disclosed. Locked defaults: no hard date cutoff ever (prefer-fresher soft, per operator); geography/jurisdiction stay open/comparative; source-type open+prefer-authoritative unless explicit; source-language ≠ prompt language; tone/heading never trigger a question. Explicit "only/must/exclude/do not use" + supplied ranges/counts/headings = hard; "prefer/focus/especially" = soft. When a soft preference starves a mandatory thread → relax + disclose; when two explicit terms conflict → interactive asks, autonomous executes the feasible intersection and labels the rest `UNSATISFIABLE`.

---

## 8. Build sequence (spikes first; each gated; faithfulness frozen throughout)
Work on a fresh branch off `bot/outline-agent-box`. Every step additive + flag-gated (OFF = byte-identical) + measured.

- **S0 — Port + reconcile (no behavior change).** Port `round1` rule-reader + tests into champion; put it and the intake extractors behind ONE candidate adapter. Do NOT port the compose-time `filter_eligible` wiring or the coverage-to-heading mapping. *Accept:* candidate reconciliation corpus; OFF path byte-identical.
- **S1 — Contract + plan schema + compiler (offline).** Schema, 2 structured calls, deterministic validators. *Accept:* compile all 100 DRB prompts in autonomous mode; human-audit a stratified sample — **no invented hard constraint, no missing explicit clause, an assumption record for every inferred term** (not merely valid JSON).
- **S2 — Retrieval projection (the no-starvation proof).** Thread `retrieval_plan`/`research_frame` into FS-Researcher + `run_live_retrieval`; scope into query text + backend routing. *Accept:* on a FRESH task-72 run, telemetry proves journal/English + every mandatory topic reach `_plan_expert_facet_queries` BEFORE results exist; the gate never reduces evidence count vs no-gate (the mechanized 997-row guard).
- **S3 — Outline FEED + gap-scope fix.** `refine_outline_from_seed`; seed gap ledger; fix `_tool_search_more_evidence` scope drop. *Accept:* replay banked corpora (tasks 30/61/76/90) — real refinement, locks + term-mappings preserved, gap queries stay in-scope, no second fresh planner.
- **S4 — Compose/render projections + compliance audit.** Thread specs; deterministic renderer; `audit_contract`. *Accept:* exact section order / comparison table / length range all trace to verified claims; term-level audit produced.
- **S5 — End-to-end fresh autonomous run** on tasks {4,30,61,72,76,90}: retrieval→outline→compose→render, RACE + FACT, **3× per the measurement protocol**. *Accept:* RACE (esp. Instruction-Following) up vs champion, **FACT ≥ 90.3% held**, `provenance_generator.py` clean diff.

**Release gate is behavioral** (both insist): the contract must visibly alter FS discovery, survive outline refinement, constrain compose/render, and yield term-level audit results on REAL output. Green unit tests / a filtered fixed corpus / a source-count bump do NOT prove the gate fired.

---

## 9. Top risks (both designers) + mitigation
- **Hallucinated hard constraint** → the `origin==explicit`-for-hard type rule + clause coverage + assumption list.
- **Re-introducing the filter trap** → design has NO post-fetch scope filter path; mechanized "gate never lowers evidence count" test.
- **Scope loss in outline gap search** → the `_tool_search_more_evidence` fix (both found this bug).
- **Two-planner fight** → FEED + required-title subordination already in `apply_revision_ops`.
- **Budget truncating a mandatory lane** → compute `mandatory_lane_count` first; expand or fail loudly.
- **Compliance-judge circularity** → deterministic checks for counts/headings/length/tables/citations; a separately-configured judge only for semantic coverage; it can NEVER alter faithfulness verdicts.
- **Autonomous blocking** → STAGE-2 autonomous is pure `contract→contract`; test asserts zero `needs_input` with no input channel.

---

*Full independent designs preserved at:* `scratchpad/reviews/sol_gate_design.md` (Sol) and the Fable agent transcript. *Best-practices digest:* `scratchpad/reviews/gate_bestpractices_digest.md`.
