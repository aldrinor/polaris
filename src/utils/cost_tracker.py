#!/usr/bin/env python3
"""
POLARIS Cost Tracker - Budget Control and Cost Monitoring

Thread-safe singleton for tracking API costs across the pipeline.
Implements circuit breaker to prevent runaway costs.

ARCHITECT DIRECTIVE: This is a RELEASE BLOCKER.
Without budget controls, the system cannot be trusted at scale.

Features:
- Thread-safe singleton pattern
- Per-model token cost calculation
- Per-API-call fixed cost tracking
- Persistent cost ledger (state/cost_ledger.json)
- Circuit breaker with configurable budget limit

Usage:
    from src.utils.cost_tracker import get_cost_tracker, BudgetExceededError

    tracker = get_cost_tracker()
    tracker.add_cost("gemini-2.5-flash", tokens_in=1000, tokens_out=500)
    tracker.add_api_call("serper")
    tracker.check_budget()  # Raises BudgetExceededError if over limit
"""

import json
import logging
import threading
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# PRICING CONFIGURATION
# =============================================================================

# Model pricing (USD per 1M tokens)
MODEL_PRICING = {
    # Gemini 3 models (latest - Jan 2026)
    "gemini-3-flash": {
        "input_per_million": 0.50,    # $0.50 per 1M input tokens
        "output_per_million": 3.00,   # $3.00 per 1M output tokens
    },
    "gemini-3-pro": {
        "input_per_million": 2.50,
        "output_per_million": 10.00,
    },
    # FIX 24: Add preview variant — same pricing as gemini-3-pro
    # This model name is what ChatGoogleGenerativeAI actually uses.
    # Missing this entry caused 68% of cost entries to be $0.00.
    "gemini-3-pro-preview": {
        "input_per_million": 2.50,
        "output_per_million": 10.00,
    },
    # Gemini 2.5 models (production tier)
    "gemini-2.5-flash": {
        "input_per_million": 0.075,   # $0.075 per 1M input tokens
        "output_per_million": 0.30,   # $0.30 per 1M output tokens
    },
    "gemini-2.5-pro": {
        "input_per_million": 1.25,
        "output_per_million": 5.00,
    },
    # Gemini 1.5 models (legacy - for historical tracking)
    "gemini-1.5-flash": {
        "input_per_million": 0.075,
        "output_per_million": 0.30,
    },
    "gemini-1.5-pro": {
        "input_per_million": 1.25,
        "output_per_million": 5.00,
    },
    # OpenAI models (for reference)
    "gpt-4o": {
        "input_per_million": 2.50,
        "output_per_million": 10.00,
    },
    "gpt-4o-mini": {
        "input_per_million": 0.15,
        "output_per_million": 0.60,
    },
    # Anthropic models (for reference)
    "claude-3-5-sonnet": {
        "input_per_million": 3.00,
        "output_per_million": 15.00,
    },
    # Local/free models
    "all-MiniLM-L6-v2": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
    "deberta-v3-large-mnli": {
        "input_per_million": 0.0,
        "output_per_million": 0.0,
    },
}

# API call pricing (fixed cost per call)
API_PRICING = {
    "serper": 0.001,        # ~$0.001 per search
    "pubmed": 0.0,          # Free (rate limited)
    "semantic_scholar": 0.0, # Free (rate limited)
    "openalex": 0.0,        # Free (no limit)
}

# Default budget limit
DEFAULT_MAX_BUDGET = 5.00  # $5.00 USD


# =============================================================================
# EXCEPTIONS
# =============================================================================

class BudgetExceededError(Exception):
    """Raised when the session budget is exceeded."""

    def __init__(self, current_spend: float, budget_limit: float):
        self.current_spend = current_spend
        self.budget_limit = budget_limit
        super().__init__(
            f"Budget exceeded: ${current_spend:.4f} > ${budget_limit:.2f} limit"
        )


# =============================================================================
# COST LEDGER DATA CLASSES
# =============================================================================

@dataclass
class CostEntry:
    """Single cost entry."""
    timestamp: str
    category: str  # "model" or "api"
    name: str      # model name or API name
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    cost_usd: float = 0.0


@dataclass
class CostLedger:
    """Persistent cost ledger."""
    session_id: str
    session_start: str
    entries: list = field(default_factory=list)
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_api_calls: int = 0
    total_cost_usd: float = 0.0
    budget_limit: float = DEFAULT_MAX_BUDGET

    def add_entry(self, entry: CostEntry):
        """Add an entry to the ledger."""
        self.entries.append(asdict(entry))
        self.total_tokens_in += entry.tokens_in
        self.total_tokens_out += entry.tokens_out
        self.total_api_calls += entry.calls
        self.total_cost_usd += entry.cost_usd


# =============================================================================
# COST TRACKER SINGLETON
# =============================================================================

class CostTracker:
    """
    Thread-safe singleton for tracking costs.

    Persists to state/cost_ledger.json.
    """

    _instance: Optional["CostTracker"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        max_budget: float = DEFAULT_MAX_BUDGET,
        reset: bool = False
    ):
        """
        Initialize the cost tracker.

        Args:
            ledger_path: Path to ledger file (default: state/cost_ledger.json)
            max_budget: Maximum budget in USD
            reset: If True, reset the ledger even if it exists
        """
        # Prevent re-initialization of singleton
        if self._initialized and not reset:
            return

        self._lock = threading.Lock()

        if ledger_path is None:
            from src.config import STATE_DIR
            ledger_path = STATE_DIR / "cost_ledger.json"

        self.ledger_path = ledger_path
        self.max_budget = max_budget

        # Load or create ledger
        if reset or not self.ledger_path.exists():
            self._create_new_ledger()
        else:
            self._load_ledger()

        self._initialized = True

    def _create_new_ledger(self):
        """Create a new cost ledger."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.ledger = CostLedger(
            session_id=session_id,
            session_start=datetime.now(timezone.utc).isoformat(),
            budget_limit=self.max_budget
        )
        self._save_ledger()

    def _load_ledger(self):
        """Load existing ledger from file."""
        try:
            with open(self.ledger_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.ledger = CostLedger(**data)
                self.max_budget = self.ledger.budget_limit
        except Exception as e:
            # LOW-115: Use logger instead of print
            logger.warning(f"Failed to load cost ledger: {e}")
            self._create_new_ledger()

    def _save_ledger(self):
        """Save ledger to file."""
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.ledger), f, indent=2)

    def add_cost(
        self,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0
    ) -> float:
        """
        Add model token cost.

        Args:
            model: Model name (e.g., "gemini-2.5-flash")
            tokens_in: Number of input tokens
            tokens_out: Number of output tokens

        Returns:
            Cost in USD for this operation
        """
        with self._lock:
            # Get pricing
            pricing = MODEL_PRICING.get(model, {
                "input_per_million": 0.0,
                "output_per_million": 0.0
            })

            # Calculate cost
            input_cost = (tokens_in / 1_000_000) * pricing["input_per_million"]
            output_cost = (tokens_out / 1_000_000) * pricing["output_per_million"]
            total_cost = input_cost + output_cost

            # Create entry
            entry = CostEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="model",
                name=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=total_cost
            )

            # Add to ledger and save
            self.ledger.add_entry(entry)
            self._save_ledger()

            return total_cost

    def add_api_call(self, service_name: str, calls: int = 1) -> float:
        """
        Add API call cost.

        Args:
            service_name: API service name (e.g., "serper", "pubmed")
            calls: Number of API calls

        Returns:
            Cost in USD for this operation
        """
        with self._lock:
            # Get pricing
            cost_per_call = API_PRICING.get(service_name, 0.0)
            total_cost = cost_per_call * calls

            # Create entry
            entry = CostEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                category="api",
                name=service_name,
                calls=calls,
                cost_usd=total_cost
            )

            # Add to ledger and save
            self.ledger.add_entry(entry)
            self._save_ledger()

            return total_cost

    def check_budget(self) -> bool:
        """
        Check if current spend is within budget.

        Returns:
            True if within budget

        Raises:
            BudgetExceededError: If budget is exceeded
        """
        with self._lock:
            if self.ledger.total_cost_usd > self.max_budget:
                raise BudgetExceededError(
                    self.ledger.total_cost_usd,
                    self.max_budget
                )
            return True

    def get_total_cost(self) -> float:
        """Get total cost so far."""
        with self._lock:
            return self.ledger.total_cost_usd

    def get_remaining_budget(self) -> float:
        """Get remaining budget."""
        with self._lock:
            return max(0.0, self.max_budget - self.ledger.total_cost_usd)

    def get_summary(self) -> Dict[str, Any]:
        """Get cost summary."""
        with self._lock:
            # Aggregate by name
            by_model: Dict[str, float] = {}
            by_api: Dict[str, float] = {}

            for entry in self.ledger.entries:
                if entry["category"] == "model":
                    by_model[entry["name"]] = by_model.get(entry["name"], 0) + entry["cost_usd"]
                elif entry["category"] == "api":
                    by_api[entry["name"]] = by_api.get(entry["name"], 0) + entry["cost_usd"]

            return {
                "session_id": self.ledger.session_id,
                "total_cost_usd": self.ledger.total_cost_usd,
                "budget_limit": self.max_budget,
                "remaining_budget": self.get_remaining_budget(),
                "total_tokens_in": self.ledger.total_tokens_in,
                "total_tokens_out": self.ledger.total_tokens_out,
                "total_api_calls": self.ledger.total_api_calls,
                "cost_by_model": by_model,
                "cost_by_api": by_api,
                "entry_count": len(self.ledger.entries),
            }

    def reset(self):
        """Reset the cost tracker (for new session)."""
        with self._lock:
            self._create_new_ledger()


# =============================================================================
# MODULE-LEVEL ACCESSOR
# =============================================================================

_tracker_instance: Optional[CostTracker] = None


def get_cost_tracker(
    max_budget: float = DEFAULT_MAX_BUDGET,
    reset: bool = False
) -> CostTracker:
    """
    Get the global cost tracker instance.

    Args:
        max_budget: Maximum budget in USD
        reset: If True, reset the tracker

    Returns:
        CostTracker singleton instance
    """
    global _tracker_instance
    if _tracker_instance is None or reset:
        _tracker_instance = CostTracker(max_budget=max_budget, reset=reset)
    return _tracker_instance


# =============================================================================
# SELF-TEST
# =============================================================================

def self_test():
    """Run self-tests for cost tracker."""
    import tempfile
    import os

    # Flush stdout for Windows compatibility
    sys.stdout.flush()

    print("\n" + "=" * 60)
    print("COST TRACKER SELF-TEST")
    print("=" * 60)
    sys.stdout.flush()

    # Create temp directory for test ledger
    test_dir = Path(tempfile.mkdtemp())
    test_ledger = test_dir / "test_ledger.json"

    # Reset singleton for testing
    CostTracker._instance = None

    # Test 1: Create tracker
    tracker = CostTracker(ledger_path=test_ledger, max_budget=1.00, reset=True)
    assert tracker.get_total_cost() == 0.0
    print("  [PASS] Tracker creation")

    # Test 2: Add model cost
    cost = tracker.add_cost("gemini-2.5-flash", tokens_in=1_000_000, tokens_out=100_000)
    expected = (1_000_000 / 1_000_000) * 0.075 + (100_000 / 1_000_000) * 0.30
    assert abs(cost - expected) < 0.0001, f"Expected {expected}, got {cost}"
    print(f"  [PASS] Model cost calculation: ${cost:.4f}")

    # Test 3: Add API cost
    cost = tracker.add_api_call("serper", calls=10)
    assert abs(cost - 0.01) < 0.0001, f"Expected 0.01, got {cost}"
    print(f"  [PASS] API cost calculation: ${cost:.4f}")

    # Test 4: Total cost
    total = tracker.get_total_cost()
    assert total > 0
    print(f"  [PASS] Total cost tracking: ${total:.4f}")

    # Test 5: Persistence
    saved_total = total
    CostTracker._instance = None
    tracker2 = CostTracker(ledger_path=test_ledger, max_budget=1.00)
    assert abs(tracker2.get_total_cost() - saved_total) < 0.0001
    print("  [PASS] Persistence to disk")

    # Test 6: Budget check (under budget)
    try:
        tracker2.check_budget()
        print("  [PASS] Budget check (under limit)")
    except BudgetExceededError:
        print("  [FAIL] Budget check raised error incorrectly")
        return False

    # Test 7: Budget exceeded
    CostTracker._instance = None
    tracker3 = CostTracker(ledger_path=test_ledger, max_budget=0.001, reset=True)
    tracker3.add_cost("gemini-2.5-flash", tokens_in=100_000, tokens_out=10_000)
    try:
        tracker3.check_budget()
        print("  [FAIL] Budget check should have raised error")
        return False
    except BudgetExceededError as e:
        print(f"  [PASS] Budget exceeded detection: {e}")

    # Test 8: Summary
    CostTracker._instance = None
    tracker4 = CostTracker(ledger_path=test_ledger, max_budget=5.00, reset=True)
    tracker4.add_cost("gemini-2.5-flash", tokens_in=100_000, tokens_out=50_000)
    tracker4.add_api_call("serper", calls=5)
    summary = tracker4.get_summary()
    assert "total_cost_usd" in summary
    assert "cost_by_model" in summary
    assert "cost_by_api" in summary
    print("  [PASS] Summary generation")

    # Test 9: Thread safety (basic) - using threading module directly
    import threading

    CostTracker._instance = None
    tracker5 = CostTracker(ledger_path=test_ledger, max_budget=10.00, reset=True)

    results = []
    def add_costs():
        for _ in range(10):
            tracker5.add_cost("gemini-2.5-flash", tokens_in=1000, tokens_out=100)
        results.append(True)

    threads = [threading.Thread(target=add_costs) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 2
    assert len(tracker5.ledger.entries) == 20
    print("  [PASS] Thread safety (20 concurrent entries)")
    sys.stdout.flush()

    # Cleanup
    try:
        os.remove(test_ledger)
        os.rmdir(test_dir)
    except (OSError, FileNotFoundError):
        pass  # Cleanup failure is OK in tests

    # Reset singleton
    CostTracker._instance = None

    print("\n" + "=" * 60)
    print("ALL SELF-TESTS PASSED")
    print("=" * 60)
    sys.stdout.flush()
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="POLARIS Cost Tracker")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    parser.add_argument("--summary", action="store_true", help="Print cost summary")
    parser.add_argument("--reset", action="store_true", help="Reset cost ledger")

    args = parser.parse_args()

    if args.self_test:
        success = self_test()
        sys.exit(0 if success else 1)

    if args.reset:
        tracker = get_cost_tracker(reset=True)
        print("Cost ledger reset.")
        sys.exit(0)

    if args.summary:
        tracker = get_cost_tracker()
        summary = tracker.get_summary()
        print("\n" + "=" * 60)
        print("COST SUMMARY")
        print("=" * 60)
        print(f"Session ID: {summary['session_id']}")
        print(f"Total Cost: ${summary['total_cost_usd']:.4f}")
        print(f"Budget Limit: ${summary['budget_limit']:.2f}")
        print(f"Remaining: ${summary['remaining_budget']:.4f}")
        print(f"\nTokens In: {summary['total_tokens_in']:,}")
        print(f"Tokens Out: {summary['total_tokens_out']:,}")
        print(f"API Calls: {summary['total_api_calls']}")
        print(f"\nCost by Model:")
        for model, cost in summary['cost_by_model'].items():
            print(f"  {model}: ${cost:.4f}")
        print(f"\nCost by API:")
        for api, cost in summary['cost_by_api'].items():
            print(f"  {api}: ${cost:.4f}")
        print("=" * 60)
        sys.exit(0)

    # Default: print summary
    tracker = get_cost_tracker()
    print(f"Total cost: ${tracker.get_total_cost():.4f}")
