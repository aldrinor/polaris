"""I-f10-005: Pydantic schema for the `polaris_provenance` extension.

Every Vega-Lite chart spec produced by `spec_builder.build_*` carries a
`polaris_provenance` dict. This module defines the typed schema + a
validator that future consumers (I-f10-006 click-through, I-f10-007
sandboxed exec) depend on. The schema is consumer-side: builders
continue to emit dicts; validators parse them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ChartType = Literal["forest_plot", "comparison_table", "timeline"]
TimelinePeriodKind = Literal["date", "quarter", "year"]


class ChartProvenance(BaseModel):
    """Typed contract for the `polaris_provenance` extension on chart specs."""

    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType
    evidence_ids: list[str] = Field(min_length=1)
    period_kind: TimelinePeriodKind | None = None

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_ids_non_blank(cls, v: list[str]) -> list[str]:
        for i, eid in enumerate(v):
            if not eid or not eid.strip():
                raise ValueError(
                    f"evidence_ids[{i}] is blank; every chart datum must cite a real evidence_id"
                )
        return v

    @model_validator(mode="after")
    def _period_kind_consistency(self) -> "ChartProvenance":
        if self.chart_type == "timeline" and self.period_kind is None:
            raise ValueError("timeline chart_type requires period_kind")
        if self.chart_type != "timeline" and self.period_kind is not None:
            raise ValueError(
                f"period_kind is only valid for timeline charts (got chart_type={self.chart_type})"
            )
        return self


def validate_chart_provenance(spec: dict[str, Any]) -> ChartProvenance:
    """Extract and validate `polaris_provenance` from a Vega-Lite spec dict."""
    if "polaris_provenance" not in spec:
        raise ValueError("chart spec missing polaris_provenance")
    raw = spec["polaris_provenance"]
    if not isinstance(raw, dict):
        raise ValueError(
            f"polaris_provenance must be a dict, got {type(raw).__name__}"
        )
    return ChartProvenance(**raw)
