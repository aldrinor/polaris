# Codex DIFF-gate — I-meta-002 sub-PR-2 — iter 2 of 5

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## What changed since your iter-1 diff review
Your iter-1 diff verdict was REQUEST_CHANGES with ONE novel P0 (zero P1/P2):

> sentinel_contract.py: duplicate identical Sentinel score tags treated as a clean parse.
> `<score>no</score><score>no</score>` returned GROUNDED with parsed_ok=True — a silent
> GROUNDED-on-bad-input path. Root cause: matches normalized into a SET, so N identical
> tokens collapse to a 1-element set and the ambiguity guard is bypassed.

**Fix applied (this is the ONLY code change in this iter):** in `parse_sentinel_score`, the
ambiguity guard now counts raw tag OCCURRENCES, not distinct values: `if len(matches) != 1:
return UNGROUNDED, parsed_ok=False`. Any input with more than one `<score>` tag fails closed
regardless of whether the tags agree. The set-of-distinct-values logic is removed.

**Regression tests added** (tests/roles/test_sentinel_contract.py):
- `test_duplicate_score_tags_fail_closed_codex_p0_regression` — asserts `<score>no</score><score>no</score>`,
  the cross-newline form, the triple form, and `<score>yes</score><score>yes</score>` ALL return
  `SentinelResult(UNGROUNDED, parsed_ok=False)`.
- Added the same duplicate-agreeing cases to the malformed parametrize list.

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` → 194 passed, 0 failed.
- `verify_lock --consistency` → exit 0.

## Everything you already APPROVED in iter-1 is unchanged
Judge enum hard-fail, Mirror composite two-pass hash binding (answer + ordered citation
bindings, JSON-array canonical form), source_missing→FABRICATED fabricated-identity-first
precedence, hygiene, and no-canonical-pipeline-drift. Only sentinel_contract.py + its test
file changed since iter-1.

## Review ask
Confirm the P0 is closed (no remaining path returns GROUNDED on >1 tag, empty, off-enum,
missing, or non-string input) and that no NEW issue was introduced. Verdict APPROVE iff the
fail-closed property now holds with zero P0/P1.

## DIFF (full sub-PR-2 diff, fix included)
