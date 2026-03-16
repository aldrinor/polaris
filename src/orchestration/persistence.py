"""
POLARIS v3 State Persistence

Handles saving and loading ResearchState to/from JSON files.
Enables crash recovery and session resumption.
"""

import json
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .state import ResearchState, serialize_state, deserialize_state


logger = logging.getLogger(__name__)


class StatePersistence:
    """
    Manages persistence of ResearchState to disk.

    Features:
    - Auto-save after each agent invocation
    - Crash recovery from last saved state
    - State history for debugging
    """

    def __init__(self, base_dir: str = "state/v3"):
        """
        Initialize state persistence.

        Args:
            base_dir: Directory for state files
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_path(self, vector_id: str) -> Path:
        """Get the path for a vector's state file."""
        safe_id = vector_id.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe_id}_state.json"

    def _get_history_dir(self, vector_id: str) -> Path:
        """Get the directory for state history."""
        safe_id = vector_id.replace("/", "_").replace("\\", "_")
        history_dir = self.base_dir / "history" / safe_id
        history_dir.mkdir(parents=True, exist_ok=True)
        return history_dir

    def save(self, state: ResearchState, checkpoint_name: Optional[str] = None) -> str:
        """
        Save state to disk.

        Args:
            state: ResearchState to save
            checkpoint_name: Optional name for this checkpoint

        Returns:
            Path to saved file
        """
        vector_id = state.get("vector_id", "unknown")

        # Update timestamp
        if "timestamps" not in state:
            state["timestamps"] = {}
        state["timestamps"]["last_saved"] = datetime.now(timezone.utc).isoformat()

        # Serialize state
        serialized = serialize_state(state)

        # Save main state file
        state_path = self._get_state_path(vector_id)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, default=str)

        # Save to history if checkpoint name provided
        if checkpoint_name:
            history_dir = self._get_history_dir(vector_id)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            history_path = history_dir / f"{timestamp}_{checkpoint_name}.json"
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, default=str)
            logger.info(f"Saved checkpoint '{checkpoint_name}' for {vector_id}")

        logger.debug(f"Saved state for {vector_id} to {state_path}")
        return str(state_path)

    def load(self, vector_id: str) -> Optional[ResearchState]:
        """
        Load state from disk.

        Args:
            vector_id: Vector ID to load

        Returns:
            ResearchState if found, None otherwise
        """
        state_path = self._get_state_path(vector_id)

        if not state_path.exists():
            logger.debug(f"No saved state found for {vector_id}")
            return None

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            state = deserialize_state(data)
            logger.info(f"Loaded state for {vector_id} (iteration {state.get('iteration_count', 0)})")
            return state

        except Exception as e:
            logger.error(f"Failed to load state for {vector_id}: {e}")
            return None

    def exists(self, vector_id: str) -> bool:
        """Check if state exists for a vector."""
        return self._get_state_path(vector_id).exists()

    def delete(self, vector_id: str) -> bool:
        """
        Delete state for a vector.

        Args:
            vector_id: Vector ID to delete

        Returns:
            True if deleted, False if not found
        """
        state_path = self._get_state_path(vector_id)

        if state_path.exists():
            state_path.unlink()
            logger.info(f"Deleted state for {vector_id}")
            return True
        return False

    def list_vectors(self) -> list:
        """List all vectors with saved state."""
        vectors = []
        for path in self.base_dir.glob("*_state.json"):
            vector_id = path.stem.replace("_state", "")
            vectors.append(vector_id)
        return vectors

    def get_checkpoint_history(self, vector_id: str) -> list:
        """Get list of checkpoints for a vector."""
        history_dir = self._get_history_dir(vector_id)
        checkpoints = []
        for path in sorted(history_dir.glob("*.json")):
            checkpoints.append({
                "name": path.stem,
                "path": str(path),
                "timestamp": path.stem.split("_")[0] + "_" + path.stem.split("_")[1]
            })
        return checkpoints

    def load_checkpoint(self, vector_id: str, checkpoint_name: str) -> Optional[ResearchState]:
        """Load a specific checkpoint."""
        history_dir = self._get_history_dir(vector_id)

        # Find checkpoint file
        for path in history_dir.glob(f"*_{checkpoint_name}.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return deserialize_state(data)
            except Exception as e:
                logger.error(f"Failed to load checkpoint {checkpoint_name}: {e}")
                return None

        logger.warning(f"Checkpoint {checkpoint_name} not found for {vector_id}")
        return None


# Global persistence instance
_persistence: Optional[StatePersistence] = None


def get_persistence() -> StatePersistence:
    """Get the global persistence instance."""
    global _persistence
    if _persistence is None:
        _persistence = StatePersistence()
    return _persistence


def save_state(state: ResearchState, checkpoint: Optional[str] = None) -> str:
    """Convenience function to save state."""
    return get_persistence().save(state, checkpoint)


def load_state(vector_id: str) -> Optional[ResearchState]:
    """Convenience function to load state."""
    return get_persistence().load(vector_id)
