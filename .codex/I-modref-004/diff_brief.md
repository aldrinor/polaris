# Codex DIFF review — I-modref-004 / GH #530: Class B rename (qwen_* → judge_*)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. >200-LOC exemption (REQUESTED)

The diff is +260/-212 ≈ 472 LOC across 35 files. This **exceeds the 200-LOC
PR cap**. The exemption is requested and is inherent to the task: a complete
identifier rename cannot be split below 200 LOC without leaving the codebase
in a half-renamed (broken-import) intermediate state. The brief (§5 item 5,
Codex-APPROVE'd iter 3) anticipated and pre-authorized this. The diff is
mechanical (rename + dual-read), introduces no new control flow, no new
external calls, and no schema-breaking change.

## 1. What you are reviewing

`git diff origin/polaris...HEAD` excluding `.codex/I-modref-004/` and
`outputs/audits/I-modref-004/` — the canonical diff in
`.codex/I-modref-004/codex_diff.patch` (sha256 trailer). Commit 1 `88b04865`.

The change implements the Codex-APPROVE'd brief `.codex/I-modref-004/brief.md`
(iter 3 APPROVE, 0 P0 / 0 P1 / 3 P2). Verify the diff faithfully executes the
brief §3 rename map + §4 migration.

## 2. Rename executed (verify completeness + correctness)

- Module `git mv live_qwen_judge.py → live_judge.py`; logger
  `polaris_graph.live_judge`, `[live_judge]` prefix, docstrings model-neutral.
  3 importers updated (`run_honest_sweep_r3.py`, `run_honest_on_prerebuild_corpus.py`,
  `run_live_honest_cycle.py`).
- Artifact `qwen_judge_output.json → judge_output.json`; 3 writers emit the
  new name.
- Identifiers `qwen_result/qwen_revision_axes/HIGH_RISK_QWEN_AXES/
  qwen_judge_raw/_QwenShim/qwen_{path,prev,shim}` → `judge_*` / `_JudgeShim`.
- Dataclass fields + `to_dict` keys `qwen_critical_axes/qwen_parse_ok` →
  `judge_critical_axes/judge_parse_ok` (`EvaluatorGateResult` in
  `evaluator_gate.py`; `EvaluatorGate` in `loader.py`).
- Reason codes `qwen_{parse_failed,citation_tightness,hedging_tone,
  completeness,multi_axis}_*` → `judge_*` (suffixes preserved; **no legacy
  alias** — these are internal gate-reason strings, not a persisted contract).
- Serialized keys `qwen_verdicts → judge_verdicts`, `qwen_judge → judge`.
- Status pair `partial_qwen_advisory/ok_qwen_advisory` →
  `partial_evaluator_advisory/ok_evaluator_advisory`; legacy values RETAINED
  as readable aliases in `UNIFIED_STATUS_VALUES`, `_SUMMARY_TO_UNIFIED`,
  `run_status.py` Literal, `regression_lab.py` weight dict.

## 3. Migration invariant to verify

- Two-level **presence-based** dual-read in every artifact reader:
  filename (`judge_output.json` then legacy `qwen_judge_output.json`) AND
  field-name (`raw["judge_*"] if "judge_*" in raw else raw.get("qwen_*")` —
  NOT `or`, so a valid new `False`/`[]`/`{}` wins). Readers:
  `loader.py`, `inspector_router.py`, `regate_v23.py`,
  `compare_live_vs_pg_lb_sa_02.py`. `inspector.js` uses `??`.
- Historical `outputs/honest_*` + `outputs/codex_findings/**` NOT rewritten
  (zero such paths in the diff — confirm).
- Golden fixtures `m_live_4_baseline/.../manifest.json` + `model_pin.json`
  updated to new names.

## 4. Documented residuals (confirm scope call is sound)

NOT renamed, by deliberate scope discipline (see
`outputs/audits/I-modref-004/claude_audit.md` §4):
- Model-SKU strings (`qwen/qwen3-8b`, `qwen/qwen-2.5-72b-instruct`) in
  `runbook.md`, `transparency.{md,py}`, `regate_v23.py:112` — model-config,
  #502/#527/#529 scope, not `qwen_*` identifiers.
- Family-label `qwen` in `.env.example:68`.
- `CLAUDE.md` + `docs/carney_delivery_plan_v6_2.md` — canonical-pin-protected
  (brief §3 excluded CLAUDE.md; carney plan is the same exclusion class).
- `docs/pipeline_audit_context/{11,16,17}` — historical pass-N audit records.

## 5. Files I have ALSO checked and they're clean (§-1.2)

Grep `qwen_*` identifier tokens across the tree (excluding
`outputs/`, `.codex/`, `archive/`, `codex_tmp_*`):
- `src/` — only intentional legacy dual-read fallbacks in `loader.py` +
  `inspector_router.py`, each commented `I-modref-004 (#530) legacy`.
- `tests/` — zero dangling renamed identifiers (`No matches`).
- `scripts/` — only `run_honest_sweep_r3.py:3246` + `inspector.js:1222-1223`
  legacy dual-read fallbacks.
- All 23 edited `.py` files `ast.parse` clean.
- `evaluator_gate.py` reason-code strings: zero `qwen_*_needs_revision` /
  `qwen_parse_failed` remain (renamed, no legacy — verify test assertions
  match).

## 6. Test state

Offline smoke (13 affected suites): **308 passed**, 2 failed. Both failures
(`test_manifest_contract.py::test_manifest_contract_abort_statuses_are_authoritative`
— `abort_quota_exceeded` taxonomy gap; `::test_manifest_contract_exception_writes_error_manifest`
— exception-handler source scan) are **PRE-EXISTING** — verified identical at
clean HEAD via `git stash`. Not a #530 regression; out of scope to fix here.

## 7. Required output schema (§8.3.9)

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
