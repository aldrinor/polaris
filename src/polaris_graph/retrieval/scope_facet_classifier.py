"""I-scope-001 — per-SOURCE scope-facet classifier (deterministic, offline).

The flexible scope+timeline gate weights/masks sources by SCOPE facet (source-type /
jurisdiction) — orthogonal to the T1-T7 CREDIBILITY tier and to the DOCUMENT GENRE. This
module answers "which scope facets does THIS source belong to?" using the extensible
ontology in ``config/scope_ontology/source_types.yaml``.

It REUSES the ``document_type_classifier`` primitives (``_host`` / ``_host_in`` /
``_doi_candidate`` / ``classify_document_type`` / ``is_peer_reviewed_journal_article``) as
signal providers — the ``peer_reviewed_journal`` facet IS
``is_peer_reviewed_journal_article(classify_document_type(...)[0])`` (single source of truth,
no duplicate journal logic). The NEW facets (law/patent/gov/central-bank/clinical/analyst/
social/standards) resolve via ontology host / DOI-registrant / url-path / genre matchers.

DNA §-1.3: this LABELS a source with its scope facets and hands back a WEIGHT. It drops
NOTHING and never touches the faithfulness engine. Fail-open: an unresolved source yields an
empty facet set + ``basis="unresolved"`` => neutral weight 1.0 (never punished). Pure / no
network. All knobs config-driven (LAW VI).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional

from src.polaris_graph.retrieval.document_type_classifier import (
    _doi_candidate,
    _host,
    _host_in,
    classify_document_type,
    is_peer_reviewed_journal_article,
)

logger = logging.getLogger("polaris_graph.scope_facet_classifier")

_ONTOLOGY_ENV = "PG_SCOPE_ONTOLOGY_PATH"
_DEFAULT_ONTOLOGY_REL = "config/scope_ontology/source_types.yaml"

# Module-default lexicons + jurisdiction hints — the fallback when the YAML is absent, so the
# extractor/classifier are never blank offline. The YAML (when present) OVERRIDES these.
_DEFAULT_OP_LEXICON: dict[str, list[str]] = {
    "restrict_hard": ["exclusively", "solely", "restricted to", "restrict to",
                      "limited to", "strictly", "only"],
    "exclude_hard": ["do not use", "do not view", "do not quote", "do not cite",
                     "do not include", "do-not", "do not", "don't use", "must not",
                     "must-not", "exclude"],
    "include_weight": ["must include", "also include", "include", "incorporate", "add"],
    "prefer_weight": ["focus on", "focusing on", "prefer", "prioritize", "prioritise",
                      "emphasize", "emphasise", "primarily", "mainly", "especially",
                      "where possible", "ideally"],
    "exclude_weight": ["avoid", "de-emphasize", "de-emphasise"],
}


def _repo_root() -> Path:
    # src/polaris_graph/retrieval/scope_facet_classifier.py -> repo root is 3 parents up.
    return Path(__file__).resolve().parents[3]


def _ontology_path() -> Path:
    env = os.getenv(_ONTOLOGY_ENV, "").strip()
    if env:
        return Path(env)
    return _repo_root() / _DEFAULT_ONTOLOGY_REL


@lru_cache(maxsize=4)
def _load_ontology_cached(path_str: str, mtime: float) -> dict[str, Any]:
    """Cached YAML load keyed on (path, mtime) so an edited ontology is re-read. Fail-soft:
    a missing/broken file yields a minimal ontology carrying only the default lexicons."""
    fallback: dict[str, Any] = {
        "facets": [],
        "jurisdictions": {},
        "jurisdiction_synonym_suffixes": ["sources", "source", "studies", "research"],
        "jurisdiction_host_tlds": {},
        "op_lexicon": dict(_DEFAULT_OP_LEXICON),
        "default_out_of_scope_weight": 0.5,
    }
    try:
        import yaml  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - pyyaml is a project dep; fail-soft regardless
        logger.warning("[scope_ontology] PyYAML unavailable; using default lexicons only")
        return fallback
    p = Path(path_str)
    if not p.is_file():
        logger.warning("[scope_ontology] ontology not found at %s; default lexicons only", p)
        return fallback
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - malformed YAML must never abort a run
        logger.warning("[scope_ontology] failed to parse %s (%s); default lexicons", p, exc)
        return fallback
    if not isinstance(data, dict):
        return fallback
    data.setdefault("facets", [])
    data.setdefault("jurisdictions", {})
    data.setdefault("jurisdiction_synonym_suffixes",
                    ["sources", "source", "studies", "research"])
    data.setdefault("jurisdiction_host_tlds", {})
    _ol = data.get("op_lexicon")
    if not isinstance(_ol, dict) or not _ol:
        data["op_lexicon"] = dict(_DEFAULT_OP_LEXICON)
    data.setdefault("default_out_of_scope_weight", 0.5)
    return data


def load_scope_ontology(path: "str | Path | None" = None) -> dict[str, Any]:
    """Load (and cache) the scope facet ontology. Pure/offline; fail-soft to defaults."""
    p = Path(path) if path else _ontology_path()
    try:
        mtime = p.stat().st_mtime if p.is_file() else 0.0
    except Exception:  # noqa: BLE001
        mtime = 0.0
    return _load_ontology_cached(str(p), mtime)


def facet_default_weight(facet_id: str, ontology: dict[str, Any]) -> float:
    """The (0,1] out-of-scope demote for a source NOT in ``facet_id`` when the facet is
    'prefer'-requested at weight strictness. Per-facet override else the ontology default."""
    for f in ontology.get("facets", []):
        if isinstance(f, dict) and str(f.get("id")) == facet_id:
            try:
                w = float(f.get("default_out_of_scope_weight"))
                if 0.0 < w <= 1.0:
                    return w
            except (TypeError, ValueError):
                break
    try:
        w = float(ontology.get("default_out_of_scope_weight", 0.5))
        return w if 0.0 < w <= 1.0 else 0.5
    except (TypeError, ValueError):
        return 0.5


def _field(source: "Any", *names: str) -> "Any":
    if isinstance(source, Mapping):
        for n in names:
            if n in source and source.get(n) is not None:
                return source.get(n)
        return None
    for n in names:
        v = getattr(source, n, None)
        if v is not None:
            return v
    return None


def _source_url(source: "Any") -> str:
    return str(_field(source, "source_url", "url") or "")


def _matches_facet(
    facet: dict[str, Any], *, url: str, low_url: str, host: str, doi: str, genre_value: str
) -> Optional[str]:
    """Return a basis string iff the source matches this facet's matchers, else None."""
    matchers = facet.get("matchers") or {}
    if not isinstance(matchers, dict):
        return None
    # journal facet — single source of truth via the genre classifier.
    if matchers.get("journal"):
        # handled by the caller (needs the DocumentType, not just its value string)
        return None
    hosts = matchers.get("hosts") or []
    if host and hosts:
        try:
            if _host_in(host, frozenset(str(h).lower() for h in hosts)):
                return f"host:{host}"
        except Exception:  # noqa: BLE001
            pass
        # substring host suffix fallback (e.g. bare 'gov' TLD family)
        for h in hosts:
            hl = str(h).lower()
            if hl and (host == hl or host.endswith("." + hl) or host.endswith(hl)):
                return f"host:{hl}"
    url_patterns = matchers.get("url_patterns") or []
    for pat in url_patterns:
        if pat and str(pat).lower() in low_url:
            return f"url:{str(pat).lower()}"
    doi_prefixes = matchers.get("doi_prefixes") or []
    if doi:
        for pre in doi_prefixes:
            if pre and doi.startswith(str(pre).lower()):
                return f"doi:{str(pre).lower()}"
    want_genre = matchers.get("genre")
    if want_genre and genre_value and str(want_genre).upper() == genre_value.upper():
        return f"genre:{genre_value}"
    return None


def _jurisdiction_facets(host: str, source: "Any", ontology: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    tlds = ontology.get("jurisdiction_host_tlds") or {}
    for suffix, iso in tlds.items():
        s = str(suffix).lower()
        if host and (host.endswith(s)):
            out.add(f"jurisdiction:{iso}")
    country = _field(source, "country", "country_code", "geo")
    if country:
        c = str(country).strip().upper()
        if 2 <= len(c) <= 3:
            out.add(f"jurisdiction:{c}")
    return out


def classify_source_facets(
    source: "Any", ontology: "dict[str, Any] | None" = None
) -> tuple[set[str], str]:
    """Classify a source into its scope facet ids (deterministic, offline).

    Returns ``(facet_ids, basis)``. Empty set + ``basis='unresolved'`` on a source with no
    resolvable signal (fail-open => neutral weight). Multi-signal per facet — OpenAlex
    over-marks ~99% as "article", so genre alone is unreliable; the ontology host / DOI /
    url-path matchers carry the weight (same discipline the genre classifier uses)."""
    ont = ontology if ontology is not None else load_scope_ontology()
    url = _source_url(source)
    low_url = url.lower()
    host = _host(url)
    doi = _doi_candidate(str(_field(source, "doi") or ""), low_url)
    title = str(_field(source, "title") or "")

    # Reuse the genre classifier once (peer_reviewed_journal facet + genre matchers).
    try:
        dt, _dt_basis = classify_document_type(
            openalex_publication_type=str(_field(source, "openalex_publication_type") or ""),
            openalex_source_type=str(_field(source, "openalex_source_type") or ""),
            source_class=str(_field(source, "source_class") or ""),
            url=url,
            title=title,
            doi=str(_field(source, "doi") or ""),
        )
        genre_value = dt.value
        is_journal = is_peer_reviewed_journal_article(dt)
    except Exception:  # noqa: BLE001 - never let a classifier error abort scope
        genre_value = ""
        is_journal = False

    facets: set[str] = set()
    bases: list[str] = []
    for facet in ont.get("facets", []):
        if not isinstance(facet, dict):
            continue
        fid = str(facet.get("id") or "")
        if not fid:
            continue
        matchers = facet.get("matchers") or {}
        if isinstance(matchers, dict) and matchers.get("journal"):
            if is_journal:
                facets.add(fid)
                bases.append(f"{fid}=journal_classifier")
            continue
        basis = _matches_facet(
            facet, url=url, low_url=low_url, host=host, doi=doi, genre_value=genre_value
        )
        if basis:
            facets.add(fid)
            bases.append(f"{fid}={basis}")

    facets |= _jurisdiction_facets(host, source, ont)

    if not facets:
        return (set(), "unresolved")
    return (facets, "; ".join(bases[:8]) or "matched")


def resolve_scope_weight(
    source: "Any",
    requested_facet_id: str,
    ontology: "dict[str, Any] | None" = None,
) -> float:
    """The (0,1] scope weight for a source under a single 'prefer'/weight facet request:
    1.0 when the source IS in the requested facet, else the facet's out-of-scope demote."""
    ont = ontology if ontology is not None else load_scope_ontology()
    facets, _ = classify_source_facets(source, ont)
    if requested_facet_id in facets:
        return 1.0
    return facet_default_weight(requested_facet_id, ont)
