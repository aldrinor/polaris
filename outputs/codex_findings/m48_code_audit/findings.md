# M-48 Code Audit

Verdict: **BLOCKED**

Scope reviewed: commit `5e0b447` only, against `outputs/audits/v27/fix_plan_v28.md` M-48 pass-2 and the approved pass-2 review.

## Findings

**BLOCKER - Population-scope labeling and preflight coverage inspect `title`, but live evidence rows do not have a `title` key.**

`label_rows_with_population_scope()` matches anchors only against `row.get("title")` in `src/polaris_graph/retrieval/primary_trial_expander.py:275`. The live retriever builds evidence rows with the search/title text stored as `statement`, not `title`, in `src/polaris_graph/retrieval/live_retriever.py:1157`. As wired in `scripts/run_honest_sweep_r3.py:611`, this means the M-48 labeler will normally label zero live retrieval rows, so SURMOUNT-1/3/4 will not receive `indirect_for_t2d=True` before selection/generation.

The same schema mismatch breaks the new retrieval preflight. `scripts/v28_retrieval_preflight.py:139` calls `_m42e_detect_primary_for_anchor(r, anchor)`, and that detector also requires `row["title"]`; `scripts/v28_retrieval_preflight.py:143` and `:150` also read `title` directly for mention counts and examples. Against real `run_live_retrieval()` rows, primary coverage will report false negatives even when the candidate title is present in `statement`. This defeats the M-48 acceptance criterion of asserting >=1 primary row per anchor before the full sweep.

Required fix: normalize the live row schema or make the M-48/M-42e anchor detectors use a shared title accessor such as `title or statement or source_title`, then add fixture coverage using live-shaped rows (`statement` only). The sweep labeler should also be re-run after optional gap-triggered expansion if expanded rows can introduce SURMOUNT evidence.

## Non-Blocking Assessment

Variant schema handling is mostly sound. Non-string anchors/variants are skipped, empty/whitespace-only variants are rejected, anchor whitespace/quotes/backslashes are rejected, and embedded double quotes in variants are rejected. Interior whitespace in variants is correctly allowed because variants are free-text first-author/journal terms. Single quotes in variants are not a quoting hazard in the emitted query form.

Query emission matches the approved plan. `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS` is applied to the anchor list before variant expansion (`primary_trial_expander.py:332`), and emission alternates bare anchor then variant (`:337`, `:340`). Slugs without a variants section retain the original anchor-only behavior.

The YAML content satisfies the requested SURMOUNT labels: SURMOUNT-2 is `direct`, while SURMOUNT-1/3/4 are `indirect_for_t2d`; SURPASS entries are direct. The substring over-tagging risk for future `SURMOUNT-11` titles is real but acceptable under the stated limitation. If this becomes generalized beyond one-digit trial names, switch to a boundary-aware regex.

The preflight exit-code contract is conceptually right: configuration errors return 2, coverage failures return 1, and all-covered returns 0. The report schema is useful enough for operators, though it would be stronger with emitted query counts and matched title/statement snippets after the schema fix. `amplified = [args.question] + ...` duplicates the base query because `run_live_retrieval()` already prepends `research_question`; this is minor budget noise, not a blocker.

The sweep integration is placed before evidence selection, which is the right stage, but the schema mismatch currently makes it a no-op for live rows.

## Verification

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m48_anchor_variants_and_scope.py tests/polaris_graph/test_m35_primary_trial_expander.py -q` passed: 57 tests. Pytest emitted only the existing cache permission warning for `.pytest_cache`.
