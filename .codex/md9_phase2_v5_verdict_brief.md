# Codex round 4 verdict-only — M-D9 phase 2 v5 (commit 56b0a44)

You already saw the diff in the prior session that was cut off
mid-review. Issue verdict only — no further file reads needed.

## Diff summary (what's at commit 56b0a44):

**`src/polaris_graph/audit_ir/beat_both_scoring.py`** lines 175-225:

```python
def _is_frame_field_populated(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str) and _is_visually_empty_text(value):
        return False
    return True


def _is_visually_empty_text(text: str) -> bool:
    if not text:
        return True
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        if category in ("Cf", "Cc", "Cn", "Co", "Cs"):
            continue
        return False
    return True
```

Mirror of `scope_classifier._is_visually_empty` (M-D5 phase 1
v3+v4 same pattern, already GREEN-locked).

**`tests/polaris_graph/test_md9_phase2_beat_both.py`** added
`test_claim_frames_treats_invisible_unicode_as_missing` —
asserts ZWSP+BOM, ZWNJ+ZWJ, word-joiner+NBSP all count as
missing. 52/52 tests passing locally.

## What round-3 PARTIAL flagged
[LOW] Whitespace-only `ci="   "` was counted complete.

## What v4 had already shipped
v4 (commit 4931331) already added `value.strip() == ""` check
which closes whitespace-only strings. v5 extends that to also
reject Cf/Cc/Cn/Co/Cs invisible characters.

## Verdict checklist (one line each):
- [Y/N] v4 strip-based fix closes round-3 whitespace-only finding?
- [Y/N] v5 Unicode-category extension is correct (mirrors M-D5)?
- [Y/N] Any new findings on `_is_frame_field_populated` predicate?
- [Y/N] Any new findings on a DIFFERENT probe surface
       (`_host_of`, `_jurisdiction_hosts`, `_citation_urls`,
       `_REGULATORY_HOSTS` membership, etc.)?

## Output format (mandatory)
```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-3 fix integration
- [x] whitespace-only stripped
- [x] invisible-unicode rejected

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```

NO file reads needed. Issue verdict on the diff above.
