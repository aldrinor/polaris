"""Tests for scripts/static/inspector/markdown.js — runs JS through Node.

The inspector renders markdown client-side because the server only exposes
report.md raw. We verify the JS renderer directly so the citation overlay
contract is locked.

Skipped if `node` is not on PATH.
"""

from __future__ import annotations

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
