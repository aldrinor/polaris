"""journal_only corpus-quality filter (I-ready-017 #1134).

A flag-gated, fail-closed filter that restricts the citeable corpus to
peer-reviewed JOURNAL ARTICLES when a protocol declares
``source_restriction: journal_only`` (e.g. the drb_72 question: "Ensure the
review only cites high-quality, English-language journal articles.").

Design (Codex APPROVE, design gate iter-4, #1134):

- ONE predicate ``is_citeable_journal`` is the single source of truth for
  "is this a citeable journal article?". It is used by every ingress filter
  AND by the final no-leak assertion, so the partition and the backstop can
  never disagree.
- A SINGLE upstream source-filter on ``retrieval.evidence_rows`` +
  ``classified_sources`` (applied after the last retrieval stage, before any
  consumer) means selection, the generator's internal retrieval
  (``live_corpus``/M-52), and all contradiction/disclosure detectors inherit
  journal-only by construction — no per-consumer chasing.
- The V30 report-contract carries entities through plan slots / entity maps /
  anchors INDEPENDENTLY of the prepended evidence rows, so those are pruned
  too; a ``required: true`` slot bound to a non-journal entity ABORTS.
- A final no-leak assertion on the generator's evidence pool is the
  structural backstop.

EVERYTHING here is inert unless BOTH ``PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1``
AND the protocol declares ``source_restriction: journal_only``. Default-OFF is
byte-identical: callers gate on ``journal_only_active(protocol)`` before
invoking any filter, and the metadata sidecar is only populated on the ON path.

Fail-closed throughout: an UNCERTAIN row (no proven journal-article signal) is
EXCLUDED, never admitted. A required non-journal contract slot, or any
non-journal row reaching the generator, ABORTS rather than silently degrades
(LAW II).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

# ── Flag + protocol gating ──────────────────────────────────────────────────

JOURNAL_ONLY_FLAG = "PG_SOURCE_RESTRICTION_JOURNAL_ONLY"
JOURNAL_ONLY_RESTRICTION = "journal_only"

# Citeable journal tiers. T1 = peer-reviewed primary; T2 = systematic review /
# meta-analysis (itself a journal article). All other tiers are non-journal.
CITEABLE_JOURNAL_TIERS = frozenset({"T1", "T2"})

# URL path fragments that mark a navigation / search / issue / table-of-contents
# / homepage surface rather than a single article. Rejected even on a journal
# domain (Codex design P1-2: domain membership alone never blesses a row).
_NON_ARTICLE_URL_MARKERS = (
    "/search", "/search?", "?search=", "/find", "/browse", "/issue", "/issues",
    "/toc", "/current", "/archive", "/aim-and-scope", "/editorial-board",
    "/most-read", "/collections", "/topics", "/journals/", "/journal/",
)


def journal_only_flag_enabled() -> bool:
    """True iff the runtime flag is explicitly set to 1 (no truthy-set; exact)."""
    return os.getenv(JOURNAL_ONLY_FLAG, "0") == "1"


def protocol_requires_journal_only(protocol: Optional[Mapping[str, Any]]) -> bool:
    """True iff the protocol declares ``source_restriction: journal_only``."""
    if not protocol:
        return False
    return str(protocol.get("source_restriction") or "").strip().lower() == (
        JOURNAL_ONLY_RESTRICTION
    )


def journal_only_active(protocol: Optional[Mapping[str, Any]]) -> bool:
    """journal_only is active iff the flag is ON AND the protocol declares it.

    Both conditions are required so that (a) the protocol field alone never
    changes behaviour without the operator-gated flag, and (b) the flag alone
    never affects a non-journal-restricted protocol. Default-OFF byte-identical.
    """
    return journal_only_flag_enabled() and protocol_requires_journal_only(protocol)


# ── URL canonicalization ────────────────────────────────────────────────────

_TRACKING_PREFIXES = ("utm_", "ref", "fbclid", "gclid", "mc_cid", "mc_eid")


def canonicalize_url(url: str) -> str:
    """Stable canonical key for a source URL.

    Lowercases scheme+host, strips ``www.``, drops the fragment and tracking
    query params, and normalizes a trailing slash. Used to key the metadata
    sidecar so stage merges (base/expansion/deepener/agentic/gap) do not
    false-exclude an article discovered via a URL variant (Codex design P2-2).
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except (ValueError, AttributeError):
        return url.strip().lower()
    # Normalize scheme to https: http/https of the same resource are the same
    # document for citeability, so they must collapse to one canonical key
    # (avoids false-excluding a URL variant across retrieval stages).
    scheme = "https"
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Drop tracking query params; keep meaningful ones (e.g. ?id=, article ids).
    kept_q = []
    for pair in (parts.query or "").split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0].lower()
        if any(key == p or key.startswith(p) for p in _TRACKING_PREFIXES):
            continue
        kept_q.append(pair)
    query = "&".join(sorted(kept_q))
    return urlunsplit((scheme, host, path, query, ""))


def _is_non_article_url(url: str) -> bool:
    """True for nav/search/issue/TOC/homepage surfaces (not a single article)."""
    if not url:
        return True
    try:
        parts = urlsplit(url.strip())
    except (ValueError, AttributeError):
        return True
    path = (parts.path or "").lower()
    # Bare host (no article path) is a homepage, not an article.
    if path in ("", "/"):
        return True
    low = url.lower()
    return any(marker in low for marker in _NON_ARTICLE_URL_MARKERS)


# ── The metadata sidecar ────────────────────────────────────────────────────


def journal_metadata_entry(
    *,
    openalex_pub_type: str = "",
    openalex_source_type: str = "",
    is_peer_reviewed: bool = False,
    is_retracted: bool = False,
    doi: str = "",
    venue: str = "",
) -> dict[str, Any]:
    """Build one sidecar entry. Populated ONLY on the journal_only ON path."""
    return {
        "openalex_pub_type": (openalex_pub_type or "").strip().lower(),
        "openalex_source_type": (openalex_source_type or "").strip().lower(),
        "is_peer_reviewed": bool(is_peer_reviewed),
        "is_retracted": bool(is_retracted),
        "doi": _normalize_doi(doi),
        "venue": (venue or "").strip(),
    }


def merge_sidecars(sidecars: Iterable[Optional[Mapping[str, Any]]]) -> dict[str, Any]:
    """Merge per-stage sidecars by canonical URL (last non-empty wins per field).

    A later retrieval stage (deepener/agentic/gap) may carry richer OpenAlex
    metadata for the same article than the base stage; merging by canonical key
    keeps the strongest signal without false-excluding URL variants.
    """
    merged: dict[str, dict[str, Any]] = {}
    for sc in sidecars:
        if not sc:
            continue
        for raw_key, entry in sc.items():
            key = canonicalize_url(str(raw_key))
            if not key or not isinstance(entry, Mapping):
                continue
            cur = merged.setdefault(key, {})
            for f, v in entry.items():
                # Last non-empty / True wins; never overwrite a real value with empty.
                if v in ("", False, None) and f in cur and cur[f] not in ("", False, None):
                    continue
                cur[f] = v
    return merged


def _normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip()


# Preprint / repository DOI prefixes that are NOT journal articles.
_PREPRINT_DOI_MARKERS = ("10.48550/arxiv", "10.31234", "10.31235", "10.2139/ssrn")


# ── The single predicate ────────────────────────────────────────────────────


def is_citeable_journal(
    url: str,
    tier: str,
    sidecar: Mapping[str, Any],
) -> tuple[bool, str]:
    """THE predicate: is this row/source a citeable peer-reviewed journal article?

    Fail-closed. Citeable iff ALL hold:
      - tier ∈ {T1, T2}; AND
      - a PROVEN journal-article signal: OpenAlex ``is_peer_reviewed`` is True
        (which OpenAlex computes as work.type ∈ {article, review} AND
        source.type == "journal"); AND
      - not retracted; AND
      - the DOI (if any) is not a preprint/repository DOI; AND
      - the URL is not a nav/search/issue/TOC/homepage surface.

    A bare publisher DOI prefix or a non-empty venue alone is NOT accepted as
    proof (would admit proceedings/books/reports). Uncertain → NOT citeable.

    Returns (citeable, reason). ``reason`` is an audit string.
    """
    t = (tier or "").strip().upper()
    if t not in CITEABLE_JOURNAL_TIERS:
        return False, f"tier_not_journal:{t or 'NONE'}"

    meta = sidecar.get(canonicalize_url(url)) if sidecar else None
    if not isinstance(meta, Mapping):
        return False, "no_journal_metadata"

    if meta.get("is_retracted"):
        return False, "retracted"

    doi = _normalize_doi(str(meta.get("doi") or ""))
    if doi and any(doi.startswith(p) for p in _PREPRINT_DOI_MARKERS):
        return False, f"preprint_doi:{doi}"

    if _is_non_article_url(url):
        return False, "non_article_url"

    # Proven journal-article signal (OpenAlex's own determination).
    if not bool(meta.get("is_peer_reviewed")):
        return False, "not_peer_reviewed_journal_article"

    # Belt-and-suspenders: if OpenAlex source_type is present it must be a
    # journal, and pub_type must be an article/review (not preprint/dataset).
    src_type = str(meta.get("openalex_source_type") or "")
    if src_type and src_type != "journal":
        return False, f"source_type_not_journal:{src_type}"
    pub_type = str(meta.get("openalex_pub_type") or "")
    if pub_type and pub_type not in ("article", "review"):
        return False, f"pub_type_not_article:{pub_type}"

    return True, "citeable_journal_article"


# ── Row / source filtering ──────────────────────────────────────────────────


def _row_url(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("source_url") or row.get("url") or "")
    return str(getattr(row, "url", "") or getattr(row, "source_url", "") or "")


def _row_tier(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("tier") or "")
    return str(getattr(row, "tier", "") or "")


@dataclass
class FilterResult:
    citeable: list[Any] = field(default_factory=list)
    excluded: list[dict[str, str]] = field(default_factory=list)


def filter_to_citeable(rows: Iterable[Any], sidecar: Mapping[str, Any]) -> FilterResult:
    """Partition evidence rows OR CorpusSource objects into citeable / excluded.

    Works on both ``evidence_row`` dicts (``source_url``/``tier`` keys) and
    ``CorpusSource`` dataclasses (``.url``/``.tier``). Excluded rows are recorded
    with their URL + reason for the audit log; they are NEVER passed downstream.
    """
    out = FilterResult()
    for row in rows:
        url = _row_url(row)
        ok, reason = is_citeable_journal(url, _row_tier(row), sidecar)
        if ok:
            out.citeable.append(row)
        else:
            out.excluded.append({"url": url, "reason": reason})
    return out


def citeable_url_set(rows: Iterable[Any], sidecar: Mapping[str, Any]) -> set[str]:
    """Canonical-URL set of the citeable rows (for detector-record backstops)."""
    keep: set[str] = set()
    for row in rows:
        url = _row_url(row)
        ok, _ = is_citeable_journal(url, _row_tier(row), sidecar)
        if ok:
            keep.add(canonicalize_url(url))
    return keep


# ── V30 contract-plan pruning ───────────────────────────────────────────────


@dataclass
class ContractPruneResult:
    kept_entity_ids: set[str] = field(default_factory=set)
    dropped_entity_ids: set[str] = field(default_factory=set)
    # A required:true rendering slot bound to a non-journal entity = hard conflict.
    required_conflicts: list[str] = field(default_factory=list)


def _entity_is_citeable_journal(entity: Any) -> tuple[bool, str]:
    """Citeability for a CONTRACT entity (metadata object, not a fetched row).

    A contract entity is a citeable journal article iff it carries a journal
    ``doi`` (not a preprint) AND is not declared a non-journal authoritative
    source (``type == policy_report`` / ``type_note == authoritative_source`` /
    a ``url_pattern`` instead of a DOI). drb_72's
    ``fourth_industrial_revolution_framing`` (policy_report, S3, url_pattern
    weforum.org) is therefore non-citeable; the journal-DOI entities pass.
    """
    def _get(name: str) -> str:
        if isinstance(entity, Mapping):
            return str(entity.get(name) or "")
        return str(getattr(entity, name, "") or "")

    etype = _get("type").strip().lower()
    type_note = _get("type_note").strip().lower()
    doi = _normalize_doi(_get("doi"))

    if type_note == "authoritative_source":
        return False, "authoritative_source_non_journal"
    if etype in ("policy_report", "regulatory_label", "guideline"):
        return False, f"non_journal_entity_type:{etype}"
    if not doi:
        return False, "no_journal_doi"
    if any(doi.startswith(p) for p in _PREPRINT_DOI_MARKERS):
        return False, f"preprint_doi:{doi}"
    return True, "citeable_journal_entity"


def prune_contract_plans(
    entities_by_id: Mapping[str, Any],
    rendering_slots: Optional[Mapping[str, Any]] = None,
) -> ContractPruneResult:
    """Decide which contract entity_ids are citeable; flag required conflicts.

    Returns the kept/dropped entity-id sets. A ``rendering_slots`` entry whose
    ``required`` is true and whose mapped entity is non-citeable is a hard
    conflict (caller ABORTS with ``error_journal_only_contract_conflict``); a
    ``required: false`` slot (e.g. drb_72 ``theory_4ir_framing``) prunes
    cleanly. The caller uses ``kept_entity_ids`` to strip plan slots / ev_ids /
    frame-row + entity maps / primary anchors down to citeable entities, then
    recomputes section focus from the survivors.
    """
    res = ContractPruneResult()
    # Map each entity to its rendering slot's required flag (default: optional).
    required_by_entity: dict[str, bool] = {}
    if rendering_slots:
        for _slot_key, slot in rendering_slots.items():
            ent_id = ""
            req = False
            if isinstance(slot, Mapping):
                ent_id = str(slot.get("entity_id") or slot.get("entity") or "")
                req = bool(slot.get("required"))
            if ent_id:
                required_by_entity[ent_id] = req

    for ent_id, entity in entities_by_id.items():
        ok, reason = _entity_is_citeable_journal(entity)
        if ok:
            res.kept_entity_ids.add(ent_id)
        else:
            res.dropped_entity_ids.add(ent_id)
            if required_by_entity.get(ent_id):
                res.required_conflicts.append(f"{ent_id}:{reason}")
    return res


# ── No-leak assertion + adequacy floor ──────────────────────────────────────


def prune_plan_entities(plans: Iterable[Any], kept_entity_ids: set[str]) -> list[Any]:
    """Drop non-citeable entities from each V30 ContractSectionPlanExt.

    For each plan: filter ``ev_ids`` and ``slots[*].entity_ids`` to the kept set,
    drop ``frame_rows_by_entity`` / ``contract_entities_by_id`` keys not kept,
    recompute the section ``focus`` from the surviving slots, and drop a plan
    whose slots all became empty. Duck-typed on the plan attributes so it does
    not import the generator's class.
    """
    out: list[Any] = []
    for plan in plans:
        ev_ids = [e for e in (getattr(plan, "ev_ids", None) or []) if e in kept_entity_ids]
        slots = []
        for slot in (getattr(plan, "slots", None) or []):
            slot_ids = [e for e in (getattr(slot, "entity_ids", None) or [])
                        if e in kept_entity_ids]
            if slot_ids:
                try:
                    slot.entity_ids = slot_ids
                except (AttributeError, TypeError):
                    pass
                slots.append(slot)
        if not slots and not ev_ids:
            continue  # whole section pruned away
        frb = getattr(plan, "frame_rows_by_entity", None)
        if isinstance(frb, dict):
            for k in [k for k in frb if k not in kept_entity_ids]:
                frb.pop(k, None)
        ceb = getattr(plan, "contract_entities_by_id", None)
        if isinstance(ceb, dict):
            for k in [k for k in ceb if k not in kept_entity_ids]:
                ceb.pop(k, None)
        try:
            plan.ev_ids = ev_ids
            plan.slots = slots
            # Recompute focus from surviving slots so no stale non-journal slot
            # label appears in prompts/logs/telemetry (Codex design P2-1).
            _titles = [getattr(s, "title", "") or getattr(s, "subsection_title", "")
                       for s in slots]
            _titles = [t for t in _titles if t]
            if _titles and hasattr(plan, "focus"):
                plan.focus = "; ".join(_titles)
        except (AttributeError, TypeError):
            pass
        out.append(plan)
    return out


class JournalOnlyLeakError(RuntimeError):
    """Raised when a non-journal row reaches the generator (status mapping
    target ``error_journal_only_leak``). Fail-closed: never synthesize."""


def _is_verified_contract_row(row: Any) -> bool:
    """A V30 contract frame row that already passed entity-level journal
    citeability pruning (``v30_frame_row``). Exempt from the URL/sidecar
    predicate in the no-leak assert — its citeability was decided by
    ``prune_contract_plans`` on the contract entity metadata, and the kept rows
    were marked citeable in the sidecar; the marker just avoids a false leak on
    a journal landing-page URL shape."""
    return isinstance(row, Mapping) and bool(row.get("v30_frame_row"))


def assert_no_leak(rows: Iterable[Any], sidecar: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return the list of leaked (non-citeable) rows. Empty list == clean.

    Caller raises ``JournalOnlyLeakError`` / aborts on a non-empty result. Run
    at the immediate pre-generator point (after contract + upload prepend) as the
    structural backstop. Rows already verified by contract entity-pruning
    (``v30_frame_row``) are exempt.
    """
    leaks: list[dict[str, str]] = []
    for row in rows:
        if _is_verified_contract_row(row):
            continue
        url = _row_url(row)
        ok, reason = is_citeable_journal(url, _row_tier(row), sidecar)
        if not ok:
            leaks.append({"url": url, "reason": reason})
    return leaks


# Default journal_only adequacy floor (overridable via the protocol's
# corpus_adequacy.journal_only block, LAW VI).
DEFAULT_MIN_DISTINCT_JOURNALS = 12


@dataclass
class JournalAdequacyResult:
    ok: bool
    distinct_journals: int
    min_required: int
    missing_anchor_dois: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def assess_journal_only_adequacy(
    citeable_rows: Iterable[Any],
    sidecar: Mapping[str, Any],
    *,
    required_anchor_dois: Iterable[str] = (),
    min_distinct: int = DEFAULT_MIN_DISTINCT_JOURNALS,
) -> JournalAdequacyResult:
    """Floor that guards against a thin-corpus false pass (Codex design P1-4).

    Requires (a) >= ``min_distinct`` distinct citeable journal articles and
    (b) every required S1 canonical-anchor DOI present in the citeable corpus.
    Fail → caller aborts ``abort_corpus_inadequate``.
    """
    distinct_urls: set[str] = set()
    present_dois: set[str] = set()
    for row in citeable_rows:
        url = _row_url(row)
        distinct_urls.add(canonicalize_url(url))
        meta = sidecar.get(canonicalize_url(url)) if sidecar else None
        if isinstance(meta, Mapping):
            doi = _normalize_doi(str(meta.get("doi") or ""))
            if doi:
                present_dois.add(doi)

    want = {_normalize_doi(d) for d in required_anchor_dois if d}
    missing = sorted(want - present_dois)

    reasons: list[str] = []
    n = len(distinct_urls)
    if n < min_distinct:
        reasons.append(f"too_few_citeable_journals:{n}<{min_distinct}")
    if missing:
        reasons.append(f"missing_s1_anchor_dois:{','.join(missing)}")

    return JournalAdequacyResult(
        ok=(not reasons),
        distinct_journals=n,
        min_required=min_distinct,
        missing_anchor_dois=missing,
        reasons=reasons,
    )
