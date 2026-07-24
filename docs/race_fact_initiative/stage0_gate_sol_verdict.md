# SOL STAGE-0 LINEAGE GATE

## VERDICT: NO-GO

Do **not** build `stage0_lineage_seam_spec.md` exactly as written. The
`PG_BENCHMARK_QUESTION_LINEAGE` selector is the correct minimal identity primitive, but the proposed
three-seam implementation is not yet single-brained or demonstrably split-brain-guarded:

1. the direct sweep entry still unconditionally replaces task-72 with DRB-II idx-56;
2. the RACE scorer packs legacy task 72 but never calls `assert_no_split_brain`;
3. both contract surfaces selected by the shared slug remain explicitly idx-56 contracts; and
4. replacing the V30 contract with a newly authored legacy-task contract would be a task-specific
   content change, which is outside a pure Stage-0 lineage diff and conflicts with `GHOST_BAN.md`.

The selector design may proceed only after the contract-lineage decision is separated and approved.
The pure lineage subset below is otherwise the right minimal shape.

## Ground truth

- The registered `SWEEP_QUERIES` question is the legacy prompt at
  `scripts/run_honest_sweep_r3.py:7927-7935`. A local AST read and byte comparison against
  `third_party/deep_research_bench/data/prompt_data/query.jsonl` id `72` found raw equality,
  length `330`, and normalized SHA-256
  `c598a9cf1912e8932da930682bccbce02157df4430cfd86c7f8303078d918fbf`.
- The DRB-II gold file named by `gate0_lineage.DEFAULT_TASKS_PATH`
  (`scripts/dr_benchmark/gate0_lineage.py:27-30`) is absent in this checkout.
- `SLUG_TO_IDX["drb_72_ai_labor"] == 56`
  (`scripts/dr_benchmark/gate0_lineage.py:32-43`), and
  `canonical_question_for_slug` always reads that DRB-II source today
  (`scripts/dr_benchmark/gate0_lineage.py:99-134`).
- Gate-B force-writes `PG_BENCHMARK_OFFICIAL_QUESTION="1"` and then replaces `q["question"]`
  with that canonical idx question on the live path
  (`scripts/dr_benchmark/run_gate_b.py:5645-5687`). This occurs before `run_one_query`
  (`scripts/dr_benchmark/run_gate_b.py:5715,5950-5958`).
- The same flag is a fail-closed preflight requirement
  (`scripts/dr_benchmark/run_gate_b.py:2064-2070`), enforced by the common truthy loop
  (`scripts/dr_benchmark/run_gate_b.py:4794-4799`).
- `assert_no_split_brain` does enforce normalized
  `packed == answered == canonical` (`scripts/dr_benchmark/gate0_lineage.py:156-178`), but repo-wide
  call-site search found no production scorer call. `score_report_race.py` only loads the selected
  `query.jsonl` record and writes it into the target pack
  (`scripts/score_report_race.py:44-68`).

## Answers to the gate questions

### 1. Selector correctness and the forced-flag invariant

`PG_BENCHMARK_QUESTION_LINEAGE` with:

- unset / `drb_ii_idx` -> current idx behavior; and
- `legacy_race_task` -> legacy RACE question identity

is the correct minimal selector.

The forced official-question flag must **not** be removed, skipped, set to `0`, or removed from
`_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` for the legacy branch. Keep
`os.environ["PG_BENCHMARK_OFFICIAL_QUESTION"] = "1"` and the tuple entry byte-for-byte. In the legacy
branch, “official” means “the selected lineage's canonical source,” not “DRB-II idx.” This preserves
the existing preflight invariant without special-casing the truthy loop.

The legacy branch must also not merely skip the idx override and trust the registered string. It
must load legacy `query.jsonl`, resolve the configured task record, and fail loud unless the raw
registered SWEEP prompt equals that canonical prompt. Only after that equality assertion may it keep
the raw `q["question"]`. Otherwise a future SWEEP edit silently recreates the wrong-question bug.

### 2. Minimal signatures and default identity

The minimal Gate-0 API shape is:

```python
canonical_question_for_slug(
    slug,
    tasks_path=DEFAULT_TASKS_PATH,
    *,
    lineage="drb_ii_idx",
    legacy_tasks_path=DEFAULT_LEGACY_TASKS_PATH,
)
```

Use the same two keyword-only arguments on `assert_launched_question_is_canonical`,
`assert_no_split_brain`, and `build_lineage_manifest`, forwarding them to the one canonical resolver.
Keep the existing positional `(slug, tasks_path)` shape valid. Add a fail-loud legacy source loader
and an explicit slug-to-legacy-record registration. `build_lineage_manifest` must record the selected
lineage and must not label a legacy run with `canonical_idx=56`
(`scripts/dr_benchmark/gate0_lineage.py:181-225`).

Default-preservation requirements:

- read the selector with an in-process default; do not write
  `PG_BENCHMARK_QUESTION_LINEAGE=drb_ii_idx` into the environment;
- keep the forced `PG_BENCHMARK_OFFICIAL_QUESTION="1"` assignment;
- on `drb_ii_idx`, execute the current `SLUG_TO_IDX` branch and current DRB-II read exactly;
- do not open legacy `query.jsonl` on the default path;
- add lineage metadata to `q`/snapshots only on `legacy_race_task`, so default serialized artifacts
  do not gain a key; and
- reject unknown selector values before spend. Do this as a separate preflight value assertion;
  do not put the selector in the truthy required-flags tuple, because unset is the valid default.

### 3. Exact legacy seams that must agree

The legacy question must reach all of these:

- **Gate-B launch:** branch the override at
  `scripts/dr_benchmark/run_gate_b.py:5645-5706`. Default uses the existing idx override. Legacy
  checks the raw SWEEP question against the legacy canonical source and retains it. Attach a
  legacy-only lineage marker to the copied `q`.
- **Preflight:** retain the official-question required flag at
  `scripts/dr_benchmark/run_gate_b.py:2064-2070` and its enforcement at `:4794-4799`; add only an
  allowlisted selector-value check in `preflight_full_capability` (`:4643-4661`).
- **Gate-0 resolver and guards:** branch only in the canonical resolver at
  `scripts/dr_benchmark/gate0_lineage.py:99-134`, then forward the selector through the launch,
  split-brain, and manifest helpers at `:137-225`. Registration must fail for a legacy lineage/slug
  pair with no legacy mapping; the existing benchmark-slug registration rule is `:56-78`.
- **Direct sweep entry:** the independent GATE0 override at
  `scripts/run_honest_sweep_r3.py:21906-21934` must consult the same selector. Left unchanged, it
  always reads idx-56 and is a split brain relative to legacy Gate-B/scoring.
- **Protocol:** Gate-B must finalize `q` before `run_one_query`. The sweep passes the exact
  `q["question"]` to `run_scope_gate` at
  `scripts/run_honest_sweep_r3.py:9888-9895`; `run_scope_gate` stores it verbatim in
  `protocol.json.research_question` at `src/polaris_graph/nodes/scope_gate.py:872-884,1131-1169`.
- **Retrieval seed:** the intent frame is seeded from `q["question"]` at
  `scripts/run_honest_sweep_r3.py:9822-9824`; its derived clean question is formed at `:9863-9877`
  and becomes the primary retrieval seed at `:10902-10920`. The registered hand-authored amplified
  list is at `:7936-7960`. Thus launch binding must happen before the intent frame; no downstream
  second override is permitted.
- **V30 question:** `compile_frame` receives `q["question"]` at
  `scripts/run_honest_sweep_r3.py:13858-13884`; every generated contract plan stores the same question
  at `:14252-14269`; the generator receives the same question at `:16012-16016`.
- **H1/title:** the success H1 is an echo of `q["question"]` at
  `scripts/run_honest_sweep_r3.py:17713-17715` and is assembled at `:17853-17869`.
- **Corpus snapshot and resume:** the snapshot call records `q["question"]` at
  `scripts/run_honest_sweep_r3.py:15818-15838`; the persistence module writes it at
  `src/polaris_graph/generator/corpus_snapshot.py:90-126`. Add a legacy-only lineage field and reject
  a resume whose stored lineage differs. Existing question-SHA guards are at
  `scripts/run_honest_sweep_r3.py:9517-9537` and `:15910-15919`.
- **Summary table / render-validity contract:** the renderer is passed the legacy question at
  `scripts/run_honest_sweep_r3.py:18167-18174`, but it first loads authoritative headers by slug at
  `:18144-18165`. Those headers come from the idx-56 contract
  (`config/benchmark/task_output_contracts.yaml:11-48`). The same contract is loaded by the pre-spend
  assertion (`scripts/dr_benchmark/run_gate_b.py:4511-4548`) and the post-render validity gate
  (`scripts/dr_benchmark/run_validity_gate.py:111-129,423-458`). All three loaders/call sites need
  the selected lineage. Returning the idx-56 table/section contract on legacy is a split brain.
- **V30/D8 per-query contract:** `workforce.yaml` explicitly says its contract was authored for the
  official idx-56 question (`config/scope_templates/workforce.yaml:161-200`) and defines an
  idx-56-shaped section/entity contract at `:200-365`. It actively shapes the V30 outline and
  retrieval through `compile_frame` (`scripts/run_honest_sweep_r3.py:13858-14269`) and supplies the
  fail-closed Gate-B required-element denominator
  (`src/polaris_graph/roles/native_gate_b_inputs.py:283-301,943-960`). It cannot silently remain the
  only contract under the shared slug and still be called single-brained.
- **Scorer pack:** in legacy mode, after loading `query.jsonl` id 72, the scorer must read the
  answered question and slug from the adjacent run snapshot/manifest and call the lineage-aware
  `assert_no_split_brain` before writing any scoring files
  (`scripts/score_report_race.py:44-68`). This guard should be legacy-selector-gated so the default
  scorer path remains unchanged. Missing answered-question evidence must fail loud on legacy.

The seams that would remain idx-56 under the current spec are therefore:

1. direct `run_honest_sweep_r3.main` GATE0 override;
2. pre-spend summary-table contract;
3. summary-table renderer headers;
4. post-render run-validity contract;
5. V30 outline/entity contract and the 4-role coverage denominator; and
6. the canonical used by any unmodified Gate-0 assertion/manifest helper.

The scorer is an additional fail-open seam: it packs task 72 correctly but presently proves no
equality with what the report answered.

## Exact minimal edit list before a build may be approved

### Pure lineage edits (acceptable Stage-0 scope)

1. `scripts/dr_benchmark/gate0_lineage.py:27-43,99-225`
   - add the legacy source path/registration and fail-loud loader;
   - add keyword-only lineage parameters to the canonical and guard APIs;
   - keep the default DRB-II branch untouched and lazy;
   - make manifest identity lineage-correct.
2. `scripts/dr_benchmark/run_gate_b.py:2064-2070,2972-2990,4643-4799,5588-5713`
   - parse/validate the selector;
   - preserve the exact forced official-question assignment and required flag;
   - default: execute today's idx branch;
   - legacy: equality-check raw SWEEP vs legacy canonical, keep the raw question, and add
     legacy-only lineage metadata.
3. `scripts/run_honest_sweep_r3.py:21906-21934`
   - make the independent CLI GATE0 binding use the same resolver/selector.
4. `src/polaris_graph/generator/corpus_snapshot.py:90-180` and
   `scripts/run_honest_sweep_r3.py:9517-9537,15828-15838`
   - persist/validate lineage only for the legacy branch; preserve default snapshot bytes.
5. `scripts/score_report_race.py:44-68`
   - in legacy mode only, load answered-question evidence and invoke the split-brain guard before
     writing the pack.

### Unresolved contract decision (blocks code)

6. `scripts/dr_benchmark/run_validity_gate.py:111-129,423-458`,
   `scripts/dr_benchmark/run_gate_b.py:4511-4548`,
   `scripts/run_honest_sweep_r3.py:18144-18174`, and
   `config/benchmark/task_output_contracts.yaml:11-48`
   - make output-contract resolution lineage-aware; legacy must not receive idx-56's four-section,
     five-column-table contract.
7. `scripts/run_honest_sweep_r3.py:10327-10343,13858-14269`,
   `src/polaris_graph/roles/native_gate_b_inputs.py:283-301,943-960`, and
   `config/scope_templates/workforce.yaml:161-365`
   - provide one lineage-aware source of the V30 generation contract and the Gate-B required-element
     denominator.

Item 7 cannot be completed as “pure lineage plumbing” by inventing a new legacy task-72 entity,
section, or source contract: that changes retrieval, outline, generation, and the binding coverage
denominator. Nor may legacy simply receive no contract, because
`load_required_entities` explicitly fails closed on an absent/empty denominator
(`native_gate_b_inputs.py:283-301`). The operator must choose one of these separately gated options:

- approve the existing workforce contract as intentionally shared across both lineages despite its
  idx-56 provenance and accept that “single-brained” applies only to question bytes; or
- authorize a separate content-contract design gate for the legacy task, outside Stage-0; or
- define a pre-existing, lineage-neutral native denominator that Stage-0 may select without
  authoring task content.

Until one is chosen, building the selector would create a run that answers task 72 in its visible
question surfaces while still being planned and coverage-gated by idx-56.

## Ghost audit

**Result: not clean enough to ship; no code diff exists yet.**

The pure lineage subset above is structurally ghost-free: it changes input identity and artifact
identity only; it adds no entailment/NLI/admission layer, no post-generation content mutation, no
new producer-to-render predicate, no typed premise carrier, and touches neither
`provenance_generator.py` nor `clinical_generator/strict_verify.py`. That is consistent with
`GHOST_BAN.md:17-33,49-63`.

The unresolved contract retarget is different. A new task-72-specific V30 contract would add
task/domain literals and would actively shape retrieval/outline/generation, matching the overfit
hazard at `GHOST_BAN.md:9-15`; it therefore cannot be smuggled into the Stage-0 lineage diff.

Mechanical audit notes:

- there is no intended code diff to grep yet, so a claimed “diff grep clean” would be guessing;
- grepping the design spec itself produces hits on `binding` at its lines 31 and 35. Those are
  canonical identity uses, not a content-admission proposal, but they still require explicit
  disposition under the mechanical rule at `GHOST_BAN.md:49-54`;
- after a build is authorized, run the exact GHOST_BAN regex on the actual diff and reject any
  hit not limited to a ban/exclusion explanation.

## Residual risk

- A global selector can be accidentally applied to `--all`; legacy registration must fail loud for
  every slug without an explicit legacy mapping.
- `transport is not None` currently suppresses the gold read. Legacy registration still needs a
  read-free structural check on offline paths; live equality must not be skipped.
- Normalized SHA equality intentionally ignores whitespace. If “byte-identical” means raw bytes,
  tests must assert both raw equality and `sha256_text` equality; the production split-brain guard
  currently enforces normalized equality (`gate0_lineage.py:89-96`).
- Selector/lineage metadata must be captured once per query. Re-reading a mutated environment later
  could make scoring/resume use a different lineage.
- Default identity must be demonstrated by a golden off-state test over env mutations, selected
  `q`, canonical file opens, protocol bytes, snapshot bytes, and output-contract resolution—not only
  by unit-testing the resolver.

## Ship decision

**NO-GO to build the current spec exactly.** Revise it to include the direct sweep override, a real
legacy scoring guard, and an explicit operator-approved disposition for both idx-56 contract
surfaces. After that, the pure selector/lineage implementation can be diff-gated with the default
path held byte-identical and the forced official-question preflight invariant unchanged.
