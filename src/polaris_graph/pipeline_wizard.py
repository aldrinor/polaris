"""
Pipeline wizard — conversational engine that interviews users about their
research problem and generates a complete PipelineDefinition.

Amendment A3: Multi-turn chat wizard replacing the "Polish with AI" button.
6 interview stages: Problem → Sources → Analysis → Verification → Output → Constraints.
After 4-8 exchanges, generates a validated pipeline YAML.

Sessions are stored in-memory (dict). For production persistence,
swap with SQLite (same pattern as campaign_store.py).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.polaris_graph.pipeline_definition import (
    MacroStage,
    PipelineDefinition,
    PipelineStage,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wizard stages
# ---------------------------------------------------------------------------

WIZARD_STAGES = [
    "problem",        # What is the research question?
    "sources",        # What types of sources?
    "analysis",       # How should evidence be evaluated?
    "verification",   # How rigorous must fact-checking be?
    "output",         # Report length? Sections? Exports?
    "constraints",    # Budget? Time? Geographic scope?
]

STAGE_LABELS = {
    "problem": "Problem Understanding",
    "sources": "Data Sources",
    "analysis": "Analysis Strategy",
    "verification": "Verification Needs",
    "output": "Output Format",
    "constraints": "Constraints",
}

STAGE_PROMPTS = {
    "problem": (
        "I'll help you build a custom research pipeline. Let's start with your research problem.\n\n"
        "**What is the main research question or topic you want to investigate?**\n\n"
        "Please describe:\n"
        "- The specific question or problem\n"
        "- The domain (technology, legal, medical, finance, etc.)\n"
        "- How deep you need the analysis to go"
    ),
    "sources": (
        "Great. Now let's define your data sources.\n\n"
        "**What types of sources should the pipeline search?**\n\n"
        "Options include:\n"
        "- **Web**: General web search (news, blogs, company sites)\n"
        "- **Academic**: Peer-reviewed papers (Semantic Scholar, OpenAlex)\n"
        "- **Documents**: Your uploaded PDFs, contracts, reports\n"
        "- **All**: Comprehensive search across all source types\n\n"
        "Do you have a preference for source types or specific databases?"
    ),
    "analysis": (
        "Now for the analysis approach.\n\n"
        "**How should the pipeline evaluate evidence?**\n\n"
        "Consider:\n"
        "- Should it prioritize peer-reviewed sources over web content?\n"
        "- Do you need multi-perspective STORM interviews (expert viewpoints)?\n"
        "- How many sub-questions should it decompose your query into? (15-80)\n"
        "- Should it chase citations from key papers?"
    ),
    "verification": (
        "Let's configure verification rigor.\n\n"
        "**How strict should fact-checking be?**\n\n"
        "Options:\n"
        "- **Standard** (80%+ faithfulness target): Good for general research\n"
        "- **Strict** (85%+): Required for compliance, legal, medical\n"
        "- **Maximum** (90%+): Multi-pass NLI + cross-reference + contradiction detection\n\n"
        "Should the pipeline detect source conflicts and highlight contradictions?"
    ),
    "output": (
        "Almost done. Let's configure the output.\n\n"
        "**What should the final report look like?**\n\n"
        "Consider:\n"
        "- **Length**: Short (2-4K words), Standard (8-12K), Long (15-20K)\n"
        "- **Style**: General, Academic, Compliance/Regulatory\n"
        "- **Visuals**: Include Mermaid diagrams? Process flows? Comparison tables?\n"
        "- **Export**: PDF, Word (DOCX), Markdown?"
    ),
    "constraints": (
        "Final step — any constraints?\n\n"
        "**Are there time or resource limits?**\n\n"
        "Consider:\n"
        "- **Time budget**: Quick (15 min), Standard (60 min), Deep (180 min)\n"
        "- **Iterations**: How many improvement passes? (1-5)\n"
        "- **Geographic focus**: Any regional scope?\n"
        "- **Language**: English only, or multilingual?\n\n"
        "If nothing specific, I'll use sensible defaults."
    ),
}

# Quick-reply chips for each stage
STAGE_CHIPS = {
    "problem": ["Technology analysis", "Literature review", "Competitive analysis", "Policy research"],
    "sources": ["Web + Academic", "Academic only", "Web only", "Include my documents"],
    "analysis": ["Comprehensive (50+ queries)", "Focused (20 queries)", "Expert interviews enabled"],
    "verification": ["Standard (80%)", "Strict (85%)", "Maximum (90%+)"],
    "output": ["Standard (8-12K words)", "Short (2-4K words)", "Long (15-20K words)"],
    "constraints": ["60 minutes", "15 minutes (quick)", "3 hours (deep)", "No constraints"],
}


# ---------------------------------------------------------------------------
# Wizard session
# ---------------------------------------------------------------------------

class WizardSession:
    """In-memory state for a single wizard conversation."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.stage_index = 0
        self.history: list[dict[str, str]] = []  # [{"role": "wizard"|"user", "text": ...}]
        self.collected: dict[str, str] = {}  # stage -> user response summary
        self.pipeline_draft: Optional[PipelineDefinition] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.finalized = False

    @property
    def current_stage(self) -> str:
        if self.stage_index >= len(WIZARD_STAGES):
            return "complete"
        return WIZARD_STAGES[self.stage_index]

    @property
    def completion_pct(self) -> float:
        return min(100.0, (self.stage_index / len(WIZARD_STAGES)) * 100)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "stage": self.current_stage,
            "stage_label": STAGE_LABELS.get(self.current_stage, "Complete"),
            "stage_index": self.stage_index,
            "total_stages": len(WIZARD_STAGES),
            "completion_pct": self.completion_pct,
            "history": self.history,
            "collected": self.collected,
            "has_draft": self.pipeline_draft is not None,
            "finalized": self.finalized,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Pipeline Wizard
# ---------------------------------------------------------------------------

# In-memory session store
_sessions: dict[str, WizardSession] = {}


class PipelineWizard:
    """Conversational wizard that interviews users to build pipeline definitions."""

    def start_session(self) -> dict:
        """Create a new wizard session, return greeting."""
        session_id = f"wiz_{uuid.uuid4().hex[:12]}"
        session = WizardSession(session_id)

        # Add greeting
        greeting = (
            "Welcome to the POLARIS Pipeline Wizard.\n\n"
            "I'll ask you a few questions about your research needs, "
            "then generate a custom pipeline definition tailored to your requirements.\n\n"
            + STAGE_PROMPTS["problem"]
        )
        session.history.append({"role": "wizard", "text": greeting})
        _sessions[session_id] = session

        return {
            "session_id": session_id,
            "response": greeting,
            "stage": session.current_stage,
            "stage_label": STAGE_LABELS[session.current_stage],
            "completion_pct": session.completion_pct,
            "chips": STAGE_CHIPS.get(session.current_stage, []),
            "pipeline_draft": None,
        }

    def chat(self, session_id: str, user_message: str) -> dict:
        """Process a user message and advance the wizard.

        Returns response dict with wizard reply, stage info, and optional pipeline draft.
        """
        session = _sessions.get(session_id)
        if not session:
            return {"error": f"Session '{session_id}' not found"}
        if session.finalized:
            return {"error": "Session already finalized"}

        # Record user message
        session.history.append({"role": "user", "text": user_message})
        session.collected[session.current_stage] = user_message

        # Advance to next stage
        session.stage_index += 1

        if session.current_stage == "complete":
            # All stages collected — generate pipeline
            pipeline = self._generate_pipeline(session)
            session.pipeline_draft = pipeline

            response = (
                "I've analyzed your requirements and generated a custom pipeline.\n\n"
                f"**Pipeline: {pipeline.name}**\n"
                f"- {pipeline.total_nodes} stages across {len(pipeline.macro_stages)} macro-stages\n"
                f"- Estimated time: {pipeline.total_estimated_minutes:.0f} minutes\n"
                f"- Tags: {', '.join(pipeline.tags)}\n\n"
                "Click **Use This Pipeline** to save and start using it, "
                "or **Edit Manually** to fine-tune in the visual editor."
            )
            session.history.append({"role": "wizard", "text": response})

            return {
                "session_id": session_id,
                "response": response,
                "stage": "complete",
                "stage_label": "Complete",
                "completion_pct": 100.0,
                "chips": [],
                "pipeline_draft": pipeline.model_dump(),
            }
        else:
            # Send next stage prompt
            prompt = STAGE_PROMPTS[session.current_stage]
            session.history.append({"role": "wizard", "text": prompt})

            return {
                "session_id": session_id,
                "response": prompt,
                "stage": session.current_stage,
                "stage_label": STAGE_LABELS[session.current_stage],
                "completion_pct": session.completion_pct,
                "chips": STAGE_CHIPS.get(session.current_stage, []),
                "pipeline_draft": None,
            }

    def get_draft(self, session_id: str) -> Optional[dict]:
        """Get the current pipeline draft for a session."""
        session = _sessions.get(session_id)
        if not session or not session.pipeline_draft:
            return None
        return session.pipeline_draft.model_dump()

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get full session state."""
        session = _sessions.get(session_id)
        if not session:
            return None
        return session.to_dict()

    def finalize(self, session_id: str) -> Optional[dict]:
        """Finalize the pipeline draft — mark session as complete."""
        session = _sessions.get(session_id)
        if not session or not session.pipeline_draft:
            return None
        session.finalized = True
        return session.pipeline_draft.model_dump()

    def _generate_pipeline(self, session: WizardSession) -> PipelineDefinition:
        """Generate a PipelineDefinition from collected wizard responses.

        Uses heuristic rules to map user preferences to pipeline configuration.
        In future, this could use an LLM call for more nuanced interpretation.
        """
        responses = session.collected
        problem = responses.get("problem", "").lower()
        sources = responses.get("sources", "").lower()
        analysis = responses.get("analysis", "").lower()
        verification = responses.get("verification", "").lower()
        output = responses.get("output", "").lower()
        constraints = responses.get("constraints", "").lower()

        # Determine pipeline characteristics from responses
        is_academic = any(kw in sources for kw in ["academic", "peer", "literature", "papers"])
        is_quick = any(kw in constraints for kw in ["15 min", "quick", "fast", "short"])
        is_deep = any(kw in constraints for kw in ["3 hour", "deep", "exhaustive", "180"])
        is_strict = any(kw in verification for kw in ["strict", "85", "maximum", "90"])
        is_compliance = any(kw in problem for kw in ["compliance", "regulatory", "legal", "contract"])
        wants_storm = "interview" in analysis or "expert" in analysis or "perspective" in analysis
        wants_docs = "document" in sources or "upload" in sources or "pdf" in sources
        wants_long = any(kw in output for kw in ["long", "15", "20"])
        wants_short = any(kw in output for kw in ["short", "2-4", "brief"])

        # Base config overrides
        config: dict[str, str] = {}

        # Query count
        if is_quick:
            query_count = 15
            config["PG_QUERIES_PER_VECTOR"] = "15"
            config["PG_MAX_ITERATIONS"] = "1"
            config["PG_MAX_EXECUTION_MINUTES"] = "15"
        elif is_deep:
            query_count = 80
            config["PG_QUERIES_PER_VECTOR"] = "80"
            config["PG_MAX_ITERATIONS"] = "5"
            config["PG_MAX_EXECUTION_MINUTES"] = "180"
        else:
            query_count = 50
            config["PG_MAX_ITERATIONS"] = "3"
            config["PG_MAX_EXECUTION_MINUTES"] = "60"

        # Word count
        if wants_long:
            config["PG_TARGET_TOTAL_WORDS"] = "20000"
            config["PG_MIN_TOTAL_WORDS"] = "15000"
        elif wants_short:
            config["PG_TARGET_TOTAL_WORDS"] = "4000"
            config["PG_MIN_TOTAL_WORDS"] = "2000"

        # Faithfulness threshold
        if is_strict:
            config["PG_MIN_FAITHFULNESS"] = "0.85"
        elif is_compliance:
            config["PG_MIN_FAITHFULNESS"] = "0.85"

        # STORM
        if not is_quick and (wants_storm or not is_quick):
            config["PG_STORM_ENABLED"] = "1"
        else:
            config["PG_STORM_ENABLED"] = "0"

        # Build macro-stages
        macro_stages: list[MacroStage] = []

        # 1. Planning
        macro_stages.append(MacroStage(
            macro_id="planning",
            label="Planning" if not is_compliance else "Compliance Planning",
            description="Generate research sub-queries",
            color="#6C5CE7",
            estimated_minutes=2.0 if not is_deep else 3.0,
            stages=[PipelineStage(
                stage_id="plan_queries",
                stage_type="plan",
                label="Query Planning",
                config={"queries_per_vector": query_count},
            )],
        ))

        # 2. Collection
        collection_stages: list[PipelineStage] = [
            PipelineStage(
                stage_id="search",
                stage_type="search",
                label="Search",
                config={"academic_priority": is_academic},
            ),
        ]
        if config.get("PG_STORM_ENABLED") == "1":
            collection_stages.append(PipelineStage(
                stage_id="storm",
                stage_type="storm_interviews",
                label="STORM Interviews",
                depends_on=["search"],
            ))
        macro_stages.append(MacroStage(
            macro_id="collection",
            label="Evidence Collection",
            description="Search web, academic, and uploaded sources",
            color="#00B894",
            estimated_minutes=10.0 if not is_deep else 20.0,
            depends_on_macros=["planning"],
            stages=collection_stages,
        ))

        # 3. Analysis
        macro_stages.append(MacroStage(
            macro_id="analysis",
            label="Analysis",
            description="Extract and score evidence",
            color="#FDCB6E",
            estimated_minutes=15.0 if not is_deep else 25.0,
            depends_on_macros=["collection"],
            stages=[PipelineStage(
                stage_id="analyze",
                stage_type="analyze",
                label="Evidence Extraction",
            )],
        ))

        # 4. Verification (skip for quick scan)
        if not is_quick:
            verify_stages: list[PipelineStage] = [
                PipelineStage(
                    stage_id="verify",
                    stage_type="verify",
                    label="NLI Verification",
                ),
                PipelineStage(
                    stage_id="evaluate",
                    stage_type="evaluate",
                    label="Quality Evaluation",
                    depends_on=["verify"],
                ),
            ]
            macro_stages.append(MacroStage(
                macro_id="verification",
                label="Verification",
                description="NLI verification and quality evaluation",
                color="#E17055",
                estimated_minutes=10.0 if not is_deep else 20.0,
                depends_on_macros=["analysis"],
                stages=verify_stages,
            ))

        # 5. Synthesis
        synth_depends = ["verification"] if not is_quick else ["analysis"]
        synth_stages: list[PipelineStage] = [
            PipelineStage(
                stage_id="synthesize",
                stage_type="synthesize",
                label="Report Generation",
            ),
        ]
        if not is_quick:
            synth_stages.append(PipelineStage(
                stage_id="gap_search",
                stage_type="search_gaps",
                label="Gap Search",
                depends_on=["synthesize"],
            ))
        macro_stages.append(MacroStage(
            macro_id="synthesis",
            label="Synthesis",
            description="Generate research report with citations",
            color="#0984E3",
            estimated_minutes=20.0 if not is_deep else 30.0,
            depends_on_macros=synth_depends,
            stages=synth_stages,
        ))

        # Generate tags
        tags: list[str] = ["custom"]
        if is_academic:
            tags.append("academic")
        if is_compliance:
            tags.append("compliance")
        if is_quick:
            tags.append("quick")
        if is_deep:
            tags.append("deep")
        if wants_docs:
            tags.append("documents")

        # Build name from first words of problem
        problem_text = responses.get("problem", "Custom Research")
        name_words = problem_text.split()[:5]
        name = " ".join(name_words)
        if len(name) > 50:
            name = name[:50] + "..."

        return PipelineDefinition(
            name=f"Custom: {name}",
            description=f"Custom pipeline generated by wizard. Problem: {problem_text[:200]}",
            macro_stages=macro_stages,
            tags=tags,
            config_overrides=config,
        )


# Module-level singleton
wizard = PipelineWizard()
