HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
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

# DIFF gate — I-cap-002 feature 3/4 (#1060): agentic search as URL-DISCOVERY in the benchmark

DIFF gate. Review the committed code against the brief (`.codex/I-cap-002-agentic/brief.md`, brief-gate
APPROVE iter-2 in `codex_brief_verdict.txt`). Patch: `.codex/I-cap-002-agentic/codex_diff.patch` (branch
`bot/I-cap-002-agentic` on `bot/I-cap-002-depth`). **The #1 thing to red-team: the faithfulness contract —
can any agent summary/notebook field reach an evidence row?**

## What the diff does (5 files, +373)
1. **NEW `src/polaris_graph/retrieval/agentic_url_harvester.py`** (stdlib + `canonical_source_url`):
   - `harvest_agentic_urls(result, cap)` — ordered DETERMINISTIC union of `web_results` then
     `academic_results` `url` fields, then `agentic_url_accumulator`; dedup BY `canonical_source_url` but
     RETURNS the original fetchable URL; NEVER reads `agentic_research_notebook`/summaries/snippets;
     cap<=0 → []; robust to missing keys. (brief-gate iter-2 P2.1 canonical-key/original-value + P2.3
     deterministic ordered union.)
   - `merge_seed_url_evidence(staged_sources, staged_rows, new_sources, new_rows)` — pure dedup-by-`.url`
     source merge + only-accepted-source rows + global `ev_###` renumber from `len(staged_rows)`; copies
     inputs (no mutation); returns `(sources, rows, accepted_src, accepted_rows)`. (brief-gate iter-2 P2.2.)
2. **`run_honest_sweep_r3.py`** — agentic block AFTER the deepener (L~2505), BEFORE the retrieval-trace
   flush, flag-gated `PG_AGENTIC_SEARCH_IN_BENCHMARK` default OFF:
   - Forces `searcher.PG_AGENTIC_CONTENT_READING_ENABLED = False` (restored in `finally`) so the only LLM
     work is per-round analysis; books a conservative envelope (`PG_AGENTIC_MAX_ROUNDS ×
     PG_AGENTIC_PER_ROUND_COST_USD`) into `_RUN_COST_CTX` and calls `check_run_budget(0)` BEFORE the try
     (so a `BudgetExceededError` PROPAGATES like STORM, not swallowed by the fail-open except).
   - Client built AFTER the precheck; `execute_agentic_search` run in an isolated `copy_context()` task;
     `harvest_agentic_urls(...)` then `del _ag_result` immediately; client + both flags restored in
     `finally`.
   - Discovered URLs fetched via `run_live_retrieval(seed_urls=…, seed_only=True)`; `merge_seed_url_evidence`
     + `compute_tier_distribution`/`check_completeness`(gated on `not _use_research_planner`)/
     `assess_corpus_adequacy` recompute, then COMMIT to `retrieval`/`dist`/`completeness`/`adequacy`.
     Fail-open on the loop AND on the merge.
3. **`run_gate_b.py`** — `os.environ.setdefault("PG_AGENTIC_SEARCH_IN_BENCHMARK", "1")`.
4. **Tests** — harvester (URLs-only; notebook IGNORED; canonical dedup keeps original; cap; malformed-safe)
   + merge (dup-URL rejection; renumber from staged base; no inflation; no input mutation) +
   activation test asserts the flag == "1".

## Red-team checklist — please confirm
- **Faithfulness:** trace every field consumed from the agentic result. Is it ONLY URLs? Can a notebook
  summary / snippet reach `direct_quote` or any evidence row? (The block harvests then `del`s the result.)
- **Budget airtight:** with `PG_AGENTIC_CONTENT_READING_ENABLED=False`, is the per-round-analysis the only
  remaining LLM call path in `execute_agentic_search`? Does the envelope+precheck-before-try guarantee the
  cap can't be breached, and does `BudgetExceededError` correctly propagate (NOT caught by the agentic
  except)?
- **Atomic merge:** does `merge_seed_url_evidence` + the inline recompute-then-commit match the deepener's
  atomicity (a recompute error leaves the post-deepener corpus untouched)? Any id-collision / inflation
  path? (Evidence ids renumber from `len(staged_rows)`; only accepted-source rows are appended.)
- **Flag OFF → byte-unchanged:** with the flag unset, is the block fully skipped (corpus/manifest identical
  to feature-2 HEAD)?
- **Fail-open:** loop error, fetch error, AND merge error each leave the corpus untouched and let the run
  complete?
- **Scope/lifecycle:** are `_amplified_effective`, `compute_tier_distribution`, `check_completeness`,
  `assess_corpus_adequacy`, `protocol`, `_use_research_planner`, `retrieval` all in scope at the insertion
  point (the deepener directly above uses them)? Are the toggled module flags + client always restored/
  closed on every path?
- **LOC:** +373 (≈252 production: 130 sweep block + 116 harvester + 6 gate_b; 121 tests). This is one
  cohesive feature (harvester + wiring + activation are inseparable). Acceptable as a single PR (like the
  feature-2 depth PR at +344), or do you want it split (harvester module PR + wiring PR)?

## Smoke evidence (offline, already run)
- `pytest tests/polaris_graph/test_agentic_url_harvester.py tests/dr_benchmark/test_benchmark_stack_activation_meta007.py` → 10 passed.
- `pytest tests/dr_benchmark/` (full suite, exercises run_gate_b + run_one_query wiring) → 233 passed.
- `py_compile` + `ast.parse` on `run_honest_sweep_r3.py` → OK; `searcher` exposes the toggled constants +
  `execute_agentic_search`.
- (Live agentic discovery needs network + spend — that is the Tier-A VM run, not this offline gate.)

## Acceptance (GREEN)
Zero NOVEL/continuing P0, zero P1. The feature is flag-OFF-default + fail-open + budget-enveloped +
URL-discovery-only, so any residual concern about discovery breadth/cost tuning is at most P2.
