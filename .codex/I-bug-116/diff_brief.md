# Codex DIFF review — I-bug-116 / GH #556: `_env_float` non-finite guard

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #556 — `git diff origin/polaris...HEAD` excluding
`.codex/I-bug-116/` and `outputs/audits/I-bug-116/` (the canonical diff in
`.codex/I-bug-116/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-bug-116/brief.md` (brief review APPROVE iter 2).

This is a diff review — the code IS now applied in the workspace. Verify the
applied diff against the brief.

## 2. The diff (2 files)

- **`src/polaris_graph/retrieval/live_retriever.py`** — `import math` added to
  the stdlib block (`logging` / `math` / `os` alphabetical lead); `_env_float`
  last line `value if value > 0 else default` →
  `value if math.isfinite(value) and value > 0 else default`; docstring
  expanded to explain the non-finite → `OverflowError` hazard. `_env_int`
  unchanged.
- **`tests/polaris_graph/test_live_retriever_env_knobs.py`** (new, 24
  parametrized cases) — non-finite rejection (`inf`/`-inf`/`nan`/`Infinity`/
  `+inf`/`-Infinity`), finite-positive acceptance, garbage/non-positive
  fallback, unset-default for `_env_float`; `_env_int` ValueError-path +
  positive-acceptance coverage.

## 3. Verify against the brief

1. `_env_float` returns `default` for `inf`/`-inf`/`nan` and still returns a
   valid finite positive override / falls back on `<= 0` and on garbage.
2. `math` is imported once, in the stdlib group; no duplicate import.
3. `_env_int` is genuinely untouched (the brief's claim that `int("inf")`
   raises `ValueError` is correct — confirm no change was needed).
4. No call site of `_env_float` (`live_retriever.py:628`, `:1384`) needs a
   change — both now receive a finite value.
5. The test imports the helpers and uses `monkeypatch.setenv`; it does not
   require network or a live backend.

## 4. Files I have ALSO checked and they're clean

- `_env_float` call sites: `live_retriever.py:628` + `:1384` — finite after
  the fix, no change needed.
- `src/polaris_graph/audit_ir/v30_runner.py:152 _read_env_float` — separate
  function, different file, out of #556 scope (different consequence class —
  see brief §4). Deliberately not touched.
- No existing test referenced `_env_float`/`_env_int` before this PR — the new
  file introduces no collision.

## 5. Test state

`python -m pytest tests/polaris_graph/test_live_retriever_env_knobs.py` →
24/24 pass offline. `ast.parse` clean.

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
