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


def _compose_junk_screen(unit: str) -> bool:
    """I-beatboth-011 §3.4 (#1289): True iff ``unit`` is allowlist crawl/social/masthead chrome —
    INPUT HYGIENE applied per sentence-unit at the verbatim-emit (and abstractive-writer input)
    consumers, NEVER inside the verify pool/regions and NEVER a verdict. Reuses the shared
    ``weighted_enrichment._make_junk_screen`` (``is_boilerplate_or_nonassertional`` + the high-precision
    multi-word chrome list). P1-4: allowlist-anchored only — a real short sentence is KEPT (no length
    drop). Faithfulness-safe: boilerplate is not a corroborating source, so removing it is not a §-1.3
    DROP. Lazy + fail-CONSERVATIVE: on any import failure fall back to the boilerplate helper, and only
    if THAT is unavailable keep the unit (never silently drop real prose)."""
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
        return bool(_JUNK_SCREEN(unit))
    except Exception:
        return False


def build_verified_span_draft(basket: Any, evidence_pool: dict) -> Optional[str]:
    """The basket-id-bound VERBATIM K-span fallback: a sentence built from the basket's own
    strongest isolated-``SUPPORTS`` member's verbatim ``direct_quote`` (the span it was verified
    against), tagged with that member's own ``[#ev:<id>:0-<len>]`` provenance token so it re-passes
    strict_verify trivially (it IS the verified span). Returns None when the basket has no verified
    span resolvable in the pool (caller emits an insufficient-evidence disclosure instead)."""
    for m in _basket_supports_members(basket):
        eid = str(getattr(m, "evidence_id", "") or "")
        quote = str(getattr(m, "direct_quote", "") or "").strip()
        gspan = _member_global_span(m, evidence_pool)
        if not eid or not quote or gspan is None:
            continue
        start, end = gspan
        # PER-SENTENCE units (Codex P1-4): a multi-sentence verified span must NOT ship as one blob
        # with a single trailing token (strict_verify would split it and drop the un-tokened earlier
        # units). Each sentence carries the member's OWN span token — the whole verified span grounds
        # each sub-sentence (it literally contains it). Offsets are the member's REAL GLOBAL offsets
        # (Codex P1-3) so downstream resolution anchors to the verified span, never 0-len of a span
        # that may differ from the global row for a shared source.
        units = [u.strip() for u in (split_into_sentences(quote) or [quote]) if u.strip()]
        # I-beatboth-011 §3.4 (#1289): drop allowlist crawl/social chrome units (input hygiene); keep all
        # real content incl. short real sentences. If EVERY unit is chrome, fall through to the next
        # SUPPORTS member (then K-span / insufficient-evidence). Faithfulness-safe, never a verdict.
        units = [u for u in units if not _compose_junk_screen(u)]
        out = []
        for u in units:
            # I-beatboth-009 (#1287): the provenance token must sit BEFORE the terminal period so the
            # downstream strict_verify splitter (split_into_sentences: terminal-punct + whitespace +
            # [A-Z0-9]) keeps it ATTACHED. The prior "U. [#ev:...]" form orphaned the token into a
            # contentless fragment -> no_provenance_token -> verified=0 (the P6 v2 STORM-section zero).
            u_core = _strip_terminal_punct(u)
            out.append(f"{u_core} [#ev:{eid}:{start}-{end}].")
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
    clauses are then joined by a SEMANTICALLY-NEUTRAL ``connective`` (default ``"; "``) with each
    continuation lowercased at its first alpha char, so the result stays ONE sentence under the
    production sentence splitter and asserts NO emergent aggregate predicate (the F1-2 guard is
    deferred; this producer never licenses a relational quantifier).

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
    if len(clauses) < 2:
        # Not a multi-cited synthesis — the caller falls back to the per-basket producer.
        return None
    parts = [clauses[0].rstrip()]
    for clause in clauses[1:]:
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


def _compose_section_per_basket(
    section_baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
) -> list[str]:
    """PRIMARY per-section prose producer: compose EVERY basket of the section (the contract
    entities are a SUBSET — this is what moves the scored breadth off the contract-slot bound).
    Returns one composed string per basket, in order. Order-stable.

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
        vacuously "all duplicate")."""
    out: list[str] = []
    seen_spans: set[tuple[str, int, int]] = set()
    seen_texts: set[str] = set()
    for basket in (section_baskets or []):
        composed = _compose_one_basket(
            basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
        )
        # §3.5: suppress the internal insufficient-evidence marker before it can leak into report.md.
        if composed.strip().startswith("[insufficient verified evidence"):
            continue
        # idx8 (Codex #1289 P1): drop a unit ONLY when it is a true duplicate — its resolved spans are
        # already emitted AND its normalized text is byte-identical to a sibling. Requiring text
        # identity (not merely a span subset) keeps every differing claim. Apply AFTER the §3.5 marker
        # filter so a token-less marker never reaches this check.
        spans = _resolved_spans(composed)
        norm = " ".join(composed.split())
        if spans and spans <= seen_spans and norm in seen_texts:
            continue
        seen_spans |= spans
        seen_texts.add(norm)
        out.append(composed)
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
