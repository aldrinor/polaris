# Codex DIFF-gate — I-meta-002 sub-PR-2 — iter 5 of 5 (FINAL before cap)

HARD ITERATION CAP: 5 per document. This is iter 5 of 5 — the LAST iteration.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If this iter-5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining
  non-P0/P1 findings per CLAUDE.md §8.3.1; any residual is captured as a follow-up issue.
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

## What changed since your iter-4 review
Your iter-4 verdict was REQUEST_CHANGES, one P1 (zero P0):

> sentinel_contract.py — `_STRICT_SCORE_RE` uses Unicode `re.IGNORECASE`, so Python accepts
> U+017F LONG S as `s`. `<ſcore>no</ſcore>` returns `(GROUNDED, parsed_ok=True)`. Fix with
> ASCII-only case matching (`re.IGNORECASE | re.ASCII`) and add the regression.

**Fix applied (the ONLY code change this iter):** added `re.ASCII`:
```python
_STRICT_SCORE_RE = re.compile(r"\s*<score>\s*(yes|no)\s*</score>\s*", re.IGNORECASE | re.ASCII)
```
`re.ASCII` folds only a-z/A-Z and limits `\s` to ASCII whitespace, so the homoglyph envelope
no longer matches. Verified empirically:
- WITHOUT re.ASCII: `fullmatch('<ſcore>no</ſcore>')` -> matched (the old bug).
- WITH re.ASCII: `fullmatch('<ſcore>no</ſcore>')` -> None -> `(UNGROUNDED, parsed_ok=False)`.
- Clean `<score>no</score>` -> `(GROUNDED, parsed_ok=True)` (unchanged).

**Regression test added** `test_unicode_homoglyph_tag_fails_closed_codex_p1_iter4_regression`
covering `<ſcore>no</ſcore>`, mixed ASCII/homoglyph close, and the yes form — all fail closed.

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 206 passed, 0 failed.
- `pytest tests/roles/test_sentinel_contract.py` -> 37 passed.
- `verify_lock --consistency` -> exit 0.

## Cumulative fail-closed property (sub-PR-2 Sentinel)
After iters 1–4 the parser admits `parsed_ok=True` ONLY for a lone ASCII
`<score>yes</score>` / `<score>no</score>` envelope (surrounding + inner ASCII whitespace
tolerated). Every other input — duplicate/partial/extra tags, prose-wrap, off-enum body,
Unicode homoglyph, missing tag, non-string — fails closed to `(UNGROUNDED, parsed_ok=False)`.
Polarity is hard-locked yes->UNGROUNDED.

## Unchanged (APPROVED in iter-1)
Judge enum hard-fail, Mirror composite two-pass hash binding, source_missing->FABRICATED
precedence, hygiene, no canonical-pipeline drift. Only sentinel_contract.py + its test file
changed since iter-1.

## Review ask
Final adversarial probe: is there ANY input that returns `(GROUNDED, parsed_ok=True)` other
than a lone ASCII `<score>no</score>` envelope? APPROVE iff the fail-closed property holds
with zero P0/P1.

## DIFF (full sub-PR-2 diff)
