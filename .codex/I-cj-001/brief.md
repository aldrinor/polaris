# Codex Brief Review — I-cj-001 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1-CJ001-IMPORT-PATH**: imports switched to `from src.polaris_graph.llm.openrouter_client import check_family_segregation` (matching the existing convention in `tests/polaris_graph/test_regression_pg_lb_sa_02_defects.py`). Dropped unused `family_from_model` import.
- **P2-CJ001-AMBIENT-OVERRIDES**: every "without override" test now passes `generator_override=""` and `evaluator_override=""` explicitly so ambient `PG_*_FAMILY_OVERRIDE` env state cannot mask the assertion.
- **P2-CJ001-TODO-WORDING**: registry doc rows for cj-002..007 now read `Pending — issued in subsequent CJ Issues` (no TODO/FIXME hygiene marker).



```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-001 — Two-family evaluator test. Crown Jewel side-track. Scope: test asserts `check_family_segregation` raises on violation. Acceptance: test green; fixture violation triggers raise. LOC estimate 80.
- **Substrate today:**
  - `src/polaris_graph/llm/openrouter_client.py` ships `family_from_model()` + `check_family_segregation()` (lines 269-339). Recognizes 10 families (deepseek, qwen, glm, llama, gemma, mistral, kimi, openai, anthropic, google-closed). Raises RuntimeError on (a) unknown family without override, (b) same family.
  - Existing tests in `tests/polaris_graph/test_regression_pg_lb_sa_02_defects.py` (test_phase_1c_*) cover the function. They live in a regression-defect module; not visible as a Crown Jewel binding.
- **Honest framing per CLAUDE.md §9.4:** ship a dedicated `tests/crown_jewels/test_cj_001_two_family_segregation.py` that pins the invariant from CLAUDE.md §9.1.1: "Two-family evaluator: generator and evaluator MUST be from different training lineages." Crown Jewel naming is the *registry surface* — when a future PR breaks this invariant, the failing test is unambiguously labeled `test_cj_001_two_family_segregation`. The substrate exists; this PR ships the binding.

## Plan

### `tests/crown_jewels/__init__.py` (NEW, empty)

### `tests/crown_jewels/test_cj_001_two_family_segregation.py` (NEW, ~70 LOC, 5 tests)

```python
"""Crown Jewel I-cj-001 — Two-family evaluator invariant.

Per CLAUDE.md §9.1.1: generator and evaluator MUST be from different
training lineages. polaris_graph.llm.openrouter_client.check_family_
segregation raises RuntimeError at construction-time when violated.

These tests are the binding registry: a future PR that weakens the
segregation gate causes one of these tests to fail under a clearly
named 'test_cj_001_*' identifier.
"""

from __future__ import annotations
import pytest
from src.polaris_graph.llm.openrouter_client import check_family_segregation


def test_cj_001_different_families_pass() -> None:
    gen, ev = check_family_segregation(
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
        generator_override="", evaluator_override="",
    )
    assert (gen, ev) == ("deepseek", "qwen")


def test_cj_001_same_family_raises() -> None:
    with pytest.raises(RuntimeError, match=r"same training-lineage family"):
        check_family_segregation(
            generator_model="qwen/qwen3-32b",
            evaluator_model="qwen/qwen3-8b",
            generator_override="", evaluator_override="",
        )


def test_cj_001_unknown_generator_without_override_raises() -> None:
    with pytest.raises(RuntimeError, match=r"generator model.*does not"):
        check_family_segregation(
            generator_model="unknown-vendor/some-model",
            evaluator_model="qwen/qwen3-8b",
            generator_override="", evaluator_override="",
        )


def test_cj_001_unknown_evaluator_without_override_raises() -> None:
    with pytest.raises(RuntimeError, match=r"evaluator model.*does not"):
        check_family_segregation(
            generator_model="deepseek/deepseek-v3.2-exp",
            evaluator_model="unknown-vendor/some-model",
            generator_override="", evaluator_override="",
        )


def test_cj_001_explicit_override_bypasses_unknown() -> None:
    gen, ev = check_family_segregation(
        generator_model="some-finetune/model",
        evaluator_model="another-finetune/model",
        generator_override="deepseek",
        evaluator_override="qwen",
    )
    assert (gen, ev) == ("deepseek", "qwen")
```

### `docs/crown_jewels.md` (NEW, ~30 LOC) — registry doc

Brief table mapping each I-cj-NNN to (a) the CLAUDE.md §9.1 invariant pinned, (b) the test file path, (c) the bound source-of-truth function. I-cj-001..007 entries (rows for cj-002..007 marked "TODO — issued in subsequent CJ Issues").

## Risks for Codex Red-Team

1. **Substrate-honest** — module docstring + brief explicit: this is binding registry of an existing invariant, NOT new functionality. The test surface is intentionally redundant with `test_phase_1c_*` in the regression module — the value is the unambiguous CJ-named test path so a future regression is loudly labeled.
2. **§9.4 hygiene** — clean. No try/except: pass; no mock; no magic numbers (raw model names from production .env defaults); no sleep; no TODO/FIXME.
3. **CHARTER §3 LOC cap** — ~100 LOC (70 tests + 30 doc). Under 200.
4. **Override semantics** — test 5 demonstrates the documented escape hatch (`PG_*_FAMILY_OVERRIDE`) so Codex can verify the mitigation pattern is preserved.

## Acceptance criteria

1. New `tests/crown_jewels/test_cj_001_two_family_segregation.py` with 5 tests covering: (a) different-family pass, (b) same-family raise, (c) unknown-gen-no-override raise, (d) unknown-eval-no-override raise, (e) explicit override bypass.
2. New `docs/crown_jewels.md` registry pointing the I-cj-NNN slot to the test path + invariant + bound function.
3. All 5 tests pass.
4. CHARTER §3 LOC cap respected.

**Forced enumeration:** before verdict, write one line per criterion 1-4.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
