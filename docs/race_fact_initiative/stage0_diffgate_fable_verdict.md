# STAGE-0 LINEAGE SEAM — Fable diff-gate verdict (implemented diff, worktree /home/polaris/wt/faithoff)

**VERDICT: GO** (commit + run the re-baseline). Pure lineage/identity plumbing confirmed; no ghost; default
path byte-identical; single-brain for legacy task-72 verified at every seam. Four non-blocking nits below.

Reviewed against `stage0_lineage_seam_spec_v2.md` + `GHOST_BAN.md`. Diff = 6 modified files (+381/−17) + 2 new
test files. HEAD = 5991f8bb.

---

## 1. DEFAULT-PATH BYTE IDENTITY — CONFIRMED, no divergence

- **Selector is in-process default, never written to env**: `gate0_lineage.py:43-88`
  (`resolve_lineage`/`lineage_from_env` — unset/empty → `drb_ii_idx`; nothing writes the env key back).
- **No query.jsonl read on default**: `load_legacy_task_question` (gate0_lineage.py:182-211) is reached ONLY
  inside the `resolved == LINEAGE_LEGACY_RACE_TASK` branch of `canonical_question_for_slug`
  (gate0_lineage.py:214-244). Locked by test `test_default_path_does_not_read_legacy_query_jsonl`
  (tracking `builtins.open`; asserts no `query.jsonl` open).
- **Forced official-question flag untouched**: `os.environ["PG_BENCHMARK_OFFICIAL_QUESTION"] = "1"`
  (run_gate_b.py:5687) has no diff hunk; the required-flags truthy tuple (~:2064-2070) and its enforce
  (~:4794-4799) have NO hunks — the only preflight change is the separate allowlisted VALUE check at
  run_gate_b.py:4824-4842, which correctly does NOT add the selector to the truthy tuple (unset is valid).
- **Default override branch unchanged**: the HEAD `if _official_slug in _GATE0_SLUG_TO_IDX:` body is now the
  final `elif` (run_gate_b.py:5742+), byte-same logic; same in main_async (run_honest_sweep_r3.py:21983+).
- **Manifest default shape identical**: `build_lineage_manifest` default emits `{"slug", "canonical_idx", ...}`
  in HEAD key order, NO `lineage` key (gate0_lineage.py:349-355; test `test_manifest_default_is_head_shape`).
- **Snapshot default JSON identical**: `lineage=None` → key omitted (corpus_snapshot.py:134-137; test
  `test_snapshot_default_omits_lineage_field`). Sweep passes `q.get("question_lineage")` → None on default.
- **Resume default identical**: `expected_lineage=None` → no check (corpus_snapshot.py:198-206).
- The default path gains only env READS (`lineage_from_env()` in run_gate_b_query, load_task_output_contract,
  the ledger predicate) — no artifact/behavior change; a bogus selector value fails loud pre-spend in BOTH
  entries (preflight allowlist for run_gate_b; `lineage_from_env` raise at the main_async GATE0 block).

## 2. SINGLE-BRAIN COMPLETENESS FOR LEGACY — CONFIRMED; no idx-56 override left

- **Both entry overrides consult the SAME selector**: run_gate_b_query (run_gate_b.py:5698-5741) and the
  direct-sweep main_async GATE0 block (run_honest_sweep_r3.py:21945-21983). Legacy: resolve legacy canonical,
  assert raw registered SWEEP question == legacy canonical (sha), keep it, attach `question_lineage` marker.
  q["question"] then flows unmodified to scope_gate protocol / retrieval seed / V30 compile_frame / H1
  (no other rebind — locked by `test_no_second_idx_override_in_sweep`: exactly 2 `_gate0_canonical_q(`
  call-sites in the sweep module, both inside the ONE block).
- **Output-contract, all 3 consumers via ONE gate — the post-spend-abort risk is closed**:
  `load_task_output_contract` returns None under legacy (run_validity_gate.py:129-134). Verified the 3
  consumers all route through it: (a) pre-spend `assert_table_contract_columns_available`
  (run_gate_b.py:4528-4534 — contract None → `required_table` empty → documented no-op); (b) summary-table
  renderer headers (run_honest_sweep_r3.py:18175-18187 — None → parse-from-question fallback, and the
  task-72 question requests no table columns); (c) post-render validity gate (run_validity_gate.py:459-461 —
  `if not contract: return None`). So a legacy run can NOT fail-loud on the idx-56
  `intent_anchors`/5-column contract after spend. Locked by `test_output_contract_legacy_is_none_default_unchanged`.
- **Coverage gate report-only for legacy**: the RequiredEntityLedger's ONLY fatal consumer is the F27 HOLD
  at run_honest_sweep_r3.py:20833-20849, gated on `_required_entity_ledger_failed_under_strict`
  (:1912-1939) which returns False under legacy → the legacy fail-soft WARN + manifest record path is kept
  (report-only), the run cannot abort post-spend on the idx-56 coverage rubric. `load_required_entities`
  (native_gate_b_inputs.py:283-301) still resolves for the drb_72 slug (workforce.yaml contract exists), so
  no new raise is introduced either.
- **Scorer**: legacy-gated split-brain guard (score_report_race.py:58-107) — reads answered question + slug +
  stored lineage from the run's corpus_snapshot.json, BLOCKs (exit 2) if snapshot/fields missing or lineage
  mismatched, then `assert_no_split_brain(slug, prompt, answered, lineage=legacy)`. Default scorer path
  unchanged (guard is a no-op unless the env selector is legacy).
- **Manifest can never label legacy as canonical_idx=56**: gate0_lineage.py:337-347 (`legacy_task_id: 72`,
  no `canonical_idx` key; test locks it). `build_lineage_manifest` has NO production caller (tests only), so
  it introduces no run-path assert.

## 3. FAIL-LOUD PRESERVED — CONFIRMED

- raw-SWEEP == legacy-canonical assert (sha) in BOTH overrides (run_gate_b.py:5716-5726;
  run_honest_sweep_r3.py:21964-21969) — a drifted SWEEP question fails loud pre-spend, never silently
  recreated. The invariant itself is locked deterministically by
  `test_raw_sweep_question_equals_legacy_canonical_for_drb72` (verified: query.jsonl id=72 exists, prompt =
  the AI-labor literature-review task).
- Split-brain guard still raw+sha256 fail-loud on deliberate mismatch, both lineages (tests
  `test_split_brain_guard_fails_loud_{default,legacy}`).
- Unregistered slug (`assert_drb_slug_registered`), legacy-with-no-mapping (resolver raise
  gate0_lineage.py:233-239 + both override fail-loud branches), unknown selector (resolve_lineage raise +
  preflight allowlist) — all fail loud.
- Cross-lineage resume: corpus snapshot rejected via `expected_lineage` (corpus_snapshot.py:198-206); the
  default-resuming-legacy direction and the FETCH-snapshot branch are both covered by the existing
  question-SHA guard `_assert_snapshot_question` (run_honest_sweep_r3.py:9537-9564) since the two lineages'
  questions differ by construction.

## 4. COVERAGE-GATE SEVERITY CHANGE — CORRECT, MINIMAL, NOT A CONTENT LEVER

The change is confined to the pure HOLD predicate (:1922-1939); it only PREVENTS a would-be-success demotion
for legacy; it adds no content, drops no content, reads only the env selector. The ledger itself (and its
WARN/manifest record) still runs. Default behavior byte-identical (pre-existing
tests/polaris_graph/blockers/test_g2_runsweep_blockers.py ledger cases still pass). This is severity-only —
exactly the spec's seam-9 resolution.

## 5. GHOST AUDIT — CLEAN (0 hits)

- GHOST_BAN mechanical grep over the ADDED diff lines: **0 hits** (exit 1). All banned-family terms in the
  diff context lines (`release_allowed`, `fail-closed`, `canary`) are pre-existing HEAD code, untouched.
- Frozen-module diff: `git diff -- provenance_generator.py strict_verify.py` = **0 lines**.
- Five structural checks: (a) no emitted-vs-stored-text comparison (all comparisons are INPUT-question
  identity, pre-generation/pre-scoring); (b) no new predicate between producer and render that can drop or
  replace content — the two gate changes only LOOSEN fatal severity for legacy; (c) no import of either
  frozen module (new imports are gate0_lineage only); (d) all new deterministic checks live under `tests/`;
  nothing in the generation path reads their result; (e) no new dataclass/type at all — only identity dict
  keys (`lineage`, `question_lineage`, `legacy_task_id`). PASS on all five.
- Overfit check: `SLUG_TO_LEGACY_TASK={"drb_72_ai_labor": 72}` is an identity registry (same family as the
  existing SLUG_TO_IDX), not a runtime content literal; selector names are descriptive, no adjective flags.

## 6. INDEPENDENT VERIFICATION (confirms the operator's run)

- 23/23 pass: `test_stage0_lineage_seam.py` (19) + `test_stage0_lineage_sweep_integration.py` (4), 1.30s.
- Pre-existing blocker suite: 56 pass / 3 fail (`test_iarch011_prb_*`) — the SAME 3 fail at clean HEAD
  5991f8bb (verified in a throwaway worktree) → pre-existing, NOT caused by this diff.
- Frozen-module diff empty — confirmed. Ghost grep 0 hits on added lines — confirmed.

## NITS (non-blocking; note for the driver)

1. **Scorer snapshot adjacency (the most important operational risk)**: legacy scoring requires
   `corpus_snapshot.json` NEXT TO the scored report.md (score_report_race.py:71-73). Any copy-the-report-
   then-score workflow (the compose/champion habit) will BLOCK exit 2. Fail-loud in the right direction,
   but the re-baseline must score the in-run_dir report (or copy the snapshot alongside).
2. **Direct-sweep no-gold asymmetry**: main_async's legacy fail-loud branch keys on `_slug in SLUG_TO_IDX`
   (run_honest_sweep_r3.py:21970-21974) while run_gate_b uses `is_benchmark_slug`. A no-gold slug
   (`drb_90_adas_liability`) under legacy in the DIRECT sweep would run unmarked and only be BLOCKED at
   scoring (snapshot lineage None) — post-spend. Edge case (only drb_72 has a mapping today); align to
   `is_benchmark_slug` in a follow-up.
3. **`DEFAULT_LEGACY_TASKS_PATH` is CWD-relative** (gate0_lineage.py:60-62), consistent with the existing
   `DEFAULT_TASKS_PATH` convention — but score_report_race.py resolves its own DRB path ROOT-absolute, so a
   from-elsewhere scorer invocation would spuriously (loudly) BLOCK. Run from repo root.
4. **Out-of-scope untracked files**: `scripts/run_race_batch3_max.sh`, `run_race_max_focus.sh` (RACE
   champion measurement leftovers) are in the worktree — do NOT let them ride the Stage-0 commit.

— Fable diff-gate, read-only review, no files modified.
