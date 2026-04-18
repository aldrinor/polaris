# POLARIS honest-rebuild — Codex code review brief

You are an independent code reviewer. The primary author (Claude Sonnet 4.6 via Claude Code) claims this repo is ready for full-scale production runs. Your job is to stress-test that claim **by reading the actual code**, not by trusting the commit messages or test suite.

## Scope

Focus exclusively on the honest-rebuild pipeline. Ignore archived code under `archive/2026-Q2_deprecated_phases/` and the legacy `src/phases/`, `src/orchestration/`, `src/agents/citefirst/` paths.

**In-scope modules (read fully):**
- `src/polaris_graph/nodes/` — scope_gate, corpus_approval_gate, corpus_adequacy_gate, completeness_checker
- `src/polaris_graph/retrieval/` — tier_classifier, live_retriever, contradiction_detector, scope_query_validator, prefetch_offtopic_filter, domain_backends
- `src/polaris_graph/generator/` — provenance_generator, live_deepseek_generator, multi_section_generator
- `src/polaris_graph/evaluator/` — external_evaluator, live_qwen_judge
- `scripts/run_honest_sweep_r3.py` — the orchestrator that stitches it together
- `scripts/run_r6_validation.py` — re-run script
- Tests in `tests/polaris_graph/test_*_r5_*`, `test_*_r6_*`, `test_regression_pg_lb_sa_02_defects.py`, `test_corpus_adequacy_r6_gap1.py`, `test_completeness_r6_gap3.py`, `test_domain_backends_r6_gap2.py`, `test_multi_section_limitations_r1.py`, `test_budget_cap_r2.py`, `test_hedging_gap2.py`, `test_limitations_gap3.py`, `test_multi_section_gap4.py`, `test_url_normalize_gap1.py`
- Live artifacts in `outputs/honest_sweep_r6_validation/` (4 queries, most recent run)

**Supporting context:**
- `loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md` — the audit that drove the honest-rebuild
- `loopback/audit/_live_vs_prerebuild_spotcheck.md` — comparison to pre-rebuild
- Recent commits on branch `PL-honest-rebuild-phase-1` (R-1 through R-6 + XF-cleanup)

## What "ready for full-scale" claims

The pipeline is supposed to behave in one of these ways on every query, and NEVER silently ship a misleading report:
1. `ok` — 13/13 rule checks, corpus adequate, 6/6 or 7/7 completeness, Qwen mostly good.
2. `ok_thin_corpus` — report shipped but Methods + Limitations disclose thin-corpus warning.
3. `ok_incomplete_corpus` — report shipped with specific completeness gaps named.
4. `abort_corpus_inadequate` — no LLM report; "pipeline verdict" artifact with adequacy findings.
5. `warn_rule_checks` — shipped with ≥3 rule-check failures exposed in the manifest.

Budget cap: PG_MAX_COST_PER_RUN (default $0.10). Observed ~$0.003-$0.006/query.

Two-family architecture: DeepSeek V3.2-Exp generator + Qwen3-8B evaluator. `check_family_segregation()` must fail fast on same-family pairs.

## What I want you to look for

Attack the claim. Specifically:

1. **Silent failure modes.** Where in the code can a query produce a confident-looking report without hitting the adequacy / completeness / approval gates? Trace every branch that writes `report.md`.

2. **Prompt-injection leakage.** `sanitize_evidence_text()` in provenance_generator handles a fixed list of patterns. What does it miss? Can an attacker escape via a pattern not in `_INJECTION_PATTERNS`? Consider: base64-encoded instructions, Unicode lookalikes, chained citation markers.

3. **Family-segregation bypass.** Can `check_family_segregation()` be defeated? What if `PG_GENERATOR_MODEL` and `PG_EVALUATOR_MODEL` are set to models on the same fine-tune lineage but different families in our `_FAMILY_PREFIXES` table? (e.g., meta-llama vs a llama fine-tune under a different slug)

4. **Budget-cap bypass.** `reset_run_cost()` is called at the top of the orchestrator. What if a caller instantiates `OpenRouterClient` outside the orchestrated flow? Does `_add_run_cost()` still fire?

5. **Citation attribution bugs.** `_subject_near_position()` in contradiction_detector was added in R-5 Fix B. Walk through edge cases: what if two drug names are equidistant from the value? What if the drug is inside a parenthetical ("Zepbound (tirzepatide) achieved 25.5%")?

6. **Tier classifier false positives / false negatives.** Re-tier the 33-entry `outputs/polaris_graph/PG_LB_SA_02.json` bibliography mentally. Does `test_tier_classifier_denylist_expansion.py` actually cover the edge cases or are there obvious ones I missed?

7. **Multi-section generator failure modes.** What happens if:
   - All sections have `dropped_due_to_failure=True`?
   - Outline JSON parses but all ev_ids are invalid?
   - `_call_limitations` hits the budget cap mid-call?
   - Two sections cite the same evidence_id (does the bibliography dedupe correctly)?

8. **Completeness checklist gaming.** Keywords are case-insensitive substring matches. Can a sentence falsely claim coverage (e.g., "pancreatitis risk was not evaluated" counts as covered because "pancreatitis" appears)?

9. **Corpus-adequacy thresholds.** Are clinical/policy/tech/DD defaults in `corpus_adequacy_gate.py` defensible? Does `abort_if_below_fraction=0.5` produce too many false aborts in practice?

10. **Test vs live divergence.** Tests mock OpenRouterClient with fakes. Is there a production code path exercised in `scripts/run_*.py` that the tests don't touch?

11. **Determinism.** If we ran the R-6 validation twice, how much would the manifest differ? What's deterministic (tier classification, adequacy decision, URL normalization) vs stochastic (DeepSeek output, Qwen verdicts)?

12. **Privileged state.** `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/report.md` is "abort_corpus_inadequate" — the pipeline refused to ship. Confirm the manifest.json for that query has `status=abort_corpus_inadequate` and `cost_usd=0` (no LLM call was made). If it has any cost or any `evaluator_rule_pass` entry, that's a silent failure of the abort path.

## What to return

Write your findings to `.codex/CODE_REVIEW_FINDINGS.md`. Structure:

```
# Code review findings — <date>

## Summary
<one paragraph: ready / not-ready / ready with conditions>

## Critical issues (block full-scale)
<numbered list, each with file:line reference and a reproducer>

## Medium issues (fix before scaling beyond ~20 queries)
<same format>

## Minor issues (clean up when convenient)
<same format>

## What's well-built (don't regress)
<what to preserve>

## My recommendation
<concrete: ship 20-query batch with X gate / fix items 1-3 first / etc.>
```

Be specific. Line numbers. Exact failure modes with inputs that would trigger them.

## Auth / budget

You are authenticated via ChatGPT OAuth (auth_mode=chatgpt). This does NOT burn OpenAI API credits — it uses the user's ChatGPT plan quota. No action needed on auth.

Do not modify any file under `src/`, `scripts/`, `tests/`, or `config/`. Your output goes to `.codex/CODE_REVIEW_FINDINGS.md` only.

Start by reading `architecture.md` and `docs/todo_list.md` to orient, then pick the highest-leverage modules from the in-scope list. You have enough context to finish in one session.
