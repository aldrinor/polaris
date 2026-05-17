# Claude architect audit — I-modref-004 (#530)

**Issue:** GH #530 — Class B rename: `qwen_*` identifiers + `live_qwen_judge.py`
module + `qwen_judge_output.json` artifact.
**Branch:** `bot/I-modref-004-judge-rename`
**Commit 1 (code):** `88b04865`
**Brief:** `.codex/I-modref-004/brief.md` — Codex APPROVE iter 3 (0 P0, 0 P1, 3 P2).

## 1. Scope executed

Model-neutral rename of the judge subsystem's `qwen`-tainted namespace, per
the brief §3 rename map + §4 migration. 35 files, +260/-212.

| Class | Old | New | Files |
|---|---|---|---|
| Module | `live_qwen_judge.py` | `live_judge.py` (`git mv`, 95% similarity) | 1 + 3 importers |
| Artifact | `qwen_judge_output.json` | `judge_output.json` | 3 writers emit new name |
| Dataclass fields / `to_dict` keys | `qwen_critical_axes`, `qwen_parse_ok` | `judge_critical_axes`, `judge_parse_ok` | `evaluator_gate.py`, `loader.py` |
| Code-internal identifiers | `qwen_result`, `qwen_revision_axes`, `HIGH_RISK_QWEN_AXES`, `qwen_judge_raw`, `_QwenShim`, `qwen_{path,prev,shim}` | `judge_*` / `_JudgeShim` | `evaluator_gate.py`, `loader.py`, `regate_v23.py` |
| Reason codes | `qwen_parse_failed`, `qwen_{citation_tightness,hedging_tone,completeness,multi_axis}_needs_revision` | `judge_*` (suffixes preserved) | `evaluator_gate.py` (no legacy alias — strings) |
| Serialized keys | `qwen_verdicts`, `qwen_judge` | `judge_verdicts`, `judge` | sweep scripts |
| Status pair | `partial_qwen_advisory`, `ok_qwen_advisory` | `partial_evaluator_advisory`, `ok_evaluator_advisory` | writers emit new; **legacy retained as readable aliases** |

## 2. Migration safety — per-claim verification

- **VERIFIED — historical artifacts not rewritten.** `git status` shows zero
  staged paths under `outputs/honest_*` or `outputs/codex_findings/`. The one
  pre-existing working-tree-modified `outputs/honest_sweep_r3/.../qwen_judge_output.json`
  was NOT staged (drift predating this issue).
- **VERIFIED — two-level dual-read.** (a) Filename: `loader.py`,
  `inspector_router.py`, `regate_v23.py`, `compare_live_vs_pg_lb_sa_02.py`
  each prefer `judge_output.json`, fall back to `qwen_judge_output.json`.
  (b) Field name: `loader.py` uses presence-based fallback
  (`raw["judge_critical_axes"] if "judge_critical_axes" in raw else
  raw.get("qwen_critical_axes", [])`) — a valid new `False`/`[]` wins over a
  legacy key, per brief §4.
- **VERIFIED — status taxonomy.** `UNIFIED_STATUS_VALUES` +
  `_SUMMARY_TO_UNIFIED` + `run_status.py` `PipelineStatus` Literal +
  `regression_lab.py` weight dict all carry BOTH `*_evaluator_advisory`
  (primary) AND `*_qwen_advisory` (legacy) so historical manifests/model_pins
  still validate and re-gate.
- **VERIFIED — golden fixtures updated.** `manifest.json` (`judge_critical_axes`,
  `judge_parse_ok`, reason codes, `judge_verdicts`, `status:
  partial_evaluator_advisory`) + `model_pin.json` note → `ok_evaluator_advisory`.

## 3. Test coverage

- `test_m205_evaluator_gate.py` rewritten: every `compute_evaluator_gate`
  call uses `judge_result=`; reason-code + `judge_critical_axes` assertions
  renamed; taxonomy tests assert BOTH primary `partial_evaluator_advisory`
  AND legacy `partial_qwen_advisory` (regression coverage on the dual path).
- `test_audit_ir_loader.py`: legacy-filename dual-read test
  (`test_partial_model_provenance_fails_loud_other_direction`, writes
  `qwen_judge_output.json`) **preserved**; new sibling
  `test_partial_model_provenance_fails_loud_new_filename` added (writes
  `judge_output.json`).
- 7 other test files: constructor-kwarg / fixture-dict renames.
- **Offline smoke:** 308 passed. 2 failures in `test_manifest_contract.py`
  (`abort_quota_exceeded` taxonomy gap; outer-exception-handler scan) are
  PRE-EXISTING — verified identical at clean HEAD via `git stash`. Not a #530
  regression.

## 4. Documented residuals (scope discipline)

Per `feedback_be_skeptical_of_codex` — the brief is the contract, but #530's
title is "`qwen_*` identifiers + module", not model-config. The following
carry `qwen` but are NOT `qwen_*` identifiers and are deferred:

- **Model-SKU strings** (`qwen/qwen3-8b`, `qwen/qwen-2.5-72b-instruct`) in
  `docs/runbook.md:154,160`, `docs/transparency.md:29`,
  `src/polaris_v6/api/transparency.py:218`, `scripts/regate_v23.py:112` —
  these are model defaults; aligning them is #502/#527/#529 model-config work,
  not a name rename. Brief §3 line 53 over-listed `transparency.{md,py}`.
- **Family-label** `qwen` in `.env.example:68` (`PG_EVALUATOR_FAMILY_OVERRIDE`
  example) — a training-lineage tag; Qwen-family models still exist.
- **Canonical-pin-protected** `CLAUDE.md:289` (brief-excluded) +
  `docs/carney_delivery_plan_v6_2.md:199` — editing either trips the
  `docs/canonical_pin.txt` §3.1-step-0 HARD STOP. Same exclusion class.
- **Historical** `docs/pipeline_audit_context/{11,16,17}` pass-N audit
  records reference reads of specific historical sweep dirs where the file
  IS `qwen_judge_output.json` — accurate-for-history, like
  `outputs/codex_findings/**`.

`README.md` + `architecture.md` + `pipeline_audit_context/{00,01,02,03,07}`
module/artifact references WERE updated (the module file genuinely no longer
exists under the old name — a true dangling reference; brief §3 P2-doc-sweep
flagged exactly this).

## 5. Risk assessment

- **Two-family invariant** untouched — `check_family_segregation` and the
  `"qwen"` family label are out of scope; generator/evaluator lineage logic
  unchanged.
- **Provenance / strict_verify** untouched.
- **Diff size** +260/-212 ≈ 472 LOC, exceeds the 200-LOC cap — inherent to a
  complete rename; the diff-review exemption is requested in `diff_brief.md`.
- No new control flow, no new external calls, no schema-breaking change
  (every consumer dual-reads).

## 6. Verdict

Implementation complete and internally consistent. Zero dangling renamed
identifiers in `src/`, `tests/`, `scripts/` (verified by grep — only
intentional legacy dual-read fallbacks remain, each commented `I-modref-004
(#530) legacy`). Ready for Codex diff review.
