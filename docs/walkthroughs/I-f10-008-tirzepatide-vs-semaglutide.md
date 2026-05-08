# F10 walkthrough — tirzepatide vs semaglutide (substrate-honest demo)

**Issue:** I-f10-008
**Branch trajectory:** I-f10-001 (Vega-Lite renderer) → I-f10-002 (Forest plot) →
I-f10-003 (Comparison table) → I-f10-004 (Timeline) → I-f10-005 (ChartProvenance schema) →
I-f10-006 (Click-through-to-source) → I-f10-007 (Sandboxed Python execution) → **I-f10-008
(this walkthrough)**.

## Purpose

This walkthrough exercises the F10 chart substrate end-to-end on a clinical research
question, demonstrating what ships TODAY in the polaris repo against what is wired
post-Carney.

**Honest scope (per CLAUDE.md §9.4 + LAW II):** the polaris pipeline does NOT yet
auto-generate Vega-Lite specs from real LLM-retrieved evidence on the
tirzepatide-vs-semaglutide question. **The clinical question itself is NOT answered
by live evidence today.** The demo routes show the chart-and-source-span SUBSTRATE
with placeholder data:

- `/charts_test/comparison_table` shows a Q3 housing-starts dataset (5 provinces ×
  2 metrics), NOT pharmaceutical efficacy data.
- `/charts_test/click_through` shows a SELECT-trial-style cardiovascular forest plot
  (MACE / MI / Stroke), NOT a tirzepatide-vs-semaglutide head-to-head.

The walkthrough validates that the F10 substrate (chart spec generators, renderer,
click-through, provenance contract, sandboxed analysis) ships and works end-to-end.
Live evidence wiring for the actual clinical question is tracked post-Carney.

---

## Setup

Standard local dev:

```powershell
cd web
npm install
npm run dev
```

This starts Next.js on `http://localhost:3000` (the default `next dev` port; the
Playwright e2e config uses port 3738 separately for `next start` — see
`web/playwright.config.ts`).

---

## Step 1: Comparison table — auto-generated with citations

**Visit:** `http://localhost:3000/charts_test/comparison_table`

**Expected:** three sections, each rendering a `<VegaChart>` with a Vega-Lite v5 bar
chart:

- `[data-testid="comparison-table-n2"]` — 2 entities × 1 metric (Ontario, Quebec).
- `[data-testid="comparison-table-n3"]` — 3 entities × 1 metric.
- `[data-testid="comparison-table-n5"]` — 5 entities (Ontario / Quebec / BC /
  Alberta / Manitoba) × 2 metrics (`starts_thousands`, `completions_thousands`) =
  **10 entity-metric data rows / 10 evidence_ids**.

**What to verify:**

- Each chart renders an SVG (`renderer: "svg"` per `web/components/ui/vega-chart.tsx:42`).
- Every datum carries `evidence_id` from `polaris_provenance` (see
  `src/polaris_v6/charts/spec_builder.py:127` for the canonical Python builder; the
  TS mirror lives at `web/lib/comparison_table_spec.ts`).
- No `[data-testid="vega-chart-error"]` is rendered.

**Auto-coverage:** `web/tests/e2e/comparison_table_chart.spec.ts` asserts each N
section renders ≥N graphics-symbol marks.

---

## Step 2: Click-through to source span

**Visit:** `http://localhost:3000/charts_test/click_through`

**Expected:** a forest-plot rendering of a SELECT-trial-style cardiovascular
meta-analysis (MACE / MI / Stroke). Click any point.

**On click:**

- `<ChartSourceInspector>` Sheet pane opens (right side, 40% width).
- The pane displays:
  - `[data-testid="chart-source-pane-evidence-id"]`: e.g., `demo-clin-001`.
  - `[data-testid="chart-source-pane-tier"]`: T1 badge.
  - `[data-testid="chart-source-pane-url"]`: link to
    `https://example.org/select-trial-...` (demo URL — placeholder for real cited URL).
  - `[data-testid="chart-source-pane-excerpt"]`: blockquote with the excerpt text
    (e.g., "MACE composite endpoint: -20% relative risk reduction (95% CI -27% to
    -13%) at 3-year follow-up.").

**What to verify:**

- Click → pane opens within ~100ms.
- Source span fields (URL + tier + excerpt) all visible.
- No `[data-testid="vega-chart-error"]`.

**Auto-coverage:** `web/tests/e2e/chart_click_through.spec.ts` clicks the first
graphics-symbol mark and asserts evidence_id + URL href + tier + excerpt visible.

**Honest gap:** the `SOURCE_REGISTRY` keyed by `evidence_id` is hand-authored demo
data in `web/app/charts_test/click_through/page.tsx:36`. In production, the click
handler would fetch `/runs/{run_id}/sources/{evidence_id}` from the FastAPI backend
(per the I-f10-005 polaris_provenance contract); that wiring is post-Carney.

---

## Step 3: ChartProvenance contract

The polaris_provenance extension on every chart spec is now formally typed (per
I-f10-005). The contract:

```python
class ChartProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chart_type: Literal["forest_plot", "comparison_table", "timeline"]
    evidence_ids: list[str] = Field(min_length=1)
    period_kind: TimelinePeriodKind | None = None
    # cross-field validator: timeline ⇔ period_kind set
```

**Test coverage:** `tests/v6/test_chart_provenance.py` runs 11 tests:

- 3 valid round-trips (forest plot / comparison table / timeline).
- 8 adversarial (missing key, non-dict container, empty/blank evidence_ids,
  unknown chart_type, timeline w/o period_kind, non-timeline w/ period_kind, extra
  field).

**Run:**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/v6/test_chart_provenance.py -v
# 11 passed
```

---

## Step 4: Sandboxed Python execution sovereignty

The LLM-driven analysis path (`generate_and_execute_analysis` in
`src/polaris_graph/tools/code_executor.py`) runs untrusted Python in a sandboxed
subprocess. I-f10-007 hardened the sandbox:

- AST-based import allowlist enforcement (closes comma-separated imports).
- AST-based reflection-attribute blocklist (`__builtins__`, frame paths,
  `ctypeslib`, sys.modules subscript via `vars(sys)`).
- AST-based dangerous-builtin Name reference rejection (catches first-class
  aliasing of `eval`/`open`/`vars`/etc.).
- Runtime socket monkey-patch preamble (blocks egress through allowed libraries
  like `pandas.read_csv("https://...")`).

**Test coverage:** `tests/v6/test_code_executor_sovereignty.py` runs 35 tests
covering 30+ adversarial bypass classes.

**Honest scope:** complete Python sovereignty requires OS-level isolation —
network namespace + seccomp-bpf + read-only FS. Tracked in **follow-up Issue
I-f10-007b: OS-level egress isolation for code_executor**, deployed at the OVH
Canada BHS H200 sovereign environment.

**Run:**

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/v6/test_code_executor_sovereignty.py -v
# 35 passed
```

---

## What's NOT yet wired (honest gap)

- **Live LLM → tirzepatide-vs-semaglutide auto-table from real evidence retrieval.**
  Substrate exists (chart builders + provenance contract + click-through + sandbox)
  but the production wiring from BPEI question → retrieval → spec generation → UI
  render is not yet end-to-end. Tracked in v6 Phase 1..3 milestones.
- **Real evidence_id resolution from sovereign Canadian retrieval pipeline.** Demo
  uses a frontend-only `SOURCE_REGISTRY`; production fetches from a backend route.
- **I-f10-007b OS-level isolation for code_executor.** Python in-process sandboxing
  has fundamental escape vectors; complete sovereignty deferred to OS-level
  controls at the OVH BHS H200 deployment.

---

## Cross-references

- **I-f10-001:** Vega-Lite renderer + error fallback — `web/components/ui/vega-chart.tsx`,
  PR #291 (commit `bad6d9e`); `outputs/audits/I-f10-001/claude_audit.md`.
- **I-f10-002:** Forest plot spec — `web/lib/forest_plot_spec.ts`,
  `tests/v6/test_charts.py` (meta-analysis test); PR #292 (commit `a3f1f50`);
  `outputs/audits/I-f10-002/claude_audit.md`.
- **I-f10-003:** Comparison table N=2/3/5 — `web/lib/comparison_table_spec.ts`,
  `tests/v6/test_charts.py` (`test_comparison_table_n2/n5_renders_correctly`); PR #293
  (commit `6fb1b37`); `outputs/audits/I-f10-003/claude_audit.md`.
- **I-f10-004:** Timeline spec (quarter + date) — `web/lib/timeline_spec.ts`; PR #294
  (commit `bbe8dbc`); `outputs/audits/I-f10-004/claude_audit.md`.
- **I-f10-005:** ChartProvenance schema — `src/polaris_v6/charts/provenance.py`,
  `tests/v6/test_chart_provenance.py`; PR #295 (commit `599bbe0`);
  `outputs/audits/I-f10-005/claude_audit.md`.
- **I-f10-006:** Click-through-to-source-data —
  `web/app/charts_test/components/chart_source_inspector.tsx`,
  `web/tests/e2e/chart_click_through.spec.ts`; PR #296 (commit `54fc31a`);
  `outputs/audits/I-f10-006/claude_audit.md`.
- **I-f10-007:** Sandboxed Python execution — `src/polaris_graph/tools/code_executor.py`,
  `tests/v6/test_code_executor_sovereignty.py`; PR #297 (commit `617605e`);
  `outputs/audits/I-f10-007/claude_audit.md`.
- **I-f10-007b (deferred):** OS-level egress isolation for code_executor.
