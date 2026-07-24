# STAGE-0 LINEAGE SEAM v2 — reconciled Sol + Fable (both ghost-audited CLEAN)

Sol NO-GO'd v1 as incomplete; Fable GO-WITH-CHANGES. They converge: the harness is wired for DRB-II idx-56 on the
`drb_72_ai_labor` slug in ~9 seams; ALL must become lineage-aware or the run is split-brained and fail-louds
post-spend. This v2 is the union of both edit lists. Pure lineage/identity plumbing — NO content lever, NO ghost
(both confirmed). Default path (`drb_ii_idx`) stays byte-for-byte identical.

## Design (both agree)
- Selector `PG_BENCHMARK_QUESTION_LINEAGE`: read with an **in-process default** `drb_ii_idx` (do NOT write it to
  env; default serialized artifacts gain no key); `legacy_race_task` = the task-72 RACE lineage.
- **KEEP the forced `PG_BENCHMARK_OFFICIAL_QUESTION="1"` + its preflight required-flag tuple BYTE-IDENTICAL** (Sol
  insists; Fable concurs). In legacy mode "official" = the legacy canonical source, not DRB-II idx. So the existing
  forced-override machinery is REUSED; we only change what the canonical resolver RETURNS.
- Branch ONLY in the canonical resolver; every consumer already routes through it → default byte-identity is free.

## The ~9 seams (all must see the legacy question/contract on `legacy_race_task`; default unchanged)
1. **gate0_lineage resolver** (`gate0_lineage.py:99-134`): add `SLUG_TO_LEGACY_TASK={"drb_72_ai_labor":72}` +
   `DEFAULT_LEGACY_TASKS_PATH` (query.jsonl) + a fail-loud legacy loader; `canonical_question_for_slug(slug,
   tasks_path=…, *, lineage="drb_ii_idx", legacy_tasks_path=…)` → legacy resolves id=72 from query.jsonl. Forward
   `lineage` through `assert_launched_question_is_canonical`, `assert_no_split_brain`, `build_lineage_manifest`
   (`:137-225`); manifest records the lineage and must NOT label a legacy run `canonical_idx=56`. Registration
   fails for a legacy/slug pair with no legacy mapping (`:56-78`). Keep positional `(slug, tasks_path)` valid.
2. **run_gate_b override** (`run_gate_b.py:5645-5706`): default = current idx override. Legacy = **assert the raw
   registered SWEEP question equals the legacy canonical (query.jsonl id=72) and only then keep it** (Sol: never
   trust the registered string blindly — a future SWEEP edit must fail loud, not silently recreate the wrong
   question); attach a legacy-only lineage marker to the copied `q`.
3. **Preflight** (`run_gate_b.py:2064-2070` tuple + `:4794-4799` enforce): keep the official-question flag exactly;
   add ONLY an allowlisted selector-VALUE check in `preflight_full_capability` (`:4643-4661`) — reject unknown
   selector values before spend. Do NOT put the selector in the required-flags truthy tuple (unset is valid).
4. **Direct sweep GATE0 override** (`run_honest_sweep_r3.py:21906-21934` — corrects v1's stale `:19099`): must
   consult the same selector; else it re-forces idx-56 = split brain vs legacy Gate-B/scoring.
5. **Output-contract, 3 loaders** (Fable's critical catch): `load_task_output_contract` feeds pre-spend assert
   (`run_gate_b.py:4511-4548`), summary-table renderer headers (`run_honest_sweep_r3.py:18144-18165`), and
   post-render validity gate (`run_validity_gate.py:111-129,423-458`). idx-56's `intent_anchors ["generative ai"]`
   would FAIL-LOUD a legacy run AFTER full spend + inject the 5-column table. **Resolution: make
   `load_task_output_contract` lineage-aware; legacy → `None` (the existing documented no-op).** One gate covers all
   three consumers.
6. **corpus_snapshot** (`run_honest_sweep_r3.py:15818-15838`; `corpus_snapshot.py:90-126`): add a legacy-only
   lineage field; **resume rejects a mismatched stored lineage** (needed for the 3-draw frozen-corpus resume).
   Existing question-SHA guards `:9517-9537`, `:15910-15919` stay.
7. **Scorer** (`score_report_race.py:44-68`): legacy-selector-gated call to the lineage-aware `assert_no_split_brain`
   (read answered question + slug from the run snapshot/manifest) before writing scores; fail loud if the answered
   evidence is missing. Default scorer path unchanged.
8. **Question flows through** (verify single-brain, no second override): scope_gate protocol.research_question
   (`scope_gate.py:872-884,1131-1169`), retrieval seed (`run_honest_sweep_r3.py:9822-9877,10902-10920`), V30
   compile_frame + contract-plan question + generator (`:13858-13884,14252-14269,16012-16016`), H1
   (`:17713-17715,17853-17869`).
9. **V30/D8 per-query contract (the ONE judgment call — flag for diff-gate)** (`workforce.yaml:161-365`;
   `native_gate_b_inputs.py:283-301,943-960`): workforce.yaml was authored FOR idx-56, shapes the V30 outline/entity
   structure AND supplies the fail-closed Gate-B required-element COVERAGE denominator. task-72 and idx-56 are the
   SAME topic (AI labor restructuring), so keeping the workforce contract STRUCTURE is acceptable (the report still
   answers task-72 in prose, scored by RACE task-72). **The risk is only the fail-CLOSED coverage gate aborting a
   task-72 run.** **Resolution (Opus call, flag for both diff-gaters): for `legacy_race_task`, make the DRB-II
   required-element coverage gate REPORT-ONLY (non-fatal), since we score on RACE task-72, not the idx-56 coverage
   rubric.** No content change; a lineage-aware gate-severity change. If either diff-gater rejects this, fall back
   to authoring a task-72 per-query contract (larger) — but do not ship a run that can abort post-spend.

## TESTS (deterministic; ship-decision only)
- Default off-state GOLDEN identity over: env mutations, selected `q`, canonical-file opens (no query.jsonl read on
  default), protocol bytes, snapshot bytes, output-contract resolution, manifest — all byte-identical to HEAD.
- Legacy: answered-question sha == query.jsonl id=72 at every seam (launch, protocol, retrieval seed, compile_frame,
  contract plan, H1, snapshot, scorer pack); NO DRB-II gold read; output-contract = None; coverage gate non-fatal.
- Split-brain guard still FAILS LOUD on a deliberate packed/answered mismatch (raw AND sha256 equality).
- Unregistered-slug + legacy/slug-with-no-mapping FAIL-LOUD preserved.
- `git diff` clean on provenance_generator/strict_verify; GHOST_BAN grep clean (identity/lineage only).

## BUILD ORDER (seam-by-seam, then ONE both-model diff-gate over the whole diff)
(1) gate0_lineage resolver+registry+manifest → (2) run_gate_b override+preflight allowlist → (5) output-contract
lineage gate → (4) direct sweep override → (6) corpus_snapshot lineage → (7) scorer guard → (9) coverage-gate
severity → (8) verify flow single-brain via tests. Then both-model diff-gate + ghost-audit BEFORE the re-baseline.
