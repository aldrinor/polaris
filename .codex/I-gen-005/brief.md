# I-gen-005 PR #911 — update verify-test for Step 1 local_support_window

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
```

## Scope (1 file, ~50 lines)

Replaces pre-existing test_verify_sentence_fails_when_span_missing_number (broken since Step 1 PR #905 added local_support_window) with two tests reflecting actual behavior + safety floor per §-1.1.

- test_verify_passes_when_number_in_local_support_window — narrow cite + data-in-broader-evidence rescued via local_support_window
- test_verify_sentence_fails_when_number_not_in_evidence_at_all — number ABSENT from evidence still fails with "number_not_in" reason (the actual safety floor)

14/14 test_provenance_generator pass.

## Canonical hash

SHA256: `19a9602903c0f989661f211fefbaafd065fe541a6ca2670037febaee30fe7bd0`

## Output

```yaml
verdict: APPROVE | REQUEST_CHANGES
test_pair_correctly_captures_intent: YES | NO
safety_floor_test_correct: YES | NO
approval_to_merge: YES | NO
```

EMIT YAML ONLY.
