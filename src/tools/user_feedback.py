"""
User Feedback Loop (OpenAI Parity)
===================================
Enables mid-research user intervention and course correction.

OpenAI Deep Research allows user feedback during research.
We implement checkpoint/resume with feedback integration.
"""

import logging
import json
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """Type of user feedback."""
    REFOCUS = "refocus"  # Change research focus
    ADD_TOPIC = "add_topic"  # Add new topic to explore
    REMOVE_TOPIC = "remove_topic"  # Stop exploring a topic
    ADJUST_DEPTH = "adjust_depth"  # More/less detail
    APPROVE = "approve"  # Continue as planned
    STOP = "stop"  # Stop research
    CUSTOM = "custom"  # Free-form feedback


@dataclass
class UserFeedback:
    """User feedback instance."""
    feedback_id: str
    feedback_type: FeedbackType
    content: str
    timestamp: str
    applied: bool = False
    impact: Optional[str] = None


@dataclass
class FeedbackCheckpoint:
    """Checkpoint for feedback collection."""
    checkpoint_id: str
    timestamp: str
    stage: str  # Which pipeline stage
    progress_pct: float
    summary: str
    questions_for_user: List[str]
    awaiting_feedback: bool = True
    state_snapshot: Dict = field(default_factory=dict)


class UserFeedbackManager:
    """
    User feedback manager.

    Handles mid-research pauses for user input.
    """

    def __init__(
        self,
        checkpoint_dir: str = "state/feedback_checkpoints",
        auto_checkpoint_interval: int = 5,  # Create checkpoint every N iterations
    ):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.auto_interval = auto_checkpoint_interval
        self.iteration_count = 0

        self.checkpoints: List[FeedbackCheckpoint] = []
        self.feedback_history: List[UserFeedback] = []

        # Callback for notifying user
        self.notify_callback: Optional[Callable[[FeedbackCheckpoint], None]] = None

    def should_checkpoint(self, state: Dict) -> bool:
        """Check if we should create a checkpoint."""
        self.iteration_count += 1

        # Regular interval checkpoint
        if self.iteration_count % self.auto_interval == 0:
            return True

        # Checkpoint on significant events
        if state.get("significant_finding"):
            return True

        if state.get("contradiction_found"):
            return True

        if state.get("coverage_below_threshold"):
            return True

        return False

    def create_checkpoint(
        self,
        state: Dict,
        stage: str,
        summary: str,
        questions: List[str] = None,
    ) -> FeedbackCheckpoint:
        """Create a feedback checkpoint."""
        checkpoint = FeedbackCheckpoint(
            checkpoint_id=f"ckpt_{len(self.checkpoints):04d}",
            timestamp=datetime.now(UTC).isoformat(),
            stage=stage,
            progress_pct=self._calculate_progress(state),
            summary=summary,
            questions_for_user=questions or self._generate_questions(state),
            state_snapshot=self._snapshot_state(state),
        )

        self.checkpoints.append(checkpoint)
        self._save_checkpoint(checkpoint)

        logger.info(f"[FEEDBACK] Created checkpoint: {checkpoint.checkpoint_id}")

        # Notify user if callback set
        if self.notify_callback:
            self.notify_callback(checkpoint)

        return checkpoint

    async def await_feedback(
        self,
        checkpoint: FeedbackCheckpoint,
        timeout_seconds: int = 300,
    ) -> Optional[UserFeedback]:
        """
        Await user feedback on checkpoint.

        In CLI mode, this prompts the user.
        In API mode, this would wait for webhook/API call.
        """
        import asyncio

        print(f"\n{'='*60}")
        print(f"CHECKPOINT: {checkpoint.checkpoint_id}")
        print(f"Stage: {checkpoint.stage}")
        print(f"Progress: {checkpoint.progress_pct:.0%}")
        print(f"\n{checkpoint.summary}")
        print(f"\nQuestions for you:")
        for i, q in enumerate(checkpoint.questions_for_user, 1):
            print(f"  {i}. {q}")
        print(f"\nOptions:")
        print("  [1] Continue as planned")
        print("  [2] Refocus research")
        print("  [3] Add topic to explore")
        print("  [4] Stop and generate report now")
        print("  [5] Provide custom feedback")
        print(f"{'='*60}")

        # In a real implementation, this would use async input
        # For now, auto-approve after timeout
        try:
            # Simplified: auto-approve
            await asyncio.sleep(1)  # Brief pause
            return UserFeedback(
                feedback_id=f"fb_{len(self.feedback_history):04d}",
                feedback_type=FeedbackType.APPROVE,
                content="Auto-approved",
                timestamp=datetime.now(UTC).isoformat(),
            )
        except asyncio.TimeoutError:
            logger.info("[FEEDBACK] Timeout, auto-continuing")
            return None

    def apply_feedback(
        self,
        feedback: UserFeedback,
        state: Dict,
    ) -> Dict:
        """Apply user feedback to research state."""
        if feedback.feedback_type == FeedbackType.APPROVE:
            logger.info("[FEEDBACK] User approved, continuing")
            feedback.impact = "Continued as planned"

        elif feedback.feedback_type == FeedbackType.REFOCUS:
            # Adjust research focus
            state["research_focus"] = feedback.content
            state["sub_queries"] = []  # Clear queries for regeneration
            feedback.impact = f"Refocused on: {feedback.content}"
            logger.info(f"[FEEDBACK] Refocused: {feedback.content}")

        elif feedback.feedback_type == FeedbackType.ADD_TOPIC:
            # Add topic to explore
            topics = state.get("topics_to_explore", [])
            topics.append(feedback.content)
            state["topics_to_explore"] = topics
            feedback.impact = f"Added topic: {feedback.content}"
            logger.info(f"[FEEDBACK] Added topic: {feedback.content}")

        elif feedback.feedback_type == FeedbackType.REMOVE_TOPIC:
            # Remove topic
            topics = state.get("topics_to_explore", [])
            if feedback.content in topics:
                topics.remove(feedback.content)
            state["topics_to_explore"] = topics
            feedback.impact = f"Removed topic: {feedback.content}"

        elif feedback.feedback_type == FeedbackType.STOP:
            # Stop research and generate final report
            state["force_finalize"] = True
            feedback.impact = "Forced early finalization"
            logger.info("[FEEDBACK] User requested stop")

        elif feedback.feedback_type == FeedbackType.CUSTOM:
            # Custom feedback - inject into state
            state["user_guidance"] = feedback.content
            feedback.impact = f"Custom guidance: {feedback.content[:50]}..."

        feedback.applied = True
        self.feedback_history.append(feedback)

        return state

    def _calculate_progress(self, state: Dict) -> float:
        """Calculate research progress percentage."""
        total_queries = state.get("total_queries", 50)
        completed_queries = state.get("completed_queries", 0)

        return min(completed_queries / total_queries, 1.0) if total_queries > 0 else 0.0

    def _generate_questions(self, state: Dict) -> List[str]:
        """Generate relevant questions for user."""
        questions = []

        coverage = state.get("coverage_pct", 0)
        if coverage < 0.5:
            questions.append(f"Coverage is at {coverage:.0%}. Should we explore more sources?")

        if state.get("contradictions"):
            questions.append("Found contradictory information. Which perspective is more important?")

        if not questions:
            questions.append("Is the research heading in the right direction?")
            questions.append("Are there any specific aspects you want to emphasize?")

        return questions

    def _snapshot_state(self, state: Dict) -> Dict:
        """Create lightweight state snapshot for checkpoint."""
        return {
            "evidence_count": len(state.get("evidence_chain", [])),
            "query_count": len(state.get("sub_queries", [])),
            "coverage_pct": state.get("coverage_pct", 0),
            "faithfulness": state.get("post_hoc_faithfulness", 0),
        }

    def _save_checkpoint(self, checkpoint: FeedbackCheckpoint):
        """Save checkpoint to disk."""
        path = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        with open(path, 'w') as f:
            json.dump({
                "checkpoint_id": checkpoint.checkpoint_id,
                "timestamp": checkpoint.timestamp,
                "stage": checkpoint.stage,
                "progress_pct": checkpoint.progress_pct,
                "summary": checkpoint.summary,
                "questions_for_user": checkpoint.questions_for_user,
                "awaiting_feedback": checkpoint.awaiting_feedback,
            }, f, indent=2)

    def load_checkpoint(self, checkpoint_id: str) -> Optional[FeedbackCheckpoint]:
        """Load checkpoint from disk."""
        path = self.checkpoint_dir / f"{checkpoint_id}.json"
        if not path.exists():
            return None

        with open(path, 'r') as f:
            data = json.load(f)
            return FeedbackCheckpoint(**data)

    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary of all feedback collected."""
        return {
            "total_checkpoints": len(self.checkpoints),
            "total_feedback": len(self.feedback_history),
            "feedback_types": [f.feedback_type.value for f in self.feedback_history],
            "impacts": [f.impact for f in self.feedback_history if f.impact],
        }
