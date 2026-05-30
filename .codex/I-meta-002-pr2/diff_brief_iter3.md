# Codex DIFF-gate — I-meta-002 sub-PR-2 — iter 3 of 5

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings. No drip-feeding across iterations.
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

## What changed since your iter-2 diff review
Your iter-2 verdict was REQUEST_CHANGES with ONE continuing P0 (zero P1/P2):

> sentinel_contract.py:75 — the guard counts only complete regex matches, not raw score
> tag occurrences. `parse_sentinel_score('<score>no</score><score>maybe')` returns
> `GROUNDED, parsed_ok=True`; same for `'<score>no</score><score>'`. A clean `no` tag
> followed by a second MALFORMED score tag still slips through as a silent GROUNDED.
> Required fix: reject if raw score markup occurs outside the single complete valid score
> element, or count raw opening/closing score tag occurrences before accepting `no`.

**Fix applied (the ONLY code change this iter):** `parse_sentinel_score` now counts RAW
opening and closing score markup with two new regexes that match malformed/partial tags too:
- `_OPEN_TAG_RE  = re.compile(r"<\s*score(?![A-Za-z])", re.IGNORECASE)`
- `_CLOSE_TAG_RE = re.compile(r"<\s*/\s*score(?![A-Za-z])", re.IGNORECASE)`
A clean parse now requires `len(open_tags)==1 AND len(close_tags)==1 AND len(matches)==1`.
Any extra OR partial score markup (second unclosed tag, stray open, stray close, malformed
close `< /score>`) fails closed to `UNGROUNDED, parsed_ok=False`. The `(?![A-Za-z])`
lookahead prevents matching words like `scoreboard`.

**Your exact iter-2 probes are now regression tests** and pass:
- `parse_sentinel_score('<score>no</score><score>maybe')` -> `(UNGROUNDED, parsed_ok=False)`
- `parse_sentinel_score('<score>no</score><score>')`      -> `(UNGROUNDED, parsed_ok=False)`
plus `<score>no< /score>`, `<score>no</score></score>`, and the iter-1 duplicate-tag set.
Test: `test_clean_tag_then_malformed_tag_fails_closed_codex_p0_iter2_regression`.

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 200 passed, 0 failed.
- `pytest tests/roles/test_sentinel_contract.py` -> 31 passed.
- `verify_lock --consistency` -> exit 0.

## Unchanged (you already APPROVED these in iter-1)
Judge enum hard-fail, Mirror composite two-pass hash binding, source_missing->FABRICATED
fabricated-identity-first precedence, hygiene, no canonical-pipeline drift. Only
sentinel_contract.py + its test file changed since iter-1.

## Review ask
Adversarially probe `parse_sentinel_score` for ANY remaining input that returns GROUNDED
with parsed_ok=True other than a single clean `<score>no</score>`. Verdict APPROVE iff the
fail-closed property holds with zero P0/P1.

## DIFF (full sub-PR-2 diff, both fixes included)
