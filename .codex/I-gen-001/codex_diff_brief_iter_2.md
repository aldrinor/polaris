Diff review iter 2 for GH#422 I-gen-001 (PBO scope conflation). Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Iter-1 P1 RESOLVED

> The saved diff artifact does not include tests/polaris_graph/test_section_prompt_gh422.py; the test file is untracked in the workspace, and git diff --stat shows only the one production-line prompt change.

**Fix:** test file is now staged. Updated diff:

```
$ git diff --cached --stat -- src/ tests/
 src/polaris_graph/generator/multi_section_generator.py |  1 +
 tests/polaris_graph/test_section_prompt_gh422.py       | 67 +
 2 files changed, 68 insertions(+)
```

Both production change + test file are in the staged tree. Saved patch at `.codex/I-gen-001/codex_diff.patch` regenerated to include both (`git diff --cached -- src/ tests/`).

# Test results (rerun)

```
PYTHONPATH=src python -m pytest tests/polaris_graph/test_multi_section_gap4.py \
  tests/polaris_graph/test_multi_section_limitations_r1.py \
  tests/polaris_graph/test_section_prompt_gh422.py
19 passed in 2.80s
```

All five new GH#422 tests pass + 14 existing multi_section tests unchanged.

# What's in the diff (verified via git diff --cached)

## src/polaris_graph/generator/multi_section_generator.py (+1 line)

Rule 13 appended to SECTION_SYSTEM_PROMPT_TEMPLATE on line 659, immediately after rule 12c's BAD examples on line 658. Rule text starts with `13. **Policy-scope disambiguation (M-NEW-1, GH#422)**:` and includes GOOD/BAD examples naming Bill C-64 + PBO universal single-payer.

## tests/polaris_graph/test_section_prompt_gh422.py (+67 lines, new file)

5 tests:
- test_section_prompt_contains_policy_scope_disambiguation_rule
- test_section_prompt_names_bill_c64_example
- test_section_prompt_requires_inline_scope_label
- test_section_prompt_rule_13_fires_across_sections
- test_section_prompt_rule_13_documents_bad_example

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
