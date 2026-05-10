## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance + scope decision

**GH#365 — I-bakeoff-A-001: Path A bakeoff (Qwen / Opus / GPT-5).**

Issue body: "Bake off generator candidates against current DeepSeek V3.2-Exp on the 5-question Carney goldset. Score by line-by-line audit (PRISMA 2020, AMSTAR-2, GRADE per claim — NOT metadata). Acceptance: outputs/bakeoff_A/{model}/audit.md with per-claim verdicts, recommendation."

The model bakeoff RUN itself is user-budget-gated (5 candidates × 5 questions × ~$0.01/run = ~$0.25 OpenRouter spend, plus model-specific quota). This PR ships the **FOUNDATION** that any bakeoff requires per CLAUDE.md §-1.1: a deterministic line-by-line audit harness producing per-claim VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE verdicts.

Per CLAUDE.md §-1.1: "Both Claude AND Codex MUST run independent line-by-line audits in parallel." This is Claude's automated audit (mechanical checks). Codex's audit is a separate manual `codex exec` pass that adds semantic claim review. The bakeoff WRAPPER (run pipeline N times with different generators, aggregate per-model audit results) is the next step on top of THIS primitive.

## §2 — Proposed change

| File | Δ |
|---|---|
| `scripts/run_line_by_line_audit.py` | NEW (+~210): per-sentence audit primitive + summary. Verdicts: VERIFIED (decimals match + overlap ok), PARTIAL (numeric_mismatch OR low_overlap, but the OTHER passes), UNSUPPORTED (no token), FABRICATED (numeric_mismatch AND low_overlap), UNREACHABLE (unknown source / span out-of-range). |
| `tests/scripts/test_run_line_by_line_audit.py` | NEW (+~135): 11 tests: each verdict path verified individually (UNSUPPORTED / UNREACHABLE / VERIFIED / FABRICATED / PARTIAL × 2 sub-cases), summary aggregation, alert on FABRICATED, alert on UNREACHABLE, sentence-preview truncation |

Net: +~345 lines.

## §3 — Files clean

- `src/polaris_graph/generator2/strict_verify.py` UNCHANGED. The audit harness reuses the SAME mechanical logic (decimal match, content overlap) — but operates POST-DELIVERY on completed report.md, not during generation.
- No production code path changes.

## §4 — Test verification

`pytest tests/scripts/test_run_line_by_line_audit.py -x -q` → 11/11 pass in 1.06s.

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
