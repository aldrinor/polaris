HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output the §8.3.9 YAML verdict FIRST, then prose:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex BRIEF gate — I-meta-005 Phase 1 (#985): Research planner + question-shaped outline

**You are reviewing the ACCEPTANCE-CRITERIA correctness of this brief** (not code — code is the diff gate).
Parent plan #982 (`docs/polaris_fundamental_rearchitecture_plan.md` rows 47, 57, 78). Phase 1 closes gaps
#1 (query decomposition), #2 (research planning), #8 (report structure), #10 (decision artifact seed).

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)
- **NO per-domain allowlist / `if domain ==` router / clinical literals in CODE.** The planner is field-
  agnostic: the question's own content drives faceting + section choice. (Same no-literals-in-code law that
  Phase 0a's authority model follows.)
- **OFF byte-identical.** All new behavior gates behind `PG_USE_RESEARCH_PLANNER` (default off). Off = the
  current `decompose()` + `_ALLOWED_SECTIONS` path, byte-for-byte. This is a shadow build; the live flip is
  a later operator-gated Gate-A step.
- **BUILD + SMOKE are spend-free.** The planner's one Writer LLM call is injected (a fake planner-LLM in
  tests); NO live OpenRouter call in the build or smoke. Live call only at runtime under the on-flag.
- **Keep gap #19 (pre-registration + SHA).** The `scope_gate.py` refactor must preserve the scope
  pre-registration + SHA-pin that gap #19 depends on.

## 1. THE PROBLEM (grounded in running code)
- `decomposer.py:71` `decompose(question, max_sub=6)` is a HEURISTIC string-split on aspect markers
  ("considering A, B, C") capped at 6; its own docstring (`:30-32`) says "Live LLM-driven decomposition …
  is a separate follow-up." A broad policy question with no "considering …" tail returns ONE sub-question.
- `nodes/scope_gate.py:258` `extract_pico_heuristic` + `:231` `_DRUG_NAME_RE` is clinical-only PICO; a
  housing/physics/trade question gets no usable frame.
- `generator/multi_section_generator.py:59-68` `_ALLOWED_SECTIONS` = 8 CLINICAL literals
  (Efficacy/Safety/Regulatory/Comparative/Mechanism/Dose Response/Population Subgroups/Long-term Outcomes);
  `:259-261` the outline prompt says "choose only from this list"; `:450-452` fallback is
  `[Efficacy,Safety,Comparative]`. So a non-clinical question gets clinical headings — gap #8, the trap.

## 2. THE BUILD (4 components, all behind PG_USE_RESEARCH_PLANNER)

### 2.1 NEW `src/polaris_graph/planning/research_planner.py`
- A typed `ResearchFrame` dataclass (generalized PICO, field-invariant): `entities`, `relations`,
  `metrics`, `comparators`, `constraints`, `claim_type` (one of: empirical / policy-comparison / forecast /
  mechanism / descriptive). NO clinical fields.
- `plan_research(question, *, planner_llm) -> ResearchPlan` makes ONE Writer call emitting JSON: the frame +
  **20-40 faceted sub-queries** + a **question-derived section outline** (each section = an archetype TAG +
  a question-specific title + a per-section **evidence target** = the done-definition: how many
  corroborated findings at what authority floor). `planner_llm` is an injected callable
  (`(prompt:str)->str`) so tests pass a fake; production passes the Writer (DeepSeek V4) via the existing
  `openrouter_client`. Strict JSON parse; on malformed output, FAIL LOUD (LAW II) — do NOT silently fall
  back to the heuristic.
- Sub-query count clamp: if the model returns <20 or >40, log + clamp to [20,40] by merge/split (bounded,
  deterministic) — never silently accept 1.

### 2.2 `nodes/scope_gate.py` refactor
- Generalize `extract_pico_heuristic` → a thin field-agnostic frame extractor (no `_DRUG_NAME_RE` clinical
  gate on the live path; the drug regex moves to a clinical fixture). KEEP the scope pre-registration + SHA
  pin (gap #19) intact — that is the auditable "we declared the plan before running" guarantee.

### 2.3 `generator/multi_section_generator.py` archetype model
- Replace `_ALLOWED_SECTIONS` (8 clinical literals) with `_SECTION_ARCHETYPES` (~12 field-invariant TAGS):
  Background, Mechanism, Quantitative-Comparison, Cost-Economics, Risk, Jurisdiction, Stakeholders,
  Scenarios, Decision, Uncertainty, Methodology, Limitations.
- The outline prompt (`:259-261`) instructs the model to write the **title for THIS question** and tag it
  with one archetype; the parser (`:363`, `:450-452`) validates the **archetype TAG**, not a clinical title
  literal. Fallback is archetype-driven (Background + Quantitative-Comparison + Decision), NOT
  `[Efficacy,Safety,Comparative]`.
- `SectionPlan.title` becomes the question-specific title; add `SectionPlan.archetype` (the validated tag).
- Clinical prompt rules move to `config/section_prompts/clinical.yaml` as an **advisory** hint selected only
  when the frame's claim_type/entities indicate clinical — config, NOT a code lock.

### 2.4 Wiring
- A single `PG_USE_RESEARCH_PLANNER` env gate. Off: the existing `decompose()` + `_ALLOWED_SECTIONS` path
  runs unchanged (byte-identical). On: the planner produces the frame + sub-queries + archetype outline that
  feed retrieval + the section generator.

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4)
New `tests/polaris_graph/planning/test_research_planner_phase1.py` + section-archetype tests:
- **P1-1 OFF byte-identity:** with PG_USE_RESEARCH_PLANNER off, `decompose()` and the section outline are
  unchanged vs pre-Phase-1 (pin exact outputs on the clinical fixture).
- **P1-2 frame + 20-40 sub-queries:** inject a fake planner-LLM returning a realistic frame for each of the
  5 golden DRB-EN Qs; assert 20 ≤ len(sub_queries) ≤ 40 and a non-empty archetype outline.
- **P1-3 off-domain probes (the field-agnostic proof):** 3 fixtures — a physics question, an ag-policy
  question, a JP-pharma-reg question. Assert: usable frame + 20-40 sub-queries each, AND **ZERO clinical
  section labels** (no Efficacy/Safety/Dose Response/Population Subgroups title or tag) on the physics and
  ag-policy outlines.
- **P1-4 archetype parser:** the section parser accepts a question-specific title carrying a valid archetype
  tag and rejects an invalid tag; fallback is archetype-driven, not clinical.
- **P1-5 malformed-LLM fail-loud:** a fake planner-LLM returning malformed JSON makes `plan_research` raise
  (no silent heuristic fallback).
- **P1-6 clamp:** fake returning 8 sub-queries → clamped/expanded toward ≥20 deterministically; fake
  returning 60 → clamped to ≤40.
- **P1-7 scope-gate gap-19 preserved:** the scope pre-registration + SHA pin still computes + matches.

## 4. EXIT CRITERIA (issue #985)
20-40 sub-questions + question-shaped outline on the 5 golden DRB-EN Qs + 3 off-domain probes (physics,
ag-policy, JP-pharma-reg); **zero clinical section labels on a non-clinical question**; OFF byte-identical;
all smoke green; no live spend in build/smoke.

## 5. WHAT I HAVE ALSO CHECKED AND THEY ARE CLEAN
- `decomposer.py` callers: the heuristic `decompose()` stays as the off-path; on-path uses the planner.
- `multi_section_generator.py:2629` (M-44 section scope) — additive, not a clinical title literal in the
  allow-list; the archetype change does not touch it.
- `config/scope_templates/*.yaml` — static clinical section logic; retired from the on-path, kept as the
  off-path + clinical fixture.

## 6. REVIEW QUESTIONS FOR CODEX
1. Is OFF byte-identity actually achievable with a single env gate given the section model + decompose are
   on the live generation path? Any code path where the archetype refactor leaks into off mode?
2. Is the 20-40 clamp honest (deterministic merge/split) or does it risk fabricating sub-questions? Should a
   genuinely simple question be allowed <20 (and is the EXIT "20-40" too rigid for a narrow question)?
3. Is the archetype-tag parser + question-specific title the right cut to kill the clinical-literal trap
   without losing the clinical fixture's auditability?
4. Does moving `_DRUG_NAME_RE` off the live path break gap #19 (pre-registration SHA) anywhere?
5. Scope: is this the right Phase-1 boundary (frame+planner+sections) vs pulling in source-discovery
   (Phase 2) — i.e., is the per-section evidence target meaningful before Phase 3's plan-sufficiency gate?

APPROVE iff the acceptance criteria are correct, OFF byte-identity + spend-free build hold, and the
field-agnostic no-clinical-literal cut is sound. This brief is the build contract.
