# Claude architect audit — I-f10-006

**Issue:** Click-through-to-source-data
**Branch:** bot/I-f10-006
**Canonical-diff-sha256:** 7de19ccf4588295f98bd32b7f3d8b21f49d1a40595eabc05f04f9e754cae51e2
**Brief verdict:** APPROVE iter 2 (Codex iter-1 P1 — full source span — applied)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- New `<ChartSourceInspector>` Sheet pane renders evidence_id + tier badge + URL link + excerpt blockquote (per Codex iter-1 P1 — full source span, not just evidence_id text).
- Demo route uses `SOURCE_REGISTRY` keyed by demo evidence_id; honestly framed as "in production, this would fetch from `/runs/{run_id}/sources/{evidence_id}` per I-f10-005 polaris_provenance contract."
- Reuses existing `VegaChart.onPointClick` callback wired in I-f10-001 — no production component changes.
- LAW II honest fallback: `source === null` renders explicit `chart-source-pane-empty` testid with "No datum selected." text.
- Playwright role-aware locator with fallback handles Vega version drift (matches I-f10-002 pattern).

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 235 net (35 LOC over 200). Exemption: SOURCE_REGISTRY data + acceptance test substrate. Codex iter-1 P1 expanded the inspector pane to render full URL/tier/excerpt (not just evidence_id), which added LOC.

## Verdict
APPROVE.
