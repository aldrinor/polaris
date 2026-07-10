"""S4 OUTLINE — ORCH-1 basket-digest menu + ORCH-2 requirements block (Design 5, ruling R2).

FS-Researcher completion piece C2: the outline planner must read CONSOLIDATED-CLAIM
DIGESTS (claim text + corroboration + tier mix + member ev_ids) — the semantic
equivalent of the paper's ``knowledge_base/`` — NOT bare row titles. Today the large-pool
outline menu terses every row to ``ev_id + tier + title`` and drops the statement
(``multi_section_generator.py:2636-2666``), so the planner assigns ev_ids to sections while
never seeing what the rows SAY. This module builds the richer menu by CONSOLIDATION
(baskets), never by dropping rows (§-1.3 weight-and-consolidate): a many-source claim shows
as ONE heavy basket line instead of N title rows, and every pool row is accounted for
(basket member OR singleton line) — the 100%-of-pool honesty invariant.

Pure: no LLM, no network, deterministic (LAW V one-responsibility). The sanitizer is
INJECTED (identity in tests) so importing this module pulls no generator-package deps.

ORCH-2 requirements block: renders the user's deliverable asks (required sections / order,
audience, tone, reference style, length ask) + explicit scope constraints into a text block
the caller appends to the outline USER prompt. Empty spec => "" => byte-identical no-append.
The spec is read via ``.get`` so it works against either Design 3's DeliverableSpec (once
WP-1b lands) or a plain protocol dict today — build-to-interface, no fake stand-in.

PUSH A (same-work-aware digest, Fable push-to-ceiling): ``build_outline_digest`` gains an
OPTIONAL ``same_work_groups`` argument — the exact cp3 ``payload.same_work_groups`` shape
(``{member_evidence_ids, canonical_index, same_work_id}``). When supplied it (a) renders each
basket's corroboration at WORK level (dedupe members through the alias map) as ``xK works (N
rows)`` while KEEPING every member ev_id disclosed (§-1.3 consolidate, drop nothing), and (b)
collapses same-work SINGLETON copies into ONE line carrying the canonical ev_id + its alias
ids — every alias still accounted for by ``covered_ev_ids()`` so the 100%-of-pool invariant
holds. ``same_work_groups=None`` (the default) is BYTE-IDENTICAL to the pre-PUSH-A behaviour.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

logger = logging.getLogger(__name__)

# ── knob defaults (LAW VI; exact names/defaults from Design 5 §6 + master §6). These are
# the resolver-swap seam per master §1.5: when run_config.py (WP-0b) lands, each read below
# becomes ``run_config.get(<id>)`` — same names, same defaults, byte-identical when unset.
# PUSH 3 (de-starve the digest, §9.1.8 read-the-API-don't-guess): the prior 60000 default
# STARVED a routine 686-row cp3 pool — its FULL verbose digest is 85712 chars, so the guard
# tersed all 512 singletons to title-only (degraded=True) even though the tersed menu was
# only 54145 chars. The serving model is GLM-5.2 (OpenRouter `z-ai/glm-5.2`): context_length
# 1,048,576 tokens, top-provider max_completion 131,072 (queried live, not guessed). The outline
# INPUT budget = context - reasoning(PG_OUTLINE_REASONING_MAX_TOKENS=6144) - content
# (PG_OUTLINE_MIN_MAX_TOKENS=16384) - system prompt; 200000 chars is ~50K input tokens, which
# leaves >20% margin against even a conservative 200K-token GLM-5.x context floor and is trivial
# against GLM-5.2's real 1M window. This is >2x the measured full-verbose size (85712), so the
# routine cp3 pool renders degraded=False with room to spare. The guard MECHANISM is unchanged —
# only the default budget rose (LAW VI: still env-overridable via PG_OUTLINE_DIGEST_MAX_CHARS).
PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT = 200000

_CLAIM_MAX_CHARS = 200          # basket representative claim, per Design 5 ORCH-1 (~200c)
_TITLE_MAX_CHARS = 120          # singleton title, matches the small-pool menu (:2616)
_STATEMENT_MAX_CHARS = 160      # singleton statement, matches the small-pool menu (:2617)
# Item 2 (same-work TITLE fallback): the MINIMUM normalized-title length that may fold two rows as
# one work. Long enough that a distinctive paper title ("GPTs are GPTs..." -> ~40 alnum chars) folds
# while a short/generic heading (two DIFFERENT OECD reg-policy docs) does NOT false-merge (§-1.3: a
# fold keeps ALL rows; a false fold would misstate corroboration, so the guard stays conservative).
_TITLE_FALLBACK_MIN_CHARS = 25


def _env_int(name: str, default: int) -> int:
    """Read an int env knob, falling back to ``default`` on unset/garbage (LAW VI)."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def _identity_sanitizer(text: str) -> tuple[str, int]:
    """Fallback used only if the real provenance sanitizer is not injected AND not
    importable. Never silently strips content — returns the text unchanged."""
    return text, 0


def _default_sanitizer() -> Callable[[str], tuple[str, int]]:
    """Resolve the real provenance sanitizer lazily so importing this module needs no
    generator-package dependency. Tests inject an identity sanitizer directly.

    Item 15: the fallback is narrowed to ``ImportError`` ONLY and LOGGED loudly. Previously a bare
    ``except Exception`` swallowed ANY failure inside the sanitizer (a bug, a bad signature) and
    silently returned identity — which DISABLES the §9.1.7 prompt-injection defense without a trace.
    Now a genuine sanitizer error PROPAGATES (fail loud), and the only-legitimate offline/unit case
    (the module is not importable) still fails open to identity BUT emits a WARNING so the disabled
    defense is DISCLOSED, never silent (§-1.3 fail-loud-never-silent)."""
    try:
        from src.polaris_graph.generator.provenance_generator import (
            sanitize_evidence_text,
        )

        return sanitize_evidence_text
    except ImportError as exc:  # offline/unit context ONLY: fail open to identity, but DISCLOSE it
        logger.warning(
            "outline_digest: real provenance sanitizer unimportable (%s) — falling back to the "
            "IDENTITY sanitizer; the §9.1.7 prompt-injection defense is DISABLED for this digest "
            "build. Inject a real sanitizer in production.", exc,
        )
        return _identity_sanitizer


@dataclass
class OutlineDigestMenu:
    """The consolidated-claim menu the outline planner reads instead of bare titles."""

    basket_lines: list[str]                 # one line per multi-member finding cluster
    singleton_lines: list[str]              # one line per row in no multi-member cluster
    ev_id_to_basket: dict[str, str]         # member ev_id -> basket id (full map; never elided)
    total_chars: int                        # rendered menu size (headroom accounting)
    degraded: bool = False                  # a headroom-guard terse pass fired
    # item 11: True when EVEN the fully-tersed+elided menu is STILL over ``max_chars`` — a
    # pathological pool that would ship a silently oversized prompt. Disclosed (never silent): the
    # builder also logs a WARNING, and the caller must surface/act on this flag (fail loud).
    oversized: bool = False
    basket_member_ev_ids: dict[str, list[str]] = field(default_factory=dict)
    # PUSH A: canonical singleton ev_id -> its FOLDED same-work alias ev_ids (the copies of the
    # same underlying work that collapsed onto that one singleton line). Empty when
    # ``same_work_groups`` was not supplied. ``covered_ev_ids()`` unions these so every alias is
    # still accounted for by the 100%-of-pool invariant (§-1.3 consolidate — folded, never dropped).
    singleton_alias_ev_ids: dict[str, list[str]] = field(default_factory=dict)
    # PUSH A: basket id -> WORK-level corroboration (distinct works among the basket's members,
    # deduped through the same-work alias map). Equals the row count when no members share a work
    # (so it is byte-identical to ``len(members)`` when ``same_work_groups`` is absent). This is the
    # honest corroboration the orphan check reads — 4 rows of 2 works corroborate a claim TWICE.
    basket_work_corroboration: dict[str, int] = field(default_factory=dict)
    # P2-2: basket id -> True when the basket's representative row is a fetch INTERSTITIAL (§-1.3.1(a)
    # chrome, e.g. an all-"Just a moment..." Cloudflare basket). Surfaced so a downstream disclosure
    # (the S4 orphan-reassign audit) can flag the basket as chrome — DELETION still stays with the
    # S5/junk gate; this is disclosure only. Empty when the digest saw no chrome baskets.
    basket_chrome: dict[str, bool] = field(default_factory=dict)

    def render(self) -> str:
        """The prompt menu text — baskets first (heaviest claims), then singletons."""
        return "\n".join(self.basket_lines + self.singleton_lines)

    def covered_ev_ids(self) -> set[str]:
        """Every ev_id the menu accounts for (basket member OR singleton OR a folded alias)."""
        covered = set(self.ev_id_to_basket)
        for line in self.singleton_lines:
            # singleton lines start with the canonical ev_id token (see _singleton_line)
            covered.add(line.split(" ", 1)[0])
        # PUSH A: same-work aliases collapsed onto a singleton line are still covered rows —
        # union them explicitly (the line only prints the canonical head token).
        for canonical, aliases in self.singleton_alias_ev_ids.items():
            covered.add(canonical)
            covered.update(aliases)
        return covered


def _ev_id_at(evidence: Sequence[Mapping[str, Any]], index: int) -> str:
    """Resolve a cluster member index to its ev_id, fail-loud on a corrupt index
    (a clusters/evidence mismatch is a real bug, never silently papered over — LAW II)."""
    if not (0 <= index < len(evidence)):
        raise ValueError(
            f"finding cluster references evidence index {index} outside the pool of "
            f"{len(evidence)} rows — clusters and evidence are misaligned (refusing to "
            "build a garbage outline menu)."
        )
    return str(evidence[index].get("evidence_id", "") or "")


# Item 3a/10: leading fetch/format chrome tokens that must be peeled off a TITLE before it is
# normalized to a work key. "(PDF) GPTs are GPTs" must key IDENTICALLY to "GPTs are GPTs" — the
# leading "pdf" is alphanumeric, so it survives the alnum-normalize and would otherwise SPLIT the
# same work into two. Exact known tokens only (content-integrity, not a lexical quality guess).
_TITLE_CHROME_PREFIXES = ("[pdf]", "(pdf)", "url source:", "pdf source:")

# P1-1(a): trailing SITE-CHROME separators. A web/repository page title is commonly rendered as
# "<work title> <sep> <site or venue>" — "GPTs are GPTs: ... of LLMs | GovAI", "How Will AI Affect
# the US Labor Market? | Goldman Sachs", "Experimental Evidence ... by Noy, Zhang :: SSRN". The tail
# after the LAST such separator is site chrome, NOT part of the work title, so it must be peeled
# before the work key is computed (else the same paper posted on two sites keys as two works). Only
# the STRUCTURALLY-UNAMBIGUOUS separators are used: the pipe "|" (a CMS/template separator that
# effectively never appears inside an academic title) and the double-colon "::" (SSRN/RePEc style).
# The single hyphen " - " and en/em dash are DELIBERATELY EXCLUDED: they appear both as site suffixes
# ("... - Sciences Po") AND inside real titles/subtitles, so blanket-stripping them would false-merge
# distinct generically-titled works (the item-3b ev_044/ev_073 guard + its test). Dash-tailed
# same-works are instead consolidated by the cp3 same_work_groups + the truncation prefix fold. This
# is question-agnostic web-title STRUCTURE — no site allow-list, no entity list, no magic per-question.
_TITLE_CHROME_TAIL_SEPARATORS = (" | ", " :: ")
# a trailing site/venue chrome segment is SHORT — at most this many whitespace tokens. Generous
# enough for real venue names ("J.P. Morgan Global Research", "YIP Institute Economic Policy") while
# the >= _TITLE_FALLBACK_MIN_CHARS remainder floor stops a real title from being eaten.
_TITLE_CHROME_TAIL_MAX_WORDS = 6


def _strip_one_trailing_chrome_segment(t: str) -> str | None:
    """P1-1(a): peel ONE trailing site-chrome segment (" | <site>" / " :: <site>") when it is SHORT
    (<= ``_TITLE_CHROME_TAIL_MAX_WORDS`` tokens) AND the remaining head still carries a real work
    title (>= ``_TITLE_FALLBACK_MIN_CHARS`` alnum chars). Uses the RIGHTMOST unambiguous separator.
    Returns the trimmed head, or ``None`` when no safe trailing-chrome segment is present (caller
    stops). Structure-based, no site allow-list — never drops the row, only cleans the KEY input."""
    best_cut = -1
    best_len = 0
    for sep in _TITLE_CHROME_TAIL_SEPARATORS:
        idx = t.rfind(sep)
        if idx > best_cut:
            best_cut = idx
            best_len = len(sep)
    if best_cut <= 0:
        return None
    head = t[:best_cut].rstrip()
    tail = t[best_cut + best_len:].strip()
    if not tail or len(tail.split()) > _TITLE_CHROME_TAIL_MAX_WORDS:
        return None
    if len(re.sub(r"[^a-z0-9]", "", head.lower())) < _TITLE_FALLBACK_MIN_CHARS:
        return None
    return head


def _strip_leading_and_ellipsis(t: str) -> str:
    """Peel leading chrome prefixes (``[pdf]`` / ``(pdf)`` / ``url source:``) and a trailing ellipsis
    (``...`` / unicode ``…``), iteratively. Split out of ``_strip_title_chrome`` so the P1-1(c)
    inverse-fold predicate can test the trailing SITE-chrome tail BEFORE it is peeled."""
    changed = True
    while changed:
        changed = False
        low = t.lower()
        for pref in _TITLE_CHROME_PREFIXES:
            if low.startswith(pref):
                t = t[len(pref):].strip()
                changed = True
                break
        if changed:
            continue
        if t.endswith("...") or t.endswith("…"):
            t = (t[:-3] if t.endswith("...") else t[:-1]).rstrip()
            changed = True
    return t


def _strip_title_chrome(title: str) -> str:
    """Peel leading chrome tokens (``[pdf]`` / ``(pdf)`` / ``url source:``), trailing ellipsis
    (``...`` / ``…``), AND trailing site-chrome tails (" | GovAI" / " :: SSRN") off a title so a
    chrome-prefixed, truncated, or site-suffixed title normalizes to the SAME key as its clean form
    (items 3a + P1-1(a)). Loops until stable so stacked chrome ("[PDF] Title ... | Site") all peels.
    Never drops the row — only cleans the KEY input (§-1.3: a fold keeps every row, it only reports
    them as one work)."""
    t = (title or "").strip()
    changed = True
    while changed:
        changed = False
        peeled = _strip_leading_and_ellipsis(t)
        if peeled != t:
            t = peeled
            changed = True
            continue
        tail_stripped = _strip_one_trailing_chrome_segment(t)
        if tail_stripped is not None and tail_stripped != t:
            t = tail_stripped
            changed = True
    return t


def _normalized_title_key(title: str) -> str | None:
    """Item 2 (same-work TITLE fallback): a work_key derived from a source TITLE, for folding
    TITLE-IDENTICAL works the cp3 URL/DOI ``same_work_groups`` missed (the same paper posted at two
    URLs — an arXiv PDF + a GovAI mirror of "GPTs are GPTs", or Noy_Zhang_1.pdf + "Experimental
    Evidence on the Productivity Effects..."). Lowercase, keep only alphanumerics. Returns
    ``title:<norm>`` ONLY when the normalized title is >= ``_TITLE_FALLBACK_MIN_CHARS`` — a
    short/generic title (two DIFFERENT OECD reg-policy docs) returns ``None`` and is NEVER folded,
    so the fallback cannot false-merge distinct works. Never a drop (§-1.3): a fold keeps ALL rows,
    it only reports them as ONE work for corroboration.

    Item 3a: leading fetch/format chrome ("(PDF)", "URL Source:") and trailing ellipsis are peeled
    FIRST (``_strip_title_chrome``), so a chrome-prefixed or truncated title keys IDENTICALLY to its
    clean form instead of splitting the same underlying work into two."""
    norm = re.sub(r"[^a-z0-9]", "", _strip_title_chrome(title).lower())
    if len(norm) < _TITLE_FALLBACK_MIN_CHARS:
        return None
    return f"title:{norm}"


def _title_had_chrome_tail(title: str) -> bool:
    """P1-1(c): True when the title carries a trailing site-chrome tail (" | Site" / " :: Site") that
    ``_strip_title_chrome`` peels. Used as the inverse-fold license — a chrome-tailed LONG key may fold
    onto a shorter clean title it strictly startswith (the GUARDED prefix fold), never by unconditional
    key rewriting. Tested with leading/ellipsis chrome peeled first so the tail test is clean."""
    return _strip_one_trailing_chrome_segment(
        _strip_leading_and_ellipsis((title or "").strip())
    ) is not None


def _colon_prefix_fold_key(title: str, existing_keys: set[str]) -> str | None:
    """P1-1(b): a LEADING "<author/site> : <work title>" chrome prefix ("Daniel Rock (University of
    Pennsylvania) : GPTs are GPTs: An Early Look...") keys to the SAME work as the clean title — but
    ONLY as a fold-time fallback, never unconditionally (a real title may itself contain a colon). For
    each colon in the (chrome-peeled) title, the after-colon remainder is a candidate key; return the
    FIRST candidate that is >= the fallback floor AND already exists as ANOTHER row's base title key.
    ``None`` when no remainder resolves to an existing work — so a genuine subtitle colon (whose
    remainder matches nothing in the pool) NEVER folds. §-1.3: a fold keeps ALL rows, only reports
    them as one work."""
    t = _strip_title_chrome(title)
    for m in re.finditer(r":", t):
        remainder = t[m.end():].strip()
        ckey = _normalized_title_key(remainder)
        if ckey is not None and ckey in existing_keys:
            return ckey
    return None


def _build_alias_map(
    same_work_groups: Sequence[Mapping[str, Any]] | None,
    evidence: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """ev_id -> work_key from the cp3 ``same_work_groups`` payload (PUSH A) + the item-2 TITLE fold.

    Each group carries ``member_evidence_ids`` (all corroborating rows of ONE underlying work)
    and a stable ``same_work_id`` string (``url:`` / ``doi:`` / ``title:`` key). The work_key is
    that ``same_work_id`` (falling back to ``canon:<canonical_index>`` only if the id is blank).
    ``setdefault`` keeps the first group to claim an ev_id, so the map is deterministic regardless
    of group order. Returns ``{}`` when no groups are supplied AND no ``evidence`` is passed (=>
    every row is its own work => byte-identical to the pre-PUSH-A path).

    Item 2 + P1-1 (normalized-TITLE fallback): when ``evidence`` is supplied, rows the cp3 URL/DOI
    groups did NOT unify are folded by ``_normalized_title_key`` whenever >= 2 rows share ONE
    distinctive (>=25 alnum-char) work title across its variants — TITLE-identical, chrome-prefixed
    ("(PDF) X"), truncated ("X ..."), SITE-tailed ("X | GovAI", "X :: SSRN" — P1-1 a/c), or
    author-prefixed ("Author (...) : X" — P1-1 b) — the same underlying work the ``same_work_id``
    missed (e.g. the SSRN-tailed "Experimental Evidence ... by Noy, Zhang :: SSRN" folds onto the clean
    "Experimental Evidence ...", and "Daniel Rock (...) : GPTs are GPTs: ..." folds onto the clean
    "GPTs are GPTs: ..."). NOTE: the eloundou "GPTs are GPTs | GovAI" mirror keys "...ofllms" after
    P1-1(a) peels its "| GovAI" site tail, but its title TEXT differs from the "An Early Look..." paper,
    so it folds only via cp3 URL/DOI, NOT by title (measured — not a title fold). Deterministic
    (evidence order = canonical). A title group that
    OVERLAPS an existing cp3 group ADOPTS that group's key (so the two are UNIFIED into one work,
    not left as two); a title group the cp3 groups never touched takes the ``title:`` key itself.
    ``evidence=None`` => no title fold (byte-identical to the cp3-only map)."""
    alias_of: dict[str, str] = {}
    for group in (same_work_groups or []):
        if not isinstance(group, Mapping):
            continue
        work_key = str(group.get("same_work_id") or "").strip()
        if not work_key:
            canonical_index = group.get("canonical_index")
            work_key = f"canon:{canonical_index}" if canonical_index is not None else ""
        members = [str(m) for m in (group.get("member_evidence_ids") or []) if str(m)]
        if not work_key or not members:
            continue
        for ev_id in members:
            alias_of.setdefault(ev_id, work_key)

    # Item 2 + P1-1: normalized-TITLE fallback fold for works the cp3 URL/DOI groups missed —
    # title-identical, chrome-prefixed, truncated, SITE-tailed, or author-prefixed variants of ONE work.
    if evidence:
        title_groups: dict[str, list[str]] = {}
        # Item 3b guard: title keys with at least one member row whose RAW title was TRUNCATED (ended
        # with "..."/"…" BEFORE _strip_title_chrome peeled it). Only a truncated key may forward-prefix-
        # fold onto a longer full-title key — a non-truncated short title that merely happens to be a
        # prefix of a longer distinct work (ev_044 "Artificial Intelligence and the Labor Market" vs
        # ev_073 "...- Sciences Po") must NOT false-merge. §-1.3: a WRONG fold misstates corroboration.
        truncated_keys: set[str] = set()
        # P1-1(c) guard: title keys with at least one member whose RAW title carried a trailing SITE-
        # chrome tail (" | Site" / " :: SSRN") that _strip_title_chrome peeled — the INVERSE-fold license.
        chrome_tailed_keys: set[str] = set()
        # P1-1(b): (raw_title, base_key) per row, for the leading "<Author> : <Title>" colon fold.
        _row_title_keys: list[tuple[str, str]] = []
        for row in evidence:
            if not isinstance(row, Mapping):
                continue
            ev_id = str(row.get("evidence_id", "") or "")
            if not ev_id:
                continue
            _raw_title = str(row.get("title", "") or "").strip()
            tkey = _normalized_title_key(_raw_title)
            if tkey is None:
                continue
            title_groups.setdefault(tkey, []).append(ev_id)
            if _raw_title.endswith("...") or _raw_title.endswith("…"):
                truncated_keys.add(tkey)
            if _title_had_chrome_tail(_raw_title):
                chrome_tailed_keys.add(tkey)
            _row_title_keys.append((_raw_title, tkey))

        base_keys = set(title_groups.keys())
        fold_target: dict[str, str] = {}

        def _final_key(k: str) -> str:
            _seen: set[str] = set()
            while k in fold_target and k not in _seen:
                _seen.add(k)
                k = fold_target[k]
            return k

        _keys_by_len = sorted(title_groups.keys(), key=lambda k: (len(k), k))
        # Item 3b FORWARD (PREFIX FOLD): a TRUNCATED short key keys to a PREFIX of the full title's key
        # ("...Impact ..." truncations vs the full paper title). Fold onto the shortest STRICTLY-longer
        # key it is a full prefix of. Every key here is already >= _TITLE_FALLBACK_MIN_CHARS alnum chars
        # (the floor), so an exact-prefix match on 25+ identical leading chars is a strong same-work
        # signal. Only a TRUNCATED short key may fold — a non-truncated short prefix of a longer DISTINCT
        # work stays its own work (the ev_044/ev_073 guard). Non-truncated identical titles still fold by
        # EXACT key equality (same title_groups bucket). Deterministic (length then lexicographic).
        for _i, _short in enumerate(_keys_by_len):
            if _short not in truncated_keys:
                continue
            for _long in _keys_by_len[_i + 1:]:
                if len(_long) > len(_short) and _long.startswith(_short):
                    fold_target[_short] = _long
                    break

        # P1-1(c) INVERSE (PREFIX FOLD): a TRUNCATED-or-chrome-tailed LONG key folds onto the LONGEST
        # non-truncated SHORTER key it strictly startswith — the SSRN/author-tailed "Experimental
        # Evidence ... by Noy Zhang" (":: SSRN" peeled) folding onto the clean "Experimental Evidence
        # ...". Today only truncated-SHORT->LONG folded, so the chrome/author-tailed LONG copy never
        # unified with its clean SHORT title. Same 25-char floor (every key clears it) + the item-4
        # false-merge guard below still applies. Skip a key already forward-folded; never point a key at
        # a target that folds back onto it (no 2-cycle — the _final_key check).
        _fold_eligible = truncated_keys | chrome_tailed_keys
        _short_targets = sorted(
            (k for k in title_groups if k not in truncated_keys), key=lambda k: (-len(k), k)
        )
        for _long in sorted(title_groups.keys(), key=lambda k: (-len(k), k)):
            if _long in fold_target or _long not in _fold_eligible:
                continue
            for _short in _short_targets:
                if _short == _long or len(_short) >= len(_long):
                    continue
                if _long.startswith(_short) and _final_key(_short) != _long:
                    fold_target[_long] = _short
                    break

        # P1-1(b) COLON PREFIX FALLBACK: a leading "<author/site> : <title>" chrome prefix keys to the
        # SAME work as the clean title, but ONLY when the after-colon remainder resolves to an EXISTING
        # clean-title key (never unconditional — a real title may contain a colon). Skip a key already
        # folded above; guard against a cycle via _final_key.
        for _raw_title, _tkey in _row_title_keys:
            if _tkey in fold_target:
                continue
            _ckey = _colon_prefix_fold_key(_raw_title, base_keys)
            if _ckey is not None and _ckey != _tkey and _final_key(_ckey) != _tkey:
                fold_target[_tkey] = _ckey

        merged_groups: dict[str, list[str]] = {}
        for _k, _members in title_groups.items():
            merged_groups.setdefault(_final_key(_k), []).extend(_members)

        for tkey, members in merged_groups.items():
            if len(members) < 2:
                continue  # a unique title is its own work — never fold a lone title
            # Item 4 (ALIAS-MAP FALSE-MERGE GUARD): collect the DISTINCT cp3 work keys the members
            # already carry. If TWO OR MORE different cp3 works share this normalized title, do NOT
            # false-merge them onto one key — leave each stamped member on its OWN cp3 key and fold
            # only the UNCLAIMED (title-only) members onto the title key. Only when the group carries
            # exactly ONE (or zero) cp3 key do we unify the whole group onto it. §-1.3: a fold never
            # drops a row; a WRONG fold would misstate corroboration, so the guard stays conservative.
            stamped = {alias_of[e] for e in members if e in alias_of}
            if len(stamped) >= 2:
                for ev_id in members:
                    if ev_id not in alias_of:
                        alias_of[ev_id] = tkey
            else:
                canonical_key = next(iter(stamped)) if stamped else tkey
                for ev_id in members:
                    alias_of[ev_id] = canonical_key
    return alias_of


# Item 6c (§-1.3.1(a) content-integrity, NOT a lexical quality guess): a row whose TITLE is a known
# fetch INTERSTITIAL is a failed fetch surfaced as a Cloudflare/bot/404 page — not a source. The row
# is KEPT (disclosure), but TAGGED so the planner never anchors on it. Exact/known-prefix match only.
_CHROME_INTERSTITIAL_TAG = " [CHROME — failed fetch, do not anchor]"
_CHROME_INTERSTITIAL_PREFIXES = (
    "just a moment",
    "attention required",
    "access denied",
    "verifying you are human",
    "are you a robot",
    "one moment, please",
    "please wait",
    "checking your browser",
)
_CHROME_INTERSTITIAL_EXACT = frozenset({
    "404", "404 not found", "404: not found", "page not found",
    "403 forbidden", "error 404", "error 403",
})


def _is_chrome_interstitial(title: str) -> bool:
    """True when a row TITLE is a known fetch interstitial (Cloudflare "Just a moment...", "Access
    Denied", a bare "404", "Attention Required"). Exact / known-prefix match only — content-integrity
    under §-1.3.1(a), NEVER a lexical quality judgement. Conservative: an unknown title => ``False``
    (KEEP + present normally; the tag only fires on a confirmed interstitial string)."""
    t = (title or "").strip().lower().rstrip(" .!")
    if not t:
        return False
    if any(t.startswith(p) for p in _CHROME_INTERSTITIAL_PREFIXES):
        return True
    return t in _CHROME_INTERSTITIAL_EXACT


# Item 4 (§-1.3 principle 1 — WEIGHT surfaced, never a drop): a row the topic judge WEIGHT-demoted for
# relevance (topic_offtopic_demoted, or content_relevance_label in {demoted, escalated_demoted}) is
# KEPT and presented, but marked so the planner PREFERS non-demoted sources when both support a claim.
# This is GUIDANCE only — never a filter. The stamp fields ride onto the bank row from cp2 (build_bank).
_DEMOTED_WEIGHT_TAG = " [w:demoted]"
_DEMOTED_LABELS = frozenset({"demoted", "escalated_demoted"})


def _is_weight_demoted(row: Mapping[str, Any]) -> bool:
    """True when a bank row carries a relevance WEIGHT-demote stamp (item 4). Surfaced to the planner
    as a compact ``[w:demoted]`` marker — §-1.3 principle 1: the weight is DISCLOSED, never a drop.
    A missing stamp => not demoted (present normally). Never raises on a malformed row (fail-open)."""
    if not isinstance(row, Mapping):
        return False
    if row.get("topic_offtopic_demoted"):
        return True
    return str(row.get("content_relevance_label", "") or "").strip().lower() in _DEMOTED_LABELS


def _basket_line(
    bid: str,
    corroboration: int,
    tiers: list[str],
    claim: str,
    member_ev_ids: list[str],
    *,
    elide_members: bool,
    work_corroboration: int | None = None,
    row_count: int | None = None,
    chrome: bool = False,
    demoted: bool = False,
) -> str:
    tier_csv = ",".join(tiers)
    members = (
        f"({len(member_ev_ids)} members)"
        if elide_members
        else "members: " + ",".join(member_ev_ids)
    )
    # PUSH A: when work-level corroboration is known, render the HONEST count — how many distinct
    # WORKS (not rows) back the claim — while still listing every member row (aliases stay).
    # ``work_corroboration is None`` (no same_work_groups) => the legacy ``xN sources`` head =>
    # byte-identical.
    if work_corroboration is None:
        head = f"[x{corroboration} sources: {tier_csv}]"
    else:
        head = f"[x{work_corroboration} works ({row_count} rows): {tier_csv}]"
    # item 6c: a basket built from a fetch-interstitial title (32 "Just a moment..." Cloudflare rows
    # consolidated into whole baskets this run) is tagged so the planner does not anchor on it. Kept
    # (disclosure), just not sold as evidence (§-1.3.1(a) content-integrity).
    chrome_tag = _CHROME_INTERSTITIAL_TAG if chrome else ""
    # item 4: a WEIGHT-demoted basket (its representative row demoted for relevance) is marked after
    # the head so the planner prefers non-demoted baskets when both support a claim (§-1.3 principle 1
    # — weight surfaced, never dropped). ``demoted=False`` (default) => "" => byte-identical.
    demoted_tag = _DEMOTED_WEIGHT_TAG if demoted else ""
    return f'{bid} {head}{demoted_tag}{chrome_tag} claim: "{claim}" {members}'


def _singleton_line(
    ev_id: str, tier: str, title: str, statement: str, alias_ev_ids: list[str],
    *, title_only: bool, seminal: bool = False, chrome: bool = False, demoted: bool = False,
) -> str:
    # PUSH A: same-work copies collapsed onto this line are disclosed inline after the tier;
    # empty ``alias_ev_ids`` (the no-same_work_groups path) => no tag => byte-identical.
    tag = f" (+{len(alias_ev_ids)} same-work: {','.join(alias_ev_ids)})" if alias_ev_ids else ""
    # Item 4a: an explicit seminal marker on a T1 singleton (the tier tag alone reads as one more
    # row in an 58k-char menu). Placed AFTER the ev_id token so ``covered_ev_ids`` still parses the
    # head. ``seminal=False`` (default) => "" => byte-identical.
    seminal_tag = " [seminal T1 — consider for anchoring]" if seminal else ""
    # item 6c: a singleton whose title is a known fetch interstitial (Cloudflare "Just a moment...",
    # "Access Denied", "404") is tagged — kept for disclosure, but never sold to the planner as an
    # anchorable source (§-1.3.1(a) content-integrity). Placed after the tier so ``covered_ev_ids``
    # still parses the ev_id head token. ``chrome=False`` (default) => "" => byte-identical.
    chrome_tag = _CHROME_INTERSTITIAL_TAG if chrome else ""
    # item 4: a WEIGHT-demoted singleton (demoted for relevance) is marked right after the tier so the
    # planner prefers non-demoted sources when both support a claim (§-1.3 principle 1 — weight
    # surfaced, never a drop). Placed after ``[{tier}]`` so ``covered_ev_ids`` still parses the ev_id
    # head token. ``demoted=False`` (default) => "" => byte-identical.
    demoted_tag = _DEMOTED_WEIGHT_TAG if demoted else ""
    if title and statement and not title_only:
        return f"{ev_id} [{tier}]{demoted_tag}{chrome_tag}{seminal_tag}{tag} | title: {title} | {statement}"
    if title:
        return f"{ev_id} [{tier}]{demoted_tag}{chrome_tag}{seminal_tag}{tag} | title: {title}"
    return f"{ev_id} [{tier}]{demoted_tag}{chrome_tag}{seminal_tag}{tag}: {statement}"


def _is_title_like(statement: str, title: str) -> bool:
    """PUSH 4 (S4-local title-like mitigation): True when a candidate basket claim is really a
    bare TITLE, not a claim sentence — an S3 representative_statement that fell back to the row
    title (measured title-like on a large fraction of cp3 baskets). Detected deterministically:
    empty; a ``[PDF]`` / ``(PDF)`` chrome prefix; a truncated ``...`` tail; or byte-equal to the
    row title. This is a LOCAL display mitigation (pick a better member statement), never a drop
    — the upstream fix (S3 should emit a claim sentence) is filed as a separate note."""
    s = (statement or "").strip()
    if not s:
        return True
    low = s.lower()
    # item 10: also treat a "URL Source:" chrome prefix and a unicode-ellipsis "…" truncation tail
    # as title-like (the ascii "..." tail + "[pdf]"/"(pdf)" prefixes were already covered).
    if low.startswith("[pdf]") or low.startswith("(pdf)") or low.startswith("url source:"):
        return True
    if s.endswith("...") or s.endswith("…"):
        return True
    if title and s == title.strip():
        return True
    return False


def build_outline_digest(
    evidence: Sequence[Mapping[str, Any]],
    clusters: Sequence[Any],
    *,
    max_chars: int | None = None,
    sanitizer: Callable[[str], tuple[str, int]] | None = None,
    same_work_groups: Sequence[Mapping[str, Any]] | None = None,
    prioritize_tier1: bool = False,
) -> OutlineDigestMenu:
    """Build the basket-digest menu from the evidence pool + finding clusters.

    ``clusters`` is duck-typed over ``FindingCluster`` (``representative_index``,
    ``member_indices``, ``corroboration_count``, ``member_hosts``) so this module never
    imports finding_dedup. A cluster with >= 2 members becomes a BASKET line; every other
    pool row becomes a SINGLETON line — so the menu accounts for 100% of the pool
    (invariant, asserted below; §-1.3 CONSOLIDATE-keep-all, zero rows dropped).

    ``same_work_groups`` (PUSH A, OPTIONAL — the exact cp3 ``payload.same_work_groups`` shape:
    ``{member_evidence_ids, canonical_index, same_work_id}``). When supplied, an alias map
    ev_id->work_key is built; basket lines then report corroboration at WORK level (``xK works
    (N rows)``) with every member id still listed, and same-work SINGLETON copies collapse into
    ONE line (canonical ev_id + alias ids). ``None`` (default) => byte-identical to the
    pre-PUSH-A menu.

    Headroom guard (Design 5 ORCH-1): if the rendered menu exceeds ``max_chars`` the
    singleton statements terse away FIRST (row kept), then basket member lists elide to
    counts (the ev_id -> basket map is ALWAYS preserved) — content degrades gracefully; no
    row ever leaves the menu.
    """
    if sanitizer is None:
        sanitizer = _default_sanitizer()
    if max_chars is None:
        max_chars = _env_int("PG_OUTLINE_DIGEST_MAX_CHARS", PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT)

    # PUSH A: alias map ev_id -> work_key. ``work_aware`` gates the honest work-level render so
    # ``same_work_groups=None`` stays byte-identical (an explicit ``[]`` opts into the new render
    # with an empty alias map => work count == row count, zero singleton folds).
    work_aware = same_work_groups is not None
    # Item 2: feed the pool so ``_build_alias_map`` also folds TITLE-identical works the cp3 groups
    # missed — but ONLY on the work-aware path, so ``same_work_groups=None`` stays byte-identical.
    alias_of = _build_alias_map(same_work_groups, evidence if work_aware else None)

    def _work_key(ev_id: str) -> str:
        return alias_of.get(ev_id, ev_id)

    def _clean(text: str) -> str:
        return sanitizer(text or "")[0]

    # ── 1. multi-member baskets, deterministically ordered (heaviest corroboration first,
    #        ties by representative ev_id then member set) so line order is worker-independent.
    multi = [c for c in clusters if len(getattr(c, "member_indices", []) or []) >= 2]

    def _sort_key(c: Any) -> tuple[Any, ...]:
        _member_ev = [e for e in (_ev_id_at(evidence, i) for i in getattr(c, "member_indices")) if e]
        rep = _ev_id_at(evidence, int(getattr(c, "representative_index")))
        members = tuple(sorted(_member_ev))
        if work_aware:
            # Item 5: order baskets by WORK-level corroboration (distinct works), NOT raw ROW count.
            # B00 must be the basket backed by the MOST distinct works — 4 duplicate rows of ONE work
            # (work_corroboration=1) must sink BELOW a genuine 2-work basket. 44 of 69 baskets this
            # run were x1-work clusters leading the menu by row count. Tie-break by row count, then
            # rep + member set for worker-independent determinism.
            #
            # Item 6c composed with item 5: a basket whose representative row is a fetch interstitial
            # ("Just a moment..." Cloudflare) is a failed fetch, NOT corroboration — its members are N
            # distinct FAILED urls, which would otherwise float it to the TOP of the menu by work
            # count (the exact opposite of item 6c's "stop selling chrome to the planner"). Sink such
            # baskets BELOW every real basket (leading sort dim), keeping work-sort WITHIN the real and
            # within the chrome groups. Still KEPT + tagged (disclosure, §-1.3.1(a)) — only its RANK
            # drops. Non-work-aware path is byte-identical (this whole branch is work-aware only).
            _rep_title = str(evidence[int(getattr(c, "representative_index"))].get("title", "") or "")
            _chrome = 1 if _is_chrome_interstitial(_rep_title) else 0
            _wc = len({_work_key(e) for e in _member_ev})
            return (_chrome, -_wc, -len(_member_ev), rep, members)
        return (-int(getattr(c, "corroboration_count", 0)), rep, members)

    multi_sorted = sorted(multi, key=_sort_key)

    basket_specs: list[dict[str, Any]] = []
    ev_id_to_basket: dict[str, str] = {}
    basket_member_ev_ids: dict[str, list[str]] = {}
    basket_work_corroboration: dict[str, int] = {}
    basket_chrome: dict[str, bool] = {}  # P2-2: bid -> representative row is a fetch interstitial
    for idx, c in enumerate(multi_sorted):
        bid = f"B{idx:02d}"
        # item 9: pair each member's ev_id with its tier and sort them TOGETHER by ev_id, so the
        # tier at position k lines up with member_ev_ids[k]. Previously ``tiers`` was built in
        # member_indices order while ``member_ev_ids`` was sorted, so the planner read a scrambled
        # tier<->member pairing (a reproduced mismatch).
        member_pairs = sorted(
            (_ev_id_at(evidence, i), str(evidence[i].get("tier", "") or ""))
            for i in getattr(c, "member_indices")
        )
        member_pairs = [(e, t) for (e, t) in member_pairs if e]
        member_ev_ids = [e for (e, _t) in member_pairs]
        rep_row = evidence[int(getattr(c, "representative_index"))]
        # PUSH 4 (title-like claim mitigation, S4-local): the basket claim is the representative
        # statement, falling back to the title. When that representative statement is title-like
        # (a chrome/PDF prefix, a truncated tail, or byte-equal to the row title), scan THIS
        # basket's OTHER member statements (in member order) for the first non-title-like one and
        # use it instead — so the planner reads a real claim sentence, not a bare title. Falls back
        # to the representative when no member has a claim sentence (deterministic, never a drop).
        rep_stmt = str(rep_row.get("statement", "") or "")
        rep_title = str(rep_row.get("title", "") or "")
        chosen_claim = rep_stmt or rep_title
        if _is_title_like(rep_stmt, rep_title):
            for _mi in getattr(c, "member_indices"):
                _m_row = evidence[int(_mi)]
                _m_stmt = str(_m_row.get("statement", "") or "")
                _m_title = str(_m_row.get("title", "") or "")
                if _m_stmt and not _is_title_like(_m_stmt, _m_title):
                    chosen_claim = _m_stmt
                    break
        # item 5: strip leading fetch/format chrome ("[PDF] ", "URL Source:") + trailing ellipsis off
        # the chosen claim BEFORE cleaning, so a basket whose members are all title-like renders a
        # CLEAN title instead of "[PDF] ... ...". Cosmetic display fix only — the underlying S3 defect
        # (representative_statement is a title, not a ~200-char claim sentence) stays FILED on the S3
        # wheel; this never papers over it there. Harmless on a real claim sentence (no chrome to peel).
        claim = _clean(_strip_title_chrome(chosen_claim))[:_CLAIM_MAX_CHARS]
        tiers = [t for (_e, t) in member_pairs]   # item 9: aligned with member_ev_ids (same order)
        # PUSH A: distinct WORKS among the members (rows sharing a same_work_id count once).
        # Equals len(member_ev_ids) when no members share a work (byte-identical default).
        work_corroboration = len({_work_key(e) for e in member_ev_ids})
        basket_specs.append(
            {
                "bid": bid,
                "corroboration": int(getattr(c, "corroboration_count", 0)),
                "tiers": tiers,
                "claim": claim,
                "members": member_ev_ids,
                "work_corroboration": work_corroboration,
                "row_count": len(member_ev_ids),
                # item 6c: a basket consolidated from fetch-interstitial rows (whole "Just a
                # moment..." Cloudflare baskets this run) — tagged, kept, never anchored.
                "chrome": _is_chrome_interstitial(rep_title),
                # item 4: WEIGHT-demote marker (representative row demoted for relevance) — surfaced,
                # never a drop (§-1.3 principle 1). Falls back to False on a bank row with no stamp.
                "demoted": _is_weight_demoted(rep_row),
            }
        )
        basket_member_ev_ids[bid] = member_ev_ids
        basket_work_corroboration[bid] = work_corroboration
        basket_chrome[bid] = bool(_is_chrome_interstitial(rep_title))  # P2-2 disclosure flag
        for e in member_ev_ids:
            # keep-first on a rare cross-basket collision (deterministic ordering fixes it)
            ev_id_to_basket.setdefault(e, bid)

    # ── 2. singletons = every pool row not claimed by a multi-member basket. PUSH A: same-work
    #        copies among the singletons COLLAPSE into one line (canonical = first seen in pool
    #        order; the rest become disclosed aliases). A row with no same-work group is its own
    #        work and stays a standalone line. ``work_aware=False`` => no fold => byte-identical.
    singleton_specs: list[dict[str, Any]] = []
    singleton_alias_ev_ids: dict[str, list[str]] = {}
    work_to_canonical: dict[str, str] = {}
    for row in evidence:
        ev_id = str(row.get("evidence_id", "") or "")
        if not ev_id or ev_id in ev_id_to_basket:
            continue
        work_key = _work_key(ev_id) if work_aware else ev_id
        if work_aware and work_key in work_to_canonical:
            # a same-work copy of an already-emitted singleton — fold, never drop (§-1.3)
            canonical = work_to_canonical[work_key]
            # item 9: a DUPLICATE evidence_id row in the pool resolves work_key -> itself, so canonical
            # == ev_id — appending would emit a spurious "(+1 same-work: ev_X)" self-alias. Skip the
            # self-append; the row is already covered by its canonical line (no double-count).
            if ev_id != canonical:
                singleton_alias_ev_ids[canonical].append(ev_id)
            continue
        work_to_canonical[work_key] = ev_id
        singleton_alias_ev_ids.setdefault(ev_id, [])
        _raw_title = str(row.get("title", "") or "")
        _raw_stmt = str(row.get("statement", "") or "")
        # item 10: when the statement is just the title (or title-like), render TITLE-ONLY. Printing
        # both duplicates the same text on nearly every singleton (the real 686-row menu did this),
        # wasting tens of KB of prompt for zero added information. Emptying the statement here makes
        # ``_singleton_line`` fall through to its title-only branch (§-1.3: nothing is dropped from
        # the pool — the row + tier stay; only the redundant second copy of its own title is elided).
        _stmt_render = (
            "" if (_raw_title and _is_title_like(_raw_stmt, _raw_title))
            else _clean(_raw_stmt)[:_STATEMENT_MAX_CHARS]
        )
        singleton_specs.append(
            {
                "ev_id": ev_id,
                "tier": str(row.get("tier", "") or ""),
                "title": _clean(_raw_title)[:_TITLE_MAX_CHARS],
                "statement": _stmt_render,
                # item 6c: a singleton whose title is a known fetch interstitial — tagged, kept
                # (disclosure), never sold to the planner as anchorable evidence (§-1.3.1(a)).
                "chrome": _is_chrome_interstitial(_raw_title),
                # item 4: WEIGHT-demote marker (row demoted for relevance) — surfaced to the planner,
                # never a drop (§-1.3 principle 1). False on a bank row with no demote stamp.
                "demoted": _is_weight_demoted(row),
            }
        )
    # attach the (possibly appended-to) alias lists to each canonical spec
    for spec in singleton_specs:
        spec["alias_ev_ids"] = singleton_alias_ev_ids.get(spec["ev_id"], [])
    # drop empty alias entries so the map holds only genuine folds (keeps covered_ev_ids clean)
    singleton_alias_ev_ids = {k: v for k, v in singleton_alias_ev_ids.items() if v}

    # Item 4a (seminal-T1 survival): when armed, stable-sort the singleton block so T1 rows LEAD.
    # A foundational T1 work on no multi-member basket (Acemoglu-Restrepo automation-tasks, Autor
    # why-still-jobs) must not sink to the bottom of a 58k-char menu and lose the planner's attention
    # — a GenAI-labor report that never anchors Acemoglu/Autor loses to ChatGPT/Gemini on expert eyes.
    # Python's sort is STABLE, so pool order is preserved WITHIN each tier band; this reorders the
    # DISPLAY only (the fold + ev_id_to_basket map are already finalised above), so the 100%-of-pool
    # invariant below is untouched. §-1.3: weight-GUIDANCE (surface order), never a cap/drop.
    # ``prioritize_tier1=False`` (default) => no reorder => byte-identical.
    if prioritize_tier1:
        singleton_specs.sort(
            key=lambda s: 0 if str(s.get("tier", "")).strip().upper() == "T1" else 1
        )

    def _render(*, title_only: bool, elide_members: bool) -> tuple[list[str], list[str], int]:
        b_lines = [
            _basket_line(
                s["bid"], s["corroboration"], s["tiers"], s["claim"], s["members"],
                elide_members=elide_members,
                work_corroboration=(s["work_corroboration"] if work_aware else None),
                row_count=(s["row_count"] if work_aware else None),
                chrome=bool(s.get("chrome")),
                demoted=bool(s.get("demoted")),
            )
            for s in basket_specs
        ]
        s_lines = [
            _singleton_line(
                s["ev_id"], s["tier"], s["title"], s["statement"], s["alias_ev_ids"],
                title_only=title_only,
                seminal=(prioritize_tier1 and str(s.get("tier", "")).strip().upper() == "T1"),
                chrome=bool(s.get("chrome")),
                demoted=bool(s.get("demoted")),
            )
            for s in singleton_specs
        ]
        total = sum(len(x) + 1 for x in b_lines + s_lines)
        return b_lines, s_lines, total

    # ── 3. headroom guard: full → terse singletons → elide basket members (Design 5 ORCH-1).
    degraded = False
    basket_lines, singleton_lines, total = _render(title_only=False, elide_members=False)
    if total > max_chars:
        degraded = True
        basket_lines, singleton_lines, total = _render(title_only=True, elide_members=False)
    if total > max_chars:
        basket_lines, singleton_lines, total = _render(title_only=True, elide_members=True)

    # item 11: even the fully-tersed+elided menu is STILL over budget — DISCLOSE, never ship a
    # silently oversized prompt. Fail loud via a WARNING + a returned ``oversized`` flag the caller
    # surfaces. We do NOT drop rows to force the number down (§-1.3: consolidate-keep-all holds; the
    # 100%-of-pool invariant below still applies) — the honest signal is "this pool is pathological".
    oversized = total > max_chars
    if oversized:
        logger.warning(
            "outline_digest: menu STILL over budget after full terse+elide degradation "
            "(total_chars=%d > max_chars=%d, baskets=%d singletons=%d) — shipping an OVERSIZED "
            "prompt; the pool is pathological. Raise PG_OUTLINE_DIGEST_MAX_CHARS or investigate.",
            total, max_chars, len(basket_lines), len(singleton_lines),
        )

    menu = OutlineDigestMenu(
        basket_lines=basket_lines,
        singleton_lines=singleton_lines,
        ev_id_to_basket=ev_id_to_basket,
        total_chars=total,
        degraded=degraded,
        oversized=oversized,
        basket_member_ev_ids=basket_member_ev_ids,
        singleton_alias_ev_ids=singleton_alias_ev_ids,
        basket_work_corroboration=basket_work_corroboration,
        basket_chrome=basket_chrome,
    )

    # ── 4. 100%-of-pool honesty invariant (Design 5 §9 bar #2): every non-empty ev_id in the
    #        pool is a basket member OR a singleton line OR a folded same-work alias. Fail loud
    #        if a row went missing (PUSH A: folded aliases are covered via covered_ev_ids()).
    pool_ev_ids = {str(r.get("evidence_id", "") or "") for r in evidence}
    pool_ev_ids.discard("")
    missing = pool_ev_ids - menu.covered_ev_ids()
    if missing:
        raise ValueError(
            f"outline digest menu dropped {len(missing)} pool row(s) {sorted(missing)[:5]} — "
            "the menu must account for 100% of the pool (§-1.3 CONSOLIDATE-keep-all)."
        )
    return menu


def dedup_plan_ev_ids_by_work(
    ev_ids: Sequence[str],
    alias_of: Mapping[str, str],
) -> tuple[list[str], dict[str, list[str]]]:
    """Fold a section plan's anchor ev_ids to ONE per underlying WORK (item 14 / PUSH A).

    A section that anchors twice on the SAME work (two rows sharing a ``same_work_id``) is not
    twice-corroborated — it is the same source counted twice, which is what dragged the lab's
    per-section distinct-work fraction below the 0.90 PUSH-A bar. This keeps the FIRST ev_id seen
    per work (deterministic: input order = canonical) and returns the folded same-work aliases per
    canonical so the cp4 audit DISCLOSES them (§-1.3: consolidate — folded + disclosed, never a
    silent drop; the folded aliases stay in the pool, bibliography, and corroboration counts).
    ``alias_of`` maps ev_id -> work_key (a missing ev_id is its own work). Empty ``alias_of`` =>
    byte-identical passthrough (canonical == the deduped-preserving-order input, no folds)."""
    canonical: list[str] = []
    folded: dict[str, list[str]] = {}
    work_to_canon: dict[str, str] = {}
    for raw in ev_ids:
        e = str(raw)
        work_key = alias_of.get(e, e)
        if work_key in work_to_canon:
            canon = work_to_canon[work_key]
            if e != canon:
                folded.setdefault(canon, []).append(e)
        else:
            work_to_canon[work_key] = e
            canonical.append(e)
    return canonical, folded


# ─────────────────────────────────────────────────────────────────────────
# ORCH-2 — requirements block (Design 5 ORCH-2). Rendered from the deliverable spec +
# explicit scope constraints; appended to the outline USER prompt by the caller.
# ─────────────────────────────────────────────────────────────────────────
def _spec_get(spec: Any, key: str, default: Any) -> Any:
    """Read ``key`` off a dict OR an object (Design 3 DeliverableSpec attr surface)."""
    if spec is None:
        return default
    if isinstance(spec, Mapping):
        return spec.get(key, default)
    return getattr(spec, key, default)


def build_requirements_block(
    deliverable: Any = None,
    scope: Any = None,
) -> str:
    """Render the REQUIREMENTS block for the outline USER prompt (Design 5 ORCH-2).

    Empty deliverable + empty scope => "" (the caller appends nothing => byte-identical to
    today's outline prompt). A user-supplied structure WINS over facet emergence; an
    undersupplied required section is DISCLOSED (emitted with ``ev_ids: []`` +
    ``undersupplied: true``), never faked — strict_verify makes fabrication impossible
    downstream regardless.
    """
    required_sections = list(_spec_get(deliverable, "required_sections", []) or [])
    audience = str(_spec_get(deliverable, "audience", "") or "").strip()
    tone = str(_spec_get(deliverable, "tone", "") or "").strip()
    reference_style = str(_spec_get(deliverable, "reference_style", "") or "").strip()
    length_target = str(_spec_get(deliverable, "length_target", "") or "").strip()

    lines: list[str] = []
    if required_sections:
        # item 1c: render each required title QUOTED and instruct the model that the title is EXACTLY
        # the text inside the quotes — NOT the list number. The model was copying the "1. " enumerator
        # into the `title` field, which broke the exact-match required-title check and burned a whole
        # extra GLM retry every run. The quotes + the explicit "do NOT include the list number"
        # sentence remove the enumerator ambiguity at the source.
        ordered = "; ".join(f'{i + 1}. "{t}"' for i, t in enumerate(required_sections))
        lines.append(
            "The user REQUIRES this section structure, in this order: "
            f"[{ordered}]. The title is EXACTLY the text inside the quotes — do NOT include the list "
            f"number. Emit EXACTLY these {len(required_sections)} sections — no more, no "
            "fewer. Each section's `title` field MUST be a CHARACTER-FOR-CHARACTER copy of the "
            "quoted required title above: no paraphrase, no renaming, no list number, no extra "
            "sections. Map the evidence facets INTO these sections and express each section's "
            "specific angle in the `focus` field, never by altering the title. If a required section "
            "has no supporting evidence, still emit it with `ev_ids: []` and set "
            '`"undersupplied": true` — the pipeline will disclose the gap, never fake content.'
        )
    if audience:
        lines.append(
            f"Intended audience: {audience}. Use this only to choose section granularity "
            "(broad sections for an executive audience; finer splits for a specialist one)."
        )
    if tone:
        lines.append(f"Requested tone/register (planning context only): {tone}.")
    if reference_style:
        lines.append(f"Reference style requested (carried for the renderer): {reference_style}.")
    if length_target:
        lines.append(
            f"Length ask (planning context, NEVER a truncation gate): {length_target}."
        )

    # explicit scope constraints (already parsed upstream; stated one line each)
    for label, key in (
        ("Date window", "date_window"),
        ("Geography", "geography"),
        ("Source types", "source_types"),
        ("Language", "language"),
        ("Named sources/authors", "authors"),
    ):
        val = _spec_get(scope, key, None)
        if val:
            rendered = ", ".join(map(str, val)) if isinstance(val, (list, tuple, set)) else str(val)
            lines.append(
                f"Scope constraint — {label}: {rendered}. Evidence outside this is "
                "weight-demoted; prefer in-scope baskets when choosing section anchors."
            )

    if not lines:
        return ""
    return "\n\nDELIVERABLE REQUIREMENTS:\n" + "\n".join(f"- {line}" for line in lines)
