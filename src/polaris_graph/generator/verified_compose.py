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

import logging
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

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

# I-deepfix-001 Wave-1a (#1344) — SYNTH_PRIMARY: compose-then-verify. Default-OFF (LAW VI): when unset/off
# ``_compose_one_basket`` is byte-identical (first-failure break + K-span glue + disclosure UNCHANGED);
# ON *and* the caller threads a group-capable re-draft writer, the writer drafts one coherent paragraph
# per basket FIRST, then the UNCHANGED verify_fn filters each sentence downstream, a bounded whole-
# paragraph repair loop re-drafts failing sentences up to ``PG_WRITER_REPAIR_MAX``, and on exhaustion the
# uncovered-fact K-span renders as a SEPARATE labeled disclosure paragraph (never mid-line glued). The
# faithfulness engine is NEVER touched — only which draft is submitted changes.
_SYNTH_PRIMARY_ENV = "PG_SYNTH_PRIMARY"
_WRITER_REPAIR_MAX_ENV = "PG_WRITER_REPAIR_MAX"
_WRITER_REPAIR_MAX_DEFAULT = 2  # bounded whole-paragraph re-draft attempts (LAW VI; clamp >= 0)

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


def _canon_number(tok: str) -> str:
    """Canonicalize a number token for the L2 distinct-fact novelty test — strip thousands-separator
    commas so ``"400,000"`` and ``"400000"`` compare equal. Any residual collision under this
    normalization can only make two DIFFERENT numbers look EQUAL, which can only cause the additive
    pass to SKIP a candidate (under-emit) — never to falsely surface a duplicate. So the normalization
    is duplication-safe by direction. Pure."""
    return (tok or "").replace(",", "")


def _bare_integer_numbers(text: str) -> set[str]:
    """The comma-normalized BARE-INTEGER number tokens in ``text`` — number tokens that are NEITHER
    decimals (contain a ``.``) NOR percent-expressed integers (immediately followed by ``%`` /
    ``percent``). These are the absolute counts, currency amounts, year/date data, and multipliers that
    the abstractive writer's numeric-completeness gate (``abstractive_writer.make_writer_verify_fn``
    P1-3) does NOT force into the one-sentence paraphrase — so they are the numbers a headline can DROP
    on the SUCCESS path, and thus the ONLY numbers the L2 additive pass triggers on. Decimals and
    percent-integers are SUBSTANTIVE (P1-3 forces them into the headline) and are owned by the
    companion-figure pass; excluding them here keeps this pass byte-identical on percent/decimal-only
    content and non-overlapping with companion-figure. Provenance ``[#ev:...]`` tokens are stripped
    first so span offsets never count as content numbers. Pure."""
    stripped = _EV_TOKEN_RE.sub(" ", text or "")
    out: set[str] = set()
    for m in _NUMBER_TOKEN_RE.finditer(stripped):
        tok = m.group(0)
        if "." in tok:
            continue  # decimal -> substantive (headline-forced) -> not a droppable bare integer
        tail = stripped[m.end():m.end() + 9].lstrip()
        if tail.startswith("%") or tail[:7].lower().startswith("percent"):
            continue  # percent-expressed integer -> substantive -> owned by the companion-figure pass
        out.add(_canon_number(tok))
    return out


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
    """PG_CROSS_SOURCE_SYNTHESIS gate (I-deepfix-001 M6; DEFAULT-ON per I-deepfix-001 cov C2).

    ON (the new default) => after the per-basket units are built, ADDITIVELY append engine-LICENSED
    cross-source analytical sentences (compare / contrast / agreement / extension) on top of the
    keep-all single-source units, so the DRB-II analysis dimension fires on EVERY render path — not
    only when the benchmark slate force-pins the flag. Each appended sentence joins TWO already
    strict_verify-PASSED atoms with an engine-licensed connective and RE-PASSES the FROZEN
    strict_verify per clause; an UNLICENSED pair stays neutral (never a fabricated relation word) and
    a clause that fails re-verify is DROPPED — faithfulness NEVER relaxed.

    Kill-switch (LAW VI): ``PG_CROSS_SOURCE_SYNTHESIS=0`` (or false/off/no) => the producer is never
    invoked and the section producer is BYTE-IDENTICAL to the pre-cov legacy path. §-1.3: this is a
    WEIGHT/CONSOLIDATE analysis lever (more synthesized relations = honest emergent depth), never a
    cap / target / thinner."""
    return os.getenv(_CROSS_SOURCE_SYNTHESIS_ENV, "1").strip().lower() not in ("", "0", "false", "off", "no")


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


# ─────────────────────────────────────────────────────────────────────
# I-deepfix-001 Wave-3 PART 1 (#1344) — COMPANION-FIGURE COMPOSE
#
# THE OMISSION (drb_72 one-sidedness): the composed headline states ONE percent (e.g.
# "1.8% of jobs") while the SAME SUPPORTS member's direct_quote also carries a materially-
# different SAME-KIND companion percent (e.g. "46% of tasks") that the headline drops.
# ``overstatement_guard.primacy_frame_reason`` already DETECTS exactly this pattern but only
# APPENDS a soft advisory; it never surfaces the companion figure in prose. This pass surfaces
# it — as a VERBATIM slice of that member's own direct_quote, tagged with the member's REAL
# global offsets, and re-verified by the UNCHANGED ``strict_verify`` (``verify_fn``). It reuses
# the SAME primacy gate constants (``_PRIMACY_MIN_ABS_GAP_PCT`` / ``_PRIMACY_MIN_RATIO`` /
# shared measure-stem) so the surfaced companion and the advisory label ALWAYS agree.
#
# FAITHFULNESS (by construction): every surfaced sentence IS a real cited span (a substring of a
# SUPPORTS member's direct_quote at that member's real offsets), carries NO connective / lead-in
# / aggregate predicate (zero non-span words added — identical semantics to ``_member_verbatim_clause``),
# and must PASS ``verify_fn`` AND land within the basket's own member regions (``_tokens_within_basket_regions``)
# to be kept. It can only ever emit a number that literally appears in a real cited span; it never
# fabricates a figure, never invents a frame, never asserts corroboration (each sentence is one
# source's own words), and never touches the >=2 distinct-origin floor. Default-ON; OFF => the pass
# never runs => byte-identical.
_COMPANION_FIGURE_COMPOSE_ENV = "PG_COMPANION_FIGURE_COMPOSE"


def _companion_figure_compose_enabled() -> bool:
    """PG_COMPANION_FIGURE_COMPOSE gate (mirrors ``_snap_span_enabled``): default-ON; only an
    explicit 0/false/off/no disables. An EMPTY string behaves like UNSET (stays ON), so a blank
    env var cannot silently disable the companion-figure pass."""
    return os.getenv(_COMPANION_FIGURE_COMPOSE_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


# I-deepfix-001 #1344 — L2 ADDITIVE DISTINCT-FACT gate (the ADDITIVE arm of sub-topic decomposition,
# Item 11). L2's multi-fact producer (``build_multi_member_sentences`` / ``build_verified_span_draft_multi``)
# today only surfaces its extra distinct facts as a per-basket FALLBACK — it fires ONLY when the
# abstractive winner's prose FAILS strict_verify. On the abstractive SUCCESS path those extra facts
# never render. This pass makes L2 ADDITIVE: after the headline is kept, surface the DISTINCT bare-integer
# facts a basket already grounds that the abstractive paraphrase DROPPED — each a VERBATIM span slice
# re-verified by the UNCHANGED strict_verify, ADDITIVE to (never replacing) the headline.
# DEFAULT-OFF (LAW VI): OFF ⇒ the pass never runs ⇒ byte-identical. Default-OFF (not ON) because this
# pass surfaces general non-percent source sentences — the SAME content space as the qualifier-elaboration
# sibling (also default-OFF), so it must be opted in per-run and its effect validated in a small real run
# before the large paid run (operator preflight discipline). §-1.3 CONSOLIDATE-keep-all (lifts
# already-verified content; drops nothing). Kill-switch PG_SUBTOPIC_ADDITIVE_FACTS.
_SUBTOPIC_ADDITIVE_FACTS_ENV = "PG_SUBTOPIC_ADDITIVE_FACTS"


def _subtopic_additive_facts_enabled() -> bool:
    """PG_SUBTOPIC_ADDITIVE_FACTS gate (mirrors ``_qualifier_elaboration_enabled``): DEFAULT-OFF =>
    byte-identical; an explicit 1/true/on/yes turns the L2 additive distinct-fact pass ON. An unset or
    blank env var stays OFF (a new content-surfacing pass must be opted in, never silently on)."""
    return os.getenv(_SUBTOPIC_ADDITIVE_FACTS_ENV, "0").strip().lower() in ("1", "true", "on", "yes")


# I-deepfix-001 D1 (#1344) — WITHIN-BASKET QUALIFIER ELABORATION gate. DEFAULT-OFF (LAW VI): the
# additive within-basket pass runs only when the flag is explicitly set. OFF => the pass never runs =>
# byte-identical. Sibling of the companion-figure pass (same faithfulness contract: surface MORE of a
# basket member's OWN verbatim, already-strict_verify-passing content — here a QUALIFIER clause
# (population/scope, timeframe, magnitude context, mechanism, stated limitation) instead of a companion
# percent). It NEVER adds a connective / aggregate / relational predicate (zero non-span words), so it
# cannot mint an unlicensed frame and never touches the >=2 distinct-origin floor (single-source
# attribution, exactly like the headline). It STRENGTHENS faithfulness (fuller, still-verified
# expression) and drops nothing.
_QUALIFIER_ELABORATION_ENV = "PG_QUALIFIER_ELABORATION"


def _qualifier_elaboration_enabled() -> bool:
    """PG_QUALIFIER_ELABORATION gate (D1). DEFAULT-OFF => byte-identical; an explicit
    1/true/on/yes turns the additive within-basket qualifier-elaboration pass ON."""
    return os.getenv(_QUALIFIER_ELABORATION_ENV, "0").strip().lower() in ("1", "true", "on", "yes")


# The CLOSED qualifier-cue vocabulary (D1). A member sentence is ELIGIBLE for elaboration iff it
# matches at least one cue AND is not already surfaced in the headline. This is purely a SELECTION
# filter for WHICH already-verified member sentences to lift — it never affects faithfulness (the
# lifted sentence re-passes the UNCHANGED strict_verify + own-region gate regardless). Grouped only for
# readability; matched case-insensitively as whole-word / phrase cues. Kept intentionally conservative:
# a miss lifts LESS (never a faithfulness risk), a false-hit still re-verifies as the source's own words.
_QUALIFIER_CUES: tuple[str, ...] = (
    # population / scope
    r"patients?", r"participants?", r"adults?", r"children", r"women", r"men",
    r"population", r"cohort", r"sample", r"subgroup", r"aged", r"years?\s+old",
    r"among", r"enrolled", r"randomi[sz]ed", r"eligible",
    # timeframe
    r"weeks?", r"months?", r"years?", r"days?", r"follow[- ]?up", r"baseline",
    r"duration", r"over\s+a?\s*period", r"median\s+follow", r"during",
    # magnitude context
    r"compared\s+(?:with|to)", r"relative\s+to", r"versus", r"\bvs\.?\b",
    r"reduction", r"increase", r"[- ]fold", r"percentage\s+points?",
    r"absolute", r"relative\s+risk", r"hazard\s+ratio", r"odds\s+ratio",
    r"confidence\s+interval", r"95%\s*ci",
    # mechanism
    r"because", r"due\s+to", r"mechanism", r"mediated", r"pathway", r"receptor",
    r"inhibit", r"activat", r"caused\s+by", r"driven\s+by", r"attributable\s+to",
    # stated limitation / caveat
    r"limitation", r"however", r"although", r"caveat", r"uncertain",
    r"not\s+statistically\s+significant", r"small\s+sample", r"generali[sz]",
    r"\bbias\b", r"confound", r"limited\s+by", r"did\s+not\s+reach",
)
_QUALIFIER_CUE_RE = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(_QUALIFIER_CUES) + r")", re.IGNORECASE,
)


def _sentence_carries_qualifier(text: str) -> bool:
    """True iff ``text`` matches at least one closed qualifier cue (D1 selection filter). Pure."""
    return bool(_QUALIFIER_CUE_RE.search(text or ""))


# I-deepfix-001 Wave-3 PART 2 ARM B (#1344) — DEGRADED-VERIFY HONEST DISCLOSURE gate.
# When a basket yields NO ENTAILMENT_VERIFIED span but carries >=1 member whose OWN span
# DETERMINISTICALLY grounds the claim and whose entailment tier is DETERMINISTIC_ONLY (the judge
# 429'd / timed out this run), the bare "insufficient verified evidence" gap reads as "no evidence"
# — dishonest, because the evidence exists and grounds deterministically; only the judge was
# unavailable. ARM B emits a DISTINCT "verification incomplete" label instead. It NEVER promotes
# DETERMINISTIC_ONLY prose into verified text — only the gap LABEL changes; the hard
# ENTAILMENT_VERIFIED gate is untouched. Default-ON; OFF => the bare gap for both causes =>
# byte-identical.
_DEGRADED_VERIFY_DISCLOSURE_ENV = "PG_DEGRADED_VERIFY_DISCLOSURE"


def _degraded_verify_disclosure_enabled() -> bool:
    """PG_DEGRADED_VERIFY_DISCLOSURE gate (mirrors ``_snap_span_enabled``): default-ON; only an
    explicit 0/false/off/no disables. OFF => ``_no_verified_span_disclosure`` returns the bare
    insufficient-evidence gap for both causes => byte-identical."""
    return os.getenv(_DEGRADED_VERIFY_DISCLOSURE_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


_SNAP_MEMBER_BOUNDARY_ENV = "PG_SNAP_MEMBER_BOUNDARY"


def _snap_member_boundary_enabled() -> bool:
    """I-deepfix-001 tail-B1 (#1344, finding #8) kill-switch (default ON). OFF => the forward
    span-snap is NOT capped against a sibling member's span => byte-identical to the pre-fix snap."""
    return os.getenv(_SNAP_MEMBER_BOUNDARY_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


def _snap_cap_to_sibling_member(
    basket: Any, member: Any, haystack: str, start: int, end: int, evidence_pool: dict
) -> int:
    """finding #8: the max ``snap_end`` that does NOT cross into ANOTHER basket ``SUPPORTS`` member's
    OWN verified quote located within THIS member's row ``haystack``. PURE; shrink-only (>= ``end``).

    THE BUG: a merged multi-source sentence inherited only the FIRST source's citation — the report
    cited ev_036's Philippine text under ev_051's number [13] while it is correctly [14] elsewhere.
    When two members' quotes co-occur in one fetched row (or a member carries two spans of the same
    source), the FORWARD sentence-boundary snap of the first member's span can extend PAST the second
    member's span start and emit that second span's text under the FIRST member's single ``[#ev]``
    token — one source's content mis-attributed to another's citation. Capping the snap at the nearest
    sibling-member span start keeps each carried-up span bound to its OWN evidence_id / ``[#ev]`` token
    (its own ``[N]``), so a sibling's span never resolves under the wrong number. Faithfulness-neutral:
    the cap can only SHRINK an over-extended snap; it never widens a span and never relaxes a verdict.
    Returns ``len(haystack)`` when no sibling span sits after ``end``."""
    this_eid = str(getattr(member, "evidence_id", "") or "")
    boundary = len(haystack)
    for other in _basket_supports_members(basket):
        if other is member:
            continue
        o_eid = str(getattr(other, "evidence_id", "") or "")
        if o_eid and o_eid == this_eid:
            # Same-source sibling: cap at ITS span start (offsets index the same row) if it is after
            # this member's verified span end.
            o_span = _member_global_span(other, evidence_pool)
            if o_span is not None and end <= o_span[0] < boundary:
                boundary = o_span[0]
            continue
        # Different-source sibling whose quote physically co-occurs in THIS member's row text: cap at
        # the first occurrence after `end` so the snap never swallows the sibling's span.
        o_quote = str(getattr(other, "direct_quote", "") or "").strip()
        if not o_quote:
            continue
        idx = haystack.find(o_quote, end)
        if idx != -1 and idx < boundary:
            boundary = idx
    return boundary


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
    # I-deepfix-001 P1_chrome_gate (#1344): make the ALL-CHROME-basket drop LOUD. When a member
    # resolves a verified span but EVERY one of its sentence units is screened out as chrome, the
    # basket silently falls through to the insufficient-evidence disclosure. Count those events and
    # emit a run-log canary if the whole draft returns None so an all-chrome basket dropping to a
    # disclosure is VISIBLE, not silent. MEASUREMENT-ONLY — never promotes a unit, never a verdict.
    all_chrome_member_drops = 0
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
            # finding #8: never let the forward snap cross into a sibling member's span (which would
            # emit that sibling's text under THIS member's single [#ev] token / [N]).
            if _snap_member_boundary_enabled():
                snap_end = min(
                    snap_end,
                    _snap_cap_to_sibling_member(basket, m, haystack, start, end, evidence_pool),
                )
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
        units_before = len(units)
        units = [
            u for u in units
            if not _compose_junk_screen(u, known_words, require_sentence_form=True)
        ]
        if units_before and not units:
            # every sentence unit of this member's verified span was screened as chrome.
            all_chrome_member_drops += 1
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
    if all_chrome_member_drops:
        subject = str(
            getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim"
        ).strip()
        logger.warning(
            "[verified_compose] P1_chrome_gate canary: all-chrome-basket drop — "
            "%d member(s) resolved a verified span but ALL its sentence units screened as chrome; "
            "basket falls through to the insufficient-evidence disclosure: %.160s",
            all_chrome_member_drops,
            subject,
        )
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
        # I-deepfix-001 FIX-D (extend-only SUPERSET span snap): the DEFAULT (non-abstractive) section
        # producer uses THIS deterministic short writer as its primary writer_fn, so its verbatim output
        # is emitted directly (the snapped K-span fallback in build_verified_span_draft never runs on
        # this path). If the selected first sentence ends MID-CLAUSE (the extractor cut the quote, e.g.
        # "...defined by the"), EXTEND it forward to the next sentence boundary IN THE SAME ROW so the
        # emitted clause is not left dangling. Extend-ONLY -> the widened slice is a SUPERSET within the
        # SAME row -> grounded by construction (the widened token covers exactly the emitted text), never
        # fabricates. Fail-OPEN (span kept AS-IS) when no clean extension exists within the source row.
        # Mirrors build_verified_span_draft; byte-identical when no snap applies. Default-ON.
        if _snap_span_enabled():
            row = (evidence_pool or {}).get(eid) or {}
            haystack = str(row.get("direct_quote") or row.get("statement") or "")
            snapped_end = _snap_span_end_to_sentence(haystack, tok_start, tok_end)
            if snapped_end > tok_end and 0 <= tok_start < snapped_end <= len(haystack):
                first = haystack[tok_start:snapped_end]
                tok_end = snapped_end
        # I-beatboth-009 (#1287): emit the token BEFORE the terminal period so split_into_sentences
        # keeps it attached (the prior "first. [#ev:...]" orphaned the token -> no_provenance_token ->
        # verified=0). tok_start/tok_end are UNCHANGED (they still index the member's real global span),
        # so faithfulness is identical — only the display punctuation moves.
        first_display = _strip_terminal_punct(first)
        return f"{first_display} [#ev:{eid}:{tok_start}-{tok_end}]."
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# L2 — SUB-TOPIC DECOMPOSITION (I-deepfix-001 #1344, Box C coverage lever; DRB-II Recall).
#
# The per-basket producers above emit ~ONE headline (build_short_member_sentence = the FIRST unit of
# the strongest member; build_verified_span_draft returns on the FIRST member that resolves a span).
# When a basket ALREADY GROUNDS several DISTINCT atomic facts — a rich member span carrying multiple
# sentences, or corroborators that each add a new fact — those extra facts never render. L2 surfaces
# them: emit ONE verified verbatim-span sentence PER DISTINCT atomic fact the basket grounds, deduped
# so a fact corroborated by many sources renders ONCE (the sources stay in the pool + multi-citation;
# §-1.3 CONSOLIDATE-keep-all — L2 NEVER drops a source). More Recall from the corpus already fetched;
# ZERO new fetching.
#
# FAITHFULNESS-NEUTRAL BY CONSTRUCTION (constraint 1, never a relax): every emitted sentence is a
# VERBATIM span carrying its own member's real ``[#ev:<id>:<a>-<b>]`` provenance token, so it re-passes
# the UNCHANGED strict_verify / NLI / 4-role D8 / provenance / span-grounding trivially (it IS the
# verified span). L2 adds NO gate, relaxes none. Kill-switch PG_SUBTOPIC_DECOMPOSITION (LAW VI);
# default ON => OFF is byte-identical to the single-headline producers above. The per-basket count is
# bounded by a generous CEILING (PG_SUBTOPIC_MAX_FACTS, a runaway guard billed by ACTUAL distinct
# facts, NOT a target — §-1.3 forbids a forced breadth number).
_SUBTOPIC_DECOMP_ENV = "PG_SUBTOPIC_DECOMPOSITION"
_SUBTOPIC_DECOMP_OFF_TOKENS = frozenset({"0", "false", "off", "no"})
_SUBTOPIC_MAX_FACTS_ENV = "PG_SUBTOPIC_MAX_FACTS"
_SUBTOPIC_MAX_FACTS_DEFAULT = 40  # CEILING (runaway guard), NOT a target; billed by actual facts.
_SUBTOPIC_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")


def _subtopic_decomposition_enabled() -> bool:
    """Return True iff PG_SUBTOPIC_DECOMPOSITION is not an off token (default ON = decompose)."""
    raw = os.environ.get(_SUBTOPIC_DECOMP_ENV)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _SUBTOPIC_DECOMP_OFF_TOKENS


def _subtopic_max_facts() -> int:
    """Per-basket CEILING on emitted distinct atomic facts (runaway guard, billed by actual use)."""
    raw = os.environ.get(_SUBTOPIC_MAX_FACTS_ENV, "")
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        n = 0
    return n if n > 0 else _SUBTOPIC_MAX_FACTS_DEFAULT


def _atomic_fact_key(unit: str) -> str:
    """Normalized dedup key for an atomic-fact sentence unit: strip any provenance token, drop
    punctuation, collapse whitespace, lowercase. Two units with the same key are the SAME atomic fact
    (the corroboration is preserved as multi-citation / pool membership elsewhere — L2 only avoids
    repeating the SENTENCE, it never drops a source). Conservative (near-exact): only a genuine repeat
    collapses, so a DISTINCT fact is never lost (precision-first)."""
    core = _SUBTOPIC_EV_TOKEN_RE.sub("", unit or "")
    core = re.sub(r"[^\w\s]", " ", core, flags=re.UNICODE)
    return " ".join(core.split()).lower()


def build_multi_member_sentences(basket: Any, evidence_pool: dict) -> str:
    """L2 DETERMINISTIC multi-fact writer (region-safe ``writer_fn`` form). Emits one verbatim-span
    sentence per DISTINCT atomic fact across ALL of the basket's isolated-``SUPPORTS`` members, deduped
    by ``_atomic_fact_key``. Each unit carries TIGHT per-unit global offsets inside its member's quote
    (NO forward snap), so every emitted token lands strictly WITHIN that member's own region — it passes
    the UNCHANGED ``_compose_one_basket`` strict_verify + P1-1 region gate exactly like
    ``build_short_member_sentence``. Cut-mid-word units are screened by ``_compose_junk_screen``
    (require_sentence_form); if EVERY unit screens out this returns "" so ``_compose_one_basket`` falls
    to the SNAP-preserving K-span fallback (``build_verified_span_draft_multi``), which recovers a cut
    quote — so L2 never REGRESSES the single-headline recall. When PG_SUBTOPIC_DECOMPOSITION is OFF this
    is byte-identical to ``build_short_member_sentence`` (single headline)."""
    if not _subtopic_decomposition_enabled():
        return build_short_member_sentence(basket, evidence_pool)
    known_words = _known_words_for_compose(evidence_pool)
    limit = _subtopic_max_facts()
    seen: set[str] = set()
    out: list[str] = []
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        gspan = _member_global_span(m, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        start, _end = gspan
        units = [u.strip() for u in (split_into_sentences(quote) or [quote]) if u.strip()]
        # INPUT HYGIENE (P1-4): drop crawl/social/masthead chrome + truncated fragments; keep real
        # short sentences. require_sentence_form drops a mid-word cut fragment (no forward snap here).
        units = [
            u for u in units
            if not _compose_junk_screen(u, known_words, require_sentence_form=True)
        ]
        for u in units:
            key = _atomic_fact_key(u)
            if not key or key in seen:
                continue
            off = quote.find(u)
            if off < 0:
                continue
            tok_start = start + off
            tok_end = tok_start + len(u)
            u_core = _strip_terminal_punct(u)
            out.append(f"{u_core} [#ev:{eid}:{tok_start}-{tok_end}].")
            seen.add(key)
            if len(out) >= limit:
                return " ".join(out)
    return " ".join(out) if out else ""


def build_verified_span_draft_multi(basket: Any, evidence_pool: dict) -> Optional[str]:
    """L2 SNAP-preserving multi-fact K-span FALLBACK — the ``build_verified_span_draft`` sibling used by
    ``_compose_one_basket`` when PG_SUBTOPIC_DECOMPOSITION is ON. Mirrors ``build_verified_span_draft``
    EXACTLY (verbatim span + real global offsets + FIX-D extend-only sentence snap + chrome/junk screen)
    but ACCUMULATES the DISTINCT atomic facts across ALL of the basket's SUPPORTS members (deduped by
    ``_atomic_fact_key``) instead of returning on the first member. Returned DIRECTLY by the caller (not
    re-region-checked), so the snap-recovered whole sentence is safe here. Returns None only when NO
    member yields a real verified unit (caller emits the insufficient-evidence disclosure). Each unit is
    a verbatim span carrying its member's own provenance token → re-passes strict_verify trivially
    (faithfulness UNCHANGED). Bounded by the PG_SUBTOPIC_MAX_FACTS ceiling."""
    known_words = _known_words_for_compose(evidence_pool)
    limit = _subtopic_max_facts()
    seen: set[str] = set()
    out: list[str] = []
    all_chrome_member_drops = 0
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        gspan = _member_global_span(m, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        start, end = gspan
        # FIX-D extend-only SUPERSET span snap (mirrors build_verified_span_draft): complete a
        # mid-sentence cut forward to the next sentence boundary in the SAME row. Extend-only => the
        # widened token covers exactly the emitted text => grounded by construction, never fabricates.
        snap_end = end
        span_text = quote
        if _snap_span_enabled():
            row = (evidence_pool or {}).get(eid) or {}
            haystack = str(row.get("direct_quote") or row.get("statement") or "")
            snap_end = _snap_span_end_to_sentence(haystack, start, end)
            # finding #8: cap the forward snap at the nearest sibling member's span so a merged
            # multi-source sentence never emits one member's span under another's single [#ev] token.
            if _snap_member_boundary_enabled():
                snap_end = min(
                    snap_end,
                    _snap_cap_to_sibling_member(basket, m, haystack, start, end, evidence_pool),
                )
            if snap_end > end and 0 <= start < snap_end <= len(haystack):
                span_text = haystack[start:snap_end]
        units = [u.strip() for u in (split_into_sentences(span_text) or [span_text]) if u.strip()]
        units_before = len(units)
        units = [
            u for u in units
            if not _compose_junk_screen(u, known_words, require_sentence_form=True)
        ]
        if units_before and not units:
            all_chrome_member_drops += 1
            continue
        for u in units:
            key = _atomic_fact_key(u)
            if not key or key in seen:
                continue
            u_core = _strip_terminal_punct(u)
            # Whole-member-span token (mirrors build_verified_span_draft): the verified span contains
            # each of its sub-sentences, so every unit grounds against [start, snap_end].
            out.append(f"{u_core} [#ev:{eid}:{start}-{snap_end}].")
            seen.add(key)
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    if out:
        return " ".join(out)
    if all_chrome_member_drops:
        subject = str(
            getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim"
        ).strip()
        logger.warning(
            "[verified_compose] L2 subtopic-decomp: all-chrome-basket drop — %d member(s) resolved a "
            "verified span but ALL its sentence units screened as chrome; basket falls through to the "
            "insufficient-evidence disclosure: %.160s",
            all_chrome_member_drops,
            subject,
        )
    return None


def _insufficient_evidence_disclosure(basket: Any) -> str:
    """Honest NEVER-empty fallback when a basket has prose-fail AND no verified span: disclose the
    gap, never fabricate filler (§-1.3). Names the claim subject so the disclosure is specific."""
    subject = str(getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim").strip()
    return f"[insufficient verified evidence to compose a sentence for: {subject[:160]}]"


def _deterministic_only_member_count(basket: Any) -> int:
    """The number of the basket's members whose entailment tier is DETERMINISTIC_ONLY — grounded on
    their OWN span (passed the deterministic (a)-(e) engine) but NOT entailment-verified (the judge
    returned NEUTRAL/CONTRADICTED OR errored/timed out this run). Read-only; NEVER a verdict, NEVER
    surfaced as prose. The tier constant is imported lazily (with a literal fallback) to avoid a
    synthesis<->generator cycle.

    NOTE (Codex Wave-3 P1b): DETERMINISTIC_ONLY alone conflates a CLEAN NEUTRAL/CONTRADICTED (judge ran)
    with a judge OUTAGE. It must NOT gate the ARM-B "verification unavailable" disclosure — use
    ``_judge_unavailable_member_count`` for that. This count is retained as a diagnostic only."""
    try:
        from src.polaris_graph.synthesis.credibility_pass import (  # noqa: PLC0415
            MEMBER_TIER_DETERMINISTIC_ONLY as _DET,
        )
    except Exception:  # pragma: no cover — credibility_pass is stable in-tree
        _DET = "DETERMINISTIC_ONLY"
    members = list(getattr(basket, "supporting_members", None) or [])
    return sum(1 for m in members if str(getattr(m, "member_tier", "") or "") == _DET)


def _judge_unavailable_member_count(basket: Any) -> int:
    """I-deepfix-001 Wave-3 PART 2 ARM B P1b (#1344): the number of the basket's members that
    DETERMINISTICALLY ground the claim (member_tier == DETERMINISTIC_ONLY) AND whose entailment judge
    was DURABLY UNAVAILABLE this run (``entailment_judge_unavailable`` — a judge_error / timeout /
    transport-hard-drop, NOT a clean NEUTRAL/CONTRADICTED verdict).

    THIS is the ONLY count that may drive the degraded-verify disclosure: a clean non-entailment (the
    judge ran and returned NEUTRAL/CONTRADICTED) is DETERMINISTIC_ONLY but NOT judge-unavailable, so it
    stays a GENUINE evidence gap — never falsely disclosed as "entailment verification was unavailable"
    (the Codex Wave-3 P1b bug). Read-only; NEVER a verdict, NEVER surfaced as prose."""
    try:
        from src.polaris_graph.synthesis.credibility_pass import (  # noqa: PLC0415
            MEMBER_TIER_DETERMINISTIC_ONLY as _DET,
        )
    except Exception:  # pragma: no cover — credibility_pass is stable in-tree
        _DET = "DETERMINISTIC_ONLY"
    members = list(getattr(basket, "supporting_members", None) or [])
    return sum(
        1 for m in members
        if str(getattr(m, "member_tier", "") or "") == _DET
        and bool(getattr(m, "entailment_judge_unavailable", False))
    )


def _degraded_verify_disclosure(basket: Any, deterministic_only_count: int) -> str:
    """I-deepfix-001 Wave-3 PART 2 ARM B (#1344) — the honest DEGRADED-VERIFY disclosure: the basket
    yields no ENTAILMENT_VERIFIED span, but ``deterministic_only_count`` member(s) DETERMINISTICALLY
    ground the claim on their OWN span and only entailment verification was unavailable this run. A
    DISTINCT label (not the bare "insufficient verified evidence" gap) so a transient judge outage is
    never reported as a genuine evidence gap. NEVER counted as verified support (carries no
    ENTAILMENT_VERIFIED [#ev] token) — it is a disclosure placeholder, recognized by
    ``contract_section_runner._is_gap_disclosure_sentence``."""
    subject = str(getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim").strip()
    return (
        f"[verification incomplete: {deterministic_only_count} source(s) deterministically ground "
        f"this claim but entailment verification was unavailable this run — not counted as verified "
        f"support: {subject[:160]}]"
    )


def _no_verified_span_disclosure(basket: Any) -> str:
    """The honest disclosure a basket emits when it yields NO verified span. Default (and the OFF /
    genuine-gap case): the bare ``_insufficient_evidence_disclosure``. ARM B
    (PG_DEGRADED_VERIFY_DISCLOSURE, default-ON): when the basket carries >=1 DETERMINISTIC_ONLY member
    (judge-outage, not a real evidence gap) the DISTINCT degraded-verify label is emitted instead —
    only the LABEL changes; no DETERMINISTIC_ONLY prose is ever promoted into verified text and the
    hard ENTAILMENT_VERIFIED gate is untouched. OFF => the bare gap for both causes => byte-identical.

    Codex Wave-3 P1b: the degraded label fires ONLY on a DURABLE judge OUTAGE
    (``_judge_unavailable_member_count`` > 0), never on a clean NEUTRAL/CONTRADICTED (which is a
    genuine gap and keeps the bare insufficient-evidence disclosure)."""
    if _degraded_verify_disclosure_enabled():
        n = _judge_unavailable_member_count(basket)
        if n > 0:
            return _degraded_verify_disclosure(basket, n)
    return _insufficient_evidence_disclosure(basket)


# ── I-deepfix-001 Wave-3 PART 2 ARM B P1a (#1344) — degraded-disclosure PRODUCTION-PATH carrier ──────
#
# THE BUG (Codex Wave-3 P1a): the DISTINCT "[verification incomplete: ...]" label is emitted as TOKENLESS
# raw text by ``_compose_one_basket``. The legacy "[insufficient verified evidence]" marker is SUPPRESSED
# by ``_compose_section_per_basket`` (:1284) before it can leak, but the degraded label was NOT — so it
# flowed into the strict_verify-bound draft where (a) ``_repair_untokened_draft`` could REBIND its
# tokenless text to some other SUPPORTS basket (laundering an honest gap into a fabricated cited claim),
# or (b) ``strict_verify`` dropped it ``no_provenance_token`` (the honest label never reached output).
#
# THE CARRIER: recognize BOTH no-verified-span disclosure placeholders, HOLD the degraded label ASIDE
# before it enters the strict_verify-bound draft (``_run_section`` calls ``partition_composed_disclosures``),
# and RENDER it back onto the section body AFTER strict_verify + the render screens (``_run_section`` calls
# ``render_degraded_disclosures``). It never becomes verified prose (no ``[#ev]`` token, not in
# ``kept_sentences``, ``sentences_verified`` unchanged), and ``repair_untokened_sentence`` refuses to
# rebind it — so it is treated EXACTLY like the legacy insufficient-evidence disclosure by
# ``_repair_untokened_draft`` / ``strict_verify`` (never rebound, never dropped as garbage). It is a
# marker-less honest disclosure, the SAME faithfulness class as the section-level gap stub. Byte-identical
# when PG_DEGRADED_VERIFY_DISCLOSURE is OFF (no such label is ever produced => the partition is a no-op).
_INSUFFICIENT_EVIDENCE_DISCLOSURE_PREFIX = "[insufficient verified evidence"
_DEGRADED_VERIFY_DISCLOSURE_PREFIX = "[verification incomplete:"
# I-deepfix-001 Wave-1a (#1344) — the SYNTH_PRIMARY uncovered-fact labeled-disclosure prefix. When the
# bounded repair loop exhausts with a residual failing authored sentence, the basket's verbatim
# uncovered-fact K-span is emitted as a SEPARATE `[`-prefixed disclosure paragraph (redactor no-touch
# set: a line starting with `[` is never TIER-2 redacted) routed aside by ``partition_composed_disclosures``
# and re-appended AFTER strict_verify by ``render_degraded_disclosures`` — NEVER the mid-line
# `" ".join(kept + [fallback])` glue. It is a verbatim span (grounded by construction) rendered as an
# honest labeled block. ONLY produced on the SYNTH_PRIMARY ON path => byte-identical when OFF.
_UNCOVERED_FACT_DISCLOSURE_PREFIX = "[uncovered supporting evidence for:"


def _is_degraded_verify_disclosure_unit(text: Any) -> bool:
    """True iff a whole composed unit IS the degraded-verify disclosure placeholder (``[verification
    incomplete: ...]``). ``_compose_one_basket`` returns the disclosure ALONE for a no-verified-span
    basket (kept prose empty), so a pure-disclosure unit STARTS with the prefix; a mixed
    ``verified prose. [verification incomplete: ...]`` unit does NOT (it starts with the prose) and
    stays in the strict_verify-bound draft, preserving its verified prose."""
    return str(text or "").strip().lower().startswith(_DEGRADED_VERIFY_DISCLOSURE_PREFIX)


def _is_no_verified_span_disclosure(text: Any) -> bool:
    """True iff ``text`` is EITHER no-verified-span disclosure placeholder — the legacy bare
    ``[insufficient verified evidence ...]`` gap OR the ARM-B ``[verification incomplete: ...]``
    degraded-verify label. Used by ``repair_untokened_sentence`` so NEITHER is ever rebound to a foreign
    SUPPORTS basket (a disclosure placeholder is not a claim; rebinding it is the P1a laundering bug)."""
    lowered = str(text or "").strip().lower()
    return (
        lowered.startswith(_INSUFFICIENT_EVIDENCE_DISCLOSURE_PREFIX)
        or lowered.startswith(_DEGRADED_VERIFY_DISCLOSURE_PREFIX)
    )


def _is_composed_disclosure_paragraph(text: Any) -> bool:
    """True iff a composed paragraph is a HELD-ASIDE disclosure unit — the ARM-B degraded-verify label
    (``[verification incomplete: ...]``) OR the SYNTH_PRIMARY uncovered-fact label
    (``[uncovered supporting evidence for: ...]``). Both are routed aside by
    ``partition_composed_disclosures`` and re-appended after strict_verify. The uncovered-fact prefix is
    ONLY produced on the SYNTH_PRIMARY ON path, so this is byte-identical to the pre-Wave-1a
    degraded-only classification when PG_SYNTH_PRIMARY is OFF (no unit ever starts with it)."""
    lowered = str(text or "").strip().lower()
    return (
        _is_degraded_verify_disclosure_unit(text)
        or lowered.startswith(_UNCOVERED_FACT_DISCLOSURE_PREFIX)
    )


def partition_composed_disclosures(units: list) -> "tuple[list[str], list[str]]":
    """Split a ``_compose_section_per_basket`` result into ``(real_units, degraded_disclosures)``.

    A pure disclosure unit (``[verification incomplete: ...]`` or the SYNTH_PRIMARY
    ``[uncovered supporting evidence for: ...]`` labeled K-span) is HELD ASIDE so it NEVER enters the
    strict_verify-bound draft (where ``_repair_untokened_draft`` could rebind it or ``strict_verify``
    would drop it). Every other unit passes through UNCHANGED, byte-for-byte (the common case).

    I-deepfix-001 Wave-1a (#1344): a SYNTH_PRIMARY exhaustion unit carries the verified authored body
    AND a trailing labeled uncovered-fact K-span as SEPARATE ``\\n\\n`` paragraphs. When (and ONLY when) a
    unit contains a ``\\n\\n`` paragraph break it is split per-paragraph so the body stays real prose and
    the labeled K-span is routed aside — as its OWN ``\\n\\n`` disclosure paragraph. Existing units are
    always ``" ".join(...)`` (no internal ``\\n\\n``), so the fast path below is taken for every existing
    unit and the output is byte-identical when PG_SYNTH_PRIMARY / PG_DEGRADED_VERIFY_DISCLOSURE are OFF.
    Order-stable."""
    real: list[str] = []
    disclosures: list[str] = []
    for unit in (units or []):
        # Fast path (byte-identical to pre-Wave-1a): a unit with no paragraph break is classified whole.
        if "\n\n" not in str(unit):
            if _is_composed_disclosure_paragraph(unit):
                disclosures.append(str(unit).strip())
            else:
                real.append(unit)
            continue
        # SYNTH_PRIMARY mixed unit: route each paragraph independently.
        body_parts: list[str] = []
        for para in str(unit).split("\n\n"):
            if not para.strip():
                continue
            if _is_composed_disclosure_paragraph(para):
                disclosures.append(para.strip())
            else:
                body_parts.append(para)
        if body_parts:
            real.append("\n\n".join(body_parts))
    return real, disclosures


def render_degraded_disclosures(body: str, disclosures: list) -> str:
    """Append the held-aside degraded-verify disclosure(s) to the section ``body`` (already produced by
    strict_verify + the render screens). They are marker-less honest disclosures — NOT verified prose,
    NOT counted as support, NEVER re-run through strict_verify — so this is a pure render-layer append
    (the SAME faithfulness class as the section-level gap stub). When ``body`` is empty (the whole
    section was degraded), the DISTINCT disclosure IS the body. Empty ``disclosures`` => ``body``
    unchanged (byte-identical)."""
    kept_disclosures = [str(d).strip() for d in (disclosures or []) if d and str(d).strip()]
    if not kept_disclosures:
        return body
    parts: list[str] = []
    body_str = str(body or "").rstrip()
    if body_str:
        parts.append(body_str)
    parts.extend(kept_disclosures)
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Box C QUALITY fix (workflow wioabua6u) — compose-time render-chrome screen. A writer can
# PARAPHRASE page furniture (author byline / masthead / ToC heading / nav run) into a sentence that
# self-entails its own span and PASSES strict_verify; catch it HERE, at compose time, before it
# reaches the render seam. WITHHOLD-only (never touches a faithfulness verdict): a flagged sentence
# is not KEPT into the composed prose; the SOURCE stays in the pool. Kill-switch
# PG_RENDER_CHROME_PROSE_SCREEN (LAW VI / constraint 3); default ON. Import-safe / fails OPEN so a
# helper error never withholds a real verified sentence (precision-first drop-path law).
_COMPOSE_CHROME_SCREEN_ENV = "PG_RENDER_CHROME_PROSE_SCREEN"
_COMPOSE_CHROME_OFF_TOKENS = frozenset({"0", "false", "off", "no"})


def _compose_render_chrome_enabled() -> bool:
    """Return True iff PG_RENDER_CHROME_PROSE_SCREEN is not an off token (default ON = screen)."""
    raw = os.environ.get(_COMPOSE_CHROME_SCREEN_ENV)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _COMPOSE_CHROME_OFF_TOKENS


def _sentence_is_render_chrome(sentence: str) -> bool:
    """True iff a writer-paraphrased sentence is render chrome (the UNBLINDED shared predicate OR the
    whole-unit furniture screen). Import-safe / fails OPEN so a helper import error never withholds a
    real verified sentence. Used at compose time to catch writer-paraphrased chrome that self-entails
    strict_verify."""
    try:
        from src.polaris_graph.generator.chrome_furniture_screen import (  # noqa: PLC0415
            is_furniture_dominant,
        )
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover - both modules are stable in-tree
        return False
    try:
        # Correction 5 (Codex+Fable gate): the structure-anchored predicate is the primary drop. If it
        # fires, drop. Otherwise use is_furniture_dominant ONLY as a whole-unit-furniture CONFIRM — it
        # already encodes the precision guard (a furniture token was removed AND the residue is near-
        # empty), so a real claim carrying a welded furniture fragment keeps its residue and is NEVER
        # dropped here. is_furniture_dominant is thus a PRECISION GUARD, never an independent broad-
        # containment OR-drop.
        if is_render_chrome_or_unrenderable(sentence):
            return True
        return bool(is_furniture_dominant(sentence))
    except Exception:  # pragma: no cover - both predicates are pure in-tree
        return False


def _screen_fallback_chrome(text: str) -> str:
    """Correction 4 (Codex+Fable gate) — close the compose-time chrome LEAK. When ``_compose_one_basket``
    WITHHOLDS a writer-paraphrased chrome sentence (the ``continue`` at the keep-loop), the K-span
    fallback ``build_verified_span_draft`` RE-DERIVES prose from the SAME verified span, so the withheld
    chrome unit can RE-ENTER via the fallback. Screen the fallback with the SAME unblinded predicate
    (``_sentence_is_render_chrome``) used above so a withheld chrome unit cannot leak back in.

    Per-sentence WITHHOLD, render-side, faithfulness-NEUTRAL (the SOURCE stays in the pool). FAIL-SAFE:
    empty/blank returns the input unchanged; a LOSSY re-segmentation (the sentence segments do not round-
    trip to the whitespace-normalized input) returns the input UNCHANGED (never corrupt real prose on a
    splitter miss); nothing-withheld returns byte-identical; an ALL-units-chrome fallback returns "" so the
    caller falls to the honest gap disclosure (never blanks a real section)."""
    if not text or not text.strip():
        return text
    sentences = split_into_sentences(text)
    if not sentences:
        return text
    # FAIL-SAFE round-trip guard: the whitespace-normalized re-join must reconstruct the input.
    norm_in = " ".join(text.split())
    norm_seg = " ".join(" ".join(s.split()) for s in sentences)
    if norm_seg != norm_in:
        return text
    kept = [s for s in sentences if not _sentence_is_render_chrome(s)]
    if len(kept) == len(sentences):
        return text  # nothing withheld -> byte-identical
    return " ".join(kept)  # "" when EVERY unit was chrome -> caller falls to the gap disclosure


# ── I-deepfix-001 Wave-1a (#1344) — SYNTH_PRIMARY: compose-then-verify + bounded repair + labeled block ─
def _synth_primary_enabled() -> bool:
    """``PG_SYNTH_PRIMARY`` gate (default OFF, LAW VI). Shares the off-token set with
    ``_compose_render_chrome_enabled`` but is DEFAULT-OFF: unset/blank/off-token => OFF. Only when ON
    (and the caller threads a group-capable ``redraft_fn``) does ``_compose_one_basket`` take the
    bounded-repair + labeled-fallback path; otherwise the legacy body runs byte-identical."""
    raw = str(os.environ.get(_SYNTH_PRIMARY_ENV, "")).strip().lower()
    return bool(raw) and raw not in _COMPOSE_CHROME_OFF_TOKENS


def _writer_repair_max() -> int:
    """``PG_WRITER_REPAIR_MAX`` (default 2, int, clamp >= 0; LAW VI). The bounded number of whole-
    paragraph re-draft attempts the SYNTH_PRIMARY repair loop may make. 0 => a single draft, no repair
    (a finite hard cap so the loop can NEVER spin forever)."""
    raw = str(os.environ.get(_WRITER_REPAIR_MAX_ENV, "")).strip()
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return _WRITER_REPAIR_MAX_DEFAULT
    return max(0, n)


def _collect_synth_revise_reasons(failed: list) -> list[str]:
    """Flatten + order-stable-dedup the wrapper failure reasons of the currently-failing sentences, fed
    back to the writer as ``revise_reasons`` (RARR). Pure."""
    seen: set[str] = set()
    out: list[str] = []
    for _sentence, reasons in (failed or []):
        for r in (reasons or []):
            if r not in seen:
                seen.add(r)
                out.append(r)
    return out


def _verify_all_sentences_synth(
    draft: str,
    scoped_pool: dict,
    regions: dict,
    *,
    verify_fn: Callable[..., Any],
) -> "tuple[list[str], list[tuple[str, list[str]]]]":
    """Verify EVERY sentence of ``draft`` against the basket-scoped pool with the UNCHANGED ``verify_fn``
    (which is the stricter writer wrapper on the SYNTH_PRIMARY path) + own-region gate + the same
    compose-time chrome screen the legacy loop applies. Unlike the legacy first-failure break, this
    collects ALL failures for the bounded repair loop. Returns ``(kept_verified_texts, failed)`` where
    ``failed`` is ``[(input_sentence, wrapper_failure_reasons), ...]``. The accept condition is
    byte-identical to the legacy loop's per-sentence accept — the faithfulness gate is untouched."""
    kept: list[str] = []
    failed: list[tuple[str, list[str]]] = []
    for sentence in split_into_sentences(draft):
        res = verify_fn(sentence, scoped_pool)
        verified_text = str(getattr(res, "sentence", "") or "").strip() or sentence.strip()
        if bool(getattr(res, "is_verified", False)) and _tokens_within_basket_regions(verified_text, regions):
            # Same chrome-screen WITHHOLD as the legacy loop: a verified chrome sentence is skipped
            # (not kept, not a failure) so real sibling sentences still survive.
            if _compose_render_chrome_enabled() and _sentence_is_render_chrome(verified_text):
                continue
            kept.append(verified_text)
        else:
            reasons = list(getattr(res, "failure_reasons", []) or []) or ["writer_sentence_rejected"]
            failed.append((sentence, reasons))
    return kept, failed


def _uncovered_fact_disclosure(basket: Any, span_text: str) -> str:
    """Wrap a basket's verbatim uncovered-fact K-span in the SYNTH_PRIMARY labeled-disclosure prefix so
    ``partition_composed_disclosures`` routes it aside and ``render_degraded_disclosures`` re-appends it
    AFTER strict_verify as its OWN ``\\n\\n`` paragraph. The unit starts with ``[`` (redactor no-touch
    set) and NAMES the source subject in the label.

    Fable P1 (raw-[#ev]-leak): the block is appended AFTER ``resolve_provenance_to_citations_with_count``
    has already converted the kept sentences' ``[#ev:...]`` tokens to ``[N]`` markers, so a raw ``[#ev]``
    token surviving in this block would ship as unresolvable chrome in report.md (the I-wire-013/014
    class; a DeepTRACE liability). Like EVERY sibling ARM-B disclosure this block is therefore
    MARKER-LESS: the ``[#ev]`` token(s) are stripped and the space-before-punctuation is tidied. It stays
    a verbatim source span (grounded by construction) rendered as an honest labeled evidence block; it is
    never body prose and never re-run through strict_verify. Fable P2: the subject is whitespace-collapsed
    so an embedded ``\\n\\n`` can never split the single disclosure paragraph."""
    subject = str(getattr(basket, "subject", "") or getattr(basket, "claim_text", "") or "this claim")
    subject = " ".join(subject.split())  # Fable P2: no embedded newline can split the paragraph
    # Fable P1: strip the raw [#ev:...] token(s) (marker-less like every sibling disclosure) and tidy the
    # space left before terminal punctuation so the block reads clean.
    clean_span = _EV_TOKEN_RE.sub("", span_text or "")
    clean_span = re.sub(r"\s+([.,;:!?])", r"\1", clean_span)
    clean_span = " ".join(clean_span.split())
    return f"{_UNCOVERED_FACT_DISCLOSURE_PREFIX} {subject[:120]}] {clean_span}"


def _synth_primary_fallback_unit(basket: Any, evidence_pool: dict, *, body: str) -> str:
    """Build the SYNTH_PRIMARY exhaustion output: the verified authored ``body`` (may be "") PLUS the
    uncovered-fact K-span as a SEPARATE labeled disclosure paragraph (``\\n\\n``-joined), NEVER the
    mid-line ``" ".join(kept + [fallback])`` glue. Reuses ``build_verified_span_draft_multi`` (or
    ``build_verified_span_draft`` when sub-topic decomposition is OFF, mirroring the legacy fallback
    selection) for the verbatim span text + the same render-chrome fallback screen. When no K-span
    resolves, falls to the honest gap disclosure (also as its own ``\\n\\n`` paragraph when a body
    exists). Failed AUTHORED sentences are already discarded by the caller (never in ``body``)."""
    fallback = (
        build_verified_span_draft_multi(basket, evidence_pool)
        if _subtopic_decomposition_enabled()
        else build_verified_span_draft(basket, evidence_pool)
    )
    if fallback and _compose_render_chrome_enabled():
        fallback = _screen_fallback_chrome(fallback)
    body = (body or "").strip()
    if fallback and fallback.strip():
        labeled = _uncovered_fact_disclosure(basket, fallback)
        return f"{body}\n\n{labeled}" if body else labeled
    # No verified K-span resolves. When verified authored prose survived, ship it alone — there is no
    # verbatim span to disclose for the discarded sentence(s), and gluing an honest-gap marker onto real
    # prose would leak the marker into the strict_verify draft. With no body, emit the honest gap
    # disclosure (a pure unit; the §3.5 filter in _compose_section_per_basket suppresses the legacy
    # insufficient-evidence marker, exactly as on the legacy path).
    if body:
        return body
    return _no_verified_span_disclosure(basket)


def _emit_synth_primary_marker(kept: list) -> None:
    """Emit the SYNTH_PRIMARY activation fire marker (I-deepfix-001 Wave-3a #1344) — the stable literal
    the activation canary parses to prove synth-primary actually produced prose. Fires ONLY when authored
    prose survived (``kept`` non-empty); NEVER on an empty / pure-disclosure return (Fable R5 — a
    ``kept=[]`` exhaustion is NOT authored prose). Structural presence + count, never a threshold (§-1.3).
    Side-effect only; the composed text is byte-untouched."""
    if kept:
        logger.info("[activation] synth_primary: authored_prose kept=%d", len(kept))


def _synth_primary_repair_loop(
    basket: Any,
    scoped_pool: dict,
    regions: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    redraft_fn: Callable[..., str],
) -> "tuple[list[str], list[tuple[str, list[str]]]]":
    """The SYNTH_PRIMARY compose-then-verify + BOUNDED whole-paragraph repair CORE (extracted #1344
    Wave-3a so BOTH the single-basket and the corroborated-basket synth-primary composers share ONE loop).
    Draft ONE paragraph via ``writer_fn``, verify EVERY sentence with the UNCHANGED
    ``_verify_all_sentences_synth`` wrapper (SAME verify_fn, own-region gate, chrome screen), and re-draft
    up to ``_writer_repair_max()`` times feeding the RARR failure reasons back. Returns ``(kept, failed)``
    — the verified authored sentences and the residual failures. The faithfulness engine (verify_fn /
    wrapper / region gate) is BYTE-UNTOUCHED; only which draft is submitted changes, under a finite cap
    that can never ship a failed sentence."""
    draft = writer_fn(basket, scoped_pool) or ""
    kept, failed = _verify_all_sentences_synth(draft, scoped_pool, regions, verify_fn=verify_fn)
    attempts = 0
    repair_max = _writer_repair_max()
    while failed and attempts < repair_max:
        attempts += 1
        revise_reasons = _collect_synth_revise_reasons(failed)
        fresh = redraft_fn(basket, scoped_pool, revise_reasons=revise_reasons) or ""
        # Codex P0 / Fable P1: an EMPTY re-draft (a 429 storm, a wedged writer abandoned by the async
        # bridge, or any writer error returning "") must NOT overwrite the prior attempt's verified
        # sentences with nothing — break and keep the prior kept/failed so the exhaustion path ships the
        # verified authored body, never collapse a partially-good paragraph because a repair came back empty.
        if not fresh.strip():
            break
        kept, failed = _verify_all_sentences_synth(fresh, scoped_pool, regions, verify_fn=verify_fn)
    return kept, failed


def _compose_one_basket_synth_primary(
    basket: Any,
    evidence_pool: dict,
    scoped_pool: dict,
    regions: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    redraft_fn: Callable[..., str],
) -> str:
    """SYNTH_PRIMARY (#1344 Wave-1a) compose-then-verify path. Draft ONE coherent paragraph, verify ALL
    sentences downstream with the UNCHANGED ``verify_fn``, keep the passing (chrome-screened) ones, and
    run a BOUNDED whole-paragraph repair loop (re-call ``redraft_fn`` with the collected wrapper failure
    reasons, up to ``_writer_repair_max()``, re-verifying each fresh draft in full). Exit:
      * all sentences pass  => body = ``" ".join(kept)`` (or the K-span/gap fallback if the draft was
        empty and nothing was kept).
      * budget exhausted with residual failures => body = the verified authored sentences; the
        uncovered-fact K-span renders as a SEPARATE labeled disclosure paragraph (ARM-B routed). FAILED
        AUTHORED sentences are DISCARDED — never shipped, never glued.
    The faithfulness engine (strict_verify / NLI / D8 / provenance / the writer wrapper) is UNTOUCHED;
    only which draft is submitted changes, under a strict finite cap that can never ship a failed
    authored sentence."""
    kept, failed = _synth_primary_repair_loop(
        basket, scoped_pool, regions, writer_fn=writer_fn, verify_fn=verify_fn, redraft_fn=redraft_fn,
    )
    body = " ".join(kept)
    # Wave-3a #1344: fire the activation marker ONLY when authored prose survived (Fable R5). When ``kept``
    # is non-empty the body ALWAYS ships below (as ``body`` or ``body`` + the labeled K-span); an empty
    # ``kept`` routes to a pure-disclosure fallback and does NOT fire.
    _emit_synth_primary_marker(kept)
    if not failed:
        # Every sentence covered (or the draft produced nothing). A non-empty body ships as-is; an empty
        # body falls to the K-span / honest-gap fallback (never an empty unit).
        if body.strip():
            return body
        return _synth_primary_fallback_unit(basket, evidence_pool, body="")
    # Budget exhausted with residual failures: verified authored body + SEPARATE labeled K-span block.
    return _synth_primary_fallback_unit(basket, evidence_pool, body=body)


def _compose_one_basket(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    redraft_fn: Optional[Callable[..., str]] = None,
) -> str:
    """Compose ONE basket: writer drafts prose -> strict_verify each sentence against the
    BASKET-SCOPED pool -> keep passing sentences; on the FIRST failing sentence (or a foreign-cited
    one, which fails closed under the scoped pool) FALL BACK to this basket's own verified K-span;
    if the basket has no verified span, emit the insufficient-evidence disclosure. NEVER empty.

    I-deepfix-001 Wave-1a (#1344): when ``PG_SYNTH_PRIMARY`` is ON AND the caller threads a group-capable
    ``redraft_fn`` (the primary path), delegate to ``_compose_one_basket_synth_primary`` (compose-then-
    verify + bounded repair + separate labeled fallback). When OFF or no ``redraft_fn`` is threaded the
    legacy body below runs UNCHANGED — byte-identical."""
    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    if redraft_fn is not None and _synth_primary_enabled():
        return _compose_one_basket_synth_primary(
            basket, evidence_pool, scoped_pool, regions,
            writer_fn=writer_fn, verify_fn=verify_fn, redraft_fn=redraft_fn,
        )
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
            # Box C QUALITY fix (workflow wioabua6u): WITHHOLD a writer-paraphrased chrome sentence
            # that passed strict_verify (self-entailing its own span) — render-side, faithfulness-
            # neutral. The SOURCE stays in the pool; only the chrome UNIT is withheld. SKIP (do NOT
            # fall back) so real sibling sentences are still kept. Kill-switch
            # PG_RENDER_CHROME_PROSE_SCREEN (default ON).
            if _compose_render_chrome_enabled() and _sentence_is_render_chrome(verified_text):
                continue
            kept.append(verified_text)
        else:
            fell_back = True
            break
    if kept and not fell_back:
        return " ".join(kept)
    # prose failed (or produced nothing): basket-id-bound verbatim fallback, else honest disclosure.
    # L2 sub-topic decomposition (I-deepfix-001 #1344): emit ONE verified verbatim-span sentence per
    # DISTINCT atomic fact the basket grounds (deduped, keep-all consolidation) instead of the first
    # member's single span. Covers BOTH the abstractive (paid) and deterministic paths — any writer
    # sentence that fails the per-basket verify falls here. Faithfulness-neutral (each unit re-passes
    # strict_verify trivially — it IS a verbatim span). OFF => build_verified_span_draft (byte-identical).
    fallback = (
        build_verified_span_draft_multi(basket, evidence_pool)
        if _subtopic_decomposition_enabled()
        else build_verified_span_draft(basket, evidence_pool)
    )
    if fallback is not None:
        # Correction 4 (Codex+Fable gate): the K-span fallback RE-DERIVES from the SAME verified span, so
        # a chrome unit withheld above (the keep-loop ``continue``) can RE-ENTER here. Screen the fallback
        # with the SAME unblinded render-chrome predicate. Gated by the default-ON kill-switch. FAIL-SAFE:
        # if screening empties the fallback, fall THROUGH to the honest gap disclosure below (never blank a
        # real section). Faithfulness-neutral (render-side WITHHOLD; the source stays in the pool).
        if _compose_render_chrome_enabled():
            fallback = _screen_fallback_chrome(fallback)
        if fallback and fallback.strip():
            # If some sentences were kept before the failure, keep them + the verbatim span (never lose
            # already-verified prose); else the span alone.
            return " ".join(kept + [fallback]) if kept else fallback
    # I-deepfix-001 Wave-3 PART 2 ARM B (#1344): no verified span. Default the honest gap, BUT when a
    # transient judge outage left DETERMINISTIC_ONLY (grounded-but-unentailed) members, disclose THAT
    # instead of "no evidence". Only the LABEL changes — no DETERMINISTIC_ONLY prose is ever promoted
    # into verified text; the ENTAILMENT_VERIFIED gate is untouched. OFF => the bare gap => byte-identical.
    disclosure = _no_verified_span_disclosure(basket)
    return " ".join(kept + [disclosure]) if kept else disclosure


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
    # Terminal-strip the FIRST clause the SAME way as every continuation
    # (``_strip_terminal_punct`` below) so a first clause ending in a sentence
    # terminal (e.g. ``...wages.``) does not glue to the ``"; "`` connective as
    # a ``".;"`` double-punctuation. A first clause ending in a provenance ``]``
    # (or any non-terminal char) is returned unchanged by the helper, so the
    # connective still lands right after the token. First clause keeps its
    # leading capital (it opens the sentence) — only continuations are lowercased.
    parts = [_strip_terminal_punct(clean[0])]
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


# ── I-deepfix-001 Wave-3a (#1344) — SYNTH_PRIMARY routing for the CORROBORATED core body ─────────────
#
# On gate-B ``PG_VERIFIED_COMPOSE_MULTICITED`` is force-ON, so every corroborated (>=2 distinct-origin
# SUPPORTS) basket — the §-1.3 consolidate-keep-all CORE report body — was composed by the multi-cited
# K-span co-location and NEVER reached the SYNTH_PRIMARY group writer. Wave-3a routes those baskets THROUGH
# synth-primary WHEN ``PG_SYNTH_PRIMARY`` is ON (and a group-capable ``redraft_fn`` is threaded), so the
# stricter per-sentence writer verify wrapper (``_verify_all_sentences_synth``) composes the coherent body,
# WHILE every distinct-origin corroborator the authored prose did not itself cite is still surfaced as its
# OWN verbatim K-span (all-corroborator multi-citation preserved — no corroborating source is dropped).
# The faithfulness engine is byte-untouched: the authored sentences ran the SAME verify wrapper; the
# appended clauses are verbatim verified spans; the caller re-runs the UNCHANGED strict_verify. OFF (flag
# unset OR no ``redraft_fn``) => the multi-cited co-location runs => byte-identical to the pre-Wave-3a path.


def _uncited_corroborator_clauses(basket: Any, evidence_pool: dict, body: str) -> list[str]:
    """VERBATIM K-span clauses for every DISTINCT-ORIGIN corroborator whose citation the synth-primary
    authored ``body`` did NOT already carry — so routing a corroborated basket THROUGH synth-primary
    (Wave-3a #1344) never DROPS a corroborating source (§-1.3 consolidate-keep-all). Each clause is the
    member's OWN verified verbatim span (``_member_verbatim_clause`` -> ``build_verified_span_draft`` over a
    1-member sub-basket) carrying its OWN ``[#ev]`` token, so it re-passes the UNCHANGED strict_verify
    trivially — the faithfulness engine is byte-untouched. Order-stable (weight desc, inherited from
    ``_distinct_origin_supports``); pure read. Returns ``[]`` when the body already cites every origin."""
    # Map every SUPPORTS member's evidence_id to its ORIGIN — the authored body may cite a NON-representative
    # member of an origin the distinct-origin roster represents by a DIFFERENT eid (never re-surface it).
    eid_to_origin: dict[str, str] = {}
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        if eid:
            eid_to_origin[eid] = str(getattr(m, "origin_cluster_id", "") or eid)
    cited_origins: set[str] = set()
    for ev_id, _s, _e in _resolved_spans(body):
        cited_origins.add(eid_to_origin.get(ev_id, ev_id))
    out: list[str] = []
    for member in _distinct_origin_supports(basket):
        origin = str(
            getattr(member, "origin_cluster_id", "")
            or getattr(member, "evidence_id", "")
            or id(member)
        )
        if origin in cited_origins:
            continue
        verbatim = _member_verbatim_clause(basket, member, evidence_pool)
        if verbatim and verbatim.strip():
            cited_origins.add(origin)  # a corroborator now surfaced cannot re-surface
            out.append(verbatim.strip())
    return out


def compose_basket_multicited_synth_primary(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    redraft_fn: Callable[..., str],
) -> str:
    """Compose a CORROBORATED (>=2 distinct-origin SUPPORTS) basket THROUGH the SYNTH_PRIMARY group writer
    (I-deepfix-001 Wave-3a #1344) while PRESERVING all-corroborator multi-citation (§-1.3).

    The synth-primary compose-then-verify + bounded repair core (``_synth_primary_repair_loop`` — the SAME
    ``_verify_all_sentences_synth`` wrapper / own-region gate / chrome screen as the single-basket path)
    authors the coherent core body. THEN every distinct-origin corroborator whose citation the authored
    prose did not itself carry is surfaced as its OWN verbatim K-span clause (``_uncited_corroborator_
    clauses``) — so NO corroborating source is dropped. When synth-primary authors NO prose (the writer
    produced nothing that survived verify), fall back to the UNCHANGED multi-cited co-location
    (``compose_basket_multicited_sentence``), which itself surfaces every corroborator — never a single
    K-span collapse. Faithfulness: strict_verify / provenance / span-grounding are byte-untouched; the
    authored sentences ran the stricter writer wrapper and the appended clauses are verbatim verified spans;
    the caller re-runs the UNCHANGED strict_verify over the rendered draft."""
    scoped_pool = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    kept, _failed = _synth_primary_repair_loop(
        basket, scoped_pool, regions, writer_fn=writer_fn, verify_fn=verify_fn, redraft_fn=redraft_fn,
    )
    body = " ".join(kept)
    # Wave-3a #1344: fire the activation marker ONLY on a non-empty authored body (Fable R5).
    _emit_synth_primary_marker(kept)
    if not body.strip():
        # Synth-primary authored NO prose for this corroborated basket -> preserve EVERY corroborator via
        # the UNCHANGED multi-cited co-location (all-corroborator guarantee); never collapse to one K-span.
        return compose_basket_multicited_sentence(
            basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
        ) or ""
    # Authored coherent prose is the primary body; append a verbatim K-span for any distinct-origin
    # corroborator it did not already cite so NO corroborating source is dropped (§-1.3).
    extra = _uncited_corroborator_clauses(basket, evidence_pool, body)
    return (body + " " + " ".join(extra)) if extra else body


# ── I-deepfix-001 Wave-3 PART 1 (#1344) — COMPANION-FIGURE COMPOSE producer ─────────────────────────


def _member_sentence_units_with_percents(
    member: Any,
    evidence_pool: dict,
    *,
    known_words: "set[str] | None" = None,
) -> list[tuple]:
    """The member's direct_quote split into sentence UNITS that carry a percent figure, each as
    ``(evidence_id, sentence_text, global_start, global_end, percents)`` — GLOBAL offsets into
    ``evidence_pool[eid]`` (via ``_member_global_span``) so the emitted ``[#ev:eid:s-e]`` token
    resolves against exactly the bytes ``strict_verify`` reads.

    Each unit is a whole sentence lifted VERBATIM from the member's own quote (so ``(s, e)`` is
    strictly WITHIN the member's verified region by construction — off >= 0, e <= quote end — and
    always clears the basket-region gate). Chrome / truncated-fragment units are screened out
    (``_compose_junk_screen`` with ``require_sentence_form=True``); units with no percent are dropped
    (they can never be a companion figure). ``percents`` is ``overstatement_guard._primacy_percents``
    output for that unit — the SAME detector the primacy advisory uses, so companion and label agree.
    Pure read; no faithfulness state touched. Returns ``[]`` when the member has no resolvable span."""
    from src.polaris_graph.generator import overstatement_guard as _osg  # noqa: PLC0415
    out: list[tuple] = []
    eid = str(getattr(member, "evidence_id", "") or "")
    quote = str(getattr(member, "direct_quote", "") or "")
    gspan = _member_global_span(member, evidence_pool)
    if not eid or not quote or gspan is None:
        return out
    gstart = gspan[0]
    # I-deepfix-001 Wave-3 PART 1 P2 (#1344): track a running search cursor so a REPEATED identical
    # sentence resolves to its TRUE (iterated) offset, not always the first occurrence. The cursor
    # advances past EVERY located unit (screened or kept) so later duplicates align correctly.
    cursor = 0
    for u in split_into_sentences(quote):
        u = u.strip()
        if not u:
            continue
        off = quote.find(u, cursor)
        if off < 0:
            # Fall back to a global search (splitter normalization edge) so a locatable unit is not
            # silently lost; if still absent, skip it.
            off = quote.find(u)
            if off < 0:
                continue
        else:
            cursor = off + len(u)  # advance past this occurrence for the next iteration
        # Input hygiene: drop allowlist chrome AND subjectless / mid-word-truncated fragments (the
        # K-span PRODUCER screen), so a companion is always a whole real source sentence.
        if _compose_junk_screen(u, known_words, require_sentence_form=True):
            continue
        s = gstart + off
        e = s + len(u)
        pcts = _osg._primacy_percents(u)
        if not pcts:
            continue  # no percent figure -> can never be a same-kind companion
        out.append((eid, u, s, e, pcts))
    return out


def compose_companion_figure_units(
    basket: Any,
    evidence_pool: dict,
    composed_unit: str,
    *,
    verify_fn: Callable[..., Any],
) -> list[str]:
    """Surface the same-kind companion percent(s) a basket member's own span carries but the composed
    headline OMITS — as VERBATIM span slices, re-verified by the UNCHANGED ``strict_verify``.

    The gate is BYTE-FOR-BYTE ``overstatement_guard.primacy_frame_reason`` (shared constants
    ``_PRIMACY_MIN_ABS_GAP_PCT`` / ``_PRIMACY_MIN_RATIO`` + the same measure-stem test), so a surfaced
    companion and the primacy advisory label ALWAYS agree: a member-span percent is surfaced iff it
    (a) is NOT already present in the headline, (b) shares a measure-context stem with a headline
    percent, and (c) differs from it MATERIALLY (absolute percentage-point gap AND ratio). The
    surfaced sentence is the member's OWN verbatim sentence tagged with its REAL global offsets, so it
    re-passes ``verify_fn`` trivially and lands within the basket's own member regions
    (``_tokens_within_basket_regions``) — kept ONLY if BOTH hold. NO connective / lead-in / aggregate
    predicate is ever added (zero non-span words), so no unlicensed frame and no relational quantifier
    can arise; each sentence is one source's own words (single-source attribution, exactly like the
    headline — it asserts NO corroboration and never touches the >=2 distinct-origin floor).

    Returns the kept companion sentences (each already ``[#ev:]``-tagged). Empty when the headline has
    no percent, no member carries a qualifying companion, or every candidate fails verify/region."""
    from src.polaris_graph.generator import overstatement_guard as _osg  # noqa: PLC0415
    kept: list[str] = []
    headline_bare = _EV_TOKEN_RE.sub(" ", composed_unit or "")
    headline_pcts = _osg._primacy_percents(headline_bare)
    if not headline_pcts:
        return kept  # the headline states no percent -> nothing to be one-sided about
    # already-present numbers (incl. the headline's own percents) are never re-surfaced.
    already: set[str] = set(_number_tokens(composed_unit or ""))
    scoped = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    known_words = _known_words_for_compose(evidence_pool)
    seen_span_keys: set[tuple] = set()
    for member in _basket_supports_members(basket):
        for (eid, text, s, e, pcts) in _member_sentence_units_with_percents(
            member, evidence_pool, known_words=known_words,
        ):
            # Does this unit carry at least ONE qualifying companion percent (same-kind, materially
            # different, not already in the headline)? Reuses the primacy gate verbatim.
            qualifies = False
            for (c_str, c_val, c_stems) in pcts:
                if c_str in already:
                    continue
                for (_h_str, h_val, h_stems) in headline_pcts:
                    if not (c_stems & h_stems):
                        continue  # different measure kind (no shared context stem)
                    gap = abs(c_val - h_val)
                    hi_val, lo_val = max(c_val, h_val), min(c_val, h_val)
                    if gap < _osg._PRIMACY_MIN_ABS_GAP_PCT:
                        continue  # not a material absolute gap (rounding neighbour)
                    if lo_val <= 0.0 or (hi_val / lo_val) < _osg._PRIMACY_MIN_RATIO:
                        continue  # not a material ratio
                    qualifies = True
                    break
                if qualifies:
                    break
            if not qualifies:
                continue
            span_key = (eid, s, e)
            if span_key in seen_span_keys:
                continue  # already surfaced this exact unit (another of its percents also qualified)
            sentence = f"{_strip_terminal_punct(text)} [#ev:{eid}:{s}-{e}]."
            res = verify_fn(sentence, scoped)
            vtext = str(getattr(res, "sentence", "") or "").strip() or sentence
            # Keep ONLY if the UNCHANGED strict_verify passes AND the cited token lands within this
            # basket's OWN member regions (anti-cross-claim; True by construction for a within-quote
            # slice, kept as a belt-and-suspenders check).
            if not bool(getattr(res, "is_verified", False)):
                continue
            if not _tokens_within_basket_regions(vtext, regions):
                continue
            seen_span_keys.add(span_key)
            # record ALL of this unit's percents so a sibling unit restating the same figure is not
            # surfaced twice (the primacy "already presented" invariant).
            for (c_str, _cv, _cs) in pcts:
                already.add(c_str)
            kept.append(vtext)
    return kept


def compose_qualifier_elaboration_units(
    basket: Any,
    evidence_pool: dict,
    composed_unit: str,
    *,
    verify_fn: Callable[..., Any],
) -> list[str]:
    """I-deepfix-001 D1 — WITHIN-BASKET QUALIFIER ELABORATION.

    Surface MORE of each source's OWN already-verified content: after the headline clause, lift the
    basket members' OTHER verbatim sentence-units that carry a QUALIFIER (population/scope, timeframe,
    magnitude context, mechanism, stated limitation) but were dropped when the single-source headline
    collapsed the basket to one sentence. Each surfaced unit is the member's OWN verbatim sentence
    tagged with its REAL global offsets, so it re-passes the UNCHANGED ``strict_verify`` (``verify_fn``)
    trivially and lands within this basket's own member regions (``_tokens_within_basket_regions``) —
    kept ONLY if BOTH hold; ungroundable units are simply not emitted (fail-closed).

    This is the sibling of ``compose_companion_figure_units``: same faithfulness contract, different
    selection filter. NO connective / lead-in / aggregate / relational predicate is ever added (zero
    non-span words), so no unlicensed frame and no relational quantifier can arise; each sentence is
    ONE source's own words (single-source attribution, exactly like the headline — it asserts NO
    corroboration and never touches the >=2 distinct-origin floor). It DROPS nothing (keep-all); it
    lifts already-verified content, strengthening faithfulness by fuller expression.

    Skips any unit already surfaced by the headline (same span OR byte-identical text) so it never
    re-states the headline sentence. Returns the kept elaboration sentences (each already ``[#ev:]``-
    tagged). Empty when no member carries a qualifying non-headline sentence, or every candidate fails
    verify/region."""
    kept: list[str] = []
    headline_norm = " ".join((_EV_TOKEN_RE.sub(" ", composed_unit or "")).split()).strip().lower()
    scoped = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    known_words = _known_words_for_compose(evidence_pool)
    seen_span_keys: set[tuple] = set()
    seen_norms: set[str] = set()
    if headline_norm:
        seen_norms.add(headline_norm)
    for member in _basket_supports_members(basket):
        eid = str(getattr(member, "evidence_id", "") or "")
        quote = str(getattr(member, "direct_quote", "") or "")
        gspan = _member_global_span(member, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        gstart = gspan[0]
        cursor = 0
        for u in split_into_sentences(quote):
            u = u.strip()
            if not u:
                continue
            off = quote.find(u, cursor)
            if off < 0:
                off = quote.find(u)
                if off < 0:
                    continue
            else:
                cursor = off + len(u)
            # Input hygiene: drop allowlist chrome + subjectless / mid-word-truncated fragments so an
            # elaboration is always a whole real source sentence.
            if _compose_junk_screen(u, known_words, require_sentence_form=True):
                continue
            # Selection filter: only lift a sentence that carries a real qualifier cue.
            if not _sentence_carries_qualifier(u):
                continue
            u_norm = " ".join(u.split()).strip().lower()
            if u_norm in seen_norms:
                continue  # the headline (or an already-surfaced unit) already states this sentence
            s = gstart + off
            e = s + len(u)
            span_key = (eid, s, e)
            if span_key in seen_span_keys:
                continue
            sentence = f"{_strip_terminal_punct(u)} [#ev:{eid}:{s}-{e}]."
            res = verify_fn(sentence, scoped)
            vtext = str(getattr(res, "sentence", "") or "").strip() or sentence
            # Keep ONLY if the UNCHANGED strict_verify passes AND the cited token lands within this
            # basket's OWN member regions (anti-cross-claim; True by construction for a within-quote
            # slice, kept as a belt-and-suspenders check).
            if not bool(getattr(res, "is_verified", False)):
                continue
            if not _tokens_within_basket_regions(vtext, regions):
                continue
            seen_span_keys.add(span_key)
            seen_norms.add(u_norm)
            kept.append(vtext)
    return kept


def compose_distinct_fact_units(
    basket: Any,
    evidence_pool: dict,
    composed_unit: str,
    *,
    verify_fn: Callable[..., Any],
) -> list[str]:
    """I-deepfix-001 #1344 (Item 11) — L2 ADDITIVE DISTINCT-FACT surfacing (the additive arm of
    sub-topic decomposition).

    THE GAP (abstractive SUCCESS path). The abstractive writer emits ONE paraphrase sentence per
    SUPPORTS member, tagged with that member's WHOLE-quote span token. Its numeric-completeness gate
    (``abstractive_writer.make_writer_verify_fn`` P1-3) forces every SUBSTANTIVE numeric (decimal /
    percent-integer) of the whole span into that one sentence — but a member quote can ALSO ground
    DISTINCT atomic facts the paraphrase drops: absolute counts, currency amounts, year/date data,
    multipliers — bare integers the completeness gate does NOT require. Those distinct facts never
    render on the success path (the per-basket K-span fallback that would surface them fires ONLY when
    the paraphrase FAILS strict_verify). This pass makes L2 ADDITIVE instead of fallback-only: it
    surfaces each such MISSING distinct fact, ADDITIVE to (never replacing) the kept headline.

    Each surfaced fact is a VERBATIM sentence-unit of a member's own ``direct_quote``, tagged with the
    member's REAL global offsets, re-verified by the UNCHANGED ``strict_verify`` (``verify_fn``) and
    gated to the basket's own member regions (``_tokens_within_basket_regions``) — kept ONLY if BOTH
    hold. General sibling of ``compose_companion_figure_units`` (which surfaces same-stem material-gap
    PERCENT companions): here the selection filter is a member sentence-unit that states a BARE-INTEGER
    number (absolute count / currency / date / multiplier — ``_bare_integer_numbers``) absent from the
    composed headline. Decimals and percent-integers are SUBSTANTIVE (P1-3 forces them into the
    paraphrase, and the companion-figure pass owns dropped percents), so this pass never triggers on
    them — which keeps it byte-identical on percent/decimal-only content and non-overlapping with the
    companion-figure pass. The bare integers are exactly the numbers a headline CAN drop on the success
    path (the drb_72 "400,000 jobs by 2030" shape).

    DUPLICATION-SAFE BY CONSTRUCTION (the operator's hard "no duplication" constraint). A unit is
    surfaced ONLY when it carries a bare-integer number (comma-normalized via ``_canon_number``) that
    appears NOWHERE in the composed headline. Because the abstractive writer copies numbers verbatim, a
    number absent from the headline means the headline did NOT state that figure — so the surfaced unit
    is a genuinely NEW fact, never a reword of the headline. A unit whose bare integers are ALL already
    in the headline is skipped: if the headline already covers every distinct numeric fact the basket
    grounds, this pass adds NOTHING. Any number collision under comma-normalization can only cause a SKIP
    (under-emit), never a false surface — so the failure direction is always toward emitting LESS, never
    a duplicate.

    FAITHFULNESS (never relaxes a gate). Each surfaced sentence IS a real cited span (the member's own
    verbatim words at its real offsets), carries NO connective / lead-in / aggregate / relational
    predicate (zero non-span words), asserts NO corroboration (single-source attribution, exactly like
    the headline — it never touches the >=2 distinct-origin floor), and must PASS ``verify_fn`` AND land
    within the basket's own member regions to be kept. It can only ever emit a number that literally
    appears in a real cited span; it never fabricates a figure and never invents a frame. §-1.3
    CONSOLIDATE-keep-all: it DROPS nothing — it lifts already-verified content the headline omitted.

    Skips any unit already surfaced by the headline (byte-identical text) so it never re-states the
    headline sentence. Returns the kept distinct-fact sentences (each already ``[#ev:]``-tagged). Empty
    when the headline already covers every member's numbers, no member carries a distinct numeric
    non-headline sentence, or every candidate fails verify/region."""
    kept: list[str] = []
    headline_norm = " ".join((_EV_TOKEN_RE.sub(" ", composed_unit or "")).split()).strip().lower()
    # Numbers the headline already states (comma-normalized). Seeded from the headline; grown as this
    # pass surfaces units so a second unit restating an already-surfaced figure is not surfaced twice.
    surfaced_numbers: set[str] = {_canon_number(n) for n in _number_tokens(composed_unit or "")}
    scoped = _basket_scoped_pool(basket, evidence_pool)
    regions = _basket_member_regions(basket, evidence_pool)
    known_words = _known_words_for_compose(evidence_pool)
    seen_span_keys: set[tuple] = set()
    seen_norms: set[str] = set()
    if headline_norm:
        seen_norms.add(headline_norm)
    for member in _basket_supports_members(basket):
        eid = str(getattr(member, "evidence_id", "") or "")
        quote = str(getattr(member, "direct_quote", "") or "")
        gspan = _member_global_span(member, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        gstart = gspan[0]
        cursor = 0
        for u in split_into_sentences(quote):
            u = u.strip()
            if not u:
                continue
            off = quote.find(u, cursor)
            if off < 0:
                off = quote.find(u)
                if off < 0:
                    continue
            else:
                cursor = off + len(u)
            # Input hygiene: drop allowlist chrome + subjectless / mid-word-truncated fragments so a
            # surfaced fact is always a whole real source sentence.
            if _compose_junk_screen(u, known_words, require_sentence_form=True):
                continue
            u_norm = " ".join(u.split()).strip().lower()
            if u_norm in seen_norms:
                continue  # the headline (or an already-surfaced unit) already states this sentence
            # SELECTION (bare-integer-anchored, duplication-safe): surface only a unit that states at
            # least one BARE-INTEGER number (count / currency / date / multiplier — the numbers P1-3
            # does NOT force into the paraphrase) that the headline dropped. A unit whose bare integers
            # are all already in the headline adds no missing fact -> skip (no duplication). Decimals /
            # percent-integers never trigger (headline-forced + companion-figure-owned).
            u_bare = _bare_integer_numbers(u)
            if not (u_bare - surfaced_numbers):
                continue
            s = gstart + off
            e = s + len(u)
            span_key = (eid, s, e)
            if span_key in seen_span_keys:
                continue
            sentence = f"{_strip_terminal_punct(u)} [#ev:{eid}:{s}-{e}]."
            res = verify_fn(sentence, scoped)
            vtext = str(getattr(res, "sentence", "") or "").strip() or sentence
            # Keep ONLY if the UNCHANGED strict_verify passes AND the cited token lands within this
            # basket's OWN member regions (anti-cross-claim; True by construction for a within-quote
            # slice, kept as a belt-and-suspenders check — never relaxes the engine).
            if not bool(getattr(res, "is_verified", False)):
                continue
            if not _tokens_within_basket_regions(vtext, regions):
                continue
            seen_span_keys.add(span_key)
            seen_norms.add(u_norm)
            # Grow the seen set with EVERY number this unit stated (bare + any percents/decimals it
            # carries) so a later unit restating the same figure is not surfaced twice.
            surfaced_numbers |= {_canon_number(n) for n in _number_tokens(u)}
            kept.append(vtext)
    return kept


def _compose_section_per_basket(
    section_baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    edges: Any = None,
    equiv_clusters: Any = None,
    agree_map: Any = None,
    redraft_fn: Optional[Callable[..., str]] = None,
    numeric_key_by_cluster: Optional[dict] = None,
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
            # I-deepfix-001 Wave-3a (#1344): the corroborated (>=2 distinct-origin SUPPORTS) baskets are
            # the §-1.3 consolidate-keep-all CORE body. When PG_SYNTH_PRIMARY is ON *and* a group-capable
            # redraft_fn is threaded, compose them THROUGH the synth-primary group writer (the stricter
            # per-sentence writer verify wrapper + bounded repair) instead of the verbatim-K-span
            # co-location — while STILL surfacing every distinct-origin corroborator the authored prose did
            # not itself cite (all-corroborator multi-citation preserved; no verify gate relaxed). Flag OFF
            # OR no redraft_fn => the UNCHANGED multi-cited co-location => byte-identical to pre-Wave-3a.
            if redraft_fn is not None and _synth_primary_enabled():
                composed = compose_basket_multicited_synth_primary(
                    basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
                    redraft_fn=redraft_fn,
                ) or ""
            else:
                composed = compose_basket_multicited_sentence(
                    basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
                ) or ""
        else:
            composed = _compose_one_basket(
                basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
                # I-deepfix-001 Wave-1a (#1344): thread the group-capable re-draft writer so the
                # SYNTH_PRIMARY bounded-repair path can re-call the writer. Default None => byte-identical
                # (the legacy _compose_one_basket path). Wave-3a (#1344): the multi-cited producer above
                # ALSO honours SYNTH_PRIMARY now (compose_basket_multicited_synth_primary), routing
                # corroborated baskets through the same group writer + strict verify while surfacing every
                # corroborator; both single-basket and multi-cite paths share the SYNTH_PRIMARY writer.
                redraft_fn=redraft_fn,
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

        # I-deepfix-001 Wave-3 PART 1 (#1344): COMPANION-FIGURE COMPOSE. DEFAULT-ON (OFF => this block is
        # skipped => byte-identical). Surface the same-kind companion percent(s) this basket's members
        # carry but the headline OMITTED — each a VERBATIM span slice re-verified by the UNCHANGED
        # strict_verify (verify_fn) + own-region gate. Route each surfaced unit through the SAME in-scope
        # dedup as `composed` (seen_spans / seen_texts / seen_numbers_by_footprint) so a TRUE duplicate
        # collapses but a genuinely-new figure is kept. The kept units are already [#ev:]-tokened, so they
        # ride the _draft_directly_tokened path and re-pass the UNCHANGED _rewrite_draft_with_spans +
        # strict_verify tail in multi_section_generator exactly like every other composed unit.
        if _companion_figure_compose_enabled():
            for companion in compose_companion_figure_units(
                basket, evidence_pool, composed, verify_fn=verify_fn,
            ):
                if not companion or not companion.strip():
                    continue
                c_spans = _resolved_spans(companion)
                c_norm = " ".join(companion.split())
                c_footprint = frozenset(c_spans)
                if c_footprint and c_footprint in seen_numbers_by_footprint:
                    c_numbers = _number_tokens(companion)
                    if not (c_numbers - seen_numbers_by_footprint[c_footprint]):
                        continue
                    seen_numbers_by_footprint[c_footprint] = seen_numbers_by_footprint[c_footprint] | c_numbers
                if c_spans and c_spans <= seen_spans and c_norm in seen_texts:
                    continue
                if c_footprint and c_footprint not in seen_numbers_by_footprint:
                    seen_numbers_by_footprint[c_footprint] = _number_tokens(companion)
                seen_spans |= c_spans
                seen_texts.add(c_norm)
                out.append(companion)

        # I-deepfix-001 D1 (#1344): WITHIN-BASKET QUALIFIER ELABORATION. DEFAULT-OFF (OFF => this block
        # is skipped => byte-identical). Surface this basket members' OTHER verbatim qualifier-carrying
        # sentences (population/scope, timeframe, magnitude context, mechanism, stated limitation) the
        # single-source headline dropped — each a VERBATIM span slice re-verified by the UNCHANGED
        # strict_verify (verify_fn) + own-region gate. Route each surfaced unit through the SAME in-scope
        # dedup as `composed` so a TRUE duplicate collapses but a genuinely-new qualifier sentence is
        # kept. Each kept unit is already [#ev:]-tokened, so it rides the same downstream
        # _rewrite_draft_with_spans + strict_verify tail as every other composed unit.
        if _qualifier_elaboration_enabled():
            for elaboration in compose_qualifier_elaboration_units(
                basket, evidence_pool, composed, verify_fn=verify_fn,
            ):
                if not elaboration or not elaboration.strip():
                    continue
                q_spans = _resolved_spans(elaboration)
                q_norm = " ".join(elaboration.split())
                q_footprint = frozenset(q_spans)
                if q_footprint and q_footprint in seen_numbers_by_footprint:
                    q_numbers = _number_tokens(elaboration)
                    if not (q_numbers - seen_numbers_by_footprint[q_footprint]):
                        continue
                    seen_numbers_by_footprint[q_footprint] = seen_numbers_by_footprint[q_footprint] | q_numbers
                if q_spans and q_spans <= seen_spans and q_norm in seen_texts:
                    continue
                if q_footprint and q_footprint not in seen_numbers_by_footprint:
                    seen_numbers_by_footprint[q_footprint] = _number_tokens(elaboration)
                seen_spans |= q_spans
                seen_texts.add(q_norm)
                out.append(elaboration)

        # I-deepfix-001 #1344 (Item 11): L2 ADDITIVE DISTINCT-FACT surfacing. DEFAULT-OFF (OFF => this
        # block is skipped => byte-identical). This is the ADDITIVE arm of sub-topic decomposition: L2's
        # extra distinct facts used to render ONLY as the per-basket fallback when the paraphrase FAILED
        # verify; now, on the SUCCESS path, surface this basket members' OTHER verbatim sentence-units
        # that state a substantive NUMBER the abstractive headline DROPPED (absolute counts, currency,
        # dates, multipliers — the bare integers the writer's numeric-completeness gate does NOT force
        # into the paraphrase). Each is a VERBATIM span slice re-verified by the UNCHANGED strict_verify
        # (verify_fn) + own-region gate, ADDITIVE to (never replacing) `composed`. Route each surfaced
        # unit through the SAME in-scope dedup as `composed` (seen_spans / seen_texts /
        # seen_numbers_by_footprint) so a TRUE duplicate collapses (incl. a unit already surfaced by the
        # companion / qualifier pass above — identical span + text) but a genuinely-new fact is kept.
        # Each kept unit is already [#ev:]-tokened, so it rides the same downstream
        # _rewrite_draft_with_spans + strict_verify tail as every other composed unit.
        if _subtopic_additive_facts_enabled():
            for extra in compose_distinct_fact_units(
                basket, evidence_pool, composed, verify_fn=verify_fn,
            ):
                if not extra or not extra.strip():
                    continue
                x_spans = _resolved_spans(extra)
                x_norm = " ".join(extra.split())
                x_footprint = frozenset(x_spans)
                if x_footprint and x_footprint in seen_numbers_by_footprint:
                    x_numbers = _number_tokens(extra)
                    if not (x_numbers - seen_numbers_by_footprint[x_footprint]):
                        continue
                    seen_numbers_by_footprint[x_footprint] = seen_numbers_by_footprint[x_footprint] | x_numbers
                if x_spans and x_spans <= seen_spans and x_norm in seen_texts:
                    continue
                if x_footprint and x_footprint not in seen_numbers_by_footprint:
                    seen_numbers_by_footprint[x_footprint] = _number_tokens(extra)
                seen_spans |= x_spans
                seen_texts.add(x_norm)
                out.append(extra)

    # I-deepfix-001 M6: ADDITIVE cross-source analytical pass. DEFAULT-OFF => byte-identical (no import,
    # no call). ON => append analytical sentences (two engine-licensed verified atoms) on top of the
    # keep-all single-source units. Each analytical unit carries TWO distinct [#ev] tokens whose two-span
    # footprint is a SUPERSET of either atom's, so the idx8 footprint-dedup above (applied identically
    # below) can never collapse it against an atom — keep-all holds. The downstream
    # _rewrite_draft_with_spans + UNCHANGED strict_verify tail gates each analytical sentence per clause.
    if _cross_source_synthesis_enabled():
        from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: PLC0415
            build_basket_agreement_map,
            compose_cross_source_analytical_units,
            cross_source_thread_consolidation_enabled,
        )
        # I-deepfix-001 FIX 3 (#1344): thread the consolidation AGREEMENT MAP so the cross-source
        # analytical pass sees ``input_threaded=True`` and cross-basket CORROBORATION admits a plan-driven
        # candidate (before FIX 3 the caller threaded only ``edges``, so the composer logged
        # ``input_threaded=False degraded=True`` and agreement never fired from consolidation). DEFAULT-OFF
        # (``PG_CROSS_SOURCE_THREAD_CONSOLIDATION``) => ``build_basket_agreement_map`` returns {} and this
        # is byte-identical to threading the caller's original ``agree_map`` (None today). Built ONLY when
        # the caller did not already thread one. Faithfulness-neutral: the map admits candidacy + telemetry;
        # each emitted connective is STILL independently re-gated per built clause inside ``_process_pair``.
        _threaded_agree_map = agree_map
        if _threaded_agree_map is None and cross_source_thread_consolidation_enabled():
            _threaded_agree_map = build_basket_agreement_map(section_baskets)
        analytical = compose_cross_source_analytical_units(
            section_baskets, evidence_pool,
            writer_fn=writer_fn, verify_fn=verify_fn,
            edges=edges, equiv_clusters=equiv_clusters, agree_map=_threaded_agree_map,
            # Wave-2a: None unless the caller threaded the numeric merge-key lookup (only when
            # PG_NUMERIC_COMPARATOR is on) => the comparator is never consulted otherwise (byte-identical).
            numeric_key_by_cluster=numeric_key_by_cluster,
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
    # B1 (I-deepfix-001 #1344): DEBATE-CLASS con-basket consolidation. When a SELECTED pro-basket
    # refutes another cluster (``refuter_cluster_ids``), CONSOLIDATE the referenced con-basket into
    # this section's compose set even if its evidence was not assigned here — so the minority side
    # composes alongside the majority BEFORE strict_verify instead of being funnel-dropped at
    # selection. CONSOLIDATE-not-DROP (§-1.3): only ADDS an already-built disagreeing basket; the
    # con side re-passes the UNCHANGED faithfulness engine per clause downstream. Default-ON
    # kill-switch; OFF => byte-identical legacy selection. Fail-open on any import/attr error.
    # I-deepfix-001 Wave-9 (#1344) ANTI-DARK activation marker (LOGGING-ONLY, faithfulness-neutral):
    # when PG_DEBATE_CON_BASKET_CONSOLIDATION is ON, surface the HONEST realized count of con-baskets this
    # section-compose call consolidated in (``consolidated=0`` = the section referenced no con-cluster / the
    # con-basket was already selected — an honest ran-ok-zero the canary ACCEPTS, §-1.3, never a >0 gate).
    # The fail-open ``except`` (import/attr fault => legacy funnel, con side dropped) emits the DISTINCT
    # ``unavailable_failopen`` degrade the canary REJECTS — but ONLY once the flag is confirmed ON, so an
    # OFF run stays byte-identical (no marker, no counter). Flag read ONCE per call (LAW VI).
    _b1_flag_on = False
    try:
        from src.polaris_graph.generator.debate_consolidation import (  # noqa: PLC0415
            debate_consolidation_enabled as _b1_enabled,
            augment_with_con_baskets as _b1_augment,
        )
        if _b1_enabled():
            _b1_flag_on = True
            _b1_before = len(out)
            if out:
                out = _b1_augment(out, baskets)
            logger.info(
                "[activation] debate_con_basket_consolidation: consolidated=%d",
                len(out) - _b1_before,
            )
    except Exception:  # noqa: BLE001 — additive consolidation; never break selection
        if _b1_flag_on:
            logger.warning(
                "[activation] debate_con_basket_consolidation: unavailable_failopen"
            )
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

# I-deepfix-001 V3 (#1344) — DIRECT EVIDENCE-SPAN GROUNDING fallback for the no-provenance-token leak.
# The basket path above REPLACES an untokened sentence with the nearest basket's clause; it recovers a
# sentence only when a CONSOLIDATED basket carries a matching isolated-SUPPORTS claim. The drb_72 leak
# left ~15 GROUNDABLE quantitative findings untokened that NO basket bound (the composer wrote them
# straight from a source span, but the consolidation produced no matching basket) — so the basket path
# returns None and strict_verify drops them ``no_provenance_token`` despite the number + prose living
# verbatim in a real evidence row. This fallback FINISHES the repair: for an untokened QUANTITATIVE
# sentence, it finds the real evidence element_id + the char span the finding was written from, attaches
# the correct ``[#ev:<id>:<start>-<end>]`` to the ORIGINAL sentence (PRESERVING the finding), and re-runs
# the UNCHANGED ``verify_fn`` (the same per-clause strict_verify the compose paths use). The sentence is
# kept ONLY IF that unchanged gate PASSES; else it stays dropped (never a fabricated binding). Default-ON;
# ``PG_NO_TOKEN_SPAN_GROUNDING=0`` => the fallback no-ops => byte-identical to the basket-only path.
_NO_TOKEN_SPAN_GROUNDING_ENV = "PG_NO_TOKEN_SPAN_GROUNDING"
# Bounds (LAW VI, overridable) so a large pool can never blow up the entailment-judge spend: at most
# MAX_SOURCES rows that pass the cheap decimal+overlap prefilter are searched, and at most MAX_CANDIDATES
# decimal-containing candidate spans per row are verified.
_SPAN_GROUNDING_MAX_SOURCES_ENV = "PG_NO_TOKEN_SPAN_GROUNDING_MAX_SOURCES"
_SPAN_GROUNDING_MAX_CANDIDATES_ENV = "PG_NO_TOKEN_SPAN_GROUNDING_MAX_CANDIDATES"
_DEFAULT_SPAN_GROUNDING_MAX_SOURCES = 500
_DEFAULT_SPAN_GROUNDING_MAX_CANDIDATES = 24
# Numeric tokens (integers + decimals) — the same shape strict_verify's decimal check uses, so a
# candidate span this fallback accepts also clears the frozen gate's decimal leg by construction.
_DECIMAL_RE_REPAIR = re.compile(r"\d+(?:\.\d+)?")

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


def no_token_span_grounding_enabled() -> bool:
    """Kill-switch ``PG_NO_TOKEN_SPAN_GROUNDING`` (default ON). OFF => the direct evidence-span
    grounding FALLBACK in ``repair_untokened_sentence`` no-ops (the basket-only path is byte-identical
    to before this fix)."""
    return os.getenv(_NO_TOKEN_SPAN_GROUNDING_ENV, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _span_grounding_max_sources() -> int:
    """Bound on the number of prefilter-passing rows searched (``PG_NO_TOKEN_SPAN_GROUNDING_MAX_SOURCES``,
    default 500). Non-integer / negative => the default (never unbounded)."""
    try:
        v = int(os.getenv(_SPAN_GROUNDING_MAX_SOURCES_ENV, "").strip())
        return v if v > 0 else _DEFAULT_SPAN_GROUNDING_MAX_SOURCES
    except ValueError:
        return _DEFAULT_SPAN_GROUNDING_MAX_SOURCES


def _span_grounding_max_candidates() -> int:
    """Bound on decimal-containing candidate spans verified PER row
    (``PG_NO_TOKEN_SPAN_GROUNDING_MAX_CANDIDATES``, default 24). Non-integer / negative => the default."""
    try:
        v = int(os.getenv(_SPAN_GROUNDING_MAX_CANDIDATES_ENV, "").strip())
        return v if v > 0 else _DEFAULT_SPAN_GROUNDING_MAX_CANDIDATES
    except ValueError:
        return _DEFAULT_SPAN_GROUNDING_MAX_CANDIDATES


def _entailment_enforce_active() -> bool:
    """True iff the strict_verify entailment judge runs in ``enforce`` mode. The span-grounding
    fallback is a SEARCH-FOR-A-MATCH shape (it scans the pool for a row whose span carries the
    sentence's numbers + words); without the enforce-mode entailment leg, a COINCIDENTAL decimal +
    2-content-word overlap on a NON-entailing span would launder a drop into a pass. Mirrors the HARD
    enforce-only accept gate in ``provenance_generator._try_reanchor``. Read at call time; a lazy
    import keeps the module load order independent of clinical_generator."""
    try:
        from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
            _entailment_mode as _emode,
        )
        return _emode() == "enforce"
    except Exception:  # pragma: no cover — defensive: never fabricate a pass on an import error
        return False


def _repair_decimals(text: str) -> set:
    """Numeric tokens (integers + decimals) in ``text`` — the strict_verify decimal shape."""
    return {m.group(0) for m in _DECIMAL_RE_REPAIR.finditer(text or "")}


def ground_untokened_sentence_to_span(
    sentence: str,
    evidence_pool: dict,
    *,
    verify_fn: Callable[..., Any],
    min_overlap: int = _DEFAULT_REPAIR_MIN_OVERLAP,
) -> Optional[str]:
    """I-deepfix-001 V3 (#1344) — DIRECT evidence-span grounding for an untokened QUANTITATIVE finding.

    The FINISH of the no-provenance-token repair (the drb_72 ``no_provenance_token`` leak on the ~15
    groundable quantitative findings the basket path could not bind). For an untokened sentence carrying
    a NUMBER, search the evidence pool for the real source row + the char span (inside that row's
    ``direct_quote`` / ``statement``) that the finding was written from: a span that (a) contains ALL the
    sentence's decimals and (b) shares >= ``min_overlap`` content words. Attach the correct
    ``[#ev:<id>:<start>-<end>]`` token to the ORIGINAL sentence (preserving the finding, never rewording
    it) and re-run the UNCHANGED ``verify_fn`` per clause with ``allow_local_window_fallback=False`` so the
    BOUND span must ITSELF entail. Return the tokened sentence ONLY IF that gate PASSES (decimal-in-span +
    percent-role + qualifier + >=2 overlap + BOUND-SPAN-ONLY ENTAILMENT-enforce); else ``None`` (the
    finding stays dropped — never a fabricated binding).

    Returns ``None`` (no grounding) when: the fallback flag is OFF; the sentence already carries a token;
    entailment is not in ``enforce`` mode (the search-for-a-match laundering guard); the sentence carries
    no decimal (no numeric anchor -> not this fallback's scope); the sentence has < ``min_overlap``
    content words; or NO span in any row verifies.

    §-1.3 / FAITHFULNESS: the frozen faithfulness engine (strict_verify / NLI / provenance / span-
    grounding) is UNTOUCHED. This attaches a token to the sentence's OWN real span and keeps it ONLY when
    the UNCHANGED gate confirms it — it can only recover a finding that already clears the full bar. A
    genuinely ungroundable sentence is STILL dropped. Enforce-only + numeric-anchor bound the search so a
    coincidental match can never launder a drop into an unverified pass.
    """
    if not no_token_span_grounding_enabled():
        return None
    if not sentence or _EV_TOKEN_RE.search(sentence):
        return None
    # Enforce-only accept gate (faithfulness-critical; mirrors _try_reanchor). Off/warn => no grounding.
    if not _entailment_enforce_active():
        return None
    sentence_decimals = _repair_decimals(sentence)
    if not sentence_decimals:
        return None  # numeric-anchor scope: a sentence with no number is left to the basket path
    sentence_words = _repair_content_words(sentence)
    if len(sentence_words) < min_overlap:
        return None
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _reanchor_candidate_spans,
    )
    max_sources = _span_grounding_max_sources()
    max_candidates = _span_grounding_max_candidates()
    # Place the token INLINE — before any trailing terminal punctuation — so the downstream
    # ``strict_verify`` sentence splitter (terminal ``.!?]`` + whitespace) keeps the token WITH its
    # sentence instead of splitting it into a tokenless fragment (which would re-drop it
    # no_provenance_token). ``stem`` + ``terminal`` reassemble around the emitted token.
    base = sentence.rstrip()
    _term_match = re.search(r"[.!?]+$", base)
    if _term_match:
        stem = base[: _term_match.start()].rstrip()
        terminal = _term_match.group(0)
    else:
        stem = base
        terminal = ""
    searched = 0
    for evidence_id, ev in (evidence_pool or {}).items():
        if not isinstance(ev, dict):
            continue
        direct_quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not direct_quote:
            continue
        # Cheap prefilter (no judge call): the row must carry EVERY sentence decimal and >= min_overlap
        # shared content words, else no tight span in it can ground the finding.
        if not sentence_decimals.issubset(_repair_decimals(direct_quote)):
            continue
        if len(sentence_words & _repair_content_words(direct_quote)) < min_overlap:
            continue
        searched += 1
        if searched > max_sources:
            break
        # Only verify TIGHT candidate spans that themselves carry all the sentence's decimals (so the
        # bound span — not a distant part of the row — supports the number). Bounded per row.
        verified_candidates = 0
        for (cand_start, cand_end) in _reanchor_candidate_spans(direct_quote):
            if verified_candidates >= max_candidates:
                break
            if not sentence_decimals.issubset(_repair_decimals(direct_quote[cand_start:cand_end])):
                continue
            verified_candidates += 1
            candidate = f"{stem} [#ev:{evidence_id}:{cand_start}-{cand_end}]{terminal}"
            # I-deepfix-001 V3 iter-2 (#1344) — Codex P1 laundering-leak fix: force
            # ``allow_local_window_fallback=False`` so the BOUND span ``[#ev:id:start-end]`` must
            # ITSELF entail. Without it, ``verify_sentence_provenance`` defaults the flag ``True``
            # (provenance_generator.py:2049) and a candidate whose bound span is NEUTRAL can still
            # PASS via a DIFFERENT in-row local window — laundering an unverified binding through with
            # its token pointing at a non-entailing span. Mirrors the enforce-only accept gate in
            # ``provenance_generator._try_reanchor`` (:1573/:1625/:1663). Every production ``verify_fn``
            # on this path accepts the kwarg: the bare ``verify_sentence_provenance`` takes it directly;
            # the abstractive ``make_writer_verify_fn`` wrapper takes ``**kwargs`` and already
            # ``setdefault``s it False. A ``verify_fn`` that REJECTS the kwarg raises ``TypeError`` ->
            # caught below -> candidate SKIPPED (fail-closed; never a laundered default-True pass).
            try:
                res = verify_fn(candidate, evidence_pool, allow_local_window_fallback=False)
            except Exception:  # pragma: no cover — a verify error / signature mismatch is a non-recovery, never a pass
                continue
            if bool(getattr(res, "is_verified", False)):
                logger.info(
                    "[verified_compose] V3 span-grounding: bound untokened quantitative finding to "
                    "%s[%d-%d] (re-verified by the UNCHANGED strict_verify)",
                    evidence_id, cand_start, cand_end,
                )
                return candidate
    return None


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
    # I-deepfix-001 Wave-3 PART 2 ARM B P1a (#1344): a no-verified-span DISCLOSURE placeholder (the
    # legacy insufficient-evidence gap OR the ARM-B degraded-verify label) is NOT a repair candidate —
    # it must NEVER be rebound to a foreign SUPPORTS basket (that would launder an honest gap disclosure
    # into a fabricated cited claim). Return it UNCHANGED (exactly as a tokened sentence is), so
    # ``_repair_untokened_draft`` counts it as "not repaired" and leaves it as-is. Faithfulness: a
    # disclosure is not a claim; rebinding it is the bug.
    if _is_no_verified_span_disclosure(sentence):
        return sentence
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
    # I-deepfix-001 V3 (#1344): FALLBACK — direct evidence-span grounding. The basket path above binds
    # a sentence only when a consolidated basket carries a matching isolated-SUPPORTS claim; the ~15
    # drb_72 groundable quantitative findings had NO such basket, so they fell straight into the
    # ``no_provenance_token`` drop despite living verbatim (number + prose) in a real evidence row.
    # FINISH the repair by grounding the ORIGINAL sentence to the real span it was written from and
    # re-running the UNCHANGED verify_fn. Preserves the finding; keeps it ONLY when the frozen gate
    # passes; returns None (still dropped) otherwise. Enforce-gated + numeric-anchored (never launders).
    grounded = ground_untokened_sentence_to_span(
        sentence, evidence_pool, verify_fn=verify_fn, min_overlap=min_overlap,
    )
    if grounded is not None:
        return grounded
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


# ── I-deepfix-001 F1 (#1344) — ROUTE EVERY CONSOLIDATED BASKET TO A SECTION ──────────────────────
#
# THE LEAK (drb_72: ~657 baskets -> 53 rendered sentences): a basket composes ONLY if one of its
# ``supporting_members`` evidence_ids is among a section plan's assigned ``ev_ids`` (the rule
# ``_section_baskets_for_compose`` enforces). The outline LLM assigns a fixed ~30 rows per section,
# so ~600 consolidated, span-verifiable baskets have NO home section and never become a cited claim —
# ~90% of honestly-retrieved-and-verified evidence earns zero coverage. This is the biggest measured
# recall leak.
#
# THE FIX (§-1.3 CONSOLIDATE / throttle-REMOVAL, faithfulness-neutral): after the outline assigns its
# primaries, give every ORPHAN basket (whose members intersect NO plan's ev_ids) a home. Assign each
# to its best-matching section by topical content-word overlap (basket claim/subject/predicate vs the
# section title/focus); a basket that matches NO section is routed to a keep-all residual "Additional
# Corroborated Findings" section appended once. Routing = appending the orphan basket's own
# ``supporting_members`` evidence_ids to the chosen plan's ``ev_ids`` so the UNCHANGED
# ``_section_baskets_for_compose`` now returns that basket for the section, and the UNCHANGED
# per-basket compose + strict_verify tail render one verified sentence for it. This DROPS nothing,
# CAPS nothing, and TARGETS no number: it stops DISCARDING baskets that had no section. Each rendered
# sentence still re-passes the frozen faithfulness engine (strict_verify / NLI / provenance /
# span-grounding) per clause — untouched. Default-OFF (``PG_ROUTE_ALL_BASKETS``) => ``plans`` is
# returned unchanged (byte-identical); ON => zero stranded verified baskets.
_ROUTE_ALL_BASKETS_ENV = "PG_ROUTE_ALL_BASKETS"
_RESIDUAL_COVERAGE_TITLE = "Additional Corroborated Findings"


def route_all_baskets_enabled() -> bool:
    """Kill-switch ``PG_ROUTE_ALL_BASKETS`` (default OFF). OFF =>
    ``route_orphan_baskets_to_section_plans`` returns the plan list unchanged => byte-identical."""
    return os.getenv(_ROUTE_ALL_BASKETS_ENV, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _basket_member_ev_ids(basket: Any) -> list[str]:
    """The evidence_ids of the basket's ``supporting_members`` (order-preserving, deduped, non-empty).
    These are the ids ``_section_baskets_for_compose`` matches on, so appending one to a plan's
    ``ev_ids`` gives the basket a home section."""
    out: list[str] = []
    seen: set[str] = set()
    for m in getattr(basket, "supporting_members", None) or []:
        eid = str(getattr(m, "evidence_id", "") or "")
        if eid and eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _basket_topic_words(basket: Any) -> set:
    """Topical content words of a basket's CLAIM (claim_text + subject + predicate). Used to pick the
    best-matching section title/focus. Pure read; touches no faithfulness state."""
    parts = [
        str(getattr(basket, "claim_text", "") or ""),
        str(getattr(basket, "subject", "") or ""),
        str(getattr(basket, "predicate", "") or ""),
    ]
    return _repair_content_words(" ".join(parts))


def _plan_topic_words(plan: Any) -> set:
    """Topical content words of a section plan (title + focus)."""
    parts = [
        str(getattr(plan, "title", "") or ""),
        str(getattr(plan, "focus", "") or ""),
    ]
    return _repair_content_words(" ".join(parts))


def _extend_plan_ev_ids(plan: Any, ev_ids: list[str]) -> int:
    """Append ``ev_ids`` (order-preserving, dedup vs the plan's existing set) to ``plan.ev_ids``.
    Returns the count newly added. Mutates ``plan.ev_ids`` in place (it is a mutable list)."""
    existing = plan.ev_ids if isinstance(getattr(plan, "ev_ids", None), list) else []
    have = set(existing)
    added = 0
    for eid in ev_ids:
        if eid and eid not in have:
            existing.append(eid)
            have.add(eid)
            added += 1
    plan.ev_ids = existing
    return added


def route_orphan_baskets_to_section_plans(
    plans: list,
    credibility_analysis: Any,
    *,
    section_plan_cls: Any,
    residual_title: str = _RESIDUAL_COVERAGE_TITLE,
) -> list:
    """F1: route EVERY consolidated basket to a section so no verified basket is stranded.

    A basket is an ORPHAN when NONE of its ``supporting_members`` evidence_ids is in ANY plan's
    ``ev_ids`` (i.e. ``_section_baskets_for_compose`` would return it for no section). Each orphan is
    assigned to the section whose title+focus shares the most topical content words with the basket's
    claim (ties broken by section order); a basket matching NO section (overlap 0 with every plan) is
    routed to a single appended keep-all residual section. Assignment = appending the orphan basket's
    own member evidence_ids to the chosen plan's ``ev_ids``.

    Returns the (possibly residual-extended) plan list. Default-OFF (``PG_ROUTE_ALL_BASKETS``) or an
    empty ``plans``/basket list => ``plans`` returned unchanged (byte-identical).

    §-1.3: pure CONSOLIDATE placement — it stops DISCARDING baskets with no home; it drops no source,
    caps nothing, targets no number. The frozen faithfulness engine is untouched: every routed
    basket's rendered sentence re-passes the UNCHANGED strict_verify per clause downstream.
    """
    if not route_all_baskets_enabled():
        return plans
    baskets = list(getattr(credibility_analysis, "baskets", None) or [])
    if not plans or not baskets:
        return plans

    claimed: set[str] = set()
    for p in plans:
        claimed |= _section_assigned_ev_ids(p)

    plan_words = [(p, _plan_topic_words(p)) for p in plans]
    residual_plan = None
    routed = 0
    for basket in baskets:
        member_ids = _basket_member_ev_ids(basket)
        if not member_ids:
            continue  # no evidence to route (cannot give it a home)
        if set(member_ids) & claimed:
            continue  # already reachable by some section — not an orphan
        bw = _basket_topic_words(basket)
        best_plan = None
        best_overlap = 0
        for p, pw in plan_words:
            overlap = len(bw & pw)
            if overlap > best_overlap:
                best_overlap = overlap
                best_plan = p
        if best_plan is not None and best_overlap >= 1:
            _extend_plan_ev_ids(best_plan, member_ids)
        else:
            if residual_plan is None:
                residual_plan = section_plan_cls(
                    title=residual_title, focus=residual_title, ev_ids=[], archetype="",
                )
            _extend_plan_ev_ids(residual_plan, member_ids)
        claimed |= set(member_ids)
        routed += 1

    out_plans = list(plans)
    if residual_plan is not None and residual_plan.ev_ids:
        out_plans.append(residual_plan)
    if routed:
        logger.info(
            "[verified_compose] F1 route-all-baskets: routed %d orphan basket(s) to sections "
            "(residual section=%s)",
            routed, "yes" if residual_plan is not None else "no",
        )
    return out_plans
