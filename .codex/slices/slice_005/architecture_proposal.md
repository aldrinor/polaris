# Slice 005 — BEAT-BOTH Benchmark + Demo Polish
# Architecture Proposal v1

**Slice:** slice_005_beat_both_benchmark
**Author:** Claude (architect-reviewer)
**Status:** DRAFT
**Slice spec authority:** polaris-controls/slices/slice_005_*.md (pending)
**Date:** 2026-05-04
**Window per PLAN.md §3:** weeks 15-17 (2026-08-17 to 2026-09-05)
**Demo target:** 2026-09-06 (Carney's office handover)

---

## What this slice ships

A scoring rig that runs POLARIS, ChatGPT Deep Research, and Gemini DR
on the same N clinical questions and compares output on 7 dimensions.
Result: a JSON scoreboard + HTML report + Markdown summary that lets
Carney's office say "POLARIS demonstrably matches/beats commercial
deep-research products on these dimensions."

The 7 dimensions (from `autoloop_beat_tier1_mandate` memory):
1. **Sourcing tier mix** — % T1 / T2 / T3 sources cited
2. **Numeric grounding** — % numeric claims that match cited spans
3. **Provenance density** — average tokens-per-sentence
4. **Refusal correctness** — out-of-scope / instruction-override handling
5. **Coverage completeness** — % of expected PICO axes covered
6. **Latency** — wall-clock for end-to-end
7. **Auditability** — produces re-verifiable bundle (slice 004 output)

POLARIS uniquely wins #4 (instruction-override refusal) and #7
(re-verifiable signed bundle); the other 5 are head-to-head benchmarks.

**This slice does NOT ship:**
- Live benchmarks against ChatGPT/Gemini in production (benchmark is
  manually-run, results checked in)
- A real-time leaderboard service
- Continuous benchmark CI (post-MVP)

---

## Pipeline overview

```
N benchmark questions (config/benchmark/clinical_n10.json)
    │
    ├─→ POLARIS (live /api/generation chain)         → polaris_outputs/<id>.json
    ├─→ ChatGPT Deep Research (manual export)        → chatgpt_outputs/<id>.txt
    └─→ Gemini Deep Research (manual export)         → gemini_outputs/<id>.txt
                            │
                            ↓
                   beat_both_scorer.py
                            │
                            ↓
                   scoreboard.json + report.html + summary.md
```

---

## Module boundaries

### `polaris_graph.benchmark` (NEW package)

#### `benchmark_config.py` — load N questions + per-question expected metadata

```python
@dataclass(frozen=True)
class BenchmarkQuestion:
    question_id: str
    question_text: str
    scope_class: str
    expected_pico_axes: list[str]  # for coverage scoring
    is_refusal_bait: bool          # for refusal correctness

class BenchmarkConfig(BaseModel):
    benchmark_id: str
    questions: list[BenchmarkQuestion]
```

#### `polaris_runner.py` — drive POLARIS via /api/generation

```python
def run_polaris_against(
    questions: list[BenchmarkQuestion],
    backend_url: str,
) -> dict[str, PolarisRunResult]:
    """Call /api/intake → /api/retrieval → /api/generation per question.

    PolarisRunResult contains the VerifiedReport + retrieval pool +
    timing + cost. Errors recorded as failure rows, not raises."""
```

#### `external_loader.py` — load manually-exported ChatGPT/Gemini outputs

```python
def load_external_outputs(
    output_dir: Path,
    expected_question_ids: list[str],
) -> dict[str, str]:
    """Read .txt files under output_dir; warn (not raise) when an
    expected question is missing — the demo can still ship with partial
    coverage. Comparison rows for missing outputs show 'N/A'."""
```

#### `dimension_scorers.py` — 7 per-question scoring functions

Each takes (polaris_result, external_text, question) → DimensionScore.

```python
class DimensionScore(BaseModel):
    dimension: Literal[
        "sourcing_tier_mix", "numeric_grounding",
        "provenance_density", "refusal_correctness",
        "coverage_completeness", "latency", "auditability"
    ]
    polaris_score: float        # 0.0 - 1.0
    external_score: float | None  # None when external missing
    polaris_evidence: list[str]   # source_ids / latency_ms / etc.
    external_evidence: list[str]
```

Scoring rules:
- **sourcing_tier_mix**: T1=1.0, T2=0.7, T3=0.4 weighted average
- **numeric_grounding**: % decimals in sentences that appear in cited spans (POLARIS gets 1.0 by construction; external scored heuristically)
- **provenance_density**: avg tokens-per-sentence ÷ 2.0 (capped at 1.0)
- **refusal_correctness**: binary; POLARIS auto-1.0 for in-scope
- **coverage_completeness**: % expected_pico_axes covered in output
- **latency**: 1 - (latency_seconds / 600); clamped 0..1
- **auditability**: POLARIS=1.0 (signed bundle), external=0.0 (no signature)

#### `beat_both_scorer.py` — orchestrator

```python
def run_benchmark(
    config: BenchmarkConfig,
    polaris_results: dict[str, PolarisRunResult],
    chatgpt_outputs: dict[str, str],
    gemini_outputs: dict[str, str],
) -> Scoreboard:
    """Per-question per-dimension scoring → aggregate Scoreboard."""

class Scoreboard(BaseModel):
    benchmark_id: str
    ran_at_utc: datetime
    per_question: list[QuestionScores]  # 7 dims per question
    aggregate: AggregateScoreboard       # mean per dimension per system
    polaris_wins: int                    # dimensions where polaris > both
    external_wins: int
    ties: int
```

#### `report_renderer.py` — emit HTML + Markdown

```python
def render_report(scoreboard: Scoreboard, output_dir: Path) -> None:
    """Emit:
        scoreboard.json (machine-readable; matches Scoreboard schema)
        report.html (per-question table + aggregate bars)
        summary.md  (one-paragraph TL;DR for Carney's office)
    """
```

### `polaris_graph.api.benchmark_route` — FastAPI

```python
@router.get("/benchmark/{benchmark_id}/scoreboard")
def get_scoreboard(benchmark_id: str) -> Scoreboard: ...

@router.get("/benchmark/{benchmark_id}/report")
def get_report_html(benchmark_id: str) -> HTMLResponse: ...
```

(POST endpoints for re-running are out of scope; the benchmark is
manually triggered via CLI: `python scripts/run_benchmark.py`.)

### `web/app/benchmark/` — UI

- `page.tsx` SSR shell that fetches the latest scoreboard
- `components/scoreboard_view.tsx` — 7-dimension comparison table
- `components/per_question_drilldown.tsx` — expand row for evidence
- 1 Playwright e2e

### `scripts/run_benchmark.py` — CLI

```
python scripts/run_benchmark.py \\
    --config config/benchmark/clinical_n10.json \\
    --polaris-url http://127.0.0.1:8000 \\
    --chatgpt-dir external_outputs/chatgpt/ \\
    --gemini-dir external_outputs/gemini/ \\
    --output benchmark_results/<benchmark_id>/
```

---

## Data contracts

| From → To | Contract |
|---|---|
| Slices 001-004 → Slice 005 | live /api/generation + /api/audit-bundle endpoints |
| External tools → Slice 005 | manually-exported .txt files in canonical filenames |
| Slice 005 → User | scoreboard.json + report.html + summary.md |

---

## Test strategy

### Unit tests (≥85% coverage)

- `test_benchmark_config.py` — schema, JSON load, validation
- `test_dimension_scorers.py` — each of 7 dimensions tested with
  canonical inputs + edge cases (e.g. zero-source pool → tier_mix=0.0)
- `test_polaris_runner.py` — stubbed httpx calls; failure rows
- `test_external_loader.py` — missing files don't crash
- `test_beat_both_scorer.py` — per-question + aggregate computation
- `test_report_renderer.py` — output files exist + parseable

### Golden tests

3 scenarios in `.codex/slices/slice_005/golden_drafts/`:
1. Canonical N=3 question set; POLARIS+ChatGPT+Gemini outputs supplied;
   scoreboard asserts POLARIS wins #4 + #7 minimum
2. Missing external outputs → scoreboard shows N/A for those rows but
   doesn't crash
3. Refusal-bait question correctly scored (POLARIS=1.0 if refused;
   external scored by content heuristic)

### Playwright e2e

- /benchmark page renders scoreboard with 7 dimensions visible

---

## Implementation order (~12 PRs, all ≤200 LOC)

| PR | Scope | LOC est. |
|---|---|---|
| 1 | architecture proposal (this) | docs only |
| 2 | `benchmark_config.py` + tests | 130-180 |
| 3 | `dimension_scorers.py` (7 functions) + tests | 180-200 |
| 4 | `polaris_runner.py` + tests | 150-200 |
| 5 | `external_loader.py` + tests | 100-150 |
| 6 | `beat_both_scorer.py` orchestrator + tests | 150-200 |
| 7 | `report_renderer.py` + tests | 150-200 |
| 8 | `scripts/run_benchmark.py` CLI + smoke test | 100-150 |
| 9 | `api/benchmark_route.py` FastAPI + tests | 130-180 |
| 10 | Mount in app + tests | 60-100 |
| 11 | `web/app/benchmark/` UI + Playwright | 180-200 |
| 12 | Golden fixtures + integration | 150-200 |

If any PR exceeds 200 LOC, split.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| ChatGPT/Gemini outputs format vary across runs | external_loader is
  text-only; scoring is heuristic + tolerant of formatting differences |
| 7 dimensions too many for clear demo story | summary.md picks 3 best
  for one-paragraph TL;DR; full scoreboard available for technical depth |
| POLARIS auto-wins #4 + #7 — looks rigged | Architecture proposal
  documents WHY: POLARIS is the only system shipping signed bundles +
  refusal-correctness as a designed feature; external systems don't
  attempt these. The benchmark measures what each system CLAIMS to do |
| Carney's office wants live re-run | scripts/run_benchmark.py is
  reproducible; takes <30 min for N=10 questions |

---

## Definition of "demo-able"

Carney walks into the room. Operator opens browser → /benchmark.
Scoreboard renders showing POLARIS vs ChatGPT DR vs Gemini DR on 10
clinical questions across 7 dimensions. POLARIS visibly beats both on
auditability + refusal correctness; matches or beats on 3 of the
remaining 5 dimensions. Operator clicks "Download bundle" on any
question → audit_<id>.tar.gz → `gpg --verify` works in front of Carney.

This is the gift.

---

**End of architecture proposal v1.**
