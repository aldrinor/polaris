"""I-arch-011 #1268 PR-c — per-basket VERIFIED-COMPOSE with basket-id-bound verbatim fallback.

The composition FLOW step 3 ("great writing, verified"): turn each claim BASKET into readable
prose WITHOUT fabricating. For every basket the abstractive WRITER (the existing generator-role
LLM — NO new model) drafts prose carrying ``[#ev:<id>:<a>-<b>]`` provenance tokens; each sentence
is then re-checked by the UNCHANGED deterministic ``strict_verify`` (``verify_sentence_provenance``)
against a BASKET-SCOPED evidence pool. A passing sentence is kept; a FAILING sentence — including
one that cites a DIFFERENT basket's evidence_id (absent from the basket-scoped pool, so it fails
closed — the Codex P1-2 anti-cross-claim contract) — FALLS BACK to THAT BASKET'S OWN verified
K-span (a verbatim quote from one of its isolated-``SUPPORTS`` members). If the basket has no
verified span at all, an honest insufficient-evidence disclosure is emitted. The result is NEVER
empty (the original FIX-K empty-section bug).

FAITHFULNESS (by construction, the crown-jewel rules are untouched):
  * The WRITER only ORGANIZES + PHRASES already-verified spans; it can never license an unsupported
    claim — a fabrication fails ``strict_verify`` and degrades to the verbatim K-span (QUOTATION is
    the only faithful-BY-CONSTRUCTION form — survey arXiv:2508.15396).
  * ``strict_verify`` / NLI / 4-role / provenance are UNCHANGED; this module calls the production
    single-sentence verifier as-is and consumes its binary verdict — it adds NO gate, relaxes none.
  * The verbatim fallback is BASKET-ID-BOUND: a failed sentence can fall back ONLY to its own
    basket's verified span, never another basket's (P1-2). Enforced by scoping the verify pool AND
    the fallback span to the basket's own members.
  * Deterministic: the fallback K-span + sentence split are pure; only the writer is an LLM call,
    and it is the EXISTING generator-role invocation (governed by polaris_runtime_lock.yaml exactly
    like every other generation). NO new model, NO new slug, NO new resolver.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Optional

# The section heading the verified-compose body renders under when it is the PRIMARY producer.
# (Re-exported from multi_section_generator so the harness + callers share one constant.)
_ENRICHMENT_TITLE = "Corroborated Findings"

_VERIFIED_COMPOSE_ENV = "PG_VERIFIED_COMPOSE"

# I-beatboth-002 Fix 1 (F1-1) — multi-cited verified synthesis. Default-OFF (LAW VI): when this
# flag is unset/off the module is byte-identical to the single-basket per-basket producer above;
# ON, the caller MAY co-locate per-member-verified clauses from N corroborating baskets into ONE
# multi-cited synthesized sentence. The faithfulness contract is UNCHANGED — see
# ``compose_multicited_sentence`` for the per-clause (NOT whole-sentence) verify invariant.
_MULTICITED_COMPOSE_ENV = "PG_VERIFIED_COMPOSE_MULTICITED"

# I-deepfix-001 M6 — verified CROSS-SOURCE analytical synthesis. Default-OFF (LAW VI): when unset/off the
# section producer is byte-identical (no import, no call); ON, an ADDITIVE pass appends analytical
# sentences (two verified atoms joined by an engine-LICENSED connective) on top of the keep-all
# single-source units. The faithfulness engine is never touched — see ``cross_source_synthesis``.
_CROSS_SOURCE_SYNTHESIS_ENV = "PG_CROSS_SOURCE_SYNTHESIS"

# A provenance token: ``[#ev:<evidence_id>:<start>-<end>]`` (the same shape strict_verify parses).
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
# Resolved-span grammar for idx8 seen-span dedup: parse the ``(evidence_id, start, end)`` identity out
# of every provenance token so a byte-identical re-emission of the same span can be detected and dropped
# (faithfulness-neutral — same resolved span, no new claim).
_EV_SPAN_RE = re.compile(r"\[#ev:(?P<ev_id>[A-Za-z0-9_]+):(?P<start>\d+)-(?P<end>\d+)\]")


def _resolved_spans(text: str) -> set[tuple[str, int, int]]:
    """The distinct resolved (evidence_id, start, end) provenance tuples a composed unit carries.

    Empty set for a unit with no ``[#ev:...]`` token (such a unit is NEVER a seen-span drop candidate —
    zero tokens must not be a vacuous "all duplicate"). Identity is the RESOLVED span (ev_id+offsets),
    so it is stable under both the stub and the real writer (both emit the same token grammar)."""
    spans: set[tuple[str, int, int]] = set()
    for m in _EV_SPAN_RE.finditer(text or ""):
        try:
            spans.add((m.group("ev_id"), int(m.group("start")), int(m.group("end"))))
        except (ValueError, TypeError):
            continue
    return spans


# I-arch-011 #1269 B11 (compose-repetition) — a number-token signature for the carve-out below.
# Standalone integers / decimals (incl. a %/$ neighbour), used ONLY to decide whether a same-span
# restatement adds a NEW statistic (it survives) or is a pure reword (it collapses). Conservative:
# a single shared 800-char span can carry >1 distinct statistic, so a sentence that introduces a
# number absent from its kept same-footprint siblings is KEPT — never dropped as "duplicate".
_NUMBER_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _number_tokens(text: str) -> frozenset[str]:
    """The distinct number tokens in ``text`` AFTER stripping every ``[#ev:...]`` provenance token
    (so the span offsets in the token never count as content numbers). Empty for non-numeric prose."""
    stripped = _EV_TOKEN_RE.sub(" ", text or "")
    return frozenset(m.group(0) for m in _NUMBER_TOKEN_RE.finditer(stripped))


def dedup_same_span_sentences(sentences: list) -> tuple[list, list]:
    """I-arch-011 #1269 B11 — collapse degenerate same-span restatements to ONE rendering per
    distinct resolved-span FOOTPRINT (the (ev_id,start,end) SET a sentence cites), keep-FIRST.

    THE DEFECT this fixes: the legacy section producer emitted ONE verified span (e.g.
    ``brynjolfsson_genai_at_work:0-800``) as 18 near-identical sentences — 18x the SAME footprint,
    zero added breadth (canary autopsy B11 / §-1.1 DO_NOT_SHIP). The §-1.3 reading: repetition of the
    SAME span is NOT corroboration; corroboration is DISTINCT works (distinct ev_ids). This pass keeps
    one sentence per distinct footprint so breadth comes from distinct works, not from re-citing one
    span N times.

    FAITHFULNESS (by construction): every dropped sentence cites a footprint already emitted by a
    KEPT sibling — it is an already-strict_verify-PASSED restatement of an already-rendered span, so
    removing it can never drop a claim that is not still present, and it NEVER touches strict_verify /
    NLI / 4-role / span-grounding (it runs AFTER them, on the kept list). It is CONSOLIDATE-keep-one,
    NOT a cap/thinner/target — there is no fixed N; the bound is content identity (one per footprint).

    DISTINCT-WORK SAFETY: a different ev_id => a different footprint => never collapsed. Multi-source
    corroborators (NBER ev_228 + MIT ev_224, etc.) carry DIFFERENT ev_ids and can never be merged or
    dropped by this pass — it only ever collapses re-citations of the IDENTICAL span set.

    NUMBER CARVE-OUT (conservative, advisor 2026-06-21): a same-footprint sentence that introduces a
    number token absent from ALL its kept same-footprint siblings is KEPT (a single 800-char span can
    state >1 statistic; do not lose a genuine second number). A pure reword (no new number) collapses.

    Order-preserving, pure. A sentence with NO provenance token is NEVER a duplicate candidate (zero
    footprint must not be vacuously "all duplicate") — it is always kept. ``sentences`` may be any
    objects exposing a ``.sentence`` str (the production SentenceVerification) OR plain strings.

    Returns ``(kept, dropped)`` — ``kept`` is the deduped list in input order; ``dropped`` is the
    collapsed redundant objects (the caller routes them into the existing dedup-redundant telemetry)."""
    kept: list = []
    dropped: list = []
    # footprint (frozenset of (ev_id,start,end)) -> union of number tokens already KEPT for it.
    seen_numbers_by_footprint: dict[frozenset, frozenset[str]] = {}
    for sv in (sentences or []):
        text = sv if isinstance(sv, str) else str(getattr(sv, "sentence", "") or "")
        footprint = frozenset(_resolved_spans(text))
        if not footprint:
            kept.append(sv)  # no provenance token -> never a same-span duplicate
            continue
        nums = _number_tokens(text)
        if footprint not in seen_numbers_by_footprint:
            # First sentence for this footprint — always keep; seed its number set.
            seen_numbers_by_footprint[footprint] = nums
            kept.append(sv)
            continue
        # A later sentence on the SAME footprint: keep ONLY if it adds a number absent from every
        # kept sibling on this footprint (a genuinely new statistic inside the shared span); else it
        # is a pure reword of an already-rendered span -> collapse (faithfulness-neutral).
        new_numbers = nums - seen_numbers_by_footprint[footprint]
        if new_numbers:
            seen_numbers_by_footprint[footprint] = seen_numbers_by_footprint[footprint] | nums
            kept.append(sv)
        else:
            dropped.append(sv)
    return kept, dropped
# Sentence split — terminal punctuation (incl. a closing provenance ``]``) + whitespace + a new
# sentence start. Fixed-width lookbehind. Mirrors the conservative splitter used elsewhere.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z0-9])")


def _verified_compose_enabled() -> bool:
    """PG_VERIFIED_COMPOSE gate. DEFAULT-OFF => the caller keeps the legacy section prose path
    byte-identical; ON => verified-compose is the PRIMARY per-section prose producer."""
    return os.getenv(_VERIFIED_COMPOSE_ENV, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _multicited_compose_enabled() -> bool:
    """PG_VERIFIED_COMPOSE_MULTICITED gate (I-beatboth-002 F1-1). DEFAULT-OFF => the multi-cited
    synthesis producer is never invoked and the module behaves byte-identically to the single-basket
    path; ON => the caller MAY compose a multi-cited synthesized sentence via
    ``compose_multicited_sentence``. Independent of ``PG_VERIFIED_COMPOSE`` so the multi-cited path
    is a SEPARATE, explicitly-opted increment (no implicit activation)."""
    return os.getenv(_MULTICITED_COMPOSE_ENV, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _cross_source_synthesis_enabled() -> bool:
    """PG_CROSS_SOURCE_SYNTHESIS gate (I-deepfix-001 M6). DEFAULT-OFF => the cross-source analytical
    producer is never invoked and the section producer is byte-identical; ON => after the per-basket
    units are built, ADDITIVELY append engine-licensed analytical sentences (keep-all)."""
    return os.getenv(_CROSS_SOURCE_SYNTHESIS_ENV, "0").strip().lower() not in ("", "0", "false", "off", "no")


def split_into_sentences(text: str) -> list[str]:
    """Split composed prose into sentence units for per-sentence strict_verify. Keeps each
    sentence's trailing provenance token(s) attached (the ``]`` lookbehind). Empty-safe."""
    if not text or not text.strip():
        return []
    return [s for s in _SENT_SPLIT_RE.split(text.strip()) if s.strip()]


def _basket_supports_members(basket: Any) -> list[Any]:
    """The basket's isolated-``SUPPORTS`` members, highest credibility weight first (the verbatim
    fallback prefers the strongest verified source). ``span_verdict == "SUPPORTS"`` is the binding
    isolated-verification result (NEVER the advisory clustered count)."""
    members = list(getattr(basket, "supporting_members", None) or [])
    supports = [m for m in members if str(getattr(m, "span_verdict", "") or "").upper() == "SUPPORTS"]
    supports.sort(key=lambda m: float(getattr(m, "credibility_weight", 0.0) or 0.0), reverse=True)
    return supports


def _distinct_origin_supports(basket: Any) -> list[Any]:
    """The basket's SUPPORTS members deduped to ONE per distinct ORIGIN (highest credibility weight
    kept), so a multi-cited sentence corroborates across DISTINCT sources and never re-cites the SAME
    origin twice (Codex gate P1: same-origin duplicate members must NOT render as a 'corroborated'
    multi-cite). Origin identity = ``origin_cluster_id`` (fallback ``evidence_id``). Order-stable
    (weight desc, inherited from ``_basket_supports_members``)."""
    seen: set[str] = set()
    out: list[Any] = []
    for m in _basket_supports_members(basket):
        origin = str(
            getattr(m, "origin_cluster_id", "") or getattr(m, "evidence_id", "") or id(m)
        )
        if origin in seen:
            continue
        seen.add(origin)
        out.append(m)
    return out


def _basket_scoped_pool(basket: Any, evidence_pool: dict) -> dict:
    """The verify pool scoped to THIS basket's member evidence_ids — using the GLOBAL rows (so the
    cited token OFFSETS stay anchored to the global ``evidence_pool[eid]`` exactly as downstream
    resolution/audit will read them; Codex core-gate P1-3). A citation to a source NOT in this
    basket is absent entirely (fails closed). The remaining P1-1 anti-cross-claim guarantee (a
    shared source backing DISTINCT baskets with DIFFERENT spans) is enforced SEPARATELY, AFTER
    verify, by ``_tokens_within_basket_regions`` — a sentence may pass strict_verify against the
    global row yet cite a span belonging to a DIFFERENT basket's claim; the region check rejects it."""
    # ISSUE #1279 P1#1 (tightening): scope to the basket's isolated-``SUPPORTS`` members ONLY, NEVER the
    # full ``supporting_members`` (which intentionally KEEPS unsupported members per Principle 2). An
    # UNSUPPORTED member's evidence_id MUST NOT enter the verify pool — else a writer citing it would
    # strict_verify-PASS against the unsupported span and render unverified text as verified. Strictly
    # MORE restrictive (fails closed); the K-span fallback already uses SUPPORTS-only members.
    own_ids = {str(getattr(m, "evidence_id", "") or "") for m in _basket_supports_members(basket)}
    own_ids.discard("")
    return {eid: row for eid, row in (evidence_pool or {}).items() if eid in own_ids}


def _member_global_span(member: Any, evidence_pool: dict) -> Optional[tuple]:
    """The member's verified span as GLOBAL offsets into ``evidence_pool[eid]`` — computed by
    LOCATING the member's ``direct_quote`` inside the global row's text, NOT from
    ``BasketMember.span`` (Codex core-gate iter-3 P1: ``_assemble_baskets`` populates ``span`` as
    a LOCAL ``(0, len(direct_quote))``, so the offset must be recovered against the real downstream
    row). Returns None when the member has no quote or the quote is not a substring of the global
    row (fail-closed: that member cannot define an acceptance region or a fallback span)."""
    eid = str(getattr(member, "evidence_id", "") or "")
    quote = str(getattr(member, "direct_quote", "") or "")
    if not eid or not quote:
        return None
    row = (evidence_pool or {}).get(eid) or {}
    haystack = str(row.get("direct_quote") or row.get("statement") or "")
    if not haystack:
        return None
    idx = haystack.find(quote)
    if idx < 0:
        return None
    return (idx, idx + len(quote))


def _basket_member_regions(basket: Any, evidence_pool: dict) -> dict:
    """``evidence_id -> list[(start, end)]`` of THIS basket's members' verified-span regions as
    GLOBAL offsets into ``evidence_pool`` (via ``_member_global_span``). The acceptance region: a
    composed sentence's cited token MUST land inside one of its own basket's member regions, else
    it is asserting a DIFFERENT basket's claim of a shared source (the 1-to-many cross-claim leak)."""
    # ISSUE #1279 P1#1 (tightening): the acceptance region is built from isolated-``SUPPORTS`` members
    # ONLY, NEVER the full ``supporting_members``. An UNSUPPORTED member's span MUST NOT define an
    # acceptance region — else a sentence citing that member's span would pass the region gate even
    # though the member is not a supporting source for the claim. Strictly MORE restrictive.
    regions: dict = {}
    for m in _basket_supports_members(basket):
        gspan = _member_global_span(m, evidence_pool)
        if gspan is None:
            continue
        regions.setdefault(str(getattr(m, "evidence_id", "") or ""), []).append(gspan)
    return regions


def _tokens_within_basket_regions(sentence: str, regions: dict) -> bool:
    """True iff EVERY provenance token in ``sentence`` cites an evidence_id in this basket AND its
    [start, end] falls within one of that member's verified-span regions. A token outside the
    member's region (a shared source's OTHER-claim span) -> False -> the sentence is rejected and
    the basket falls back to its OWN K-span. A sentence with no token -> False (fail closed)."""
    from src.polaris_graph.generator.provenance_generator import parse_provenance_tokens  # noqa: PLC0415
    toks = parse_provenance_tokens(sentence)
    if not toks:
        return False
    for tok in toks:
        eid = str(getattr(tok, "evidence_id", "") or "")
        t_start = int(getattr(tok, "start", -1))
        t_end = int(getattr(tok, "end", -1))
        spans = regions.get(eid)
        if not spans or not any(s <= t_start and t_end <= e for (s, e) in spans):
            return False
    return True


_JUNK_SCREEN = None


def _compose_junk_screen(
    unit: str,
    known_words: "set[str] | frozenset[str] | None" = None,
    *,
    require_sentence_form: bool = False,
) -> bool:
    """I-beatboth-011 §3.4 (#1289): True iff ``unit`` is allowlist crawl/social/masthead chrome —
    INPUT HYGIENE applied per sentence-unit at the verbatim-emit (and abstractive-writer input)
    consumers, NEVER inside the verify pool/regions and NEVER a verdict. Reuses the shared
    ``weighted_enrichment._make_junk_screen`` (``is_boilerplate_or_nonassertional`` + the high-precision
    multi-word chrome list). P1-4: allowlist-anchored only — a real short sentence is KEPT (no length
    drop). Faithfulness-safe: boilerplate is not a corroborating source, so removing it is not a §-1.3
    DROP. Lazy + fail-CONSERVATIVE: on any import failure fall back to the boilerplate helper, and only
    if THAT is unavailable keep the unit (never silently drop real prose).

    I-wire-017 (#1339) FIX R1: optional ``known_words`` (the run's corpus-vocabulary allowlist) +
    ``require_sentence_form`` are threaded into the shared predicate so the K-span PRODUCER path
    (``build_verified_span_draft``) actually exercises the truncation + subjectless-fragment legs —
    previously inert here because they were called without these arguments. Safe on this path: K-span
    units are whole lifted SOURCE sentences (not the render seam's mid-clause ``[N]`` fragments).
    Still suppress-only; the fallback screens (which take no kwargs) are called positionally."""
    global _JUNK_SCREEN
    if _JUNK_SCREEN is None:
        try:
            from src.polaris_graph.generator.weighted_enrichment import _make_junk_screen
            _JUNK_SCREEN = _make_junk_screen()
        except Exception:  # pragma: no cover — weighted_enrichment is stable in-tree
            try:
                from src.tools.access_bypass import is_boilerplate_or_nonassertional as _b
                _JUNK_SCREEN = lambda t: bool(_b(t))  # noqa: E731
            except Exception:
                _JUNK_SCREEN = lambda _t: False  # noqa: E731 — keep content; never drop real prose
    try:
        return bool(
            _JUNK_SCREEN(
                unit, require_sentence_form=require_sentence_form, known_words=known_words
            )
        )
    except TypeError:
        # The boilerplate / no-op fallback screens take only the unit (no kwargs).
        try:
            return bool(_JUNK_SCREEN(unit))
        except Exception:
            return False
    except Exception:
        return False


def _known_words_for_compose(evidence_pool: Any) -> "set[str] | None":
    """I-wire-017 (#1339) FIX R1 helper: the run's corpus-vocabulary allowlist for the K-span chrome
    screen, built from the evidence pool's own fetched source text via the shared
    ``weighted_enrichment.build_known_words_from_evidence``. Lazy + fail-CONSERVATIVE: returns None on
    any import/build failure (and on an empty pool), so the truncation leg is simply skipped — never a
    wrong drop, never a crash. PURE."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (
            build_known_words_from_evidence,
        )
    except Exception:  # pragma: no cover — weighted_enrichment is stable in-tree
        return None
    try:
        words = build_known_words_from_evidence(evidence_pool)
    except Exception:  # pragma: no cover — defensive; build is pure
        return None
    return words or None


# ─────────────────────────────────────────────────────────────────────
# I-deepfix-001 FIX-D part 3 (#1335) — snap a mid-sentence-truncated cited span to a sentence boundary
#
# Forensic (drb_72): an evidence span byte-range that terminates MID-SENTENCE / MID-NUMBER (the
# extractor cut the quote) composes a dangling clause (e.g. "quadrupled from approximately 100,000
# [ev]" with the "to 400,000" endpoint dropped). The fix EXTENDS the cited span forward to the next
# sentence boundary WITHIN THE SAME evidence row, so the composed clause is whole. Extend-ONLY: the
# snapped span is always a SUPERSET of the original within the same row, so it stays grounded by
# construction (the token covers exactly the emitted text) and NEVER fabricates. Faithfulness-NEUTRAL.
# Default-ON; ``PG_COMPOSE_SNAP_SPAN_SENTENCE=0`` restores byte-identical legacy behavior.
_ENV_SNAP_SPAN_SENTENCE = "PG_COMPOSE_SNAP_SPAN_SENTENCE"
_ENV_SNAP_MAX_EXTEND_CHARS = "PG_COMPOSE_SNAP_SPAN_MAX_EXTEND_CHARS"
_DEFAULT_SNAP_MAX_EXTEND_CHARS = 320   # cap so a missing terminator never swallows the whole row


def _snap_span_enabled() -> bool:
    # default-ON; only an explicit 0/false/off/no disables. An EMPTY string behaves like UNSET
    # (Codex #1335 gate P2) -> stays ON, so a blank env var cannot silently disable the snap.
    return os.getenv(_ENV_SNAP_SPAN_SENTENCE, "1").strip().lower() not in ("0", "false", "off", "no")


# I-deepfix-001 (Codex #1335 gate P2): a closed set of common abbreviations whose trailing ``.``
# is NOT a sentence boundary. Matched against the lowercased alphabetic token IMMEDIATELY before
# the ``.`` (so "Fig." → "fig", "vs." → "vs", "No." → "no", "pp." → "pp", "et al." → "al"). The
# dotted-initialism forms (U.S., e.g., i.e.) are caught by the single-letter-preceded-by-a-dot rule
# in ``_preceding_token_is_abbreviation`` rather than by listing every chained letter. Refusing a
# boundary here can only EXTEND the snapped span (extend-only + bounded), so a rare false positive
# never truncates a span — it is faithfulness-safe by construction.
_KNOWN_ABBREVIATIONS = frozenset(
    {
        "fig", "figs", "dr", "mr", "mrs", "ms", "prof", "no", "nos", "pp", "vs",
        "al", "vol", "etc", "eg", "ie", "cf", "approx", "ca", "inc", "ltd", "co",
        "jr", "sr", "st", "ed", "eds", "repr", "ch", "sec",
    }
)


def _preceding_token_is_abbreviation(haystack: str, k: int) -> bool:
    """True iff the alphabetic token immediately before ``haystack[k]`` (a ``.``) is a known
    abbreviation (``Fig`` / ``Dr`` / ``No`` / ``pp`` / ``vs`` / ``al`` …) OR a single letter that is
    itself preceded by a ``.`` — the dotted-initialism shape of ``U.S.`` / ``e.g.`` / ``i.e.`` (so the
    final dot of the initialism is not read as a sentence end). A single capital that is NOT preceded
    by a dot ("…the grade was A.") stays a real terminator. Pure, oob-safe."""
    i = k - 1
    while i >= 0 and haystack[i].isalpha():
        i -= 1
    token = haystack[i + 1:k].lower()
    if not token:
        return False
    if token in _KNOWN_ABBREVIATIONS:
        return True
    # Single-letter token glued to a leading '.' → a chained initialism (U.S. / e.g. / i.e.).
    if len(token) == 1 and i >= 0 and haystack[i] == ".":
        return True
    return False


def _is_real_sentence_terminator(haystack: str, k: int, n: int) -> bool:
    """True iff ``haystack[k]`` actually ends a sentence. ``!``/``?`` always do. A ``.`` does ONLY
    when the next char (past a closing quote/paren) is whitespace / EOL / end-of-string — a ``.``
    glued to a DIGIT is a decimal point (e.g. ``3.75``) and a ``.`` glued to a letter is an
    abbreviation, neither of which ends a sentence. This stops the span-snap from truncating a
    number to its integer part (Codex #1335 gate P1: ``... to 3.75`` must never snap to ``... to 3.``).
    I-deepfix-001 (Codex #1335 gate P2): a ``.`` immediately after a known abbreviation token
    (Fig. / Dr. / U.S. / et al. / e.g. / i.e. / vs. / No. / pp.) is likewise NOT a terminator, so the
    span-snap can no longer stop after the abbreviation. Extend-only + faithfulness-safe."""
    if not (0 <= k < n):
        return False
    c = haystack[k]
    if c in "!?":
        return True
    if c != ".":
        return False
    j = k + 1
    if j < n and haystack[j] in "\"')]":
        j += 1
    if not (j >= n or haystack[j] in " \t\r\n"):
        return False
    # The dot looks terminal (whitespace/EOL follows) — but reject it when the preceding token is a
    # common abbreviation, so e.g. "see Fig. 4 for the trend" never snaps to end after "Fig.".
    if _preceding_token_is_abbreviation(haystack, k):
        return False
    return True


def _ends_at_sentence_boundary(haystack: str, end: int) -> bool:
    """True iff the cited span [.., end) already ends at a REAL sentence boundary — the last
    non-(space/close-quote/paren) char before ``end`` is a genuine terminal ``. ! ?`` (a decimal
    point or abbreviation dot does NOT count). Empty/oob-safe."""
    k = end - 1
    while k >= 0 and k < len(haystack) and haystack[k] in " \t\r\n\"')]":
        k -= 1
    return _is_real_sentence_terminator(haystack, k, len(haystack))


def _snap_span_end_to_sentence(haystack: str, start: int, end: int) -> int:
    """EXTEND ``end`` forward to just past the next REAL sentence terminator in ``haystack`` when the
    cited span ends mid-sentence. Extend-ONLY (never shrinks) -> the result is always a SUPERSET of the
    original span within the SAME row. Returns ``end`` unchanged when the span already ends at a
    boundary, when no REAL terminator is found within the bounded scan (avoid running to EOF), or on
    any out-of-range input (fail-safe no-op). A decimal point / abbreviation dot is NOT a terminator
    (Codex #1335 gate P1) so the snap can never truncate a number to its integer part."""
    if not haystack:
        return end
    n = len(haystack)
    if not (0 <= start < end <= n):
        return end
    if _ends_at_sentence_boundary(haystack, end):
        return end
    try:
        max_extend = int(os.getenv(_ENV_SNAP_MAX_EXTEND_CHARS, "").strip() or _DEFAULT_SNAP_MAX_EXTEND_CHARS)
    except ValueError:
        max_extend = _DEFAULT_SNAP_MAX_EXTEND_CHARS
    max_extend = max(1, max_extend)
    limit = min(n, end + max_extend)
    for i in range(end, limit):
        if _is_real_sentence_terminator(haystack, i, n):
            j = i + 1
            if j < n and haystack[j] in "\"')]":
                j += 1
            return j
    return end


def build_verified_span_draft(basket: Any, evidence_pool: dict) -> Optional[str]:
    """The basket-id-bound VERBATIM K-span fallback: a sentence built from the basket's own
    strongest isolated-``SUPPORTS`` member's verbatim ``direct_quote`` (the span it was verified
    against), tagged with that member's own ``[#ev:<id>:0-<len>]`` provenance token so it re-passes
    strict_verify trivially (it IS the verified span). Returns None when the basket has no verified
    span resolvable in the pool (caller emits an insufficient-evidence disclosure instead).

    I-wire-017 (#1339) FIX R1: build the run's corpus-vocabulary allowlist ONCE from the evidence
    pool and pass it (+ ``require_sentence_form=True``) into the per-unit chrome/truncation screen so
    this PRODUCER path screens out mid-word span cuts and subjectless fragments before they ship —
    previously the screen ran without these, so those legs were inert and the render seam was the
    only net. Suppress-only: faithfulness verdicts are untouched."""
    known_words = _known_words_for_compose(evidence_pool)
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        gspan = _member_global_span(m, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        start, end = gspan
        # I-deepfix-001 FIX-D part 3 (#1335): if the verified span ends MID-SENTENCE (the extractor cut
        # the quote), EXTEND it forward to the next sentence boundary IN THE SAME ROW so the composed
        # clause is not left dangling. Extend-only -> a SUPERSET of the same row -> grounded by
        # construction (the widened token covers exactly the emitted text), never fabricates. When no
        # snap applies (snap_end == end) the path is byte-identical to legacy. Default-ON.
        snap_end = end
        span_text = quote
        if _snap_span_enabled():
            row = (evidence_pool or {}).get(eid) or {}
            haystack = str(row.get("direct_quote") or row.get("statement") or "")
            snap_end = _snap_span_end_to_sentence(haystack, start, end)
            if snap_end > end and 0 <= start < snap_end <= len(haystack):
                # Rebuild the prose from the SAME-row slice the widened token cites, so the completed
                # final sentence is whole; the earlier sentences are unchanged (they are a prefix of it).
                span_text = haystack[start:snap_end]
        # PER-SENTENCE units (Codex P1-4): a multi-sentence verified span must NOT ship as one blob
        # with a single trailing token (strict_verify would split it and drop the un-tokened earlier
        # units). Each sentence carries the member's OWN span token — the whole verified span grounds
        # each sub-sentence (it literally contains it). Offsets are the member's REAL GLOBAL offsets
        # (Codex P1-3) so downstream resolution anchors to the verified span, never 0-len of a span
        # that may differ from the global row for a shared source.
        units = [u.strip() for u in (split_into_sentences(span_text) or [span_text]) if u.strip()]
        # I-beatboth-011 §3.4 (#1289): drop allowlist crawl/social chrome units (input hygiene); keep all
        # real content incl. short real sentences. If EVERY unit is chrome, fall through to the next
        # SUPPORTS member (then K-span / insufficient-evidence). Faithfulness-safe, never a verdict.
        units = [
            u for u in units
            if not _compose_junk_screen(u, known_words, require_sentence_form=True)
        ]
        out = []
        for u in units:
            # I-beatboth-009 (#1287): the provenance token must sit BEFORE the terminal period so the
            # downstream strict_verify splitter (split_into_sentences: terminal-punct + whitespace +
            # [A-Z0-9]) keeps it ATTACHED. The prior "U. [#ev:...]" form orphaned the token into a
            # contentless fragment -> no_provenance_token -> verified=0 (the P6 v2 STORM-section zero).
            u_core = _strip_terminal_punct(u)
            out.append(f"{u_core} [#ev:{eid}:{start}-{snap_end}].")
        if out:
            return " ".join(out)
    return None


def build_short_member_sentence(basket: Any, evidence_pool: dict) -> str:
    """I-arch-011 PR-c RENDER PROBE (advisor 2026-06-20): a DETERMINISTIC, NO-LLM short writer — the
    FIRST sentence of the basket's strongest isolated-``SUPPORTS`` member's verified span, tagged with
    that member's REAL global offsets for exactly that first-sentence prefix. It is a verbatim PREFIX of
    the verified span, so it re-passes strict_verify trivially AND lands within the member's own region
    (the P1-1 region gate). Used to PROBE the render path (does verified-compose fire through
    _run_section->render? does short prose fit the 150K answer_body budget?) WITHOUT the per-basket LLM
    writer (the real PR-c writer) and WITHOUT the verbatim-full-span overflow. Returns '' when no member
    resolves (caller falls back to the basket's K-span / insufficient-evidence disclosure)."""
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        gspan = _member_global_span(m, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        start, _end = gspan
        units = [u.strip() for u in (split_into_sentences(quote) or [quote]) if u.strip()]
        # I-beatboth-011 §3.4 (#1289): drop allowlist crawl/social chrome units (input hygiene); if EVERY
        # unit is chrome, fall through to the next SUPPORTS member. Real short sentences are KEPT (P1-4).
        units = [u for u in units if not _compose_junk_screen(u)]
        if not units:
            continue
        first = units[0]
        # Offset the token to the first sentence's position WITHIN the verified span (prefix => the
        # quote starts at `start`; locate `first` in `quote` to stay exact if there is leading text).
        off = quote.find(first)
        tok_start = start + (off if off >= 0 else 0)
        tok_end = tok_start + len(first)
        # I-beatboth-009 (#1287): emit the token BEFORE the terminal period so split_into_sentences
        # keeps it attached (the prior "first. [#ev:...]" orphaned the token -> no_provenance_token ->
        # verified=0). tok_start/tok_end are UNCHANGED (they still index the member's real global span),
        # so faithfulness is identical — only the display punctuation moves.
        first_display = _strip_terminal_punct(first)
        return f"{first_display} [#ev:{eid}:{tok_start}-{tok_end}]."
    return ""


def _insufficient_evidence_disclosure(basket: Any) -> str:
    """Honest NEVER-empty fallback when a basket has prose-fail AND no verified span: disclose the
    gap, never fabricate filler (§-1.3). Names the claim subject so the disclosure is specific."""
    subject = str(getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim").strip()
    return f"[insufficient verified evidence to compose a sentence for: {subject[:160]}]"


def _compose_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
) -> str:
    """Compose ONE basket: writer drafts prose -> strict_verify each sentence against the
    BASKET-SCOPED pool -> keep passing sentences; on the FIRST failing sentence (or a foreign-cited
    one, which fails closed under the scoped pool) FALL BACK to this basket's own verified K-span;
    if the basket has no verified span, emit the insufficient-evidence disclosure. NEVER empty."""
    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    draft = writer_fn(basket, scoped_pool) or ""
    kept: list[str] = []
    fell_back = False
    for sentence in split_into_sentences(draft):
        res = verify_fn(sentence, scoped_pool)
        # Append the VERIFIER'S sentence, not the raw input (Codex core-gate P1-2): with
        # PG_SPAN_RESOLVER on, verify_sentence_provenance RE-ANCHORS the token to the span it actually
        # entailed (``SentenceVerification.sentence`` = the re-pointed ``final_sentence``).
        verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
        # PASS requires BOTH (a) strict_verify, AND (b) every cited token lands WITHIN this basket's
        # OWN member span regions (Codex core-gate P1-1): a shared source's OTHER-claim span span-
        # grounds against the global row, but it is NOT this basket's claim -> reject -> own K-span.
        if bool(getattr(res, "is_verified", False)) and _tokens_within_basket_regions(verified_text, regions):
            kept.append(verified_text)
        else:
            fell_back = True
            break
    if kept and not fell_back:
        return " ".join(kept)
    # prose failed (or produced nothing): basket-id-bound verbatim fallback, else honest disclosure.
    fallback = build_verified_span_draft(basket, evidence_pool)
    if fallback is not None:
        # If some sentences were kept before the failure, keep them + the verbatim span (never lose
        # already-verified prose); else the span alone.
        return " ".join(kept + [fallback]) if kept else fallback
    return " ".join(kept + [_insufficient_evidence_disclosure(basket)]) if kept \
        else _insufficient_evidence_disclosure(basket)


# ── I-beatboth-002 Fix 1 (F1-1) — multi-cited verified synthesis ──────────────────────────────────
#
# The DRB-II analysis dimension needs cross-source SYNTHESIS: ONE rendered sentence that carries
# corroborating citations from MORE THAN ONE basket. The faithfulness-by-construction design (advisor
# 2026-06-20, Codex BRIEF APPROVE):
#
#   * VERIFY PER CLAUSE, NEVER the whole multi-token sentence against one pool. A co-located sentence
#     carries tokens from >=2 baskets; verifying it WHOLE against any single basket's scoped pool would
#     fail-closed on the OTHER basket's token (its evidence_id is absent from that scoped pool) and
#     artifactually REJECT genuine multi-cite. That false rejection is the exact trap that would make
#     per-basket "look too tight" and tempt the (OUT-of-scope) union pool. The escape hatch is to verify
#     EACH per-member clause against its OWN basket's scoped pool + own-region gate (the existing P1-2 /
#     P1-1 contract, untouched) and ONLY THEN co-locate. Each token was already verified against its own
#     basket; the co-location asserts NOTHING new.
#   * NO emergent aggregate predicate. The clauses are joined by a SEMANTICALLY-NEUTRAL connective
#     (``"; "``) with no quantifier ("consistently" / "most" / "studies show"). The relational-quantifier
#     guard is F1-2 (DEFERRED); because this producer never emits an aggregate predicate, it is SAFE
#     without F1-2 (the boundary contract — under-relaxing is safe; over-relaxing is the lethal direction).
#   * JOIN CHARACTER. ``"; "`` + a lowercased continuation keeps the multi-token co-location as ONE
#     sentence under the production ``_SENT_SPLIT_RE`` (terminal ``.!?]`` + whitespace + ``[A-Z0-9]``);
#     joining with ``". "`` would re-split the clauses apart and defeat the multi-cited requirement.
#   * P1-2 FAIL-CLOSED preserved. A clause whose writer cites an evidence_id OUTSIDE its own basket
#     fails closed under that basket's scoped pool and falls back to the basket's OWN verbatim K-span —
#     a foreign citation can NEVER leak into the co-located sentence.
#
# strict_verify / NLI / 4-role D8 / provenance / span-grounding are UNCHANGED and run as-is per clause.


def _strip_terminal_punct(clause: str) -> str:
    """Drop a single trailing sentence terminal (``. ! ?``) so a verified clause can be co-located
    with ``"; "`` as ONE multi-token sentence. A clause ending in a provenance ``]`` (or any other
    char) is returned unchanged — the connective is appended after the token by the caller."""
    clause = (clause or "").rstrip()
    return clause[:-1].rstrip() if clause[-1:] in ".!?" else clause


def _per_basket_verified_clause(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
) -> Optional[str]:
    """Produce ONE per-member-VERIFIED clause for a single basket, suitable for co-location.

    Reuses the UNCHANGED single-basket contract: ``_compose_one_basket`` drafts via ``writer_fn``,
    strict_verifies each sentence against THIS basket's scoped pool, and gates every cited token to
    THIS basket's own member regions (P1-2 / P1-1). On prose-fail it returns the basket's own verbatim
    K-span (never a foreign basket's). The returned text is therefore faithful-by-construction for THIS
    basket alone. Returns ``None`` only when the basket yields no real verified content (an
    insufficient-evidence disclosure) — such a basket contributes NO clause to the multi-cited sentence
    (it is surfaced separately by the existing per-basket path, never fabricated into the synthesis).
    """
    composed = _compose_one_basket(
        basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
    )
    if not composed or not composed.strip():
        return None
    # An insufficient-evidence disclosure is NOT a verified clause — do not co-locate it.
    if composed.strip().startswith("[insufficient verified evidence"):
        return None
    # The clause MUST carry at least one provenance token (else it is not a cited synthesis member).
    if not _EV_TOKEN_RE.search(composed):
        return None
    return composed.strip()


def _lowercase_first_alpha(text: str) -> str:
    """Lowercase the FIRST alphabetic character of a continuation clause so the co-located sentence
    does not present a mid-sentence capital that (a) reads as a new sentence and (b) trips the
    ``[A-Z0-9]`` lookahead of ``_SENT_SPLIT_RE``. Proper-noun casing further into the clause is left
    intact (only the leading word's first letter is touched). No-op on empty / non-alpha-leading text."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.lower() + text[i + 1:]
        if ch.isalnum():
            return text  # leading digit — nothing to lowercase
    return text


def _join_verified_clauses(clauses: list, *, connective: str = "; ") -> Optional[str]:
    """Co-locate N already-strict_verify-PASSED single-source clauses into ONE multi-cited sentence.

    Extracted (I-beatboth-011 keystone-F1 F1-2b, #1284) from ``compose_multicited_sentence`` so BOTH
    the cross-basket producer AND the within-basket producer share ONE join contract. Each input clause
    is a string that ALREADY carries its own ``[#ev:<id>:<a>-<b>]`` provenance token(s) and ALREADY
    passed the UNCHANGED ``strict_verify`` against its own span (the caller is responsible for that —
    this helper NEVER verifies, NEVER relaxes a gate, NEVER edits a clause's claim; it only joins).

    The clauses are joined by a SEMANTICALLY-NEUTRAL ``connective`` (default ``"; "``) with each
    continuation lowercased at its first alpha char, so the result stays ONE sentence under the
    production ``_SENT_SPLIT_RE`` (terminal ``.!?]`` + whitespace + ``[A-Z0-9]``) and asserts NO
    emergent aggregate predicate — each clause keeps its OWN token, so the joined sentence still passes
    ``strict_verify`` PER CLAUSE exactly as each clause did alone. Joining with ``". "`` would re-split
    the clauses and defeat the multi-cited requirement; ``"; "`` + a lowercased continuation keeps the
    co-location as one sentence (the join-char invariant).

    Returns ``None`` when FEWER THAN TWO non-empty clauses are supplied (a single clause is not a
    multi-cited synthesis — the caller keeps the unchanged single-cite path). Pure; order-preserving.
    """
    clean = [str(c).strip() for c in (clauses or []) if c and str(c).strip()]
    if len(clean) < 2:
        return None
    parts = [clean[0].rstrip()]
    for clause in clean[1:]:
        cont = _strip_terminal_punct(clause).lstrip()
        cont = _lowercase_first_alpha(cont)
        # Append the connective to the PREVIOUS part (after its provenance token), then the
        # continuation — the splitter sees ``...] ; <lower>...`` and keeps it as one sentence.
        parts[-1] = parts[-1].rstrip()
        parts.append(cont)
    sentence = connective.join(parts)
    if sentence and sentence[-1:] not in ".!?]":
        sentence = sentence + "."
    return sentence


def compose_multicited_sentence(
    baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    connective: str = "; ",
) -> Optional[str]:
    """Co-locate per-member-VERIFIED clauses from N corroborating baskets into ONE multi-cited
    synthesized sentence carrying citations from >1 basket.

    Each contributing basket yields exactly one clause via ``_per_basket_verified_clause`` (verified
    against its OWN basket's scoped pool + own-region gate — the UNCHANGED P1-2/P1-1 contract). The
    clauses are then joined by ``_join_verified_clauses`` (a SEMANTICALLY-NEUTRAL connective, each
    continuation lowercased) so the result stays ONE sentence under the production sentence splitter and
    asserts NO emergent aggregate predicate (this cross-basket producer never licenses a relational
    quantifier).

    Returns ``None`` when FEWER THAN TWO baskets yield a verified clause — a single-basket result is
    NOT a multi-cited synthesis, so the caller keeps the existing single-basket prose for it (this
    producer adds breadth, it never strands a basket). Faithfulness: every emitted token was already
    strict_verify-passed against its own basket region; the co-location adds nothing to verify.
    """
    clauses: list[str] = []
    for basket in (baskets or []):
        clause = _per_basket_verified_clause(
            basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
        )
        if clause is not None:
            clauses.append(clause)
    return _join_verified_clauses(clauses, connective=connective)


# ── I-beatboth-011 keystone-F1 (#1284) — WITHIN-BASKET multi-cited verified synthesis ──────────────
#
# The §-1.3 DNA reading of corroboration: when ONE claim basket carries >=2 isolated-``SUPPORTS`` members
# (the same claim, multiple independent sources), surface that corroboration as ONE sentence carrying
# ALL of their citations — NOT collapsed to the single strongest member (the legacy K-span). Each
# member contributes ONE single-source clause that INDEPENDENTLY passes the UNCHANGED strict_verify
# against its OWN span (via the existing single-member per-basket contract), the
# ``relational_quantifier_guard`` drops any unlicensed aggregate predicate, then ``_join_verified_clauses``
# co-locates them. A single-member basket returns the UNCHANGED single-cite K-span draft (byte-identical
# — the producer adds breadth, it NEVER rewrites the one-source path).


def _single_member_basket(basket: Any, member: Any) -> Any:
    """A shallow COPY of ``basket`` whose ``supporting_members`` is the single ``member`` — so the
    existing ``_per_basket_verified_clause`` machinery (basket-scoped verify pool + own-region gate,
    the UNCHANGED P1-2/P1-1 contract) runs over ONE member at a time. Pure: copies the dataclass via
    ``dataclasses.replace`` when available, else a lightweight attribute shim; never mutates the input.
    Refuter references + verdict are preserved so the guard still sees the basket's contested state."""
    # I-beatboth-011 keystone-F1 (#1284, Codex gate P0-2): give the sub-basket a member-UNIQUE
    # claim_cluster_id so the abstractive writer (keyed by claim_cluster_id) CANNOT return the parent
    # WHOLE-basket draft for this single member — its cluster-keyed lookup MISSES -> _member_writer_clause
    # returns None -> the UNGUARDED verbatim K-span fallback fires. This is exactly what the relational-
    # quantifier guard's KNOWN-BOUND assumed; without it a source-written quantifier embedded in the
    # abstractive whole-basket frame would reach the guard and be stripped (misquoting the source). The
    # DEFAULT writer (build_short_member_sentence) ignores claim_cluster_id, so its verbatim-span path is
    # unaffected. NOTE: a member-unique cluster id never re-collides with a real basket id (the ``::member::``
    # infix is not produced by the clusterer), so the only effect is forcing the abstractive miss.
    _sub_cid = (
        f"{str(getattr(basket, 'claim_cluster_id', '') or '')}::member::"
        f"{str(getattr(member, 'evidence_id', '') or id(member))}"
    )
    import dataclasses  # noqa: PLC0415
    if dataclasses.is_dataclass(basket):
        try:
            return dataclasses.replace(basket, supporting_members=[member], claim_cluster_id=_sub_cid)
        except (TypeError, ValueError):
            pass
    # Non-dataclass fallback: a read-only shim exposing the same attributes with a 1-member roster.
    class _OneMemberBasket:  # noqa: N801 — local shim type
        pass
    shim = _OneMemberBasket()
    for name in ("claim_cluster_id", "claim_text", "subject", "predicate", "refuter_cluster_ids",
                 "weight_mass", "total_clustered_origin_count", "verified_support_origin_count",
                 "basket_verdict"):
        setattr(shim, name, getattr(basket, name, None))
    shim.claim_cluster_id = _sub_cid  # override the parent's id (P0-2: force the abstractive lookup miss)
    shim.supporting_members = [member]
    return shim


def _member_verbatim_clause(basket: Any, member: Any, evidence_pool: dict) -> Optional[str]:
    """ONE member's VERBATIM K-span clause: the member's own verified ``direct_quote`` tagged with its
    OWN real global ``[#ev:<id>:<start>-<end>]`` token (the existing ``build_verified_span_draft`` shape,
    scoped to a single member via a 1-member sub-basket). Faithful-BY-CONSTRUCTION — it IS the verified
    span, so it re-passes the UNCHANGED ``strict_verify`` trivially and carries the source's OWN words
    (a quantifier in the source's words is what the source SAID, never a fabricated aggregate — so the
    relational-quantifier guard MUST NOT touch this path). Returns None when the member has no resolvable
    verified span (the producer then skips this member)."""
    return build_verified_span_draft(_single_member_basket(basket, member), evidence_pool)


def _member_writer_clause(
    sub_basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
) -> Optional[str]:
    """ONE member's WRITER-SYNTHESIZED clause — and ONLY the writer's output, NEVER a K-span fallback.

    Mirrors ``_compose_one_basket``'s writer+verify head (basket-scoped pool + per-sentence
    ``strict_verify`` + the own-region P1-1 gate, all UNCHANGED) but DROPS the K-span fallback tail: it
    returns the verified writer prose, or ``None`` if the writer produced nothing or any sentence failed
    verify/region. This is the ONLY text the relational-quantifier guard is allowed to touch — so the
    guard can NEVER mutate a verbatim K-span (a quantifier the SOURCE wrote stays verbatim; the producer
    supplies the K-span fallback SEPARATELY, unguarded). Pure read of the production verifier; no relax."""
    scoped_pool = _basket_scoped_pool(sub_basket, evidence_pool)
    regions = _basket_member_regions(sub_basket, evidence_pool)
    draft = writer_fn(sub_basket, scoped_pool) or ""
    kept: list[str] = []
    for sentence in split_into_sentences(draft):
        res = verify_fn(sentence, scoped_pool)
        verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
        if bool(getattr(res, "is_verified", False)) and _tokens_within_basket_regions(verified_text, regions):
            kept.append(verified_text)
        else:
            return None  # writer prose failed verify/region -> NO writer clause (caller uses K-span)
    if not kept:
        return None
    joined = " ".join(kept).strip()
    return joined or None


def compose_basket_multicited_sentence(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    connective: str = "; ",
) -> Optional[str]:
    """Compose ONE multi-cited sentence from a SINGLE basket's >=2 corroborating verified members.

    For a basket with exactly ONE isolated-``SUPPORTS`` member (or none), returns the UNCHANGED
    single-cite path — ``build_verified_span_draft`` — so the one-source contract is byte-identical (the
    producer NEVER rewrites a single-source claim). For a basket with >=2 ``SUPPORTS`` members it builds
    ONE single-source clause PER member and co-locates them:

      1. For each ``SUPPORTS`` member, attempt a WRITER-SYNTHESIZED clause via the EXISTING single-member
         per-basket contract (``_per_basket_verified_clause`` over a 1-member sub-basket) — so the clause
         INDEPENDENTLY passes the UNCHANGED ``strict_verify`` against its OWN span + lands within its OWN
         member region (the P1-2/P1-1 gates, untouched). The relational-quantifier guard runs ONLY on
         this writer-synthesized clause (a fabricated aggregate predicate over a single member's claim is
         the only thing it can target). If the guard annihilates it (a pure predicate, no span) OR the
         writer produced nothing/failed verify, the member FALLS BACK to its OWN VERBATIM K-span
         (``_member_verbatim_clause``) — which the guard NEVER touches (the source's own words, incl. any
         quantifier the source itself wrote, are faithful-by-construction and must be preserved verbatim).
      2. Joins the surviving per-member clauses via ``_join_verified_clauses`` — each clause keeps its OWN
         ``[#ev:...]`` token, so the joined sentence STILL passes ``strict_verify`` PER CLAUSE exactly as
         each clause did alone (decimals, multilingual content, etc. ride inside each member's own span).

    The relational-quantifier guard targets ONLY the writer's synthesized output — NEVER a verbatim
    K-span — so it can never misquote a source by deleting a word the source actually wrote. The abstractive
    writer (keyed by ``claim_cluster_id``) precomputes a WHOLE-basket draft per basket, not per member; the
    sub-basket lookup therefore misses (or returns a draft that fails the single-member scoped pool) and the
    member cleanly falls back to its own verbatim K-span — so the keystone multi-cite ALWAYS fires from the
    deterministic verbatim spans regardless of the writer path (the writer can only IMPROVE a member's
    phrasing, never gate the multi-cite). Returns the joined multi-cited sentence; if fewer than TWO members
    yield a clause it falls back to the basket's single-cite K-span (always-release — never a silent empty).
    Faithfulness: the engine is never touched; the guard only DROPS an unsupported quantifier from
    SYNTHESIZED prose; verbatim spans are preserved; the single-source path is byte-identical. The caller
    re-runs the UNCHANGED ``strict_verify`` over the rendered draft.
    """
    from src.polaris_graph.generator.relational_quantifier_guard import (  # noqa: PLC0415
        guard_relational_quantifier,
    )
    # P1: corroborate across DISTINCT origins only — same-origin duplicate members must not render as a
    # multi-cited "corroborated" sentence (each clause cites a distinct source).
    supports = _distinct_origin_supports(basket)
    # Single-source (or no verified source): UNCHANGED single-cite path — byte-identical to legacy.
    if len(supports) < 2:
        return build_verified_span_draft(basket, evidence_pool)

    clauses: list[str] = []
    for member in supports:
        sub = _single_member_basket(basket, member)
        clause: Optional[str] = None
        # (1a) WRITER-synthesized clause ONLY (no K-span fallback bundled in — so the guard can never
        # touch a verbatim span). None => the writer produced nothing or failed verify/region.
        written = _member_writer_clause(
            sub, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
        )
        if written:
            # The guard runs ONLY on this synthesized prose: strip any unlicensed relational quantifier
            # the writer fabricated. None => the synthesis was a pure aggregate predicate with no span
            # left; fall back to the member's verbatim span rather than drop the corroborator.
            guarded = guard_relational_quantifier(written, basket)
            if guarded and guarded.strip():
                clause = guarded.strip()
        if clause is None:
            # (1b) VERBATIM K-span fallback — the source's own words, NEVER guard-touched (a quantifier
            # the SOURCE wrote is faithful; deleting it would misquote the source). Faithful-by-construction.
            verbatim = _member_verbatim_clause(basket, member, evidence_pool)
            if verbatim and verbatim.strip():
                clause = verbatim.strip()
        if clause:
            clauses.append(clause)

    joined = _join_verified_clauses(clauses, connective=connective)
    if joined is not None:
        return joined
    # Fewer than TWO members yielded a clause — always-release the basket's single-cite K-span rather
    # than strand the corroborated basket (never empty).
    return build_verified_span_draft(basket, evidence_pool)


def _compose_section_per_basket(
    section_baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    edges: Any = None,
    equiv_clusters: Any = None,
    agree_map: Any = None,
) -> list[str]:
    """PRIMARY per-section prose producer: compose EVERY basket of the section (the contract
    entities are a SUBSET — this is what moves the scored breadth off the contract-slot bound).
    Returns one composed string per basket, in order. Order-stable.

    I-deepfix-001 M6 (cross-source analytical synthesis): when ``PG_CROSS_SOURCE_SYNTHESIS`` is ON
    (DEFAULT-OFF => byte-identical; ``edges``/``equiv_clusters``/``agree_map`` are then unused and never
    read), an ADDITIVE pass appends analytical sentences — each ``[verified clause A][engine-LICENSED
    connective][verified clause B]`` spanning TWO baskets — AFTER the per-basket units are built. The
    two atoms keep their own ``[#ev]`` tokens and re-pass the UNCHANGED ``strict_verify`` per clause; the
    connective carries no token and is licensed by ``cross_source_synthesis.license_relation`` from the
    certified relation engines (``edges`` = ContradictionEdge list, the agreement map). KEEP-ALL: the
    analytical unit is additive on top of the single-source units; the idx8 footprint dedup below never
    collapses it (its two-token footprint is a SUPERSET of either atom's), so no source/basket vanishes.

    I-beatboth-011 (#1289):
      §3.5 placeholder-leak — DROP any per-basket result that is the internal insufficient-evidence
        marker before appending (the same filter the sibling multi-cite path already applies at the
        `_per_basket_verified_clause` :337-338 precedent). An empty post-suppression section routes
        through the existing gap/abort handling (the producer no longer guarantees one unit per basket
        when that unit would be the internal marker — leaking the marker into report.md is the bug).
      idx8 seen-span — DROP a composed unit ONLY when it is a TRUE duplicate: ALL of its RESOLVED
        (ev_id,start,end) provenance tuples already appear in an emitted sibling in THIS section AND its
        whitespace-normalized text is byte-identical to that sibling (faithfulness-neutral — a true
        duplicate adds nothing). A SUBSET span alone does NOT prove the same claim (Codex #1289 iter-1
        P1: different prose can cite an overlapping span), so a DIFFERING claim that merely shares a
        span subset is KEPT. A unit with NO provenance token is NEVER dropped (zero tokens must not be
        vacuously "all duplicate").

    I-beatboth-011 keystone-F1 (#1284): when ``PG_VERIFIED_COMPOSE_MULTICITED`` is ON (DEFAULT-OFF =>
    byte-identical), a basket carrying >=2 corroborating isolated-``SUPPORTS`` members is composed via
    ``compose_basket_multicited_sentence`` — ONE multi-cited sentence surfacing ALL its corroborators
    (the §-1.3 consolidate-keep-all reading) instead of collapsing to the single strongest member.
    A single-``SUPPORTS`` (or zero) basket routes the UNCHANGED ``_compose_one_basket`` path. The
    relational-quantifier guard inside the multi-cited producer drops any unlicensed aggregate predicate;
    each clause still passes the UNCHANGED ``strict_verify`` per-clause. The downstream §3.5 marker filter
    + idx8 seen-span dedup are applied identically to the multi-cited unit."""
    out: list[str] = []
    seen_spans: set[tuple[str, int, int]] = set()
    seen_texts: set[str] = set()
    # I-arch-011 #1269 B11 (compose-repetition): a SECOND, stronger key — the exact resolved-span
    # FOOTPRINT (frozenset) already emitted -> the union of its kept number tokens. A later unit with
    # the IDENTICAL footprint that adds NO new number is a pure reword of an already-rendered span ->
    # collapse (the 18x-same-span degenerate-repetition defect). This is footprint EQUALITY, not the
    # subset key Codex #1289 rejected, and it is faithfulness-neutral (same span, already verified).
    seen_numbers_by_footprint: dict[frozenset, frozenset[str]] = {}
    _multicited_on = _multicited_compose_enabled()
    for basket in (section_baskets or []):
        # keystone-F1: surface a >=2-corroborator basket as ONE multi-cited sentence (flag-gated,
        # default-OFF). A single-source basket falls through to the UNCHANGED single-basket producer
        # (the multi-cited producer itself returns the same K-span draft for <2 SUPPORTS, but routing
        # explicitly keeps the default-OFF path byte-identical with NO new import/call when the flag is
        # off, and only invokes the new producer for genuinely-corroborated baskets when on).
        if _multicited_on and len(_distinct_origin_supports(basket)) >= 2:
            composed = compose_basket_multicited_sentence(
                basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
            ) or ""
        else:
            composed = _compose_one_basket(
                basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
            )
        # §3.5: suppress the internal insufficient-evidence marker before it can leak into report.md.
        # Also skip an empty multi-cited result (a basket with no resolvable span at all) — the §3.5
        # filter for ``_compose_one_basket`` never sees an empty unit (it always returns at least the
        # disclosure), but the multi-cited producer can return ``""`` when even the K-span is absent;
        # an empty unit must not be appended (it would render a blank line, never a silent success).
        if not composed.strip() or composed.strip().startswith("[insufficient verified evidence"):
            continue
        # idx8 (Codex #1289 P1): drop a unit ONLY when it is a true duplicate — its resolved spans are
        # already emitted AND its normalized text is byte-identical to a sibling. Requiring text
        # identity (not merely a span subset) keeps every differing claim. Apply AFTER the §3.5 marker
        # filter so a token-less marker never reaches this check.
        spans = _resolved_spans(composed)
        norm = " ".join(composed.split())
        footprint = frozenset(spans)
        # I-arch-011 #1269 B11: footprint-EQUALITY same-span collapse (the 18x-degenerate-repetition
        # defect). A unit whose EXACT footprint was already emitted AND that adds NO new number token is
        # a pure reword of an already-rendered span -> drop (faithfulness-neutral; same verified span).
        # The conservative number carve-out keeps a same-span unit that states a genuinely NEW statistic.
        if footprint and footprint in seen_numbers_by_footprint:
            unit_numbers = _number_tokens(composed)
            if not (unit_numbers - seen_numbers_by_footprint[footprint]):
                continue
            seen_numbers_by_footprint[footprint] = seen_numbers_by_footprint[footprint] | unit_numbers
        # idx8 legacy key (subset-of-already-emitted + byte-identical text) — retained so a unit whose
        # spans are a SUBSET (not equal) of an emitted sibling AND is text-identical still collapses.
        if spans and spans <= seen_spans and norm in seen_texts:
            continue
        if footprint and footprint not in seen_numbers_by_footprint:
            seen_numbers_by_footprint[footprint] = _number_tokens(composed)
        seen_spans |= spans
        seen_texts.add(norm)
        out.append(composed)

    # I-deepfix-001 M6: ADDITIVE cross-source analytical pass. DEFAULT-OFF => byte-identical (no import,
    # no call). ON => append analytical sentences (two engine-licensed verified atoms) on top of the
    # keep-all single-source units. Each analytical unit carries TWO distinct [#ev] tokens whose two-span
    # footprint is a SUPERSET of either atom's, so the idx8 footprint-dedup above (applied identically
    # below) can never collapse it against an atom — keep-all holds. The downstream
    # _rewrite_draft_with_spans + UNCHANGED strict_verify tail gates each analytical sentence per clause.
    if _cross_source_synthesis_enabled():
        from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: PLC0415
            compose_cross_source_analytical_units,
        )
        analytical = compose_cross_source_analytical_units(
            section_baskets, evidence_pool,
            writer_fn=writer_fn, verify_fn=verify_fn,
            edges=edges, equiv_clusters=equiv_clusters, agree_map=agree_map,
        )
        for unit in analytical:
            if not unit or not unit.strip():
                continue
            spans = _resolved_spans(unit)
            norm = " ".join(unit.split())
            footprint = frozenset(spans)
            # Same footprint-equality + subset dedup contract as the per-basket loop above (so a
            # true-duplicate analytical unit collapses) — but the two-span footprint guarantees a real
            # cross-source unit is never a subset of a single-source sibling.
            if footprint and footprint in seen_numbers_by_footprint:
                unit_numbers = _number_tokens(unit)
                if not (unit_numbers - seen_numbers_by_footprint[footprint]):
                    continue
                seen_numbers_by_footprint[footprint] = seen_numbers_by_footprint[footprint] | unit_numbers
            if spans and spans <= seen_spans and norm in seen_texts:
                continue
            if footprint and footprint not in seen_numbers_by_footprint:
                seen_numbers_by_footprint[footprint] = _number_tokens(unit)
            seen_spans |= spans
            seen_texts.add(norm)
            out.append(unit)
    return out


def _section_baskets_for_compose(section: Any, credibility_analysis: Any) -> list:
    """ALL baskets whose verified members back evidence assigned to THIS section (primary, not
    augment: contract-entity baskets are a SUBSET). A basket belongs to the section if any of its
    member evidence_ids is in the section's assigned ev_ids. Deterministic; order follows the
    credibility_analysis.baskets order. None/empty => [] (caller keeps the legacy path)."""
    baskets = list(getattr(credibility_analysis, "baskets", None) or [])
    if not baskets:
        return []
    section_ev_ids = _section_assigned_ev_ids(section)
    if not section_ev_ids:
        return []
    out: list = []
    for b in baskets:
        member_ids = {str(getattr(m, "evidence_id", "") or "") for m in getattr(b, "supporting_members", None) or []}
        if member_ids & section_ev_ids:
            out.append(b)
    return out


# ── I-deepfix-001 WS-3 (#1344) — NO-PROVENANCE-TOKEN LEAK REPAIR ─────────────────────────────────
#
# THE LEAK (drb_72 ``no_provenance_token=34``): an abstractive-writer sentence that arrives with NO
# ``[#ev:...]`` provenance token is silently DROPPED by strict_verify — so a claim genuinely supported
# by a corroborating basket span never renders and its source never counts toward breadth. Instead of
# dropping, REPAIR it: bind the NEAREST supporting basket's OWN verified clause (via the per-basket
# verified contract ``_per_basket_verified_clause``, :665) BEFORE strict_verify. The emitted clause is
# that basket's own strict_verify-PASSED span carrying a real ``[#ev]`` token — faithful-BY-CONSTRUCTION,
# exactly the QUOTATION-is-faithful philosophy the K-span fallback already uses everywhere in this module.
#
# §-1.3 / FAITHFULNESS: this NEVER fabricates a binding. It does NOT keep the untokened sentence and it
# does NOT staple a token onto it; it REPLACES it with the nearest overlapping basket's verified clause.
# "Nearest" = maximum shared content-word overlap between the sentence and the basket's claim + its
# isolated-``SUPPORTS`` members' spans, requiring >= ``min_overlap`` (default 2, mirroring the
# strict_verify >=2-content-word invariant) so an UNRELATED basket is never bound. If NO candidate basket
# clears the overlap bar AND yields a verified clause, the sentence is STILL dropped (returns ``None``) —
# the repair can only ADD a faithful cited clause where the legacy path rendered nothing; it can never
# make the output less faithful. The frozen faithfulness engine (strict_verify / NLI / provenance /
# span-grounding) is UNTOUCHED: the returned clause re-passes the UNCHANGED strict_verify per clause.
# Default-ON; ``PG_NO_TOKEN_SENTENCE_REPAIR=0`` => an untokened sentence returns ``None`` (the legacy
# drop) => byte-identical.
_NO_TOKEN_REPAIR_ENV = "PG_NO_TOKEN_SENTENCE_REPAIR"
_DEFAULT_REPAIR_MIN_OVERLAP = 2

# Content-word extractor for the nearest-basket selection: alphabetic-led tokens >= 3 chars, minus a
# small closed stopword set. Provenance tokens are stripped first so span offsets never count as content.
_CONTENT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
_REPAIR_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "had", "was", "were",
    "are", "been", "will", "would", "could", "should", "their", "there", "these", "those",
    "which", "while", "when", "where", "what", "who", "whom", "into", "than", "then", "such",
    "also", "not", "but", "its", "our", "your", "his", "her", "they", "them", "some", "more",
    "most", "over", "under", "between", "among", "per", "via", "about", "each", "any", "all",
})


def no_token_sentence_repair_enabled() -> bool:
    """Kill-switch ``PG_NO_TOKEN_SENTENCE_REPAIR`` (default ON). OFF => an untokened abstractive
    sentence is NOT repaired (``repair_untokened_sentence`` returns ``None``) => the legacy silent
    drop => byte-identical."""
    return os.getenv(_NO_TOKEN_REPAIR_ENV, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _repair_content_words(text: str) -> set:
    """Lowercased content words in ``text`` (>=3 chars, minus stopwords); provenance tokens stripped."""
    stripped = _EV_TOKEN_RE.sub(" ", text or "")
    return {
        w.lower()
        for w in _CONTENT_WORD_RE.findall(stripped)
        if w.lower() not in _REPAIR_STOPWORDS
    }


def _basket_repair_content_words(basket: Any) -> set:
    """The content words the basket's claim + its isolated-``SUPPORTS`` member spans carry (the overlap
    target for nearest-basket selection). Pure read; no faithfulness state touched."""
    parts = [
        str(getattr(basket, "claim_text", "") or ""),
        str(getattr(basket, "subject", "") or ""),
        str(getattr(basket, "predicate", "") or ""),
    ]
    for m in _basket_supports_members(basket):
        parts.append(str(getattr(m, "direct_quote", "") or ""))
    return _repair_content_words(" ".join(parts))


def repair_untokened_sentence(
    sentence: str,
    baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    min_overlap: int = _DEFAULT_REPAIR_MIN_OVERLAP,
) -> Optional[str]:
    """Repair an abstractive-writer sentence that carries NO provenance token by binding the NEAREST
    supporting basket's verified clause (via ``_per_basket_verified_clause``), so its source counts as
    breadth instead of being silently dropped.

    Returns:
      * the ORIGINAL ``sentence`` unchanged when it ALREADY carries a ``[#ev:...]`` token (only an
        untokened sentence is a repair candidate — a tokened one is handled by the normal path);
      * a verified, tokened clause (the nearest overlapping basket's OWN strict_verify-PASSED span)
        when a real ``SUPPORTS`` span can be bound;
      * ``None`` when the flag is OFF, the sentence is empty/wordless, or NO candidate basket clears the
        overlap bar AND yields a verified clause — the sentence is then STILL dropped (never fabricate a
        binding).

    §-1.3: the untokened sentence is REPLACED by the bound basket's verified clause, never kept and
    never given a fabricated token; the clause re-passes the UNCHANGED ``strict_verify`` per clause. The
    caller supplies the production ``writer_fn`` / ``verify_fn`` (the same ones every compose path uses),
    so the repair adds NO new model and touches NO gate.
    """
    if not sentence or not sentence.strip():
        return None
    # A sentence that already cites a span is not this path's concern — return it untouched.
    if _EV_TOKEN_RE.search(sentence):
        return sentence
    if not no_token_sentence_repair_enabled():
        return None  # legacy: an untokened sentence is dropped
    sentence_words = _repair_content_words(sentence)
    if not sentence_words:
        return None
    # Rank candidate baskets that carry an isolated-``SUPPORTS`` span by content-word overlap
    # (nearest first). A basket with no SUPPORTS span cannot bind a verified clause -> skipped.
    ranked: list = []
    for basket in (baskets or []):
        if not _basket_supports_members(basket):
            continue
        overlap = len(sentence_words & _basket_repair_content_words(basket))
        if overlap >= min_overlap:
            ranked.append((basket, overlap))
    ranked.sort(key=lambda t: t[1], reverse=True)
    for basket, _overlap in ranked:
        clause = _per_basket_verified_clause(
            basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
        )
        if clause:  # carries a real [#ev] token + passed strict_verify per clause
            return clause
    return None  # no real SUPPORTS span could be bound -> still dropped (never fabricated)


def _section_assigned_ev_ids(section: Any) -> set:
    """The evidence_ids assigned to a section plan, read defensively across the plan shapes
    (``ev_ids`` list, or rows carrying ``evidence_id``). Empty set when unresolvable."""
    ids: set = set()
    raw = getattr(section, "ev_ids", None)
    if raw:
        ids |= {str(x) for x in raw if x}
    rows = getattr(section, "evidence", None) or getattr(section, "rows", None)
    for row in (rows or []):
        eid = (row or {}).get("evidence_id") if isinstance(row, dict) else getattr(row, "evidence_id", None)
        if eid:
            ids.add(str(eid))
    ids.discard("")
    return ids
