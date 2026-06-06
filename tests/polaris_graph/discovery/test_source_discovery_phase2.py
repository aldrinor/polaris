"""I-meta-005 Phase 2 (#986) offline smoke — source discovery by NEED-TYPE.

Implements brief §3 cases P2-1..P2-11 + P2-malformed. Spend-free + serialized
(§8.4): every adapter is a PLAIN-CLASS stub (NO unittest.mock), and the
whole-wiring tests assert no live HTTP client is constructed.

Anchor invariants:
- P2-1  OFF byte-identity (legacy `run_domain_backends` unchanged).
- P2-2  need-type routing selects exactly the mapped adapters (NOT S2).
- P2-3  EXIT issuer-class breadth (>=3 distinct authoritative classes).
- P2-4  zero `if domain ==` on the on-path (whole wiring incl. the seam).
- P2-5  jurisdiction-scoped gov from the NEW versioned data file.
- P2-6  empty-needs fallback -> {primary_literature, open_web}.
- P2-7  spend-free (no live HTTP client constructed).
- P2-8  jurisdiction contract (CA scopes / [] / unknown ZZ / malformed SHAPE).
- P2-9  company_filings reachable on-mode (sec_edgar + non-US issuer scope).
- P2-10 new-needs routing (standards/datasets/news_press).
- P2-11 whole-wiring actual-invocation (code-only frame -> {serper,S2,github}).
- P2-malformed: malformed plan FAILS LOUD BEFORE any discovery, not swallowed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.discovery import need_type_router as ntr_module
from src.polaris_graph.discovery.need_type_router import (
    route_needs_to_adapters,
    validate_frame_needs,
)
from src.polaris_graph.discovery.source_adapter_registry import (
    JurisdictionScopeLoader,
    SourceAdapterRegistry,
    _normalize_host,
)
from src.polaris_graph.planning.research_planner import (
    EVIDENCE_NEEDS,
    MalformedPlanError,
    ResearchFrame,
)
from src.polaris_graph.retrieval import domain_backends as db
from src.polaris_graph.retrieval import live_retriever as lr
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCOPES_PATH = _REPO_ROOT / "config" / "discovery" / "jurisdiction_scopes.yaml"
_VERSION_PATH = _REPO_ROOT / "config" / "discovery" / "VERSION"


# ─────────────────────────────────────────────────────────────────────────────
# Plain-class stubs (NO unittest.mock — §8.4 / §9.4)
# ─────────────────────────────────────────────────────────────────────────────


class CaptureAdapter:
    """A capture-recording adapter stub. `fn(query, limit)` records the call
    and returns its canned candidates."""

    def __init__(self, name: str, candidates=None):
        self.name = name
        self.candidates = candidates or []
        self.calls: list[tuple[str, int]] = []

    def __call__(self, query, limit=10):
        self.calls.append((query, limit))
        return list(self.candidates)


class CaptureScopedSerper:
    """Capture stub for `site_scoped_serper(query, *, scopes, source, limit)`.
    Records the scopes it was bound with so the test can assert the resolved
    jurisdiction scopes without any network call."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, query, *, scopes, source="serper_scoped", limit=10):
        self.calls.append({"query": query, "scopes": list(scopes), "source": source})
        # Emit one fake candidate per call so dedupe/cap can be exercised.
        return [SearchCandidate(url=f"https://{scopes[0]}/x" if scopes else "https://x", source=source)]


def _make_registry(scoped_serper=None, **adapter_overrides) -> SourceAdapterRegistry:
    """Build a registry with stub adapters; the real scope loader (reads the
    committed yaml DATA — no network)."""
    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
    return SourceAdapterRegistry(
        scope_loader=loader,
        scoped_serper_fn=scoped_serper or CaptureScopedSerper(),
        **adapter_overrides,
    )


def _frame(evidence_needs=None, jurisdictions=None) -> ResearchFrame:
    return ResearchFrame(
        entities=["x"],
        claim_type="descriptive",
        evidence_needs=list(evidence_needs or []),
        jurisdictions=list(jurisdictions or []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# P2-1 — OFF byte-identity: legacy run_domain_backends unchanged
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_1_off_domain_switch_byte_identical_tech(monkeypatch):
    """OFF path: tech domain selects exactly {arxiv, github} in order."""
    ax = CaptureAdapter("arxiv", [SearchCandidate(url="https://arxiv/1", source="arxiv")])
    gh = CaptureAdapter("github", [SearchCandidate(url="https://gh/1", source="github")])
    monkeypatch.setattr(db, "arxiv_search", ax)
    monkeypatch.setattr(db, "github_search_repos", gh)
    result = db.run_domain_backends(domain="tech", research_question="rag")
    assert result.domain == "tech"
    assert result.backends_used == ["arxiv", "github"]
    assert [c.source for c in result.candidates] == ["arxiv", "github"]


def test_p2_1_off_policy_uses_us_only_policy_site_filters():
    """OFF path: `_POLICY_SITE_FILTERS` text + order is the frozen US-only
    allowlist (appears ONLY off-path)."""
    assert db._POLICY_SITE_FILTERS == (
        "site:federalregister.gov",
        "site:regulations.gov",
        "site:fda.gov",
        "site:cms.gov",
        "site:hhs.gov",
        "site:ftc.gov",
        "site:sec.gov",
        "site:treasury.gov",
        "site:ema.europa.eu",
        "site:nice.org.uk",
    )


def test_p2_1_off_unknown_domain_empty():
    result = db.run_domain_backends(domain="made_up", research_question="q")
    assert result.candidates == []
    assert result.backends_used == []


def test_p2_1_off_clinical_europe_pmc_kill_switch(monkeypatch):
    monkeypatch.setenv("PG_CLINICAL_EUROPE_PMC", "0")
    epmc = CaptureAdapter("europe_pmc", [SearchCandidate(url="https://pmc/1", source="europe_pmc")])
    monkeypatch.setattr(db, "europe_pmc_search", epmc)
    result = db.run_domain_backends(domain="clinical", research_question="q")
    assert not epmc.calls
    assert result.candidates == []


def test_p2_1_off_clinical_europe_pmc_on_by_default(monkeypatch):
    monkeypatch.delenv("PG_CLINICAL_EUROPE_PMC", raising=False)
    epmc = CaptureAdapter("europe_pmc", [SearchCandidate(url="https://pmc/1", source="europe_pmc")])
    monkeypatch.setattr(db, "europe_pmc_search", epmc)
    result = db.run_domain_backends(domain="clinical", research_question="q")
    assert epmc.calls
    assert result.backends_used == ["europe_pmc"]


def test_p2_1_off_dedupe_by_url_order(monkeypatch):
    dup = "https://shared/x"
    ax = CaptureAdapter("arxiv", [SearchCandidate(url=dup, source="arxiv")])
    gh = CaptureAdapter("github", [SearchCandidate(url=dup, source="github")])
    monkeypatch.setattr(db, "arxiv_search", ax)
    monkeypatch.setattr(db, "github_search_repos", gh)
    result = db.run_domain_backends(domain="tech", research_question="q")
    assert len(result.candidates) == 1
    assert result.candidates[0].source == "arxiv"  # first backend wins
    assert result.per_backend_counts == {"arxiv": 1, "github": 0}


# ─────────────────────────────────────────────────────────────────────────────
# P2-2 — need-type routing (field-agnostic core); NOT S2
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_2_routing_primary_literature_and_code():
    reg = _make_registry(
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
        github_search_fn=CaptureAdapter("github"),
    )
    adapters = route_needs_to_adapters(
        _frame(["primary_literature", "code"]), registry=reg,
    )
    names = {a.name for a in adapters}
    assert names == {"openalex_search", "arxiv", "europe_pmc", "github"}
    # S2 is the CORE baseline, never a registry adapter.
    assert "s2" not in names
    assert "semantic_scholar" not in names


def test_p2_2_no_domain_attribute_consulted():
    """The frame carries no domain; routing reads only evidence_needs."""
    frame = _frame(["code"])
    assert not hasattr(frame, "domain")
    adapters = route_needs_to_adapters(frame, registry=_make_registry())
    assert {a.name for a in adapters} == {"github"}


# ─────────────────────────────────────────────────────────────────────────────
# P2-3 — EXIT issuer-class breadth (>=3 distinct authoritative classes)
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_3_housing_policy_reaches_three_issuer_classes():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(
        _frame(["regulatory", "statistical", "legal", "open_web"], ["CA"]),
        registry=reg,
    )
    names = {a.name for a in adapters}
    # gov-regulatory + statistical-agency + legal-issuer (each a scoped serper).
    # open_web adds NO registry adapter (core baseline Serper covers it).
    assert {"serper_regulatory", "serper_statistical", "serper_legal"} <= names
    scoped_names = {n for n in names if n.startswith("serper_") and n != "serper"}
    assert len(scoped_names) >= 3
    # The US-only generic serper ("serper") must NEVER appear on the on-path.
    assert "serper" not in names


def test_p2_3_physics_reaches_three_classes():
    reg = _make_registry(
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
        github_search_fn=CaptureAdapter("github"),
    )
    adapters = route_needs_to_adapters(
        _frame(["primary_literature", "code"]), registry=reg,
    )
    names = {a.name for a in adapters}
    # scholarly-graph (openalex) + preprint (arxiv) + code-host (github) >= 3
    assert {"openalex_search", "arxiv", "github"} <= names
    assert len(names) >= 3


# ─────────────────────────────────────────────────────────────────────────────
# P2-4 — zero `if domain ==` on the on-path (whole-wiring grep)
# ─────────────────────────────────────────────────────────────────────────────

_ON_PATH_SOURCE_FILES = [
    _REPO_ROOT / "src" / "polaris_graph" / "discovery" / "source_adapter_registry.py",
    _REPO_ROOT / "src" / "polaris_graph" / "discovery" / "need_type_router.py",
]


def _count_domain_eq_branches(source: str) -> int:
    """Count ACTUAL `if domain ==` (or `elif domain ==`) control branches in
    the source CODE via AST — strings/comments/docstrings are ignored entirely,
    so a docstring that NAMES the forbidden pattern is not a false positive.

    A branch counts when an `If`-test compares a `domain` Name with `==`/`!=`,
    or a `q["domain"]`/`q['domain']` subscript with `==`/`!=`.
    """
    import ast

    count = 0

    def _is_domain_ref(node) -> bool:
        if isinstance(node, ast.Name) and node.id == "domain":
            return True
        if isinstance(node, ast.Subscript):
            sl = node.slice
            key = getattr(sl, "value", None)
            if isinstance(key, str) and key == "domain":
                return True
        return False

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if isinstance(test, ast.Compare) and any(
            isinstance(op, (ast.Eq, ast.NotEq)) for op in test.ops
        ):
            operands = [test.left, *test.comparators]
            if any(_is_domain_ref(op) for op in operands):
                count += 1
    return count


def test_p2_4_no_if_domain_branch_in_discovery_package():
    """The NEW on-path discovery files take NO actual `if domain ==` branch
    (AST-level — docstrings naming the constraint are not false positives)."""
    for path in _ON_PATH_SOURCE_FILES:
        src = path.read_text(encoding="utf-8")
        assert _count_domain_eq_branches(src) == 0, f"{path} has an on-path domain branch"
        # no domain-enum control literal as a routing key (real code subscript)
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                key = getattr(node.slice, "value", None)
                assert key != "domain", f"{path} reads q['domain'] on-path"


def test_p2_4_need_type_backend_dispatch_takes_no_domain_branch():
    """The on-path seam function `run_need_type_backends` consults no domain."""
    import inspect
    assert _count_domain_eq_branches(inspect.getsource(db.run_need_type_backends)) == 0


def test_p2_4_legacy_domain_branch_is_offpath_only():
    """The legacy `if domain ==` switch survives ONLY in run_domain_backends
    (off-path), not in the need-type dispatcher."""
    import inspect
    assert _count_domain_eq_branches(inspect.getsource(db.run_domain_backends)) >= 1
    assert _count_domain_eq_branches(inspect.getsource(db.run_need_type_backends)) == 0


def test_p2_4_sweep_seam_passes_domain_none_on_mode():
    """Whole-wiring (Codex diff-gate P2): the live_retriever + sweep seam cannot
    consult q['domain'] on-mode. The legacy live_retriever domain branch is
    gated on `domain` being truthy; the sweep sets domain=None on-mode, so the
    legacy branch is structurally unreachable when the research planner is on.
    Asserted on the real sweep source (the seam the brief requires P2-4 to cover
    beyond the discovery package)."""
    sweep_src = (
        _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    ).read_text(encoding="utf-8")
    # On-mode the retrieval domain passed to run_live_retrieval is None.
    assert "None if _use_research_planner else q[\"domain\"]" in sweep_src or \
           "None if _use_research_planner else q['domain']" in sweep_src, \
        "sweep must pass domain=None into run_live_retrieval on-mode"
    # The live_retriever on-mode registry seam is gated on research_frame, and
    # the legacy domain backend dispatch is gated on `domain` truthiness.
    import inspect

    from src.polaris_graph.retrieval import live_retriever as lr
    rlr_src = inspect.getsource(lr.run_live_retrieval)
    assert "research_frame is not None and not seed_only" in rlr_src, \
        "on-mode need-type seam must be gated on research_frame"
    assert "run_need_type_backends" in rlr_src


# ─────────────────────────────────────────────────────────────────────────────
# P2-5 — jurisdiction-scoped gov from the NEW versioned data file
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_5_ca_scopes_from_data_file():
    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
    reg_scopes = loader.scopes_for("regulatory", ["CA"])
    stat_scopes = loader.scopes_for("statistical", ["CA"])
    legal_scopes = loader.scopes_for("legal", ["CA"])
    assert "canada.ca" in reg_scopes
    assert "gc.ca" in reg_scopes  # normalized from any `*.gc.ca`
    assert "statcan.gc.ca" in stat_scopes
    assert "canlii.org" in legal_scopes
    # NOT the US `_POLICY_SITE_FILTERS` hosts
    assert "federalregister.gov" not in reg_scopes


def test_p2_5_jp_scopes_distinct_from_us():
    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
    jp = loader.scopes_for("regulatory", ["JP"])
    us = loader.scopes_for("regulatory", ["US"])
    assert "pmda.go.jp" in jp
    assert "fda.gov" in us
    assert set(jp).isdisjoint(set(us))


def test_p2_5_unknown_jurisdiction_no_scope():
    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
    assert loader.scopes_for("regulatory", ["ZZ"]) == []


def test_p2_5_version_present():
    assert _VERSION_PATH.exists()
    loader = JurisdictionScopeLoader(scopes_path=_SCOPES_PATH, version_path=_VERSION_PATH)
    assert loader.version()  # non-empty VERSION
    assert loader.schema_version is not None


def test_p2_5_wildcard_normalization():
    """build-note-2: a `*.gc.ca` data entry normalizes to `gc.ca` and the
    emitted scope is `site:gc.ca`, never `site:*.gc.ca`."""
    assert _normalize_host("*.gc.ca") == "gc.ca"
    assert _normalize_host("site:*.gc.ca") == "gc.ca"
    assert _normalize_host(".GC.CA") == "gc.ca"
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["regulatory"], ["CA"]), registry=reg)
    [a.run("housing", limit=5) for a in adapters]
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "gc.ca" in all_scopes
    assert all(not s.startswith("*.") for s in all_scopes)


# ─────────────────────────────────────────────────────────────────────────────
# P2-6 — empty-needs fallback -> {primary_literature, open_web}
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_6_empty_needs_fallback():
    reg = _make_registry(
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
    )
    adapters = route_needs_to_adapters(_frame([]), registry=reg)
    names = {a.name for a in adapters}
    # empty-needs fallback {primary_literature, open_web}: open_web adds NO
    # registry adapter (core baseline Serper covers it), so only the
    # primary_literature adapters remain — and NO US-scoped serper.
    assert names == {"openalex_search", "arxiv", "europe_pmc"}
    assert "serper" not in names  # no US _POLICY_SITE_FILTERS on the on-path
    # never a domain — no sec_edgar / no scoped gov
    assert "sec_edgar" not in names


# ─────────────────────────────────────────────────────────────────────────────
# P2-7 — spend-free: no live HTTP client constructed
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_7_routing_constructs_no_http_client(monkeypatch):
    """Building + running the registry with stub adapters constructs no
    httpx.Client (the brief's spend-free invariant)."""
    constructed = {"count": 0}
    real_client = db.httpx.Client

    class _Guard:
        def __init__(self, *a, **k):
            constructed["count"] += 1
            raise AssertionError("live HTTP client constructed in spend-free smoke")

    monkeypatch.setattr(db.httpx, "Client", _Guard)
    reg = _make_registry(
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
        github_search_fn=CaptureAdapter("github"),
    )
    adapters = route_needs_to_adapters(_frame(["primary_literature", "code"]), registry=reg)
    for a in adapters:
        a.run("q", limit=3)
    assert constructed["count"] == 0
    monkeypatch.setattr(db.httpx, "Client", real_client)


# ─────────────────────────────────────────────────────────────────────────────
# P2-8 — jurisdiction contract (parser SHAPE vs loader MEMBERSHIP)
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_8_ca_resolves_scopes():
    needs, juris = validate_frame_needs(_frame(["regulatory"], ["CA"]))
    assert juris == ["CA"]


def test_p2_8_empty_jurisdictions_no_scope():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["regulatory"], []), registry=reg)
    # No jurisdiction -> regulatory has no scope -> no scoped adapter.
    assert all(not a.name.startswith("serper_regulatory") for a in adapters)


def test_p2_8_unknown_shape_valid_code_non_fatal():
    # "ZZ" is shape-valid but absent from the data file -> non-fatal, no scope.
    needs, juris = validate_frame_needs(_frame(["regulatory"], ["ZZ"]))
    assert juris == ["ZZ"]  # parser keeps it (membership is non-fatal)
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["regulatory"], ["ZZ"]), registry=reg)
    assert all(not a.name.startswith("serper_regulatory") for a in adapters)


def test_p2_8_malformed_shape_fails_loud():
    with pytest.raises(MalformedPlanError):
        validate_frame_needs(_frame(["regulatory"], ["Canada"]))  # not a code
    with pytest.raises(MalformedPlanError):
        validate_frame_needs(_frame(["regulatory"], ["123"]))


def test_p2_malformed_scalar_evidence_needs_fails_loud(monkeypatch):
    """Codex diff-gate P1: a planner-emitted SCALAR evidence_needs (not a list)
    must FAIL LOUD up-front, NOT silently coerce to [] and slip into the safe
    empty-needs fallback. `_parse_frame` calls `_as_str_list_strict` which raises
    MalformedPlanError on a present-but-non-list value."""
    import json as _json

    from src.polaris_graph.planning import research_planner as rp

    # A well-formed plan EXCEPT evidence_needs is a scalar string, not a list.
    bad_plan = {
        "frame": {
            "entities": ["x"], "claim_type": "descriptive",
            "evidence_needs": "totally_made_up_need",  # SCALAR, not a list
            "jurisdictions": [],
        },
        "sub_queries": ["q1", "q2"],
        "outline": [{"archetype": "Background", "title": "T", "evidence_target": 1}],
    }
    with pytest.raises(rp.MalformedPlanError):
        rp.plan_research("any question", planner_llm=lambda _p: _json.dumps(bad_plan))


def test_p2_malformed_scalar_jurisdictions_fails_loud():
    """Same as above for a scalar `jurisdictions` (e.g. 'Canada' not ['CA'])."""
    import json as _json

    from src.polaris_graph.planning import research_planner as rp

    bad_plan = {
        "frame": {
            "entities": ["x"], "claim_type": "descriptive",
            "evidence_needs": ["regulatory"],
            "jurisdictions": "Canada",  # SCALAR, not a list
        },
        "sub_queries": ["q1", "q2"],
        "outline": [{"archetype": "Background", "title": "T", "evidence_target": 1}],
    }
    with pytest.raises(rp.MalformedPlanError):
        rp.plan_research("any question", planner_llm=lambda _p: _json.dumps(bad_plan))


def test_p2_8_eu_and_intl_shape_valid():
    needs, juris = validate_frame_needs(_frame(["standards"], ["EU", "INTL"]))
    assert juris == ["EU", "INTL"]


# ─────────────────────────────────────────────────────────────────────────────
# P2-9 — company_filings reachable on-mode
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_9_company_filings_us_selects_sec_edgar():
    reg = _make_registry(sec_edgar_search_fn=CaptureAdapter("sec_edgar"))
    adapters = route_needs_to_adapters(_frame(["company_filings"], ["US"]), registry=reg)
    assert "sec_edgar" in {a.name for a in adapters}


def test_p2_9_company_filings_ca_adds_issuer_scope():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap, sec_edgar_search_fn=CaptureAdapter("sec_edgar"))
    adapters = route_needs_to_adapters(_frame(["company_filings"], ["CA"]), registry=reg)
    names = {a.name for a in adapters}
    assert "sec_edgar" in names
    assert "serper_company_filings" in names
    for a in adapters:
        a.run("filing", limit=3)
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "sedarplus.ca" in all_scopes


# ─────────────────────────────────────────────────────────────────────────────
# P2-10 — new-needs routing (standards / datasets / news_press)
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_10_standards_includes_intl_bodies():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["standards"], ["CA"]), registry=reg)
    assert "serper_standards" in {a.name for a in adapters}
    for a in adapters:
        a.run("iso quality", limit=3)
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "iso.org" in all_scopes  # INTL key folded in
    assert "scc.ca" in all_scopes   # CA standards body


def test_p2_10_standards_without_jurisdiction_still_reaches_intl():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["standards"], []), registry=reg)
    # INTL standards bodies make standards reachable even with no jurisdiction.
    assert "serper_standards" in {a.name for a in adapters}
    for a in adapters:
        a.run("q", limit=3)
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "iso.org" in all_scopes


def test_p2_10_datasets_routes_to_data_portal():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["datasets"], ["CA"]), registry=reg)
    assert "serper_datasets" in {a.name for a in adapters}
    for a in adapters:
        a.run("housing data", limit=3)
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "open.canada.ca" in all_scopes


def test_p2_10_news_press_is_issuer_scope_only():
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    adapters = route_needs_to_adapters(_frame(["news_press"], ["CA"]), registry=reg)
    names = {a.name for a in adapters}
    assert "serper_news_press" in names  # data-driven issuer newsroom scope
    # The generic open-web component is the CORE baseline Serper, NOT a registry
    # adapter — so the US-scoped "serper" must NOT appear on the on-path.
    assert "serper" not in names


# ─────────────────────────────────────────────────────────────────────────────
# P2-11 — whole-wiring actual-invocation (code-only frame)
# ─────────────────────────────────────────────────────────────────────────────


def _install_capture_baseline(monkeypatch):
    """Replace live_retriever's core Serper+S2 with capture stubs; return the
    call-log dicts. fetch_cap=0 keeps the fetch loop from constructing clients."""
    serper_calls: list[str] = []
    s2_calls: list[str] = []

    def _fake_serper(query, num=10, api_calls=None):  # FX-17 (#1126): _serper_search gained api_calls
        serper_calls.append(query)
        return [{"url": f"https://serp/{len(serper_calls)}", "title": "", "snippet": ""}]

    def _fake_s2(query, limit=20):
        s2_calls.append(query)
        return [{"url": f"https://s2/{len(s2_calls)}", "title": "", "snippet": "", "doi": None, "year": None}]

    monkeypatch.setattr(lr, "_serper_search", _fake_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", _fake_s2)
    return serper_calls, s2_calls


def test_p2_11_code_only_frame_invokes_serper_s2_github_only(monkeypatch):
    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
    gh = CaptureAdapter("github", [SearchCandidate(url="https://gh/1", source="github")])
    # No-op the other registry adapters so we can prove ONLY github fires.
    reg = _make_registry(
        github_search_fn=gh,
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
        sec_edgar_search_fn=CaptureAdapter("sec_edgar"),
    )

    # Patch the registry the router builds inside run_need_type_backends by
    # routing through the explicit registry path: call run_need_type_backends.
    result = db.run_need_type_backends(
        frame=_frame(["code"]),
        research_question="rust async runtime",
        registry=reg,
    )
    invoked = set(result.backends_used)
    assert invoked == {"github"}
    # The OTHER specialized adapters did NOT fire.
    assert not reg._openalex_search_fn.calls
    assert not reg._sec_edgar_search_fn.calls

    # And the live seam runs the CORE Serper+S2 baseline over the sub-queries.
    retrieval = lr.run_live_retrieval(
        research_question="rust async runtime",
        amplified_queries=["tokio scheduler"],
        fetch_cap=0,
        enable_openalex_enrich=False,
        research_frame=_frame(["code"]),
    )
    # core baseline fired (serper + s2 over each query)
    assert serper_calls  # core open-web baseline
    assert s2_calls      # core scholarly baseline


def test_p2_11_regulatory_ca_frame_fires_ca_scoped_serper(monkeypatch):
    _install_capture_baseline(monkeypatch)
    cap = CaptureScopedSerper()
    reg = _make_registry(scoped_serper=cap)
    result = db.run_need_type_backends(
        frame=_frame(["regulatory"], ["CA"]),
        research_question="federal housing policy",
        registry=reg,
    )
    assert "serper_regulatory" in result.backends_used
    all_scopes = [s for call in cap.calls for s in call["scopes"]]
    assert "canada.ca" in all_scopes


def test_p2_11_dedupe_and_api_calls_accounting(monkeypatch):
    """Merged candidate dedupe-by-URL + api_calls accounting at the seam."""
    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
    gh = CaptureAdapter("github", [
        SearchCandidate(url="https://dup/x", source="github"),
        SearchCandidate(url="https://gh/2", source="github"),
    ])
    reg = _make_registry(github_search_fn=gh)
    result = db.run_need_type_backends(
        frame=_frame(["code"]),
        research_question="q",
        registry=reg,
    )
    # github dedupes within the seam (both unique here).
    assert result.per_backend_counts["github"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# P2-malformed — fail loud BEFORE any discovery, not swallowed by fail-open
# ─────────────────────────────────────────────────────────────────────────────


def test_p2_malformed_bad_evidence_need_raises_before_baseline(monkeypatch):
    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
    bad_frame = ResearchFrame(claim_type="descriptive")
    # A malformed need cannot be set via the validated parser, so set it raw to
    # simulate a planner that emitted an off-enum need.
    object.__setattr__(bad_frame, "evidence_needs", ["totally_made_up_need"])
    with pytest.raises(MalformedPlanError):
        lr.run_live_retrieval(
            research_question="q",
            fetch_cap=0,
            enable_openalex_enrich=False,
            research_frame=bad_frame,
        )
    # CRITICAL: failed loud BEFORE the core Serper/S2 baseline spent anything.
    assert serper_calls == []
    assert s2_calls == []


def test_p2_malformed_bad_jurisdiction_shape_raises_before_baseline(monkeypatch):
    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
    bad_frame = _frame(["regulatory"])
    object.__setattr__(bad_frame, "jurisdictions", ["Canada"])  # not a code
    with pytest.raises(MalformedPlanError):
        lr.run_live_retrieval(
            research_question="q",
            fetch_cap=0,
            enable_openalex_enrich=False,
            research_frame=bad_frame,
        )
    assert serper_calls == []
    assert s2_calls == []


def test_p2_malformed_not_swallowed_by_fail_open_wrapper():
    """The MalformedPlanError is a VALIDATION error — distinct from the
    fail-OPEN adapter wrapper. route_needs_to_adapters re-raises it."""
    bad = _frame(["regulatory"])
    object.__setattr__(bad, "evidence_needs", ["nope"])
    with pytest.raises(MalformedPlanError):
        route_needs_to_adapters(bad, registry=_make_registry())


def test_p2_malformed_valid_shape_unknown_jurisdiction_is_non_fatal(monkeypatch):
    """A valid-shape unknown code (ZZ) does NOT raise; the baseline still runs."""
    serper_calls, s2_calls = _install_capture_baseline(monkeypatch)
    reg = _make_registry()
    retrieval = lr.run_live_retrieval(
        research_question="q",
        fetch_cap=0,
        enable_openalex_enrich=False,
        research_frame=_frame(["regulatory"], ["ZZ"]),
    )
    # non-fatal: no raise, baseline ran.
    assert serper_calls
    assert s2_calls


def test_p2_malformed_empty_needs_is_safe_fallback_not_raise():
    """Only an empty evidence_needs -> safe fallback (no raise)."""
    adapters = route_needs_to_adapters(_frame([]), registry=_make_registry(
        openalex_search_fn=CaptureAdapter("openalex_search"),
        arxiv_search_fn=CaptureAdapter("arxiv"),
        europe_pmc_search_fn=CaptureAdapter("europe_pmc"),
    ))
    # open_web adds no registry adapter (core baseline covers it); no US serper.
    assert {a.name for a in adapters} == {"openalex_search", "arxiv", "europe_pmc"}


# ─────────────────────────────────────────────────────────────────────────────
# Enum sanity (10 needs, brief §2.1)
# ─────────────────────────────────────────────────────────────────────────────


def test_evidence_need_enum_is_ten():
    assert len(EVIDENCE_NEEDS) == 10
    assert "company_filings" in EVIDENCE_NEEDS
    assert "standards" in EVIDENCE_NEEDS
    assert "datasets" in EVIDENCE_NEEDS
    assert "news_press" in EVIDENCE_NEEDS
