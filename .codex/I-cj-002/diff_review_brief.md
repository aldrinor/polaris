# Codex Diff Review — I-cj-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-002 — Provenance token Crown Jewel test. Brief APPROVE'd iter 2 (P1 collection blocker fixed via conftest.py; P2 unused imports dropped).
- **Diff under review:** `.codex/I-cj-002/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/conftest.py` (~10 LOC, prepends src/ to sys.path)
  - NEW `tests/crown_jewels/test_cj_002_provenance_tokens.py` (~70 LOC, 6 tests)
  - MODIFY `docs/crown_jewels.md` (~1 row, I-cj-002 path + bound function)

## Acceptance criteria (from brief APPROVE iter 2)

1. ✅ 6 tests pass locally.
2. ✅ Registry doc row updated to correct generator2/provenance path.
3. ✅ conftest.py adds src/ to sys.path so the deep `polaris_graph.retrieval2.evidence_pool` re-import inside `provenance.py` resolves.
4. ✅ ~80 LOC under 200.

## Red-team checklist

1. **conftest scoping** — file is under `tests/crown_jewels/` so the sys.path mutation only fires when running tests from that subdir. Doesn't pollute the broader pytest path setup.
2. **Test independence** — pure-function tests on regex parser; no I/O, no LLM, no network.
3. **Match patterns** — `[#ev:src_001:10-25]`, `[#ev:s1:0-5]` align with the canonical format documented in `provenance.py:7`.
4. **Malformed tokens** — 5 distinct rejection cases cover non-numeric span, empty source_id, wrong tag, missing #, single-int span.
5. **§9.4 hygiene** — clean.

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
