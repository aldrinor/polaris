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

import json
import re
from enum import Enum
from typing import Any, NamedTuple


class SentinelVerdict(Enum):
    """Groundedness verdict for one Sentinel score."""

    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"


class SentinelResult(NamedTuple):
    """Result of parsing one Sentinel `<score>` output.

    Returned on EVERY path. `parsed_ok` is True only on a clean, unambiguous parse;
    on any malformed/missing/ambiguous input it is False and `verdict` is forced to the
    safe (UNGROUNDED) side so the caller can escalate rather than trust a bad score.

    `atoms` (F05, GH #1254) carries the per-atom DECOMPOSITION detail — the model's own
    `[{atom, type, status, why}, ...]` list — when the decomposition parser produced one,
    else None. It is an APPENDED OPTIONAL field with a `None` default so the two non-
    decomposition parsers and EVERY positional `SentinelResult(verdict, parsed_ok)` call
    site stay byte-identical. It is READ-ONLY metadata threaded into the Judge prompt so the
    terminal arbiter sees the Sentinel's per-atom "why" (not just the compressed
    grounded/ungrounded token) and cannot rubber-stamp a doc-level "unsupported" without a
    per-atom span-grounded rebuttal. It NEVER feeds a verdict decision — `verdict`/`parsed_ok`
    are computed exactly as before, so no composition or override behaviour changes.
    """

    verdict: SentinelVerdict
    parsed_ok: bool
    atoms: list[dict[str, Any]] | None = None


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


# === DECOMPOSITION (certified MiniMax-M2) groundedness parser (I-run11-004) ===================
# WHY a THIRD parser: the broken Granite Guardian Sentinel was replaced with the CERTIFIED
# MiniMax-M2 claim-DECOMPOSITION detector. On the 56-item fixture (28 grounded + 28 fabricated
# across NUMBER_SWAP / ENTITY_SWAP / NEGATION / FABRICATED_ATTRIBUTION / SCOPE_INFLATION) the
# certified prompt+parse scored 0 false-accepts on all 28 fabrications and over-flag 0.107. The
# certified call returns STRICT JSON {verdict: "supported"|"unsupported", unsupported_atoms, atoms}
# (scripts/diagnostics/sentinel_bakeoff.py: GLM_PROMPT + _strip_json + run_glm_decomposition).
#
# This parser PORTS the certified `_strip_json` robust extraction (strip ```json fences, json.loads,
# largest {...} span, trailing-comma repair) and maps the certified verdict to the SentinelResult:
#     "supported"   -> GROUNDED,   parsed_ok=True
#     "unsupported" -> UNGROUNDED,  parsed_ok=True
# It preserves the LETHAL fail-closed property identical to the other two parsers: ANY parse
# failure, a missing verdict, an off-enum verdict, or a non-string input -> UNGROUNDED,
# parsed_ok=False. There is NO code path that returns GROUNDED on bad input — an unverifiable
# claim is HELD, never released (§-1.1 clinical-safety).


def _strip_json(text: str) -> dict:
    """Robust JSON extraction from a frontier-LLM response (ported VERBATIM-in-behavior from
    scripts/diagnostics/sentinel_bakeoff.py `_strip_json`, the CERTIFIED harness).

    Frontier models wrap JSON in markdown fences, prepend reasoning text, or emit trailing commas.
    A brittle `json.loads` crashes on one such reply. This handles: fenced ```json blocks, reasoning
    prefixes/suffixes (largest {...} span), and trailing commas. Raises ValueError when NO parseable
    JSON object is present (the caller maps that to a fail-closed UNGROUNDED).
    """
    if not isinstance(text, str):
        raise ValueError(f"non-string response: {type(text).__name__}")
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        block = s[start:end + 1]
        for attempt in (block, re.sub(r",(\s*[}\]])", r"\1", block)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no parseable JSON object in response: {text[:200]!r}")


# The two valid decomposition verdict tokens and their groundedness mapping (LOCKED, certified).
_DECOMPOSITION_VERDICT_SUPPORTED = "supported"
_DECOMPOSITION_VERDICT_UNSUPPORTED = "unsupported"
_DECOMPOSITION_VERDICT_TO_VERDICT = {
    _DECOMPOSITION_VERDICT_SUPPORTED: SentinelVerdict.GROUNDED,
    _DECOMPOSITION_VERDICT_UNSUPPORTED: SentinelVerdict.UNGROUNDED,
}


def parse_sentinel_decomposition(raw: str) -> SentinelResult:
    """Parse a CERTIFIED MiniMax-M2 DECOMPOSITION output (JSON) into a SentinelResult (I-run11-004).

    The certified output is STRICT JSON {"verdict": "supported"|"unsupported", "unsupported_atoms":
    <int>, "atoms": [...]}. Mapping (LOCKED): "supported" -> GROUNDED, "unsupported" -> UNGROUNDED.

    FAIL CLOSED (lethal-inversion guard, identical safety to the other two parsers): ANY of —
      - non-string input,
      - unparseable JSON (after the robust `_strip_json` fence/prefix/trailing-comma handling),
      - a missing `verdict` key,
      - an off-enum verdict (anything other than the exact tokens "supported"/"unsupported"),
      - a "supported" verdict that OMITS the decomposition contract — no non-empty `atoms` list
        (with >=1 atom object) OR no `unsupported_atoms` field (Codex brief-gate P1: a bare/
        truncated/non-atomized "supported" did no per-atom work and must not release),
    yields UNGROUNDED with parsed_ok=False. There is NO path that returns GROUNDED on bad input.
    `parsed_ok=True` is reserved for a clean JSON object carrying a recognized verdict AND, for
    "supported", the full decomposition contract (non-empty atoms + unsupported_atoms count == 0,
    every atom supported).
    """
    if not isinstance(raw, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    try:
        parsed = _strip_json(raw)
    except ValueError:
        # Unparseable / no JSON object -> fail CLOSED (clinical-safe: hold, never release).
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    if not isinstance(parsed, dict):
        # A bare JSON array / scalar carries no verdict -> fail CLOSED.
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    verdict_token = parsed.get("verdict")
    if not isinstance(verdict_token, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    verdict = _DECOMPOSITION_VERDICT_TO_VERDICT.get(verdict_token.strip().lower())
    if verdict is None:
        # Missing/odd/off-enum verdict -> fail CLOSED (never a silent GROUNDED).
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    # F05 (GH #1254): carry the model's per-atom decomposition list through to the result so the
    # Judge prompt can show the per-atom "why" (NOT just the compressed grounded/ungrounded token).
    # This is READ-ONLY metadata — it does NOT participate in the verdict/parsed_ok decision below,
    # which is computed byte-for-byte as before. `_atom_list` is the model's `atoms` list iff it is a
    # list of atom dicts, else None (so a malformed/absent atoms field never threads garbage). Every
    # `parsed_ok=True` return below carries it; the contract-fail (`parsed_ok=False`) returns above
    # already returned and carry None (a failed parse has no trustworthy atom detail to surface).
    _raw_atoms = parsed.get("atoms")
    _atom_list: list[dict[str, Any]] | None = (
        [a for a in _raw_atoms if isinstance(a, dict)]
        if isinstance(_raw_atoms, list) and any(isinstance(a, dict) for a in _raw_atoms)
        else None
    )
    # SAFETY cross-check (Codex diff-gate iter-3 P1): a top-level "supported" verdict that
    # SIMULTANEOUSLY reports unsupported atoms is an INTERNALLY CONTRADICTORY output. Trusting the
    # top-level "supported" there is a fail-OPEN path — a fabricated claim laundered to VERIFIED.
    # When the verdict is GROUNDED but the model's OWN atom analysis flags any unsupported
    # sub-assertion (unsupported_atoms > 0, or an atom whose status is "unsupported"), VETO to
    # UNGROUNDED — the clinical-safe side. The atom analysis OVERRIDES an over-confident top verdict.
    if verdict is SentinelVerdict.GROUNDED:
        # CONTRACT GATE (Codex BRIEF-gate P1 fail-open fix): the certified decomposition output is
        # STRICT JSON {verdict, unsupported_atoms, atoms}. A top-level "supported" verdict that OMITS
        # the decomposition — no non-empty `atoms` list (with >=1 atom object), or no
        # `unsupported_atoms` field — is a non-atomized / truncated / lazy answer that did NOT do the
        # per-atom span-coverage work. Trusting it as GROUNDED is a fail-OPEN: a bare
        # {"verdict":"supported"} could release a fabricated claim if the Judge verifies. FAIL CLOSED
        # (parsed_ok=False: the output did not meet the decomposition contract). Validated against the
        # certification cache: all 25 real "supported" outputs carry BOTH a non-empty atoms list AND
        # unsupported_atoms, so this contract gate has ZERO false-drops on the real model.
        atoms = parsed.get("atoms")
        has_atoms = isinstance(atoms, list) and any(isinstance(a, dict) for a in atoms)
        if not has_atoms or "unsupported_atoms" not in parsed:
            return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
        # Robustly coerce unsupported_atoms (Codex diff-gate iter-4 P1 + iter-5 P1). A JSON-mode model
        # can QUOTE the number ("unsupported_atoms": "1"), emit a bool (true/false), null, or a list —
        # a bare numeric check would FAIL OPEN. The field is REQUIRED (contract gate above); a value is
        # released ONLY if it coerces to a CLEAN ZERO; anything else (>0, fractional, bool, null,
        # non-numeric) VETOES to UNGROUNDED.
        raw_count = parsed["unsupported_atoms"]
        count: float | None
        if isinstance(raw_count, bool):
            count = None  # a JSON bool is not a count -> present-but-invalid
        elif isinstance(raw_count, (int, float)):
            count = raw_count
        elif isinstance(raw_count, str):
            token = raw_count.strip()
            try:
                count = int(token)
            except ValueError:
                try:
                    count = float(token)
                except ValueError:
                    count = None
        else:
            count = None  # null (None), list, dict, ... -> present-but-invalid
        if count is None or count != 0:
            return SentinelResult(
                SentinelVerdict.UNGROUNDED, parsed_ok=True, atoms=_atom_list
            )
        # atoms is a non-empty list with >=1 atom object (contract gate): veto if ANY atom is unsupported.
        for atom in atoms:
            if not isinstance(atom, dict):
                continue
            status = atom.get("status") or atom.get("verdict")
            if isinstance(status, str) and status.strip().lower() == "unsupported":
                return SentinelResult(
                    SentinelVerdict.UNGROUNDED, parsed_ok=True, atoms=_atom_list
                )
            if atom.get("supported") is False:
                return SentinelResult(
                    SentinelVerdict.UNGROUNDED, parsed_ok=True, atoms=_atom_list
                )
    return SentinelResult(verdict, parsed_ok=True, atoms=_atom_list)
