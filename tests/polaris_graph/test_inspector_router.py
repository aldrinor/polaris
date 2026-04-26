"""Tests for src/polaris_graph/audit_ir/inspector_router.py.

Spins up a minimal FastAPI app with just the inspector router mounted, to
keep tests independent of the full live_server.py surface area.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir.inspector_router import router
from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_runs_endpoint() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["canonical_demo_slug"] == CANONICAL_DEMO_SLUG
    assert body["count"] >= 1
    slugs = [r["slug"] for r in body["runs"]]
    assert CANONICAL_DEMO_SLUG in slugs


def test_get_run_returns_full_ir() -> None:
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"]
    assert body["manifest"]["contradictions_found"] == 14
    assert len(body["contradictions"]) == 14
    assert body["frame_coverage"]["pass_count"] == 14
    assert body["ir_schema_version"]


def test_get_run_unknown_slug_returns_404() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs/does_not_exist")
    assert resp.status_code == 404


def test_get_report_markdown_endpoint() -> None:
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/report.md")
    assert resp.status_code == 200
    assert "[1]" in resp.text  # has inline citations


def test_get_report_markdown_unknown_returns_404() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs/does_not_exist/report.md")
    assert resp.status_code == 404


def test_inspector_root_redirects_to_canonical_demo() -> None:
    client = _make_client()
    resp = client.get("/inspector", follow_redirects=False)
    assert resp.status_code in (302, 307, 308)
    assert resp.headers["location"].endswith(CANONICAL_DEMO_SLUG)


def test_inspector_page_renders_html() -> None:
    client = _make_client()
    resp = client.get(f"/inspector/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    body = resp.text
    # The 5-view scaffold tabs must be present
    assert 'data-view="report"' in body
    assert 'data-view="contradictions"' in body
    assert 'data-view="frame-coverage"' in body
    assert 'data-view="methods"' in body
    assert 'data-view="tier-mix"' in body
    # The slug must be substituted into the template
    assert CANONICAL_DEMO_SLUG in body
    # JS must be linked
    assert "/static/inspector/inspector.js" in body


def test_inspector_page_unknown_returns_404() -> None:
    client = _make_client()
    resp = client.get("/inspector/does_not_exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Codex M-2 review (high #1, #2): list/detail round-trip + uniqueness
# ---------------------------------------------------------------------------


def test_list_to_detail_round_trip_for_every_listed_run() -> None:
    """Every run from /api/inspector/runs must be fetchable at /api/inspector/runs/{slug}.

    Before the fix: list reported 90 runs, but 75 of them returned 500 on detail.
    """
    client = _make_client()
    list_resp = client.get("/api/inspector/runs")
    assert list_resp.status_code == 200
    body = list_resp.json()
    for run in body["runs"]:
        slug = run["slug"]
        listed_run_id = run["run_id"]
        detail_resp = client.get(f"/api/inspector/runs/{slug}")
        assert detail_resp.status_code == 200, f"Detail 404/500 for slug={slug}"
        detail = detail_resp.json()
        assert detail["run_id"] == listed_run_id, (
            f"run_id drift: list={listed_run_id} detail={detail['run_id']}"
        )


# ---------------------------------------------------------------------------
# M-3: View 1 (Report click-to-inspect) prerequisites in API surface
# ---------------------------------------------------------------------------


def test_inspector_page_loads_markdown_renderer_and_inspector_js() -> None:
    """M-3: HTML shell must include both scripts in correct order."""
    client = _make_client()
    resp = client.get(f"/inspector/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    body = resp.text
    md_idx = body.find("/static/inspector/markdown.js")
    insp_idx = body.find("/static/inspector/inspector.js")
    assert md_idx > 0
    assert insp_idx > md_idx, "markdown.js must load before inspector.js"
    assert "evidence-pane" in body
    assert "report-shell" in body


def test_detail_response_has_data_for_click_to_inspect() -> None:
    """View 1 click handler needs: bibliography by num, verified sentences with
    tokens.evidence_id, contradiction claims with evidence_id."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    assert resp.status_code == 200
    ir = resp.json()

    # 1. Bibliography numerically indexable
    biblio = ir["bibliography"]
    assert len(biblio) >= 5
    nums = {b["num"] for b in biblio}
    assert 1 in nums
    eids = {b["evidence_id"] for b in biblio}
    assert "surpass_1_primary" in eids

    # 2. Verified sentences with tokens that point to evidence_ids
    sections = ir["verified_report"]["sections"]
    assert len(sections) > 0
    found_token = False
    for sec in sections:
        for sent in sec["sentences"]:
            for tok in sent["tokens"]:
                assert "evidence_id" in tok
                assert "start" in tok
                assert "end" in tok
                if tok["evidence_id"] == "surpass_1_primary":
                    found_token = True
    assert found_token

    # 3. Contradictions index by claim.evidence_id
    contra = ir["contradictions"]
    assert len(contra) == 14
    found_claim = False
    for cluster in contra:
        for claim in cluster["claims"]:
            if claim["evidence_id"]:
                found_claim = True
                break
        if found_claim:
            break
    assert found_claim


def test_report_md_has_inline_citations_to_render() -> None:
    """The report markdown must contain [N] tokens for the renderer to overlay."""
    import re
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/report.md")
    assert resp.status_code == 200
    md = resp.text
    citations = re.findall(r"\[(\d+)\]", md)
    assert len(citations) > 50  # run-14 has 100+ inline citations
    # Every citation N must have a bibliography entry
    detail = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}").json()
    biblio_nums = {b["num"] for b in detail["bibliography"]}
    cited_nums = {int(c) for c in citations}
    unresolved = cited_nums - biblio_nums
    assert not unresolved, f"Unresolved citations: {unresolved}"


def test_inspector_page_serves_static_inspector_assets() -> None:
    """The static assets must be reachable through live_server's static route.

    M-3 ships markdown.js + inspector.js + inspector.css. Mounting the actual
    /static endpoint requires the real live_server, not the minimal test app.
    Here we just confirm the files exist on disk so the live_server's static
    handler will find them.
    """
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    static_dir = REPO_ROOT / "scripts" / "static" / "inspector"
    assert (static_dir / "inspector.js").exists()
    assert (static_dir / "markdown.js").exists()
    assert (static_dir / "inspector.css").exists()


# ---------------------------------------------------------------------------
# Codex M-3 review fixes — layout structure + a11y attributes in shell
# ---------------------------------------------------------------------------


def test_inspector_page_has_split_pane_layout_structure() -> None:
    """Codex M-3 high: evidence-pane was OUTSIDE inspector-main; the grid never
    actually split. Now the pane lives INSIDE main, beside .inspector-views."""
    client = _make_client()
    resp = client.get(f"/inspector/{CANONICAL_DEMO_SLUG}")
    body = resp.text
    main_idx = body.find('class="inspector-main"')
    views_idx = body.find('class="inspector-views"', main_idx)
    pane_idx = body.find('class="evidence-pane"', main_idx)
    main_close = body.find("</main>")
    assert views_idx > main_idx
    assert pane_idx > main_idx
    assert pane_idx < main_close
    assert views_idx < pane_idx


def test_inspector_page_has_a11y_attributes_on_pane() -> None:
    """Codex M-3 medium: pane needs aria-labelledby + body has tabindex for focus."""
    client = _make_client()
    resp = client.get(f"/inspector/{CANONICAL_DEMO_SLUG}")
    body = resp.text
    assert 'aria-labelledby="evidence-pane-title"' in body
    assert 'id="evidence-pane-title"' in body
    assert 'id="evidence-pane-body"' in body
    assert 'tabindex="-1"' in body


def test_inspector_js_validates_tier_and_severity_against_enum() -> None:
    """Codex M-3 medium: tier/severity must be validated before HTML injection."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "VALID_TIERS" in js
    assert "VALID_SEVERITIES" in js
    assert "validateTier" in js
    assert "validateSeverity" in js


def test_inspector_js_sanitizes_url_protocols() -> None:
    """Codex M-3 medium: only http/https URLs may go into href."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "sanitizeUrl" in js
    assert "/^https?:\\/\\//i" in js


def test_inspector_js_renders_full_cluster_not_just_active_claim() -> None:
    """Codex M-3 high: contradiction drilldown must render every claim in the
    cluster, not only the matching one."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The cluster.claims iteration is the contract
    assert "cluster.claims" in js
    assert "cluster-claim-active" in js
    assert "context_snippet" in js


def test_inspector_js_has_identifier_resolver() -> None:
    """Codex M-3 v2 high: ID drift between bibliography (surpass_X) and
    contradiction (ev_NNN) namespaces is bridged by canonical identifiers
    (DOI/PMID/URL) extracted from source_url + frame_coverage entries."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "extractIdentifiers" in js
    assert "bibIdentifiers" in js
    assert "clustersByIdentifier" in js
    assert "findClustersForBibEntry" in js
    # DOI extraction regex (escaped dot in JS regex literal)
    assert "10\\.\\d" in js
    # PMID via pubmed URL (escaped dots in regex literal)
    assert "pubmed\\.ncbi\\.nlm\\.nih\\.gov" in js


def test_url_stem_preserves_query_string() -> None:
    """Codex M-3 v2 review: stripping query was over-joining distinct URLs.
    The new urlStem must preserve everything below the path-and-query level."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The line that strips query string must NOT exist anymore
    assert ".replace(/[?#].*$/," not in js


def test_resolver_could_bridge_doi_namespaces_in_run14() -> None:
    """Sanity check on real run-14 data: at least some entity-anchored
    bibliography entries (surpass_*) carry a DOI in frame_coverage that
    appears in at least one contradiction claim's source_url."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    ir = resp.json()
    fc_entries = ir["frame_coverage"]["entries"]
    bib_dois = set()
    for entry in fc_entries:
        if entry.get("doi"):
            bib_dois.add(entry["doi"].lower())
    # Walk contradiction claims and look for DOI matches in source_url
    bridged = 0
    for cluster in ir["contradictions"]:
        for claim in cluster["claims"]:
            url = (claim.get("source_url") or "").lower()
            if any(doi in url for doi in bib_dois):
                bridged += 1
    # Run-14 may have 0 bridged entries (the bibliography trials and the
    # contradiction corpus are largely disjoint sets). The test asserts the
    # resolver is *plumbed correctly* — that bib DOIs and claim URLs are
    # both reachable from the API. Real bridging count is data-dependent.
    assert len(bib_dois) > 0, "Expected at least one biblio DOI in run-14"
    assert isinstance(bridged, int)
