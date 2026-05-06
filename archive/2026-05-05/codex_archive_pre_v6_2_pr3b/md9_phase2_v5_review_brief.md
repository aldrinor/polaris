# Codex round 4 — M-D9 phase 2 v5 (commit 56b0a44)

## Scope
Verify that v5 closes Codex round-3 PARTIAL finding
(whitespace-only frame strings now treated as missing) AND that
the v5 pre-emptive hardening (invisible Unicode Cf/Cc/Cn/Co/Cs
characters) is correct.

## Round-3 finding to verify closed
[LOW] `src/polaris_graph/audit_ir/beat_both_scoring.py:187`
only rejected `""`, so whitespace-only strings still scored as
populated via `:434`; a claim with `ci="   "` was counted complete.

## What v5 changed
- Added `_is_visually_empty_text(text)` helper (lines ~205-220)
- `_is_frame_field_populated` (lines 175-200) now uses the
  helper rather than `value.strip() == ""`. Behavior:
  - `None` → missing
  - `""` → missing
  - `"   "`, `"\t\n"` → missing (round-3 fix preserved)
  - `"​﻿"` (ZWSP+BOM) → missing (NEW v5)
  - `"‌‍"` (ZWNJ+ZWJ) → missing (NEW v5)
  - `0` / `0.0` → present (v2 fix preserved)
- New test `test_claim_frames_treats_invisible_unicode_as_missing`
  pins the new behavior

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md9_phase2_beat_both.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- 52 tests now (was 51)

## Convergence note
Rounds 1-3 each tightened the SAME predicate ("what counts as
a populated frame field"):
  - v1: regex URL parsing (regulatory_coverage)
  - v2: truthy → is_not_None (claim_frames)
  - v3: empty-string → whitespace-only (claim_frames)
  - v4: structural fix
  - v5: whitespace → Unicode-category check (claim_frames)

If round 4 finds another edge in the SAME `_is_frame_field_populated`
or `_host_of` predicate, that's still convergence — fix it. If
round 4 reaches for an entirely new probe surface (e.g.
`_jurisdiction_hosts` IDNA, `_citation_urls` Unicode normalization,
or some new module-level concern), THAT is the asymptote signal —
flag it explicitly so Claude can lock with a documented boundary.

## Verdict format
PARTIAL or GREEN or BLOCKED, then a final-word line.
