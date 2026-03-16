"""
POLARIS Dynamic Re-Planning - OpenAI o3 Parity

Implements adaptive research direction changes based on findings:
- Detects contradictions in evidence
- Identifies unexpected findings requiring deeper investigation
- Spots critical knowledge gaps
- Generates adaptive queries to address issues

This enables the pipeline to adjust its research strategy mid-execution
rather than following a rigid plan.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class ReplanTrigger(Enum):
    """Triggers that can cause re-planning."""
    CONTRADICTION = "contradiction"
    UNEXPECTED_FINDING = "unexpected_finding"
    CRITICAL_GAP = "critical_gap"
    EVIDENCE_SATURATION = "evidence_saturation"
    QUALITY_DECLINE = "quality_decline"
    NONE = "none"


@dataclass
class ReplanDecision:
    """Decision about whether to re-plan research direction."""
    should_replan: bool
    trigger: ReplanTrigger
    reason: str
    confidence: float
    suggested_focus: Optional[str] = None  # New focus area
    adaptive_queries: List[str] = field(default_factory=list)


@dataclass
class ContradictionInfo:
    """Information about a detected contradiction."""
    evidence_id_1: str
    evidence_id_2: str
    claim_1: str
    claim_2: str
    contradiction_score: float
    topic: str


@dataclass
class UnexpectedFinding:
    """An unexpected finding that warrants deeper investigation."""
    finding: str
    source_evidence_id: str
    novelty_score: float
    relevance_to_query: float
    suggested_queries: List[str] = field(default_factory=list)


class DynamicReplanner:
    """
    Detects situations requiring research re-planning and generates
    adaptive queries to address them.

    Monitors for:
    1. Contradictions between evidence pieces
    2. Unexpected findings that open new research directions
    3. Critical gaps that need immediate attention
    4. Evidence saturation in current direction

    When triggered, generates new queries focused on the issue.
    """

    def __init__(
        self,
        max_replans: int = 3,
        contradiction_threshold: float = 0.7,
        unexpected_finding_threshold: float = 0.8,
        critical_gap_threshold: int = 3,
        max_adaptive_queries: int = 10,
        novelty_weight: float = 0.4,
        relevance_weight: float = 0.6,
    ):
        """
        Initialize the replanner.

        Args:
            max_replans: Maximum re-plans allowed per vector
            contradiction_threshold: Score to flag as contradiction
            unexpected_finding_threshold: Score for unexpected findings
            critical_gap_threshold: Number of critical gaps to trigger
            max_adaptive_queries: Max queries to generate per replan
            novelty_weight: Weight for novelty in query scoring
            relevance_weight: Weight for relevance in query scoring
        """
        self.max_replans = max_replans
        self.contradiction_threshold = contradiction_threshold
        self.unexpected_finding_threshold = unexpected_finding_threshold
        self.critical_gap_threshold = critical_gap_threshold
        self.max_adaptive_queries = max_adaptive_queries
        self.novelty_weight = novelty_weight
        self.relevance_weight = relevance_weight

        # Track replan count
        self._replan_count = 0
        self._replan_history: List[ReplanDecision] = []

    @property
    def replan_count(self) -> int:
        """Number of replans performed."""
        return self._replan_count

    def should_replan(self, state: Dict[str, Any]) -> ReplanDecision:
        """
        Determine if research direction should be changed.

        Checks for various triggers in priority order:
        1. Contradictions (highest priority)
        2. Critical gaps
        3. Unexpected findings
        4. Evidence saturation

        Args:
            state: Current research state

        Returns:
            ReplanDecision with recommendation and adaptive queries
        """
        if self._replan_count >= self.max_replans:
            return ReplanDecision(
                should_replan=False,
                trigger=ReplanTrigger.NONE,
                reason=f"Maximum replans ({self.max_replans}) reached",
                confidence=1.0
            )

        # Check for contradictions
        contradiction = self._detect_contradictions(state)
        if contradiction:
            logger.info(
                f"[REPLAN] Contradiction detected: {contradiction.topic} "
                f"(score: {contradiction.contradiction_score:.2f})"
            )
            queries = self._generate_contradiction_queries(contradiction, state)
            return ReplanDecision(
                should_replan=True,
                trigger=ReplanTrigger.CONTRADICTION,
                reason=f"Evidence contradiction on: {contradiction.topic}",
                confidence=contradiction.contradiction_score,
                suggested_focus=contradiction.topic,
                adaptive_queries=queries
            )

        # Check for critical gaps
        critical_gaps = self._detect_critical_gaps(state)
        if critical_gaps:
            logger.info(
                f"[REPLAN] Critical gaps detected: {len(critical_gaps)} high-priority gaps"
            )
            queries = self._generate_gap_queries(critical_gaps, state)
            return ReplanDecision(
                should_replan=True,
                trigger=ReplanTrigger.CRITICAL_GAP,
                reason=f"{len(critical_gaps)} critical gaps requiring attention",
                confidence=0.8,
                suggested_focus=critical_gaps[0].get("description", "Critical research gap"),
                adaptive_queries=queries
            )

        # Check for unexpected findings
        unexpected = self._detect_unexpected_findings(state)
        if unexpected:
            logger.info(
                f"[REPLAN] Unexpected finding: {unexpected.finding[:60]}... "
                f"(novelty: {unexpected.novelty_score:.2f})"
            )
            queries = unexpected.suggested_queries[:self.max_adaptive_queries]
            return ReplanDecision(
                should_replan=True,
                trigger=ReplanTrigger.UNEXPECTED_FINDING,
                reason=f"Unexpected finding warrants investigation: {unexpected.finding[:100]}",
                confidence=unexpected.novelty_score,
                suggested_focus=unexpected.finding,
                adaptive_queries=queries
            )

        # No trigger found
        return ReplanDecision(
            should_replan=False,
            trigger=ReplanTrigger.NONE,
            reason="Research proceeding normally",
            confidence=1.0
        )

    def execute_replan(self, decision: ReplanDecision, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a replan by updating state with new direction.

        Args:
            decision: The replan decision
            state: Current research state

        Returns:
            Updated state with new queries and focus
        """
        self._replan_count += 1
        self._replan_history.append(decision)

        # Add adaptive queries to sub_queries
        from src.orchestration.state import SubQuery
        new_queries = []
        for i, query_text in enumerate(decision.adaptive_queries):
            query = SubQuery(
                query_id=f"adaptive_{self._replan_count}_{i}",
                query_text=query_text,
                expected_data_type="factual",
                priority=1,  # High priority for adaptive queries
                search_keywords=query_text.split()[:5],
                domain_hints=[],
                status="pending"
            )
            new_queries.append(query)

        existing_queries = state.get("sub_queries", [])
        state["sub_queries"] = new_queries + list(existing_queries)

        # Log the replan
        logger.info(
            f"[REPLAN] Executed replan #{self._replan_count}: "
            f"trigger={decision.trigger.value}, "
            f"new_queries={len(decision.adaptive_queries)}, "
            f"focus={decision.suggested_focus}"
        )

        return state

    def _detect_contradictions(self, state: Dict[str, Any]) -> Optional[ContradictionInfo]:
        """
        Detect contradictions between evidence pieces.

        Uses simple heuristics:
        - Look for negation patterns
        - Compare numerical claims
        - Check for opposing qualitative statements
        """
        evidence_chain = state.get("evidence_chain", [])

        if len(evidence_chain) < 2:
            return None

        # Group evidence by topic/entity
        topic_evidence: Dict[str, List[Any]] = {}
        for e in evidence_chain:
            # Extract entities/topics from evidence
            entities = getattr(e, "entities", [])
            for entity in entities[:3]:  # Check first 3 entities
                if entity not in topic_evidence:
                    topic_evidence[entity] = []
                topic_evidence[entity].append(e)

        # Check each topic for contradictions
        for topic, evidences in topic_evidence.items():
            if len(evidences) < 2:
                continue

            for i, e1 in enumerate(evidences[:-1]):
                for e2 in evidences[i+1:]:
                    text1 = getattr(e1, "text", str(e1)).lower()
                    text2 = getattr(e2, "text", str(e2)).lower()

                    # Simple contradiction detection
                    score = self._calculate_contradiction_score(text1, text2)

                    if score >= self.contradiction_threshold:
                        return ContradictionInfo(
                            evidence_id_1=getattr(e1, "evidence_id", "unknown"),
                            evidence_id_2=getattr(e2, "evidence_id", "unknown"),
                            claim_1=text1[:200],
                            claim_2=text2[:200],
                            contradiction_score=score,
                            topic=topic
                        )

        return None

    def _calculate_contradiction_score(self, text1: str, text2: str) -> float:
        """Calculate contradiction score between two texts."""
        # Negation indicators
        negation_words = ["not", "no", "never", "none", "neither", "without", "lack"]
        contrast_words = ["however", "but", "although", "contrary", "opposite", "instead"]

        # Check for negation pattern
        words1 = set(text1.split())
        words2 = set(text2.split())

        # If one has negation and other doesn't, on same topic = potential contradiction
        neg1 = any(w in words1 for w in negation_words)
        neg2 = any(w in words2 for w in negation_words)

        if neg1 != neg2:
            # Calculate topic overlap
            common_words = words1 & words2
            significant_common = len([w for w in common_words if len(w) > 4])

            if significant_common >= 3:
                return 0.7 + (min(significant_common, 10) / 100)

        # Check for numerical contradictions
        import re
        nums1 = re.findall(r'\d+\.?\d*%?', text1)
        nums2 = re.findall(r'\d+\.?\d*%?', text2)

        if nums1 and nums2:
            # If same topic but very different numbers
            try:
                val1 = float(nums1[0].rstrip('%'))
                val2 = float(nums2[0].rstrip('%'))
                if abs(val1 - val2) / max(val1, val2, 1) > 0.5:
                    return 0.6
            except ValueError:
                pass

        return 0.0

    def _detect_critical_gaps(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect critical knowledge gaps requiring immediate attention."""
        gaps = state.get("gaps", [])

        critical = []
        for gap in gaps:
            priority = getattr(gap, "priority", 3)
            gap_type = getattr(gap, "gap_type", "unknown")

            # High priority or certain types are critical
            if priority <= 2 or gap_type in ["missing_data", "contradictory"]:
                critical.append({
                    "gap_id": getattr(gap, "gap_id", "unknown"),
                    "description": getattr(gap, "description", str(gap)),
                    "gap_type": gap_type,
                    "priority": priority,
                    "suggested_queries": getattr(gap, "suggested_queries", [])
                })

        # Only trigger if exceeds threshold
        if len(critical) >= self.critical_gap_threshold:
            return critical

        return []

    def _detect_unexpected_findings(self, state: Dict[str, Any]) -> Optional[UnexpectedFinding]:
        """Detect unexpected findings that warrant deeper investigation."""
        evidence_chain = state.get("evidence_chain", [])
        original_query = state.get("original_query", "")

        if not evidence_chain or not original_query:
            return None

        query_words = set(original_query.lower().split())

        for evidence in evidence_chain[-20:]:  # Check recent evidence
            text = getattr(evidence, "text", str(evidence))
            text_lower = text.lower()

            # Calculate novelty (new terms not in query)
            evidence_words = set(text_lower.split())
            novel_words = evidence_words - query_words
            novel_significant = [w for w in novel_words if len(w) > 6]

            novelty_score = min(len(novel_significant) / 20, 1.0)

            # Calculate relevance (shared terms with query)
            shared = query_words & evidence_words
            relevance_score = len(shared) / max(len(query_words), 1)

            # Check for surprising indicators
            surprise_indicators = [
                "surprisingly", "unexpectedly", "contrary to",
                "novel", "breakthrough", "unprecedented",
                "significant finding", "new research shows",
                "recent study", "latest evidence"
            ]

            has_surprise = any(ind in text_lower for ind in surprise_indicators)

            # Combine scores
            combined_score = (
                novelty_score * self.novelty_weight +
                relevance_score * self.relevance_weight +
                (0.2 if has_surprise else 0.0)
            )

            if combined_score >= self.unexpected_finding_threshold:
                return UnexpectedFinding(
                    finding=text[:500],
                    source_evidence_id=getattr(evidence, "evidence_id", "unknown"),
                    novelty_score=novelty_score,
                    relevance_to_query=relevance_score,
                    suggested_queries=self._generate_finding_queries(text, original_query)
                )

        return None

    def _generate_contradiction_queries(
        self,
        contradiction: ContradictionInfo,
        state: Dict[str, Any]
    ) -> List[str]:
        """Generate queries to resolve a contradiction."""
        original_query = state.get("original_query", "")
        topic = contradiction.topic

        queries = [
            f"meta-analysis {topic} consensus research findings",
            f"systematic review {topic} evidence quality",
            f"conflicting evidence {topic} resolution",
            f"{topic} authoritative sources academic",
            f"{topic} recent research 2024 2025 findings",
        ]

        return queries[:self.max_adaptive_queries]

    def _generate_gap_queries(
        self,
        gaps: List[Dict[str, Any]],
        state: Dict[str, Any]
    ) -> List[str]:
        """Generate queries to fill critical gaps."""
        queries = []

        for gap in gaps[:3]:  # Focus on top 3 gaps
            description = gap.get("description", "")
            suggested = gap.get("suggested_queries", [])

            # Use suggested queries if available
            queries.extend(suggested[:2])

            # Generate additional targeted queries
            if description:
                queries.append(f"{description} research evidence")
                queries.append(f"{description} data statistics")

        return queries[:self.max_adaptive_queries]

    def _generate_finding_queries(
        self,
        finding_text: str,
        original_query: str
    ) -> List[str]:
        """Generate queries to investigate an unexpected finding."""
        # Extract key terms from finding
        import re
        words = re.findall(r'\b[a-zA-Z]{5,}\b', finding_text.lower())
        word_freq = {}
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1

        # Get most frequent meaningful words
        stop_words = {"which", "where", "their", "these", "those", "would", "could", "should", "about"}
        key_terms = sorted(
            [w for w in word_freq if w not in stop_words],
            key=lambda x: word_freq[x],
            reverse=True
        )[:5]

        queries = [
            f"{' '.join(key_terms[:3])} research evidence",
            f"{' '.join(key_terms[:2])} latest findings",
            f"{key_terms[0] if key_terms else 'topic'} implications {original_query.split()[0]}",
        ]

        return queries[:self.max_adaptive_queries]

    def generate_adaptive_queries(
        self,
        state: Dict[str, Any],
        trigger: ReplanTrigger,
        llm: Optional[Any] = None
    ) -> List[str]:
        """
        Generate adaptive queries using optional LLM for better quality.

        If no LLM provided, falls back to rule-based generation.
        """
        if llm is None:
            # Use rule-based generation
            decision = self.should_replan(state)
            return decision.adaptive_queries

        # LLM-based query generation
        original_query = state.get("original_query", "")
        evidence_summary = self._summarize_evidence(state)

        prompt = f"""Based on the research question and evidence collected, generate {self.max_adaptive_queries}
targeted search queries to improve research coverage.

Original Question: {original_query}

Evidence Summary:
{evidence_summary}

Trigger: {trigger.value}

Generate queries that:
1. Address gaps in current evidence
2. Resolve any contradictions
3. Explore unexpected but relevant findings
4. Ensure comprehensive coverage

Respond with one query per line, no numbering."""

        try:
            response = llm.invoke(prompt)
            queries = [q.strip() for q in response.content.split("\n") if q.strip()]
            return queries[:self.max_adaptive_queries]
        except Exception as e:
            logger.warning(f"LLM query generation failed: {e}. Using rule-based fallback.")
            decision = self.should_replan(state)
            return decision.adaptive_queries

    def _summarize_evidence(self, state: Dict[str, Any], max_chars: int = 2000) -> str:
        """Create a brief summary of collected evidence."""
        evidence_chain = state.get("evidence_chain", [])

        if not evidence_chain:
            return "No evidence collected yet."

        lines = []
        char_count = 0

        for e in evidence_chain[:20]:  # Limit to first 20 pieces
            text = getattr(e, "text", str(e))
            summary = text[:200] + "..." if len(text) > 200 else text
            tier = getattr(e, "quality_tier", "UNKNOWN")
            line = f"[{tier}] {summary}"

            if char_count + len(line) > max_chars:
                break

            lines.append(line)
            char_count += len(line)

        return "\n".join(lines)

    @classmethod
    def from_config(cls, config_path: str = "config/settings/thresholds.yaml") -> "DynamicReplanner":
        """Load replanner configuration from YAML file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            replan_config = config.get("dynamic_replanning", {})

            return cls(
                max_replans=replan_config.get("max_replans", 3),
                contradiction_threshold=replan_config.get("contradiction_threshold", 0.7),
                unexpected_finding_threshold=replan_config.get("unexpected_finding_threshold", 0.8),
                critical_gap_threshold=replan_config.get("critical_gap_threshold", 3),
                max_adaptive_queries=replan_config.get("max_adaptive_queries", 10),
                novelty_weight=replan_config.get("novelty_weight", 0.4),
                relevance_weight=replan_config.get("relevance_weight", 0.6),
            )
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return cls()
        except Exception as e:
            logger.warning(f"Error loading config: {e}. Using defaults.")
            return cls()
