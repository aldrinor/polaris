## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#355 — I-bug-101: distributional FPR audit on entailment judge.**

Issue: "Run entailment judge on 200 known-good sentences (already strict_verify-passing) to measure false-NULL_DROP rate. Acceptance: outputs/I-bug-101_audit/distribution.json with per-sentence verdict + false-positive rate. If FPR > 5%, escalate as urgent."

## §2 — Scope decision

The 200-pair LIVE audit is user-budget-gated (200 calls × ~$0.001 = ~$0.20 OpenRouter spend). This PR provides the **HARNESS** that runs the audit + tests it offline; the actual live invocation is a manual run when the user provides:
- PG_STRICT_VERIFY_ENTAILMENT in {warn,enforce}
- OPENROUTER_API_KEY
- 200-pair golden JSONL (production-derived; NOT user-curated synthetic)

The harness ships with a 5-pair smoke fixture so CI / local dev verifies the script-shape without spending budget. `--live` flag triggers the real judge call.

## §3 — Proposed change

| File | Δ |
|---|---|
| `scripts/run_entailment_fpr_audit.py` | NEW (+~190 lines): CLI + `run_fpr_audit()` core; --smoke + --golden + --live flags; output schema includes per-pair verdicts + summary {entailed, neutral, contradicted, judge_error, fpr_rate, fpr_alert} |
| `tests/scripts/test_run_entailment_fpr_audit.py` | NEW (+~110 lines): 8 tests covering smoke fixture, golden JSONL load, malformed-row rejection, no-source error, dry-run stub manifest, output dir creation |

Net: +~300 lines. 8 tests pass.

## §4 — FPR alert contract

`fpr_alert: True` iff `(neutral + contradicted) / n_pairs > 0.05`. Per acceptance: "If FPR > 5%, escalate as urgent." Script returns exit-2 in --live mode when alert fires; user sees this and files a follow-up issue.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Expected APPROVE iter 1.
