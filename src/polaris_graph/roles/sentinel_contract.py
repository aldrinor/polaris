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
import os
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


# === F06 (P1, GH I-arch-004) ATOM-COVERAGE COMPLETENESS CROSS-CHECK ============================
# WHY this exists: `parse_sentinel_decomposition` (above) gates a GROUNDED ("supported") verdict on
# the model's OWN atom bookkeeping — a non-empty `atoms` list, `unsupported_atoms == 0`, and no
# per-atom "unsupported" status. But it NEVER verifies that the atom set actually COVERS every
# assertion in the cited sentence. A half-decomposed clinical claim — e.g. an efficacy clause that
# IS atomized + supported, with a SECOND contraindication/safety clause the model silently dropped
# (never atomized, never checked) — therefore passes as GROUNDED. The dropped clause carries the
# clinical risk (a missed contraindication is §-1.1 lethal), yet no atom ever examined it.
#
# This is an INDEPENDENT cross-check: the clauses are derived FROM THE CITED SENTENCE (not from the
# model's verdict or its atom list), then each substantive clause is required to be REPRESENTED by
# at least one atom. If a substantive clause has no covering atom, the decomposition is INCOMPLETE
# and the claim is treated as UNGROUNDED (STRICTER — it can only DOWNGRADE a GROUNDED to UNGROUNDED,
# never the reverse). It STRENGTHENS the faithfulness gate; it can never relax it.
#
# FLAG (F05 precedent, judge_adapter._sentinel_atoms_enabled): default OFF -> byte-identical (the
# caller never runs this), enabled by the Gate-B / cert run slate so the strengthened behavior is
# the cert-slate default without churning the locked offline suite. Read at call time so one process
# can exercise both states in tests (mirrors the rubric/atoms flags).
_ATOM_COVERAGE_FLAG = "PG_SENTINEL_ATOM_COVERAGE"

# Coverage tuning (LAW VI / §9.4: named constants, never inline magic numbers):
#  - _ATOM_COVERAGE_MAX_DISTINCTIVE_MISSES: the incidental-word tolerance for a MULTI-WORD clause.
#    Coverage checks each clause's DISTINCTIVE content words (its own words minus the claim's common
#    backbone — see `_distinctive_words`); a MULTI-word clause is covered iff at most this many of its
#    distinctive words are absent from the union of all atom texts. The tolerance (>0) is REQUIRED so a
#    faithful atom that drops ONE incidental word ("...in the trial") does not false-drop a legit
#    multi-word clause. It applies ONLY to multi-word clauses (see `_allowed_misses`): a SINGLE-
#    distinctive-word clause gets ZERO tolerance, so its lone assertion ("contraindicated") must be
#    covered — Codex diff-gate iter-2 P1: a flat tolerance of 1 waived any size-1 distinctive clause,
#    re-opening the dropped one-word-contraindication risk.
#  - _MIN_CLAUSE_CONTENT_WORDS: a clause must carry at least this many content words to be checkable.
#    Set to 1 (Codex iter-2 P1): a one-content-word safety predicate ("is contraindicated") is a real
#    assertion that must be covered, not skipped. Only a 0-content-word fragment (bare numeral, pure
#    function words) is non-substantive and waived.
#  - _BACKBONE_MIN_CLAUSE_COUNT: a content word is "backbone" (the shared drug/population subject) iff
#    it appears in at least this many clauses; backbone words are discounted from a clause's
#    distinctive set so a repeated subject term cannot launder a dropped predicate.
_ATOM_COVERAGE_MAX_DISTINCTIVE_MISSES = 1
_MIN_CLAUSE_CONTENT_WORDS = 1
_BACKBONE_MIN_CLAUSE_COUNT = 2
# A single-distinctive-word clause carries its whole assertion in that one word -> ZERO tolerance.
_SINGLE_DISTINCTIVE_WORD = 1

# Content-word tokenizer for the cross-check. Kept LOCAL (self-contained, no clinical_generator /
# strict_verify import from the roles package) but the stoplist + ">=3 chars, drop stopwords" rule
# mirror strict_verify._content_words so coverage counts the SAME substantive vocabulary the rest of
# the faithfulness engine does. The connective/contrastive words that START a new clause are folded
# into the stoplist so they never count as the lone "shared" word.
_COVERAGE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")
_COVERAGE_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "with", "as", "by", "from", "into", "through", "during",
    "before", "after", "above", "below", "between", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "should", "could", "may",
    "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "their", "there", "they", "them", "we", "us", "our", "you",
    "your", "i", "me", "my", "he", "she", "his", "her",
    # contrastive / subordinating connectives that introduce a SEPARATE clause (split markers below):
    "however", "although", "though", "whereas", "while", "despite", "except", "yet", "not",
})

# Intra-sentence CONTRASTIVE/SUBORDINATING clause markers. The decimal-aware SENTENCE boundary
# (lazy-imported from claim_atom_extractor, the read-only cross-check tool) splits on `. ; ! ?` /
# newlines without cutting decimals; these connectives additionally split a single sentence into its
# constituent clauses so a "X works, BUT it is contraindicated in Y" claim yields TWO clauses to
# cover — the contraindication clause cannot hide inside the efficacy sentence. Matched
# case-insensitively as whole words.
_CLAUSE_CONNECTIVE_RE = re.compile(
    r"\b(?:however|although|though|whereas|while|despite|except|but|yet)\b",
    re.IGNORECASE,
)

# Codex diff-gate iter-1 P1.2: coordinating "and"/"or" must split COORDINATED PREDICATES so
# "Drug reduced HbA1c and is contraindicated in pancreatitis" yields two clauses — otherwise the
# dropped contraindication conjunct hides in one clause and the efficacy atom covers it. But naive
# and/or splitting RE-BREAKS numeric lists ("5 mg, 10 mg, and 15 mg") and noun coordinations
# ("HbA1c and body weight"). CONSTRAINT: split at " and "/" or " ONLY when the following conjunct
# opens with a finite PREDICATE verb (is/are/was/were/has/have/had/showed/reduced/increased/...). A
# noun/numeric conjunct ("15 mg in the trial") carries no leading finite verb and is NOT split. This
# discriminates clausal-and (split) from noun/numeric-and (keep) without a comma split.
_PREDICATE_AND_OR_RE = re.compile(
    r"\s+(?:and|or)\s+(?="
    r"(?:is|are|was|were|has|have|had|"
    r"shows?|showed|demonstrat\w*|reduc\w*|increas\w*|decreas\w*|lower\w*|rais\w*|"
    r"caus\w*|le[ad]\w*|result\w*|associat\w*|improv\w*|worsen\w*|"
    r"remain\w*|appear\w*|prevent\w*|induc\w*|inhibit\w*|"
    r"is\s+contraindicat\w*|contraindicat\w*|"
    r"may|can|should|must|might|will|would)"
    r"\b)",
    re.IGNORECASE,
)


def sentinel_atom_coverage_enabled() -> bool:
    """True iff the F06 atom-coverage completeness cross-check is enabled (read at call time).

    Default OFF: the locked decomposition behavior stays byte-identical until the cert run slate
    turns it on (F05 precedent). Read here (not at import) so a single process can exercise both
    flag states in tests.
    """
    return os.getenv(_ATOM_COVERAGE_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _coverage_content_words(text: str) -> set[str]:
    """Lowercase content words (>=3 chars, not stopwords/connectives) from `text` (F06).

    Mirrors strict_verify._content_words so the cross-check counts the SAME substantive vocabulary
    the faithfulness engine uses. Non-string / empty -> empty set (the caller treats a clause with
    too few content words as non-substantive and skips it)."""
    if not isinstance(text, str):
        return set()
    return {
        m.group(0).lower()
        for m in _COVERAGE_WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _COVERAGE_STOPWORDS
    }


def _split_claim_clauses(claim: str) -> list[str]:
    """Split a claim sentence into its constituent clauses (F06, independent of the model).

    Three-stage split, decimal-safe: (1) the decimal-aware SENTENCE boundary regex lazy-imported from
    `claim_atom_extractor` (the spec's read-only cross-check tool) cuts on `. ; ! ?` / newlines
    WITHOUT splitting decimals like `8.21`; (2) each sentence is further split on the contrastive /
    subordinating CONNECTIVES (`_CLAUSE_CONNECTIVE_RE`) so intra-sentence clauses (the "...BUT
    contraindicated in..." tail) become their own clause; (3) each piece is split on COORDINATING
    "and"/"or" that introduce a PREDICATE conjunct (`_PREDICATE_AND_OR_RE`) so "X reduced Y and is
    contraindicated in Z" yields two clauses — but a noun/numeric "and" ("5 mg, 10 mg, and 15 mg")
    is left intact. Returns the non-empty trimmed clause strings; an empty/non-string claim yields []."""
    if not isinstance(claim, str) or not claim.strip():
        return []
    # Lazy import (anti-coupling, evidence_distiller.py:511-514 precedent): the roles package does not
    # import the generator package at module load. The regex is READ-ONLY (used only to .split()).
    from src.polaris_graph.generator.claim_atom_extractor import _SENTENCE_BOUNDARY_RE

    clauses: list[str] = []
    for sentence in _SENTENCE_BOUNDARY_RE.split(claim):
        if not sentence or not sentence.strip():
            continue
        for connective_piece in _CLAUSE_CONNECTIVE_RE.split(sentence):
            if not connective_piece or not connective_piece.strip():
                continue
            # Split coordinating predicate-bearing and/or (Codex iter-1 P1.2); numeric/noun and/or
            # (no leading finite verb) is NOT matched and stays one clause.
            for clause in _PREDICATE_AND_OR_RE.split(connective_piece):
                if clause and clause.strip():
                    clauses.append(clause.strip())
    return clauses


def _distinctive_words(clause_words: set[str], all_clause_word_sets: list[set[str]]) -> set[str]:
    """The clause's DISTINCTIVE content words: its own words minus the claim's BACKBONE (Codex iter-1
    P1.1). A word is backbone iff it appears in >= `_BACKBONE_MIN_CLAUSE_COUNT` clauses — that is the
    shared drug/population SUBJECT ("tirzepatide", "patients") every clause repeats. Discounting the
    backbone means a dropped clause that merely echoes the subject cannot be laundered as covered by
    another clause's atom; only the clause's OWN predicate content ("contraindicated", "pancreatitis")
    can satisfy coverage. If a clause is ALL backbone (empty distinctive set), it carries no unique
    assertion and is treated as covered by the caller."""
    backbone = {
        word
        for word in clause_words
        if sum(1 for other in all_clause_word_sets if word in other)
        >= _BACKBONE_MIN_CLAUSE_COUNT
    }
    return clause_words - backbone


def atom_coverage_complete(claim: str, atoms: list[dict[str, Any]] | None) -> bool:
    """Does the Sentinel `atoms` set COVER every substantive assertion in `claim`? (F06 cross-check.)

    INDEPENDENT of the model's verdict: clauses are derived from the CITED SENTENCE (sentence +
    contrastive + predicate-and/or split), then each substantive clause's DISTINCTIVE content words
    (its own words minus the shared drug/population backbone) must appear in the UNION of all atom
    texts. A MULTI-word distinctive clause allows at most `_ATOM_COVERAGE_MAX_DISTINCTIVE_MISSES`
    incidental misses; a SINGLE-distinctive-word clause ("...is contraindicated") allows ZERO — its
    lone assertion must be covered (Codex iter-2 P1). Returns:
      - True  -> every substantive clause is covered (decomposition is complete; do NOT downgrade).
      - False -> at least one substantive clause's distinctive assertion is NOT represented by any
                 atom (a dropped/un-atomized clause; the caller treats this as UNGROUNDED — STRICTER).

    Distinctive-word coverage (Codex iter-1 P1.1) discounts the shared subject so a dropped clause
    cannot pass merely by repeating the drug/population terms of a covered clause. The miss tolerance
    keeps a faithful atom that drops one incidental word ("...in the trial") from false-dropping.

    FAIL-CLOSED on a missing/empty atom set: `atoms` None or carrying no usable atom text, against a
    claim that DOES have a substantive distinctive clause, returns False (no atom did the per-clause
    work). A claim with no substantive distinctive assertion at all (a bare numeral, or all-backbone)
    returns True (nothing unique to cover -> the coverage check adds no constraint; the model's own
    per-atom gate above still applies)."""
    clauses = _split_claim_clauses(claim)
    # Per-clause content-word sets; keep only clauses that carry a checkable assertion.
    clause_word_sets: list[set[str]] = [
        words
        for clause in clauses
        if len(words := _coverage_content_words(clause)) >= _MIN_CLAUSE_CONTENT_WORDS
    ]
    if not clause_word_sets:
        # No checkable assertion in the claim text -> coverage imposes no extra constraint.
        return True

    # Union of all atom texts' content words (join each atom's own contract fields). A model atom that
    # speaks to a clause should contribute that clause's distinctive vocabulary into this union.
    atom_word_union: set[str] = set()
    for atom in atoms or []:
        if not isinstance(atom, dict):
            continue
        atom_text = " ".join(
            str(atom.get(field, "") or "") for field in ("atom", "why", "type")
        )
        atom_word_union |= _coverage_content_words(atom_text)

    for clause_words in clause_word_sets:
        distinctive = _distinctive_words(clause_words, clause_word_sets)
        if not distinctive:
            # All-backbone clause: no unique assertion to cover (redundant subject restatement).
            continue
        # A SINGLE-distinctive-word clause ("...is contraindicated") gets ZERO tolerance: its whole
        # assertion is that one word and must be covered. The incidental-word tolerance applies ONLY
        # to multi-word clauses, where it forgives one dropped incidental word ("...in the trial").
        # Codex diff-gate iter-2 P1: a flat tolerance waived size-1 distinctive clauses.
        allowed_misses = (
            0
            if len(distinctive) == _SINGLE_DISTINCTIVE_WORD
            else _ATOM_COVERAGE_MAX_DISTINCTIVE_MISSES
        )
        misses = len(distinctive - atom_word_union)
        if misses > allowed_misses:
            # The clause's distinctive assertion is NOT represented -> incomplete decomposition.
            return False
    return True
