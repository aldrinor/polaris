# Stage-0 lineage seam — Sol diff-gate verdict

## Verdict

**NO-GO to commit and NO-GO to run the re-baseline.**

The default `drb_ii_idx` path is clean and the mapped task-72 legacy happy path is mostly
single-brained, but the implementation does not fully match the reconciled v2 design:

1. the direct-sweep legacy branch fails open for an explicitly registered no-gold benchmark slug
   with no legacy mapping;
2. the purported legacy “coverage report-only” change alters the wrong predicate (a
   RequiredEntityLedger implementation-error abort), not the native fixed-denominator
   required-element coverage decision;
3. raw-byte equality is not enforced/tested as required; the production comparisons use only a
   SHA over whitespace-normalized text, and a new test explicitly accepts raw drift;
4. the sweep caller does not enforce the snapshot lineage mismatch in the legacy-to-default
   direction (the question-SHA guard happens to catch task-72 because the two questions differ,
   but the required lineage invariant is incomplete);
5. the new tests do not behaviorally exercise all advertised seams or the scorer.

No generation or scoring spend should start until these are fixed and re-diff-gated.

## Per-item results

### 1. DEFAULT-PATH BYTE IDENTITY — PASS

Grounded code review:

- `scripts/dr_benchmark/gate0_lineage.py:215-244` keeps the positional
  `(slug, tasks_path)` call valid and selects the unchanged DRB-II loader on the default branch.
- `scripts/dr_benchmark/run_gate_b.py:5688` still force-assigns
  `PG_BENCHMARK_OFFICIAL_QUESTION="1"`.
- `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` still contains that flag exactly once at
  `scripts/dr_benchmark/run_gate_b.py:2064-2070`; the selector is not added to the tuple.
- The selector allowlist at `scripts/dr_benchmark/run_gate_b.py:4824-4842` is inert when unset and
  accepts explicit `drb_ii_idx`.
- The default Gate-B override remains the old canonical-idx branch at
  `scripts/dr_benchmark/run_gate_b.py:5742-5750`; it adds no lineage key.
- `scripts/dr_benchmark/run_validity_gate.py:128-144` loads the normal output contract for unset
  or `drb_ii_idx`.
- `scripts/run_honest_sweep_r3.py:15847-15860` passes `lineage=None` on the default path, and
  `src/polaris_graph/generator/corpus_snapshot.py:134-137` therefore adds no snapshot key.
- `scripts/dr_benchmark/gate0_lineage.py:351-374` preserves the default manifest shape and key
  order, including `canonical_idx`, with no `lineage` key.
- `scripts/score_report_race.py:64-69` adds only a stdlib gate0 import/env read on default; the
  legacy scoring block is not entered.

Read-only deterministic HEAD-vs-worktree harness results:

- default canonical resolver output: exact;
- default lineage-manifest dict and serialized JSON: exact;
- default snapshot bytes: exact, with no `lineage` key;
- output-contract result: exact for unset and explicit `drb_ii_idx`;
- required-flags tuple: exact;
- default coverage-helper truth table: exact for unset and explicit `drb_ii_idx`;
- default resolver opened only the DRB-II task file and did not open `query.jsonl`.

No default-path artifact or behavior divergence was found for the stated surfaces.

### 2. SINGLE-BRAIN COMPLETENESS FOR LEGACY — FAIL

What is correct for mapped task 72:

- Resolver: `scripts/dr_benchmark/gate0_lineage.py:182-244` resolves
  `SLUG_TO_LEGACY_TASK["drb_72_ai_labor"] == 72` from legacy `query.jsonl`.
- Gate-B override: `scripts/dr_benchmark/run_gate_b.py:5706-5731` selects legacy and attaches the
  legacy-only `question_lineage` marker.
- Direct task-72 sweep override: `scripts/run_honest_sweep_r3.py:21946-21970` does the same.
- Scope protocol: `scripts/run_honest_sweep_r3.py:9905-9912` passes `q["question"]`, and
  `src/polaris_graph/nodes/scope_gate.py:1131-1138` stores it as `protocol.research_question`.
- Retrieval is rooted in `_clean_question`, initialized from `q["question"]` at
  `scripts/run_honest_sweep_r3.py:9718` and passed to the active FS/IterResearch lane at
  `scripts/run_honest_sweep_r3.py:10899-10912`.
- V30 compile/frame and contract plans receive `q["question"]` at
  `scripts/run_honest_sweep_r3.py:13887-13901` and `:14269-14286`.
- Both generator/re-entry paths receive it at `scripts/run_honest_sweep_r3.py:16022-16035`.
- H1 uses it at `scripts/run_honest_sweep_r3.py:17735-17737`.
- Corpus snapshot stores it and the legacy marker at
  `scripts/run_honest_sweep_r3.py:15847-15860`.
- RACE scorer reads the answered question/slug/lineage and invokes the legacy split-brain guard
  before pack writes at `scripts/score_report_race.py:69-107`.
- All assignment scans found no later idx-56 rewrite outside the two intended override blocks.
- The raw registered task-72 question, legacy resolver, and `query.jsonl` id 72 are in fact
  byte-equal and share SHA
  `c598a9cf1912e8932da930682bccbce02157df4430cfd86c7f8303078d918fbf`.
- The three output-contract consumers all route through the lineage-aware loader:
  pre-spend at `scripts/dr_benchmark/run_gate_b.py:4528-4529`, render at
  `scripts/run_honest_sweep_r3.py:18173-18195`, and post-render at
  `scripts/dr_benchmark/run_validity_gate.py:438-461`. Legacy receives `None`.

Blocking incompleteness:

- `gate0_lineage.assert_drb_slug_registered` is not lineage-aware. It accepts any slug in
  `DRB_SLUGS_WITHOUT_CANONICAL_GOLD` at `scripts/dr_benchmark/gate0_lineage.py:116-127`.
- The direct sweep's no-mapping legacy rejection is restricted to `_slug in SLUG_TO_IDX` at
  `scripts/run_honest_sweep_r3.py:21971-21982`. Therefore an explicitly registered no-gold
  benchmark slug such as `drb_90_adas_liability` is a benchmark, has no legacy mapping, passes
  registration, misses both legacy branches, and is appended unchanged at `:21991`. This violates
  the v2 requirement that every legacy/benchmark-slug pair without a mapping fail loud and makes
  global/`--only drb_90...` selector behavior split from Gate-B, whose broader
  `is_benchmark_slug` rejection at `scripts/dr_benchmark/run_gate_b.py:5732-5741` is correct.

Required fix:

- Make legacy registration/checking reject **every** benchmark slug absent from
  `SLUG_TO_LEGACY_TASK`, including explicit no-gold slugs, in the shared resolver/registration
  seam; use that same check from both Gate-B and direct sweep.

### 3. FAIL-LOUD PRESERVATION — FAIL

PASS portions:

- Unknown selectors fail at `scripts/dr_benchmark/gate0_lineage.py:64-77`.
- Canonical resolver legacy/no-mapping fails at `scripts/dr_benchmark/gate0_lineage.py:230-238`.
- Gate-B rejects every legacy benchmark slug with no mapping at
  `scripts/dr_benchmark/run_gate_b.py:5732-5741`.
- Packed/answered/canonical mismatches fail via the SHA guard at
  `scripts/dr_benchmark/gate0_lineage.py:274-302`.
- The scorer refuses missing snapshot evidence or wrong stored lineage at
  `scripts/score_report_race.py:69-98`.

FAIL portions:

- Direct sweep's explicit-no-gold hole is described in item 2.
- “Raw registered question equals legacy canonical” is not a raw assertion:
  `scripts/dr_benchmark/run_gate_b.py:5716-5717` and
  `scripts/run_honest_sweep_r3.py:21963-21964` compare only `sha256_text`.
  `sha256_text` normalizes all whitespace first at
  `scripts/dr_benchmark/gate0_lineage.py:144-151`.
- The new test `tests/dr_benchmark/test_stage0_lineage_seam.py:197-206` explicitly passes three
  raw-different strings (`"LEGACY   Q"`, `"LEGACY Q"`, `"LEGACY\nQ"`), contradicting the required
  raw-AND-SHA test. The task-72 integration test at
  `tests/dr_benchmark/test_stage0_lineage_sweep_integration.py:24-37` asserts only SHA equality.

Required fix:

- Assert raw string/byte equality **and** normalized SHA equality for the registered legacy
  question and the packed/answered/canonical evidence where v2 requires both.
- Replace the whitespace-drift acceptance test with explicit raw-equality plus SHA-equality tests.

### 4. COVERAGE GATE REPORT-ONLY FOR LEGACY — FAIL

The code changed at `scripts/run_honest_sweep_r3.py:1912-1939` is
`_required_entity_ledger_failed_under_strict`: it controls only whether an **exception while
building/rendering the RequiredEntityLedger** becomes the F27 post-spend abort at
`scripts/run_honest_sweep_r3.py:20824-20845`.

That is not the native required-element coverage decision identified by v2:

- native denominator load: `src/polaris_graph/roles/native_gate_b_inputs.py:283-301`;
- fixed denominator enters `CoverageLedger` at
  `src/polaris_graph/roles/native_gate_b_inputs.py:959-960,1228-1231`;
- actual below-threshold coverage HOLD is created at
  `src/polaris_graph/roles/release_policy.py:235-254`.

Consequences:

- the intended native coverage result has not been made lineage-aware at its severity/disposition
  seam;
- if the separate report-level ledger implementation throws, legacy now suppresses the F27 abort
  but keeps only the WARN at `scripts/run_honest_sweep_r3.py:20464-20471`; it produces neither the
  required coverage report nor a durable manifest failure marker. That is log-only fail-soft, not a
  report-only coverage decision;
- the new tests at `tests/dr_benchmark/test_stage0_lineage_seam.py:284-293` and
  `test_stage0_lineage_sweep_integration.py:54-64` test this wrong exception predicate, not a native
  low-coverage result.

This edit is not a content lever—it changes status severity only—but it is the wrong severity
surface and can hide a broken coverage-report producer.

Required fix:

- Preserve the native coverage fraction/gaps/audit unchanged, and make only the idx-56
  required-element **coverage-shortfall blocker** report-only for `legacy_race_task` at an outer
  lineage-aware disposition seam. Do not relax claim faithfulness, S0/fabrication/zero-grounding
  decisions, or edit content.
- Keep a RequiredEntityLedger implementation failure fail-loud/durably disclosed; do not silently
  convert it to a WARN-only success.
- Add a behavioral test that supplies a below-threshold native fixed-denominator result and proves:
  default blocks as before, legacy retains the exact coverage telemetry/gap but does not abort for
  that reason alone.

### 5. GHOST AUDIT — PASS

Exact GHOST_BAN regex over `git diff -- scripts/ src/` produced four hits:

1. `binding by idx` — identity-lineage description;
2. `Fail CLOSED` — pre-existing adjacent model-selector comment;
3. `touches NO faithfulness gate (... NLI ...)` — explicit exclusion;
4. `NO binding` — explanation of the historical unbound-question failure.

None is a proposal for admission, entailment/NLI, premise binding, suppression, or
post-generation content acceptance.

Frozen-module diff is empty for:

- `src/polaris_graph/generator/provenance_generator.py`
- `src/polaris_graph/clinical_generator/strict_verify.py`

Structural checks:

- (a) PASS — no emitted-vs-admitted/planned comparison;
- (b) PASS — no new producer-to-render content-drop/replace predicate;
- (c) PASS — no new import/change of either frozen faithfulness module;
- (d) PASS for content checks — production checks are lineage identity/pre-spend guards, not
  content admission; deterministic content ship checks remain tests only;
- (e) PASS — no new dataclass/type or banned carrier fields.

`SLUG_TO_LEGACY_TASK` contains task 72 only as the required canonical identity registry; no
task-72 domain vocabulary, prompt lever, target count, or score-forcing rule was added.

### 6. BUG / OFF-BY-SEAM / MISSED OVERRIDE — FAIL

Blocking bugs are the direct no-gold fail-open, wrong coverage-severity seam, and missing raw
equality above.

Additional required lineage fix:

- `scripts/run_honest_sweep_r3.py:9554-9559` passes
  `expected_lineage=q.get("question_lineage")`. Default queries have no marker, so this is `None`,
  and `src/polaris_graph/generator/corpus_snapshot.py:198-207` performs no lineage check.
  Consequently a stored legacy snapshot is accepted by the loader when a later run selects the
  default lineage. The following question-SHA guard at `scripts/run_honest_sweep_r3.py:9537-9560`
  catches task 72 today because its legacy and idx-56 questions differ, but the explicit invariant
  “resume rejects a mismatched stored lineage” is only enforced default-to-legacy, not
  legacy-to-default.
- `tests/dr_benchmark/test_stage0_lineage_seam.py:263-278` exposes this gap: it deliberately calls
  `expected_lineage=None` as a no-check, while the only legacy-to-default rejection test calls the
  loader manually with explicit `drb_ii_idx`; the production caller never does that.

Required fix:

- At the production resume seam, treat an absent query marker as the effective
  `drb_ii_idx` lineage for comparison while continuing to omit the default lineage from serialized
  artifacts. Add caller-level tests for both mismatch directions.

Test-harness incompleteness:

- `tests/dr_benchmark/test_stage0_lineage_sweep_integration.py:67-79` counts alias call sites. It
  can miss a second override written through another alias/direct loader and does not prove any
  downstream value.
- No new test behaviorally asserts the protocol, retrieval seed, compile frame, contract plan,
  generator argument, H1, snapshot, and scorer pack all carry the same task-72 raw value/SHA.
- No scorer guard test is present.
- Default “golden identity” tests check manifest shape/no snapshot key rather than comparing exact
  HEAD bytes; they do not exercise selected `q` or protocol bytes.

## Verification evidence and limitations

- All six modified production files and both new tests compile successfully via Python `compile()`.
- `git diff --check` reports CR-at-EOL on added `run_gate_b.py` lines because that entire file is
  already CRLF in both HEAD and worktree (HEAD: 6,859/6,859 CRLF; worktree: 6,922/6,922 CRLF);
  no mixed-newline regression was found.
- The requested pytest files could not be executed in this checkout: `pytest` is not installed,
  `python3 -m pytest` reports `No module named pytest`, no project virtualenv is present, and importing
  the full sweep directly also lacks `python-dotenv`. No dependency/network installation was
  attempted (operator required no web). The pure deterministic harnesses listed in item 1 were run
  with stdlib only.
- Two additional untracked shell files (`scripts/run_race_batch3_max.sh`,
  `scripts/run_race_max_focus.sh`) are present in the shared worktree but are outside the stated
  six-file diff and were not treated as part of this Stage-0 review.
- The binding campaign `state/beatboth_campaign/loop_state.json` referenced by `AGENTS.md` is absent
  from this worktree. The operator's explicit bounded read-only Stage-0 authorization was used.

## Single most important risk

**The implementation claims the legacy required-element coverage gate is report-only, but it
actually disables only the post-spend abort for a broken coverage-ledger reporter.** That can both
leave the real native idx-56 coverage disposition unaddressed and allow a legacy success with the
coverage disclosure silently absent. The re-baseline would then spend against a seam whose
ship-decision test is testing the wrong predicate.
