# Stage-0 lineage seam — Fable RE-GATE verdict (post-Sol-fixes)

## Verdict: GO-WITH-CHANGES

One required change before commit + re-baseline: a one-line hard-block guard on the Fix-3
coverage downgrade (zero-grounding hole, item 2 below) plus its test. Everything else — default
byte-identity, single-brain, Fixes 1/2/4, ghost cleanliness — verified PASS. I ran the tests
myself this time (Sol could not): **31/31 pass** via `/home/polaris/conda_cu128/bin/python -m
pytest` (1.30s). Frozen-module diff: **0 lines**. GHOST grep: **4 hits, zero proposals**.

## 1. Default byte-identity — PASS (no fix leaked into the default path)

- Forced flag intact: `scripts/dr_benchmark/run_gate_b.py:5688` still force-assigns
  `PG_BENCHMARK_OFFICIAL_QUESTION="1"`; the required-flags tuple still carries it exactly once
  (`run_gate_b.py:2070`); the selector is NOT in the tuple (preflight check at `:4824-4842` is
  value-allowlist-only, inert when unset).
- Manifest default branch: `gate0_lineage.py:388-401` — `{"slug", **lineage_label, ...}` with
  `lineage_label={"canonical_idx": ...}` preserves HEAD key order exactly; no `lineage` key.
  Test `test_manifest_default_is_head_shape` locks it.
- Snapshot: `corpus_snapshot.py:134-137` adds the key only when `lineage is not None`; sweep
  passes `q.get("question_lineage")` (None on default). Test locks no-key on default.
- Output contract: `run_validity_gate.py:128-135` returns early ONLY for legacy;
  default/unset falls through to HEAD code. (Nit: the docstring says the selector is "unread on
  the default path" — it IS read via `lineage_from_env()`; behavior is still identical.)
- Scorer: `score_report_race.py:47-49` returns 0 before any file read on default/unset.
- Gate-B override restructure (`run_gate_b.py:5706-5747`): under default the legacy `if`s are
  false and the `elif _official_slug in _GATE0_SLUG_TO_IDX` chain is byte-equivalent to HEAD's
  `if`; no-gold branches unchanged.
- ONE intentional default-path behavioral delta: the production resume seam
  (`run_honest_sweep_r3.py:9569-9585`) now ALWAYS passes `expected_lineage` (resolved
  `drb_ii_idx` for a marker-less q). A default resume atop a legacy-stored snapshot is now
  rejected — that IS Fix 4, cannot trigger on HEAD-produced artifacts, and changes no bytes of
  any default artifact.

## 2. Fix 3 (coverage) — MOSTLY PASS, one hole = THE required change

**Correct parts (confirmed):**
- The ledger-exception predicate `_required_entity_ledger_failed_under_strict`
  (`run_honest_sweep_r3.py:1932-1956`) is back to lineage-INDEPENDENT — only the docstring
  changed vs HEAD; the return expression is context in the diff (byte-identical). F27
  implementation-failure stays fail-loud under every lineage; tested in both suites.
- The downgrade now targets the RIGHT predicate: the native coverage-shortfall held reason
  `d8_unsupported_residual_below_coverage` (`release_policy.py:57`, appended at `:243` from the
  fixed-denominator ledger), at the OUTER disposition seam (`run_honest_sweep_r3.py:19583-19625`),
  gated on `lineage_from_env() == legacy_race_task`.
- Set-EQUALITY (`_legacy_coverage_shortfall_report_only`, `:1912-1930`) + the explicit
  `fabricated_occurrence_latched` check protect fabrication, S0-must-cover, and pending-rewrite
  holds — any of them in `held_reasons` breaks equality. Predicate is pure and well-tested
  (`test_stage0_lineage_seam.py:377-405`).
- Telemetry preserved: the `manifest["four_role_evaluation"]` block (coverage_fraction,
  held_reasons, gaps) is written unchanged AFTER the downgrade (`:19634-19660`). Severity-only,
  no content read/edit — NOT a ghost.

**THE HOLE (zero-grounding not structurally protected):**
- Zero-grounding is NOT a `held_reasons` entry — it is `zero_verified AND zero_usable_evidence`
  (`sweep_integration.py:1092-1097`) surfacing as `hard_block`/`hard_block_reasons` in the
  ReleaseOutcome (`release_policy.py:546-547, 566-568, 584-593`). Set-equality on held_reasons
  cannot see it. The predicate's docstring claim — "a zero-grounding hard block (separate
  fields) is NEVER downgraded: set-equality ... cannot pass any of them" — is FALSE for
  zero-grounding.
- The shields that would normally co-fire are BOTH absent here: (a) the workforce contract has
  ZERO S0 entities (`config/scope_templates/workforce.yaml` — all S1/S2, no `s0_category`), so
  no S0-must-cover reason ever joins the set; (b) under `PG_ALWAYS_RELEASE=1` the
  pending-rewrite reason is suppressed (`release_policy.py:305-306`).
- Concrete path (legacy + PG_ALWAYS_RELEASE=1): claims present, none VERIFIED, no claim citing
  any evidence document → `hard_block=True`, `summary_status=STATUS_ABORT_NO_VERIFIED`
  (`release_policy.py:584-593`); `held_reasons == {coverage}` exactly → the downgrade FIRES,
  sets `manifest["release_allowed"]=True` and `released_with_disclosed_gaps`, overriding the
  zero-grounding hard block and leaving a contradictory manifest
  (`release_disclosure.hard_block=True` + `release_allowed=True`). The code comment "under
  PG_ALWAYS_RELEASE=1 ... this is a no-op there" is inverted: on the ON path the downgrade is a
  no-op in EVERY case EXCEPT the banned hard-block one. The OFF path has the analogous hole
  when claims are absent/non-material (coverage becomes the sole reason).
- Reachability is narrow (requires a degenerate zero-evidence run surviving to the D8 seam),
  but sweep_integration's own comment says this state is exactly what `zero_usable_evidence`
  exists to hard-block, and Sol's fix requirement was explicit: "fabrication/S0/zero-grounding
  never downgraded".

**Required change (small, mechanical):** add to the outer guard
`and not getattr(getattr(four_role_result, "release_outcome", None), "hard_block", False)`
(this excludes zero-grounding and fabricated-with-redaction-off on BOTH always-release paths),
fix the predicate/comment claims, and add a test: held_reasons={coverage} + hard_block outcome
→ NOT downgraded. No redesign needed.

## 3. Single-brain for legacy — PASS (one test-strength caveat)

- No idx-56 override survives under legacy: Gate-B (`run_gate_b.py:5714-5747`) and the direct
  sweep (`run_honest_sweep_r3.py:22007-22058`) both route benchmark slugs through
  `assert_legacy_slug_supported` first, then bind the legacy canonical with the marker; the
  rebound `_q` is what `_gate0_bound.append(_q)` captures (`:22058`). The idx branch is
  `elif`-fenced and unreachable for a legacy benchmark slug.
- Output contract → None for legacy at the single loader covering all 3 consumers.
- `test_no_second_idx_override_in_sweep` asserts exactly 2 `_gate0_canonical_q(` call sites in
  the sweep module (legacy + default branches of the one block).
- CAVEAT (honest grading of the new flow test):
  `test_single_brain_task72_value_carries_through_all_seams` executes production code only for
  the snapshot and scorer legs; the protocol/retrieval/compile/contract/generator/H1 legs are
  asserted BY CONSTRUCTION (bound_q is built inline in the test, and "seam_value ==
  legacy_q" is tautological). It does prove registered==legacy raw-equality and the
  snapshot→scorer chain end-to-end, and is backed by Sol's manual per-seam scan + the
  alias-count test — acceptable, but weaker than its docstring advertises. Non-blocking.

## 4. Fixes 1/2/4 — PASS

- **Fix 1 (no-gold fail-open):** `assert_legacy_slug_supported` (`gate0_lineage.py:136-160`) is
  the shared seam, pattern-based via `is_benchmark_slug` (regex `drb_<id>_...`, `:111-113`) so
  it rejects `drb_90_adas_liability` AND any future `drb_NN` absent from `SLUG_TO_LEGACY_TASK`.
  Called pre-spend at BOTH entries (`run_gate_b.py:5714-5715`; sweep `:22025-22031`). The
  direct-sweep hole Sol found is closed; one source of truth.
- **Fix 2 (raw equality):** `questions_raw_and_sha_equal` (`gate0_lineage.py:180-191`) enforced
  at the split-brain guard (`:333-345`, both packed and answered vs canonical) and at both
  registered-question asserts (`run_gate_b.py:5728-5738`; sweep `:22041-22048`). The
  whitespace-drift-ACCEPTING test is gone, replaced by explicit rejection tests
  (`test_stage0_lineage_seam.py:197-235`). Safety of the tightening checked: NO production
  default-path caller of `assert_no_split_brain` exists (only the bakeoff self-test with
  identical strings, and the new scorer guard), so the raw-tightening cannot break default.
- **Fix 4 (resume both directions):** production seam passes
  `resolve_lineage(q.get("question_lineage"))` — absent marker → effective `drb_ii_idx`;
  loader treats a missing stored field as `drb_ii_idx` (`corpus_snapshot.py:198-206`). Both
  mismatch directions rejected; both matching directions load; caller-level tests present
  (`test_stage0_lineage_seam.py:310-353`). Minor residual (out of Sol's stated scope, note
  only): the post-FETCH checkpoint (`fetch_snapshot`, sweep `:9591-9594`) carries no lineage
  field — cross-lineage protection there rests on the question-SHA guard, which catches task-72
  only because the two questions differ (the same "happens-to-catch" shape Sol flagged for the
  corpus snapshot). Consider stamping it in a follow-up; not a blocker for this run.

## 5. GHOST audit — PASS (confirms operator's grep-0-on-added-lines)

- Exact GHOST_BAN regex over `git diff -- scripts/ src/`: 4 hits, all non-proposing —
  (1) "binding by idx" identity description (pre-existing comment), (2) pre-existing adjacent
  "Fail CLOSED" model-selector comment, (3) "touches NO faithfulness gate (... NLI ...)"
  explicit exclusion, (4) "NO binding" historical-failure description. Zero proposals.
- Frozen-module diff: `provenance_generator.py` + `strict_verify.py` = **0 lines**.
- Structural (a)-(e): PASS. (a) no emitted-vs-admitted compare; (b) the coverage downgrade is
  consulted post-producer but can only RELABEL status/severity — it cannot drop or replace a
  byte of content (and it widens release, the opposite of a fail-closed content state);
  (c) no frozen-module import; (d) all new deterministic checks live under `tests/`, nothing in
  the generation path reads them; (e) no new dataclass/banned carrier fields.
  `SLUG_TO_LEGACY_TASK={"drb_72_ai_labor": 72}` remains pure identity registry — no domain
  vocabulary, counts, or score-forcing.

## 6. New-bug hunt from the fixes themselves

- The zero-grounding downgrade hole (item 2) — the one real finding; introduced by the Fix-3
  relocation to the outer seam.
- Contradictory manifest state (`hard_block=True` + `release_allowed=True`) in that same
  scenario — fixed by the same guard.
- Cosmetic: the downgrade writes a NEW top-level `manifest["disclosed_gaps"]` key (existing
  home is `release_disclosure.disclosed_gaps`); legacy-only, schema-only, non-blocking.
- Checked and clean: shared helper cannot mis-fire on default (caller-gated on legacy);
  `build_lineage_manifest` gained positional params but no HEAD caller breaks (grep: no
  production caller outside gate0 self-use); scorer guard runs BEFORE the pack write
  (`score_report_race.py:117-124`); cross-task scoring (snapshot slug vs --task-id) fails loud
  through the canonical resolve; seam-unadjudicated runs can't be downgraded (their
  held_reasons is the seam reason, not coverage).

## Operator's independent claims — CONFIRMED
31/31 stage0 tests pass (I re-ran them: `/home/polaris/conda_cu128/bin/python -m pytest ... 31
passed in 1.30s`); frozen-module diff 0; GHOST grep 0 proposals on the diff (4 benign hits).
