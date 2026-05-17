# Claude architect audit — I-bug-116 (#556)

**Issue:** GH #556 — `live_retriever._env_float` accepts non-finite env values.
**Branch:** `bot/I-bug-116-env-float-finite`
**Commit 1 (fix + test):** `aa8fe964`
**Brief:** `.codex/I-bug-116/brief.md` — Codex APPROVE iter 2 (iter 1
REQUEST_CHANGES was a brief-vs-diff stage misunderstanding; clarified, iter 2
APPROVE clean).

## 1. What shipped

| File | Change |
|---|---|
| `src/polaris_graph/retrieval/live_retriever.py` | `import math` added to the stdlib block; `_env_float` last line `value if value > 0 else default` → `value if math.isfinite(value) and value > 0 else default`; docstring updated to explain the non-finite hazard. |
| `tests/polaris_graph/test_live_retriever_env_knobs.py` (new) | 24 parametrized cases — non-finite rejection, finite-positive acceptance, garbage/non-positive fallback, unset-default for `_env_float`; `_env_int` ValueError-path + positive-acceptance coverage. |

## 2. Per-finding verification

- **VERIFIED — the #556 bug**: before the fix, `_env_float("PG_OPENALEX_
  ENRICH_DEADLINE", 45.0)` with the env set to `inf` returned `inf`
  (`float("inf")` parses, `inf > 0` is `True`). After the fix
  `math.isfinite(inf)` is `False` → returns `45.0`. Test
  `test_env_float_rejects_non_finite` covers `inf / -inf / nan / Infinity /
  +inf / -Infinity`.
- **VERIFIED — `nan` was partially covered before, now uniform**: `nan > 0` was
  already `False`, so `nan` fell back even pre-fix; `inf`/`-inf` did not.
  `math.isfinite` covers all three in one predicate.
- **VERIFIED — `_env_int` correctly unchanged**: `int("inf")` / `int("nan")` /
  `int("3.5")` raise `ValueError`, caught by the existing
  `except (TypeError, ValueError)` → default. Test
  `test_env_int_rejects_non_finite_and_non_int` pins this.
- **VERIFIED — call sites unaffected**: `_env_float` is used at
  `live_retriever.py:628` (`PG_OPENALEX_ENRICH_DEADLINE` → `Thread.join`
  timeout) and `:1384` (`time.monotonic() + _env_float(...)`). Both now
  always receive a finite value; no call-site change.

## 3. Test / smoke

`python -m pytest tests/polaris_graph/test_live_retriever_env_knobs.py` →
24/24 pass. `ast.parse` clean on both files.

## 4. Scope + residuals

- `src/polaris_graph/audit_ir/v30_runner.py:152 _read_env_float` is a separate
  function in a different file (feeds `cost_cap_usd` for the preflight
  surface) that also lacks a finiteness check. It is **out of #556's stated
  scope** (`live_retriever._env_float` only) and has a different consequence
  class (an `inf` cost cap degrades to "no cap", not an `OverflowError`
  crash). Left untouched; noted as a possible separate follow-up — NOT folded
  in (scope discipline).

## 5. Risk assessment

The change strictly narrows `_env_float`'s accepted domain (3 additional
inputs — `inf`/`-inf` plus the already-handled `nan` — now uniformly fall
back). Pure function; no behaviour change for any finite override. No
existing test references `_env_float`, so no regression surface.

## 6. Verdict

Implementation complete, faithful to the iter-2 APPROVE'd brief, 24/24 tests
green. Ready for Codex diff review.
