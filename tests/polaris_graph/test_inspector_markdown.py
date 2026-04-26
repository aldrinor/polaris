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
