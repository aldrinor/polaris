"""
Pipeline definition models for custom research pipelines.

Two-tier hierarchy (Amendment A4):
  PipelineDefinition → MacroStage → PipelineStage

A flat SVG DAG with 175 nodes is unreadable. MacroStages are collapsible
groups that become LangGraph sub-graphs. The editor shows ~5 macro boxes
that expand to reveal internal stages on click.

Stage types map to existing polaris_graph node functions:
  plan, search, storm_interviews, analyze, verify, evaluate, synthesize,
  search_gaps, custom_llm, filter, merge
"""

import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Stage type registry — maps stage_type strings to node function paths
# ---------------------------------------------------------------------------

class StageType(str, Enum):
    """Supported pipeline stage types."""
    PLAN = "plan"
    SEARCH = "search"
    STORM_INTERVIEWS = "storm_interviews"
    ANALYZE = "analyze"
    VERIFY = "verify"
    EVALUATE = "evaluate"
    SYNTHESIZE = "synthesize"
    SEARCH_GAPS = "search_gaps"
    CUSTOM_LLM = "custom_llm"
    FILTER = "filter"
    MERGE = "merge"


# Maps stage types to their module paths for dynamic import
STAGE_TYPE_REGISTRY: dict[str, str] = {
    "plan": "src.polaris_graph.agents.planner",
    "search": "src.polaris_graph.agents.searcher",
    "storm_interviews": "src.polaris_graph.agents.storm_interviews",
    "analyze": "src.polaris_graph.agents.analyzer",
    "verify": "src.polaris_graph.agents.verifier",
    "evaluate": "src.polaris_graph.graph",
    "synthesize": "src.polaris_graph.agents.synthesizer",
    "search_gaps": "src.polaris_graph.agents.synthesizer",
    "custom_llm": "src.polaris_graph.graph",
    "filter": "src.polaris_graph.graph",
    "merge": "src.polaris_graph.graph",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PipelineStage(BaseModel):
    """A single stage (node) within a macro-stage."""

    stage_id: str = Field(
        ...,
        description="Unique ID within the pipeline (e.g., 'web_search', 'nli_verify')",
    )
    stage_type: StageType = Field(
        ...,
        description="Node type — maps to a registered handler function",
    )
    label: str = Field(
        default="",
        description="Human-readable label for the UI",
    )
    description: str = Field(
        default="",
        description="What this stage does",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Stage-specific configuration (thresholds, prompts, concurrency)",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Stage IDs this stage depends on (within the same macro-stage)",
    )
    timeout_seconds: int = Field(
        default=300,
        description="Max execution time for this stage",
    )
    retries: int = Field(
        default=1,
        description="Number of retry attempts on failure",
    )

    @field_validator("stage_id")
    @classmethod
    def validate_stage_id(cls, v: str) -> str:
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"stage_id must be alphanumeric with underscores: {v}")
        return v

    @field_validator("label", mode="before")
    @classmethod
    def default_label(cls, v: str, info) -> str:
        if not v and "stage_id" in info.data:
            return info.data["stage_id"].replace("_", " ").title()
        return v


class MacroStage(BaseModel):
    """A collapsible group of stages — becomes a LangGraph sub-graph."""

    macro_id: str = Field(
        ...,
        description="Unique ID for the macro-stage (e.g., 'collection', 'verification')",
    )
    label: str = Field(
        ...,
        description="Human-readable label (e.g., 'Evidence Collection')",
    )
    description: str = Field(
        default="",
        description="What this macro-stage accomplishes",
    )
    stages: list[PipelineStage] = Field(
        ...,
        min_length=1,
        description="Internal stages within this macro-stage",
    )
    depends_on_macros: list[str] = Field(
        default_factory=list,
        description="Macro-stage IDs this macro depends on",
    )
    color: str = Field(
        default="#4A90D9",
        description="Visual color in the pipeline editor",
    )
    estimated_minutes: float = Field(
        default=5.0,
        description="Estimated execution duration for the UI",
    )

    @field_validator("macro_id")
    @classmethod
    def validate_macro_id(cls, v: str) -> str:
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"macro_id must be alphanumeric with underscores: {v}")
        return v

    @property
    def stage_count(self) -> int:
        """Number of internal stages."""
        return len(self.stages)

    def get_stage(self, stage_id: str) -> Optional[PipelineStage]:
        """Find a stage by ID within this macro-stage."""
        for s in self.stages:
            if s.stage_id == stage_id:
                return s
        return None

    def get_entry_stages(self) -> list[PipelineStage]:
        """Stages with no internal dependencies — entry points of the sub-graph."""
        all_ids = {s.stage_id for s in self.stages}
        return [
            s for s in self.stages
            if not any(dep in all_ids for dep in s.depends_on)
        ]

    def get_exit_stages(self) -> list[PipelineStage]:
        """Stages that nothing depends on — exit points of the sub-graph."""
        depended_on = set()
        for s in self.stages:
            depended_on.update(s.depends_on)
        return [s for s in self.stages if s.stage_id not in depended_on]


class PipelineDefinition(BaseModel):
    """Full pipeline = ordered list of MacroStages.

    Top-level model that defines a complete research pipeline.
    Can be serialized to/from YAML for storage and sharing.
    """

    pipeline_id: str = Field(
        default_factory=lambda: f"pipe_{uuid.uuid4().hex[:12]}",
        description="Unique pipeline identifier",
    )
    name: str = Field(
        ...,
        description="Human-readable pipeline name",
    )
    description: str = Field(
        default="",
        description="What this pipeline is designed for",
    )
    version: str = Field(
        default="1.0.0",
        description="Semantic version of the pipeline definition",
    )
    author: str = Field(
        default="system",
        description="Who created this pipeline",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation timestamp",
    )
    macro_stages: list[MacroStage] = Field(
        ...,
        min_length=1,
        description="Ordered list of macro-stages",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization and search",
    )
    is_template: bool = Field(
        default=False,
        description="Whether this is a built-in template (read-only)",
    )

    # Quality gate overrides (optional per-pipeline config)
    config_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-pipeline environment variable overrides (e.g., PG_MAX_ITERATIONS=5)",
    )

    @model_validator(mode="after")
    def validate_dependencies(self) -> "PipelineDefinition":
        """Ensure all macro-stage dependencies reference existing macro IDs."""
        macro_ids = {m.macro_id for m in self.macro_stages}
        for macro in self.macro_stages:
            for dep in macro.depends_on_macros:
                if dep not in macro_ids:
                    raise ValueError(
                        f"MacroStage '{macro.macro_id}' depends on unknown "
                        f"macro '{dep}'. Available: {macro_ids}"
                    )
            # Validate internal stage dependencies
            stage_ids = {s.stage_id for s in macro.stages}
            for stage in macro.stages:
                for dep in stage.depends_on:
                    if dep not in stage_ids:
                        raise ValueError(
                            f"Stage '{stage.stage_id}' in macro '{macro.macro_id}' "
                            f"depends on unknown stage '{dep}'. "
                            f"Available in macro: {stage_ids}"
                        )
        return self

    @model_validator(mode="after")
    def validate_no_cycles(self) -> "PipelineDefinition":
        """Ensure no circular dependencies between macro-stages."""
        visited: set[str] = set()
        path: set[str] = set()
        macro_map = {m.macro_id: m for m in self.macro_stages}

        def _dfs(mid: str) -> None:
            if mid in path:
                raise ValueError(f"Circular dependency detected: {mid}")
            if mid in visited:
                return
            path.add(mid)
            for dep in macro_map[mid].depends_on_macros:
                _dfs(dep)
            path.discard(mid)
            visited.add(mid)

        for m in self.macro_stages:
            _dfs(m.macro_id)
        return self

    def flatten(self) -> list[PipelineStage]:
        """Return all stages across all macro-stages as a flat list."""
        result = []
        for macro in self.macro_stages:
            result.extend(macro.stages)
        return result

    @property
    def total_nodes(self) -> int:
        """Total number of stages across all macro-stages."""
        return sum(m.stage_count for m in self.macro_stages)

    @property
    def total_estimated_minutes(self) -> float:
        """Total estimated execution time."""
        return sum(m.estimated_minutes for m in self.macro_stages)

    def get_macro(self, macro_id: str) -> Optional[MacroStage]:
        """Find a macro-stage by ID."""
        for m in self.macro_stages:
            if m.macro_id == macro_id:
                return m
        return None

    def get_execution_order(self) -> list[str]:
        """Topological sort of macro-stage IDs based on dependencies."""
        macro_map = {m.macro_id: m for m in self.macro_stages}
        in_degree: dict[str, int] = {mid: 0 for mid in macro_map}
        for m in self.macro_stages:
            for dep in m.depends_on_macros:
                in_degree[m.macro_id] += 1

        queue = [mid for mid, deg in in_degree.items() if deg == 0]
        result: list[str] = []
        while queue:
            mid = queue.pop(0)
            result.append(mid)
            for m in self.macro_stages:
                if mid in m.depends_on_macros:
                    in_degree[m.macro_id] -= 1
                    if in_degree[m.macro_id] == 0:
                        queue.append(m.macro_id)
        return result

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        data = self.model_dump(exclude_none=True)
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "PipelineDefinition":
        """Deserialize from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls(**data)

    @classmethod
    def from_yaml_file(cls, path: Path) -> "PipelineDefinition":
        """Load from a YAML file."""
        content = path.read_text(encoding="utf-8")
        return cls.from_yaml(content)


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(os.getenv(
    "PG_PIPELINE_TEMPLATES_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "config" / "pipeline_templates"),
))


def list_templates() -> list[dict[str, Any]]:
    """List available pipeline templates (metadata only)."""
    templates = []
    if not TEMPLATES_DIR.exists():
        return templates
    for f in sorted(TEMPLATES_DIR.glob("*.yaml")):
        try:
            pipeline = PipelineDefinition.from_yaml_file(f)
            templates.append({
                "pipeline_id": pipeline.pipeline_id,
                "name": pipeline.name,
                "description": pipeline.description,
                "total_nodes": pipeline.total_nodes,
                "macro_count": len(pipeline.macro_stages),
                "estimated_minutes": pipeline.total_estimated_minutes,
                "tags": pipeline.tags,
                "file": f.name,
            })
        except Exception:
            continue
    return templates


def load_template(template_name: str) -> Optional[PipelineDefinition]:
    """Load a specific template by file stem name."""
    path = TEMPLATES_DIR / f"{template_name}.yaml"
    if not path.exists():
        return None
    return PipelineDefinition.from_yaml_file(path)
