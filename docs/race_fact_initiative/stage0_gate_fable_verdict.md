# STAGE-0 LINEAGE SEAM — FABLE GATE VERDICT

Gate: Fable (read-only design gate, /home/polaris/wt/faithoff). Date: 2026-07-24.
Spec: stage0_lineage_seam_spec.md. Verdict: **GO-WITH-CHANGES** (2 required changes, 1 documentation item).

## Q1 — Is the lineage-selector design correct and minimal? Does it preserve the forced-flag invariant without reopening the wrong-question bug?

**YES on design shape; the spec's 3 seams are necessary but NOT sufficient (see Q3).**

Verified facts:
- `run_gate_b.py:5669` forces `os.environ["PG_BENCHMARK_OFFICIAL_QUESTION"] = "1"` unconditionally; the flag is
  required-truthy in `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (`run_gate_b.py:1904` tuple, entry at `:2070`). Under
  `legacy_race_task` NOTHING changes here: the flag stays forced "1", the tuple is untouched, and the override at
  `:5670-5705` STILL FIRES — it just resolves canonical from the legacy source. The invariant "a benchmark run can
  never answer an unbound question" is preserved because binding still happens; only the bound SOURCE changes.
- The wrong-question hole is not reopened: `assert_no_split_brain` (`gate0_lineage.py:156-178`) still enforces
  packed==answered==canonical; under legacy, canonical = `query.jsonl` id=72 (sha `c598a9cf1912e893`, re-verified
  this session), packed = scorer's `query.jsonl` id=72 (`score_report_race.py:46-56`), answered = the registered
  SWEEP question (`run_honest_sweep_r3.py:7928-7936`) which I re-byte-verified == id=72 normalized. All three are
  the SAME text, so the guard holds by construction and still FAILS LOUD on any drift.
- The unregistered-slug FAIL-LOUD (`run_gate_b.py:5695-5705`, `gate0_lineage.py:61-78`) is preserved untouched.
- `third_party/DeepResearch-Bench-II/` is EMPTY in this checkout (verified `ls`) — the default idx-56 live path
  fails loud in `load_canonical_question` (`gate0_lineage.py:105-108`); the legacy path never reads it. Confirms
  the spec's motivation.
- Under legacy, slugs drb_75/76/78 have no legacy binding — `canonical_question_for_slug` must FAIL LOUD for them
  (spec's `SLUG_TO_LEGACY_TASK` contains only `drb_72_ai_labor: 72`). Correct and required.
- Selector value handling should be FAIL-LOUD on an unrecognized non-empty value (unset/""/"drb_ii_idx" → default;
  "legacy_race_task" → legacy; anything else → `GateZeroLineageError`). A typo must never silently pick a lineage.

## Q2 — Exact seams + minimal signature (default byte-identical)

The MINIMAL correct implementation is smaller than the spec sketched — the question path needs edits in **one
file** (`gate0_lineage.py`), because every consumer already routes through `canonical_question_for_slug`:

1. **`gate0_lineage.py` (the only question-path edit):**
   - `LEGACY_QUERY_PATH = third_party/deep_research_bench/data/prompt_data/query.jsonl` (constant).
   - `SLUG_TO_LEGACY_TASK: dict[str, int] = {"drb_72_ai_labor": 72}`.
   - `question_lineage()` reads `PG_BENCHMARK_QUESTION_LINEAGE` at call time (LAW VI); fail-loud on unknown values.
   - Branch inside `canonical_question_for_slug` (`gate0_lineage.py:127-134`): legacy → load prompt by id from
     `LEGACY_QUERY_PATH` (fail loud if file/id/prompt missing, mirroring `load_canonical_question`); slug not in
     `SLUG_TO_LEGACY_TASK` → `GateZeroLineageError`. Default lineage → EXACTLY the existing code path, same reads.
   - This automatically single-brains every consumer: the run_gate_b override (`run_gate_b.py:5675` imports
     `canonical_question_for_slug`), the main_async GATE0 override (`run_honest_sweep_r3.py:21913` — NOTE: the
     spec's ":19099" line ref is STALE; the block is at :21901-21934), `assert_no_split_brain`,
     `assert_launched_question_is_canonical`, `build_lineage_manifest`, and the retrieval_bakeoff gate0 harness.
   - `run_gate_b.py`'s override block and the preflight tuple need **zero edits** for the question path.

2. **`run_validity_gate.py::load_task_output_contract` (`:113` region) — the REQUIRED extra chokepoint (Q3):**
   make contract resolution lineage-aware: under `legacy_race_task`, an entry bound to a DRB-II idx (the existing
   `drb_idx` key in `task_output_contracts.yaml`) resolves to `None` → the documented no-op path all three
   consumers already handle. Keyed off the config's existing `drb_idx` field — no task literal in code.

Default byte-identity: env unset → `question_lineage()` returns default → identical code path, identical gold-file
read, no new read, no env mutation. The forced flag and required-flags tuple are untouched on BOTH paths.

## Q3 — Single-brain enumeration for legacy task-72 (and the seams that would SPLIT)

Flows automatically single-brained once the override binds legacy canonical (all read `q["question"]` downstream
of `run_gate_b.py:5670-5691`):
- protocol.json `research_question` (threaded through `run_one_query`); retrieval seed (question + amplified);
- H1 title (`run_honest_sweep_r3.py:5950` `# Research report: {research_question}`);
- corpus_snapshot answered-question (`run_honest_sweep_r3.py:15830-15838`, `question=q["question"]`);
- resume drift guards (`:9522-9535` snapshot-vs-run sha; `:15913` postgen-reuse sha) — lineage-agnostic sha
  equality against the current bound question; auto-correct;
- main_async GATE0 override (`:21901-21934`) — via the gate0_lineage branch (only relevant off the run_gate_b path);
- scorer pack (`score_report_race.py:46-56`, `query.jsonl` id=72) — already legacy-canonical.

**Seams that would REMAIN idx-56 and split the brain (the spec misses these — hence GO-WITH-CHANGES):**
`config/benchmark/task_output_contracts.yaml` is keyed by SLUG, and its `drb_72_ai_labor` entry is transcribed
VERBATIM from the idx-56 gold prompt (`drb_idx: 56`). Its three consumers:
1. **`enforce_render_validity` (`run_gate_b.py:5995-5996` → `run_validity_gate.py:429-458`) — HARD BLOCKER.**
   `intent_anchors` group `["generative ai", "generative artificial intelligence"]` is matched against the H1;
   the legacy question contains neither → `RunValidityGateError` AFTER FULL SPEND on every legacy run. Also
   `required_sections` (positive/negative/challenge/opportunit) and the EXACT 5-column table check
   (`run_validity_gate.py:349-367`) would fail a legitimately task-72-shaped report.
   (`forbidden_reformulations` is safe by design — "Fourth Industrial Revolution"/"English-language journal
   articles" ARE in the legacy bound question, and `check_question_fidelity` skips phrases present in it,
   `run_validity_gate.py:291-293`.)
2. **Summary-table injection (`run_honest_sweep_r3.py:18144-18174`)** — `_st_contract_headers` from the contract is
   the AUTHORITATIVE header source → the idx-56 5-column table ("Research Literature" … "Key Risks and
   Limitations") is rendered into a legacy task-72 report. This is the Sol-flagged reshaping seam. With the
   contract lineage-gated to None, the renderer falls back to parse-from-question; the legacy question requests no
   table → existing no-op.
3. **`assert_table_contract_columns_available` (`run_gate_b.py:4511`, called `:5713`)** — pre-spend; the contract's
   5 columns make it pass silently under legacy, arming seams 1-2. Contract→None makes it the documented no-op
   (`required_table` absent → return, `:4534`).
All three route through `load_task_output_contract` (`run_gate_b.py:4529`, `run_honest_sweep_r3.py:18155`,
`run_validity_gate.py` inside `enforce_render_validity`) — ONE lineage-gate there covers all three.

**Documentation item (not a required change):** `config/scope_templates/workforce.yaml:200-230`
`per_query_report_contract[drb_72_ai_labor]` (V30 outline `section_order` incl. `Generative_AI_Evidence`; 4-role
required-entity denominator) was authored against the idx-56 question (comment `:172-176`). It is a PRE-GENERATION
advisory scaffold; its entities (Acemoglu/Autor/Frey-Osborne/Brynjolfsson/Eloundou/Goos) are equally canonical for
the broader legacy task-72 question and already appear in the legacy slug's own `amplified` list
(`run_honest_sweep_r3.py:7941-7960`). No gate compares it against the bound question, so it cannot abort or
post-edit anything. ACCEPT under legacy with an explicit note in the run manifest/spec; lineage-gating it is
optional follow-up, not correctness.

Off-run-path: the qgen tools (`run_qgen_*.py`) read `SLUG_TO_IDX` directly for DRB-II rubrics — they fail loud on
the missing gold file and are not on the Gate-B run path; out of scope.

## Q4 — Ghost / content-lever audit

GHOST_BAN mechanical grep run on the spec: 4 hits (lines 6, 31, 35, 51) — every one is a naming-to-exclude ("NO
verify/gate/NLI touched", "grep the diff per GHOST_BAN.md") or QUESTION-source binding ("binding canonical=legacy",
"SLUG_TO_LEGACY_TASK binding"), i.e. lineage identity, NOT admission/marker/premise binding. Zero proposing hits.
Structural checks on the intended change surface (gate0_lineage.py + run_validity_gate.py contract chokepoint):
(a) no emitted-vs-admitted comparison; (b) no NEW predicate between producer and render — the legacy branch makes
an EXISTING ship/no-ship gate + an EXISTING render-time injector take their pre-existing documented no-op paths
(a reduction, not machinery); (c) no import of the frozen faithfulness modules; (d) no generation-path reader of
any test; (e) no new typed carrier with premise/admitted/binding fields. `SLUG_TO_LEGACY_TASK`'s task-id literal is
the same accepted class as the existing `SLUG_TO_IDX` experiment-identity registry — it never reaches a prompt.
**CLEAN — pure lineage plumbing, no content lever, no ghost.**

## Q5 — Verdict

**GO-WITH-CHANGES.** Build exactly the spec PLUS:
1. (REQUIRED) Lineage-gate `load_task_output_contract`: under `legacy_race_task`, a `drb_idx`-bound contract entry
   resolves to None (single chokepoint neutralizing the intent-anchor HARD FAIL, the 5-column table injection, and
   the pre-spend table assert).
2. (REQUIRED) Selector fail-loud on unrecognized values; legacy-unmapped slugs raise `GateZeroLineageError`.
3. (DOC) Record the workforce.yaml V30 contract accept-under-legacy decision; fix the spec's stale `:19099` ref
   (actual `:21901-21934`).
Then diff-gate (both models) per GHOST_BAN process guard.
