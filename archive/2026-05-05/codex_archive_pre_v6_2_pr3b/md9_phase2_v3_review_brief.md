M-D9 phase 2 v3 review (commit 7209a72).

**Tool hints**: use `python -m pytest -q
tests\polaris_graph\test_md9_phase2_beat_both.py`. Skip
`outputs/codex_*` and `.codex_tmp/` in `rg`.

## Context

Round counts: R1=2 MED + 1 LOW (28b0354). v2 closed all 3.
R2 = 1 MED (port/query/userinfo) + 1 LOW (empty-string ci) on
v2 (4599f15). v3 closes both.

## What changed in v3

`src/polaris_graph/audit_ir/beat_both_scoring.py`:

1. **`_host_of` now uses `urllib.parse.urlsplit`** (round-2 MED).
   Replaces the v2 `_HOST_RE` regex that only stopped at `/`.
   urlsplit returns parts.hostname which is the bare host with
   port, query, userinfo, fragment all stripped. v3 also unifies
   `www.fda.gov` and `fda.gov`.

2. **`_is_frame_field_populated` helper** (round-2 LOW). Uses
   sentinel + None + empty-string rejection. Numeric 0 stays
   present (round-1 fix); empty string and None are missing.

`tests/polaris_graph/test_md9_phase2_beat_both.py` (50, +7):
  - test_regulatory_coverage_handles_url_with_port
  - test_regulatory_coverage_handles_url_with_query
  - test_regulatory_coverage_handles_url_with_userinfo
  - test_regulatory_coverage_handles_url_with_fragment
  - test_regulatory_coverage_handles_www_prefix
  - test_claim_frames_treats_empty_string_as_missing
  - test_claim_frames_missing_key_treated_as_missing

`docs/md9_phase2_threat_model.md` boundary 4 expanded with
v3 fix list.

## Your job

GREEN-LOCK or PARTIAL.

1. **Round-2 fix integration**:
   - [ ] _host_of returns canonical bare host for URLs with
     port / query / userinfo / fragment combinations
   - [ ] www.X and X parse to same regulatory key
   - [ ] _is_frame_field_populated rejects "" but accepts 0
   - [ ] threat-model boundary 4 v3 wording matches code

2. **Stop criterion**: GREEN-lock if remaining findings are
   minor. PARTIAL only if you find:
     (a) Another _host_of edge (e.g. uppercase host, IDNA,
         IPv6 brackets) that breaks regulatory matching
     (b) _is_frame_field_populated has another edge (e.g.
         whitespace-only string treated as present?)
     (c) New regression introduced

3. **Phase-2 readiness**: same as round 1.

## Output

`outputs/codex_findings/md9_phase2_v3_review/findings.md`:

```markdown
# Codex round 3 — M-D9 phase 2 v3 (commit 7209a72)

## Verdict
GREEN

## Round-2 fix integration
- [x/no] _host_of canonical parsing
- [x/no] www-prefix unification
- [x/no] empty-string rejection / numeric-0 acceptance
- [x/no] threat-model boundary 4 matches code

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D9 phase 2.
```

Be terse. Under 30 lines.
