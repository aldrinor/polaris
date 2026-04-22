"""M-43 tests: regulatory anchor cap raised from 10 to 12.

V26 caught-by-preservation-guard regression: adding M-42d's hpfb-dgpsa.ca
anchor pushed clinical.yaml's regulatory_anchors list to 11 entries,
but `PG_SWEEP_MAX_REGULATORY_ANCHORS` default=10 truncated the last
entry (nice.org.uk). V26 produced NICE=0 in biblio vs V25's 4.

M-43 raises `_DEFAULT_MAX_ANCHORS` from 10 to 12, restoring NICE
coverage and giving 1 future-anchor headroom. Tests below verify:
1. The default cap is now 12 (not 10).
2. The current clinical.yaml template emits all 11 anchors (including
   nice.org.uk as the final entry).
3. Env override still works for further expansion/contraction.
"""
from __future__ import annotations

import pytest


class TestDefaultCap:
    def test_default_cap_raised_to_12(self, monkeypatch) -> None:
        monkeypatch.delenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", raising=False)
        from src.polaris_graph.retrieval.regulatory_expander import (
            _max_anchors,
        )
        assert _max_anchors() == 12, (
            "M-43 default must be 12 so the 11-anchor clinical template "
            "fits with 1 future-anchor headroom"
        )


class TestClinicalTemplateEmissionCoverage:
    def test_clinical_yaml_emits_all_anchors_including_nice(
        self, monkeypatch,
    ) -> None:
        """Ensure the cap accommodates every anchor in clinical.yaml.

        V26 regression: nice.org.uk was at position 11 and dropped.
        This test proves M-43 restored coverage.
        """
        monkeypatch.delenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", raising=False)
        import yaml
        from pathlib import Path
        from src.polaris_graph.retrieval.regulatory_expander import (
            expand_regulatory_queries,
        )
        p = Path(__file__).parent.parent.parent / "config" / "scope_templates" / "clinical.yaml"
        template = yaml.safe_load(p.read_text(encoding="utf-8"))
        queries = expand_regulatory_queries(
            "tirzepatide efficacy safety t2dm",
            template,
        )
        # Every anchor in clinical.yaml must produce a query.
        declared_anchors = [
            a.strip().lower()
            for a in template.get("regulatory_anchors", [])
            if isinstance(a, str) and a.strip()
        ]
        assert len(queries) == len(declared_anchors), (
            f"Anchor truncation: {len(queries)} emitted vs "
            f"{len(declared_anchors)} declared in clinical.yaml. "
            f"Check PG_SWEEP_MAX_REGULATORY_ANCHORS cap."
        )
        # Regression guard: nice.org.uk specifically must fire a query.
        nice_queries = [q for q in queries if "site:nice.org.uk" in q]
        assert nice_queries, (
            "NICE anchor not emitted. V26 regression signature."
        )
        # M-42d additions still fire.
        hpfb_queries = [q for q in queries if "site:hpfb-dgpsa.ca" in q]
        assert hpfb_queries, "hpfb-dgpsa.ca (M-42d) anchor dropped"


class TestEnvOverrideStillWorks:
    def test_env_override_shrinks_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "5")
        from src.polaris_graph.retrieval.regulatory_expander import (
            _max_anchors,
        )
        assert _max_anchors() == 5

    def test_env_override_expands_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "20")
        from src.polaris_graph.retrieval.regulatory_expander import (
            _max_anchors,
        )
        assert _max_anchors() == 20

    def test_env_zero_disables_cap(self, monkeypatch) -> None:
        monkeypatch.setenv("PG_SWEEP_MAX_REGULATORY_ANCHORS", "0")
        from src.polaris_graph.retrieval.regulatory_expander import (
            _max_anchors,
        )
        # Cap = 0 is the documented "no cap" sentinel. In the expander
        # logic, `if cap > 0 and len(anchors) > cap` would be False,
        # so all anchors emit. That is the intended behavior.
        assert _max_anchors() == 0
