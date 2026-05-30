# Q1 LIVE-RUN LAUNCH RUNBOOK + READINESS REVIEW (I-meta-002 #938) — pre-spend

Investigated by Claude (main-thread, grounded reads). Codex is the gate. Q1 does NOT start until Codex APPROVE + operator promotes the lock + operator says go.

## 1. READINESS CHECKLIST
| Item | State | Evidence |
|---|---|---|
| Gate-A (offline pre-rental) | READY | `gate_a_dry_run` OVERALL PASS rc0 |
| Runtime lock promoted | **BLOCKER** | `config/architecture/polaris_runtime_lock.yaml:37 status: codex_approved_pending_operator_signature` — NOT `locked`; live non-offline runs frozen; `pathB_run_gate._assert_architecture_coverage` raises while pending. OPERATOR-SIGNATURE-GATED. |
| Judge slug correct | READY (confirm) | lock:80 / serving:96,111 / gate_a:262 all `qwen/qwen3.6-35b-a3b` — consistent; the earlier "Judge slug typo" appears already fixed. |
| Generator reasoning↔output separation | READY (clean) | I-gen-004 (#496): `set_reasoning_sink` + `reasoning_trace.jsonl`; `generate()` = clean prose only, reasoning captured SEPARATELY via the sink; `report.md` uses content only. NO soap. |
| Verifier reasoning↔output separation + capture | **GAP** | `openai_compatible_transport.py:305 content = message.get("content")` — M1 reads ONLY `content`; the verifiers' `reasoning_content` is NOT captured. (a) Verifier reasoning is NOT logged → cannot line-by-line review WHY Mirror/Sentinel/Judge ruled. (b) If served Qwen inlines reasoning as `<think>…</think>` in `content`, the Judge exact-match parser (`judge_contract.py:45,52`) fails — no `<think>` stripping present. |
| Full run traceability (other than verifier reasoning) | READY (strong) | Per-question run_dir writes: manifest.json, report.md, run_log.txt, reasoning_trace.jsonl (generator), four_role_claim_audit.json, judge_output.json, verification_details.json, evidence_pool.json, live_corpus_dump.json, evaluator_rule_checks.json, bibliography.json, completeness.json, contradictions.json, model_pin.json, cost_ledger.jsonl + global pg_cost_ledger.jsonl; audit_bundle hashes all. |
| served==pinned (M4) | READY | `pathB_run_gate` self-host preflight + assert_post_run consume `_pathb_served.endpoint`/served model. |
| Cost cap | CONFIRM | `PG_MAX_COST_PER_RUN` must be set for Q1 (canary budget Vast $300 / OpenRouter $50, Codex-approved). |

## 2. REASONING vs OUTPUT — the operator's "no soap" bar
- **Generator: CLEAN.** Reasoning is a separate stream (reasoning_trace.jsonl); the shipped report is content-only. Reviewable separately.
- **Verifiers: NEEDS A NO-SPEND FIX.** Today only `content` is captured. To meet "clear division on reasoning and output + full log for line-by-line review" for the verifiers, BEFORE Q1:
  1. Capture the verifier `reasoning_content` (or the `<think>` block) into the captured record / a per-role reasoning log — SEPARATE from the parsed verdict, never concatenated into the report.
  2. Make the verdict parsers robust to served reasoning: either configure vLLM with the Qwen reasoning-parser so reasoning lands in `reasoning_content` (preferred — keeps `content` = the bare verdict), OR strip a leading `<think>…</think>` in the Judge/Sentinel/Mirror parsers before matching. Confirm which at serving time.
- This is a no-spend code change (transport capture + parser robustness + a test). Recommend doing it via a Claude Codex Workflow BEFORE Q1.

## 3. BLOCKERS (must clear before Q1 spends), in order
1. **Verifier reasoning capture + parse robustness** (no-spend code fix — section 2). The operator's core requirement; do FIRST.
2. **Runtime-lock promotion to `status: locked`** — OPERATOR signature. Live runs frozen until then.
3. **Confirm `PG_MAX_COST_PER_RUN`** cost cap is set for the canary.
4. (Verify, not block) Judge slug already consistent; re-confirm at serving that vLLM `--served-model-name == qwen/qwen3.6-35b-a3b` so M4 served==pinned passes for the right reason.

## 4. Q1 LAUNCH STEPS (after blockers clear)
1. (no-spend) Land the verifier-reasoning-capture fix; re-run Gate-A green.
2. Operator promotes the runtime lock to `status: locked`.
3. Rent Vast with a PERSISTENT VOLUME (438GB Mirror download paid once). Bring **Sentinel + Judge up FIRST** (cheap); bring **Mirror 8×H100 up LAST**.
4. For each role: `python -m scripts.dr_benchmark.verify_serving_identity` → served model id == locked slug (Mirror cohere/command-a-plus, Sentinel ibm-granite/granite-guardian-4.1-8b, Judge qwen/qwen3.6-35b-a3b). Abort if any mismatch.
5. Set `PG_FOUR_ROLE_MODE=1`, the per-role `PG_<ROLE>_BASE_URL`/`PG_<ROLE>_API_KEY`, and `PG_MAX_COST_PER_RUN`.
6. Run the SINGLE Q1 question (e.g. drb_75) via the Gate-B caller (`run_gate_b`) → one run_dir with all artifacts.
7. Tear **Mirror DOWN FIRST**, then Sentinel/Judge; **destroy** instances (keep the volume). Record spend.

## 5. ABORT conditions
- Any role's served id ≠ locked slug (served==pinned fail).
- Cost approaching `PG_MAX_COST_PER_RUN` → `BudgetExceededError`.
- Judge returns unparseable verdicts (the `<think>` risk) — stop, fix serving/parse, do NOT loosen the gate.

## 6. What a CLEAN Q1 looks like (and what is NOT failure)
- All 4 roles served==pinned; all artifacts written; generator reasoning in reasoning_trace.jsonl; verifier reasoning captured separately (after the fix); cost within cap.
- **A `four_role_held` (release HELD) verdict is NOT a failure** — POLARIS's clinical S0 exact-source gates may hold Q1 (a clinical question) until evidence with the exact required sources is retrieved. That is the safe, fail-closed direction. Do NOT weaken S0 to force a release. Q1 SUCCESS = the pipeline ran end-to-end live, reasoning/output cleanly separated, every step reconstructable from the logs — NOT necessarily a "released" answer.
