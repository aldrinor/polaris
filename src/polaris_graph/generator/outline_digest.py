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
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

# ── knob defaults (LAW VI; exact names/defaults from Design 5 §6 + master §6). These are
# the resolver-swap seam per master §1.5: when run_config.py (WP-0b) lands, each read below
# becomes ``run_config.get(<id>)`` — same names, same defaults, byte-identical when unset.
PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT = 60000

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

    def render(self) -> str:
        """The prompt menu text — baskets first (heaviest claims), then singletons."""
        return "\n".join(self.basket_lines + self.singleton_lines)

    def covered_ev_ids(self) -> set[str]:
        """Every ev_id the menu accounts for (basket member OR singleton)."""
        covered = set(self.ev_id_to_basket)
        for line in self.singleton_lines:
            # singleton lines start with the ev_id token (see _singleton_line)
            covered.add(line.split(" ", 1)[0])
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


def _basket_line(
    bid: str,
    corroboration: int,
    tiers: list[str],
    claim: str,
    member_ev_ids: list[str],
    *,
    elide_members: bool,
) -> str:
    tier_csv = ",".join(tiers)
    members = (
        f"({len(member_ev_ids)} members)"
        if elide_members
        else "members: " + ",".join(member_ev_ids)
    )
    return f'{bid} [x{corroboration} sources: {tier_csv}] claim: "{claim}" {members}'


def _singleton_line(
    ev_id: str, tier: str, title: str, statement: str, *, title_only: bool
) -> str:
    if title and statement and not title_only:
        return f"{ev_id} [{tier}] | title: {title} | {statement}"
    if title:
        return f"{ev_id} [{tier}] | title: {title}"
    return f"{ev_id} [{tier}]: {statement}"


def build_outline_digest(
    evidence: Sequence[Mapping[str, Any]],
    clusters: Sequence[Any],
    *,
    max_chars: int | None = None,
    sanitizer: Callable[[str], tuple[str, int]] | None = None,
) -> OutlineDigestMenu:
    """Build the basket-digest menu from the evidence pool + finding clusters.

    ``clusters`` is duck-typed over ``FindingCluster`` (``representative_index``,
    ``member_indices``, ``corroboration_count``, ``member_hosts``) so this module never
    imports finding_dedup. A cluster with >= 2 members becomes a BASKET line; every other
    pool row becomes a SINGLETON line — so the menu accounts for 100% of the pool
    (invariant, asserted below; §-1.3 CONSOLIDATE-keep-all, zero rows dropped).

    Headroom guard (Design 5 ORCH-1): if the rendered menu exceeds ``max_chars`` the
    singleton statements terse away FIRST (row kept), then basket member lists elide to
    counts (the ev_id -> basket map is ALWAYS preserved) — content degrades gracefully; no
    row ever leaves the menu.
    """
    if sanitizer is None:
        sanitizer = _default_sanitizer()
    if max_chars is None:
        max_chars = _env_int("PG_OUTLINE_DIGEST_MAX_CHARS", PG_OUTLINE_DIGEST_MAX_CHARS_DEFAULT)

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
    for idx, c in enumerate(multi_sorted):
        bid = f"B{idx:02d}"
        member_ev_ids = sorted(_ev_id_at(evidence, i) for i in getattr(c, "member_indices"))
        member_ev_ids = [e for e in member_ev_ids if e]
        rep_row = evidence[int(getattr(c, "representative_index"))]
        claim = _clean(str(rep_row.get("statement", "") or rep_row.get("title", "") or ""))[
            :_CLAIM_MAX_CHARS
        ]
        tiers = [str(evidence[i].get("tier", "") or "") for i in getattr(c, "member_indices")]
        basket_specs.append(
            {
                "bid": bid,
                "corroboration": int(getattr(c, "corroboration_count", 0)),
                "tiers": tiers,
                "claim": claim,
                "members": member_ev_ids,
            }
        )
        basket_member_ev_ids[bid] = member_ev_ids
        for e in member_ev_ids:
            # keep-first on a rare cross-basket collision (deterministic ordering fixes it)
            ev_id_to_basket.setdefault(e, bid)

    # ── 2. singletons = every pool row not claimed by a multi-member basket.
    singleton_specs: list[dict[str, Any]] = []
    for row in evidence:
        ev_id = str(row.get("evidence_id", "") or "")
        if not ev_id or ev_id in ev_id_to_basket:
            continue
        singleton_specs.append(
            {
                "ev_id": ev_id,
                "tier": str(row.get("tier", "") or ""),
                "title": _clean(str(row.get("title", "") or ""))[:_TITLE_MAX_CHARS],
                "statement": _clean(str(row.get("statement", "") or ""))[:_STATEMENT_MAX_CHARS],
            }
        )

    def _render(*, title_only: bool, elide_members: bool) -> tuple[list[str], list[str], int]:
        b_lines = [
            _basket_line(
                s["bid"], s["corroboration"], s["tiers"], s["claim"], s["members"],
                elide_members=elide_members,
            )
            for s in basket_specs
        ]
        s_lines = [
            _singleton_line(
                s["ev_id"], s["tier"], s["title"], s["statement"], title_only=title_only
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
    )

    # ── 4. 100%-of-pool honesty invariant (Design 5 §9 bar #2): every non-empty ev_id in the
    #        pool is a basket member OR a singleton line. Fail loud if a row went missing.
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
            f"[{ordered}]. Map the evidence facets INTO these sections. Do not invent "
            "sections outside this list. If a required section has no supporting evidence, "
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
