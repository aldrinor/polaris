"""
POLARIS Circuit Breaker

SOTA FIX: Issues #55-58 - Architecture improvements.

Provides:
- Circuit breaker pattern for external services
- Graceful degradation
- Fallback mechanisms
- Health monitoring
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes to close from half-open
    timeout_seconds: float = 60.0       # Time to wait before half-open
    half_open_max_calls: int = 3        # Max calls in half-open state


@dataclass
class CircuitStats:
    """Statistics for circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: List[Dict[str, Any]] = field(default_factory=list)


class CircuitBreaker:
    """
    Circuit breaker implementation.

    SOTA FIX: Issue #56 - Circuit breakers per source.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service failing, calls rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Name of the protected service
            config: Configuration options
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self.stats = CircuitStats()

    @property
    def state(self) -> CircuitState:
        """Get current state, checking for timeout transition."""
        if self._state == CircuitState.OPEN:
            # Check if timeout has passed
            if time.time() - self._last_failure_time >= self.config.timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state."""
        old_state = self._state
        self._state = new_state

        self.stats.state_changes.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": time.time(),
        })

        logger.info(f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}")

        # Reset counters on state change
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_success(self) -> None:
        """Record a successful call."""
        self.stats.total_calls += 1
        self.stats.successful_calls += 1

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed call."""
        self.stats.total_calls += 1
        self.stats.failed_calls += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

    def allow_request(self) -> bool:
        """Check if request should be allowed."""
        current_state = self.state  # This may trigger timeout transition

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.OPEN:
            self.stats.rejected_calls += 1
            return False
        else:  # HALF_OPEN
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.stats.total_calls,
            "successful_calls": self.stats.successful_calls,
            "failed_calls": self.stats.failed_calls,
            "rejected_calls": self.stats.rejected_calls,
            "failure_rate": self.stats.failed_calls / max(self.stats.total_calls, 1),
        }


def circuit_breaker(
    breaker: CircuitBreaker,
    fallback: Optional[Callable[..., T]] = None,
):
    """
    Decorator to protect function with circuit breaker.

    SOTA FIX: Issue #56 - Circuit breaker decorator.

    Args:
        breaker: CircuitBreaker instance
        fallback: Optional fallback function

    Usage:
        cb = CircuitBreaker("serper_api")

        @circuit_breaker(cb, fallback=get_cached_results)
        def search_serper(query):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            if not breaker.allow_request():
                logger.warning(f"Circuit breaker '{breaker.name}' is OPEN, rejecting call")
                if fallback:
                    return fallback(*args, **kwargs)
                raise CircuitOpenError(breaker.name)

            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                logger.error(f"Circuit breaker '{breaker.name}' recorded failure: {e}")
                if fallback:
                    return fallback(*args, **kwargs)
                raise

        return wrapper
    return decorator


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Circuit breaker for '{service_name}' is OPEN")


# =============================================================================
# Graceful Degradation
# =============================================================================

@dataclass
class DegradationLevel:
    """Degradation level configuration."""
    name: str
    description: str
    enabled_features: List[str]
    disabled_features: List[str]


class GracefulDegrader:
    """
    Manages graceful degradation of features.

    SOTA FIX: Issue #57 - Graceful degradation.
    """

    # Standard degradation levels
    LEVELS = {
        "full": DegradationLevel(
            name="full",
            description="All features enabled",
            enabled_features=["search", "llm_analysis", "nli_verification", "graph_enrichment"],
            disabled_features=[],
        ),
        "reduced": DegradationLevel(
            name="reduced",
            description="Reduced functionality",
            enabled_features=["search", "llm_analysis"],
            disabled_features=["nli_verification", "graph_enrichment"],
        ),
        "minimal": DegradationLevel(
            name="minimal",
            description="Minimal functionality",
            enabled_features=["search"],
            disabled_features=["llm_analysis", "nli_verification", "graph_enrichment"],
        ),
        "offline": DegradationLevel(
            name="offline",
            description="Offline mode, cache only",
            enabled_features=[],
            disabled_features=["search", "llm_analysis", "nli_verification", "graph_enrichment"],
        ),
    }

    def __init__(self, initial_level: str = "full"):
        """Initialize with degradation level."""
        self._level = self.LEVELS.get(initial_level, self.LEVELS["full"])
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def register_circuit_breaker(self, name: str, breaker: CircuitBreaker) -> None:
        """Register a circuit breaker for monitoring."""
        self._circuit_breakers[name] = breaker

    def check_and_adjust(self) -> None:
        """Check circuit breakers and adjust degradation level."""
        open_count = sum(
            1 for cb in self._circuit_breakers.values()
            if cb.state == CircuitState.OPEN
        )

        if open_count == 0:
            self._level = self.LEVELS["full"]
        elif open_count == 1:
            self._level = self.LEVELS["reduced"]
        elif open_count == 2:
            self._level = self.LEVELS["minimal"]
        else:
            self._level = self.LEVELS["offline"]

        logger.info(f"Degradation level: {self._level.name}")

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled at current level."""
        return feature in self._level.enabled_features

    def get_status(self) -> Dict[str, Any]:
        """Get degradation status."""
        return {
            "level": self._level.name,
            "description": self._level.description,
            "enabled_features": self._level.enabled_features,
            "disabled_features": self._level.disabled_features,
            "circuit_breakers": {
                name: cb.get_stats()
                for name, cb in self._circuit_breakers.items()
            },
        }


# =============================================================================
# Health Monitor
# =============================================================================

class HealthMonitor:
    """
    Monitors health of external services.

    SOTA FIX: Issue #58 - Health monitoring.
    """

    def __init__(self):
        self._services: Dict[str, Dict[str, Any]] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def register_service(
        self,
        name: str,
        health_check: Optional[Callable[[], bool]] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """Register a service for monitoring."""
        self._services[name] = {
            "health_check": health_check,
            "last_check": None,
            "last_status": None,
        }
        if circuit_breaker:
            self._circuit_breakers[name] = circuit_breaker

    def check_health(self, name: str) -> bool:
        """Check health of a specific service."""
        if name not in self._services:
            return True

        service = self._services[name]
        health_check = service.get("health_check")

        if health_check:
            try:
                status = health_check()
                service["last_status"] = status
                service["last_check"] = time.time()
                return status
            except Exception as e:
                logger.warning(f"Health check failed for {name}: {e}")
                service["last_status"] = False
                service["last_check"] = time.time()
                return False

        # Check circuit breaker state
        if name in self._circuit_breakers:
            return self._circuit_breakers[name].state != CircuitState.OPEN

        return True

    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall health status."""
        statuses = {}
        for name in self._services:
            statuses[name] = self.check_health(name)

        healthy_count = sum(1 for s in statuses.values() if s)
        total_count = len(statuses)

        return {
            "healthy": healthy_count == total_count,
            "healthy_count": healthy_count,
            "total_count": total_count,
            "services": statuses,
        }


# =============================================================================
# Global Instances
# =============================================================================

_degrader: Optional[GracefulDegrader] = None
_health_monitor: Optional[HealthMonitor] = None


def get_degrader() -> GracefulDegrader:
    """Get global graceful degrader."""
    global _degrader
    if _degrader is None:
        _degrader = GracefulDegrader()
    return _degrader


def get_health_monitor() -> HealthMonitor:
    """Get global health monitor."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
