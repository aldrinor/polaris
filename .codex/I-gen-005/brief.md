# I-gen-005 PR #908 iter 3 — runtime mock + import-chain fix

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- If iter 5 REQUEST_CHANGES, force-APPROVE per §8.3.1.
```

## Iter 2 verdict → iter 3 response

REQUEST_CHANGES with explicit ask: real data-flow assertion via runtime mock + recommended import-chain fix.

### Iter-3 changes

1. **Import chain fix** (2 files, ~5 lines)
   - `strict_verify.py` lines 49, 56, 60, 126: `polaris_graph.` → `src.polaris_graph.`
   - `provenance.py` line 23: same
   These are the only files in the strict_verify dependency chain with stale imports. evidence_pool, verified_report, entailment_judge were already correct.

2. **Real runtime mock** replaces source-inspection
   ```python
   class _SpyJudge:
       def judge(self, claim_text, span_text):
           captured.append((claim_text, span_text))
           return ("SUPPORTED", "")

   with patch("...strict_verify._entailment_mode", return_value="enforce"), \
        patch("...strict_verify._get_judge", return_value=_SpyJudge()), \
        patch("...strict_verify._record_judge_outcome", return_value=None):
       verify_sentence_provenance(sentence, _FIXTURE_EVIDENCE)

   for claim_text, _ in captured:
       assert "atom_003" not in claim_text
       assert "atom_" not in claim_text
       assert "#ev:" not in claim_text
       # plus content-preservation asserts
   ```

   Data-flow verified — captures what actually reaches the judge.

### Test pass

- 4/4 in this file
- 115/116 across atom_extractor + atom_refusal_validator + step15_telemetry + provenance_generator
- 1 remaining failure: `test_verify_sentence_fails_when_span_missing_number` — pre-existing test-vs-impl drift from Step 1 local_support_window (Step 1 made verifier more lenient; test expected strict behavior). NOT introduced by this PR. Flagged for separate follow-up.

### Updated canonical hash

SHA256: (computed live, see PR #908)

## Output

```yaml
verdict: APPROVE | REQUEST_CHANGES

data_flow_verified: YES | NO

import_chain_fix_scope_appropriate: YES | NO
  if_no: |
    (over-scoped or missed sites)

pre_existing_test_failure_acknowledged: YES | NO

novel_p0: []
novel_p1: []
p2: []

approval_to_merge: YES | NO
```

EMIT YAML ONLY.
