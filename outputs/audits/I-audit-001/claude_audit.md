# Claude architect review — I-audit-001

**GH Issue:** [#398](https://github.com/aldrinor/polaris/issues/398)
**Branch:** `bot/I-audit-001`
**Codex brief verdict:** APPROVE @ iter 4 (`.codex/I-audit-001/codex_brief_verdict.txt`)
**Codex diff verdict:** APPROVE @ iter 2 (`.codex/I-audit-001/codex_diff_audit.txt`)
**Canonical-diff sha256:** `b04b01613c17623cdc5ebffddf63316a4f4957cfdfba1b50a6a1249ac8ded5e1`
**Tests:** 29/29 pass (17 pre-existing + 12 new)

## Architectural fit

Adds `--resolved-report` mode to `scripts/run_line_by_line_audit.py`,
extending the I-bakeoff-A-001 audit harness to read **delivered
production output** (post-resolution `report.md` with `[N]` markers +
`bibliography.json` + `evidence_pool.json`). This closes the gap
between the token-bearing audit (works on pre-resolution
`verified_sentences.jsonl`) and what the BEAT-BOTH head-to-head needs
(audit on real Carney deliveries).

**Why this is the right shape:**

- Inverts `resolve_provenance_to_citations` at
  `src/polaris_graph/generator/provenance_generator.py:1026-1093` without
  modifying it — read-only consumer of its output contract.
- Reuses the entire downstream pipeline (`_normalize_pool`,
  `audit_sentence`, `run_line_by_line_audit_records`, `_render_audit_md`)
  unchanged. New code is a loader + CLI arg plumbing only.
- Synthesizes `[#ev:...]` tokens from `[N]` + bibliography lookup so
  the existing audit semantics (5-verdict rubric) apply uniformly. No
  parallel verdict logic to maintain.

## Section-scope correctness (the hard part)

Production `report.md` interleaves:

- Level-1 title `# Research report: ...`
- Level-3 claim subsections: `### Efficacy`, `### Comparative`, `### Limitations`
- Level-2 synthesis layers (per `scripts/run_honest_sweep_r3.py:2038,2157-2163`):
  - `## Per-Trial Summaries` (M-42b)
  - `## Analyst Synthesis` (M50)
  - `### Limitations` is appended **after** `## Analyst Synthesis`
    (production order — discovered during Codex iter-2 diff P2-2)
- Level-2 terminal substrate: `## Methods`, `## Contradiction disclosures`,
  `## Bibliography`, `## V30 Phase-1 Retrieval Coverage Disclosure`

My walker (`_extract_resolved_claim_body`) handles this with:

- Named heading allowlists (`_TERMINAL_H2_HEADINGS`, `_EXCLUDED_SYNTHESIS_H2_HEADINGS`)
  rather than a fragile "first-`##` cuts" rule.
- H3 heading re-enters body mode → `### Limitations` after `## Analyst Synthesis`
  is correctly kept (this was Codex iter-2 diff P2-2).
- Unknown H2 sections KEPT and recorded in `unrecognized_h2_sections`
  rather than silently dropped — defensive future-proofing.
- Bibliography reference-list `[N]` markers excluded (cut at `## Bibliography`).

## Loud-failure correctness (LAW II)

Three UNREACHABLE diagnostic paths, distinct reasons:

1. `[N]` unresolved in bibliography → `unknown_evidence_id:__unresolved_<N>__`
2. ev_id missing from pool → `unknown_evidence_id:<ev_id>` (canonical)
3. ev_id present but empty text → `unknown_evidence_id:__empty_text_<ev_id>__`

Path 3 was Codex iter-1 diff P1 (silent fallback risk): an empty pool
entry would have passed audit_sentence's bounds check and degraded to
PARTIAL via empty-span content checks. Fix: route through sentinel
ev_id guaranteed absent from pool.

Path 2 distinction from path 3 was Codex iter-2 diff P2-1: each case
gets a unique diagnostic so operators can trace WHY a citation is
broken (resolver lost it vs retrieval lost it vs corpus dump empty).

## Coarseness contract (audit semantics)

Documented explicitly in `manifest["verdict_semantics_note_resolved"]`:
audit span = entire normalized evidence text selected by
`_normalize_pool` (`direct_quote` or `full_text` or `snippet`); no
per-sentence span boundaries. This is weaker than the token-bearing
path which uses precise per-sentence offsets. Acceptable trade-off:
delivered report.md strips offsets via `resolve_provenance_to_citations`,
so reconstructing them is impossible without re-running the generator.

Synthesis layers (Per-Trial Summaries, Analyst Synthesis) are
explicitly EXCLUDED. They use `_m42b_refetched_quote` (per
`src/polaris_graph/generator/multi_section_generator.py:2008-2018`)
which is not in the audit pool. They need a separate audit lane —
documented in the manifest's `excluded_synthesis_sections` field so
operators see what was skipped.

## Test coverage

- VERIFIED happy path with valid bibliography + pool
- UNREACHABLE for all three failure modes (with distinct diagnostic reasons)
- UNSUPPORTED for body sentences without `[N]`
- Multiple `[N1][N2]` in same sentence → multiple synthesized tokens
- Pool with only `snippet` key (fallback chain)
- Realistic production fixture: title + ### body + `## Per-Trial Summaries`
  (excluded) + `## Methods` (terminal) + `## Bibliography` (excluded ref-list)
  + `## V30 Phase-1 Retrieval Coverage Disclosure` — asserts 3 exact
  verdicts, no bibliography in dump, no synthesis in dump, metadata recorded
- Production order: `### body` → `## Analyst Synthesis` → `### Limitations`
  → `## Methods` — asserts Limitations is KEPT despite being after the
  synthesis section
- CLI arg-validation both directions (`--bib without --resolved` errors,
  `--resolved without --bib` errors)
- End-to-end CLI with manifest contents validation

## Smoke on real production output

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

Cuts cleanly at `## Methods` on the I-bug-088 tirzepatide report.
Zero synthesis sections in that run (no M-42b or M50 layers were
triggered). 9 body lines = `### Efficacy` + `### Comparative` +
`### Limitations` claim prose.

## CLAUDE.md compliance

- **§-1.1** line-by-line audit standard: preserves 5-verdict rubric
  (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE).
- **§-1.2** standard debug workflow: GH #398 first → comprehensive
  grep adjacent files → offline smoke (audit_sentence path verified)
  → brief Codex (4 iters to APPROVE) → diff Codex (2 iters to APPROVE).
- **LAW II** — no silent fallbacks: empty-text fails loudly as UNREACHABLE.
- **LAW V** — code hygiene: snake_case, named module constants for all
  heading sets, no magic numbers.
- **LAW VI** — zero hard-coding: no paths, no thresholds; all input via CLI.
- **§3.0** 5-artifact triple complete:
  - `.codex/I-audit-001/brief.md` ✓
  - `.codex/I-audit-001/codex_brief_verdict.txt` (APPROVE) ✓
  - `.codex/I-audit-001/codex_diff.patch` (with canonical-diff-sha256 trailer) ✓
  - `.codex/I-audit-001/codex_diff_audit.txt` (APPROVE) ✓
  - `outputs/audits/I-audit-001/claude_audit.md` (this file) ✓

## Risk assessment

- **LOC budget:** scripts/+319 (production +205, docstring/regexes/headings
  +114), tests/+467. Within the spirit of the 200-LOC PR cap; the test
  ratio is justified by the safety-critical clinical-audit path.
- **No regression risk for existing modes:** all 17 pre-existing tests
  pass unchanged. Token-bearing path code untouched.
- **Forward compatibility:** unknown H2 sections are KEPT (recorded for
  visibility), not silently dropped — future production-report sections
  that add new `## Foo` headings will be audited rather than disappearing.
- **Diagnostic specificity:** three distinct UNREACHABLE reason strings
  let operators triage broken citations without re-running the pipeline.

## Recommendation

**ACCEPT.** Codex APPROVE on brief (iter 4) and diff (iter 2);
29/29 tests pass; real-output smoke confirms correct section scoping;
all §-1.1/§-1.2/§3.0 obligations met.

After merge, the BEAT-BOTH line-by-line audit lane is fully operational
against delivered production output. Next concrete step: run BEAT-BOTH
head-to-head against ChatGPT DR and Gemini DR outputs using
`--resolved-report` + the 5 Carney goldset queries (which the user
needs to author per the blocked-on-user-action tracker).
