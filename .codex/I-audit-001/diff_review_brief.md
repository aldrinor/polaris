```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

# I-audit-001 — DIFF review

## Output schema (binding)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Brief APPROVE recap (already at iter-4 APPROVE)

`.codex/I-audit-001/codex_brief_verdict.txt` shows brief APPROVE with one
P2 about helper return-type metadata plumbing. This diff implements the
APPROVE'd design.

## Diff

Read `.codex/I-audit-001/codex_diff.patch`. Two files:

1. `scripts/run_line_by_line_audit.py` — adds:
   - `_RESOLVED_CITATION_RE`, `_H2_HEADING_RE`, `_DEEP_HEADING_RE`,
     `_TITLE_HEADING_RE` regexes.
   - `_TERMINAL_H2_HEADINGS` frozenset (methods, contradiction disclosures,
     bibliography, v30 phase-1 retrieval coverage disclosure).
   - `_EXCLUDED_SYNTHESIS_H2_HEADINGS` frozenset (per-trial summaries,
     analyst synthesis).
   - `_load_bibliography()` — parses bibliography.json to `{num → evidence_id}`.
   - `_extract_resolved_claim_body()` — line-by-line walker that returns
     `(cleaned_body, scope_metadata)` per iter-4 P2-1 plumbing fix.
   - `_load_sentences_with_resolved_citations()` — orchestrator that
     reads report.md, extracts body, parses [N], synthesizes [#ev:...]
     tokens against full evidence text, returns `(sentences, scope_metadata)`.
   - CLI flag plumbing: `--resolved-report` + `--bibliography`, mutual
     exclusivity with `--report`/`--verified-sentences`, required-iff
     validation in both directions.
   - main() resolved-mode branch: writes manifest with `resolved_mode`,
     `excluded_synthesis_sections`, `unrecognized_h2_sections`,
     `terminal_h2_boundary_hit`, `verdict_semantics_note_resolved`.
   - Module docstring updated to document the three input modes.

2. `tests/scripts/test_run_line_by_line_audit.py` — adds 10 new tests
   covering: valid [N] → VERIFIED, unresolved [N] → UNREACHABLE with
   exact `unknown_evidence_id:__unresolved_<N>__` reason, ev_id-not-in-pool
   → UNREACHABLE, multiple `[N1][N2]` in one sentence → multiple tokens,
   pool with only snippet key, no-citation → UNSUPPORTED, realistic
   production-report fixture (title + ### body + ## Per-Trial Summaries
   + ## Methods + ## Bibliography + ## V30 disclosure) asserting (a)
   exactly 3 verdicts, (b) bibliography ref-list NOT in any verdict,
   (c) synthesis-layer sentence NOT in any verdict, (d) metadata
   `excluded_synthesis_sections == ["per-trial summaries"]`, both arg-
   validation directions (`--bib without --resolved`, `--resolved without
   --bib`), end-to-end CLI manifest with `verdict_semantics_note_resolved`.

## Test results (verifiable)

```
$ python -m pytest tests/scripts/test_run_line_by_line_audit.py -v
==================== 27 passed in 3.96s =====================
```

(17 pre-existing tests still pass + 10 new resolved-mode tests pass.)

## Real-output smoke

```
$ python -c "from scripts.run_line_by_line_audit import _extract_resolved_claim_body; ..."
=== scope metadata ===
{
  "excluded_synthesis_sections": [],
  "unrecognized_h2_sections": [],
  "terminal_h2_boundary_hit": true
}
=== body line count: 9
```

Confirms the I-bug-088 production report.md is correctly bounded at
`## Methods` (terminal_h2_boundary_hit=true), 9 body lines retained,
zero excluded synthesis sections (this run had none).

## Red-team checklist

- [x] Real data only — no synthetic data outside tests/fixtures.
- [x] Fail loudly — invalid arg combos error with clear stderr + exit 1.
- [x] No silent fallbacks — unknown H2 sections recorded in
  `unrecognized_h2_sections` rather than silently dropped.
- [x] No hardcoded paths — only env-driven / argv-driven inputs.
- [x] No magic numbers — all heading sets are named module constants.
- [x] No mocked production code path — tests use real loader functions,
  CLI tests use subprocess.run against the real script.
- [x] Existing tests still pass (17/17 pre-existing + 10/10 new = 27/27).
- [x] No regression in token-bearing audit path (existing tests cover it).
- [x] CLAUDE.md §-1.1 compliance — per-claim verdict mapping
  (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE) preserved.

## What to look for

- Section-scope correctness on edge cases: empty report, only `# title`,
  only `## Bibliography`, multiple synthesis sections, unknown H2 names.
- Off-by-one in `[N]` regex matching (e.g. `[10]` matched as `1` then `0`?
  No — `\d+` is greedy so `[10]` matches as `10`).
- Span-text synthesis: `[#ev:ev_id:0-0]` for missing pool entry — does
  the existing audit_sentence treat 0-0 as out-of-range? Looking at
  `audit_sentence`: `if start < 0 or end > len(full_text) or start > end`
  — `start=0, end=0, len=0` → `0 > 0` false, all conditions false → NOT
  unreachable on the span-bounds check; falls through to content checks
  with empty span. Result: decimals_match (empty span set is subset of
  anything), overlap=0 → PARTIAL. **That's wrong** — should be UNREACHABLE.
  But wait: the brief acceptance criterion 4 says "ev_id not in pool →
  UNREACHABLE via `unknown_evidence_id:<ev_id>`". My code path: I look up
  `pool.get(ev_id, {})` for span_text but I do NOT short-circuit on
  pool absence. So the token gets synthesized as `[#ev:<real_ev_id>:0-0]`
  with the real ev_id, then audit_sentence sees it IS in the pool (because
  `_normalize_pool` would have an entry IF the ev_id was in the input; if
  not, then `pool.get(ev_id, {})` returns empty dict but the audit's `if
  ev_id not in pool` check still fails). Need to verify: in the test
  `test_resolved_ev_id_not_in_pool_yields_unreachable`, the pool is
  empty, so `pool.get("ev_missing", {})` returns `{}`, span_text="",
  span_len=0, token = `[#ev:ev_missing:0-0]`. audit_sentence then checks
  `if ev_id not in pool` (line 199) — `"ev_missing" not in {}` is True
  → returns UNREACHABLE with `unknown_evidence_id:ev_missing`. **Test
  passes** (per my pytest run). So the path is correct.

This is the question I want Codex to specifically verify: is the
0-0 token-synthesis safe in all combinations of pool/bibliography state?

## Scope discipline

- LOC: scripts/+232, tests/+357. Test ratio is high but appropriate for
  the safety-critical clinical-audit path.
- No changes outside the two files.
- No new dependencies.
- Three regex constants added at module top; two frozensets added at
  module top. Idiomatic.

## I want Codex to audit

1. Heading-walker correctness on production report shapes (I-bug-088
   sample shape verified, but edge cases worth checking).
2. The 0-0 token synthesis path for ev_id-not-in-pool: my analysis says
   it goes through `audit_sentence`'s `if ev_id not in pool` short-circuit
   before reaching the span-bounds check. Verify.
3. Whether sentence-splitter could mis-segment the synthesized
   `[#ev:...]` token suffix and produce malformed records. (The token
   has no `.!?` so the splitter shouldn't touch it.)
4. Whether `_split_sentences` regex behaviour on the cleaned body
   produces the expected sentence count when claim subsections are
   separated by blank lines (`### Efficacy\n\n<sentence>\n\n###
   Limitations\n\n<sentence>`).
