HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# DIFF gate — I-cap-002 feature 2/4 (#1060): advisory analytical-depth annotation

This is the **DIFF** gate. Review the committed code against the design brief
(`.codex/I-cap-002-depth/brief.md`, your brief-gate APPROVE iter-2 is in
`.codex/I-cap-002-depth/codex_brief_verdict.txt`). The patch is `.codex/I-cap-002-depth/codex_diff.patch`
(branch `bot/I-cap-002-depth` on top of `bot/I-cap-002-storm`).

## What the diff does (6 files, +344/-58; ~58 of the new lines are the heuristic RELOCATED verbatim)
1. **NEW `src/polaris_graph/generator/analytical_depth.py`** (stdlib only: `re` + typing).
   - `evaluate_analytical_depth(report_sections)` — body MOVED VERBATIM from
     `synthesizer._evaluate_analytical_depth` (same regex strings, same per-section `ops_present`
     logic, same thresholds 10/2/3/3/≤2, same return keys). Verified equal at runtime:
     `legacy(secs) == shared(secs)` (delegate parity smoke passed).
   - `split_report_into_sections(report_md)` — splits assembled markdown on ATX headers
     `^#{1,6}\s+title`; text before the first header → a `Preamble` section; header line excluded
     from content (Pipeline B scores `section["content"]`, the body); empty/blank → `[]`.
2. **`synthesizer.py`** — `_evaluate_analytical_depth` becomes a 1-call delegate to the new module.
   RC-8 behavior preserved (verified by parity smoke + `tests/v3` 33/34, the 1 failure pre-existing).
3. **`run_honest_sweep_r3.py`** (success path, ~L4905, AFTER the 4-role seam status/release overwrite +
   V30 report.md append + cost recompute) — ON-mode-only (`PG_DEPTH_ANNOTATION_IN_BENCHMARK`), fail-open:
   reads the FULL on-disk `report.md` (fallback to in-memory `final_report`), computes the depth dict,
   sets `advisory=True` + `surface="benchmark_atx_split"`, writes `analytical_depth.json` FIRST, then
   stamps `manifest["analytical_depth_advisory"]`, logs a `[depth]` line. Never mutates
   status/release/abort. Flag OFF → manifest byte-unchanged.
4. **`run_gate_b.py::run_gate_b_query`** — `os.environ.setdefault("PG_DEPTH_ANNOTATION_IN_BENCHMARK","1")`
   alongside the existing `PG_ENABLE_QUANTIFIED_ANALYSIS` / `PG_V30_*` activations (your brief-gate P1).
5. **`tests/polaris_graph/test_analytical_depth.py`** (NEW, 10 tests) — marker counts, deficient flag,
   `passed` threshold boundary, malformed/empty safety, splitter multi-header/Preamble/H2-H3/empty, and
   the KNOWN benchmark behavior: front `## Key Findings` ATX block is NOT counted (conservative
   undercount), per-section `**Key Findings**` bold IS counted.
6. **`tests/dr_benchmark/test_benchmark_stack_activation_meta007.py`** (extended) — asserts
   `PG_DEPTH_ANNOTATION_IN_BENCHMARK == "1"` at `run_one_query` time; `_clear_flags()` pops it.

## Your brief-gate iter-2 P2s — how the diff handled them (please verify)
- **P2 (V30 appends after final_report):** the annotation now reads the on-disk `report.md` (post-V30),
  fallback to `final_report` — so the V30 Methods disclosure IS in the scored surface.
- **P2 (front Key Findings is ATX, undercounted):** heuristic kept VERBATIM (no Pipeline-B drift);
  documented in the module docstring + tested explicitly (`test_front_atx_key_findings_is_known_…`).
- **P2 (ATX split changes deficient semantics vs RC-8):** documented in the module docstring + the
  annotation comment that benchmark `passed`/`deficient_sections` are an advisory split read, NOT the
  RC-8 verdict; dict also carries `surface="benchmark_atx_split"` + `advisory=True`.

## Red-team checklist — please confirm
- **Advisory/non-gating:** the block ADDS a manifest key + sidecar and never touches
  `status`/`release_allowed`/`summary_status`/abort. Placed after ALL status mutations.
- **Fail-open:** any exception (incl. the inner `report.md` read) logs + skips; the run completes.
- **Flag OFF → byte-unchanged** legacy manifest (key absent), matching the research_plan/saturation/
  finding_dedup/quantified_analysis ON-mode-only precedent.
- **Faithfulness:** reads delivered report text only; produces no evidence/`direct_quote`/claims.
- **Parity:** is `evaluate_analytical_depth` truly byte-equivalent to the prior inline function? Any
  subtle behavioral difference in the delegate?
- **Splitter correctness:** does `split_report_into_sections` mis-handle any delivered-report shape
  (e.g. a `|`-table row that looks like a header? a `#` inside a code fence? lines starting with `#`
  that aren't headers)? Is any of that a real risk for the advisory metric, or P3?
- **LOC:** net production delta is ~142 (much relocated); tests +137. Acceptable for a single-feature
  extraction PR, or do you want it split?

## Smoke evidence (offline, already run)
- `pytest tests/polaris_graph/test_analytical_depth.py tests/dr_benchmark/test_benchmark_stack_activation_meta007.py` → 14 passed.
- delegate parity: `legacy(secs) == shared(secs)` → True.
- `pytest tests/v3/test_integration.py` → 33 passed, 1 failed (`TestSandboxFileIO::test_script_can_access_sandbox_dirs`, `Blocked import 'os'` — PROVEN pre-existing: fails identically with my changes stashed).
- `py_compile` on all 4 touched src/scripts files → OK.

## Acceptance (GREEN)
Zero NOVEL P0, zero continuing P0, zero P1. The feature is advisory + fail-open + flag-OFF-byte-unchanged,
so any residual concern about the metric's exact counting is at most P2 (it never gates).
