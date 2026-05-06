# Codex round 5 verdict-only — M-D9 phase 2 v6 (commit c6612f0)

Your prior session ran pytest (53/53 passed), found
`scope_classifier._is_visually_empty` for cross-milestone
comparison, then hit Windows cp1252 console encoding error
on a Python verification script. Issue verdict on the diff
without running more Python — work from the description below.

## Context

v6 extends `_is_visually_empty_text` skip set in
`src/polaris_graph/audit_ir/beat_both_scoring.py` from
`("Cf","Cc","Cn","Co","Cs")` to also include `("Mn","Mc","Me")`
to close the round-4 LOW finding (CGJ U+034F, VS16 U+FE0F,
FVS1 U+180B previously bypassed as populated).

```python
def _is_visually_empty_text(text: str) -> bool:
    if not text:
        return True
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        if category in (
            "Cf", "Cc", "Cn", "Co", "Cs",
            "Mn", "Mc", "Me",
        ):
            continue
        return False
    return True
```

Tests added (all green per your prior pytest run):
- `test_claim_frames_treats_combining_marks_as_missing` —
  asserts CGJ, VS16, lone cedilla → missing; `"a̧"` and
  `"[5.2, 5.8]"` → present.

Threat model `docs/md9_phase2_threat_model.md` updated to v6
documenting all 8 skip categories.

## Cross-milestone observation (your prior session noticed)

`scope_classifier._is_visually_empty` (M-D5 phase 1, already
LOCKED at v4) skips only Cf/Cc/Cn/Co/Cs — it does NOT skip
Mn/Mc/Me. M-D9 phase 2 v6 is now STRICTER than M-D5 phase 1.

For verdict purposes, treat this as out-of-scope for THIS
milestone (M-D9 phase 2). M-D5 phase 1's gap (if any) is a
separate cycle. M-D9's job here is just to close the round-4
finding on its own surface.

## Verdict checklist

- [Y/N] v6 Mn/Mc/Me extension closes round-4 bypass on
  `_is_frame_field_populated`?
- [Y/N] No regression on `"a̧"` (base char + Mn still
  populated because loop exits on 'a')?
- [Y/N] Any new findings on `_is_frame_field_populated` /
  `_is_visually_empty_text` predicate within M-D9 phase 2?
- [Y/N] Any new findings on a DIFFERENT M-D9 phase 2 probe
  surface (`_host_of`, `_REGULATORY_HOSTS`, `_jurisdiction_hosts`,
  `_citation_urls`, etc.)?

## Output format (mandatory)

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-4 fix integration
- [x/ ] Mn/Mc/Me skip extension closes round-4 bypass
- [x/ ] No regression on base+combining sequences

## New findings (if any)
[SEVERITY] file:line — description

## Cross-milestone note (M-D5 phase 1 alignment)
optional 1-line observation, but DO NOT block on it

## Final word
GREEN | PARTIAL until X
```

NO file reads or Python verification needed — issue verdict on
the diff above only.
