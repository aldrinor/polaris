"""I-cred-003 (Phase 3, L2 / §6c-2) — temporal / supersession + retraction hard penalty.

Pure-function credibility adjustment for time-sensitive evidence. It downgrades stale-but-authoritative
sources (old guidelines, superseded datasets/regulations) and applies a HARD penalty to
retracted/withdrawn sources, plus a per-claim ``soft_warning`` and a ``certainty_downgrade`` signal.

Default-OFF: this is inert library code — nothing in the production path imports or invokes it, so OFF
behaviour is byte-identical by construction. It acts only when a flagged caller (the Phase-2 scorer)
calls ``supersession_adjustment``; ``supersession_enabled()`` gates that wiring. It edits no
faithfulness-critical file (provenance_generator / strict_verify / 4-role / two-family / corpus_approval
are untouched). LAW VI: every threshold is an env-overridable named constant — no hardcoded magic
numbers, snake_case, explicit imports, no network, no live data.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass

# Runtime flag (default OFF). Both this and a caller invocation are needed for any effect.
_FLAG = "PG_SWEEP_SUPERSESSION"

# Source types whose credibility is TIME-SENSITIVE (a stale one is downgraded). Everything else
# (e.g. a foundational-theory paper) is NOT downgraded for age alone. Env-overridable (LAW VI).
_TIME_SENSITIVE_TYPES = frozenset(
    t.strip().lower()
    for t in os.getenv(
        "PG_SUPERSESSION_TIME_SENSITIVE_TYPES",
        "guideline,regulation,dataset,statistics,news,advisory",
    ).split(",")
    if t.strip()
)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def supersession_enabled() -> bool:
    """True iff the supersession layer is wired ON (default OFF => byte-identical)."""
    return os.getenv(_FLAG, "0") == "1"


@dataclass
class SupersessionResult:
    multiplier: float            # multiply the source's credibility weight by this (1.0 = no change)
    hard_penalty: bool           # True iff retracted/withdrawn (a near-zero multiplier)
    soft_warning: str | None     # surfaced per claim; None when no adjustment was made
    certainty_downgrade: bool    # True iff the claim's certainty label should drop


def _is_truthy(row: dict, *keys: str) -> bool:
    for key in keys:
        value = row.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in (
            "1", "true", "yes", "retracted", "withdrawn", "superseded",
        ):
            return True
    return False


def _publication_year(row: dict) -> int | None:
    for key in ("year", "publication_year", "pub_year"):
        value = row.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    for key in ("date", "published", "publication_date"):
        value = row.get(key)
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    return None


def supersession_adjustment(row: dict, *, now_year: int | None = None) -> SupersessionResult:
    """Return the temporal/supersession credibility adjustment for one source row.

    ``row`` may carry a retraction flag (``is_retracted`` / ``retracted`` / ``retraction_notice`` /
    ``withdrawn``), a supersession flag (``is_superseded`` / ``superseded`` / ``superseded_by``), a
    source type (``source_type`` / ``type`` / ``tier_label``), and a publication year/date. ``now_year``
    defaults to the current UTC year — pass it explicitly for deterministic tests.
    """
    if now_year is None:
        now_year = datetime.datetime.now(datetime.timezone.utc).year

    retraction_multiplier = _env_float("PG_SUPERSESSION_RETRACTION_MULTIPLIER", 0.05)
    stale_multiplier = _env_float("PG_SUPERSESSION_STALE_MULTIPLIER", 0.6)
    stale_years = _env_int("PG_SUPERSESSION_STALE_YEARS", 7)

    # 1) Retraction / withdrawal -> HARD penalty (overrides freshness + everything else).
    if _is_truthy(row, "is_retracted", "retracted", "retraction_notice", "withdrawn"):
        return SupersessionResult(
            multiplier=retraction_multiplier,
            hard_penalty=True,
            soft_warning="retracted/withdrawn source — hard credibility penalty applied",
            certainty_downgrade=True,
        )

    # 2) Explicitly superseded -> stale-grade downgrade.
    if _is_truthy(row, "is_superseded", "superseded") or row.get("superseded_by"):
        return SupersessionResult(
            multiplier=stale_multiplier,
            hard_penalty=False,
            soft_warning="superseded by a newer version — downgraded",
            certainty_downgrade=True,
        )

    # 3) Stale-by-age, ONLY for time-sensitive source types (no fabricated penalty otherwise).
    source_type = str(
        row.get("source_type") or row.get("type") or row.get("tier_label") or ""
    ).strip().lower()
    publication_year = _publication_year(row)
    if source_type in _TIME_SENSITIVE_TYPES and publication_year is not None:
        age = now_year - publication_year
        if age > stale_years:
            return SupersessionResult(
                multiplier=stale_multiplier,
                hard_penalty=False,
                soft_warning=(
                    f"potentially out-of-date: {source_type} published {age} years ago "
                    f"(> {stale_years}y staleness threshold)"
                ),
                certainty_downgrade=True,
            )

    # 4) No adjustment.
    return SupersessionResult(multiplier=1.0, hard_penalty=False, soft_warning=None, certainty_downgrade=False)
