# Phase 1 BUILD SPEC — research planner + archetype sections (#985). BINDING.

**The APPROVED brief `.codex/I-meta-005-phase-1/brief.md` (Codex APPROVE iter 5) is the detailed design
contract. Implement it EXACTLY, file by file.** This spec is the checklist + the 2 Codex P2 build notes.

## HARD CONSTRAINTS (from brief §0 — do not relax)
1. Everything behind `PG_USE_RESEARCH_PLANNER` (default off). **OFF = byte-identical** to today's
   `query_decomposer.decompose_question` + `_ALLOWED_SECTIONS` path. True dual path — do NOT delete the
   legacy code; retain + select it when off.
2. **BUILD + SMOKE spend-free**: the planner Writer call is an injected callable; smoke installs a fake AND
   asserts no `OpenRouterClient`/live httpx client is constructed.
3. **NO `if domain ==` / clinical literal as a control value on the on-path.** Field-agnostic.
4. snake_case, explicit imports, no `unittest.mock` in src/ (§9.4). One responsibility per file.

## FILE-BY-FILE (implement brief §2)
1. **NEW `src/polaris_graph/planning/__init__.py` + `research_planner.py`** (brief §2.1): `ResearchFrame`
   (entities/relations/metrics/comparators/constraints/claim_type) + `ResearchPlan` (frame + sub_queries +
   outline[archetype tag + question-specific title + evidence_target]) dataclasses; `plan_research(question,
   *, planner_llm)` = one Writer call + at most one bounded retry; strict JSON parse, malformed → raise;
   upper-clamp 40 (merge/truncate), lower bound retry-then-accept-honest (NO padding); `ResearchFrame.
   to_anchor_protocol()`; canonical-JSON serialize + sha256 + `{plan_path, plan_sha256}` into manifest
   BEFORE retrieval.
2. **`src/polaris_graph/nodes/scope_gate.py`** (brief §2.2): ADD a field-agnostic frame extractor for the
   on-path. KEEP `extract_pico_heuristic` + `_DRUG_NAME_RE` exactly (clinical importers unchanged). KEEP the
   scope pre-registration + SHA (gap #19).
3. **`src/polaris_graph/retrieval/scope_query_validator.py`** (brief §2.4): extend `_build_anchor_tokens`
   ADDITIVELY to also merge `entities/relations/metrics/comparators/constraints` when present (clinical
   PICO behavior unchanged — already skips missing fields).
4. **`src/polaris_graph/generator/multi_section_generator.py`** (brief §2.3): ADD `_SECTION_ARCHETYPES`
   (~12 tags) + `SectionPlan.archetype: str = ""` (additive). Dual path: off = legacy `_ALLOWED_SECTIONS`
   prompt(`:259`)/parser(`:363`)/fallback(`:450`) BYTE-IDENTICAL; on = archetype outline prompt + tag-
   validating parser + archetype-driven fallback. **Route M-44(`:2618`)/M-47(`:4260`)/contract-matching on
   `archetype` in on-mode; off-mode title routing untouched.** Clinical prompt rules →
   `config/section_prompts/clinical.yaml` (advisory prompt-TEXT only, no control branch).
5. **`scripts/run_honest_sweep_r3.py`** (brief §2.4): on-mode → amplified list fed `decomposed=
   plan.sub_queries`, `regulatory=[]/trial=[]/hand_authored=[]`; bypass `run_domain_backends` per-domain
   router; disable R-6 `{domain}.yaml` completeness expansion. Off-mode: all legacy paths byte-identical.
6. **NEW `config/section_prompts/clinical.yaml`**: advisory clinical writing guidance (prompt-text only).

## CODEX P2 BUILD NOTES (iter-5 APPROVE — fold into the build)
- **A (archetype no-leak in OFF):** `SectionPlan.archetype` default "" must NOT appear in OFF-mode
  serialized/`asdict`/manifest-observed artifacts. The OFF byte-identity smoke (P1-1) MUST pin the
  `asdict`/manifest-style section output (not only the titles), proving the additive field is inert in OFF.
- **B (M-44/M-47 archetype resolution):** the post-generation M-44/M-47 checks operate on `SectionResult`
  /title today. In on-mode, resolve the archetype from the originating `SectionPlan` (carry `archetype`
  onto `SectionResult`, OR pass an explicit plan-by-index/title→archetype map into the post-gen checks).
  Do not re-introduce a clinical-title literal to route.

## SMOKE — `tests/polaris_graph/planning/test_research_planner_phase1.py` (+ section/wiring tests)
Implement ALL 17 brief cases P1-1..P1-17 (serialized §8.4; fakes are plain classes, no unittest.mock; real
dict evidence pools). The two non-relaxable walls: **P1-1 OFF byte-identity (pin asdict/manifest output per
note A)** and the field-agnostic guards **P1-4 (zero clinical labels on physics/ag-policy), P1-15/16/17
(on-mode suppresses every domain router)**. Plus P1-2 (effective-query seam), P1-11 (no live client
constructed), P1-12 (outline→ev_ids handoff), P1-14 (validator adapter). Run:
`python -m pytest tests/polaris_graph/planning/ -q -p no:cacheprovider` → all green; then a provenance/
generator regression subset to confirm OFF byte-identity didn't break existing generator tests.
