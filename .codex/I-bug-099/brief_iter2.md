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

## §1 — Iter 1 finding + iter 2 disposition

**Iter 1 verdict: REQUEST_CHANGES, 1 P1, 1 P2.**

| Iter-1 finding | Severity | Iter-2 fix |
|---|---|---|
| Production tests patch `strict_verify._get_judge`. After moving definitions to `polaris_graph.llm.entailment_judge` and changing `provenance_generator.py` to import directly from there, monkeypatching strict_verify wouldn't propagate. 66 tests would break. | **P1** | **CHOSEN: Option B — preserve test patch surface.** Provenance_generator's lazy import target is **UNCHANGED** (still goes through `polaris_graph.generator2.strict_verify`). strict_verify.py re-exports the moved symbols so attribute-access pattern (`strict_verify._get_judge`, `strict_verify._JUDGE_TELEMETRY`, etc.) is preserved. monkeypatch.setattr on strict_verify still affects all consumers (verify_sentence + provenance_generator both go through strict_verify). |
| Same re-export limitation affects `_UNKNOWN_MODE_WARNED` dedup set: `monkeypatch.setattr(strict_verify, "_UNKNOWN_MODE_WARNED", set(), raising=False)` rebinds strict_verify's attribute but _entailment_mode (defined in entailment_judge.py) reads entailment_judge._UNKNOWN_MODE_WARNED. | P2 (related to P1, same root cause) | **FIXED.** `_DEFAULT_MODE`, `_UNKNOWN_MODE_WARNED`, and `_entailment_mode()` STAY in strict_verify.py. Only the JUDGE class + lazy singleton + telemetry counters move to entailment_judge.py. |

## §2 — Revised Proposed Change

| File | Δ | Notes |
|---|---|---|
| `src/polaris_graph/llm/entailment_judge.py` | NEW (+~155 lines) | Move ONLY: `_DEFAULT_ENTAILMENT_MODEL`, `_ENTAILMENT_TIMEOUT_S`, `_ENTAILMENT_PROMPT`, `_EntailmentJudge` class, `_JUDGE_SINGLETON` global, `_get_judge()` lazy singleton, `_JUDGE_TELEMETRY` dict, `get_judge_telemetry()`, `reset_judge_telemetry()`, `_record_judge_outcome()`. |
| `src/polaris_graph/generator2/strict_verify.py` | -~155 lines, +~10 lines | Replace inline definitions with `from polaris_graph.llm.entailment_judge import (…)`. Module attribute access still works for monkeypatch (strict_verify._get_judge, strict_verify._JUDGE_TELEMETRY, etc. all bind to the same objects via re-export). **KEEP** `_DEFAULT_MODE`, `_UNKNOWN_MODE_WARNED`, `_entailment_mode()` in strict_verify.py because tests rebind these via `monkeypatch.setattr(strict_verify, "_UNKNOWN_MODE_WARNED", set())` and the function reading them must see the rebind. |
| `src/polaris_graph/generator/provenance_generator.py` | **UNCHANGED.** | Still lazy-imports from `polaris_graph.generator2.strict_verify`. Per Codex iter-1 P1: this preserves test patch propagation. The "single import path" goal is achieved at the symbol-definition level (canonical home is `polaris_graph.llm.entailment_judge`), not at the import-site level. |

**Net: ~+165 / -155 lines. Net-new module file. Tests unchanged. Behavior unchanged.**

## §3 — Why this design preserves all 66 tests

**Test 1: `tests/polaris_graph/generator2/test_strict_verify_telemetry.py`** does `monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)`. After refactor:
- `strict_verify._get_judge` is the same object as `entailment_judge._get_judge` (re-export).
- monkeypatch rebinds `strict_verify._get_judge` to `fake`.
- `verify_sentence` (inside strict_verify.py) calls `_get_judge()` — name lookup uses strict_verify globals → reads `fake`. ✓
- `provenance_generator.py:755` lazy-imports `_get_judge` from strict_verify. Lazy import resolves AT CALL TIME, after monkeypatch took effect → picks up `fake`. ✓

**Test 2: `tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py`** does `monkeypatch.setattr(strict_verify, "_UNKNOWN_MODE_WARNED", set(), raising=False)`. After refactor:
- `_UNKNOWN_MODE_WARNED` STAYS in strict_verify.py (per iter-2 P2 fix).
- monkeypatch rebinds strict_verify._UNKNOWN_MODE_WARNED to a fresh set.
- `_entailment_mode()` (inside strict_verify.py) reads `_UNKNOWN_MODE_WARNED` from strict_verify globals → reads the fresh set. ✓

**Test 3: `tests/polaris_graph/test_provenance_generator_entailment.py`** does `monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)` where `_gen2 = polaris_graph.generator2.strict_verify`. Same as Test 1. ✓

**Test 4: `tests/crown_jewels/test_cj_008_entailment_correctness.py`** is black-box (calls `verify_sentence_provenance` end-to-end with PG_STRICT_VERIFY_ENTAILMENT env override). No monkeypatch on entailment helpers. Behavior preserved. ✓

**Test 5: `tests/polaris_graph/generator2/test_strict_verify_entailment.py`** uses `from polaris_graph.generator2.strict_verify import (…)` and patches `strict_verify._get_judge`. Same as Test 1. ✓

## §4 — Files I have ALSO checked and they're clean (re-verified iter 2)

- `src/polaris_graph/generator2/generator.py:43` — imports `verify_sentence` etc. from `strict_verify`. Does NOT import any entailment helper. ✓
- `src/polaris_graph/llm/__init__.py` — empty/passthrough. ✓
- `src/polaris_graph/llm/openrouter_client.py` — no entailment helper imports. The new `entailment_judge.py` imports `check_family_segregation` from this file (lazy import inside `_EntailmentJudge.__init__`), preserving the §9.1.1 family-segregation invariant. Lazy import avoids circular concerns. ✓
- `tests/polaris_graph/generator2/conftest.py` — no entailment fixtures. ✓
- `.github/workflows/` — no entailment helper references. ✓
- Smoke test on `bot/I-bug-099` HEAD (= `polaris` HEAD currently): `pytest tests/polaris_graph/generator2/test_strict_verify_entailment.py tests/polaris_graph/generator2/test_strict_verify_telemetry.py tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py tests/polaris_graph/test_provenance_generator_entailment.py tests/crown_jewels/test_cj_008_entailment_correctness.py -x -q` → 66 passed in 3.62s baseline. Will re-verify after refactor.

## §5 — Test Strategy

- **Smoke baseline:** captured (66/66 pass on `polaris` HEAD).
- **Post-refactor verification:** re-run the same 66 tests; acceptance is 66/66 unchanged.
- **Module-import smoke:** `python -c "from polaris_graph.llm.entailment_judge import _EntailmentJudge, _get_judge, get_judge_telemetry, reset_judge_telemetry, _record_judge_outcome, _JUDGE_TELEMETRY; print('ok')"`.
- **Re-export smoke:** `python -c "from polaris_graph.generator2 import strict_verify; assert callable(strict_verify._get_judge) and isinstance(strict_verify._JUDGE_TELEMETRY, dict); print('ok')"`.

## §6 — Output Schema Bound (per CLAUDE.md §8.3.9)

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

Iter-1 P1 + P2 are addressed by **scoping the move**:
- Things that are pure data/lazy-singleton (judge class, telemetry counters) → MOVE.
- Things that are tightly coupled to the test rebinding pattern (mode resolver + WARNED set) → KEEP in strict_verify.

This is a smaller refactor than iter 1 proposed, but it's the right one. "Single import path" is achieved at the canonical-definition level for the judge logic itself; mode resolution stays generator2-internal where it has always lived.

Expected APPROVE on iter 2.
