You are auditing M-28 Fix #1 (regulatory-anchor retrieval) as a code
review BEFORE any full-scale sweep runs. This is a code audit, not a
DR content audit. No V18 output exists yet — the goal is to catch
correctness, generalization, and safety issues in the implementation
before we spend a sweep cycle on it.

## Context

The user mandate 2026-04-20: "we cannot hard code it to get a narrow
win, we need to make sure it is going to be generalized for many
different kinds of queries". Earlier we tried M-26a (T6 tier exclude)
which regressed V14/V15 outline structure by removing topic-diversity
signal. We reverted and went back to V17 baseline.

M-28 is the first of 4 reconciled fixes from Claude+Codex deep
comparison (see `outputs/codex_findings/v17_vs_tier1_deep_comparison/
findings.md` and `state/v17_vs_tier1_claude_deep_read.md`).

## What to audit

Commit-diff: check what changed on this branch since commit `14b50a9`
(V17 TOP-TIER baseline). The relevant files:

1. `config/scope_templates/clinical.yaml` — adds
   `regulatory_anchors` list at the end.
2. `config/scope_templates/policy.yaml` — adds anchors for policy.
3. `config/scope_templates/due_diligence.yaml` — adds anchors for DD.
4. `src/polaris_graph/retrieval/regulatory_expander.py` — new module
   exporting `expand_regulatory_queries(question, template) -> list[str]`.
5. `tests/polaris_graph/test_m28_regulatory_expander.py` — 20 tests
   covering empty/missing template, valid expansion, invalid-entry
   rejection, deduplication, empty-question handling, and three
   generalization smoke tests (policy, due-diligence, environmental).
6. `scripts/run_honest_sweep_r3.py` (lines ~539-565) — wiring that
   loads the template for the query's domain, calls the expander,
   appends to the amplified list.

## Specific review questions

1. **No hard-coded agency/domain names in Python.** Confirm that
   `regulatory_expander.py` contains ZERO agency-specific strings
   (no "fda.gov", no "sec.gov", no "ema.europa.eu" anywhere in the
   .py file). All agency names live only in YAML templates.

2. **Generalization safety.** Imagine the pipeline being asked a
   materials-science query with a template that has no
   regulatory_anchors. Verify the code path behaves correctly
   (empty list returned, no crash, no extra queries emitted).

3. **Anchor-list robustness.** The template parser should tolerate:
   - missing `regulatory_anchors` key (treat as empty)
   - wrong type (dict, int, None) instead of list (treat as empty)
   - non-string entries mixed in (drop silently)
   - URL paths instead of hosts (e.g. "fda.gov/drugs") — reject
   - empty strings / whitespace-only (drop)
   - case duplicates ("FDA.gov" vs "fda.gov") — dedupe

4. **Serper `site:` operator correctness.** The query format
   `{question} site:{host}` is correct Serper/Google syntax. Verify
   the expander emits exactly this format, NOT `site:{host} {question}`
   (order shouldn't matter to Google, but consistency helps).

5. **Scope-validator interaction.** The amplified list passes through
   `validate_amplified_queries` in `live_retriever.py`. Will a
   `tirzepatide safety site:fda.gov` query survive scope validation
   for a clinical/tirzepatide question? If the validator rejects
   scoped queries for drifting off the anchor tokens, M-28 would be
   dead on arrival. Check `src/polaris_graph/retrieval/
   scope_query_validator.py` to confirm.

6. **Cost impact.** Each anchor adds one Serper call (up to
   `PG_SWEEP_MAX_SERPER=50` amplified queries total). Clinical template
   has 7 anchors. If amplified list was already near the Serper cap,
   these may be dropped. Check whether the wiring truncates anchor
   queries in the name of the cap, or whether it blindly appends
   and overshoots budget.

7. **Duplicate amplified queries.** If the hand-curated `amplified`
   list in `run_honest_sweep_r3.py` already has a `site:fda.gov`
   query, M-28's addition would duplicate. Does the downstream
   de-dup logic collapse this? (Look at `live_retriever.py` seen-URL
   set — that dedups URLs not queries; queries could fan out to same
   URLs and dedup happens later.)

8. **Test coverage completeness.** 20 tests exist. Are there
   coverage holes? Specifically:
   - YAML integration test: does the template actually load with
     the new `regulatory_anchors` field without breaking scope_gate?
   - Does `run_honest_sweep_r3.py` still work when a template has
     zero anchors?

9. **Template YAML hygiene.** The three template files were updated
   via `cat >> file` append. Check they are still valid YAML and
   don't have duplicate top-level keys.

10. **Regression against V17 TOP-TIER baseline.** Would M-28 alone
    possibly regress V17's pass-8 verdict? M-26a taught us selector
    changes have non-obvious effects. M-28 is retrieval-side (only
    ADDS queries) so the blast radius is smaller — but confirm.

## Verdict format

Write findings to `outputs/codex_findings/m28_code_audit/findings.md`:

```
---
audit_type: code_review_pre_sweep
fix: M-28 Fix #1 (regulatory-anchor retrieval)
commit_range: 14b50a9..HEAD
verdict: READY | CONDITIONAL | NOT_READY
blockers: <int>
mediums: <int>
---

Section per review question, verdict per section.

Final verdict sentence:
"M-28 may / may not proceed to V18 sweep."
```

Verdict rules:
- READY: no blockers, ≤2 mediums with documented mitigations.
  Claude may launch V18 immediately.
- CONDITIONAL: zero blockers but ≥3 mediums. Claude patches, Codex re-audits.
- NOT_READY: any blocker. Claude fixes before V18.

Be uncompromising but concrete. Reference file:line for each finding.
