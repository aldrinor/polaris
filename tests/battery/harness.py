"""Shared contract for the T2 edge-case battery (docs/agentic_outline_redesign.md PART 2/3).

A battery *case* is a real, deterministic exercise of the agentic-outliner faithfulness/compute
machinery that emits a list of ``Assertion``s. Each assertion is STRUCTURAL only (design §-1.1.1
class A): a gold-number match, a ledger/registry state, a kept/dropped count, a disclosure
presence — NEVER a word count or prose-wording match. The runner (``scripts/outline_battery.py``)
collects the assertions, ranks the failures by severity S0..S4, and writes the wheel's plain-text
output.

Severity ladder (design §3 "Result collection & failure ranking"):
  S0 FAITHFULNESS BREACH  — a wrong/unsupported number rendered as VERIFIED; a derived number
                            laundered through the [#ev:] span path; id-collision swallowed.
                            Blocks everything.
  S1 WRONG ANSWER, UNDISCLOSED — gold missed with no UNFILLED/uncertainty disclosure.
  S2 CAPABILITY MISS, HONEST    — gold missed but correctly disclosed (roadmap, not a blocker).
  S3 BEHAVIOR                   — redundant retrieval, budget overshoot, looping, timeout.
  S4 cosmetic.

Cases mark themselves ``xfail=True`` when they stress a capability that has not landed yet
(e.g. find_contradictions for H07/H22); an xfail case that FAILS is reported as ``xfail`` (a
known gap, not a regression) and an xfail case that PASSES is reported as ``xpass`` (land it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

# Severity ranks: lower number == more severe (S0 is the worst).
SEVERITIES = ("S0", "S1", "S2", "S3", "S4")


def severity_rank(sev: str) -> int:
    try:
        return SEVERITIES.index(sev)
    except ValueError:
        return len(SEVERITIES)


@dataclass
class Assertion:
    """One structural check. ``severity`` is what this failure COSTS if ``passed`` is False."""

    name: str
    passed: bool
    expected: object = ""
    actual: object = ""
    severity: str = "S1"
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "pass": self.passed,
            "expected": _json_safe(self.expected),
            "actual": _json_safe(self.actual),
            "severity": self.severity,
            "detail": self.detail,
        }


def _json_safe(v: object) -> object:
    """Coerce sets/tuples/other non-JSON scalars to a stable serializable form."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return sorted(str(x) for x in v)
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)


@dataclass
class BatteryCase:
    """A single battery case. ``run`` returns the case's assertions (may be async)."""

    id: str
    domain: str
    capability: str
    run: Callable[[], "Awaitable[list[Assertion]] | list[Assertion]"]
    xfail: bool = False
    note: str = ""


@dataclass
class CaseResult:
    case_id: str
    domain: str
    capability: str
    assertions: list[Assertion] = field(default_factory=list)
    xfail: bool = False
    error: str = ""
    wall_s: float = 0.0
    note: str = ""

    @property
    def failed(self) -> list[Assertion]:
        return [a for a in self.assertions if not a.passed]

    @property
    def worst_severity(self) -> str | None:
        """The most-severe failing assertion's severity, or None if all passed."""
        fails = self.failed
        if self.error:
            return "S0"  # an uncaught exception in a faithfulness probe is treated as worst-case
        if not fails:
            return None
        return min((a.severity for a in fails), key=severity_rank)

    @property
    def outcome(self) -> str:
        """pass | fail | xfail | xpass | error."""
        if self.error and not self.xfail:
            return "error"
        worst = self.worst_severity
        if self.xfail:
            return "xpass" if worst is None else "xfail"
        return "pass" if worst is None else "fail"

    def as_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "domain": self.domain,
            "capability": self.capability,
            "xfail": self.xfail,
            "outcome": self.outcome,
            "worst_severity": self.worst_severity,
            "error": self.error,
            "wall_s": round(self.wall_s, 3),
            "assertions": [a.as_dict() for a in self.assertions],
        }
