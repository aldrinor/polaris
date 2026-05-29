"""Sentinel (IBM Granite Guardian 4.1) groundedness contract — FAIL CLOSED.

Granite Guardian groundedness polarity (primary source: ibm.com/granite/docs/models/guardian,
confirmed in I-meta-002 iter-2 verdict F3):
    output is `<score>yes|no</score>` (NOT JSON), where
      yes = risk present       -> the answer is UNGROUNDED
      no  = risk not present    -> the answer is GROUNDED

This is the LETHAL inversion guard. The two failure modes that hurt patients are:
  (1) silently reading `yes` as GROUNDED (polarity inversion), and
  (2) silently defaulting an unparseable/missing/ambiguous output to GROUNDED.
Both are prevented here: the polarity is hard-coded yes->UNGROUNDED, and EVERY
non-clean parse falls to the safe side (UNGROUNDED) with parsed_ok=False so the
caller can escalate. There is NO code path that returns GROUNDED on bad input.

Contrast with `entailment_judge.py`, which fails OPEN on transient error; Sentinel
deliberately fails CLOSED, so it is a SEPARATE contract, not a reuse.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class SentinelVerdict(Enum):
    """Groundedness verdict for one Sentinel score."""

    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"


class SentinelResult(NamedTuple):
    """Result of parsing one Sentinel `<score>` output.

    Returned on EVERY path. `parsed_ok` is True only on a clean, unambiguous parse;
    on any malformed/missing/ambiguous input it is False and `verdict` is forced to the
    safe (UNGROUNDED) side so the caller can escalate rather than trust a bad score.
    """

    verdict: SentinelVerdict
    parsed_ok: bool


# The canonical Granite Guardian score tokens (LOCKED polarity, F3).
_SCORE_TOKEN_YES = "yes"
_SCORE_TOKEN_NO = "no"

# Map the canonical score token to its groundedness verdict. yes=risk=UNGROUNDED.
_SCORE_TOKEN_TO_VERDICT = {
    _SCORE_TOKEN_YES: SentinelVerdict.UNGROUNDED,
    _SCORE_TOKEN_NO: SentinelVerdict.GROUNDED,
}

# STRICT ENVELOPE: the WHOLE output must be exactly one `<score>yes|no</score>` element,
# with only surrounding whitespace allowed (and inner whitespace around the token). We
# `fullmatch` the entire raw string, so ANY surrounding prose, a second (even malformed)
# score tag, stray markup, or an off-enum body fails the match and falls to the safe side.
# This single anchored rule subsumes the weaker "count the matches/tags" guards (which let
# `<score>no</score><score>maybe` and `prefix <score>no</score> suffix` slip through as a
# silent GROUNDED — Codex sub-PR-2 diff P0 iter-1/iter-2 + P1 iter-3). The token group is
# constrained to yes|no so a clean match can never carry an off-enum body.
#
# NOTE for PR4 (adapter): if the SERVED Granite Guardian build emits an additional token
# (e.g. a trailing `<confidence>...` line) alongside the score, this contract must be
# EXTENDED with that exact verified format — never loosened to "tag present anywhere".
# `re.ASCII` is REQUIRED alongside IGNORECASE: without it, Unicode case-folding accepts
# homoglyphs like U+017F LONG S ('ſ') as 's', so `<ſcore>no</ſcore>` would match and return
# a silent GROUNDED (Codex sub-PR-2 diff P1 iter-4). ASCII mode folds only a-z/A-Z and limits
# `\s` to ASCII whitespace, so the envelope must be the verified ASCII `<score>yes|no</score>`.
_STRICT_SCORE_RE = re.compile(
    r"\s*<score>\s*(yes|no)\s*</score>\s*", re.IGNORECASE | re.ASCII
)


def parse_sentinel_score(raw: str) -> SentinelResult:
    """Parse a raw Granite Guardian groundedness output into a SentinelResult.

    Mapping (LOCKED, F3): `<score>yes</score>` -> UNGROUNDED, `<score>no</score>` -> GROUNDED.
    Case- and whitespace-tolerant.

    FAIL CLOSED: any output that is not EXACTLY one `<score>yes|no</score>` element
    (surrounding whitespace aside) -> UNGROUNDED with parsed_ok=False. NEVER returns
    GROUNDED on bad input. Surrounding prose, a second/partial score tag, off-enum body,
    missing tag, or non-string are ALL treated as failed parses, not best-effort guesses.
    parsed_ok=True is reserved for a single clean score envelope.
    """
    if not isinstance(raw, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)

    # Anchor on the WHOLE output. fullmatch fails on any prefix/suffix/extra/partial markup,
    # so the only parsed_ok=True paths are a lone `<score>yes</score>` or `<score>no</score>`.
    match = _STRICT_SCORE_RE.fullmatch(raw)
    if match is None:
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)

    token = match.group(1).lower()
    verdict = _SCORE_TOKEN_TO_VERDICT.get(token)
    if verdict is None:
        # Defensive: the regex constrains the group to yes|no, so this is unreachable;
        # keep the fail-closed branch so a future regex change cannot leak GROUNDED.
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)

    return SentinelResult(verdict, parsed_ok=True)
