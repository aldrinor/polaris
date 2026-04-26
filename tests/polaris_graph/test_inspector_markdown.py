"""Tests for scripts/static/inspector/markdown.js — runs JS through Node.

The inspector renders markdown client-side because the server only exposes
report.md raw. We verify the JS renderer directly so the citation overlay
contract is locked.

Skipped if `node` is not on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

NODE_BIN = shutil.which("node")
SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "static" / "inspector"
MARKDOWN_JS = SCRIPT_DIR / "markdown.js"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_inline_citation() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("Sentence with citation [3].");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert '<a class="citation" data-num="3"' in out
    assert "[3]" in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_consecutive_citations() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("Multiple sources [19][20] cite this.");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    # Both citations must be replaced with separate clickable elements
    assert 'data-num="19"' in out
    assert 'data-num="20"' in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_table() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const md = "| Trial | N | Ref |\\n|---|---|---|\\n| SURPASS-1 | 478 | [1] |";
        const out = window.PolarisMarkdown.render(md);
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "<table>" in out
    assert "<thead>" in out
    assert "<th>Trial</th>" in out
    assert 'data-num="1"' in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_headings() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("# Title\\n\\n### Subtitle\\n\\nBody.");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "<h1>Title</h1>" in out
    assert "<h3>Subtitle</h3>" in out
    assert "<p>Body.</p>" in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_escapes_html_in_text() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("Sentence with <script>alert(1)</script> tags.");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_bullet_list() -> None:
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("- alpha\\n- beta with [4]\\n- gamma");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "<ul>" in out
    assert "<li>alpha</li>" in out
    assert 'data-num="4"' in out


# ---------------------------------------------------------------------------
# Codex M-3 review fixes
# ---------------------------------------------------------------------------


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_horizontal_rule() -> None:
    """Codex M-3 review low: --- separator must render as <hr>, not literal text."""
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const out = window.PolarisMarkdown.render("Before.\\n\\n---\\n\\nAfter.");
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "<hr>" in out
    # The literal "---" must NOT appear as paragraph text
    assert "<p>---</p>" not in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_markdown_js_renders_adjacent_tables_without_blank_line() -> None:
    """Codex M-3 review medium: adjacent tables must not bleed into each other."""
    js = textwrap.dedent(
        """
        const window = {};
        require(%s);
        const md = "| A | B |\\n|---|---|\\n| 1 | 2 |\\n| C | D |\\n|---|---|\\n| 3 | 4 |";
        const out = window.PolarisMarkdown.render(md);
        console.log(out);
        """
        % repr(str(MARKDOWN_JS).replace("\\", "/"))
    )
    res = subprocess.run(
        [NODE_BIN, "-e", js], capture_output=True, text=True, timeout=15
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout
    # Two distinct tables, not one merged table
    assert out.count("<table>") == 2
    assert "<th>A</th>" in out
    assert "<th>C</th>" in out


# ---------------------------------------------------------------------------
# Codex M-3 v3 review: identifier resolver canonicalization tests
# ---------------------------------------------------------------------------

INSPECTOR_JS = SCRIPT_DIR / "inspector.js"


def _build_resolver_test_harness(test_body: str) -> str:
    """Wrap test body in a harness that exposes resolver helpers from inspector.js.

    inspector.js wraps everything in an IIFE so its helpers aren't visible to
    require(). The harness re-implements the helper functions inline by
    splicing them out of the source.
    """
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const src = fs.readFileSync({repr(str(INSPECTOR_JS).replace(chr(92), '/'))}, 'utf8');
        // Splice helpers out of the IIFE for direct testing.
        const helperNames = ['stripUrlPrefix', 'canonicalizeDoi', 'extractIdentifiers', 'urlStem'];
        const exposed = {{}};
        helperNames.forEach((name) => {{
          const re = new RegExp('function ' + name + '\\\\b[\\\\s\\\\S]*?\\\\n  }}', 'm');
          const m = src.match(re);
          if (m) {{
            // eval the function in this scope so it captures stripUrlPrefix etc.
            eval(m[0]);
            exposed[name] = eval(name);
          }}
        }});
        const stripUrlPrefix = exposed.stripUrlPrefix;
        const canonicalizeDoi = exposed.canonicalizeDoi;
        const extractIdentifiers = exposed.extractIdentifiers;
        const urlStem = exposed.urlStem;
        {test_body}
        """
    )


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_doi_canonicalization_strips_pdf_suffix() -> None:
    """Frontiers: 10.3389/fphar.2022.998816/pdf -> 10.3389/fphar.2022.998816"""
    body = """
        const result = canonicalizeDoi('10.3389/fphar.2022.998816/pdf');
        console.log(result);
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_resolver_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "10.3389/fphar.2022.998816"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_doi_canonicalization_strips_dot_pdf() -> None:
    """Springer: 10.1007/s13300-023-01470-w.pdf -> 10.1007/s13300-023-01470-w"""
    body = """
        const result = canonicalizeDoi('10.1007/s13300-023-01470-w.pdf');
        console.log(result);
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_resolver_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "10.1007/s13300-023-01470-w"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_extract_identifiers_canonicalizes_doi_in_url() -> None:
    """Distinct publisher URLs sharing the same DOI should produce the same DOI key."""
    body = """
        const a = extractIdentifiers('https://www.frontiersin.org/articles/10.3389/fphar.2022.998816/pdf');
        const b = extractIdentifiers('https://doi.org/10.3389/fphar.2022.998816');
        const aDoi = Array.from(a).find((x) => x.startsWith('doi:'));
        const bDoi = Array.from(b).find((x) => x.startsWith('doi:'));
        console.log(JSON.stringify({a: aDoi, b: bDoi, equal: aDoi === bDoi}));
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_resolver_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.strip()
    assert '"equal":true' in out, f"Expected DOI canonicalization to match: {out}"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_strip_url_prefix_handles_oa_full_text() -> None:
    """Retrieval-log URLs prefixed with oa_full_text: must strip cleanly."""
    body = """
        const a = stripUrlPrefix('oa_full_text:https://example.com/paper.pdf');
        const b = stripUrlPrefix('url_pattern:https://example.com/paper');
        const c = stripUrlPrefix('https://example.com/paper');  // unprefixed pass-through
        console.log(JSON.stringify({a: a, b: b, c: c}));
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_resolver_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.strip()
    assert '"a":"https://example.com/paper.pdf"' in out
    assert '"b":"https://example.com/paper"' in out
    assert '"c":"https://example.com/paper"' in out


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_extract_identifiers_unwraps_oa_full_text_and_extracts_doi() -> None:
    """End-to-end: oa_full_text: prefix + DOI URL should yield the canonical DOI key."""
    body = """
        const ids = extractIdentifiers('oa_full_text:https://www.frontiersin.org/articles/10.3389/fphar.2022.998816/pdf');
        const doi = Array.from(ids).find((x) => x.startsWith('doi:'));
        console.log(doi || 'NONE');
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_resolver_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "doi:10.3389/fphar.2022.998816"


# ---------------------------------------------------------------------------
# Codex M-4 review: clusterMatchesQuery behavior tests
# ---------------------------------------------------------------------------


def _build_matrix_test_harness(test_body: str) -> str:
    """Splice clusterMatchesQuery + helpers out of inspector.js IIFE.

    Note: eval() inside a forEach callback creates locally-scoped bindings.
    To make helpers visible at the top level, we eval them at module scope
    via direct concatenation, then bind explicitly.
    """
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const src = fs.readFileSync({repr(str(INSPECTOR_JS).replace(chr(92), '/'))}, 'utf8');
        // VALID_TIERS / VALID_SEVERITIES used by validateTier/Severity
        const VALID_TIERS = new Set(['T1','T2','T3','T4','T5','T6','T7','UNKNOWN']);
        const VALID_SEVERITIES = new Set(['low','medium','high','critical','unknown']);
        // _matrixState used by applyMatrixFilters
        const _matrixState = {{ severity: 'all', tier: 'all', dose: 'all', query: '' }};
        const helperNames = [
          'validateTier', 'validateSeverity', 'uniqueSorted', 'clusterTiers',
          'clusterDoses', 'clusterMatchesQuery', 'applyMatrixFilters',
        ];
        let allSrc = '';
        helperNames.forEach((name) => {{
          const re = new RegExp('function ' + name + '\\\\b[\\\\s\\\\S]*?\\\\n  }}', 'm');
          const m = src.match(re);
          if (m) allSrc += m[0] + '\\n';
        }});
        // Eval all extracted helper sources together at top level so they
        // bind in this scope (forEach + eval would scope-trap them).
        eval(allSrc);
        {test_body}
        """
    )


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_cluster_matches_query_searches_all_visible_claim_fields() -> None:
    """Codex M-4 review: search must cover dose, arm, value, unit, source_tier."""
    body = """
        const cluster = {
            subject: 'tirzepatide',
            predicate: 'body weight',
            recommended_action: 'Disclose both values.',
            claims: [
                { evidence_id: 'ev_1', source_url: 'https://x.com/a', context_snippet: 'context here',
                  dose: '10 mg', arm: 'treatment', value: 25.3, unit: '%', source_tier: 'T1' },
            ],
        };
        const cases = [
            ['10 mg', true],
            ['treatment', true],
            ['25.3', true],
            ['T1', true],
            ['%', true],
            ['nonsense_string', false],
            ['', true],     // empty matches everything
            ['   ', true],  // whitespace trimmed -> empty -> matches
        ];
        cases.forEach(([q, expected]) => {
            const result = clusterMatchesQuery(cluster, q);
            console.log(JSON.stringify({q, expected, result, pass: result === expected}));
        });
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_matrix_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    for line in res.stdout.strip().splitlines():
        result = json.loads(line)
        assert result["pass"], f"clusterMatchesQuery failed for q={result['q']!r}: {result}"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_apply_matrix_filters_composes_severity_tier_dose_and_query() -> None:
    """AND-composition: severity AND tier AND dose AND query."""
    body = """
        const clusters = [
            { cluster_id: 0, severity: 'high', subject: 'x', predicate: 'body weight',
              claims: [{ evidence_id: 'a', source_tier: 'T1', dose: '10 mg', value: 5 }] },
            { cluster_id: 1, severity: 'low', subject: 'y', predicate: 'mortality',
              claims: [{ evidence_id: 'b', source_tier: 'T2', dose: '15 mg', value: 6 }] },
            { cluster_id: 2, severity: 'high', subject: 'z', predicate: 'mortality',
              claims: [{ evidence_id: 'c', source_tier: 'T1', dose: '15 mg', value: 7 }] },
        ];
        // 1. All filters = all -> all 3
        _matrixState.severity = 'all'; _matrixState.tier = 'all'; _matrixState.dose = 'all'; _matrixState.query = '';
        let r = applyMatrixFilters(clusters);
        console.log('all:' + r.length);
        // 2. severity=high
        _matrixState.severity = 'high';
        r = applyMatrixFilters(clusters);
        console.log('high:' + r.map((c)=>c.cluster_id).join(','));
        // 3. severity=high AND tier=T1 -> clusters 0 and 2
        _matrixState.tier = 'T1';
        r = applyMatrixFilters(clusters);
        console.log('high+T1:' + r.map((c)=>c.cluster_id).join(','));
        // 4. add dose=15 mg -> only cluster 2
        _matrixState.dose = '15 mg';
        r = applyMatrixFilters(clusters);
        console.log('high+T1+15mg:' + r.map((c)=>c.cluster_id).join(','));
        // 5. add query that doesn't match cluster 2
        _matrixState.query = 'nonsense';
        r = applyMatrixFilters(clusters);
        console.log('high+T1+15mg+nonsense:' + r.length);
    """
    res = subprocess.run(
        [NODE_BIN, "-e", _build_matrix_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    lines = res.stdout.strip().splitlines()
    assert "all:3" in lines
    assert "high:0,2" in lines
    assert "high+T1:0,2" in lines
    assert "high+T1+15mg:2" in lines
    assert "high+T1+15mg+nonsense:0" in lines


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_inspector_js_separates_toolbar_from_results_for_focus_retention() -> None:
    """Codex M-4 review: live search must not destroy the input on each
    keystroke. The toolbar and results are rendered by separate functions;
    only renderMatrixResults runs on filter change."""
    src = INSPECTOR_JS.read_text(encoding="utf-8")
    assert "renderMatrixToolbar" in src
    assert "renderMatrixResults" in src
    # The change handler calls renderMatrixResults, NOT renderMatrixView
    # (which would re-render the toolbar and destroy the focused input).
    assert "renderMatrixResults(ir)" in src
    # Wiring is split: wireMatrixToolbar + wireMatrixRowInteraction
    assert "wireMatrixToolbar" in src
    assert "wireMatrixRowInteraction" in src


# ---------------------------------------------------------------------------
# Codex M-7 review: promo calibration + band-marker edge cases
# ---------------------------------------------------------------------------


def _build_promo_test_harness(test_body: str) -> str:
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const src = fs.readFileSync({repr(str(INSPECTOR_JS).replace(chr(92), '/'))}, 'utf8');
        const helperNames = ['_stripTablesAndBibliography', 'countPromoAdjectives', '_bandMarkerLeftPct'];
        let allSrc = '';
        helperNames.forEach((name) => {{
          // Match function name (with leading underscore) up to closing brace.
          const escaped = name.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
          const re = new RegExp('function ' + escaped + '\\\\b[\\\\s\\\\S]*?\\\\n  }}', 'm');
          const m = src.match(re);
          if (m) allSrc += m[0] + '\\n';
        }});
        // _PROMO_PATTERNS is also inside the IIFE; extract it.
        const patRe = /const _PROMO_PATTERNS = \\[[\\s\\S]*?\\];/m;
        const patMatch = src.match(patRe);
        if (patMatch) allSrc += patMatch[0] + '\\n';
        eval(allSrc);
        {test_body}
        """
    )


def _run_promo_count_via_node(input_path: Path) -> int:
    """Run countPromoAdjectives over a file by reading it inside Node.

    Avoids Windows command-line length limits (long files embedded as JSON
    string literals exceed CreateProcess's 32K limit).
    """
    body = textwrap.dedent(
        f"""
        const fs2 = require('fs');
        const md = fs2.readFileSync({repr(str(input_path).replace(chr(92), '/'))}, 'utf8');
        const n = countPromoAdjectives(md);
        console.log(n);
        """
    )
    res = subprocess.run(
        [NODE_BIN, "-e", _build_promo_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr)
    return int(res.stdout.strip())


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_promo_count_is_exactly_one_for_run14() -> None:
    """Codex M-7 review: run-14 must give exactly 1 promo hit ("superior" in
    narrative prose), not 2 (the "superior" in the Trial Summary table row
    must be excluded by table-stripping)."""
    repo_root = Path(__file__).resolve().parents[2]
    run14 = repo_root / "outputs" / "full_scale_v30_phase2_run14" / "clinical" / "clinical_tirzepatide_t2dm" / "report.md"
    n = _run_promo_count_via_node(run14)
    assert n == 1, f"Expected 1 promo hit in run-14, got {n}"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_promo_count_for_gemini_comparator_is_at_least_50() -> None:
    """Codex M-7 review: comparator baseline must reproduce roughly 50+
    promo hits against state/compare_gemini_dr.txt to validate the
    'well-calibrated vs promotional drift' calibration story."""
    repo_root = Path(__file__).resolve().parents[2]
    cmp_path = repo_root / "state" / "compare_gemini_dr.txt"
    if not cmp_path.exists():
        pytest.skip("Gemini comparator file not available")
    n = _run_promo_count_via_node(cmp_path)
    # Calibrated lexicon should produce 50+ hits on Gemini; documented
    # FINAL_PLAN baseline is "1 vs 58" — we accept >= 50 as in-spec.
    assert n >= 50, f"Expected >= 50 promo hits in Gemini comparator, got {n}"


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_band_marker_clamps_to_visible_range() -> None:
    """Codex M-7 review: actual=0 → 0%, actual=1 → 99.5% (capped), actual>1 → 99.5%."""
    body = textwrap.dedent(
        """
        const cases = [
            [0, '0.00%'],
            [0.5, '50.00%'],
            [1, '99.50%'],
            [1.5, '99.50%'],   // clamped
            [-0.5, '0.00%'],   // clamped
        ];
        cases.forEach(([input, expected]) => {
            const out = _bandMarkerLeftPct(input);
            console.log(JSON.stringify({input, expected, out, pass: out === expected}));
        });
        """
    )
    res = subprocess.run(
        [NODE_BIN, "-e", _build_promo_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    for line in res.stdout.strip().splitlines():
        result = json.loads(line)
        assert result["pass"], f"Marker clamp failed: {result}"


def test_band_bracket_position_clamps_min_and_max() -> None:
    """Codex M-7 v2 review: bracket left/width must clamp BOTH minF and maxF
    to [0, 1] so malformed min_fraction>1 doesn't render at left:150%."""
    from src.polaris_graph.audit_ir.registry import REPO_ROOT
    js = (REPO_ROOT / "scripts" / "static" / "inspector" / "inspector.js").read_text(encoding="utf-8")
    # Both directions of clamp must be present in renderTierBandRow
    assert "Math.min(minF, 1)" in js
    assert "Math.min(maxF, 1)" in js
    # Width formula uses the clamped values, not raw maxF/minF
    assert "clampedMax - clampedMin" in js


@pytest.mark.skipif(NODE_BIN is None, reason="node not available")
def test_strip_tables_and_bibliography_removes_pipe_rows() -> None:
    """Codex M-7 review: promo counting must be narrative-only — table rows
    and bibliography sections must be stripped before scanning."""
    body = textwrap.dedent(
        """
        const md = "# Title\\n\\nThis is impressive narrative.\\n\\n| Trial | Note |\\n|---|---|\\n| X | impressive |\\n\\n## Bibliography\\n\\n[1] An impressive paper.";
        const stripped = _stripTablesAndBibliography(md);
        console.log(stripped);
        """
    )
    res = subprocess.run(
        [NODE_BIN, "-e", _build_promo_test_harness(body)],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stderr
    out = res.stdout.strip()
    # Narrative kept; table rows + biblio dropped
    assert "narrative" in out
    assert "| Trial" not in out
    assert "| X" not in out
    assert "An impressive paper" not in out
