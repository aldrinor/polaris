# Codex BRIEF review — I-modref-004 / GH #530: Class B rename — qwen_* identifiers + live_qwen_judge.py + qwen_judge_output.json

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

A **BRIEF review** (iter 3) — verify the rename map + migration approach are correct + complete BEFORE the diff is written.

## 0.1 Iteration trail — all findings addressed

- iter-1 P1s (missed `qwen_verdicts`/`qwen_judge`; dual-read missed 2 readers; false "gitignored" premise — 206 tracked `outputs/honest_*` files) → addressed in iter 2.
- iter-2 NOVEL P1 (`ok_qwen_advisory` — a SECOND qwen-tainted serialized status) → §3 + §4 below.
- iter-2 P2s (`_QwenShim` class; 7 more stale doc/config sites; presence-based field fallback) → §3 + §4 + §5.

## 1. The issue (GH #530 / I-modref-004)

Carved from I-rdy-006 (#502); Codex flagged these legacy model-tainted names warrant a dedicated rename. Acceptance: rename complete (all call sites / imports / artifact consumers updated, no dangling old names); artifact-name change migration-safe; full test suite green.

## 2. Grounded blast radius

### 2.1 Module — `src/polaris_graph/evaluator/live_qwen_judge.py`
Public API already neutral (`LiveJudgeResult`, `judge_report`). `qwen` only in: filename, logger `polaris_graph.live_qwen_judge`, `[live_qwen_judge]` log prefix, two stale docstrings. Importers (4): `run_honest_sweep_r3.py`, `run_honest_on_prerebuild_corpus.py`, `run_live_honest_cycle.py`, `evaluator_gate.py` (docstring).

### 2.2 Artifact — `qwen_judge_output.json`
Writers: `run_honest_sweep_r3.py:2670`, `run_honest_on_prerebuild_corpus.py:416`, `run_live_honest_cycle.py:377` (write new name only). Readers needing dual-read: `audit_ir/loader.py:996`, `audit_ir/inspector_router.py:668`, `scripts/compare_live_vs_pg_lb_sa_02.py:106`, `scripts/regate_v23.py:80`. Tests: `test_audit_ir_loader.py`, `test_inspector_router.py`.

### 2.3 `qwen_*` identifiers — classified
- **Code-internal:** `qwen_result`, `qwen_revision_axes`, `HIGH_RISK_QWEN_AXES` (`evaluator_gate.py`); `qwen_judge_raw` (`loader.py`); `qwen_path`, `qwen_prev`, `qwen_shim`, class `_QwenShim` (`regate_v23.py:49`).
- **Serialized data-contract fields / keys:** `qwen_critical_axes`, `qwen_parse_ok` (`EvaluatorGateResult` + `to_dict()`); `qwen_verdicts` (`run_honest_sweep_r3.py:2799,3244`, fixture line 851; local in `regate_v23.py`); `qwen_judge` (`run_honest_on_prerebuild_corpus.py:496`).
- **Greppable reason codes:** `qwen_parse_failed`, `qwen_citation_tightness_needs_revision`, `qwen_hedging_tone_needs_revision`, `qwen_completeness_needs_revision`, `qwen_multi_axis_needs_revision`.
- **Serialized status values (a PAIR):** `partial_qwen_advisory` AND `ok_qwen_advisory`. `ok_qwen_advisory` is mapped at `run_honest_sweep_r3.py:196`, emitted at `:2719`, persisted into `model_pin.json` notes at `:3218`, asserted in `test_m205_evaluator_gate.py:232,249`, present in pinned fixture `tests/fixtures/m_live_4_baseline/clinical/clinical_tirzepatide_t2dm/model_pin.json:59`. `partial_qwen_advisory` consumers (11): `evaluator_gate.py` docstring, `run_status.py` (Pydantic status schema), `regression_lab.py`, `polaris_v6/api/bundle.py`, `scripts/{regate_v23,run_full_scale_v27,run_honest_sweep_r3}.py`, golden fixture manifest.json, tests `test_m205_evaluator_gate.py`/`test_manifest_contract.py`/`test_bundle_endpoint_targz.py`. (Sibling `abort_evaluator_critical` is already neutral — the inconsistency is what #530 fixes.)

## 3. Proposed rename map (model-neutral: qwen → judge / evaluator)

| Old | New |
|---|---|
| `live_qwen_judge.py` (+ logger / `[live_qwen_judge]` / stale docstrings) | `live_judge.py` (`polaris_graph.live_judge`, `[live_judge]`, docstrings → Gemma) |
| `qwen_judge_output.json` | `judge_output.json` |
| `qwen_result` / `qwen_revision_axes` / `HIGH_RISK_QWEN_AXES` / `qwen_judge_raw` / `qwen_path` / `qwen_prev` / `qwen_shim` / `_QwenShim` | `judge_result` / `judge_revision_axes` / `HIGH_RISK_JUDGE_AXES` / `judge_raw` / `judge_path` / `judge_prev` / `judge_shim` / `_JudgeShim` |
| `qwen_critical_axes` / `qwen_parse_ok` (fields + to_dict keys) | `judge_critical_axes` / `judge_parse_ok` |
| `qwen_verdicts` (serialized key + local) | `judge_verdicts` |
| `qwen_judge` (serialized key, prerebuild script) | `judge` |
| reason codes `qwen_parse_failed`, `qwen_{citation_tightness,hedging_tone,completeness,multi_axis}_needs_revision` | `judge_*` (same suffixes) |
| status `partial_qwen_advisory` / `ok_qwen_advisory` (PAIR) | `partial_evaluator_advisory` / `ok_evaluator_advisory` (match sibling `abort_evaluator_critical`) |
| current docs/config: `.env.example:68`, `ground_rules.md:176,195`, `docs/file_directory.md:53`, `docs/runbook.md:160`, `docs/transparency.md:29`, `src/polaris_v6/api/transparency.py:218` | updated to new names |

**`CLAUDE.md:289`** also carries a `qwen` mention, but `CLAUDE.md` is a canonical-pin-protected file (`docs/canonical_pin.txt`, §3.1 step-0). A P2-cosmetic doc rename does NOT justify a canonical-pin-reconciliation commit; `CLAUDE.md` is **explicitly excluded** from #530 and noted as a documented residual (a separate pin-aware change if the operator wants it). Confirm this scope call.

## 4. Migration approach

- **Historical artifacts NOT rewritten.** ~206 tracked `outputs/honest_*` files + `outputs/codex_findings/**` are immutable run records — excluded from the rename.
- **Two-level dual-read absorbs the legacy contract** so every historical artifact still loads:
  1. **Filename:** every reader prefers `judge_output.json`, falls back to `qwen_judge_output.json`.
  2. **Field / status names:** **presence-based** fallback — `data["judge_verdicts"] if "judge_verdicts" in data else data.get("qwen_verdicts")` (NOT `data.get(new) or data.get(old)` — a valid new value of `False`/`[]`/`{}` must still win over a legacy field). Applies to `judge_verdicts`/`judge_critical_axes`/`judge_parse_ok`/`judge`/the reason codes; and status readers accept legacy `partial_qwen_advisory`/`ok_qwen_advisory` as input.
- **Writers emit only the new names.** `run_status.py` Pydantic status schema lists the new `*_evaluator_advisory` values AND retains the legacy `*_qwen_advisory` values as still-valid (so historical manifests/model_pins validate).
- **Golden fixtures updated** in-PR: `tests/fixtures/m_live_4_baseline/clinical/clinical_tirzepatide_t2dm/{manifest.json,model_pin.json}`.
- `git mv` the module (history preserved).

## 5. Acceptance criteria for this brief

1. Rename map (§3) complete — every `qwen`-tainted identifier / status / filename / current-doc reference covered; CLAUDE.md scope-out is the only documented exclusion.
2. The status PAIR `partial_qwen_advisory` + `ok_qwen_advisory` both renamed, both kept legacy-readable; `run_status.py` schema + `model_pin.json` writer path + tests + both fixtures covered.
3. Two-level **presence-based** dual-read sound; every artifact-filename reader (4) covered.
4. Historical-exclusion (`outputs/honest_*`, `outputs/codex_findings/`) sound.
5. Diff spans module + artifact + ~16 identifiers across ~32 files (Python + JS + fixtures + docs) — exceeds the 200-LOC cap inherent to a complete rename; request the Codex diff-review exemption.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
