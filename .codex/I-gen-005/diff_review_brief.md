# I-gen-005 Step 3j diff iter 5 — phrasal verb completeness (FINAL)

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (diff review).
If REQUEST_CHANGES at iter 5, force-APPROVE per §8.3.1.
```

## Iter 4 verdict → iter 5 response

REQUEST_CHANGES with 1 P1: phrasal verbs (led to / leads to / leading to / resulted in / results in / resulting in) missing from branch (f).

Fix: added to branch (f) verb list.

## Diff bound

canonical-diff-sha256: e162e6ab27de92e1725feb6b265dc7949913baf6a58ea439a9db24acea34cba9
- 148/148 tests pass
- 1 new test case covering 5 phrasal-verb sentences

## Repro verification

| Sentence | Expected | Actual |
|---|---|---|
| "treatment led to HbA1c of 6.2% at 40 weeks" | REFUSE | REFUSE ✓ |
| "treatment resulted in HbA1c of 6.2% at 40 weeks" | REFUSE | REFUSE ✓ |
| "treatment led to nausea of 22%" | REFUSE | REFUSE ✓ |
| "treatment resulted in weight loss of 14.9% at 68 weeks" | REFUSE | REFUSE ✓ |
| "treatment leading to weight loss of 14.9%" | REFUSE | REFUSE ✓ |

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

iter4_p1_addressed: YES | NO

novel_p0: []
novel_p1: []
p2: []

canonical_diff_sha256_verified: e162e6ab27de92e1725feb6b265dc7949913baf6a58ea439a9db24acea34cba9
```

EMIT YAML ONLY.
