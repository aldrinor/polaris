# Codex DIFF-gate — I-meta-002 sub-PR-2 — iter 4 of 5

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1.
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

## What changed since your iter-3 review
Your iter-3 verdict was REQUEST_CHANGES, one P1 (zero P0):

> sentinel_contract.py — parser returns GROUNDED, parsed_ok=True for non-clean outputs
> containing one valid `no` tag plus arbitrary surrounding text (`Reasoning: unsafe\n<score>no</score>`,
> `<score>no</score> trailing rationale`, `prefix <score>no</score> suffix`). Fix by
> anchoring/fullmatching the whole stripped raw output to exactly one `<score>yes|no</score>`
> element with only surrounding whitespace allowed.

**Fix applied (the ONLY code change this iter):** the three weaker guards (complete-match
count, raw open/close tag count) are REPLACED by a single anchored rule:
```python
_STRICT_SCORE_RE = re.compile(r"\s*<score>\s*(yes|no)\s*</score>\s*", re.IGNORECASE)
match = _STRICT_SCORE_RE.fullmatch(raw)
if match is None:
    return SentinelResult(UNGROUNDED, parsed_ok=False)
```
`fullmatch` anchors the WHOLE output, so the ONLY `parsed_ok=True` paths are a lone
`<score>yes</score>` or `<score>no</score>` (surrounding + inner whitespace tolerated). Any
prefix/suffix prose, second/partial tag, off-enum body, missing tag, or non-string fails
closed to `(UNGROUNDED, parsed_ok=False)`. The token group is constrained to `yes|no`, so a
clean match can never carry an off-enum body.

**Your exact iter-3 probes are now regression tests and pass** (all -> UNGROUNDED, parsed_ok=False):
`Reasoning: unsafe\n<score>no</score>`, `<score>no</score> trailing rationale`,
`prefix <score>no</score> suffix`, `Reasoning: risk detected.\n<score>yes</score>`.
Test: `test_prose_wrapped_score_fails_closed_codex_p1_iter3_regression`. Plus the iter-1/iter-2
duplicate/partial-tag regressions still pass.

I documented a deliberate scope note in the source: if the SERVED Granite build (PR4/Gate-B)
emits an extra token (e.g. a trailing confidence line) alongside the score, this contract
must be EXTENDED with that exact verified format — never loosened to "tag present anywhere".

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 205 passed, 0 failed.
- `pytest tests/roles/test_sentinel_contract.py` -> 36 passed.
- `verify_lock --consistency` -> exit 0.

## Unchanged (APPROVED in iter-1)
Judge enum hard-fail, Mirror composite two-pass hash binding, source_missing->FABRICATED
precedence, hygiene, no canonical-pipeline drift. Only sentinel_contract.py + its test file
changed since iter-1.

## Review ask
Adversarially probe `parse_sentinel_score` once more: is there ANY input that returns
`(GROUNDED, parsed_ok=True)` other than a lone `<score>no</score>` envelope? Verdict APPROVE
iff the fail-closed property now holds with zero P0/P1.

## DIFF (full sub-PR-2 diff)
