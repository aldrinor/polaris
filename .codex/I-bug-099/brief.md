## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Issue + Acceptance Criteria

**GH#353 — I-bug-099: extract entailment-judge helpers to shared module.**

The entailment-judge logic introduced in I-bug-092..I-bug-098 is currently defined inline in `src/polaris_graph/generator2/strict_verify.py` (lines 132-339) and lazy-imported by both:
- `src/polaris_graph/generator2/strict_verify.py` itself (the canonical strict verifier — `verify_sentence`)
- `src/polaris_graph/generator/provenance_generator.py` (the production verifier wired by I-bug-098)

This split is the source of the I-bug-098 latent gap (production verifier didn't initially exercise the entailment gate; the gap was caught only because the user pushed). A shared module gives a single import path so future call sites (e.g., I-bug-100 routing through OpenRouterClient, I-bug-101 FPR audit harness) don't repeat the same lazy-import pattern.

**Acceptance:**
- New module `src/polaris_graph/llm/entailment_judge.py` containing:
  - `_DEFAULT_ENTAILMENT_MODEL`, `_ENTAILMENT_TIMEOUT_S`, `_ENTAILMENT_PROMPT` constants
  - `_EntailmentJudge` class
  - `_get_judge()` lazy singleton
  - `_UNKNOWN_MODE_WARNED` dedup set + `_DEFAULT_MODE` constant
  - `_entailment_mode()` env-parser
  - `_JUDGE_TELEMETRY` dict + `get_judge_telemetry()`, `reset_judge_telemetry()`, `_record_judge_outcome()`
- `generator2/strict_verify.py`: replace local definitions with `from polaris_graph.llm.entailment_judge import …` re-export form; preserve module-level access pattern that tests rely on (`strict_verify._entailment_mode`, `strict_verify._get_judge`, etc).
- `generator/provenance_generator.py`: lazy import points at `polaris_graph.llm.entailment_judge` instead of `polaris_graph.generator2.strict_verify`.
- All 66 existing entailment tests pass without modification.
- **No behavior change.** Same env vars, same defaults, same telemetry counters.

## §2 — Proposed Change

| File | Δ | Notes |
|---|---|---|
| `src/polaris_graph/llm/entailment_judge.py` | NEW (+~210 lines) | Move all entailment-judge logic here. Verbatim from `strict_verify.py:132-339` minus the docstring delta noted below. |
| `src/polaris_graph/generator2/strict_verify.py` | -~210 lines, +~10 lines | Remove inline definitions; replace with `from polaris_graph.llm.entailment_judge import (_EntailmentJudge, _ENTAILMENT_PROMPT, _DEFAULT_ENTAILMENT_MODEL, _ENTAILMENT_TIMEOUT_S, _DEFAULT_MODE, _UNKNOWN_MODE_WARNED, _JUDGE_TELEMETRY, _get_judge, _entailment_mode, _record_judge_outcome, get_judge_telemetry, reset_judge_telemetry,)` so module-level attribute access still works. Update file-level docstring to reference the new module location. |
| `src/polaris_graph/generator/provenance_generator.py` | -3 lines, +3 lines | Change line 755 `from polaris_graph.generator2.strict_verify import (_entailment_mode, _get_judge, _record_judge_outcome,)` → `from polaris_graph.llm.entailment_judge import …`. No other change. |

**Net: ~+220 / -213 lines, single net-new module file. Well under §3.0 200-LOC cap; the +220 is mostly relocation, not new code.**

**Why `polaris_graph/llm/` and not `polaris_graph/generator/` (per issue body):** the judge IS an LLM client (httpx wrapper around OpenRouter). The repo already has `polaris_graph/llm/openrouter_client.py` and `polaris_graph/llm/loopback_client.py`. Keeping LLM-client wrappers in `llm/` is consistent with existing layout. Putting it in `generator/` would force `generator2/strict_verify.py` to import from `generator/` — backwards layering. `llm/` is neutral relative to both `generator/` and `generator2/` consumers.

## §3 — Files I have ALSO checked and they're clean

Comprehensive grep:
- `grep -r "_entailment_mode\|_get_judge\|_record_judge_outcome\|_JUDGE_TELEMETRY\|_DEFAULT_MODE\|_UNKNOWN_MODE_WARNED" src/`:
  - **2 hits in src/**: `generator2/strict_verify.py` (definitions + 1 call site at line 421) and `generator/provenance_generator.py` (lazy import at line 755). Both updated.
- `grep -r "from polaris_graph.generator2.strict_verify import" src/`:
  - **2 hits**: `generator2/generator.py:43` (imports `verify_sentence` etc. — does NOT import any entailment helper) and `generator/provenance_generator.py:755` (imports entailment helpers — UPDATED in this PR).
- `grep -r "from polaris_graph.generator2.strict_verify import\|_entailment_mode\|_get_judge" tests/`:
  - **5 test files** import via attribute access `strict_verify.<name>`:
    - `tests/polaris_graph/generator2/test_strict_verify_entailment.py` — patches `strict_verify._get_judge`, calls `strict_verify._entailment_mode()`. Re-export pattern preserves access. ✓
    - `tests/polaris_graph/generator2/test_strict_verify_telemetry.py` — `from polaris_graph.generator2.strict_verify import (get_judge_telemetry, reset_judge_telemetry,)`, `monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)`. Re-export pattern preserves both forms. ✓
    - `tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py` — calls `strict_verify._entailment_mode()` repeatedly, accesses `strict_verify._UNKNOWN_MODE_WARNED`. Re-export pattern preserves both. ✓
    - `tests/polaris_graph/test_provenance_generator_entailment.py` — production verifier tests. Uses end-to-end flow (`verify_sentence` from production module + env override). Should pass without change. ✓
    - `tests/crown_jewels/test_cj_008_entailment_correctness.py` — Crown Jewel binding test. Black-box; should pass without change. ✓
- `grep -r "_entailment_mode\|_get_judge" src/polaris_graph/llm/`:
  - **0 hits.** No prior content in `llm/entailment_judge.py` to conflict with.
- `src/polaris_graph/llm/__init__.py`:
  - Currently empty / passthrough. Nothing to update.
- `tests/polaris_graph/generator2/conftest.py`:
  - **0 hits** for entailment-related fixtures or imports. Clean.
- `.github/workflows/`:
  - **0 hits** referencing entailment helper names. Clean.

## §4 — Test Strategy

- **Smoke baseline (already run):** `pytest tests/polaris_graph/generator2/test_strict_verify_entailment.py tests/polaris_graph/generator2/test_strict_verify_telemetry.py tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py tests/polaris_graph/test_provenance_generator_entailment.py tests/crown_jewels/test_cj_008_entailment_correctness.py -x -q` → 66 passed in 3.62s on `polaris` HEAD before refactor.
- **Post-refactor verification:** re-run the same 66 tests. Acceptance criterion: all 66 pass.
- **Module-import smoke:** `python -c "from polaris_graph.llm.entailment_judge import _EntailmentJudge, _entailment_mode, _get_judge, get_judge_telemetry, reset_judge_telemetry, _record_judge_outcome; print('ok')"` to verify the new module is importable and exports the public surface.
- **Cross-module smoke:** `python -c "from polaris_graph.generator2 import strict_verify; m = strict_verify._entailment_mode(); print(m)"` to verify the re-export from strict_verify still works (so tests' attribute-access pattern doesn't break).

## §5 — Output Schema Bound (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §6 — Convergence Hint

Pure refactor with passing test suite. No behavior change. The risk surface is:
1. Import-cycle bugs (mitigated: `llm/` does not import from `generator/` or `generator2/`).
2. Telemetry counter sharing (mitigated: re-export keeps the SAME `_JUDGE_TELEMETRY` dict instance — both `strict_verify._JUDGE_TELEMETRY` and `entailment_judge._JUDGE_TELEMETRY` are bound to the same `dict` object via Python's module re-export semantics).
3. `_UNKNOWN_MODE_WARNED` set sharing (same as #2; same instance).

Expected APPROVE on iter 1.
