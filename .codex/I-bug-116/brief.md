# Codex BRIEF review — I-bug-116 / GH #556: `_env_float` accepts non-finite env values

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review (read first)

This is the **brief** review, not the diff review. Per CLAUDE.md §3.0 there
are two separate Codex calls per Issue: (a) **brief** review — APPROVE the
*plan* (acceptance-criteria correctness, fix approach, test adequacy, scope);
(b) **diff** review — later, APPROVE the *applied code* against this brief.

The working tree is therefore **intentionally unmodified** at this stage —
`live_retriever.py` still has `value if value > 0 else default`, `math` is not
yet imported, and `test_live_retriever_env_knobs.py` does not yet exist. That
is the expected pre-implementation state, **not a defect of this brief**.
Implementation happens only after this brief is APPROVE'd; the separate diff
review (`.codex/I-bug-116/diff_brief.md` + `codex_diff.patch`) is where you
verify the applied `math.isfinite` guard and the regression test file.

iter-1 raised exactly this as a P1 ("fix not present in the workspace") —
that observation is correct but is a property of the brief stage, not a brief
defect. Please evaluate §2-§4 below as a *plan*: is the fix approach right, is
`_env_int` correctly excluded, is the scope boundary (`_read_env_float` left
out) sound, is the test coverage adequate?

---

## 1. Issue

GH #556 (I-bug-116) — a Codex diff-review P2 carried over from PR #555.

`_env_float` in `src/polaris_graph/retrieval/live_retriever.py:590-596` accepts
positive **non-finite** floats. `PG_OPENALEX_ENRICH_DEADLINE=inf` →
`float("inf")` → `inf > 0` is `True` → `inf` is returned →
`threading.Thread.join(timeout=inf)` raises
`OverflowError: timestamp out of range for platform time_t` on Windows,
instead of the intended fall-back to the finite default.

Severity: env-misconfiguration hygiene — **non-blocking under defaults**
(default `45.0` is finite); only a pathological operator override triggers it.

## 2. The fix (1 logic line + 1 import)

`src/polaris_graph/retrieval/live_retriever.py`:

- Add `import math` to the stdlib import block (currently `logging`, `os`,
  `asyncio`, `re`, `threading`, `time` — insert `math` so `logging / math /
  os` lead alphabetically).
- `_env_float` last line:
  ```
  -    return value if value > 0 else default
  +    return value if math.isfinite(value) and value > 0 else default
  ```
  `math.isfinite` is `False` for `inf`, `-inf`, `nan` → all three fall back
  to `default`. `nan > 0` is already `False` (so `nan` was handled), but
  `inf`/`-inf` were not — `isfinite` covers all three uniformly.

`_env_int` is **not** changed: `int("inf")` / `int("nan")` raise `ValueError`,
already caught by the existing `except (TypeError, ValueError)` → `default`.
(Confirmed by reading lines 599-605.)

## 3. Test (regression)

New `tests/polaris_graph/test_live_retriever_env_knobs.py`:
- `_env_float` returns the default for `PG_*=inf`, `=-inf`, `=nan`,
  `=Infinity` (Python `float()` accepts these spellings).
- `_env_float` still returns a valid positive override (e.g. `=30.5` → `30.5`)
  and still falls back on garbage (`=abc`) and on `<= 0` (`=0`, `=-5`).
- `_env_int` returns the default for `=inf` / `=nan` (via the `ValueError`
  path) — pins the issue's claim that `_env_int` needs no change.
- Uses `monkeypatch.setenv`; imports the two helpers from
  `src.polaris_graph.retrieval.live_retriever`.

## 4. Files I have ALSO checked and they're clean

- Call sites of `_env_float`: `live_retriever.py:628`
  (`PG_OPENALEX_ENRICH_DEADLINE`, → `Thread.join` timeout) and `:1384`
  (`_loop_deadline = time.monotonic() + _env_float(...)`). Both receive a
  finite value after the fix; no call-site change needed.
- `_env_int` (`live_retriever.py:599`) — `int()` rejects `inf`/`nan` with
  `ValueError`; correct as-is.
- `src/polaris_graph/audit_ir/v30_runner.py:152 _read_env_float` — a
  **separate** function in a different file (feeds `cost_cap_usd` for the
  preflight surface). It also lacks a finiteness check, but: (a) it is out of
  #556's stated scope (`live_retriever._env_float` only), (b) an `inf` cost
  cap degrades to "no cap" rather than an `OverflowError` crash — different
  consequence class. Left untouched; flagged here as a possible separate
  follow-up, NOT folded in (scope discipline).
- No existing test references `_env_float`/`_env_int` (`grep tests/`), so the
  new file introduces no collision.

## 5. Test / smoke

`PYTHONPATH=. python -m pytest tests/polaris_graph/test_live_retriever_env_knobs.py`
+ `python -c "import ast; ast.parse(open('src/polaris_graph/retrieval/live_retriever.py').read())"`.

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
