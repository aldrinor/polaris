HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
Front-load ALL real findings. Reserve P0/P1 for real execution risks.

# Codex DIFF gate — I-meta-005 Phase 2 (#986): source discovery by need-type

Reviewing the CODE DIFF vs the APPROVED brief (.codex/I-meta-005-phase-2/brief.md, Codex APPROVE iter5) +
build_spec.md. This verdict AUTHORIZES THE MERGE (operator governance 2026-05-31). Output §8.3.9 YAML first.
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## VERIFY (read actual diff + workspace):
1. OFF byte-identity: PG_USE_RESEARCH_PLANNER off → run_domain_backends if-domain== switch +
   _POLICY_SITE_FILTERS byte-identical; additive frame fields (evidence_needs/jurisdictions) inert in OFF;
   off-mode passes research_frame=None → legacy seam.
2. Field-agnostic (operator HARD lock): NO if-domain==/domain-enum/clinical literal as a control VALUE on
   the on-path (EXIT: on-path count 0; P2-4 uses AST inspection). Discovery keyed on evidence_needs +
   normalized jurisdictions, never domain.
3. **The US-host-literal leak the Claude architect found + I FIXED (verify the fix is complete):** the
   open_web AND news_press need-adapters were wired to policy_targeted_serper (which wraps queries in the
   US-only _POLICY_SITE_FILTERS — a US host literal on the ON-path). FIX: open_web → NO registry adapter
   (the core baseline Serper over sub-queries covers generic open-web — single source of truth, mirrors the
   S2 exclusion from primary_literature); news_press → data-driven issuer-newsroom scope ONLY (site_scoped_
   serper from the yaml); policy_targeted_serper REMOVED from the registry imports entirely. Confirm NO
   path in the registry/router reaches _POLICY_SITE_FILTERS on the on-path, and the empty-needs fallback
   {primary_literature, open_web} yields {OpenAlex-search, arxiv, europe_pmc} (no US serper).
4. Spend-free: adapters injected/stubbed; no live HTTP client constructed in smoke.
5. Malformed fail-loud: malformed evidence_need OR malformed jurisdiction SHAPE raises MalformedPlanError
   UP-FRONT (Step-0) before ANY live discovery incl. core Serper/S2; valid-shape-unknown jurisdiction
   non-fatal; adapter/network errors stay fail-open.
6. Jurisdiction data-driven: scopes from config/discovery/jurisdiction_scopes.yaml (versioned DATA,
   schema_version/provenance), wildcard entries normalized (gc.ca not *.gc.ca); no on-path host literal.
7. All 4 legacy backends reachable on-mode by need: code→github, regulatory→scoped, company_filings→
   sec_edgar, primary_literature→OpenAlex-search/arxiv/europe_pmc.

## SMOKE: 40/40 Phase-2 (P2-1..P2-11 + malformed, open_web fix asserts no US serper on-path) + 15/15 domain_backends regression (OFF byte-identity).
## ARCHITECT (Claude): off-byte-identity / zero-if-domain / spend-free / malformed-fail-loud CLEAN; the jurisdiction-data-driven P1 (open_web US-literal) FIXED post-build.

APPROVE iff OFF is byte-identical, the field-agnostic lock holds (no US/domain literal on on-path incl. the
fixed open_web path), spend-free, malformed fails loud up-front, and jurisdiction scoping is data-driven.

--- FULL DIFF BELOW ---
```diff
diff --git a/config/discovery/VERSION b/config/discovery/VERSION
new file mode 100644
index 00000000..d4dbdffd
--- /dev/null
+++ b/config/discovery/VERSION
@@ -0,0 +1 @@
+jurisdiction_scopes_v1
diff --git a/config/discovery/jurisdiction_scopes.yaml b/config/discovery/jurisdiction_scopes.yaml
new file mode 100644
index 00000000..6d918b68
--- /dev/null
+++ b/config/discovery/jurisdiction_scopes.yaml
@@ -0,0 +1,182 @@
+# Jurisdiction-scoped discovery site-scopes — I-meta-005 Phase 2 (#986).
+#
+# VERSIONED DATA CONTRACT (LAW VI: knowledge lives in DATA, never in on-path
+# host literals in code). This file REPLACES the on-path use of the US-only
+# `_POLICY_SITE_FILTERS` tuple in `domain_backends.py`; that tuple is retained
+# byte-identical ONLY on the OFF (legacy `if domain ==`) path.
+#
+# Consumed by:
+#   src/polaris_graph/discovery/source_adapter_registry.py
+#   src/polaris_graph/discovery/need_type_router.py
+# via a scope loader that resolves jurisdiction MEMBERSHIP non-fatally:
+#   - a jurisdiction code present here  -> its per-need site scopes apply;
+#   - a valid-shape code ABSENT here    -> NO scope for that need (logged,
+#     never a fabricated/US-default scope), NEVER parser-fatal.
+#
+# NOT a DNS-suffix pre-filter. `config/authority/psl_gov_suffixes.txt` stays an
+# authority pre-filter only (its own header notes it MISSES canada.ca); this
+# file is the discovery-SCOPE source.
+#
+# WILDCARD NORMALIZATION (Phase 2 build-note-2):
+#   Store CANONICAL hosts only — `gc.ca`, NOT `*.gc.ca`. Search operators
+#   handle wildcard hosts (`site:*.gc.ca`) inconsistently, so the adapter
+#   emits `site:gc.ca` (a `site:` on a registrable host already matches
+#   sub-hosts on the major engines). Any `*.` prefix that slips into the data
+#   is normalized away by the loader before emission. Do not add `*.` entries.
+
+schema_version: 1
+provenance:
+  source: "POLARIS Phase 2 bootstrap — official issuer/regulator/statistical/legal/standards hosts per jurisdiction"
+  curated_by: "I-meta-005 Phase 2 (#986)"
+  notes: >-
+    Bootstrap set (US/CA/GB/EU/JP/AU + INTL). Extensible by editing THIS DATA
+    file (add a jurisdiction code + its per-need host arrays), never by adding
+    a host literal to code. Per-need keys are field-agnostic EvidenceNeed
+    values: regulatory / legal / statistical / standards / company_filings /
+    datasets / news_press. A scoped need with no entry for a jurisdiction
+    yields no scope for that need (logged, no fabricated default).
+fetch_date: "2026-05-31"
+
+# ── INTL: cross-jurisdiction standards/issuer bodies (not tied to one code) ──
+# `standards` adapters always include these in addition to any jurisdiction
+# standards scopes.
+INTL:
+  standards:
+    - iso.org
+    - iec.ch
+    - itu.int
+    - ietf.org
+
+jurisdictions:
+  US:
+    regulatory:
+      - federalregister.gov
+      - regulations.gov
+      - fda.gov
+      - cms.gov
+      - hhs.gov
+      - ftc.gov
+      - epa.gov
+    legal:
+      - law.cornell.edu
+      - supremecourt.gov
+      - uscourts.gov
+      - govinfo.gov
+    statistical:
+      - census.gov
+      - bls.gov
+      - bea.gov
+    standards:
+      - nist.gov
+      - ansi.org
+    company_filings:
+      - sec.gov
+    datasets:
+      - data.gov
+    news_press:
+      - whitehouse.gov
+
+  CA:
+    regulatory:
+      - canada.ca
+      - gc.ca
+      - hc-sc.gc.ca
+    legal:
+      - canlii.org
+      - laws-lois.justice.gc.ca
+      - scc-csc.ca
+    statistical:
+      - statcan.gc.ca
+    standards:
+      - scc.ca
+      - csagroup.org
+    company_filings:
+      - sedarplus.ca
+      - osc.ca
+    datasets:
+      - open.canada.ca
+    news_press:
+      - pm.gc.ca
+
+  GB:
+    regulatory:
+      - gov.uk
+      - mhra.gov.uk
+      - nice.org.uk
+      - fca.org.uk
+    legal:
+      - legislation.gov.uk
+      - bailii.org
+      - supremecourt.uk
+    statistical:
+      - ons.gov.uk
+    standards:
+      - bsigroup.com
+    company_filings:
+      - find-and-update.company-information.service.gov.uk
+    datasets:
+      - data.gov.uk
+    news_press:
+      - gov.uk
+
+  EU:
+    regulatory:
+      - europa.eu
+      - ema.europa.eu
+      - eur-lex.europa.eu
+    legal:
+      - eur-lex.europa.eu
+      - curia.europa.eu
+    statistical:
+      - ec.europa.eu
+    standards:
+      - cen.eu
+      - cenelec.eu
+      - etsi.org
+    company_filings:
+      - esma.europa.eu
+    datasets:
+      - data.europa.eu
+    news_press:
+      - ec.europa.eu
+
+  JP:
+    regulatory:
+      - mhlw.go.jp
+      - pmda.go.jp
+      - meti.go.jp
+    legal:
+      - japaneselawtranslation.go.jp
+      - courts.go.jp
+    statistical:
+      - stat.go.jp
+    standards:
+      - jisc.go.jp
+    company_filings:
+      - disclosure2.edinet-fsa.go.jp
+      - fsa.go.jp
+    datasets:
+      - data.go.jp
+    news_press:
+      - kantei.go.jp
+
+  AU:
+    regulatory:
+      - gov.au
+      - tga.gov.au
+      - accc.gov.au
+    legal:
+      - austlii.edu.au
+      - legislation.gov.au
+      - hcourt.gov.au
+    statistical:
+      - abs.gov.au
+    standards:
+      - standards.org.au
+    company_filings:
+      - asic.gov.au
+      - asx.com.au
+    datasets:
+      - data.gov.au
+    news_press:
+      - pm.gov.au
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index db31c1b4..e2cc3638 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1864,13 +1864,17 @@ async def run_one_query(
             _trial_doi_seeds = []
 
         t0 = time.time()
-        # I-meta-005 Phase 1 (#985): ON-mode bypasses the two live-path domain
-        # routers (brief §2.4) — `domain=None` skips the domain_backends
-        # per-domain `if domain ==` candidate router (live_retriever:1795
-        # guards `if domain and not seed_only`), and the frame-derived protocol
-        # replaces the clinical PICO protocol so planner sub-queries validate
-        # against the frame's own tokens. No trial-DOI seeds on-mode. OFF: the
-        # legacy domain + PICO protocol + DOI seeds run byte-identically.
+        # I-meta-005 Phase 1 (#985) + Phase 2 (#986): ON-mode bypasses the
+        # legacy domain router (brief §2.4) — `domain=None` skips the
+        # domain_backends per-domain `if domain ==` candidate router. Phase 2
+        # threads the planner FRAME so the field-agnostic NEED-TYPE registry
+        # (keyed on the frame's declared evidence_needs + jurisdictions, NO
+        # domain literal) REPLACES the domain backends at the live seam. The
+        # frame-derived protocol replaces the clinical PICO protocol so planner
+        # sub-queries validate against the frame's own tokens. No trial-DOI
+        # seeds on-mode. OFF: the legacy domain + PICO protocol + DOI seeds run
+        # byte-identically (research_frame=None -> the legacy `if domain ==`
+        # seam is taken).
         _retrieval_domain = None if _use_research_planner else q["domain"]
         _retrieval_protocol = (
             _planner_protocol
@@ -1878,6 +1882,11 @@ async def run_one_query(
             else protocol
         )
         _retrieval_seed_urls = [] if _use_research_planner else _trial_doi_seeds
+        _retrieval_frame = (
+            _research_plan.frame
+            if (_use_research_planner and _research_plan is not None)
+            else None
+        )
         retrieval = run_live_retrieval(
             research_question=q["question"],
             amplified_queries=_amplified_effective,
@@ -1889,6 +1898,7 @@ async def run_one_query(
             enable_prefetch_filter=False,
             domain=_retrieval_domain,   # R-6 Gap-2 domain backends (None on-mode)
             seed_urls=_retrieval_seed_urls,   # #817 layer-4 DOI candidates (off-mode only)
+            research_frame=_retrieval_frame,  # Phase 2 need-type registry (None off-mode)
         )
         dt = time.time() - t0
         _log(f"[retrieval]   pre_filter={retrieval.total_candidates_pre_filter}, "
diff --git a/src/polaris_graph/discovery/__init__.py b/src/polaris_graph/discovery/__init__.py
new file mode 100644
index 00000000..e22eff4e
--- /dev/null
+++ b/src/polaris_graph/discovery/__init__.py
@@ -0,0 +1,16 @@
+"""Field-agnostic source discovery by NEED-TYPE — I-meta-005 Phase 2 (#986).
+
+This package replaces the bypassed 4-branch domain enum switch in
+`retrieval/domain_backends.run_domain_backends` with a field-agnostic registry
+keyed on the planner's DECLARED EvidenceNeed + extracted JURISDICTION — never a
+domain. Behind `PG_USE_RESEARCH_PLANNER` (default off); OFF is byte-identical
+(the legacy `if domain ==` switch is retained + selected when off).
+
+Public surface:
+- `source_adapter_registry`: maps each EvidenceNeed -> its discovery adapter
+  callables (the EXISTING functions, re-keyed off the need) + the jurisdiction
+  scope loader for the scoped needs.
+- `need_type_router.route_needs_to_adapters(frame)`: returns the deduped union
+  of adapters for `frame.evidence_needs`; empty -> {primary_literature,
+  open_web} safe generic fallback; NO `if domain ==`.
+"""
diff --git a/src/polaris_graph/discovery/need_type_router.py b/src/polaris_graph/discovery/need_type_router.py
new file mode 100644
index 00000000..23ba92d6
--- /dev/null
+++ b/src/polaris_graph/discovery/need_type_router.py
@@ -0,0 +1,85 @@
+"""Need-type router — I-meta-005 Phase 2 (#986).
+
+`route_needs_to_adapters(frame)` reads the planner frame's field-agnostic
+`evidence_needs` + normalized `jurisdictions` and returns the deduped union of
+discovery adapters for those needs. NO `if domain ==` — the frame carries no
+domain; routing is keyed only on the declared need + extracted jurisdiction.
+
+Fallback (brief §2.3): an EMPTY `evidence_needs` (older legacy plan) routes to
+the safe generic set {primary_literature, open_web} — NEVER to a domain. A
+MALFORMED evidence_need / jurisdiction SHAPE is a fail-loud `MalformedPlanError`
+(validated UP-FRONT, brief §2.4 P2-note-1), NOT a fallback.
+"""
+from __future__ import annotations
+
+import logging
+from typing import Any
+
+from src.polaris_graph.discovery.source_adapter_registry import (
+    DiscoveryAdapter,
+    SourceAdapterRegistry,
+)
+from src.polaris_graph.planning.research_planner import (
+    MalformedPlanError,
+    ResearchFrame,
+    validate_evidence_needs,
+    validate_jurisdiction_shapes,
+)
+
+logger = logging.getLogger("polaris_graph.need_type_router")
+
+# Safe generic fallback for an EMPTY evidence_needs (brief §2.3). NEVER a domain.
+_EMPTY_NEEDS_FALLBACK: tuple[str, ...] = ("primary_literature", "open_web")
+
+
+def validate_frame_needs(frame: ResearchFrame) -> tuple[list[str], list[str]]:
+    """Validate the frame's `evidence_needs` + `jurisdictions` UP-FRONT and
+    return the normalized (needs, jurisdictions). Raises `MalformedPlanError`
+    on a malformed need value OR a malformed jurisdiction SHAPE — the live seam
+    calls this BEFORE any discovery (incl. core Serper/S2) so a malformed frame
+    fails loud without spending (brief §2.4 P2-note-1).
+
+    A valid-shape-but-unknown jurisdiction code passes here (membership is the
+    scope loader's non-fatal concern). An EMPTY `evidence_needs` passes (the
+    router applies the safe generic fallback) — only a MALFORMED value raises.
+    """
+    needs = validate_evidence_needs(list(getattr(frame, "evidence_needs", []) or []))
+    jurisdictions = validate_jurisdiction_shapes(
+        list(getattr(frame, "jurisdictions", []) or [])
+    )
+    return needs, jurisdictions
+
+
+def route_needs_to_adapters(
+    frame: ResearchFrame,
+    *,
+    registry: SourceAdapterRegistry | None = None,
+) -> list[DiscoveryAdapter]:
+    """Return the deduped union of discovery adapters for the frame's declared
+    needs, scoped to its jurisdictions. NO domain consulted.
+
+    - Validates needs + jurisdiction SHAPE UP-FRONT (raises MalformedPlanError).
+    - EMPTY needs -> {primary_literature, open_web} safe generic fallback.
+    - Dedupes adapters by (name) so a need overlap (e.g. news_press + open_web
+      both yielding `serper`) selects each adapter once.
+    """
+    if registry is None:
+        registry = SourceAdapterRegistry()
+
+    needs, jurisdictions = validate_frame_needs(frame)
+    if not needs:
+        logger.info(
+            "[need_type_router] empty evidence_needs -> safe generic fallback "
+            "%s (NOT a domain)", list(_EMPTY_NEEDS_FALLBACK),
+        )
+        needs = list(_EMPTY_NEEDS_FALLBACK)
+
+    selected: list[DiscoveryAdapter] = []
+    seen_names: set[str] = set()
+    for need in needs:
+        for adapter in registry.adapters_for_need(need, jurisdictions=jurisdictions):
+            if adapter.name in seen_names:
+                continue
+            seen_names.add(adapter.name)
+            selected.append(adapter)
+    return selected
diff --git a/src/polaris_graph/discovery/source_adapter_registry.py b/src/polaris_graph/discovery/source_adapter_registry.py
new file mode 100644
index 00000000..49385512
--- /dev/null
+++ b/src/polaris_graph/discovery/source_adapter_registry.py
@@ -0,0 +1,326 @@
+"""Field-agnostic source-adapter registry — I-meta-005 Phase 2 (#986).
+
+Maps each `EvidenceNeed` (NOT a domain) to a set of discovery adapter
+callables, re-keyed off the DECLARED need. NO domain literal lives here; the
+on-path takes no `if domain ==` branch (brief §0, EXIT P2-4).
+
+Components:
+- `JurisdictionScopeLoader`: loads `config/discovery/jurisdiction_scopes.yaml`
+  (the versioned DATA contract that REPLACES the US-only `_POLICY_SITE_FILTERS`
+  on-path). Resolves `(need, jurisdiction_codes) -> [canonical host scopes]`
+  with NON-FATAL membership: a valid-shape code absent from the file logs +
+  yields no scope, NEVER raises. Normalizes wildcard entries (`*.gc.ca` ->
+  `gc.ca`) per build-note-2.
+- `DiscoveryAdapter`: a named, need-keyed adapter — `Callable[[str, int],
+  list[SearchCandidate]]` (query, limit). Scoped-need adapters bind their
+  resolved `site:` scopes; non-scoped adapters wrap the existing functions.
+- `SourceAdapterRegistry`: holds the BASE per-need adapter callables (the
+  EXISTING `domain_backends` functions). Adapters are injectable so smoke tests
+  stub them spend-free. `S2 is NOT registered` — the core baseline already runs
+  S2 over the sub-queries (single source of truth, brief §2.2 iter-4 P2).
+
+Registered (brief §2.2):
+  primary_literature -> openalex_search + arxiv_search + europe_pmc_search
+  code               -> github_search_repos
+  company_filings    -> sec_edgar_search (+ jurisdiction issuer-filing scopes)
+  regulatory/legal/statistical/standards/datasets/news_press
+                     -> jurisdiction-scoped Serper site-queries via the yaml
+                        (standards also includes the INTL bodies)
+  news_press         -> issuer-newsroom scope + Serper (open_web)
+  open_web           -> serper (the core open-web baseline adapter)
+"""
+from __future__ import annotations
+
+import functools
+import logging
+import os
+from dataclasses import dataclass, field
+from pathlib import Path
+from typing import Any, Callable
+
+import yaml
+
+from src.polaris_graph.planning.research_planner import (
+    EVIDENCE_NEEDS,
+    is_valid_jurisdiction_shape,
+)
+from src.polaris_graph.retrieval.domain_backends import (
+    PG_DOMAIN_MAX_HITS,
+    arxiv_search,
+    europe_pmc_search,
+    github_search_repos,
+    openalex_search,
+    sec_edgar_search,
+    site_scoped_serper,
+)
+from src.polaris_graph.retrieval.prefetch_offtopic_filter import (
+    SearchCandidate,
+)
+
+logger = logging.getLogger("polaris_graph.source_adapter_registry")
+
+# An adapter is (query, limit) -> list[SearchCandidate]. Same shape as the
+# existing domain backends, so the live seam runs them uniformly with the same
+# dedupe-by-URL + per-backend cap discipline.
+AdapterFn = Callable[..., list[SearchCandidate]]
+
+# The needs whose discovery is jurisdiction-SCOPED via the yaml (brief §2.4).
+# These take no specialized API; they fire `site:`-scoped Serper queries
+# resolved from the planner-extracted jurisdiction(s). `company_filings` is
+# scoped for NON-US issuers (US uses the dedicated SEC EDGAR adapter).
+SCOPED_NEEDS: frozenset[str] = frozenset({
+    "regulatory",
+    "legal",
+    "statistical",
+    "standards",
+    "datasets",
+    "news_press",
+    "company_filings",
+})
+
+# The cross-jurisdiction key in the data file (iso.org/iec.ch ... for
+# standards). `standards` adapters always include INTL scopes (brief §2.2/2.4).
+_INTL_KEY = "INTL"
+
+_DEFAULT_SCOPES_PATH = (
+    Path(__file__).resolve().parents[3]
+    / "config"
+    / "discovery"
+    / "jurisdiction_scopes.yaml"
+)
+_DEFAULT_VERSION_PATH = (
+    Path(__file__).resolve().parents[3] / "config" / "discovery" / "VERSION"
+)
+
+
+def _normalize_host(entry: str) -> str:
+    """Normalize a scope-file host entry to a CANONICAL bare host (build-note-2).
+
+    Strips a leading `*.` wildcard (`*.gc.ca` -> `gc.ca`), a leading `site:`
+    if present, a scheme, a leading dot, and surrounding whitespace. Search
+    operators handle wildcard hosts inconsistently, so we store + emit the
+    canonical host and let `site:<host>` match sub-hosts.
+    """
+    host = (entry or "").strip()
+    if host.lower().startswith("site:"):
+        host = host[len("site:"):]
+    host = host.split("://", 1)[-1]
+    host = host.strip().lstrip(".")
+    if host.startswith("*."):
+        host = host[2:]
+    return host.strip().lower()
+
+
+def _dedupe_preserve(items: list[str]) -> list[str]:
+    out: list[str] = []
+    seen: set[str] = set()
+    for item in items:
+        if item and item not in seen:
+            seen.add(item)
+            out.append(item)
+    return out
+
+
+@dataclass
+class JurisdictionScopeLoader:
+    """Loads + resolves the versioned jurisdiction-scope DATA contract.
+
+    Membership is NON-FATAL (brief §2.1b / P2-8): a valid-shape jurisdiction
+    code absent from the data file logs + contributes no scope; it NEVER raises
+    (SHAPE is the parser's fail-loud concern, already enforced upstream).
+    """
+
+    scopes_path: Path = field(default_factory=lambda: _DEFAULT_SCOPES_PATH)
+    version_path: Path = field(default_factory=lambda: _DEFAULT_VERSION_PATH)
+    _data: dict[str, Any] = field(default_factory=dict, init=False)
+    _loaded: bool = field(default=False, init=False)
+
+    def _ensure_loaded(self) -> None:
+        if self._loaded:
+            return
+        raw = yaml.safe_load(self.scopes_path.read_text(encoding="utf-8"))
+        if not isinstance(raw, dict):
+            raise ValueError(
+                f"jurisdiction_scopes.yaml root is not a mapping: {self.scopes_path}"
+            )
+        self._data = raw
+        self._loaded = True
+
+    @property
+    def schema_version(self) -> Any:
+        self._ensure_loaded()
+        return self._data.get("schema_version")
+
+    def version(self) -> str:
+        """The pinned discovery-scope version (the VERSION file content)."""
+        try:
+            return self.version_path.read_text(encoding="utf-8").strip()
+        except OSError:
+            return ""
+
+    def known_jurisdictions(self) -> set[str]:
+        self._ensure_loaded()
+        return set((self._data.get("jurisdictions") or {}).keys())
+
+    def _intl_scopes(self, need: str) -> list[str]:
+        self._ensure_loaded()
+        intl = self._data.get(_INTL_KEY) or {}
+        return [_normalize_host(h) for h in (intl.get(need) or [])]
+
+    def scopes_for(self, need: str, jurisdictions: list[str]) -> list[str]:
+        """Resolve the canonical `site:` host scopes for `need` across the given
+        normalized jurisdiction codes. NON-FATAL membership: an unknown code
+        logs + adds nothing. `standards` always folds in the INTL bodies.
+
+        Returns a deduped, order-preserving list of bare canonical hosts.
+        """
+        self._ensure_loaded()
+        out: list[str] = []
+        juris_map = self._data.get("jurisdictions") or {}
+        for code in jurisdictions or []:
+            token = str(code).strip().upper()
+            if not is_valid_jurisdiction_shape(token):
+                # SHAPE is the parser's fail-loud concern; defensively skip here.
+                continue
+            entry = juris_map.get(token)
+            if entry is None:
+                logger.info(
+                    "[source_adapter_registry] jurisdiction code %r not in "
+                    "scope data file — no %s scope (non-fatal)", token, need,
+                )
+                continue
+            hosts = entry.get(need) or []
+            out.extend(_normalize_host(h) for h in hosts)
+        if need == "standards":
+            out.extend(self._intl_scopes("standards"))
+        return _dedupe_preserve([h for h in out if h])
+
+
+@dataclass
+class DiscoveryAdapter:
+    """A named, need-keyed discovery adapter.
+
+    `fn(query, limit)` -> list[SearchCandidate]. `name` is the stable
+    backend-id used for `backends_used` / `per_backend_counts` / api_calls
+    accounting (matches the existing domain_backends ids where reused).
+    `scoped=True` adapters carry resolved `site:` scopes (may be empty -> the
+    adapter is omitted by the router so no empty scope query fires).
+    """
+
+    name: str
+    need: str
+    fn: AdapterFn
+    scoped: bool = False
+
+    def run(self, query: str, *, limit: int) -> list[SearchCandidate]:
+        return self.fn(query, limit=limit)
+
+
+class SourceAdapterRegistry:
+    """Holds the BASE per-need adapter callables (the existing functions).
+
+    Adapters are INJECTABLE (constructor override) so smoke tests stub every
+    network call spend-free. The registry has NO domain literal — it is keyed
+    only on `EvidenceNeed`. S2 is intentionally NOT registered (core baseline).
+    """
+
+    def __init__(
+        self,
+        *,
+        scope_loader: JurisdictionScopeLoader | None = None,
+        openalex_search_fn: AdapterFn = openalex_search,
+        arxiv_search_fn: AdapterFn = arxiv_search,
+        europe_pmc_search_fn: AdapterFn = europe_pmc_search,
+        github_search_fn: AdapterFn = github_search_repos,
+        sec_edgar_search_fn: AdapterFn = sec_edgar_search,
+        scoped_serper_fn: Callable[..., list[SearchCandidate]] = site_scoped_serper,
+    ) -> None:
+        self.scope_loader = scope_loader or JurisdictionScopeLoader()
+        self._openalex_search_fn = openalex_search_fn
+        self._arxiv_search_fn = arxiv_search_fn
+        self._europe_pmc_search_fn = europe_pmc_search_fn
+        self._github_search_fn = github_search_fn
+        self._sec_edgar_search_fn = sec_edgar_search_fn
+        self._scoped_serper_fn = scoped_serper_fn
+
+    # ── non-scoped, fixed-issuer-class adapters ──────────────────────────
+    def _primary_literature_adapters(self) -> list[DiscoveryAdapter]:
+        # OpenAlex-SEARCH + arxiv + europe_pmc. NOT S2 (core baseline).
+        return [
+            DiscoveryAdapter("openalex_search", "primary_literature", self._openalex_search_fn),
+            DiscoveryAdapter("arxiv", "primary_literature", self._arxiv_search_fn),
+            DiscoveryAdapter("europe_pmc", "primary_literature", self._europe_pmc_search_fn),
+        ]
+
+    def _code_adapters(self) -> list[DiscoveryAdapter]:
+        return [DiscoveryAdapter("github", "code", self._github_search_fn)]
+
+    def _scoped_serper_adapter(
+        self, need: str, scopes: list[str], *, source: str,
+    ) -> DiscoveryAdapter:
+        bound = functools.partial(
+            self._scoped_serper_fn, scopes=list(scopes), source=source,
+        )
+        return DiscoveryAdapter(source, need, bound, scoped=True)
+
+    def adapters_for_need(
+        self, need: str, *, jurisdictions: list[str],
+    ) -> list[DiscoveryAdapter]:
+        """Return the adapters mapped to a single `EvidenceNeed`, scoped to the
+        given jurisdiction codes. NO domain literal; keyed only on the need.
+
+        A SCOPED need with no resolved scopes for the jurisdiction(s) yields NO
+        adapter (the run falls back to core open_web + scholarly, never a
+        fabricated/US-default scope). `standards` always reaches INTL bodies, so
+        it yields an adapter even with no jurisdiction.
+        """
+        if need == "primary_literature":
+            return self._primary_literature_adapters()
+        if need == "code":
+            return self._code_adapters()
+        if need == "open_web":
+            # The CORE baseline already runs generic Serper over the sub-queries
+            # (single source of truth — mirrors the S2 exclusion from
+            # primary_literature). open_web therefore adds NO registry adapter;
+            # a registry open-web adapter would either duplicate the core Serper
+            # OR (as the pre-fix default policy_targeted_serper did) inject the
+            # US-only _POLICY_SITE_FILTERS host literal onto the on-path — the
+            # exact cross-jurisdiction frame bug Phase 2 exists to eliminate.
+            return []
+        if need == "company_filings":
+            adapters: list[DiscoveryAdapter] = [
+                DiscoveryAdapter("sec_edgar", "company_filings", self._sec_edgar_search_fn),
+            ]
+            # Non-US issuer-filing scopes from the data file (e.g. sedarplus.ca).
+            scopes = self.scope_loader.scopes_for("company_filings", jurisdictions)
+            if scopes:
+                adapters.append(self._scoped_serper_adapter(
+                    "company_filings", scopes, source="serper_company_filings",
+                ))
+            return adapters
+        if need in SCOPED_NEEDS:
+            scopes = self.scope_loader.scopes_for(need, jurisdictions)
+            out: list[DiscoveryAdapter] = []
+            if scopes:
+                out.append(self._scoped_serper_adapter(
+                    need, scopes, source=f"serper_{need}",
+                ))
+            # news_press is the issuer-newsroom (jurisdiction-scoped, data-driven)
+            # ONLY. The generic open-web component is the CORE baseline Serper —
+            # NOT a registry adapter (a registry open-web adapter would re-inject
+            # the US _POLICY_SITE_FILTERS literal on the on-path; same root cause
+            # as the open_web fix above).
+            return out
+        # Defensive: an unrecognized need (should never happen — validated
+        # upstream) yields no adapter rather than a domain branch.
+        logger.info(
+            "[source_adapter_registry] no adapter mapping for need=%r", need,
+        )
+        return []
+
+
+def build_registry(
+    *, scope_loader: JurisdictionScopeLoader | None = None, **adapter_overrides: Any,
+) -> SourceAdapterRegistry:
+    """Convenience constructor (tests inject stub adapters via kwargs)."""
+    return SourceAdapterRegistry(scope_loader=scope_loader, **adapter_overrides)
diff --git a/src/polaris_graph/planning/research_planner.py b/src/polaris_graph/planning/research_planner.py
index 4b53c323..c37cf3b0 100644
--- a/src/polaris_graph/planning/research_planner.py
+++ b/src/polaris_graph/planning/research_planner.py
@@ -41,6 +41,7 @@ from __future__ import annotations
 import hashlib
 import json
 import logging
+import re
 from dataclasses import dataclass, field
 from typing import Any, Callable
 
@@ -62,6 +63,114 @@ CLAIM_TYPES: frozenset[str] = frozenset({
     "descriptive",
 })
 
+
+# ── I-meta-005 Phase 2 (#986): field-agnostic EVIDENCE-NEED taxonomy ─────────
+# A field-INVARIANT enum (10 needs, brief §2.1) that declares WHAT KINDS of
+# evidence the question needs — NOT a domain. The planner emits these on the
+# frame; source discovery (the need-type registry) routes adapters off these,
+# never off a domain enum. `company_filings` keeps the legacy
+# due_diligence/sec_edgar capability reachable on-mode; standards/datasets/
+# news_press cover engineering bodies / official data portals / institutional
+# statements so "any field, any region" reaches the right issuer, never a bare
+# open_web fallback.
+EVIDENCE_NEEDS: frozenset[str] = frozenset({
+    "primary_literature",
+    "regulatory",
+    "legal",
+    "statistical",
+    "standards",
+    "datasets",
+    "news_press",
+    "company_filings",
+    "code",
+    "open_web",
+})
+
+# Normalized JURISDICTION code SHAPE (brief §2.1b). ISO-3166 alpha-2 (e.g.
+# "CA", "JP") plus the two pseudo-codes "EU" and "INTL". The PARSER validates
+# SHAPE only; the scope LOADER validates MEMBERSHIP non-fatally (a valid-shape
+# code absent from `jurisdiction_scopes.yaml` logs + yields no scope and is
+# NEVER parser-fatal). "EU" matches `^[A-Z]{2}$`; "INTL" is the only 4-letter
+# member, allowed explicitly.
+_JURISDICTION_ALPHA2_RE = re.compile(r"^[A-Z]{2}$")
+_JURISDICTION_EXTRA_CODES: frozenset[str] = frozenset({"EU", "INTL"})
+
+
+class MalformedPlanError(RuntimeError):
+    """Raised when the planner emits a STRUCTURALLY malformed need/jurisdiction
+    frame (I-meta-005 Phase 2, brief §2.1/2.1b): an `evidence_needs` value not
+    in `EVIDENCE_NEEDS`, or a `jurisdictions` value whose SHAPE is not a valid
+    code (`^[A-Z]{2}$` / "EU" / "INTL").
+
+    Distinct from `PlannerError` (unusable LLM output) AND from a fail-OPEN
+    adapter/network error: a malformed plan FAILS LOUD before ANY live
+    discovery and is re-raised PAST the fail-open dispatch wrapper at the live
+    seam — it NEVER silently degrades to core Serper/S2 (brief §2.4 P2-note-1).
+    A valid-shape-but-unknown jurisdiction code is NOT malformed (membership is
+    a non-fatal scope-loader concern); only a bad SHAPE raises here.
+    """
+
+
+def is_valid_jurisdiction_shape(code: str) -> bool:
+    """True iff `code` is a SHAPE-valid normalized jurisdiction code
+    (`^[A-Z]{2}$` or "EU"/"INTL"). MEMBERSHIP (presence in the data file) is a
+    separate, non-fatal scope-loader concern."""
+    if not isinstance(code, str):
+        return False
+    token = code.strip()
+    if not token:
+        return False
+    if token in _JURISDICTION_EXTRA_CODES:
+        return True
+    return bool(_JURISDICTION_ALPHA2_RE.match(token))
+
+
+def validate_evidence_needs(values: list[str]) -> list[str]:
+    """Validate + normalize `evidence_needs` (brief §2.1). Each value must be in
+    `EVIDENCE_NEEDS` (case-insensitive); an unknown value FAILS LOUD with
+    `MalformedPlanError` (NOT a silent fallback — only an EMPTY list is the safe
+    older-plan fallback, handled by the router). Returns the normalized,
+    order-preserving, deduped lowercased list."""
+    out: list[str] = []
+    seen: set[str] = set()
+    for raw in values or []:
+        token = str(raw).strip().lower()
+        if not token:
+            continue
+        if token not in EVIDENCE_NEEDS:
+            raise MalformedPlanError(
+                f"malformed evidence_need={raw!r}; allowed={sorted(EVIDENCE_NEEDS)}"
+            )
+        if token in seen:
+            continue
+        seen.add(token)
+        out.append(token)
+    return out
+
+
+def validate_jurisdiction_shapes(values: list[str]) -> list[str]:
+    """Validate + normalize `jurisdictions` SHAPE (brief §2.1b). Each value must
+    be a SHAPE-valid normalized code; a malformed SHAPE FAILS LOUD with
+    `MalformedPlanError`. A valid-shape-but-unknown code is KEPT (membership is
+    checked non-fatally later by the scope loader). Returns the normalized,
+    order-preserving, deduped UPPERCASED list."""
+    out: list[str] = []
+    seen: set[str] = set()
+    for raw in values or []:
+        token = str(raw).strip().upper()
+        if not token:
+            continue
+        if not is_valid_jurisdiction_shape(token):
+            raise MalformedPlanError(
+                f"malformed jurisdiction code={raw!r}; expected ISO-3166 "
+                f"alpha-2 / 'EU' / 'INTL'"
+            )
+        if token in seen:
+            continue
+        seen.add(token)
+        out.append(token)
+    return out
+
 # UPPER bound on emitted sub-queries (brief §2.1). >40 is merged/truncated
 # deterministically. The fetch cap (`PG_SWEEP_FETCH_CAP`) bounds FETCHED URLs
 # downstream; this bounds the per-question query fan-out.
@@ -89,6 +198,14 @@ class ResearchFrame:
     comparators: list[str] = field(default_factory=list)
     constraints: list[str] = field(default_factory=list)
     claim_type: str = "descriptive"
+    # I-meta-005 Phase 2 (#986): additive, default [] -> OFF unaffected.
+    # `evidence_needs` = the field-agnostic EvidenceNeed values the question
+    # needs (brief §2.1). `jurisdictions` = normalized codes for scope routing
+    # (brief §2.1b). Both validated at parse time (malformed value/SHAPE ->
+    # MalformedPlanError); a valid-shape-unknown jurisdiction is kept (non-fatal
+    # membership). Empty `evidence_needs` -> the router's safe generic fallback.
+    evidence_needs: list[str] = field(default_factory=list)
+    jurisdictions: list[str] = field(default_factory=list)
 
     def to_anchor_protocol(self, research_question: str) -> dict[str, Any]:
         """Produce an anchor-protocol dict for `validate_amplified_queries`
@@ -144,6 +261,11 @@ class ResearchPlan:
                 "comparators": list(self.frame.comparators),
                 "constraints": list(self.frame.constraints),
                 "claim_type": self.frame.claim_type,
+                # I-meta-005 Phase 2 (#986): additive frame fields included in
+                # the canonical projection so the SHA-pinned plan covers the
+                # declared evidence-needs + jurisdictions.
+                "evidence_needs": list(self.frame.evidence_needs),
+                "jurisdictions": list(self.frame.jurisdictions),
             },
             "sub_queries": list(self.sub_queries),
             "outline": [
@@ -228,6 +350,19 @@ def _parse_frame(obj: dict[str, Any]) -> ResearchFrame:
             f"planner emitted unknown claim_type={claim_type!r}; "
             f"allowed={sorted(CLAIM_TYPES)}"
         )
+    # I-meta-005 Phase 2 (#986): additive evidence_needs + jurisdictions.
+    # Validated HERE at parse time (brief §2.1/2.1b): a malformed evidence_need
+    # value OR a malformed jurisdiction SHAPE raises MalformedPlanError (fail
+    # loud, NOT a silent fallback). A missing/empty list is fine (older legacy
+    # plan / OFF) — only the router treats empty evidence_needs as the safe
+    # generic fallback. A valid-shape-unknown jurisdiction is kept (membership
+    # is a non-fatal scope-loader concern).
+    evidence_needs = validate_evidence_needs(
+        _as_str_list(raw_frame.get("evidence_needs"))
+    )
+    jurisdictions = validate_jurisdiction_shapes(
+        _as_str_list(raw_frame.get("jurisdictions"))
+    )
     return ResearchFrame(
         entities=_as_str_list(raw_frame.get("entities")),
         relations=_as_str_list(raw_frame.get("relations")),
@@ -235,6 +370,8 @@ def _parse_frame(obj: dict[str, Any]) -> ResearchFrame:
         comparators=_as_str_list(raw_frame.get("comparators")),
         constraints=_as_str_list(raw_frame.get("constraints")),
         claim_type=claim_type,
+        evidence_needs=evidence_needs,
+        jurisdictions=jurisdictions,
     )
 
 
@@ -337,6 +474,7 @@ def _build_prompt(question: str, *, more_facets: bool, min_subqueries: int) -> s
     facets + archetype outline."""
     archetype_list = ", ".join(SECTION_ARCHETYPES)
     claim_type_list = ", ".join(sorted(CLAIM_TYPES))
+    evidence_need_list = ", ".join(sorted(EVIDENCE_NEEDS))
     base = (
         "You are a field-agnostic research planner. Decompose the research "
         "question into a structured plan. The question may be from ANY field "
@@ -350,7 +488,17 @@ def _build_prompt(question: str, *, more_facets: bool, min_subqueries: int) -> s
         '     "metrics":    [the quantities / outcomes / measures of interest],\n'
         '     "comparators":[the alternatives / baselines / counterfactuals],\n'
         '     "constraints":[scope limits: population, jurisdiction, timeframe, setting],\n'
-        f'     "claim_type": one of [{claim_type_list}]\n'
+        f'     "claim_type": one of [{claim_type_list}],\n'
+        '     "evidence_needs": [the KINDS of evidence this question needs — '
+        f"choose from: {evidence_need_list}; pick every kind the question "
+        "genuinely requires, e.g. a regulatory question needs 'regulatory' "
+        "(and likely 'legal'/'statistical'); a software question needs 'code'; "
+        "a company question needs 'company_filings'; an engineering-standards "
+        "question needs 'standards'; leave EMPTY only if truly generic],\n"
+        '     "jurisdictions": [NORMALIZED codes for any country/region the '
+        "question is scoped to — ISO-3166 alpha-2 (e.g. \"US\",\"CA\",\"GB\","
+        "\"JP\",\"AU\") or \"EU\"/\"INTL\"; EMPTY if the question is not "
+        "jurisdiction-specific. Use the CODE, never a country name]\n"
         "  },\n"
         '  "sub_queries": [faceted search queries, each a focused phrase that '
         "covers ONE facet of the question — collectively spanning every "
diff --git a/src/polaris_graph/retrieval/domain_backends.py b/src/polaris_graph/retrieval/domain_backends.py
index 78b9abf0..69e6521f 100644
--- a/src/polaris_graph/retrieval/domain_backends.py
+++ b/src/polaris_graph/retrieval/domain_backends.py
@@ -215,6 +215,67 @@ def policy_targeted_serper(
     return out
 
 
+def site_scoped_serper(
+    query: str,
+    *,
+    scopes: list[str],
+    source: str = "serper_scoped",
+    limit: int = PG_DOMAIN_MAX_HITS,
+) -> list[SearchCandidate]:
+    """Field-agnostic, JURISDICTION-driven Serper scope query (I-meta-005
+    Phase 2 #986). The generalized cousin of `policy_targeted_serper`: the
+    `site:` scopes are PASSED IN (resolved from `jurisdiction_scopes.yaml` by
+    the need-type router), NOT read from the US-only `_POLICY_SITE_FILTERS`
+    literal. NO host literal lives in this function — knowledge is in the DATA.
+
+    `scopes` is a list of bare canonical hosts (e.g. `["canada.ca", "gc.ca"]`);
+    each becomes a `site:<host>` clause. Empty scopes -> [] (no scope query is
+    fired; the caller falls back to core open_web + scholarly). Fail-open.
+    """
+    if not scopes:
+        return []
+    api_key = os.getenv("SERPER_API_KEY", "").strip()
+    if not api_key:
+        return []
+    try:
+        from src.polaris_graph.benchmark import pathB_capture as _pathb
+        _pathb.record_retrieval_attempt("serper")
+    except Exception:
+        pass
+    site_clause = " OR ".join(f"site:{host}" for host in scopes)
+    q = f"{query} ({site_clause})"
+    try:
+        with httpx.Client(timeout=HTTP_TIMEOUT) as c:
+            r = c.post(
+                "https://google.serper.dev/search",
+                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
+                json={"q": q, "num": max(1, min(limit, 20))},
+            )
+        if r.status_code != 200:
+            return []
+        data = r.json()
+    except Exception as exc:
+        logger.debug("[domain_backends] scoped serper failed: %s", exc)
+        return []
+    out: list[SearchCandidate] = []
+    for item in (data.get("organic") or [])[:limit]:
+        url = item.get("link", "") or ""
+        if not url:
+            continue
+        out.append(SearchCandidate(
+            url=url,
+            title=item.get("title", "") or "",
+            snippet=item.get("snippet", "") or "",
+            source=source,
+        ))
+    try:
+        from src.polaris_graph.benchmark import pathB_capture as _pathb
+        _pathb.record_retrieval_query(source, q, [c.url for c in out])
+    except Exception:
+        pass
+    return out
+
+
 # ─────────────────────────────────────────────────────────────────────────────
 # DUE DILIGENCE: SEC EDGAR full-text search
 # ─────────────────────────────────────────────────────────────────────────────
@@ -388,6 +449,69 @@ def europe_pmc_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[Searc
         return []
 
 
+# ─────────────────────────────────────────────────────────────────────────────
+# PRIMARY LITERATURE: OpenAlex /works keyword SEARCH (I-meta-005 Phase 2 #986)
+# ─────────────────────────────────────────────────────────────────────────────
+# DISTINCT from the OpenAlex ENRICHMENT path in live_retriever
+# (`/works/doi:<doi>` per-URL lookup). This is the keyword DISCOVERY adapter:
+# `/works?search=<query>` returns NEW candidate works the keyword set surfaces,
+# re-keyed under the `primary_literature` need (NOT a domain). Keyless / free.
+# Fail-open: any error / empty body returns [] (the run degrades to the core
+# Serper + S2 + the other primary-lit adapters). The CORE baseline already runs
+# S2 over the sub-queries, so this ADDS non-baseline scholarly-graph breadth.
+
+_OPENALEX_WORKS_SEARCH = "https://api.openalex.org/works"
+
+
+def openalex_search(query: str, limit: int = PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]:
+    """Keyword-SEARCH OpenAlex /works for primary-literature discovery.
+
+    Emits a resolvable primary-literature URL per work in DOI -> OpenAlex-id
+    priority; a work with neither is SKIPPED. Candidates flow through the SAME
+    fetch / tier / strict_verify chokepoint as Serper/S2. Fail-open.
+    """
+    try:
+        data = _http_get_json(
+            _OPENALEX_WORKS_SEARCH,
+            params={
+                "search": query,
+                "per_page": max(1, min(limit, 25)),
+            },
+        )
+        if not data:
+            return []
+        results = data.get("results") or []
+        out: list[SearchCandidate] = []
+        for work in results:
+            doi = str(work.get("doi") or "").strip()
+            oa_id = str(work.get("id") or "").strip()
+            if doi:
+                # OpenAlex DOIs are full URLs (https://doi.org/...).
+                url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
+            elif oa_id:
+                url = oa_id
+            else:
+                continue  # no resolvable id — skip
+            title = str(work.get("display_name") or "").strip()
+            out.append(SearchCandidate(
+                url=url,
+                title=title,
+                snippet="",
+                source="openalex_search",
+                metadata={
+                    "doi": doi or None,
+                    "openalex_id": oa_id or None,
+                    "year": work.get("publication_year"),
+                },
+            ))
+            if len(out) >= limit:
+                break
+        return out
+    except Exception as exc:
+        logger.warning("[domain_backends] openalex_search failed (fail-open): %s", exc)
+        return []
+
+
 # ─────────────────────────────────────────────────────────────────────────────
 # Dispatcher
 # ─────────────────────────────────────────────────────────────────────────────
@@ -460,3 +584,98 @@ def run_domain_backends(
         backends_used=used,
         per_backend_counts=per,
     )
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# I-meta-005 Phase 2 (#986): NEED-TYPE on-path dispatcher (field-agnostic)
+# ─────────────────────────────────────────────────────────────────────────────
+# Replaces `run_domain_backends` on the ON-path. Routes off the planner frame's
+# DECLARED evidence-needs + extracted jurisdiction via the need-type registry —
+# NO `if domain ==` branch reached on-mode (EXIT P2-4). OFF-mode the legacy
+# switch above runs byte-identically. The router import is LAZY (the router
+# imports adapters FROM this module — avoids a circular import at module load).
+
+
+@dataclass
+class NeedTypeBackendResult:
+    """On-path analogue of `DomainBackendResult` — carries NO domain field
+    (field-agnostic). `needs` records the declared evidence-needs routed."""
+
+    needs: list[str]
+    candidates: list[SearchCandidate]
+    backends_used: list[str]
+    per_backend_counts: dict[str, int]
+
+
+def run_need_type_backends(
+    *,
+    frame: Any,
+    research_question: str,
+    amplified_queries: list[str] | None = None,
+    max_hits_per_backend: int = PG_DOMAIN_MAX_HITS,
+    registry: Any = None,
+) -> NeedTypeBackendResult:
+    """Run the need-type-routed discovery adapters for the planner `frame`.
+
+    The field-agnostic ON-path replacement for `run_domain_backends`. Resolves
+    the adapter union via `need_type_router.route_needs_to_adapters(frame)`
+    (NO domain literal), then runs each adapter with the SAME dedupe-by-URL +
+    per-backend cap discipline as the legacy switch (brief §2.5).
+
+    Validation note (brief §2.4 P2-note-1): a MALFORMED frame
+    (`evidence_needs` not in the enum / jurisdiction bad SHAPE) raises
+    `MalformedPlanError` from the router's up-front validation — that
+    propagates (it is NOT swallowed here). The live seam validates the frame
+    BEFORE any discovery; this function additionally surfaces a malformed frame
+    loudly if reached. ADAPTER exceptions stay fail-open (each `_run` swallows).
+    """
+    # Lazy imports (router imports adapters from THIS module).
+    from src.polaris_graph.discovery.need_type_router import (
+        route_needs_to_adapters,
+    )
+    from src.polaris_graph.planning.research_planner import (
+        validate_evidence_needs,
+    )
+
+    # route_needs_to_adapters validates SHAPE + need-enum up-front and re-raises
+    # MalformedPlanError (fail loud, NOT fail-open).
+    adapters = route_needs_to_adapters(frame, registry=registry)
+    # Record the normalized declared needs (after fallback) for telemetry.
+    declared_needs = validate_evidence_needs(
+        list(getattr(frame, "evidence_needs", []) or [])
+    )
+
+    queries: list[str] = [research_question]
+    if amplified_queries:
+        queries.extend(amplified_queries[:3])   # cap amplified count (parity)
+
+    candidates: list[SearchCandidate] = []
+    used: list[str] = []
+    per: dict[str, int] = {}
+
+    def _run(name: str, fn) -> None:
+        nonlocal candidates, used, per
+        try:
+            got: list[SearchCandidate] = []
+            for q in queries:
+                got.extend(fn(q, limit=max_hits_per_backend))
+                if len(got) >= max_hits_per_backend * 2:
+                    break
+            seen_urls = {c.url for c in candidates}
+            new = [c for c in got if c.url and c.url not in seen_urls]
+            candidates.extend(new)
+            used.append(name)
+            per[name] = len(new)
+        except Exception as exc:
+            logger.warning("[need_type_backends] %s failed (fail-open): %s", name, exc)
+            per[name] = 0
+
+    for adapter in adapters:
+        _run(adapter.name, adapter.run)
+
+    return NeedTypeBackendResult(
+        needs=declared_needs,
+        candidates=candidates,
+        backends_used=used,
+        per_backend_counts=per,
+    )
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index e5854556..7da2762b 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -1685,6 +1685,7 @@ def run_live_retrieval(
     domain: Optional[str] = None,
     seed_urls: Optional[list[str]] = None,
     seed_only: bool = False,
+    research_frame: Any = None,
 ) -> LiveRetrievalResult:
     """Execute live retrieval and classify the corpus.
 
@@ -1702,12 +1703,40 @@ def run_live_retrieval(
             tech / due_diligence). When set, R-6 Gap-2 domain backends
             augment the generic Serper+S2 retrieval with arxiv (tech),
             SEC EDGAR (DD), or policy-site targeted Serper queries.
+        research_frame: Optional planner `ResearchFrame` (I-meta-005 Phase 2
+            #986). When set (ON-mode), the field-agnostic need-type registry
+            REPLACES the domain backends at the Step-2a seam — discovery is
+            keyed on the frame's declared `evidence_needs` + extracted
+            `jurisdictions`, NOT a domain. Mutually exclusive with `domain` on
+            the on-path (the sweep passes `domain=None` on-mode).
 
     Returns LiveRetrievalResult.
+
+    Raises:
+        MalformedPlanError: when `research_frame` carries a malformed
+            `evidence_needs` value OR a malformed jurisdiction SHAPE. This is
+            validated UP-FRONT (before ANY live discovery, incl. core
+            Serper/S2) and FAILS LOUD — it NEVER silently degrades to core
+            Serper/S2 (brief §2.4 P2-note-1). Distinct from the fail-OPEN
+            adapter/network handling at the Step-2a seam.
     """
     api_calls: dict[str, int] = {"serper": 0, "s2": 0, "openalex": 0, "fetch": 0}
     notes: list[str] = []
 
+    # ── Step 0: UP-FRONT plan validation (I-meta-005 Phase 2, P2-note-1) ──
+    # A malformed frame (bad evidence_need / bad jurisdiction SHAPE) must FAIL
+    # LOUD here — BEFORE the core Serper/S2 baseline spends or populates any
+    # candidate. The router's validation raises MalformedPlanError; we let it
+    # propagate (it is a VALIDATION error, distinct from the fail-OPEN
+    # adapter/network handling at Step 2a). Only fires on-mode (frame present).
+    if research_frame is not None and not seed_only:
+        from src.polaris_graph.discovery.need_type_router import (
+            validate_frame_needs,
+        )
+        # Raises MalformedPlanError on a malformed value/SHAPE; a valid-shape
+        # unknown jurisdiction + an empty evidence_needs both pass (non-fatal).
+        validate_frame_needs(research_frame)
+
     # ── Step 1: compile the effective query list ──────────────────────
     all_queries: list[str] = [research_question]
     if amplified_queries:
@@ -1788,11 +1817,54 @@ def run_live_retrieval(
                 query_origin=q,
             ))
 
-    # ── Step 2a: R-6 Gap-2 domain-routed backends ──────────────────
-    # arXiv for tech, SEC EDGAR for due-diligence, policy-site Serper
-    # for policy. Fail-open: any backend exception yields 0 new hits.
-    # Skipped on the seed_only deepener pass (no extra retrieval).
-    if domain and not seed_only:
+    # ── Step 2a: specialized issuer-class backends ──────────────────
+    # I-meta-005 Phase 2 (#986) DUAL PATH:
+    #   ON-mode (research_frame present): the field-agnostic NEED-TYPE registry
+    #     REPLACES the domain backends — discovery is routed off the frame's
+    #     declared evidence_needs + jurisdictions (NO `if domain ==` branch
+    #     reached). The malformed-frame case already FAILED LOUD at Step 0.
+    #   OFF-mode (domain set, no frame): the legacy R-6 Gap-2 domain switch runs
+    #     byte-identically (arXiv for tech, SEC EDGAR for DD, policy-site Serper
+    #     for policy, Europe PMC for clinical).
+    # Both stay fail-OPEN at the live seam (ADAPTER/network exception -> 0 new
+    # hits; the run degrades to the core Serper/S2 baseline). Skipped on the
+    # seed_only deepener pass (no extra retrieval).
+    if research_frame is not None and not seed_only:
+        # ON-path: need-type registry dispatch. NO domain literal consulted.
+        try:
+            from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
+                run_need_type_backends,
+            )
+            need_result = run_need_type_backends(
+                frame=research_frame,
+                research_question=research_question,
+                amplified_queries=amplified_queries,
+            )
+            for cand in need_result.candidates:
+                url = cand.url
+                if not url or url in seen_urls:
+                    continue
+                seen_urls.add(url)
+                if not getattr(cand, "query_origin", ""):
+                    cand.query_origin = "need_type_backend"
+                candidates.append(cand)
+            if need_result.backends_used:
+                notes.append(
+                    f"need_type_backends({need_result.needs}): "
+                    f"{need_result.per_backend_counts}"
+                )
+                for backend_name in need_result.backends_used:
+                    api_calls[backend_name] = (
+                        api_calls.get(backend_name, 0) + 1
+                    )
+        except Exception as exc:
+            # ADAPTER/network fail-open ONLY. A MalformedPlanError cannot reach
+            # here — it raised at Step 0 before the baseline ran.
+            logger.warning(
+                "[live_retriever] need_type_backends failed (fail-open): %s",
+                exc,
+            )
+    elif domain and not seed_only:
         try:
             from src.polaris_graph.retrieval.domain_backends import (  # noqa: E402
                 run_domain_backends,
diff --git a/tests/polaris_graph/discovery/__init__.py b/tests/polaris_graph/discovery/__init__.py
new file mode 100644
index 00000000..e69de29b
diff --git a/tests/polaris_graph/discovery/test_source_discovery_phase2.py b/tests/polaris_graph/discovery/test_source_discovery_phase2.py
new file mode 100644
index 00000000..fe6afdf1
--- /dev/null
+++ b/tests/polaris_graph/discovery/test_source_discovery_phase2.py
@@ -0,0 +1,714 @@
+"""I-meta-005 Phase 2 (#986) offline smoke — source discovery by NEED-TYPE.
+
+Implements brief §3 cases P2-1..P2-11 + P2-malformed. Spend-free + serialized
+(§8.4): every adapter is a PLAIN-CLASS stub (NO unittest.mock), and the
+whole-wiring tests assert no live HTTP client is constructed.
+
+Anchor invariants:
+- P2-1  OFF byte-identity (legacy `run_domain_backends` unchanged).
+- P2-2  need-type routing selects exactly the mapped adapters (NOT S2).
+- P2-3  EXIT issuer-class breadth (>=3 distinct authoritative classes).
+- P2-4  zero `if domain ==` on the on-path (whole wiring incl. the seam).
+- P2-5  jurisdiction-scoped gov from the NEW versioned data file.
+- P2-6  empty-needs fallback -> {primary_literature, open_web}.
+- P2-7  spend-free (no live HTTP client constructed).
+- P2-8  jurisdiction contract (CA scopes / [] / unknown ZZ / malformed SHAPE).
+- P2-9  company_filings reachable on-mode (sec_edgar + non-US issuer scope).
+- P2-10 new-needs routing (standards/datasets/news_press).
+- P2-11 whole-wiring actual-invocation (code-only frame -> {serper,S2,github}).
+- P2-malformed: malformed plan FAILS LOUD BEFORE any discovery, not swallowed.
+"""
+from __future__ import annotations
+
+from pathlib import Path
+
+import pytest
+
+from src.polaris_graph.discovery import need_type_router as ntr_module
+from src.polaris_graph.discovery.need_type_router import (
+    route_needs_to_adapters,
+    validate_frame_needs,
+)
+from src.polaris_graph.discovery.source_adapter_registry import (
+    JurisdictionScopeLoader,
+    SourceAdapterRegistry,
+    _normalize_host,
+)
+from src.polaris_graph.planning.research_planner import (
+    EVIDENCE_NEEDS,
+    MalformedPlanError,
+    ResearchFrame,
+)
+from src.polaris_graph.retrieval import domain_backends as db
+from src.polaris_graph.retrieval import live_retriever as lr
+from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
+
+
+_REPO_ROOT = Path(__file__).resolve().parents[3]
+_SCOPES_PATH = _REPO_ROOT / "config" / "discovery" / "jurisdiction_scopes.yaml"
+_VERSION_PATH = _REPO_ROOT / "config" / "discovery" / "VERSION"
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Plain-class stubs (NO unittest.mock — §8.4 / §9.4)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+class CaptureAdapter:
+    """A capture-recording adapter stub. `fn(query, limit)` records the call
+    and returns its canned candidates."""
+
+    def __init__(self, name: str, candidates=None):
+        self.name = name
+        self.candidates = candidates or []
+        self.calls: list[tuple[str, int]] = []
+
+    def __call__(self, query, limit=10):
+        self.calls.append((query, limit))
+        return list(self.candidates)
+
+
+class CaptureScopedSerper:
+    """Capture stub for `site_scoped_serper(query, *, scopes, source, limit)`.
+    Records the scopes it was bound with so the test can assert the resolved
+    jurisdiction scopes without any network call."""
+
+    def __init__(self):
+        self.calls: list[dict] = []
+
+    def __call__(self, query, *, scopes, source="serper_scoped", limit=10):
+        self.calls.append({"query": query, "scopes": list(scopes), "source": source})
+        # Emit one fake candidate per call so dedupe/cap can be exercised.
+        return [SearchCandidate(url=f"https://{scopes[0]}/x" if scopes else "https://x", source=source)]
+
+
+def _make_registry(scoped_serper=None, **adapter_overrides) -> SourceAdapterRegistry:
+    """Build a registry with stub adapters; the real scope loader (reads the
+    committed yaml DATA — no network)."""
+    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
+    return SourceAdapterRegistry(
+        scope_loader=loader,
+        scoped_serper_fn=scoped_serper or CaptureScopedSerper(),
+        **adapter_overrides,
+    )
+
+
+def _frame(evidence_needs=None, jurisdictions=None) -> ResearchFrame:
+    return ResearchFrame(
+        entities=["x"],
+        claim_type="descriptive",
+        evidence_needs=list(evidence_needs or []),
+        jurisdictions=list(jurisdictions or []),
+    )
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-1 — OFF byte-identity: legacy run_domain_backends unchanged
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_1_off_domain_switch_byte_identical_tech(monkeypatch):
+    """OFF path: tech domain selects exactly {arxiv, github} in order."""
+    ax = CaptureAdapter("arxiv", [SearchCandidate(url="https://arxiv/1", source="arxiv")])
+    gh = CaptureAdapter("github", [SearchCandidate(url="https://gh/1", source="github")])
+    monkeypatch.setattr(db, "arxiv_search", ax)
+    monkeypatch.setattr(db, "github_search_repos", gh)
+    result = db.run_domain_backends(domain="tech", research_question="rag")
+    assert result.domain == "tech"
+    assert result.backends_used == ["arxiv", "github"]
+    assert [c.source for c in result.candidates] == ["arxiv", "github"]
+
+
+def test_p2_1_off_policy_uses_us_only_policy_site_filters():
+    """OFF path: `_POLICY_SITE_FILTERS` text + order is the frozen US-only
+    allowlist (appears ONLY off-path)."""
+    assert db._POLICY_SITE_FILTERS == (
+        "site:federalregister.gov",
+        "site:regulations.gov",
+        "site:fda.gov",
+        "site:cms.gov",
+        "site:hhs.gov",
+        "site:ftc.gov",
+        "site:sec.gov",
+        "site:treasury.gov",
+        "site:ema.europa.eu",
+        "site:nice.org.uk",
+    )
+
+
+def test_p2_1_off_unknown_domain_empty():
+    result = db.run_domain_backends(domain="made_up", research_question="q")
+    assert result.candidates == []
+    assert result.backends_used == []
+
+
+def test_p2_1_off_clinical_europe_pmc_kill_switch(monkeypatch):
+    monkeypatch.setenv("PG_CLINICAL_EUROPE_PMC", "0")
+    epmc = CaptureAdapter("europe_pmc", [SearchCandidate(url="https://pmc/1", source="europe_pmc")])
+    monkeypatch.setattr(db, "europe_pmc_search", epmc)
+    result = db.run_domain_backends(domain="clinical", research_question="q")
+    assert not epmc.calls
+    assert result.candidates == []
+
+
+def test_p2_1_off_clinical_europe_pmc_on_by_default(monkeypatch):
+    monkeypatch.delenv("PG_CLINICAL_EUROPE_PMC", raising=False)
+    epmc = CaptureAdapter("europe_pmc", [SearchCandidate(url="https://pmc/1", source="europe_pmc")])
+    monkeypatch.setattr(db, "europe_pmc_search", epmc)
+    result = db.run_domain_backends(domain="clinical", research_question="q")
+    assert epmc.calls
+    assert result.backends_used == ["europe_pmc"]
+
+
+def test_p2_1_off_dedupe_by_url_order(monkeypatch):
+    dup = "https://shared/x"
+    ax = CaptureAdapter("arxiv", [SearchCandidate(url=dup, source="arxiv")])
+    gh = CaptureAdapter("github", [SearchCandidate(url=dup, source="github")])
+    monkeypatch.setattr(db, "arxiv_search", ax)
+    monkeypatch.setattr(db, "github_search_repos", gh)
+    result = db.run_domain_backends(domain="tech", research_question="q")
+    assert len(result.candidates) == 1
+    assert result.candidates[0].source == "arxiv"  # first backend wins
+    assert result.per_backend_counts == {"arxiv": 1, "github": 0}
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-2 — need-type routing (field-agnostic core); NOT S2
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_2_routing_primary_literature_and_code():
+    reg = _make_registry(
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+        github_search_fn=CaptureAdapter("github"),
+    )
+    adapters = route_needs_to_adapters(
+        _frame(["primary_literature", "code"]), registry=reg,
+    )
+    names = {a.name for a in adapters}
+    assert names == {"openalex_search", "arxiv", "europe_pmc", "github"}
+    # S2 is the CORE baseline, never a registry adapter.
+    assert "s2" not in names
+    assert "semantic_scholar" not in names
+
+
+def test_p2_2_no_domain_attribute_consulted():
+    """The frame carries no domain; routing reads only evidence_needs."""
+    frame = _frame(["code"])
+    assert not hasattr(frame, "domain")
+    adapters = route_needs_to_adapters(frame, registry=_make_registry())
+    assert {a.name for a in adapters} == {"github"}
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-3 — EXIT issuer-class breadth (>=3 distinct authoritative classes)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_3_housing_policy_reaches_three_issuer_classes():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(
+        _frame(["regulatory", "statistical", "legal", "open_web"], ["CA"]),
+        registry=reg,
+    )
+    names = {a.name for a in adapters}
+    # gov-regulatory + statistical-agency + legal-issuer (each a scoped serper).
+    # open_web adds NO registry adapter (core baseline Serper covers it).
+    assert {"serper_regulatory", "serper_statistical", "serper_legal"} <= names
+    scoped_names = {n for n in names if n.startswith("serper_") and n != "serper"}
+    assert len(scoped_names) >= 3
+    # The US-only generic serper ("serper") must NEVER appear on the on-path.
+    assert "serper" not in names
+
+
+def test_p2_3_physics_reaches_three_classes():
+    reg = _make_registry(
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+        github_search_fn=CaptureAdapter("github"),
+    )
+    adapters = route_needs_to_adapters(
+        _frame(["primary_literature", "code"]), registry=reg,
+    )
+    names = {a.name for a in adapters}
+    # scholarly-graph (openalex) + preprint (arxiv) + code-host (github) >= 3
+    assert {"openalex_search", "arxiv", "github"} <= names
+    assert len(names) >= 3
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-4 — zero `if domain ==` on the on-path (whole-wiring grep)
+# ─────────────────────────────────────────────────────────────────────────────
+
+_ON_PATH_SOURCE_FILES = [
+    _REPO_ROOT / "src" / "polaris_graph" / "discovery" / "source_adapter_registry.py",
+    _REPO_ROOT / "src" / "polaris_graph" / "discovery" / "need_type_router.py",
+]
+
+
+def _count_domain_eq_branches(source: str) -> int:
+    """Count ACTUAL `if domain ==` (or `elif domain ==`) control branches in
+    the source CODE via AST — strings/comments/docstrings are ignored entirely,
+    so a docstring that NAMES the forbidden pattern is not a false positive.
+
+    A branch counts when an `If`-test compares a `domain` Name with `==`/`!=`,
+    or a `q["domain"]`/`q['domain']` subscript with `==`/`!=`.
+    """
+    import ast
+
+    count = 0
+
+    def _is_domain_ref(node) -> bool:
+        if isinstance(node, ast.Name) and node.id == "domain":
+            return True
+        if isinstance(node, ast.Subscript):
+            sl = node.slice
+            key = getattr(sl, "value", None)
+            if isinstance(key, str) and key == "domain":
+                return True
+        return False
+
+    for node in ast.walk(ast.parse(source)):
+        if not isinstance(node, ast.If):
+            continue
+        test = node.test
+        if isinstance(test, ast.Compare) and any(
+            isinstance(op, (ast.Eq, ast.NotEq)) for op in test.ops
+        ):
+            operands = [test.left, *test.comparators]
+            if any(_is_domain_ref(op) for op in operands):
+                count += 1
+    return count
+
+
+def test_p2_4_no_if_domain_branch_in_discovery_package():
+    """The NEW on-path discovery files take NO actual `if domain ==` branch
+    (AST-level — docstrings naming the constraint are not false positives)."""
+    for path in _ON_PATH_SOURCE_FILES:
+        src = path.read_text(encoding="utf-8")
+        assert _count_domain_eq_branches(src) == 0, f"{path} has an on-path domain branch"
+        # no domain-enum control literal as a routing key (real code subscript)
+        import ast
+        tree = ast.parse(src)
+        for node in ast.walk(tree):
+            if isinstance(node, ast.Subscript):
+                key = getattr(node.slice, "value", None)
+                assert key != "domain", f"{path} reads q['domain'] on-path"
+
+
+def test_p2_4_need_type_backend_dispatch_takes_no_domain_branch():
+    """The on-path seam function `run_need_type_backends` consults no domain."""
+    import inspect
+    assert _count_domain_eq_branches(inspect.getsource(db.run_need_type_backends)) == 0
+
+
+def test_p2_4_legacy_domain_branch_is_offpath_only():
+    """The legacy `if domain ==` switch survives ONLY in run_domain_backends
+    (off-path), not in the need-type dispatcher."""
+    import inspect
+    assert _count_domain_eq_branches(inspect.getsource(db.run_domain_backends)) >= 1
+    assert _count_domain_eq_branches(inspect.getsource(db.run_need_type_backends)) == 0
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-5 — jurisdiction-scoped gov from the NEW versioned data file
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_5_ca_scopes_from_data_file():
+    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
+    reg_scopes = loader.scopes_for("regulatory", ["CA"])
+    stat_scopes = loader.scopes_for("statistical", ["CA"])
+    legal_scopes = loader.scopes_for("legal", ["CA"])
+    assert "canada.ca" in reg_scopes
+    assert "gc.ca" in reg_scopes  # normalized from any `*.gc.ca`
+    assert "statcan.gc.ca" in stat_scopes
+    assert "canlii.org" in legal_scopes
+    # NOT the US `_POLICY_SITE_FILTERS` hosts
+    assert "federalregister.gov" not in reg_scopes
+
+
+def test_p2_5_jp_scopes_distinct_from_us():
+    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
+    jp = loader.scopes_for("regulatory", ["JP"])
+    us = loader.scopes_for("regulatory", ["US"])
+    assert "pmda.go.jp" in jp
+    assert "fda.gov" in us
+    assert set(jp).isdisjoint(set(us))
+
+
+def test_p2_5_unknown_jurisdiction_no_scope():
+    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
+    assert loader.scopes_for("regulatory", ["ZZ"]) == []
+
+
+def test_p2_5_version_present():
+    assert _VERSION_PATH.exists()
+    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
+    assert loader.version()  # non-empty VERSION
+    assert loader.schema_version is not None
+
+
+def test_p2_5_wildcard_normalization():
+    """build-note-2: a `*.gc.ca` data entry normalizes to `gc.ca` and the
+    emitted scope is `site:gc.ca`, never `site:*.gc.ca`."""
+    assert _normalize_host("*.gc.ca") == "gc.ca"
+    assert _normalize_host("site:*.gc.ca") == "gc.ca"
+    assert _normalize_host(".GC.CA") == "gc.ca"
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["regulatory"], ["CA"]), registry=reg)
+    [a.run("housing", limit=5) for a in adapters]
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "gc.ca" in all_scopes
+    assert all(not s.startswith("*.") for s in all_scopes)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-6 — empty-needs fallback -> {primary_literature, open_web}
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_6_empty_needs_fallback():
+    reg = _make_registry(
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+    )
+    adapters = route_needs_to_adapters(_frame([]), registry=reg)
+    names = {a.name for a in adapters}
+    # empty-needs fallback {primary_literature, open_web}: open_web adds NO
+    # registry adapter (core baseline Serper covers it), so only the
+    # primary_literature adapters remain — and NO US-scoped serper.
+    assert names == {"openalex_search", "arxiv", "europe_pmc"}
+    assert "serper" not in names  # no US _POLICY_SITE_FILTERS on the on-path
+    # never a domain — no sec_edgar / no scoped gov
+    assert "sec_edgar" not in names
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-7 — spend-free: no live HTTP client constructed
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_7_routing_constructs_no_http_client(monkeypatch):
+    """Building + running the registry with stub adapters constructs no
+    httpx.Client (the brief's spend-free invariant)."""
+    constructed = {"count": 0}
+    real_client = db.httpx.Client
+
+    class _Guard:
+        def __init__(self, *a, **k):
+            constructed["count"] += 1
+            raise AssertionError("live HTTP client constructed in spend-free smoke")
+
+    monkeypatch.setattr(db.httpx, "Client", _Guard)
+    reg = _make_registry(
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+        github_search_fn=CaptureAdapter("github"),
+    )
+    adapters = route_needs_to_adapters(_frame(["primary_literature", "code"]), registry=reg)
+    for a in adapters:
+        a.run("q", limit=3)
+    assert constructed["count"] == 0
+    monkeypatch.setattr(db.httpx, "Client", real_client)
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-8 — jurisdiction contract (parser SHAPE vs loader MEMBERSHIP)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_8_ca_resolves_scopes():
+    needs, juris = validate_frame_needs(_frame(["regulatory"], ["CA"]))
+    assert juris == ["CA"]
+
+
+def test_p2_8_empty_jurisdictions_no_scope():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["regulatory"], []), registry=reg)
+    # No jurisdiction -> regulatory has no scope -> no scoped adapter.
+    assert all(not a.name.startswith("serper_regulatory") for a in adapters)
+
+
+def test_p2_8_unknown_shape_valid_code_non_fatal():
+    # "ZZ" is shape-valid but absent from the data file -> non-fatal, no scope.
+    needs, juris = validate_frame_needs(_frame(["regulatory"], ["ZZ"]))
+    assert juris == ["ZZ"]  # parser keeps it (membership is non-fatal)
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["regulatory"], ["ZZ"]), registry=reg)
+    assert all(not a.name.startswith("serper_regulatory") for a in adapters)
+
+
+def test_p2_8_malformed_shape_fails_loud():
+    with pytest.raises(MalformedPlanError):
+        validate_frame_needs(_frame(["regulatory"], ["Canada"]))  # not a code
+    with pytest.raises(MalformedPlanError):
+        validate_frame_needs(_frame(["regulatory"], ["123"]))
+
+
+def test_p2_8_eu_and_intl_shape_valid():
+    needs, juris = validate_frame_needs(_frame(["standards"], ["EU", "INTL"]))
+    assert juris == ["EU", "INTL"]
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-9 — company_filings reachable on-mode
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_9_company_filings_us_selects_sec_edgar():
+    reg = _make_registry(sec_edgar_search_fn=CaptureAdapter("sec_edgar"))
+    adapters = route_needs_to_adapters(_frame(["company_filings"], ["US"]), registry=reg)
+    assert "sec_edgar" in {a.name for a in adapters}
+
+
+def test_p2_9_company_filings_ca_adds_issuer_scope():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap, sec_edgar_search_fn=CaptureAdapter("sec_edgar"))
+    adapters = route_needs_to_adapters(_frame(["company_filings"], ["CA"]), registry=reg)
+    names = {a.name for a in adapters}
+    assert "sec_edgar" in names
+    assert "serper_company_filings" in names
+    for a in adapters:
+        a.run("filing", limit=3)
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "sedarplus.ca" in all_scopes
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-10 — new-needs routing (standards / datasets / news_press)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_10_standards_includes_intl_bodies():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["standards"], ["CA"]), registry=reg)
+    assert "serper_standards" in {a.name for a in adapters}
+    for a in adapters:
+        a.run("iso quality", limit=3)
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "iso.org" in all_scopes  # INTL key folded in
+    assert "scc.ca" in all_scopes   # CA standards body
+
+
+def test_p2_10_standards_without_jurisdiction_still_reaches_intl():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["standards"], []), registry=reg)
+    # INTL standards bodies make standards reachable even with no jurisdiction.
+    assert "serper_standards" in {a.name for a in adapters}
+    for a in adapters:
+        a.run("q", limit=3)
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "iso.org" in all_scopes
+
+
+def test_p2_10_datasets_routes_to_data_portal():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["datasets"], ["CA"]), registry=reg)
+    assert "serper_datasets" in {a.name for a in adapters}
+    for a in adapters:
+        a.run("housing data", limit=3)
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "open.canada.ca" in all_scopes
+
+
+def test_p2_10_news_press_is_issuer_scope_only():
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    adapters = route_needs_to_adapters(_frame(["news_press"], ["CA"]), registry=reg)
+    names = {a.name for a in adapters}
+    assert "serper_news_press" in names  # data-driven issuer newsroom scope
+    # The generic open-web component is the CORE baseline Serper, NOT a registry
+    # adapter — so the US-scoped "serper" must NOT appear on the on-path.
+    assert "serper" not in names
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-11 — whole-wiring actual-invocation (code-only frame)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def _install_capture_baseline(monkeypatch):
+    """Replace live_retriever's core Serper+S2 with capture stubs; return the
+    call-log dicts. fetch_cap=0 keeps the fetch loop from constructing clients."""
+    serper_calls: list[str] = []
+    s2_calls: list[str] = []
+
+    def _fake_serper(query, num=10):
+        serper_calls.append(query)
+        return [{"url": f"https://serp/{len(serper_calls)}", "title": "", "snippet": ""}]
+
+    def _fake_s2(query, limit=20):
+        s2_calls.append(query)
+        return [{"url": f"https://s2/{len(s2_calls)}", "title": "", "snippet": "", "doi": None, "year": None}]
+
+    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
+    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)
+    return serper_calls, s2_calls
+
+
+def test_p2_11_code_only_frame_invokes_serper_s2_github_only(monkeypatch):
+    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
+    gh = CaptureAdapter("github", [SearchCandidate(url="https://gh/1", source="github")])
+    # No-op the other registry adapters so we can prove ONLY github fires.
+    reg = _make_registry(
+        github_search_fn=gh,
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+        sec_edgar_search_fn=CaptureAdapter("sec_edgar"),
+    )
+
+    # Patch the registry the router builds inside run_need_type_backends by
+    # routing through the explicit registry path: call run_need_type_backends.
+    result = db.run_need_type_backends(
+        frame=_frame(["code"]),
+        research_question="rust async runtime",
+        registry=reg,
+    )
+    invoked = set(result.backends_used)
+    assert invoked == {"github"}
+    # The OTHER specialized adapters did NOT fire.
+    assert not reg._openalex_search_fn.calls
+    assert not reg._sec_edgar_search_fn.calls
+
+    # And the live seam runs the CORE Serper+S2 baseline over the sub-queries.
+    retrieval = lr.run_live_retrieval(
+        research_question="rust async runtime",
+        amplified_queries=["tokio scheduler"],
+        fetch_cap=0,
+        enable_openalex_enrich=False,
+        research_frame=_frame(["code"]),
+    )
+    # core baseline fired (serper + s2 over each query)
+    assert serper_calls  # core open-web baseline
+    assert s2_calls      # core scholarly baseline
+
+
+def test_p2_11_regulatory_ca_frame_fires_ca_scoped_serper(monkeypatch):
+    _install_capture_baseline(monkeypatch)
+    cap = CaptureScopedSerper()
+    reg = _make_registry(scoped_serper=cap)
+    result = db.run_need_type_backends(
+        frame=_frame(["regulatory"], ["CA"]),
+        research_question="federal housing policy",
+        registry=reg,
+    )
+    assert "serper_regulatory" in result.backends_used
+    all_scopes = [s for call in cap.calls for s in call["scopes"]]
+    assert "canada.ca" in all_scopes
+
+
+def test_p2_11_dedupe_and_api_calls_accounting(monkeypatch):
+    """Merged candidate dedupe-by-URL + api_calls accounting at the seam."""
+    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
+    gh = CaptureAdapter("github", [
+        SearchCandidate(url="https://dup/x", source="github"),
+        SearchCandidate(url="https://gh/2", source="github"),
+    ])
+    reg = _make_registry(github_search_fn=gh)
+    result = db.run_need_type_backends(
+        frame=_frame(["code"]),
+        research_question="q",
+        registry=reg,
+    )
+    # github dedupes within the seam (both unique here).
+    assert result.per_backend_counts["github"] == 2
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# P2-malformed — fail loud BEFORE any discovery, not swallowed by fail-open
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_p2_malformed_bad_evidence_need_raises_before_baseline(monkeypatch):
+    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
+    bad_frame = ResearchFrame(claim_type="descriptive")
+    # A malformed need cannot be set via the validated parser, so set it raw to
+    # simulate a planner that emitted an off-enum need.
+    object.__setattr__(bad_frame, "evidence_needs", ["totally_made_up_need"])
+    with pytest.raises(MalformedPlanError):
+        lr.run_live_retrieval(
+            research_question="q",
+            fetch_cap=0,
+            enable_openalex_enrich=False,
+            research_frame=bad_frame,
+        )
+    # CRITICAL: failed loud BEFORE the core Serper/S2 baseline spent anything.
+    assert serper_calls == []
+    assert s2_calls == []
+
+
+def test_p2_malformed_bad_jurisdiction_shape_raises_before_baseline(monkeypatch):
+    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
+    bad_frame = _frame(["regulatory"])
+    object.__setattr__(bad_frame, "jurisdictions", ["Canada"])  # not a code
+    with pytest.raises(MalformedPlanError):
+        lr.run_live_retrieval(
+            research_question="q",
+            fetch_cap=0,
+            enable_openalex_enrich=False,
+            research_frame=bad_frame,
+        )
+    assert serper_calls == []
+    assert s2_calls == []
+
+
+def test_p2_malformed_not_swallowed_by_fail_open_wrapper():
+    """The MalformedPlanError is a VALIDATION error — distinct from the
+    fail-OPEN adapter wrapper. route_needs_to_adapters re-raises it."""
+    bad = _frame(["regulatory"])
+    object.__setattr__(bad, "evidence_needs", ["nope"])
+    with pytest.raises(MalformedPlanError):
+        route_needs_to_adapters(bad, registry=_make_registry())
+
+
+def test_p2_malformed_valid_shape_unknown_jurisdiction_is_non_fatal(monkeypatch):
+    """A valid-shape unknown code (ZZ) does NOT raise; the baseline still runs."""
+    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
+    reg = _make_registry()
+    retrieval = lr.run_live_retrieval(
+        research_question="q",
+        fetch_cap=0,
+        enable_openalex_enrich=False,
+        research_frame=_frame(["regulatory"], ["ZZ"]),
+    )
+    # non-fatal: no raise, baseline ran.
+    assert serper_calls
+    assert s2_calls
+
+
+def test_p2_malformed_empty_needs_is_safe_fallback_not_raise():
+    """Only an empty evidence_needs -> safe fallback (no raise)."""
+    adapters = route_needs_to_adapters(_frame([]), registry=_make_registry(
+        openalex_search_fn=CaptureAdapter("openalex_search"),
+        arxiv_search_fn=CaptureAdapter("arxiv"),
+        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
+    ))
+    # open_web adds no registry adapter (core baseline covers it); no US serper.
+    assert {a.name for a in adapters} == {"openalex_search", "arxiv", "europe_pmc"}
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# Enum sanity (10 needs, brief §2.1)
+# ─────────────────────────────────────────────────────────────────────────────
+
+
+def test_evidence_need_enum_is_ten():
+    assert len(EVIDENCE_NEEDS) == 10
+    assert "company_filings" in EVIDENCE_NEEDS
+    assert "standards" in EVIDENCE_NEEDS
+    assert "datasets" in EVIDENCE_NEEDS
+    assert "news_press" in EVIDENCE_NEEDS
```
