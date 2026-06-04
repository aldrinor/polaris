HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# Brief — I-cap-001 (#1059) PART A: un-throttle the 3 hardcoded depth caps to Tier-A SOTA

## 0. Context + operator authorization
Operator audited POLARIS's silent capability downgrades (#1059) and APPROVED "lift ALL to SOTA" for the
1000-URL beat-both run. Most Tier-A caps are ALREADY env-overridable (set at run time via the env slate);
this PR is the small CODE part — the 3 caps whose DEFAULTS were below SOTA. Per the operator's binding
no-downgrade directive: the DEFAULT must be full capability (not throttled when the env is unset), and per
LAW VI every cap must be env-overridable.

## 1. The 3 caps + current state (verified)
1. **`DEFAULT_MAX_SUBQUERIES`** (`src/polaris_graph/retrieval/query_decomposer.py:36`) = `6`, hardcoded, NOT
   env-overridable. Used as the default of `decompose_question(question, *, max_subqueries=DEFAULT_MAX_
   SUBQUERIES)`; the benchmark caller (`run_honest_sweep_r3.py:1968 decompose_question(q["question"])`)
   does NOT pass `max_subqueries`, so it uses the default 6. → bump to 15 + make env-overridable.
2. **`section_max_tokens`** — ALREADY env-overridable at the call site
   (`run_honest_sweep_r3.py:3688 section_max_tokens=int(os.environ.get("PG_SECTION_MAX_TOKENS","2400"))`),
   but the DEFAULT fallback is `2400` (throttled when the env is unset). → bump the fallback to `5000`.
3. **`limitations_max_tokens`** (`multi_section_generator.py:4064`) default `400`, and the benchmark caller
   does NOT pass it (uses the 400 default). → add a call-site env override defaulting to `1500` (mirrors
   the `section_max_tokens` pattern; does not change the function's own default, which other callers keep).

## 2. The diff (3 edits, ~6 LOC)
1. `query_decomposer.py`: add `import os` (currently only `import re`); change
   `DEFAULT_MAX_SUBQUERIES = 6` → `DEFAULT_MAX_SUBQUERIES = int(os.getenv("PG_MAX_SUBQUERIES", "15"))`.
2. `run_honest_sweep_r3.py:3688-3690`: change the `PG_SECTION_MAX_TOKENS` fallback `"2400"` → `"5000"`.
3. `run_honest_sweep_r3.py` (same `generate_multi_section_report(...)` call, ~L3690): add
   `limitations_max_tokens=int(os.environ.get("PG_LIMITATIONS_MAX_TOKENS", "1500"))`.

## 3. Invariants
- **No-downgrade default:** each cap's DEFAULT is now SOTA (15 / 5000 / 1500); a run with NO env set is at
  full capability, not throttled.
- **LAW VI env-overridable:** each cap reads `PG_MAX_SUBQUERIES` / `PG_SECTION_MAX_TOKENS` /
  `PG_LIMITATIONS_MAX_TOKENS` so the operator can tune without code.
- **Faithfulness-untouched:** these caps only widen query breadth + raise generation token budgets; the
  strict_verify + 4-role seam still drop any unsupported sentence. Raising the prose budget does NOT relax
  verification — unverifiable extra prose is dropped, not shipped.
- **No new magic numbers beyond the operator-approved 15/5000/1500.**

## 4. Files I have ALSO checked
- `research_planner.py:197` has a SEPARATE `DEFAULT_MAX_SUBQUERIES = 40` (V30 planner path) — NOT the
  query_decomposer cap; untouched (already ≥ SOTA).
- `multi_section_generator.py:4056 section_max_tokens: int = 2400` — the function default; the benchmark
  passes the env value so this PR does not need to touch the signature (the call-site fallback is the
  effective default). Left as-is to avoid changing other callers; only the call-site fallback is raised.
- `multi_section_generator.py:4382 max_tokens=max(section_max_tokens, 6000)` — regeneration path already
  floors at 6000; unaffected.

## 5. Acceptance (GREEN)
- The 3 caps default to 15 / 5000 / 1500 and are each env-overridable.
- A benchmark run with no env set uses the SOTA defaults (no silent throttle).
- Existing tests green (query_decomposer + dr_benchmark import smoke); no signature break.
- ≤ ~10 LOC.

## 6. Smoke plan (offline)
1. `python -c` import `query_decomposer`; assert `DEFAULT_MAX_SUBQUERIES == 15` (no env) and `== 9` with
   `PG_MAX_SUBQUERIES=9`.
2. `ast.parse` / `py_compile` `run_honest_sweep_r3.py`; confirm the call passes
   `limitations_max_tokens` + the 5000 fallback.
3. `pytest` any query_decomposer tests + a dr_benchmark import smoke.

## 7. Question for the gate
- Bumping the call-site `section_max_tokens` fallback to 5000 (vs touching the function default 2400):
  correct minimal-blast-radius choice, or do you want the function default raised too for non-benchmark
  callers? (I chose call-site only — the benchmark is the only SOTA consumer; other callers keep 2400.)
