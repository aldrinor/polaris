"""Field-agnostic source-adapter registry — I-meta-005 Phase 2 (#986).

Maps each `EvidenceNeed` (NOT a domain) to a set of discovery adapter
callables, re-keyed off the DECLARED need. NO domain literal lives here; the
on-path takes no `if domain ==` branch (brief §0, EXIT P2-4).

Components:
- `JurisdictionScopeLoader`: loads `config/discovery/jurisdiction_scopes.yaml`
  (the versioned DATA contract that REPLACES the US-only `_POLICY_SITE_FILTERS`
  on-path). Resolves `(need, jurisdiction_codes) -> [canonical host scopes]`
  with NON-FATAL membership: a valid-shape code absent from the file logs +
  yields no scope, NEVER raises. Normalizes wildcard entries (`*.gc.ca` ->
  `gc.ca`) per build-note-2.
- `DiscoveryAdapter`: a named, need-keyed adapter — `Callable[[str, int],
  list[SearchCandidate]]` (query, limit). Scoped-need adapters bind their
  resolved `site:` scopes; non-scoped adapters wrap the existing functions.
- `SourceAdapterRegistry`: holds the BASE per-need adapter callables (the
  EXISTING `domain_backends` functions). Adapters are injectable so smoke tests
  stub them spend-free. `S2 is NOT registered` — the core baseline already runs
  S2 over the sub-queries (single source of truth, brief §2.2 iter-4 P2).

Registered (brief §2.2):
  primary_literature -> openalex_search + arxiv_search + europe_pmc_search
  code               -> github_search_repos
  company_filings    -> sec_edgar_search (+ jurisdiction issuer-filing scopes)
  regulatory/legal/statistical/standards/datasets/news_press
                     -> jurisdiction-scoped Serper site-queries via the yaml
                        (standards also includes the INTL bodies)
  news_press         -> issuer-newsroom scope + Serper (open_web)
  open_web           -> serper (the core open-web baseline adapter)
"""
from __future__ import annotations

import functools
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from src.polaris_graph.planning.research_planner import (
    EVIDENCE_NEEDS,
    is_valid_jurisdiction_shape,
)
from src.polaris_graph.retrieval.domain_backends import (
    PG_DOMAIN_MAX_HITS,
    arxiv_search,
    europe_pmc_search,
    github_search_repos,
    openalex_search,
    sec_edgar_search,
    site_scoped_serper,
)
from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
    SearchCandidate,
)

logger = logging.getLogger("polaris_graph.source_adapter_registry")

# An adapter is (query, limit) -> list[SearchCandidate]. Same shape as the
# existing domain backends, so the live seam runs them uniformly with the same
# dedupe-by-URL + per-backend cap discipline.
AdapterFn = Callable[..., list[SearchCandidate]]

# The needs whose discovery is jurisdiction-SCOPED via the yaml (brief §2.4).
# These take no specialized API; they fire `site:`-scoped Serper queries
# resolved from the planner-extracted jurisdiction(s). `company_filings` is
# scoped for NON-US issuers (US uses the dedicated SEC EDGAR adapter).
SCOPED_NEEDS: frozenset[str] = frozenset({
    "regulatory",
    "legal",
    "statistical",
    "standards",
    "datasets",
    "news_press",
    "company_filings",
})

# The cross-jurisdiction key in the data file (iso.org/iec.ch ... for
# standards). `standards` adapters always include INTL scopes (brief §2.2/2.4).
_INTL_KEY = "INTL"

_DEFAULT_SCOPES_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "discovery"
    / "jurisdiction_scopes.yaml"
)
_DEFAULT_VERSION_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "discovery" / "VERSION"
)


def _normalize_host(entry: str) -> str:
    """Normalize a scope-file host entry to a CANONICAL bare host (build-note-2).

    Strips a leading `*.` wildcard (`*.gc.ca` -> `gc.ca`), a leading `site:`
    if present, a scheme, a leading dot, and surrounding whitespace. Search
    operators handle wildcard hosts inconsistently, so we store + emit the
    canonical host and let `site:<host>` match sub-hosts.
    """
    host = (entry or "").strip()
    if host.lower().startswith("site:"):
        host = host[len("site:"):]
    host = host.split("://", 1)[-1]
    host = host.strip().lstrip(".")
    if host.startswith("*."):
        host = host[2:]
    return host.strip().lower()


def _dedupe_preserve(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


@dataclass
class JurisdictionScopeLoader:
    """Loads + resolves the versioned jurisdiction-scope DATA contract.

    Membership is NON-FATAL (brief §2.1b / P2-8): a valid-shape jurisdiction
    code absent from the data file logs + contributes no scope; it NEVER raises
    (SHAPE is the parser's fail-loud concern, already enforced upstream).
    """

    scopes_path: Path = field(default_factory=lambda: _DEFAULT_SCOPES_PATH)
    version_path: Path = field(default_factory=lambda: _DEFAULT_VERSION_PATH)
    _data: dict[str, Any] = field(default_factory=dict, init=False)
    _loaded: bool = field(default=False, init=False)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        raw = yaml.safe_load(self.scopes_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"jurisdiction_scopes.yaml root is not a mapping: {self.scopes_path}"
            )
        self._data = raw
        self._loaded = True

    @property
    def schema_version(self) -> Any:
        self._ensure_loaded()
        return self._data.get("schema_version")

    def version(self) -> str:
        """The pinned discovery-scope version (the VERSION file content)."""
        try:
            return self.version_path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def known_jurisdictions(self) -> set[str]:
        self._ensure_loaded()
        return set((self._data.get("jurisdictions") or {}).keys())

    def _intl_scopes(self, need: str) -> list[str]:
        self._ensure_loaded()
        intl = self._data.get(_INTL_KEY) or {}
        return [_normalize_host(h) for h in (intl.get(need) or [])]

    def scopes_for(self, need: str, jurisdictions: list[str]) -> list[str]:
        """Resolve the canonical `site:` host scopes for `need` across the given
        normalized jurisdiction codes. NON-FATAL membership: an unknown code
        logs + adds nothing. `standards` always folds in the INTL bodies.

        Returns a deduped, order-preserving list of bare canonical hosts.
        """
        self._ensure_loaded()
        out: list[str] = []
        juris_map = self._data.get("jurisdictions") or {}
        for code in jurisdictions or []:
            token = str(code).strip().upper()
            if not is_valid_jurisdiction_shape(token):
                # SHAPE is the parser's fail-loud concern; defensively skip here.
                continue
            entry = juris_map.get(token)
            if entry is None:
                logger.info(
                    "[source_adapter_registry] jurisdiction code %r not in "
                    "scope data file — no %s scope (non-fatal)", token, need,
                )
                continue
            hosts = entry.get(need) or []
            out.extend(_normalize_host(h) for h in hosts)
        if need == "standards":
            out.extend(self._intl_scopes("standards"))
        return _dedupe_preserve([h for h in out if h])


@dataclass
class DiscoveryAdapter:
    """A named, need-keyed discovery adapter.

    `fn(query, limit)` -> list[SearchCandidate]. `name` is the stable
    backend-id used for `backends_used` / `per_backend_counts` / api_calls
    accounting (matches the existing domain_backends ids where reused).
    `scoped=True` adapters carry resolved `site:` scopes (may be empty -> the
    adapter is omitted by the router so no empty scope query fires).
    """

    name: str
    need: str
    fn: AdapterFn
    scoped: bool = False

    def run(self, query: str, *, limit: int) -> list[SearchCandidate]:
        return self.fn(query, limit=limit)


class SourceAdapterRegistry:
    """Holds the BASE per-need adapter callables (the existing functions).

    Adapters are INJECTABLE (constructor override) so smoke tests stub every
    network call spend-free. The registry has NO domain literal — it is keyed
    only on `EvidenceNeed`. S2 is intentionally NOT registered (core baseline).
    """

    def __init__(
        self,
        *,
        scope_loader: JurisdictionScopeLoader | None = None,
        openalex_search_fn: AdapterFn = openalex_search,
        arxiv_search_fn: AdapterFn = arxiv_search,
        europe_pmc_search_fn: AdapterFn = europe_pmc_search,
        github_search_fn: AdapterFn = github_search_repos,
        sec_edgar_search_fn: AdapterFn = sec_edgar_search,
        scoped_serper_fn: Callable[..., list[SearchCandidate]] = site_scoped_serper,
    ) -> None:
        self.scope_loader = scope_loader or JurisdictionScopeLoader()
        self._openalex_search_fn = openalex_search_fn
        self._arxiv_search_fn = arxiv_search_fn
        self._europe_pmc_search_fn = europe_pmc_search_fn
        self._github_search_fn = github_search_fn
        self._sec_edgar_search_fn = sec_edgar_search_fn
        self._scoped_serper_fn = scoped_serper_fn

    # ── non-scoped, fixed-issuer-class adapters ──────────────────────────
    def _primary_literature_adapters(self) -> list[DiscoveryAdapter]:
        # OpenAlex-SEARCH + arxiv + europe_pmc. NOT S2 (core baseline).
        return [
            DiscoveryAdapter("openalex_search", "primary_literature", self._openalex_search_fn),
            DiscoveryAdapter("arxiv", "primary_literature", self._arxiv_search_fn),
            DiscoveryAdapter("europe_pmc", "primary_literature", self._europe_pmc_search_fn),
        ]

    def _code_adapters(self) -> list[DiscoveryAdapter]:
        return [DiscoveryAdapter("github", "code", self._github_search_fn)]

    def _scoped_serper_adapter(
        self, need: str, scopes: list[str], *, source: str,
    ) -> DiscoveryAdapter:
        bound = functools.partial(
            self._scoped_serper_fn, scopes=list(scopes), source=source,
        )
        return DiscoveryAdapter(source, need, bound, scoped=True)

    def adapters_for_need(
        self, need: str, *, jurisdictions: list[str],
    ) -> list[DiscoveryAdapter]:
        """Return the adapters mapped to a single `EvidenceNeed`, scoped to the
        given jurisdiction codes. NO domain literal; keyed only on the need.

        A SCOPED need with no resolved scopes for the jurisdiction(s) yields NO
        adapter (the run falls back to core open_web + scholarly, never a
        fabricated/US-default scope). `standards` always reaches INTL bodies, so
        it yields an adapter even with no jurisdiction.
        """
        if need == "primary_literature":
            return self._primary_literature_adapters()
        if need == "code":
            return self._code_adapters()
        if need == "open_web":
            # The CORE baseline already runs generic Serper over the sub-queries
            # (single source of truth — mirrors the S2 exclusion from
            # primary_literature). open_web therefore adds NO registry adapter;
            # a registry open-web adapter would either duplicate the core Serper
            # OR (as the pre-fix default policy_targeted_serper did) inject the
            # US-only _POLICY_SITE_FILTERS host literal onto the on-path — the
            # exact cross-jurisdiction frame bug Phase 2 exists to eliminate.
            return []
        if need == "company_filings":
            adapters: list[DiscoveryAdapter] = [
                DiscoveryAdapter("sec_edgar", "company_filings", self._sec_edgar_search_fn),
            ]
            # Non-US issuer-filing scopes from the data file (e.g. sedarplus.ca).
            scopes = self.scope_loader.scopes_for("company_filings", jurisdictions)
            if scopes:
                adapters.append(self._scoped_serper_adapter(
                    "company_filings", scopes, source="serper_company_filings",
                ))
            return adapters
        if need in SCOPED_NEEDS:
            scopes = self.scope_loader.scopes_for(need, jurisdictions)
            out: list[DiscoveryAdapter] = []
            if scopes:
                out.append(self._scoped_serper_adapter(
                    need, scopes, source=f"serper_{need}",
                ))
            # news_press is the issuer-newsroom (jurisdiction-scoped, data-driven)
            # ONLY. The generic open-web component is the CORE baseline Serper —
            # NOT a registry adapter (a registry open-web adapter would re-inject
            # the US _POLICY_SITE_FILTERS literal on the on-path; same root cause
            # as the open_web fix above).
            return out
        # Defensive: an unrecognized need (should never happen — validated
        # upstream) yields no adapter rather than a domain branch.
        logger.info(
            "[source_adapter_registry] no adapter mapping for need=%r", need,
        )
        return []


def build_registry(
    *, scope_loader: JurisdictionScopeLoader | None = None, **adapter_overrides: Any,
) -> SourceAdapterRegistry:
    """Convenience constructor (tests inject stub adapters via kwargs)."""
    return SourceAdapterRegistry(scope_loader=scope_loader, **adapter_overrides)
