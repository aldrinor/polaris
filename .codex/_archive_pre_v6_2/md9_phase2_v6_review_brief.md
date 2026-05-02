# Codex round 5 — M-D9 phase 2 v6 (commit c6612f0)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md9_phase2_beat_both.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`

## Round-4 finding to verify closed
[LOW] `_is_visually_empty_text` previously skipped only
Cf/Cc/Cn/Co/Cs. Standalone Mn (Mark Nonspacing) characters
like CGJ U+034F, VS16 U+FE0F, FVS1 U+180B were accepted as
populated frame values, violating the "visually empty"
predicate.

## What v6 changed
- `_is_visually_empty_text` skip set extended from
  `("Cf","Cc","Cn","Co","Cs")` to also include
  `("Mn","Mc","Me")` (all 3 Unicode Mark categories — Mark
  Nonspacing, Mark Spacing Combining, Mark Enclosing).
- Docstring updated to enumerate all 8 skip categories +
  explicit non-regression note on `"a̧"` (base char + Mn
  still counts as populated because the loop exits on 'a').
- New test `test_claim_frames_treats_combining_marks_as_missing`
  pins: lone CGJ, lone VS16, lone cedilla all → missing;
  `"a̧"` and `"[5.2, 5.8]"` both → present.
- Threat model `docs/md9_phase2_threat_model.md` v5→v6.

## Convergence note
This is round 5 on the same `_is_frame_field_populated`
predicate. Round-by-round:
  R1: regex URL parsing (regulatory_coverage)
  R2: truthy → is_not_None
  R3: empty-string → whitespace-only
  R4: whitespace → Cf/Cc/Cn/Co/Cs
  R5: Cf/... → Cf+Mc/Mn/Me

If round 5 finds another edge in the SAME predicate, that's
still convergence — fix it. If round 5 reaches for an entirely
new probe surface (e.g. `_host_of` IDNA, `_REGULATORY_HOSTS`
membership semantics, `_citation_urls` Unicode normalization),
THAT is the asymptote signal — flag explicitly so Claude can
lock with a documented boundary doc.

## Verdict format
```
## Verdict
GREEN | PARTIAL | BLOCKED

## Round-4 fix integration
- [x/ ] Mn/Mc/Me skip extension closes round-4 bypass

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
