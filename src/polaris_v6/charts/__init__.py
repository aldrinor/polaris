"""Vega-Lite chart spec generators (Phase 2B Task 2B.2 substrate).

Per docs/carney_delivery_plan_v6_2.md F10a, the v6 plan ships THREE
chart types with provenance-enabled data points:

1. forest_plot — effect-size + CI per source/study (clinical, trade)
2. comparison_table — values per entity per source (housing, defense)
3. timeline — values per period per source (climate, productivity)

Each chart spec includes a `polaris_provenance` extension that maps
each datum to the originating evidence_id so the F10b click-through-
to-source is wired by construction.
"""
