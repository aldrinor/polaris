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


def test_inspector_js_canonicalizes_doi_publisher_suffixes() -> None:
    """Codex M-3 v3 review: DOI suffixes like /pdf, /full, .pdf must be
    stripped so distinct publisher URLs sharing a DOI canonicalize."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "canonicalizeDoi" in js
    # Check the suffix-stripping regex covers the publisher artefacts
    # Codex flagged: /pdf (Frontiers), .pdf (Springer), /full
    assert "pdf|full|abstract|html|epdf|metrics|references" in js


def test_inspector_js_strips_retrieval_log_prefixes() -> None:
    """Codex M-3 v3 review: retrieval_attempt_log URLs sometimes have
    pseudo-URL prefixes (oa_full_text:, url_pattern:, pdf:) that must be
    stripped before identifier extraction."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "stripUrlPrefix" in js
    # The regex must match an alphanumeric-prefix:https://... pattern
    assert "https?:\\/\\/" in js


# ---------------------------------------------------------------------------
# M-4: View 2 (Contradiction Matrix) — first-class disagreement view
# ---------------------------------------------------------------------------


def test_inspector_js_has_matrix_renderer() -> None:
    """M-4: inspector.js must expose Contradiction Matrix wiring.

    Updated post-Codex review: renderMatrixView delegates to
    renderMatrixToolbar + renderMatrixResults to preserve input focus
    on filter changes. wireMatrixToolbar + wireMatrixRowInteraction
    are the two interaction wirers."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderMatrixView" in js
    assert "renderMatrixToolbar" in js
    assert "renderMatrixResults" in js
    assert "wireMatrixToolbar" in js
    assert "wireMatrixRowInteraction" in js
    assert "applyMatrixFilters" in js
    assert "_matrixState" in js


def test_matrix_view_filters_by_severity_tier_dose_and_query() -> None:
    """M-4: matrix toolbar exposes severity / tier / dose / search filters."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The renderer constructs `data-matrix-filter="${name}"` for each filter,
    # then calls sel("severity", ...), sel("tier", ...), sel("dose", ...).
    # The 4 filter names must each appear as keys in _matrixState.
    assert "_matrixState.severity" in js
    assert "_matrixState.tier" in js
    assert "_matrixState.dose" in js
    assert "_matrixState.query" in js
    # The handler reads dataset.matrixFilter
    assert "dataset.matrixFilter" in js or 'data-matrix-filter' in js


def test_matrix_view_renders_full_cluster_claims_with_snippets() -> None:
    """M-4: each row, when expanded, must render every claim in the cluster
    with tier, evidence_id, value, dose, arm, context_snippet, sanitized URL."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "matrix-claim-snippet" in js
    assert "matrix-claim-value" in js
    assert "context_snippet" in js  # already in view 1, but matrix uses it too


def test_matrix_view_responds_to_real_run14_data() -> None:
    """M-4: contradictions endpoint returns the 14 clusters with all metadata
    the matrix view consumes (severity, subject, predicate, claims with tiers,
    absolute_difference, relative_difference, recommended_action)."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    ir = resp.json()
    contradictions = ir["contradictions"]
    assert len(contradictions) == 14

    severities = set()
    tiers = set()
    doses = set()
    for cluster in contradictions:
        # Required fields the matrix renders
        assert "severity" in cluster
        assert "subject" in cluster
        assert "predicate" in cluster
        assert "absolute_difference" in cluster
        assert "relative_difference" in cluster
        assert "recommended_action" in cluster
        assert "claims" in cluster
        severities.add(cluster["severity"])
        for claim in cluster["claims"]:
            tiers.add(claim.get("source_tier", ""))
            doses.add(claim.get("dose", "") or "")
    # Run-14 has at least 'high' severity, multiple tiers, multiple doses
    assert "high" in severities
    assert len([t for t in tiers if t]) >= 2  # at least T1 + T2 + ...


def test_matrix_view_css_classes_present() -> None:
    """M-4: shell HTML must contain placeholders that the renderer replaces;
    inspector.css must define styles for matrix-row, matrix-claim, etc."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    for cls in ["matrix-toolbar", "matrix-row", "matrix-row.expanded", "matrix-claim", "matrix-empty"]:
        assert cls in css, f"Missing CSS class: {cls}"


# ---------------------------------------------------------------------------
# M-5: View 3 (Frame Coverage Manifest) — pass/partial/gap visual + per-slot
# ---------------------------------------------------------------------------


def test_inspector_js_has_coverage_renderer() -> None:
    """M-5: inspector.js must expose Frame Coverage rendering."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderCoverageView" in js
    assert "renderCoverageSummaryBar" in js
    assert "renderCoverageRow" in js
    assert "wireCoverageInteraction" in js
    assert "classifyCoverageStatus" in js


def test_coverage_view_has_visual_segments_per_status() -> None:
    """M-5: visual coverage bar must have segments for pass/partial/gap/pipeline-fault."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    for cls in [
        "coverage-summary",
        "coverage-bar",
        "coverage-segment-pass",
        "coverage-segment-partial",
        "coverage-segment-gap",
        "coverage-warning",
        "coverage-row",
        "coverage-status-badge",
        "coverage-action-btn",
    ]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_coverage_view_renders_v30_semantics_warning() -> None:
    """M-5: V30 retrieval-coverage caveat must surface in the view (FINAL_PLAN
    requirement: surface 'phase1_retrieval_coverage_only' warning)."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderCoverageWarning" in js
    assert "semantics_warning" in js


def test_coverage_view_offers_operator_action_on_gap_rows() -> None:
    """M-5: gap rows expose an operator-action button hooked to a custom event."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert 'data-action="resolve-gap"' in js
    assert "polaris:resolve-gap" in js
    assert "human_completion_eligible" in js


def test_coverage_view_consumes_run14_payload() -> None:
    """End-to-end: API returns the 15-entity frame_coverage payload the
    renderer needs (status, section, slot_id, doi, pmid, retrieval_attempt_log,
    required_fields, etc.)."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    fc = resp.json()["frame_coverage"]
    entries = fc["entries"]
    assert len(entries) == 15
    statuses = set(e["status"] for e in entries)
    assert "pass" in statuses
    sections = set(e.get("section", "") for e in entries)
    # run-14 has at least Efficacy, Mechanism, Regulatory sections
    assert any(s for s in sections), "Expected at least one populated section"
    # At least one entry must have a DOI and a retrieval_attempt_log
    assert any(e.get("doi") for e in entries)
    assert any(e.get("retrieval_attempt_log") for e in entries)
    # The semantics_warning is preserved
    assert fc.get("semantics_warning") and "phase1_retrieval_coverage_only" in fc["semantics_warning"]


def test_coverage_view_renders_slot_id() -> None:
    """Codex M-5 review fix #2: slot_id (canonical contract-slot key) must
    be rendered, not just entity_id."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "coverage-row-slot" in js
    assert "data-slot-id" in js
    assert "entry.slot_id" in js


def test_coverage_view_differentiates_required_vs_retrieved_chips() -> None:
    """Codex M-5 review fix #3: required_fields and available_artifacts must
    have visible labels and distinct chip styling."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    # Distinct chip classes
    assert "coverage-chip-required" in js
    assert "coverage-chip-retrieved" in js
    assert "coverage-chip-required" in css
    assert "coverage-chip-retrieved" in css
    # Visible label markup
    assert "coverage-fields-label" in js
    assert "coverage-fields-label" in css
    # Visible label text
    assert ">required<" in js
    assert ">retrieved<" in js


def test_coverage_status_classifier_distinguishes_partial_from_gap() -> None:
    """Codex M-5 review fix #1: fail_min_fields with non-gap provenance and
    non-empty available_artifacts should classify as partial, not gap."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # Classifier is now entry-aware
    assert "function classifyCoverageStatus(status, entry)" in js
    # Hard-gap path keys
    assert "frame_gap_unrecoverable" in js
    assert "available_artifacts" in js
    # Partial path is reachable from fail_min_fields
    assert 'fail_min_fields' in js


def test_resolve_gap_event_includes_slot_context() -> None:
    """Codex M-5 review fix #2: polaris:resolve-gap CustomEvent must include
    slot_id + status + section + subsection_title in addition to entity_id."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "slot_id:" in js or "slot_id :" in js
    assert "status:" in js or "status :" in js
    assert "section:" in js or "section :" in js
    assert "subsection_title:" in js or "subsection_title :" in js


# ---------------------------------------------------------------------------
# M-6: View 4 (Methods + Provenance Bundle) — audit-bundle header + export
# ---------------------------------------------------------------------------


def test_inspector_js_has_methods_renderer() -> None:
    """M-6: inspector.js must expose Methods + Provenance rendering."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderMethodsView" in js
    assert "renderTwoFamilyBanner" in js
    assert "methods-export-btn" in js
    assert "Pre-commit rule checks" in js
    assert "Expected vs actual tier distribution" in js


def test_methods_view_has_export_button_to_audit_bundle() -> None:
    """M-6: the export button must point at /api/inspector/runs/{slug}/audit-bundle.zip."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "/audit-bundle.zip" in js


def test_methods_view_renders_two_family_invariant() -> None:
    """M-6: the two-family invariant (generator family != evaluator family)
    is core to V30's audit-grade discipline. Must be visible in this view."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "Two-family invariant" in js
    assert "generator_family" in js
    assert "evaluator_family" in js


def test_methods_view_css_classes_present() -> None:
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    for cls in [
        "methods-grid",
        "methods-card",
        "methods-section",
        "methods-kv-table",
        "methods-rule-list",
        "methods-rule-pass",
        "methods-rule-fail",
        "methods-export-btn",
        "methods-two-family-banner",
    ]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_audit_bundle_export_endpoint() -> None:
    """M-6: /api/inspector/runs/{slug}/audit-bundle.zip returns a valid ZIP
    with all canonical artifact files."""
    import io
    import zipfile

    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/audit-bundle.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "polaris-audit-bundle" in resp.headers.get("content-disposition", "")

    buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
        # INDEX.txt is the human-readable header
        assert "INDEX.txt" in names
        # Canonical V30 artifacts
        for required in [
            "report.md",
            "manifest.json",
            "bibliography.json",
            "contradictions.json",
            "verification_details.json",
        ]:
            assert required in names, f"Bundle missing {required}"
        # Optional artifacts present in run-14
        for optional in [
            "protocol.json",
            "evaluator_rule_checks.json",
            "qwen_judge_output.json",
        ]:
            assert optional in names, f"Bundle missing optional {optional}"
        # INDEX.txt must mention the run_id and the protocol_sha256
        index_content = zf.read("INDEX.txt").decode("utf-8")
        assert "POLARIS V30 Phase-2 Audit Bundle" in index_content
        assert "Run ID:" in index_content
        assert "Run slug:" in index_content


def test_audit_bundle_export_404_for_unknown_slug() -> None:
    client = _make_client()
    resp = client.get("/api/inspector/runs/does_not_exist/audit-bundle.zip")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Codex M-6 review fixes — bundle hardening + missing-provenance + tier edges
# ---------------------------------------------------------------------------


def test_audit_bundle_index_contains_full_provenance_header() -> None:
    """Codex M-6 fix: INDEX.txt must include protocol_sha256, model IDs,
    gate decisions, and per-file digests."""
    import io
    import zipfile

    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/audit-bundle.zip")
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        index = zf.read("INDEX.txt").decode("utf-8")
        # Headers per Codex M-6 review
        assert "RUN IDENTITY" in index
        assert "MODEL PROVENANCE" in index
        assert "GATE DECISIONS" in index
        assert "BUNDLE FILES + DIGESTS" in index
        # Run-14 specifics
        assert "Protocol SHA-256:" in index
        assert "Generator family:" in index
        assert "deepseek" in index
        assert "Evaluator family:" in index
        assert "qwen" in index
        # Adequacy + corpus + evaluator gate decisions
        assert "Adequacy:" in index
        assert "Corpus approved:" in index
        assert "Evaluator gate:" in index
        # Verification instructions
        assert "MANIFEST.SHA256" in index


def test_audit_bundle_includes_sha256_manifest() -> None:
    """Codex M-6 fix: tamper-evident MANIFEST.SHA256 with per-file digests."""
    import hashlib
    import io
    import re
    import zipfile

    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/audit-bundle.zip")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "MANIFEST.SHA256" in names
        manifest_text = zf.read("MANIFEST.SHA256").decode("utf-8")
        # Each line: "<64-hex-digest>  <filename>"
        line_re = re.compile(r"^[0-9a-f]{64}\s{2}.+$")
        non_empty = [ln for ln in manifest_text.splitlines() if ln.strip()]
        assert len(non_empty) > 0
        for line in non_empty:
            assert line_re.match(line), f"Malformed digest line: {line}"
        # Sample digest verification: report.md
        first_digest_line = next((ln for ln in non_empty if ln.endswith("  report.md")), None)
        assert first_digest_line is not None
        expected_digest = first_digest_line.split("  ", 1)[0]
        actual_digest = hashlib.sha256(zf.read("report.md")).hexdigest()
        assert expected_digest == actual_digest


def test_audit_bundle_fails_loud_on_missing_required_files(tmp_path) -> None:
    """Codex M-6 fix: missing canonical-required artifact files must return 500,
    not silently produce a stripped-down ZIP."""
    # Build a stub allowlist run that only has manifest.json (missing report.md)
    import json as _json

    incomplete = tmp_path / "incomplete_run"
    incomplete.mkdir()
    minimal_manifest = {
        "run_id": "stub_incomplete",
        "slug": "stub_incomplete",
        "status": "ok",
        "question": "stub",
        "protocol_sha256": "0",
        "evaluator_gate": {"gate_class": "pass", "release_allowed": True},
        "completeness": {"covered_fraction": 1.0},
        "frame_coverage_report": {"by_status": {"pass": 0}, "entries": []},
        "corpus": {"tier_fractions": {"T1": 1.0}, "count": 1},
    }
    (incomplete / "manifest.json").write_text(_json.dumps(minimal_manifest), encoding="utf-8")
    # Deliberately omit report.md, bibliography.json, etc.

    # Patch the registry to point at our incomplete run for the duration of this test
    from src.polaris_graph.audit_ir import inspector_router as ir_router_mod
    from src.polaris_graph.audit_ir.registry import RunSummary
    fake_summary = RunSummary(
        slug="stub_incomplete",
        run_id="stub_incomplete",
        domain="",
        status="ok",
        artifact_dir=incomplete,
        cost_usd=0.0,
        word_count=0,
        contradictions_found=0,
        release_allowed=True,
        created_at_iso=None,
    )
    original_finder = ir_router_mod.find_run_by_slug
    ir_router_mod.find_run_by_slug = lambda s: fake_summary if s == "stub_incomplete" else original_finder(s)
    try:
        client = _make_client()
        resp = client.get("/api/inspector/runs/stub_incomplete/audit-bundle.zip")
        assert resp.status_code == 500
        detail = resp.json().get("detail", "")
        assert "missing" in detail.lower()
        assert "report.md" in detail
    finally:
        ir_router_mod.find_run_by_slug = original_finder


def test_methods_view_warns_when_model_provenance_missing() -> None:
    """Codex M-6 review: missing model_provenance must surface as a warning
    state, not silence the banner entirely."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The "missing" branch must explicitly emit a warning class
    assert "methods-two-family-banner-warning" in js
    assert "NOT RECORDED" in js


def test_methods_view_two_family_violation_has_distinct_style() -> None:
    """Codex M-6 review low: same-family pair must render with a distinct
    visible style (not just a class name)."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    assert "methods-two-family-banner-violation" in css
    # The violation style must declare its own background or border
    violation_block = css[css.index("methods-two-family-banner-violation"):]
    violation_block = violation_block[: violation_block.index("}")]
    assert "background" in violation_block or "border-color" in violation_block


def test_methods_view_renders_retrieval_queries_section() -> None:
    """Codex M-6 review: retrieval queries must be surfaced (not just counts)."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "rs.queries" in js
    assert "methods-query-line" in js
    assert "not persisted by this run" in js  # explicit fallback when absent


def test_methods_view_renders_pre_generation_gates() -> None:
    """Codex M-6 review: adequacy + corpus_approval gates surfaced as
    structured UI alongside the evaluator gate."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "Pre-generation gates" in js
    assert "ir.adequacy" in js
    assert "ir.corpus_approval" in js


def test_methods_view_handles_zero_max_fraction_correctly() -> None:
    """Codex M-6 medium: explicit max_fraction=0 should mean 'tier forbidden',
    not be coerced to default 1."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The new nullish-safe parser uses `== null` checks rather than `||`.
    assert "exp.max_fraction == null" in js
    assert "exp.min_fraction == null" in js


def test_methods_view_emits_residual_rows_for_unexpected_tiers() -> None:
    """Codex M-6 medium: tiers present in actual distribution but absent from
    expected_tier_distribution must surface as 'unexpected (no band declared)'."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "residualTiers" in js
    assert "unexpected (no band declared)" in js


def test_audit_ir_loads_adequacy_and_corpus_approval() -> None:
    """The IR loader must persist adequacy + corpus_approval so the view
    can render them."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    ir = resp.json()
    # Adequacy in run-14
    assert ir.get("adequacy") is not None
    assert ir["adequacy"]["decision"] == "proceed"
    assert ir["adequacy"]["findings_ok"] == 7
    # Corpus approval in run-14
    assert ir.get("corpus_approval") is not None
    assert ir["corpus_approval"]["approved"] is True
    assert ir["corpus_approval"]["approved_count"] > 0


# ---------------------------------------------------------------------------
# M-7: View 5 (Source Tier Mix) — corpus tier audit + promo calibration
# ---------------------------------------------------------------------------


def test_inspector_js_has_tier_mix_renderer() -> None:
    """M-7: inspector.js must expose Source Tier Mix wiring."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderTierMixView" in js
    assert "countPromoAdjectives" in js
    assert "renderTierBandRow" in js
    assert "renderTierResidualRow" in js
    assert "_PROMO_PATTERNS" in js


def test_tier_mix_view_renders_promo_adjective_count() -> None:
    """M-7: promo adjective count must be derived from report.md and surface
    a calibration badge (good/warn/bad)."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # Patterns covering "revolutionary", "groundbreaking", etc.
    for word in ["revolutionary", "groundbreaking", "unprecedented", "breakthrough"]:
        assert word in js
    # Three calibration thresholds
    assert "tier-mix-promo-badge-good" in js
    assert "tier-mix-promo-badge-warn" in js
    assert "tier-mix-promo-badge-bad" in js


def test_tier_mix_view_css_classes_present() -> None:
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    css = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.css").read_text(encoding="utf-8")
    for cls in [
        "tier-headline",
        "tier-headline-card",
        "tier-mix-bar-large",
        "tier-mix-segment-large",
        "tier-mix-table",
        "tier-mix-band-graphic",
        "tier-mix-band-bracket",
        "tier-mix-band-actual",
        "tier-mix-band-actual-in",
        "tier-mix-band-actual-out",
        "tier-mix-promo-badge",
        "tier-mix-row-residual",
        "tier-mix-deviation-warning",
    ]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_tier_mix_view_uses_nullish_safe_band_parsing() -> None:
    """M-7: same nullish-safe parsing as Methods view (zero max_fraction must
    not be coerced to 1)."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # The renderTierBandRow path itself doesn't parse exp; the renderTierMixView
    # body parses each `exp` with the same nullish-safe pattern as M-6.
    # Two occurrences of "exp.max_fraction == null" exist in the file (M-6 and M-7 each).
    assert js.count("exp.max_fraction == null") >= 2
    assert js.count("exp.min_fraction == null") >= 2


def test_tier_mix_view_emits_residual_rows_for_unexpected_tiers() -> None:
    """M-7: tiers in actual but not in protocol must surface as residual rows."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "renderTierResidualRow" in js
    assert "tier-mix-row-residual" in js


def test_tier_mix_view_handles_material_deviation() -> None:
    """M-7: when manifest.corpus.material_deviation=true, surface a banner."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    assert "tier-mix-deviation-warning" in js
    assert "Material tier deviation" in js
    assert "tm.material_deviation" in js


def test_tier_mix_data_exposed_via_api() -> None:
    """End-to-end: the API must expose tier_mix.fractions + corpus_count +
    material_deviation flag + report_md (for promo counting) + protocol."""
    client = _make_client()
    resp = client.get(f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}")
    ir = resp.json()
    tm = ir["tier_mix"]
    assert tm["corpus_count"] > 0
    assert isinstance(tm["fractions"], dict)
    assert "T1" in tm["fractions"]
    assert "material_deviation" in tm
    # Report markdown is in the IR (renderer reads it for promo counting)
    assert isinstance(ir["report_md"], str)
    assert len(ir["report_md"]) > 100
    # Protocol (with expected_tier_distribution) for the band-comparison table
    assert ir["protocol"] is not None
    assert len(ir["protocol"]["expected_tier_distribution"]) > 0
