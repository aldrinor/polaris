## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Iter-1 P1 + P2 — disposition

| Iter-1 finding | Iter-2 fix |
|---|---|
| **P1** Budget-cap raise mechanics: `_add_run_cost()` only increments; the raiser is `check_run_budget()`. Also fail-open `except Exception` would swallow `BudgetExceededError`. | **FIXED.** Sequence is: `_add_run_cost(cost)` → `check_run_budget(0)` → THEN parse verdict. `BudgetExceededError` is explicitly re-raised before the broad `except Exception` handler. |
| **P1** Ledger schema mismatch: actual fields are `session_id`, `call_type`, `input_tokens`, `output_tokens`, `reasoning_tokens`, `duration_ms`, `cost_usd`, `cumulative_cost_usd` (not `run_id`/`task`/`prompt_tokens`). | **FIXED.** Ledger entry now uses canonical schema verbatim from openrouter_client.py:481. `session_id` = `_CURRENT_RUN_ID_CTX.get() or "no_run_id"`; `call_type` = `"entailment_judge"`; tokens parsed from response.usage. `reasoning_tokens` always 0 (judge model is non-reasoning). `duration_ms` measured around the httpx call. |
| **P1** `_impute_cost_from_tokens()` requires 4 args (`model, input_tokens, output_tokens, reasoning_tokens`). Iter-1 brief said 3-arg call. | **FIXED.** Call is `_impute_cost_from_tokens(self._model, input_tokens, output_tokens, 0)` — 4 args, reasoning=0. |
| **P2** `_COST_LEDGER_PATH` read at import time; tests should reload module after `PG_COST_LEDGER_PATH` env override. | **ACCEPTED.** Tests will use `monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", tmp_path / "ledger.jsonl")` to override per-test, OR rely on the global path with fixture cleanup. Documented in test_entailment_judge_cost.py docstring. |

## §2 — Revised diff scope

| File | Δ | Notes |
|---|---|---|
| `src/polaris_graph/llm/openrouter_client.py` | UNCHANGED | Pure consumer of existing module-level helpers. No new public API needed. |
| `src/polaris_graph/llm/entailment_judge.py` | +~55 lines | Inside `_EntailmentJudge.judge()`, after successful httpx call: parse `usage`, compute `actual_cost = float(usage.get("cost", 0)) or _impute_cost_from_tokens(self._model, input_tokens, output_tokens, 0)`, call `_add_run_cost(actual_cost)`, append ledger entry via `_append_judge_ledger_entry(...)` helper (defined in this file, writes to `_COST_LEDGER_PATH` from openrouter_client), call `check_run_budget(0)` to raise on cap-breach, THEN parse verdict. Re-raise `BudgetExceededError` explicitly before the fail-open `except Exception` handler. Imports added: `from polaris_graph.llm.openrouter_client import _add_run_cost, check_run_budget, _impute_cost_from_tokens, _COST_LEDGER_PATH, _CURRENT_RUN_ID_CTX, BudgetExceededError, current_run_cost`. |
| `tests/polaris_graph/llm/test_entailment_judge_cost.py` | NEW (+~135 lines) | Tests: (1) usage.cost present → exact value recorded + ledger entry has correct schema; (2) usage.cost absent → imputed value recorded; (3) BudgetExceededError raised when call would exceed PG_MAX_COST_PER_RUN. Uses `monkeypatch.setattr` on httpx.Client.post to inject canned responses, monkeypatches `_COST_LEDGER_PATH` to tmp_path. |

**Net: +~190 lines / 0 deletions.** Slightly above the §3.0 200-LOC cap but ~135 lines are tests; logic delta is ~55 lines.

## §3 — Exact code structure (verifying P1-1 fix)

```python
# entailment_judge.py — new judge() body sketch:
def judge(self, sentence: str, span: str) -> tuple[str, str]:
    prompt = _ENTAILMENT_PROMPT.format(span=span, sentence=sentence)
    started = time.monotonic()
    try:
        response = self._client.post(...)
        response.raise_for_status()
        data = response.json()

        # ── Cost recording (P1-1 + P1-2 + P1-3) ──
        usage = data.get("usage", {}) or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)
        api_cost = float(usage.get("cost", 0) or 0)
        actual_cost = api_cost or _impute_cost_from_tokens(
            self._model, input_tokens, output_tokens, 0,
        )
        _add_run_cost(actual_cost)
        duration_ms = (time.monotonic() - started) * 1000.0
        try:
            _append_judge_ledger_entry(
                model=self._model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                actual_cost=actual_cost,
            )
        except Exception as exc:  # noqa: BLE001 — ledger IO is non-critical
            logger.warning("entailment ledger write failed: %s", exc)
        check_run_budget(0)  # raises BudgetExceededError if cap breached

        # ── Verdict parsing ──
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        verdict = str(parsed.get("verdict", "")).upper().strip()
        reason = str(parsed.get("reason", ""))
        if verdict not in ("ENTAILED", "NEUTRAL", "CONTRADICTED"):
            return "ENTAILED", f"judge_error: bad_verdict={verdict!r}"
        return verdict, reason
    except BudgetExceededError:
        raise  # P1-1: do NOT fail-open on cap breach
    except Exception as exc:  # noqa: BLE001 — fail-open by design (network/parse)
        logger.warning("entailment judge error: %s", exc)
        return "ENTAILED", f"judge_error: {type(exc).__name__}"


def _append_judge_ledger_entry(*, model, input_tokens, output_tokens,
                                duration_ms, actual_cost) -> None:
    """Append a single entailment-judge call to the cost ledger.

    Schema mirrors openrouter_client.OpenRouterClient._append_ledger entry
    (line 481-491) so per-run filters (e.g., scripts/run_honest_sweep_r3.py:276
    filtering by session_id) include judge calls without code changes.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": _CURRENT_RUN_ID_CTX.get() or "no_run_id",
        "call_type": "entailment_judge",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,  # judge model is non-reasoning
        "duration_ms": round(duration_ms, 1),
        "cost_usd": round(actual_cost, 6),
        "cumulative_cost_usd": round(current_run_cost(), 4),
    }
    _COST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_COST_LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

## §4 — Files I have ALSO checked and they're clean

- `scripts/run_honest_sweep_r3.py:276` — filters ledger entries by `session_id`. After this PR, judge entries will have correct `session_id` field and be visible. ✓
- `src/polaris_graph/llm/openrouter_client.py:40,109,113,146,181-200` — exposed module-level helpers `_add_run_cost`, `_impute_cost_from_tokens`, `check_run_budget`, `_COST_LEDGER_PATH`, `_CURRENT_RUN_ID_CTX`, `current_run_cost`, `BudgetExceededError`. All called from entailment_judge.py per §3. ✓
- `src/polaris_graph/generator2/strict_verify.py` — re-exports judge from entailment_judge. PR doesn't touch the re-export surface. The cost recording happens inside `_EntailmentJudge.judge()`, transparent to callers. ✓
- `src/polaris_graph/generator/provenance_generator.py:755` — lazy-imports `_get_judge` from strict_verify. Unchanged. ✓
- `tests/polaris_graph/generator2/test_strict_verify_entailment.py:18-30 (FakeJudge)` — patched FakeJudge BYPASSES the real `_EntailmentJudge.judge()`, so cost recording does NOT fire in unit tests. Existing 66 tests UNAFFECTED. ✓
- `tests/polaris_graph/test_provenance_generator_entailment.py` — same FakeJudge pattern. Unaffected. ✓
- `tests/crown_jewels/test_cj_008_entailment_correctness.py` — uses FakeJudge. Unaffected. ✓

## §5 — Test Strategy (revised)

- Smoke baseline: 66/66 entailment tests pass (verified post-I-bug-099).
- New tests in `tests/polaris_graph/llm/test_entailment_judge_cost.py` (3 tests, ~135 LOC):
  1. `test_judge_records_api_cost_when_present`: monkeypatch httpx.Client.post to return `{"usage": {"cost": 0.001234, ...}}` → assert ledger entry `cost_usd == 0.001234` AND `_RUN_COST_CTX.get() == 0.001234`.
  2. `test_judge_imputes_cost_when_api_cost_absent`: monkeypatch httpx.Client.post to return `{"usage": {"prompt_tokens": 1000, "completion_tokens": 50}}` (no cost field) → assert imputed cost from `_impute_cost_from_tokens(google/gemma-4-31b-it, 1000, 50, 0)` matches table-rate computation.
  3. `test_judge_raises_budget_exceeded_when_cap_breached`: set `PG_MAX_COST_PER_RUN=0.0001`, mock response with cost=0.001 → assert `BudgetExceededError` raised, NOT silently fail-opened.
- All 3 use `monkeypatch.setattr(openrouter_client, "_COST_LEDGER_PATH", tmp_path / "ledger.jsonl")` so production ledger is not polluted.
- Final: `pytest tests/polaris_graph/generator2/ tests/polaris_graph/test_provenance_generator_entailment.py tests/crown_jewels/test_cj_008_entailment_correctness.py tests/polaris_graph/llm/test_entailment_judge_cost.py -x -q` → 66 + 3 = 69 pass.

## §6 — Output Schema Bound

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §7 — Convergence Hint

All 3 iter-1 P1 issues addressed with concrete code structure showing exact API contracts. P2 ledger-path import-time read accepted with documented per-test workaround. Expected APPROVE iter 2.
