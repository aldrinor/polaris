HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
Front-load ALL real findings. Reserve P0/P1 for real execution risks; P2/P3 for the rest.

Output the §8.3.9 YAML verdict FIRST:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# Codex BRIEF gate — I-meta-005 Phase 3 (#987): Plan-sufficiency gate (the money-trap fix)

Reviewing ACCEPTANCE-CRITERIA correctness. Parent plan #982 row 51. Phase 3 closes the "trap": today the
adequacy gate is domain-keyed + AGGREGATE-count only, so a broad-but-shallow corpus PASSES, BILLS the
generator, then gaps 8/18 gut the report. Phase 3 makes adequacy = "does the corpus cover EVERY planned
sub-question to its evidence target at the authority floor?" — held at EXPAND/abort BEFORE a generator token
is billed.

## 0. HARD CONSTRAINTS (operator-locked — NOT Codex-consultable; do not offer the relaxed option)
- **NO per-domain threshold dict / `if domain ==` / clinical literal as a control value on the on-path.**
  Sufficiency is computed from the PLAN (Phase 1 `ResearchPlan`: sub_queries + per-section evidence_target)
  × AUTHORITY (Phase 0a `score_source_authority`), never a domain.
- **OFF byte-identical.** Gated on the existing `PG_USE_RESEARCH_PLANNER` (default off). Off = the current
  `assess_corpus_adequacy` domain-keyed `_DEFAULT_DOMAIN_THRESHOLDS` gate, byte-for-byte. On = the new
  plan-sufficiency gate.
- **MONEY: the gate runs BEFORE the generator is billed.** A broad/shallow corpus → EXPAND or
  abort_corpus_inadequate with ZERO generator tokens spent. (This is the entire point of Phase 3.)
- **BUILD + SMOKE spend-free.** No live LLM/retrieval; sufficiency is a pure function over the already-
  retrieved corpus + the pinned plan + the authority scores. Smoke asserts no client constructed.

## 1. THE PROBLEM (grounded in running code)
- `nodes/corpus_adequacy_gate.py:71-136` `_DEFAULT_DOMAIN_THRESHOLDS` — 7 hand-tuned per-DOMAIN threshold
  sets (clinical/policy/tech/due_diligence/ai_sovereignty/canada_us/workforce); `_get_thresholds(domain,…)`
  (`:139`) keys on `domain`; `assess_corpus_adequacy(…, domain=…)` (`:167`) checks only AGGREGATE tier
  counts (min_total_sources, min_t1_count, tier fractions) — NOT per-sub-question coverage. Called at
  `run_honest_sweep_r3.py:2001` (+ `:2152` staged + `:2249` deepener) BEFORE `generate_multi_section_report`
  (`:54`). So a corpus with 12 sources none of which cover sub-question #7 PASSES the aggregate count and
  bills the generator.
- Phase 1 `ResearchPlan` (`planning/research_planner.py:243`) carries `sub_queries: list[str]` (`:250`) +
  `outline: list[SectionOutlineItem]` each with `evidence_target: int` (`:228-239`) — the per-section
  done-definition. Phase 0a `score_source_authority` (`authority/authority_model.py:84`) →
  `authority_confidence` (`:198`) is the per-source authority floor signal.

## 2. THE BUILD (behind PG_USE_RESEARCH_PLANNER)

### 2.1 NEW `src/polaris_graph/adequacy/plan_sufficiency_gate.py`
- `assess_plan_sufficiency(*, plan, corpus_rows, authority_floor, round_index, max_rounds) ->
  PlanSufficiencyReport`. Pure, no-network, no-LLM. For EACH planned coverage UNIT (see 2.2 for the unit
  choice) count the corpus rows that (a) are RELEVANT to that unit AND (b) meet the AUTHORITY floor; a unit
  is SUFFICIENT iff covered_count ≥ its evidence_target, else UNDER_COVERED. Overall verdict:
  - **PROCEED** — every unit SUFFICIENT → the generator may be billed.
  - **EXPAND** — ≥1 unit UNDER_COVERED AND `round_index < max_rounds` → return the under-covered units (+
    their gap) so Phase 4 saturation can target new sub-queries; NO generator bill this round.
  - **ABORT** — ≥1 unit UNDER_COVERED AND rounds/budget exhausted → status `abort_corpus_inadequate` with
    a per-unit shortfall report; NO generator bill, ever.
- `PlanSufficiencyReport`: `verdict` (PROCEED/EXPAND/ABORT) + `per_unit` (unit id, evidence_target,
  covered_count, sufficient: bool, relevant-but-below-authority count) + `under_covered_units` (for EXPAND).

### 2.2 THE COVERAGE UNIT + RELEVANCE (the hard design point — Codex please probe)
- **Unit = the section outline item** (each `SectionOutlineItem` has an `evidence_target`). (Sub-queries are
  the discovery facets; the SECTION is the done-definition unit per plan row 47. Confirm this is the right
  unit, vs per-sub-query.)
- **Relevance signal (field-agnostic, no LLM, no domain):** a corpus row is RELEVANT to a section iff its
  retrieval-provenance maps to that section OR its content-word overlap with the section's
  title/focus/its sub-queries clears a floor (reuse the existing `_content_words` overlap primitive — the
  same one the verifier uses; NO new heuristic). Each retrieved row already carries WHICH sub-query/need
  surfaced it (Phase 2 provenance); the plan maps sub-queries→sections at planning time. So coverage is
  computed from real provenance + a deterministic overlap floor, not an LLM relevance call.
- **Authority floor:** a row counts toward coverage iff `score_source_authority(...).authority_confidence ≥
  authority_floor` (env `PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR`, a single global float — NOT a per-domain
  dict). A relevant-but-below-floor row is counted separately (reported, not credited).

### 2.3 Wiring into the sweep (the money gate)
- `run_honest_sweep_r3.py`: on-mode, BEFORE `generate_multi_section_report`, call
  `assess_plan_sufficiency(...)`:
  - PROCEED → continue to the generator (as today).
  - EXPAND → (Phase 3 scope) record status + the under-covered units; for THIS phase, EXPAND with no
    further retrieval loop available behaves as a documented hold → `abort_corpus_inadequate` (the actual
    saturation EXPANSION loop is Phase 4). So Phase 3's guarantee is: a shallow corpus NEVER bills the
    generator; whether it EXPANDs (Phase 4) or ABORTs (now) it spends zero generator tokens.
  - ABORT → status `abort_corpus_inadequate`, zero generator tokens.
  - Off-mode: the legacy `assess_corpus_adequacy` domain-keyed gate runs unchanged.
- The on-mode path must run the sufficiency gate at the SAME pre-generator point(s) the legacy gate runs
  (`:2001` + the staged `:2152` + deepener `:2249`) so no pre-generator path is left ungated on-mode.

## 3. OFFLINE SMOKE (heavy, spend-free, serialized §8.4) — `tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py`
- **P3-1 OFF byte-identity:** off → `assess_corpus_adequacy` domain-keyed verdict byte-identical on the
  clinical/policy fixtures (pin the report).
- **P3-2 PROCEED:** a plan with 3 sections (evidence_target 2 each) + a corpus where each section has ≥2
  relevant above-floor rows → verdict PROCEED.
- **P3-3 THE TRAP (housing):** a broad housing plan (6 sections) + a BROAD-BUT-SHALLOW corpus (lots of rows,
  but section #5 has 0 relevant above-floor rows) → verdict EXPAND/ABORT, and assert ZERO generator call
  (spy on `generate_multi_section_report` — it must NOT be invoked). This is the money-trap EXIT.
- **P3-4 THE TRAP (sovereignty):** same shape for an ai-sovereignty plan → held before billing.
- **P3-5 authority floor bites:** a section with 3 relevant rows ALL below the authority floor → UNDER_
  COVERED (relevant-but-below-floor counted separately, not credited).
- **P3-6 EXPAND vs ABORT:** under-covered + round_index < max_rounds → EXPAND (returns the under-covered
  units); under-covered + rounds exhausted → ABORT.
- **P3-7 field-agnostic guard:** a grep-style test asserts the on-path sufficiency code consults NO
  `_DEFAULT_DOMAIN_THRESHOLDS` / `if domain ==` / domain key; the legacy domain dict is whitelisted off-path.
- **P3-8 zero generator bill on hold:** the strongest assertion — across P3-3/P3-4/P3-6-ABORT, the generator
  (and any LLM client) is never constructed/called when the verdict is EXPAND or ABORT.
- Plus a regression subset confirming OFF byte-identity didn't break existing corpus_adequacy tests.

## 4. EXIT CRITERIA (issue #987)
On-mode, a broad/shallow corpus is held at EXPAND/abort BEFORE a generator token is billed; the housing +
sovereignty trap cases replay with ZERO generator bill; sufficiency = per-section evidence_target × authority
floor, computed from the plan + authority (no domain dict); OFF byte-identical; all smoke green; spend-free.

## 5. WHAT I HAVE ALSO CHECKED
- `assess_corpus_adequacy` call sites: `:2001` (main), `:2152` (staged), `:2249` (deepener) — all
  pre-generator; on-mode must gate all three.
- Phase 1 `SectionOutlineItem.evidence_target` is the done-definition; Phase 2 retrieval provenance maps
  rows→sub-queries→sections.
- Phase 0a `authority_confidence` is the per-source floor signal (a single global float threshold, NOT a
  per-domain dict).

## 6. REVIEW QUESTIONS FOR CODEX
1. Is the coverage UNIT = section (with its evidence_target) the right grain, vs per-sub-query? (The plan's
   done-definition is per-section; but a section may span several sub-questions.)
2. Is the relevance signal (retrieval-provenance + deterministic content-word overlap floor, NO LLM) sound
   and genuinely field-agnostic, or does it risk crediting an off-topic row / missing an on-topic one?
3. Is "EXPAND collapses to ABORT in Phase 3 (saturation loop is Phase 4)" the right scope boundary, and is
   the zero-generator-bill guarantee airtight at all 3 pre-generator call sites?
4. Is a single global authority floor (env) correct, vs the plan declaring a per-section floor?
5. Is gating on PG_USE_RESEARCH_PLANNER right (the gate needs the ResearchPlan's evidence_targets, which
   only exist on-mode)?

APPROVE iff the acceptance criteria are correct, the plan×authority (no-domain-dict) sufficiency is sound,
the zero-generator-bill-before-sufficiency guarantee holds, and OFF stays byte-identical. This is the build
contract.
