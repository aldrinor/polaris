HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
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

# Codex BRIEF gate iter 4 — I-meta-005 Phase 1 (#985): Research planner + question-shaped outline

ITER-1 = REQUEST_CHANGES (5 P1, 4 P2). This rewrite addresses each. Parent plan #982 rows 47/57/78.
Phase 1 closes gaps #1 (decomposition), #2 (planning), #8 (report structure), #10 (decision seed).

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)
- **NO per-domain allowlist / `if domain ==` router / clinical literal in CODE on the on-path.** Field-
  agnostic; the question's content drives faceting + section choice.
- **OFF byte-identical via a TRUE dual path.** `PG_USE_RESEARCH_PLANNER` default off. Off = the existing
  `query_decomposer.decompose_question` + `_ALLOWED_SECTIONS` prompt/parser/fallback/dataclass, byte-for-
  byte (NOT a literal replacement of the module-level list — the legacy code path is retained and selected
  when off). Shadow build; live flip is a later operator-gated Gate-A step.
- **BUILD + SMOKE are spend-free.** The planner's one Writer call is an injected callable; smoke installs a
  fake AND asserts NO `OpenRouterClient` / live httpx client is constructed.
- **Keep gap #19 AND extend it.** Preserve the existing scope pre-registration + SHA; ADDITIONALLY
  pre-register + SHA-pin the new `ResearchPlan` before retrieval.

## 1. THE PROBLEM (grounded in the LIVE path — iter-1 P1 fix)
- **Live decomposition** is `retrieval/query_decomposer.py:108` `decompose_question` (pure, no-LLM, clause-
  split), called at `run_honest_sweep_r3.py:1677` gated `PG_SWEEP_QUERY_DECOMPOSE` (default ON), feeding
  `build_amplified_query_list`. (`decomposer.py:71` is TEST-ONLY — NOT the live path; iter-1 mistarget.)
  Clause-splitting a 40-70-word question yields a handful of keyword sub-queries, never a planned 20-40.
- **Clinical-only PICO**: `nodes/scope_gate.py:258` `extract_pico_heuristic` + `:231` `_DRUG_NAME_RE`. A
  housing/physics/trade question gets no usable frame. (`_DRUG_NAME_RE` is also imported by
  `completeness_checker.py:175` and `contradiction_detector.py:240,270` — it must STAY in scope_gate.)
- **Clinical section literals**: `multi_section_generator.py:59-68` `_ALLOWED_SECTIONS` (8 clinical),
  baked into the import-time outline prompt (`:259-261`) + fallback (`:450-452` `[Efficacy,Safety,
  Comparative]`). Worse, `title` is a CONTROL-FLOW key: M-44 clinical-title check (`:2618`), M-47 exact
  `"mechanism"` (`:4260`), and contract/enrichment matching key by `title`. So a non-clinical question gets
  clinical headings AND clinical routing — gap #8.

## 2. THE BUILD (behind PG_USE_RESEARCH_PLANNER; true dual path)

### 2.1 NEW `src/polaris_graph/planning/research_planner.py`
- `ResearchFrame` dataclass (generalized PICO, field-invariant): `entities`, `relations`, `metrics`,
  `comparators`, `constraints`, `claim_type` ∈ {empirical, policy-comparison, forecast, mechanism,
  descriptive}. No clinical fields.
- `plan_research(question, *, planner_llm) -> ResearchPlan` makes ONE Writer call emitting JSON: frame +
  faceted sub-queries + a section outline (each = an archetype TAG + a question-specific title + a
  per-section evidence target). `planner_llm: Callable[[str], str]` injected (fake in tests; production
  passes the Writer via the existing `openrouter_client`). Strict JSON parse; malformed → **raise**
  (LAW II), NO silent fallback to the clause-splitter.
- **Sub-query count (honest, iter-1 P2 fix):** UPPER bound 40 (merge/truncate deterministically if >40).
  LOWER bound is a **fail-loud retry**, not deterministic padding: if <`MIN_SUBQUERIES` (e.g. 12), retry
  the planner once asking for more facets; if still short for a genuinely narrow question, ACCEPT the
  smaller honest count + log (do NOT fabricate). The "20-40" EXIT target is for the broad golden/probe Qs;
  a narrow question may legitimately have fewer.
- **Persist + SHA-pin (iter-1 P1 #4; canonical, iter-3 P2):** serialize the `ResearchPlan` (frame +
  sub-queries + outline + evidence targets) as **canonical JSON** (`sort_keys=True`, fixed separators) to a
  run artifact BEFORE retrieval, compute `sha256` of those canonical bytes, and record `{plan_path,
  plan_sha256}` in the run `manifest`. The gap-#19 pre-registration now covers the plan — the audit trail
  proves the exact plan was declared before running (not merely "an artifact exists somewhere").

### 2.2 `nodes/scope_gate.py` — ADDITIVE, no removals (iter-1 P1 #3 fix)
- ADD a field-agnostic frame extractor for the on-path. **KEEP** `extract_pico_heuristic` AND
  `_DRUG_NAME_RE` exactly where they are (off-path + the existing clinical importers
  `completeness_checker.py:175`, `contradiction_detector.py:240,270` continue to import them unchanged).
  The new planner simply does not use the clinical regex. KEEP the scope pre-registration + SHA (gap #19).

### 2.3 `generator/multi_section_generator.py` — dual path + archetype as control-flow key
- ADD `_SECTION_ARCHETYPES` (~12 field-invariant tags: Background, Mechanism, Quantitative-Comparison,
  Cost-Economics, Risk, Jurisdiction, Stakeholders, Scenarios, Decision, Uncertainty, Methodology,
  Limitations). ADD `SectionPlan.archetype: str` (additive; default "" so off-mode is unchanged).
- **Dual path (iter-1 P1 #2):** when `PG_USE_RESEARCH_PLANNER` off, the legacy `_ALLOWED_SECTIONS` prompt
  (`:259-261`), parser (`:363`), fallback (`:450-452`), and title semantics run BYTE-IDENTICAL. When on, a
  separate archetype outline prompt asks for a question-specific title + archetype tag; the parser
  validates the TAG; fallback is archetype-driven (Background + Quantitative-Comparison + Decision).
- **Route on archetype, not title, in on-mode (iter-1 P1 #2):** M-44 (`:2618`), M-47 (`:4260`), and
  contract/enrichment title-matching consult `SectionPlan.archetype` (e.g. M-47 `archetype ==
  "Mechanism"`) in on-mode; off-mode keeps title-keyed behavior untouched. This prevents archetype mode
  from breaking clinical audit logic AND prevents leakage into off mode.
- Clinical prompt rules → `config/section_prompts/clinical.yaml` as ADVISORY PROMPT-TEXT only (extra
  writing guidance appended to the section prompt), NOT a control branch (iter-3 P2). The archetype outline
  prompt, parser, tag-validation, and fallback are byte-identical regardless of which prompt-text file is
  appended; selecting clinical.yaml does NOT change routing, archetypes, or section structure — it only
  enriches prose guidance when `frame.claim_type`/`entities` read clinical. No `if domain ==` branch.

### 2.4 Query wiring — ON-mode is planner-only; to the EFFECTIVE-QUERY seam (iter-2 P1 #2 + iter-3 P1 #2)
- **ON-mode is the ONLY non-anchor query source = the planner (iter-3 P1 #2).** Today the sweep also runs
  domain-keyed expanders: `expand_regulatory_queries` (M-28) + `expand_primary_trial_queries` (M-35), both
  keyed on `q["domain"]` + `load_scope_template(q["domain"])` (`run_honest_sweep_r3.py:1635-1648`), plus
  `expand_primary_trial_dois` (I-bug-776), and per-slug hand-authored `q["amplified"]`; all four feed
  `build_amplified_query_list(hand_authored, decomposed, regulatory, trial)` (`:1687`). These are the exact
  CLINICAL/domain-keyed machinery the field-agnostic re-architecture replaces. So under
  `PG_USE_RESEARCH_PLANNER` ON: the domain-keyed expanders are **NOT invoked**; the amplified list is fed
  `decomposed=plan.sub_queries`, `regulatory=[]`, `trial=[]`, `hand_authored=[]` (the planner's 20-40
  facets ARE the regulatory/primary-evidence expansion, field-agnostically). OFF: all legacy expanders run
  byte-identically.
- **Validator adapter (iter-3 P1 #1).** `validate_amplified_queries`'s `_build_anchor_tokens`
  (`scope_query_validator.py:85`) reads only clinical PICO fields (`research_question`, `population`,
  `intervention`, `comparator`, `outcome`). The new `ResearchFrame` (entities/relations/metrics/
  comparators/constraints) won't validate through that. Fix: (a) ADD `ResearchFrame.to_anchor_protocol()`
  producing a dict with `research_question` + the frame's tokens, AND (b) extend `_build_anchor_tokens`
  ADDITIVELY to also merge `entities`/`relations`/`metrics`/`comparators`/`constraints` when present (it
  already "skips missing fields gracefully", so clinical PICO protocols are unaffected = OFF byte-
  identical). Then planner sub-queries validate against the frame's OWN tokens.
- **The planner sub-queries must survive to the actual search calls.** `run_live_retrieval`
  (`live_retriever.py:1675`) → `validate_amplified_queries(... protocol ...)` → `effective_queries`
  (`:1720`) → search loop (`:1757`) → `_serper_search`/`_s2_bulk_search` (`:144`,`:187`). Acceptance
  asserts planner sub-queries reach the `effective_queries`/search seam (using the frame-derived protocol),
  NOT merely `build_amplified_query_list`.
- **Runtime fanout note (corrected, iter-2 P2):** `PG_SWEEP_FETCH_CAP` limits FETCHED URLs, NOT the number
  of Serper/S2 query CALLS. 20-40 planner sub-queries → up to ~20-40 Serper + S2 calls per round vs today's
  handful — a real per-run API-call increase (governed later by Phase-4 saturation, not Phase 1). Phase 1
  does not raise the fetch cap; build + smoke remain spend-free (no client constructed).

### 2.5 Outline handoff — pinned plan → post-retrieval SectionPlan.ev_ids (iter-2 P1 #1 fix)
The pre-retrieval `ResearchPlan` outline has archetype + question-specific title + evidence target but NO
evidence IDs (no evidence exists yet). The live generator's `_call_outline` (`:3685`) plans sections FROM
the retrieved `evidence` and assigns `SectionPlan.ev_ids` (`_parse_outline:393`). Bridge (on-mode):
`_call_outline` is CONSTRAINED by the pinned plan — the section STRUCTURE (titles + archetype tags + count)
is fixed by `ResearchPlan.outline`; the outline step's job in on-mode is to ASSIGN retrieved evidence rows
to those pre-declared sections (populate `ev_ids`), not to invent new clinical sections. Off-mode:
`_call_outline` runs exactly as today (`_ALLOWED_SECTIONS`-driven, evidence-first). The deterministic
fallback (`:436`), M-44 primary injection (`:3012`), and regen plans (`:4183`,`:4329`) MUST preserve the
`archetype` field when they copy/rebuild a `SectionPlan` (iter-2 P2). Acceptance: in on-mode the final
`multi.outline`/manifest sections ARE the planner's question-specific titles + archetype tags.

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4)
`tests/polaris_graph/planning/test_research_planner_phase1.py` + section-archetype + wiring tests:
- **P1-1 OFF byte-identity:** off → `decompose_question` output AND the section outline/parser/fallback are
  byte-identical to pre-Phase-1 on the clinical fixture (pin exact outputs).
- **P1-2 LIVE-PATH wiring to the EFFECTIVE-QUERY seam:** with on-flag + fake planner + a stub
  `_serper_search`/`_s2_bulk_search` (capture-only, no network), assert the planner sub-queries actually
  REACH the search calls — i.e. they survive `validate_amplified_queries` into `effective_queries`
  (`live_retriever.py:1720`) and appear at `_serper_search`/`_s2_bulk_search`, NOT merely in
  `build_amplified_query_list`. Off-flag: the captured queries are `decompose_question`'s, unchanged.
- **P1-3 frame + sub-queries (5 golden):** fake planner per golden Q → valid frame + 20-40 sub-queries +
  non-empty archetype outline.
- **P1-4 off-domain (the field-agnostic proof):** physics, ag-policy, JP-pharma-reg fixtures → usable
  frame + sub-queries, AND **zero clinical section labels/tags** (no Efficacy/Safety/Dose Response/
  Population Subgroups title OR archetype) on physics + ag-policy.
- **P1-5 archetype routing:** M-47 mechanism logic fires on `archetype == "Mechanism"` with a question-
  specific title (e.g. "How carbon pricing changes investment"); off-mode title routing unchanged.
- **P1-6 fail-loud:** malformed planner JSON → `plan_research` raises (no clause-splitter fallback).
- **P1-7 honest count:** fake returning 60 → ≤40 by merge/truncate; fake returning 5 → retry once, then
  accept honest small count + log (NO deterministic padding to 20).
- **P1-8 gap-19 plan pin (canonical):** the `ResearchPlan` is serialized as canonical JSON, sha256-pinned,
  and `{plan_path, plan_sha256}` recorded in the manifest BEFORE retrieval; re-serializing the same plan
  reproduces the identical sha256; the existing scope pre-registration SHA still matches.
- **P1-14 validator adapter (iter-3 P1 #1):** a `ResearchFrame` for a non-clinical question →
  `to_anchor_protocol()` → `validate_amplified_queries(planner_subqueries, protocol)` KEEPS the on-scope
  planner sub-queries (they validate against the frame's entities/metrics/comparators tokens), and a
  genuinely off-scope query is dropped. A clinical PICO protocol still validates byte-identically (additive
  `_build_anchor_tokens` extension does not change PICO behavior).
- **P1-15 on-mode suppresses legacy domain expanders (iter-3 P1 #2):** with on-flag + fake planner +
  capture stubs, NO regulatory (M-28) / primary-trial (M-35) / trial-DOI / per-slug hand-authored query
  reaches `effective_queries` — only planner sub-queries + the anchor. Off-flag: the legacy expanders run
  and their queries appear, unchanged.
- **P1-9 _DRUG_NAME_RE compat:** `completeness_checker` + `contradiction_detector` still import + use
  `_DRUG_NAME_RE` from `scope_gate` (no breakage).
- **P1-10 no-clinical-literal code guard (ON-PATH scoped, iter-2 P2):** a grep-style test asserts the
  on-mode planner/archetype code contains no clinical title/drug literals as control values (Phase-0a-style
  zero-literal sweep). The RETAINED legacy off-path block (`_ALLOWED_SECTIONS` + clinical outline prompt +
  `extract_pico_heuristic` + `_DRUG_NAME_RE`) is explicitly whitelisted — it must stay clinical for OFF
  byte-identity. The guard fails only on clinical literals in the NEW on-mode paths.
- **P1-11 spend-free guard:** smoke asserts no `OpenRouterClient` / live httpx client is constructed.
- **P1-12 outline handoff (iter-2 P1 #1):** on-mode, with a fake planner outline (e.g. archetype Decision,
  title "Which carbon-pricing path minimizes cost") + a small retrieved evidence pool, the final
  `multi.outline`/manifest sections ARE the planner's titles + archetype tags, and each section's `ev_ids`
  are assigned from the retrieved evidence (not invented clinical sections). Off-mode: `_call_outline` is
  evidence-first as today.
- **P1-13 archetype preserved through copy/rebuild (iter-2 P2):** a `SectionPlan` carrying an archetype,
  passed through `_build_deterministic_fallback_outline` / `_m44_inject_primaries_into_outline` (`:3012`) /
  the regen path (`:4183`,`:4329`), retains its `archetype` field (no drop to "" that would re-leak title
  routing).

## 4. EXIT CRITERIA (issue #985)
On the 5 golden DRB-EN Qs + 3 off-domain probes: a question-shaped archetype outline + faceted sub-queries
(20-40 for the broad Qs; honest-smaller allowed for a genuinely narrow Q, never padded); **zero clinical
section labels/tags on a non-clinical question**; **planner sub-queries proven to reach the
`effective_queries`/search seam** (not just the pre-validator list); **the final `multi.outline` sections
are the planner's titles+archetypes with evidence assigned post-retrieval**; OFF byte-identical;
ResearchPlan SHA-pinned before retrieval; all smoke green; no live spend in build/smoke.

## 5. WHAT I HAVE ALSO CHECKED AND THEY ARE CLEAN
- `decomposer.py` is test-only — left as-is; NOT the wiring target.
- `_DRUG_NAME_RE` importers (`completeness_checker.py:175`, `contradiction_detector.py:240,270`) — keep the
  regex in scope_gate; no move, compat test added (P1-9).
- M-44 (`:2618`) / M-47 (`:4260`) — on-mode routes on `archetype`; off-mode title routing untouched.
- `config/scope_templates/*.yaml` — static clinical section logic; off-path only + clinical fixture.

## 6. REVIEW QUESTIONS FOR CODEX
1. Is the dual-path (legacy `_ALLOWED_SECTIONS` retained for off; archetypes for on) the right cut for true
   OFF byte-identity given the import-time prompt baking?
2. Is routing M-44/M-47/contract-matching on `archetype` (on-mode) vs `title` (off-mode) sufficient to keep
   clinical audit logic intact AND prevent on-mode leakage?
3. Is the honest count policy (upper-bound truncate + lower-bound retry-then-accept, no padding) right, and
   is "20-40 for broad / fewer-allowed-for-narrow" the correct EXIT phrasing?
4. Is SHA-pinning the ResearchPlan before retrieval the correct extension of gap #19, and is P1-8 the right
   acceptance for it?
5. Scope: is frame+planner+sections+live-wiring the right Phase-1 boundary, with per-section evidence
   targets PERSISTED now but ENFORCED only at Phase 3's plan-sufficiency gate?

APPROVE iff the acceptance criteria are correct, the LIVE-path wiring + dual-path OFF byte-identity +
archetype-routing + _DRUG_NAME_RE compat + plan SHA-pin + spend-free guard all hold. This brief is the build
contract.
