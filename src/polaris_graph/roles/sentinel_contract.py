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

    This is the INVERTED (yes=risk) Guardian contract — it stays the SOVEREIGN self-host
    path's parser (the task-trained `granite-guardian-4.1-8b` honors yes=risk). The benchmark
    OpenRouter path uses `parse_sentinel_grounded_token` instead (I-run11-002 L1).
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


# === NON-INVERTED (benchmark) groundedness parser (I-run11-002 L1) ===========================
# WHY a SECOND parser: run 11 proved the general `ibm-granite/granite-4.1-8b` (the OpenRouter
# benchmark Sentinel) IGNORES the inverted Guardian instruction and answers the NATURAL question,
# so the yes=risk contract above mislabels every grounded claim as UNGROUNDED (the run-11 wipeout,
# outputs/audits/I-run11-002/l1_groundedness_probe.md). The non-inverted prompt asks the model to
# emit one word — GROUNDED or UNGROUNDED — directly. This parser reads THAT.
#
# It is NOT a polarity flip of the inverted parser (a flip would false-accept fabricated claims —
# §-1.1 clinically lethal). It is a SEPARATE contract over a DIFFERENT prompt's output. The
# polarity is direct (GROUNDED -> GROUNDED, UNGROUNDED -> UNGROUNDED), and EVERY ambiguous output
# (both tokens, neither token, a repeated token, a non-string) fails CLOSED to UNGROUNDED with
# parsed_ok=False — never a silent GROUNDED, identical to the inverted parser's safety property.
#
# Word-boundary count (NOT substring): `\bgrounded\b` does NOT match inside "ungrounded" (no left
# word boundary before the 'g'), so a clean `UNGROUNDED` yields grounded_count=0, ungrounded_count=1
# -> UNGROUNDED. `re.ASCII` reuses the inverted parser's homoglyph defense (Unicode case-folding
# under bare IGNORECASE would accept homoglyphs like U+017F LONG S).
#
# STRICT WHOLE-OUTPUT grammar (Codex diff-gate P1, no-false-accept): the ENTIRE response, after
# stripping surrounding whitespace, must be EXACTLY `GROUNDED` or `UNGROUNDED` with at most a single
# trailing period. A word-boundary COUNT was REJECTED because it false-accepts negated prose — e.g.
# "not grounded" / "The claim is not grounded." would count one standalone `grounded`, zero
# `ungrounded` -> a WRONG GROUNDED parsed_ok=True (a genuinely-ungrounded claim laundered to
# VERIFIED, §-1.1 clinically lethal). With the anchored full match, "not grounded", "grounded: no",
# "not fully grounded", and any prose all FAIL the match and fall CLOSED to UNGROUNDED (also the
# correct verdict for a "not grounded" answer). Trailing-period tolerance keeps the common
# "GROUNDED." case clean. `^\s*grounded\s*\.?\s*$` does NOT match "ungrounded" (the `un` prefix
# breaks the start anchor), so the substring trap cannot mis-fire.
_GROUNDED_FULL_RE = re.compile(r"^\s*grounded\s*\.?\s*$", re.IGNORECASE | re.ASCII)
_UNGROUNDED_FULL_RE = re.compile(r"^\s*ungrounded\s*\.?\s*$", re.IGNORECASE | re.ASCII)


def parse_sentinel_grounded_token(raw: str) -> SentinelResult:
    """Parse a NON-INVERTED groundedness output (one word: GROUNDED | UNGROUNDED) -> SentinelResult.

    Direct polarity (I-run11-002 L1, validated on `ibm-granite/granite-4.1-8b`), STRICT whole-output:
        whole output == `UNGROUNDED` (optional trailing `.`) -> UNGROUNDED, parsed_ok=True
        whole output == `GROUNDED`   (optional trailing `.`) -> GROUNDED,  parsed_ok=True

    FAIL CLOSED to UNGROUNDED (never a silent GROUNDED) on ANYTHING else — negated/prose output
    ("not grounded", "grounded: no", "not fully grounded"), extra tokens, both/neither token, a
    repeated token, or non-string input.
    """
    if not isinstance(raw, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)

    # UNGROUNDED checked first (mutually exclusive under full anchoring; order-safe regardless).
    if _UNGROUNDED_FULL_RE.match(raw):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True)
    if _GROUNDED_FULL_RE.match(raw):
        return SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
    # Negated prose, extra tokens, both/neither, repeats, non-clean output -> fail CLOSED.
    return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
