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

# Codex BRIEF gate iter 5 — I-meta-005 Phase 3 (#987): Plan-sufficiency gate (the money-trap fix)

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
  PlanSufficiencyReport`. Pure, no-network, no-LLM, over rows that ALREADY carry the §2.3a authority sidecar +
  `query_origin`. For EACH section (its `evidence_target` + `sub_query_indices`) count the corpus rows that
  (a) are RELEVANT to that section (provenance-first, §2.2) AND (b) have `authority_score ≥ authority_floor`.
  A section is SUFFICIENT iff **BOTH (iter-2 P1 #1 — facet-level, not section-aggregate):**
    (i) total above-floor covered_count ≥ `evidence_target`, AND
    (ii) EVERY mapped `sub_query_index` has ≥ `PG_PLAN_SUFFICIENCY_MIN_PER_FACET` above-floor relevant rows
        (default 1) — so a section mapped to sub-queries [4,5,6] CANNOT pass on rows from sub-query 4 alone
        while 5 and 6 are empty. This is the actual "cover EVERY planned sub-question" guarantee; section
        total alone would reopen the trap at a finer grain.
  Else UNDER_COVERED (with the specific empty/under facets named). Overall verdict:
  - **PROCEED** — every unit SUFFICIENT → the generator may be billed.
  - **EXPAND** — ≥1 unit UNDER_COVERED AND `round_index < max_rounds` → return the under-covered units (+
    their gap) so Phase 4 saturation can target new sub-queries; NO generator bill this round.
  - **ABORT** — ≥1 unit UNDER_COVERED AND rounds/budget exhausted → status `abort_corpus_inadequate` with
    a per-unit shortfall report; NO generator bill, ever.
- `PlanSufficiencyReport`: `verdict` (PROCEED/EXPAND/ABORT) + `per_unit` (unit id, evidence_target,
  covered_count, sufficient: bool, relevant-but-below-authority count) + `under_covered_units` (for EXPAND).

### 2.2 THE COVERAGE UNIT + RELEVANCE (iter-1 P1 #2 — provenance-first, executable)
- **Unit = the section outline item.** Each `SectionOutlineItem` has an `evidence_target`. But today it has
  ONLY `archetype`/`title`/`evidence_target` (`research_planner.py:227`) — NO facet mapping, so title-overlap
  alone could credit OFF-facet rows to a section (the partial money-trap Codex flagged). FIX: ADD
  `sub_query_indices: list[int]` to `SectionOutlineItem` (additive, default `[]`). The planner declares, per
  section, WHICH of the 20-40 `sub_queries` (by index) make that section complete. The planner prompt emits it.
  **FAIL-CLOSED post-finalization validation (iter-3 P1):** `plan_research()` parses the plan THEN mutates
  `plan.sub_queries` via `_merge_truncate_subqueries` (`research_planner.py:596`), so an index valid at parse
  time can go stale. So AFTER the sub_queries list is FINAL (post-truncation/retry-winner selection), the
  builder re-validates EVERY outline section: each section MUST have ≥1 sub_query_index, ALL indices in-range
  of the FINAL `sub_queries`, AND `evidence_target ≥ 1`, AND (iter-4 P1 #1 — WHOLE-PLAN coverage) the UNION
  of all sections' `sub_query_indices` MUST equal `set(range(len(final sub_queries)))` — EVERY planned
  sub-query is mapped to some section, so no orphaned facet escapes the gate (today `_parse_outline` allows `evidence_target=0` at
  `:437-445` → a vacuous section; planner mode forbids it). Any empty/stale/invalid mapping → raise
  `MalformedPlanError` BEFORE retrieval/generation (fail closed, zero spend). A `[]` default is fine ONLY
  off-mode; on-mode a section with `[]` is malformed.
- **Relevance = PROVENANCE-FIRST (iter-1 P1 #2):** each evidence row already persists `query_origin` (the
  sub-query text that surfaced it — `live_retriever.py:2226`). A row is RELEVANT to a section iff its
  `query_origin` matches (normalized-equality) one of the sub-query texts at that section's
  `sub_query_indices`. This is the real retrieval provenance, NOT a heuristic.
  - **Fallback (tightly specified, iter-3 P2):** a row is FALLBACK-ELIGIBLE iff its `query_origin` is EMPTY
    OR is one of the explicit NON-QUERY SENTINEL origins that legitimately carry no sub-query text:
    `{primary_trial_doi_seed, need_type_backend, domain_backend}` (`live_retriever.py:1774,1849,1885`) —
    these lanes (seed DOIs, the Phase-2 need-type registry, legacy domain backend) surface AUTHORITATIVE
    evidence with no originating sub-query, so they must be creditable, not silently abort an otherwise-
    sufficient corpus. For a fallback-eligible row, use `_content_words` overlap floored against the
    section's OWN sub-query texts (at `sub_query_indices`), NOT just the title. A row whose `query_origin`
    is a REAL sub-query text that doesn't match the section is NOT relevant to it (no title-overlap rescue) —
    real-query provenance is authoritative; only the sentinel/empty lanes use the fallback.
- **Authority floor (iter-1 P1 #1 — numeric, persisted):** the numeric authority strength is
  `AuthorityResult.authority_score: float [0,1]` (`source_class.py:75`), NOT the `authority_confidence`
  HIGH/MEDIUM/LOW enum. A row counts toward coverage iff its `authority_score ≥
  PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR` (a single global float in [0,1], NOT a per-domain dict). BUT evidence
  rows do NOT persist any authority field today (`live_retriever.py:2222-2230` persists tier/source/
  query_origin only). So §2.3a ADDS the per-row authority sidecar the gate reads. A relevant-but-below-floor
  row is counted separately (reported, not credited).

### 2.3a Persist the per-row authority result (iter-1 P1 #1 + iter-2 P1 #2 — guaranteed in planner mode)
- At the on-mode evidence-row build (`live_retriever.py:2222-2230`), ADD additive fields
  `authority_score: float` and `authority_confidence: str` to each row.
- **CRITICAL (iter-2 P1 #2): the sidecar is computed DIRECTLY via `score_source_authority(...)` whenever
  `PG_USE_RESEARCH_PLANNER` is ON, INDEPENDENT of the legacy `PG_USE_AUTHORITY_MODEL` tier switch.** Today the
  tier_classifier only computes authority when `PG_USE_AUTHORITY_MODEL` is on (`tier_classifier.py:1099`); so
  planner mode must call the Phase-0a `score_source_authority` pure function ITSELF for the sidecar — else
  every row reads `authority_score=0.0` and the gate aborts every planner-mode corpus. If the authority
  computation genuinely cannot run (missing inputs), it returns an HONEST low score with
  `authority_confidence=LOW` (per the Phase-0a honest-confidence contract), NOT a silent 0.0 default — and
  the gate treats LOW-confidence-but-scored rows per the floor. Additive, default `0.0`/`""` → OFF rows
  unchanged (legacy gate ignores them; byte-identical). The gate is pure over rows that already carry the
  sidecar (written at retrieval time, not by the gate).
- **Canonical serialization (iter-2 P2):** `SectionOutlineItem.sub_query_indices` is ADDED to
  `to_canonical_dict()` (`research_planner.py:271`) + the SHA-pinned `research_plan.json`, so the sufficiency
  contract is reproducible from the pinned plan artifact (gap #19 audit trail).

### 2.2b Gate the BILLED evidence set + provenance-first assignment (iter-4 P1 #2 — the handoff)
The generator does NOT bill on the raw corpus — it bills on `evidence_for_gen`, the SELECTED subset from
`select_evidence_for_generation` (`run_honest_sweep_r3.py:2560`), assigned to sections ROUND-ROBIN
(`_assign_evidence_to_planned_outline`, `multi_section_generator.py:618` `ev_ids[i::n_sections]`) — NOT by
facet. So a full-corpus certification can PROCEED while the generator gets OFF-facet rows per section. Two
coupled fixes make the certification carry through to what's billed:
- **The sufficiency gate assesses the FINAL `evidence_for_gen` (the billed set), NOT `retrieval.evidence_rows`.**
  The gate runs AFTER `select_evidence_for_generation` (which is cheap — relevance/authority ranking, NO
  generator bill) and BEFORE `generate_multi_section_report`. So it certifies exactly the rows that will be
  billed.
- **On-mode `_assign_evidence_to_planned_outline` becomes PROVENANCE-FIRST, not round-robin:** each row is
  assigned to the section(s) whose `sub_query_indices` its `query_origin` matches (sentinel/empty origins use
  the §2.2 content-word fallback). So each section's `ev_ids` = ITS credited rows. Off-mode: the round-robin
  path is unchanged (byte-identical). This guarantees the gate's per-section/per-facet PROCEED means the
  generator actually receives the credited rows for each section.

### 2.3 Wiring into the sweep (the money gate)
- `run_honest_sweep_r3.py`: on-mode, AFTER `select_evidence_for_generation` and BEFORE
  `generate_multi_section_report`, call `assess_plan_sufficiency(...)` ON `evidence_for_gen`:
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
- **P3-5 authority floor bites (numeric):** a section with 3 relevant rows ALL with `authority_score` below
  `PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR` → UNDER_COVERED (relevant-but-below-floor counted separately).
- **P3-5b provenance-first mapping:** a row whose `query_origin` matches a section's `sub_query_indices`
  counts toward THAT section; a row with a non-empty `query_origin` that matches a DIFFERENT section's
  sub-queries does NOT count toward this section even if its title-words overlap (no off-facet credit). An
  empty-`query_origin` row uses the content-word fallback against the section's sub-query texts.
- **P3-5c authority sidecar persisted:** the on-mode evidence row built by live_retriever carries
  `authority_score` (float) + `authority_confidence` (str); off-mode rows are unchanged (no sidecar).
- **P3-6 EXPAND vs ABORT:** under-covered + round_index < max_rounds → EXPAND (returns the under-covered
  units); under-covered + rounds exhausted → ABORT.
- **P3-7 field-agnostic guard:** a grep-style test asserts the on-path sufficiency code consults NO
  `_DEFAULT_DOMAIN_THRESHOLDS` / `if domain ==` / domain key; the legacy domain dict is whitelisted off-path.
- **P3-8 zero GENERATOR bill on hold (iter-2 P2 scoped):** the strongest assertion — across P3-3/P3-4/
  P3-6-ABORT, the GENERATOR (`generate_multi_section_report`) + downstream evaluator LLM clients are NEVER
  constructed/called when the verdict is EXPAND or ABORT. (The pre-retrieval PLANNER is faked/injected in
  smoke per the spend-free rule; the assertion is scoped to the generator/downstream, not the planner.)
- **P3-9 facet-level (iter-2 P1 #1):** a section mapped to sub-queries [4,5,6] with 5 above-floor rows ALL
  from sub-query 4 → UNDER_COVERED (sub-queries 5,6 empty), even though total (5) ≥ evidence_target (e.g. 3).
  Proves section-total alone cannot hide an empty facet.
- **P3-10 authority in planner mode (iter-2 P1 #2):** with PG_USE_RESEARCH_PLANNER on + PG_USE_AUTHORITY_MODEL
  OFF, the evidence rows STILL carry a real numeric `authority_score` (computed directly), NOT 0.0.
- **P3-11 canonical pin (iter-2 P2):** `to_canonical_dict()` + `research_plan.json` include `sub_query_indices`;
  re-serializing reproduces the same SHA.
- **P3-12 fail-closed mapping (iter-3 P1):** a plan whose section has an EMPTY `sub_query_indices`, OR an
  out-of-range index after truncation, OR `evidence_target=0` on-mode → `plan_research` raises
  `MalformedPlanError` BEFORE any retrieval/generation (zero spend); off-mode a `[]` mapping is inert.
- **P3-13 sentinel fallback (iter-3 P2):** a `need_type_backend` (or `domain_backend`/`primary_trial_doi_seed`)
  row whose content overlaps a section's sub-query texts is CREDITED via the fallback (not falsely abort); a
  real-sub-query row that doesn't match the section is NOT credited to it.
- **P3-14 whole-plan facet union (iter-4 P1 #1):** a plan where sub-query #7 is mapped to NO section →
  `plan_research` raises `MalformedPlanError` (orphaned planned facet forbidden) before spend.
- **P3-15 gate the BILLED set + provenance assignment (iter-4 P1 #2):** the gate runs on `evidence_for_gen`
  (the selected billed set), and on-mode `_assign_evidence_to_planned_outline` assigns each section its
  `query_origin`-matched rows (NOT round-robin); a section certified SUFFICIENT actually receives its credited
  rows in the generator's `ev_ids`. Off-mode the round-robin assignment is byte-identical.
- Plus a regression subset confirming OFF byte-identity didn't break existing corpus_adequacy tests.

## 4. EXIT CRITERIA (issue #987)
On-mode, a broad/shallow corpus is held at EXPAND/abort BEFORE a generator token is billed; the housing +
sovereignty trap cases replay with ZERO generator bill; sufficiency = per-section evidence_target coverage (provenance-first row→section mapping via query_origin ×
`sub_query_indices`) × the NUMERIC authority_score floor; computed from the plan + the persisted per-row
authority sidecar (no domain dict); OFF byte-identical; all smoke green; spend-free.

## 5. WHAT I HAVE ALSO CHECKED
- `assess_corpus_adequacy` call sites: `:2001` (main), `:2152` (staged), `:2249` (deepener) — all
  pre-generator; on-mode must gate all three.
- Phase 1 `SectionOutlineItem.evidence_target` is the done-definition; Phase 2 retrieval provenance maps
  rows→sub-queries→sections.
- Phase 0a authority: the floor signal is the NUMERIC `AuthorityResult.authority_score` (float [0,1], a
  single global env threshold) — NOT the `authority_confidence` HIGH/MED/LOW enum (corrected iter-4 P2).

## 5b RESOLVED FROM ITER-1 (Codex answers folded in)
- Unit = section, with the plan now recording the section's facets via `sub_query_indices` (Codex: "section
  can be the reporting unit only if the plan records the facets/sub-queries that make that section complete").
- Relevance = provenance-first (query_origin × sub_query_indices), content-word overlap ONLY as the
  empty-provenance fallback, floored against the section's sub-query texts (Codex: "acceptable only with
  provenance-first mapping and a tightly specified overlap fallback").
- Authority = the NUMERIC `authority_score` (not the confidence enum), persisted per row by live_retriever.
- EXPAND→ABORT in Phase 3 + gate on PG_USE_RESEARCH_PLANNER: Codex confirmed both correct.

## 6. REVIEW QUESTIONS FOR CODEX (iter 2)
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
