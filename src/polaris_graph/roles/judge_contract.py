"""Judge (Qwen3.6) verdict contract — hard-enum, NO silent default.

Reuses the canonical 5-enum verdict shape from `claim_audit_scorer.Verdict`
(VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE). It is IMPORTED, never
redefined, so there is exactly one verdict vocabulary in the codebase.

The Judge runs self-hosted under vLLM with a hard enum constraint
(`structured_outputs.choice`, the correct spelling — `guided_choice` is deprecated, F4).
`JUDGE_CHOICES` exposes the exact allowed token list for that constraint (PR4).

This module also holds the `source_missing` split classifier (`classify_unreachable`),
which separates a genuine artifact/fetch miss (UNREACHABLE) from a fabricated citation
identity (FABRICATED). The wiring into the release gate is sub-PR-3.
"""

from __future__ import annotations

from typing import Iterable, get_args

from src.polaris_graph.benchmark.claim_audit_scorer import Verdict

# The exact allowed verdict tokens, derived from the canonical Literal so the two can
# never drift. Used by PR4 for the vLLM `structured_outputs.choice` constraint.
JUDGE_CHOICES: list[str] = list(get_args(Verdict))

# Fetch-miss subtypes: a real artifact/fetch failure for an IN-POOL source -> UNREACHABLE.
_FETCH_MISS_SUBTYPES = ("paywall", "robots", "fetch_failure")

# Classification outputs of classify_unreachable.
_CLASS_UNREACHABLE = "UNREACHABLE"
_CLASS_FABRICATED = "FABRICATED"


class JudgeEnumError(ValueError):
    """Raised when a raw Judge output is not exactly one of the 5 canonical verdicts.

    There is NO silent default. A non-enum token is a hard failure (clinical safety):
    the caller must treat it as a parse error and escalate, never coerce it to a verdict.
    """


def parse_judge_verdict(raw: str) -> Verdict:
    """Parse a raw Judge output into the canonical 5-enum `Verdict`.

    The match is exact against `JUDGE_CHOICES` after stripping surrounding whitespace.
    Any non-enum token — garbage, empty, lowercase-unknown, partial — raises
    `JudgeEnumError`. There is deliberately NO case-folding and NO fuzzy match: the Judge
    is enum-constrained at decode time (vLLM), so anything off-enum signals a real fault.
    """
    if not isinstance(raw, str):
        raise JudgeEnumError(f"Judge output is not a string: {type(raw)!r}")
    token = raw.strip()
    if token not in JUDGE_CHOICES:
        raise JudgeEnumError(
            f"Judge output {token!r} is not one of the {len(JUDGE_CHOICES)} canonical "
            f"verdicts {JUDGE_CHOICES}"
        )
    # token is now a member of the Verdict Literal domain.
    return token  # type: ignore[return-value]


def classify_unreachable(
    subtype: str | None,
    citation_id: str | None,
    evidence_pool_ids: Iterable[str],
) -> str:
    """Split a 'source could not be confirmed' case into UNREACHABLE vs FABRICATED.

    LOCKED PRECEDENCE (I-meta-002 iter-2 P1-b) — fabricated identity wins FIRST:
      (1) if `citation_id` is None/empty OR `citation_id` is NOT in `evidence_pool_ids`
          -> FABRICATED, regardless of `subtype`. A fabricated/unknown citation identity
          must NOT be laundered as a fetch failure.
      (2) ELSE if `subtype` in {paywall, robots, fetch_failure} -> UNREACHABLE.

    `evidence_pool_ids` contract: it is the set of CANONICAL PRE-FETCH evidence IDs — every
    source the pipeline selected/attempted, INCLUDING records whose fetch later FAILED
    (paywall/robots/fetch_failure). A genuine fetch failure therefore still has its
    `citation_id` present in the pool -> correctly UNREACHABLE; only an id that was never a
    selected source -> FABRICATED.

    Anything else (an in-pool id whose subtype is not a known fetch-miss, e.g.
    `source_missing`/None/unknown) is OUT of this contract's domain and is a programming
    error, so it raises rather than silently defaulting (LAW II fail-loud).
    """
    pool = set(evidence_pool_ids)
    # (1) fabricated identity check — evaluated BEFORE the subtype branch.
    if not citation_id or citation_id not in pool:
        return _CLASS_FABRICATED
    # (2) in-pool id: a real fetch miss is UNREACHABLE.
    if subtype in _FETCH_MISS_SUBTYPES:
        return _CLASS_UNREACHABLE
    raise ValueError(
        f"classify_unreachable: in-pool citation {citation_id!r} with subtype {subtype!r} "
        f"is outside the fetch-miss contract domain {_FETCH_MISS_SUBTYPES}"
    )
