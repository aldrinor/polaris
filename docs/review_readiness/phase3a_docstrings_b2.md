# Phase 3A — contract/API/public docstrings (batch 2)

**Status: PREPARED, NOT COMMITTED — validate gate not fully satisfied in this
environment.** 47 docstrings drafted across 19 files on a fileset disjoint from
batch 1 (compare/, memory/, benchmark/, charts/, queue/middleware/, followup/,
sycophancy/, templates/, regression_lab/, anti_sycophancy/). Pure documentation
intent — zero behavior change.

## What was verified (deterministic, in-environment)

1. **Docstring-stripped AST equivalence — 19/19 PASS.** For every changed file
   the working-tree AST, with every Module/ClassDef/FunctionDef/AsyncFunctionDef
   leading string-literal removed, is identical to the same strip of `HEAD`. The
   only textual delta the AST admits is docstrings. Diff is additive only: 465
   added lines, **0 removed** source lines.

2. **Independent `__doc__`-consumer audit — 0 load-bearing, 0 reverted.** All 47
   new docstrings checked for a runtime consumer:
   - No `.__doc__` / `inspect.getdoc` reads anywhere in `src/`.
   - No `doctest` usage in `src/`.
   - None of the 19 changed files import `typer` / `click` / `argparse` /
     `fastapi` (so no function `__doc__` becomes CLI/OpenAPI help text).
   - No pydantic model in the changed files sets
     `use_attribute_docstrings=True`; class-level docstrings never become
     pydantic field descriptions. The changed models (BenchmarkQuestion,
     DimensionScore, SystemAnswer, FollowUpRequest, ForestPlotPoint,
     ComparisonRow, TimelinePoint, ClaimDiff*, Jurisdictional*,
     RegressionLabReport, SycophancyVerdict) expose the new text only through
     `help()`/pydoc — intended documentation exposure, not a runtime dependency.

3. **Per-claim accuracy spot-check — accurate.** Sampled docstrings verified
   against their bodies, e.g.:
   - `coverage_scorer.score_response_coverage`: "prefers expected_pico_keywords
     else expected_anchors; all-or-nothing case-insensitive substring; 0.0 when
     both empty" — matches `targets = pico or anchors; all(t.lower() in lower)`.
   - `memory/store.recall`: "top-k token-count-cosine, highest first, bumps
     use_count + last_used_at on returned entries" — matches body exactly.
   - `templates/registry.load_template`: FileNotFoundError + pydantic
     ValidationError raises — matches.
   - `otel_propagate.*`: no-op-when-uninstalled + `_otel_token` stash/detach —
     matches.

4. **py_compile — clean** on all 19 changed files.

## Blocker — why this was NOT committed

The commit gate requires **all** of `ast_equivalence_all_pass`, `oracle_matches`,
`collection_ok`, **and** `codex=DOCS-SAFE`. Two are unmet in this environment:

- **oracle_matches — UNRESOLVED (not attributable to this batch).** Running the
  governing oracle (`tests/oracle/acceptance_portable.py --replay`, frozen LLM +
  retrieval cassettes, golden `9c0a3d438da9…`) fails with a cassette MISS on the
  very first request (`generate_structured call_id='0' not in acceptance_llm.jsonl`).
  The **identical failure reproduces on clean `HEAD` with the docstrings stashed**,
  proving it is a pre-existing harness/cassette↔`outline_agent.py` mismatch in this
  checkout, **not** a behavior change from the batch-2 docstrings (which the AST
  proof independently rules out). But it means a *passing, byte-identical* oracle
  replay could not be produced here, so `oracle_matches=true` cannot be
  affirmatively established in this environment.

- **codex=DOCS-SAFE — NOT OBTAINED for batch 2.** The only codex verdict on disk
  is batch 1's stale **DOCS-REVISE** about `get_pin_by_date` in `api/pins.py` — a
  file not in this batch. No batch-2 codex DOCS-SAFE review exists.

Per the standing rule (commit only if validate passed AND codex=DOCS-SAFE; else
commit nothing and report the blocker), the working tree was left staged-clean and
no commit was made. The `tests/oracle/` overlay remained untracked and unstaged.

## To unblock

1. Reproduce a passing oracle replay (`--replay` byte-identical to
   `9c0a3d438da9…`, both controls valid) in an environment whose cassettes match
   the current `outline_agent.py`, OR re-record the golden and confirm it is
   unchanged by the docstrings.
2. Run the batch-2 codex DOCS-SAFE gate over this src-only diff and obtain
   DOCS-SAFE.
3. Then stage explicit paths (`git add src/` for the 19 files, then
   `git add docs/review_readiness/phase3a_docstrings_b2.md`), verify
   `git diff --cached --name-only | grep -c tests/oracle` is 0, and commit.
