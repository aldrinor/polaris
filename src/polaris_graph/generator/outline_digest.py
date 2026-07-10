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

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

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
    generator-package dependency. Tests inject an identity sanitizer directly."""
    try:
        from src.polaris_graph.generator.provenance_generator import (
            sanitize_evidence_text,
        )

        return sanitize_evidence_text
    except Exception:  # noqa: BLE001 — offline/unit context: fall back to identity, fail-open
        return _identity_sanitizer


@dataclass
class OutlineDigestMenu:
    """The consolidated-claim menu the outline planner reads instead of bare titles."""

    basket_lines: list[str]                 # one line per multi-member finding cluster
    singleton_lines: list[str]              # one line per row in no multi-member cluster
    ev_id_to_basket: dict[str, str]         # member ev_id -> basket id (full map; never elided)
    total_chars: int                        # rendered menu size (headroom accounting)
    degraded: bool = False                  # a headroom-guard terse pass fired
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


def _build_alias_map(
    same_work_groups: Sequence[Mapping[str, Any]] | None,
) -> dict[str, str]:
    """ev_id -> work_key from the cp3 ``same_work_groups`` payload (PUSH A).

    Each group carries ``member_evidence_ids`` (all corroborating rows of ONE underlying work)
    and a stable ``same_work_id`` string (``url:`` / ``doi:`` / ``title:`` key). The work_key is
    that ``same_work_id`` (falling back to ``canon:<canonical_index>`` only if the id is blank).
    ``setdefault`` keeps the first group to claim an ev_id, so the map is deterministic regardless
    of group order. Returns ``{}`` when no groups are supplied (=> every row is its own work =>
    byte-identical to the pre-PUSH-A path)."""
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
    return alias_of


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
    return f'{bid} {head} claim: "{claim}" {members}'


def _singleton_line(
    ev_id: str, tier: str, title: str, statement: str, alias_ev_ids: list[str],
    *, title_only: bool,
) -> str:
    # PUSH A: same-work copies collapsed onto this line are disclosed inline after the tier;
    # empty ``alias_ev_ids`` (the no-same_work_groups path) => no tag => byte-identical.
    tag = f" (+{len(alias_ev_ids)} same-work: {','.join(alias_ev_ids)})" if alias_ev_ids else ""
    if title and statement and not title_only:
        return f"{ev_id} [{tier}]{tag} | title: {title} | {statement}"
    if title:
        return f"{ev_id} [{tier}]{tag} | title: {title}"
    return f"{ev_id} [{tier}]{tag}: {statement}"


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
    if low.startswith("[pdf]") or low.startswith("(pdf)"):
        return True
    if s.endswith("..."):
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
    alias_of = _build_alias_map(same_work_groups)

    def _work_key(ev_id: str) -> str:
        return alias_of.get(ev_id, ev_id)

    def _clean(text: str) -> str:
        return sanitizer(text or "")[0]

    # ── 1. multi-member baskets, deterministically ordered (heaviest corroboration first,
    #        ties by representative ev_id then member set) so line order is worker-independent.
    multi = [c for c in clusters if len(getattr(c, "member_indices", []) or []) >= 2]

    def _sort_key(c: Any) -> tuple[int, str, tuple[str, ...]]:
        rep = _ev_id_at(evidence, int(getattr(c, "representative_index")))
        members = tuple(sorted(_ev_id_at(evidence, i) for i in getattr(c, "member_indices")))
        return (-int(getattr(c, "corroboration_count", 0)), rep, members)

    multi_sorted = sorted(multi, key=_sort_key)

    basket_specs: list[dict[str, Any]] = []
    ev_id_to_basket: dict[str, str] = {}
    basket_member_ev_ids: dict[str, list[str]] = {}
    basket_work_corroboration: dict[str, int] = {}
    for idx, c in enumerate(multi_sorted):
        bid = f"B{idx:02d}"
        member_ev_ids = sorted(_ev_id_at(evidence, i) for i in getattr(c, "member_indices"))
        member_ev_ids = [e for e in member_ev_ids if e]
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
        claim = _clean(chosen_claim)[:_CLAIM_MAX_CHARS]
        tiers = [str(evidence[i].get("tier", "") or "") for i in getattr(c, "member_indices")]
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
            }
        )
        basket_member_ev_ids[bid] = member_ev_ids
        basket_work_corroboration[bid] = work_corroboration
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
            singleton_alias_ev_ids[canonical].append(ev_id)
            continue
        work_to_canonical[work_key] = ev_id
        singleton_alias_ev_ids.setdefault(ev_id, [])
        singleton_specs.append(
            {
                "ev_id": ev_id,
                "tier": str(row.get("tier", "") or ""),
                "title": _clean(str(row.get("title", "") or ""))[:_TITLE_MAX_CHARS],
                "statement": _clean(str(row.get("statement", "") or ""))[:_STATEMENT_MAX_CHARS],
            }
        )
    # attach the (possibly appended-to) alias lists to each canonical spec
    for spec in singleton_specs:
        spec["alias_ev_ids"] = singleton_alias_ev_ids.get(spec["ev_id"], [])
    # drop empty alias entries so the map holds only genuine folds (keeps covered_ev_ids clean)
    singleton_alias_ev_ids = {k: v for k, v in singleton_alias_ev_ids.items() if v}

    def _render(*, title_only: bool, elide_members: bool) -> tuple[list[str], list[str], int]:
        b_lines = [
            _basket_line(
                s["bid"], s["corroboration"], s["tiers"], s["claim"], s["members"],
                elide_members=elide_members,
                work_corroboration=(s["work_corroboration"] if work_aware else None),
                row_count=(s["row_count"] if work_aware else None),
            )
            for s in basket_specs
        ]
        s_lines = [
            _singleton_line(
                s["ev_id"], s["tier"], s["title"], s["statement"], s["alias_ev_ids"],
                title_only=title_only,
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

    menu = OutlineDigestMenu(
        basket_lines=basket_lines,
        singleton_lines=singleton_lines,
        ev_id_to_basket=ev_id_to_basket,
        total_chars=total,
        degraded=degraded,
        basket_member_ev_ids=basket_member_ev_ids,
        singleton_alias_ev_ids=singleton_alias_ev_ids,
        basket_work_corroboration=basket_work_corroboration,
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
        ordered = "; ".join(f"{i + 1}. {t}" for i, t in enumerate(required_sections))
        lines.append(
            "The user REQUIRES this section structure, in this order: "
            f"[{ordered}]. Emit EXACTLY these {len(required_sections)} sections — no more, no "
            "fewer. Each section's `title` field MUST be a CHARACTER-FOR-CHARACTER copy of the "
            "required title above: no paraphrase, no renaming, no extra sections. Map the evidence "
            "facets INTO these sections and express each section's specific angle in the `focus` "
            "field, never by altering the title. If a required section has no supporting evidence, "
            'still emit it with `ev_ids: []` and set `"undersupplied": true` — the pipeline '
            "will disclose the gap, never fake content."
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
