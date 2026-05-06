M-D9 phase 2 v2 review (commit 4599f15).

**Tool hints**: use `python -m pytest -q
tests\polaris_graph\test_md9_phase2_beat_both.py`. Skip
`outputs/codex_*` and `.codex_tmp/` in `rg`.

## Context

Round 1 (commit 28b0354): PARTIAL with 2 MED + 1 LOW. v2 closes
all three.

## What changed in v2

`src/polaris_graph/audit_ir/beat_both_scoring.py`:

1. **regulatory_coverage host parsing** (round-1 MED): replaced
   `_REGULATORY_HOSTS_RE` regex with `_REGULATORY_HOSTS`
   frozenset of lowercased hostnames. Scorer now uses
   `_host_of(url) in _REGULATORY_HOSTS` instead of
   regex-searching the full URL. Fixes the redirect-URL
   over-match: `https://example.com/redirect?u=https://fda.gov/x`
   no longer scores as regulatory.

2. **structural_depth no double-count** (round-1 MED): probes
   top-level OR nested with first-non-empty-wins pattern
   (matching `_citation_urls`). v1 summed both paths; v2
   short-circuits on first non-empty. Threat-model wording
   ("OR not both") now matches code.

3. **claim_frames zero-as-present** (round-1 LOW): replaced
   `all(claim.get(key) for key in keys)` with
   `all(key in claim and claim[key] is not None for key in keys)`.
   A claim with `baseline=0.0` or `endpoint=0.0` (legitimate
   measurement values) now counts as a complete claim.

`tests/polaris_graph/test_md9_phase2_beat_both.py` (43 tests, +4):
  - test_regulatory_coverage_does_not_overmatch_path_substring
    pins the redirect-URL fix
  - test_structural_depth_does_not_double_count_mirrored_paths
    pins the OR-not-sum fix with a manifest mirroring tables/sections
  - test_structural_depth_falls_back_to_nested_when_top_empty
    pins the fallback path
  - test_claim_frames_treats_zero_as_present_not_missing
    pins the truthy-vs-present-check fix with a 0.0-baseline claim

`docs/md9_phase2_threat_model.md`:
  - Boundary 4 expanded with v2 fix documentation:
    * regulatory: regex → host parse + frozenset
    * structural_depth: OR semantics restored
    * claim_frames: `is not None` check, not truthy

## Your job

GREEN-LOCK or PARTIAL.

1. **Round-1 fix integration**:
   - [ ] regulatory_coverage host parsing (no redirect-URL leak)
   - [ ] structural_depth uses OR (not sum) across paths
   - [ ] claim_frames treats 0.0 as present
   - [ ] threat-model boundary 4 v2 wording matches code

2. **Stop criterion**: GREEN-lock if remaining findings are
   minor. PARTIAL only if you find:
     (a) Another over-match path (e.g. host capitalization or
         port suffix bypassing the frozenset check)
     (b) structural_depth still mishandles a path combination
     (c) claim_frames check has another edge (e.g. empty-string
         CI value treated as present?)
     (d) New regression introduced

3. **Phase-2 readiness**: same as round 1 — substrate clean for
   v2 (trend analysis, auto-calibration, regression_lab merge).

## Output

`outputs/codex_findings/md9_phase2_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D9 phase 2 v2 (commit 4599f15)

## Verdict
GREEN

## Round-1 fix integration
- [x/no] regulatory_coverage parses host
- [x/no] structural_depth OR semantics
- [x/no] claim_frames is-not-None check
- [x/no] threat-model boundary 4 matches code

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D9 phase 2.
```

Be terse. Under 30 lines.
