# I-gen-005 PR #912 — 3 real-V4-Pro-smoke-found validator bugs

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
```

## Scope (3 fixes + 3 regression tests)

PR #910 smoke (PG_ATOM_REFUSAL_MODE=log_only) produced real-V4-Pro gaps.json with 61.5% refusal_rate. Analysis: bugs not compliance.

1. Splitter `;` inside parens (efficacy.s001-s003 in real gaps.json)
2. Unicode minus mismatch (4/4 SOFT_MISMATCHES were this)
3. Smoke print U+2192 crash on Windows cp1252

120/120 tests pass.

Canonical hash: `017b788bb52c3415e7e8ee3aec1be6031175705e4fd998bd9df10fb45dc630fa`

## Output

```yaml
verdict: APPROVE | REQUEST_CHANGES
bug1_splitter_paren_aware_correct: YES | NO
bug2_unicode_minus_both_sides_correct: YES | NO
bug3_ascii_arrow_correct: YES | NO
novel_p0: []
novel_p1: []
approval_to_merge: YES | NO
```

EMIT YAML ONLY.
