HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

# Brief — I-cap-002 feature 2/4 (#1060): advisory analytical-depth annotation in the benchmark path

## CHANGELOG vs iter 1 (your REQUEST_CHANGES findings, all addressed)
- **P1 (Gate-B silent / missing activation) — FIXED in design.** `run_gate_b_query` now activates the flag
  via `os.environ.setdefault("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "1")`, alongside the existing
  `PG_ENABLE_QUANTIFIED_ANALYSIS` / `PG_V30_PHASE2_ENABLED` activations (run_gate_b.py L436-459). So the
  paid Gate-B run fires the annotation; the legacy honest-sweep `run_one_query` default stays OFF
  (byte-unchanged). `setdefault` keeps the operator override (LAW VI). See §4.5.
- **P2.1 (insertion before the 4-role overwrite) — FIXED.** The block moves to just BEFORE the
  `manifest.json` write (~L4905), AFTER the 4-role seam status/release overwrite (L4740-4751), the V30
  block (L4810+), and the cost recompute (L4904). status/release_allowed are final there. See §4.3.
- **P2.2 (input surface too narrow) — FIXED.** The metric is now computed over the FULL assembled
  delivered report (`final_report`) via a new tested `split_report_into_sections()` helper, so appended
  blocks (Key Findings, Trial Summary tables, Per-Trial, Limitations) ARE counted. Surface defined + tested.
  See §4.1 + §4.3.
- **P2.3 (manifest key without sidecar) — FIXED.** The sidecar `analytical_depth.json` is written FIRST;
  `manifest["analytical_depth_advisory"]` is assigned only AFTER the write succeeds. See §4.3.
- **P2.4 (launcher activation regression) — FIXED.** Extend the existing
  `tests/dr_benchmark/test_benchmark_stack_activation_meta007.py::test_gate_b_query_sets_both_flags_…` to
  also assert `PG_DEPTH_ANNOTATION_IN_BENCHMARK == "1"` at `run_one_query` time. See §4.2.

## 0. What this gate reviews
This is the **BRIEF** gate (design + acceptance criteria correctness). Code does not exist yet; a separate
diff gate reviews the implementation. Review the DESIGN. Do not flag "code not present" — that is the next
gate.

## 1. Context — the umbrella issue
Operator directive 2026-06-04: "B then A". B = wire the four Tier-B deep-research capabilities into the
**benchmark path (Pipeline A)**; A = then run the Tier-A 1000-URL beat-both on the OVH VM. POLARIS has TWO
pipelines: Pipeline A (benchmark: `run_gate_b` → `run_honest_sweep_r3.run_one_query` → `live_retriever` →
4-role seam) and Pipeline B (web-UI LangGraph `graph.py` + `agents/`). The Tier-B capabilities live in
Pipeline B and are NO-OPs for the benchmark. Issue #1060 wires them in, one small fallback-safe PR each.
Feature **1/4 (STORM)** is DONE — Codex diff-gate APPROVE iter-3, PR #1061. This is **feature 2/4:
depth-gate**, scoped as an **advisory, non-gating annotation** (operator-approved scope: "advisory
annotation, stdlib only").

## 2. The capability today (Pipeline B only)
`src/polaris_graph/agents/synthesizer.py::_evaluate_analytical_depth(report_sections) -> dict` (L813-880)
is a pure stdlib regex heuristic. Across all report sections it counts:
- **comparison_markers** — `compared to | in contrast | whereas | however | unlike | …`
- **aggregation_patterns** — `across N studies | multiple sources | ranged from | median of | …`
- **challenge_markers** — `limitation | conflicting | gap in | insufficient evidence | remains unclear | …`
- **tables** — markdown table rows `|...|...|`
- **key_findings** — `**Key Findings**` headers
Per section: `ops_present = sum(comp>0, agg>0, chal>0, tables>0, kf>0)`; a section is "deficient" if
`ops_present < 2`. Returns `passed` (comparison≥10 AND tables≥2 AND key_findings≥3 AND challenge≥3 AND
len(deficient)≤2) plus the raw counts + deficient list. In Pipeline B this drives the **RC-8 gate**
(synthesizer L3633-3668). It is the ONLY consumer; it has **no dedicated unit test**.

In the **benchmark (Pipeline A)** this never runs — so we have no machine-readable signal of whether a
delivered POLARIS report is analytically deep (comparisons, aggregation, trade-off/limitation framing,
summary tables) vs a flat fact list. That signal is what an auditable "beat ChatGPT/Gemini DR" claim needs
per §-1.1.

## 3. Goal of feature 2/4
Surface the analytical-depth metrics on the **benchmark manifest** + a sidecar, computed on the **full
delivered report** of each run — as an **ADVISORY annotation that NEVER gates**. Observability only: never
changes `release_allowed`, `status`/`summary_status`/`unified_status`, or any abort path.

## 4. Design (what the diff will implement)

### 4.1 Extract the heuristic to a stdlib-only shared module (no duplication — LAW V)
New file `src/polaris_graph/generator/analytical_depth.py` (stdlib only: `re`, `from __future__`,
`typing`). Hosts TWO pure functions:
```python
def evaluate_analytical_depth(report_sections: list[dict]) -> dict:
    # body MOVED VERBATIM from synthesizer._evaluate_analytical_depth: same regex strings, same
    # per-section ops_present logic, same thresholds, same return keys (passed, comparison_markers,
    # aggregation_patterns, challenge_markers, tables, key_findings, deficient_sections).

def split_report_into_sections(report_md: str) -> list[dict]:
    """Split assembled markdown into [{title, content}] on ATX headers (lines matching ^#{1,6}\\s).
    Text before the first header becomes a single {"title": "Preamble", "content": ...} section
    (this captures the leading Key Findings block). Returns [] for empty/blank input. Pure stdlib."""
```
Then in `synthesizer.py`, `_evaluate_analytical_depth` becomes a **behavior-preserving delegate**:
```python
def _evaluate_analytical_depth(report_sections: list[dict]) -> dict:
    from src.polaris_graph.generator.analytical_depth import evaluate_analytical_depth
    return evaluate_analytical_depth(report_sections)
```
Rationale: the benchmark must not import `synthesizer.py` (it pulls `OpenRouterClient`, tracer, schemas,
state, section_writer — heavy, with construction side-effects). Extraction gives a stdlib-only import AND a
single source of truth so the two pipelines cannot drift. Pipeline B's RC-8 behavior is **byte-identical**
(same regexes/thresholds/keys); the `tests/v3` RC-8 integration path stays green.

### 4.2 New stdlib-only unit tests
`tests/polaris_graph/test_analytical_depth.py`:
- `evaluate_analytical_depth`: counts across multiple sections; per-section `ops_present < 2` deficient flag;
  `passed` threshold boundary (comparison 10 vs 9, tables 2 vs 1); empty/missing `content`/`title` keys are
  safe (no raise); markdown-table detection.
- `split_report_into_sections`: multi-header split; Preamble capture (text before first header); a Key
  Findings block in the preamble is counted; `## ` and `### ` both split; empty/blank → `[]`; a report with
  no headers → one Preamble section.
Plus extend `tests/dr_benchmark/test_benchmark_stack_activation_meta007.py`:
- `test_gate_b_query_sets_both_flags_…` additionally asserts
  `captured["PG_DEPTH_ANNOTATION_IN_BENCHMARK"] == "1"` and `_clear_flags()` also pops it.

### 4.3 Wire the advisory annotation into `run_one_query` (success path only)
In `scripts/run_honest_sweep_r3.py`, immediately BEFORE the success-path `manifest.json` write (~L4905,
AFTER `augment_v6_manifest` + the `run_cost = current_run_cost()` recompute at L4903-4904, so status,
release_allowed, four_role_evaluation, V30, and cost are all final), add an **ON-mode-only, fail-open**
block:
```python
# I-cap-002 feature 2/4 (#1060): ADVISORY analytical-depth annotation. Never gates.
# Placed AFTER the 4-role seam + V30 manifest mutations so status/release_allowed are final.
if os.environ.get("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "0").strip() in ("1", "true", "True"):
    try:
        from src.polaris_graph.generator.analytical_depth import (
            evaluate_analytical_depth, split_report_into_sections,
        )
        _depth = evaluate_analytical_depth(split_report_into_sections(final_report))
        _depth["advisory"] = True  # benchmark NEVER gates on this signal
        # P2.3: sidecar FIRST; only then stamp the manifest key, so the two cannot disagree.
        (run_dir / "analytical_depth.json").write_text(
            json.dumps(_depth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["analytical_depth_advisory"] = _depth
        _log(f"[depth]       advisory comparisons={_depth['comparison_markers']} "
             f"tables={_depth['tables']} key_findings={_depth['key_findings']} "
             f"challenges={_depth['challenge_markers']} "
             f"deficient={len(_depth['deficient_sections'])} (non-gating)")
    except Exception as _depth_exc:  # noqa: BLE001 — advisory; never abort the run
        _log(f"[depth]       WARN advisory annotation skipped (fail-open): {_depth_exc}")
```
`final_report` (assembled at L4119) and `manifest` (built at L4440, mutated through L4904) are both in scope
here.

### 4.4 Wire activation at the Gate-B benchmark entrypoint
In `scripts/dr_benchmark/run_gate_b.py::run_gate_b_query`, alongside the existing ON-mode activations
(L436-459), add:
```python
# I-cap-002 feature 2/4 (#1060): turn on the ADVISORY analytical-depth annotation for the
# benchmark/paid run ONLY here (gate-B entry), never globally. setdefault keeps the operator
# override (LAW VI). The annotation is non-gating + fail-open, so this can never withhold release.
os.environ.setdefault("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "1")
```
This is the P1 fix: the paid Gate-B run emits `analytical_depth.json` + `manifest['analytical_depth_advisory']`
without any out-of-band env, mirroring `PG_ENABLE_QUANTIFIED_ANALYSIS` / `PG_V30_PHASE2_ENABLED`.

### 4.5 Invariants the diff MUST hold
1. **Advisory only** — the block runs AFTER all status/release_allowed mutations and only ADDS a manifest
   key + a sidecar. Never mutates status/release/abort. Dict carries `advisory: True`.
2. **Flag default OFF in `run_one_query` → legacy path byte-unchanged**; Gate-B turns it ON at the
   entrypoint (precedent: research_plan/saturation/finding_dedup/quantified_analysis are ON-mode-only keys).
3. **Fail-open** — any exception logs `[depth] WARN … (fail-open)`; the run completes normally.
4. **Faithfulness-untouched** — depth reads the already-delivered `final_report` (post strict_verify +
   4-role). Produces no evidence, no `direct_quote`, no new claims. Zero faithfulness surface.
5. **Stdlib only** — the new module imports only `re` + typing. Zero new dependency; zero network; zero cost.
6. **Success path only** — abort/hold paths have no delivered report to annotate; not wired there.
7. **No new magic numbers** — thresholds are MOVED VERBATIM from the Pipeline-B heuristic, not invented.

## 5. Files I have ALSO checked and they're clean
- `src/polaris_graph/contracts_v3.py:270` `analytical_depth` Field — a SEPARATE draft dict (charts/depth),
  NOT this function; untouched.
- `src/polaris_graph/nodes/synthesize.py:395,532` — builds its own `analytical_depth` dict from a draft;
  unrelated; untouched.
- `src/polaris_graph/tools/react_agent.py:5911,6077` — an LLM "analytical_depth" review dimension; unrelated;
  untouched.
- `tests/v3/conftest.py:192`, `tests/v3/test_integration.py:663` — the unrelated contracts `analytical_depth`
  dict field; stay green.
- Only consumer of `_evaluate_analytical_depth` is `synthesizer.py:3636` (RC-8). The delegate preserves it.
- Benchmark manifest ON-mode-only precedent: `run_honest_sweep_r3.py` L4535 (research_plan), L4551
  (saturation), L4557 (finding_dedup), L4564 (quantified_analysis). Gate-B activation precedent:
  `run_gate_b.py` L436 (PG_ENABLE_QUANTIFIED_ANALYSIS), L447-459 (PG_V30_* + setdefault enhancers).
- `final_report` assembled at `run_honest_sweep_r3.py:4119`; `manifest.json` write at L4906; cost recompute
  at L4903-4904; 4-role status overwrite at L4740-4751 — all confirmed in scope/order.

## 6. Acceptance criteria (GREEN)
- New `src/polaris_graph/generator/analytical_depth.py` (stdlib only) hosts `evaluate_analytical_depth` +
  `split_report_into_sections`.
- `synthesizer._evaluate_analytical_depth` delegates to it; Pipeline-B RC-8 behavior unchanged; `tests/v3`
  integration path green.
- `tests/polaris_graph/test_analytical_depth.py` passes (function counts, deficient flag, threshold boundary,
  safety; splitter multi-header/Preamble/no-header/empty).
- `run_gate_b_query` sets `PG_DEPTH_ANNOTATION_IN_BENCHMARK` (setdefault); the extended activation test
  asserts it == "1" at `run_one_query` time.
- `run_one_query` success path, with the flag ON, writes `analytical_depth.json` then stamps
  `manifest["analytical_depth_advisory"]` (sidecar-first ordering) and logs a `[depth]` advisory line;
  with the flag OFF the legacy manifest is byte-unchanged.
- The annotation NEVER changes `status`/`release_allowed`/`summary_status` and fails open.
- ≤ ~200 LOC.

## 7. Smoke plan (offline, before the diff gate)
1. `pytest tests/polaris_graph/test_analytical_depth.py -q`.
2. `pytest tests/dr_benchmark/test_benchmark_stack_activation_meta007.py -q` (activation incl. depth flag).
3. `pytest tests/v3/test_integration.py -q` (RC-8 path unchanged) + import-smoke `synthesizer`.
4. `python -c` on a tiny synthetic assembled report (title + Key Findings + 2 `###` sections + Limitations)
   → confirm `split_report_into_sections` captures all blocks and the advisory dict shape (offline).

## 8. Questions for the gate
- Is computing on `split_report_into_sections(final_report)` the right "full delivered surface", or do you
  want it restricted to body sections with an explicit name (`…_body_only`)? (I chose full delivered report
  so the appended tables/key-findings/limitations — which the heuristic specifically rewards — are counted.)
- Is `analytical_depth_advisory` (with `advisory: True`) a clear enough non-gating key name?
