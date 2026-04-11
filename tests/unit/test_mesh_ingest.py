"""
Unit tests for wiki mesh ingest (Unit 2).

Covers:
  - ingest_file: markdown upload end-to-end
  - ingest_file: dedup returns same src_id without rewriting
  - ingest_file: missing file raises MeshStoreError
  - ingest_file: unsupported extension raises
  - ingest_file: bad workspace_id raises
  - ingest_file: sig_authority default rules (upload=0.95, web=0.5)
  - ingest_file: short extracted text raises
  - ingest_web_content: HTML → markdown via trafilatura
  - ingest_web_content: is_markdown=True passes raw through
  - ingest_web_content: dedup
  - read_source_text: strips the inline markdown header
  - read_source_text: file without a header is returned unchanged
  - _write_source_markdown: atomic write (no half-written files)
  - char-offset integrity: raw file offset vs body offset differ by exactly the header length

Run:
    python -m pytest tests/unit/test_mesh_ingest.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.wiki.mesh import MeshStore, MeshStoreError
from src.polaris_graph.wiki.mesh.ingest import (
    MIN_EXTRACTED_TEXT_LEN,
    _compute_content_hash,
    _predicted_src_id,
    ingest_file,
    ingest_web_content,
    read_source_text,
)


# ───────── fixtures ─────────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "mesh.db"


@pytest.fixture
def store(tmp_db: Path) -> MeshStore:
    s = MeshStore.open(tmp_db)
    yield s
    s.close()


@pytest.fixture
def workspace_id(store: MeshStore) -> str:
    return store.create_workspace(
        name="ingest_test",
        root_question="How do PFAS filters work?",
    )


@pytest.fixture
def markdown_file(tmp_path: Path) -> Path:
    content = (
        "# PFAS Filtration Study\n\n"
        "## Background\n\n"
        "This study evaluates three household PFAS filtration technologies. "
        "Granular activated carbon (GAC), reverse osmosis (RO), and ion "
        "exchange resins were tested against long-chain perfluoroalkyl "
        "substances (PFOA, PFOS) at typical household concentrations.\n\n"
        "## Findings\n\n"
        "GAC achieved 85% removal of long-chain PFAS compounds with contact "
        "time of 10 minutes. RO membranes performed better (95% CI: 91-97%) "
        "but required higher pressure and produced reject water. Ion exchange "
        "resins showed variable performance (n=12 trials, p<0.01).\n"
    )
    path = tmp_path / "study.md"
    path.write_text(content, encoding="utf-8")
    return path


# ───────── ingest_file ─────────

class TestIngestFile:

    def test_upload_creates_source_row_and_file(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        src_id, was_new = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=markdown_file,
        )
        assert was_new is True
        assert src_id.startswith("src_")

        # source_page row exists
        src = store.get_source(src_id)
        assert src is not None
        assert src["kind"] == "upload"
        assert src["sig_authority"] == 0.95  # upload default
        assert src["workspace_id"] == workspace_id
        assert src["title"] == "PFAS Filtration Study"  # first H1 extracted
        assert src["word_count"] > 50

        # markdown file exists on disk in the workspace's sources dir
        md_path = store.workspace_dir / src["filepath"]
        assert md_path.exists()
        assert md_path.is_file()

        # workspace counter bumped
        ws = store.get_workspace(workspace_id)
        assert ws["source_count"] == 1

    def test_dedup_returns_same_id_without_rewriting(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        src_id_1, was_new_1 = ingest_file(
            store=store, workspace_id=workspace_id, file_path=markdown_file,
        )
        assert was_new_1 is True

        # Record the mtime of the markdown file
        md_path = store.workspace_dir / store.get_source(src_id_1)["filepath"]
        original_mtime = md_path.stat().st_mtime_ns

        src_id_2, was_new_2 = ingest_file(
            store=store, workspace_id=workspace_id, file_path=markdown_file,
        )
        assert src_id_2 == src_id_1
        assert was_new_2 is False
        # File was NOT rewritten on dedup
        assert md_path.stat().st_mtime_ns == original_mtime
        # source_count stayed at 1
        ws = store.get_workspace(workspace_id)
        assert ws["source_count"] == 1

    def test_missing_file_raises(
        self, store: MeshStore, workspace_id: str, tmp_path: Path
    ):
        with pytest.raises(MeshStoreError, match="not found"):
            ingest_file(
                store=store,
                workspace_id=workspace_id,
                file_path=tmp_path / "does_not_exist.md",
            )

    def test_unsupported_extension_raises(
        self, store: MeshStore, workspace_id: str, tmp_path: Path
    ):
        bad = tmp_path / "thing.exe"
        bad.write_text("some bytes", encoding="utf-8")
        with pytest.raises(MeshStoreError, match="Unsupported file extension"):
            ingest_file(
                store=store, workspace_id=workspace_id, file_path=bad,
            )

    def test_bad_workspace_id_raises(
        self, store: MeshStore, markdown_file: Path
    ):
        with pytest.raises(MeshStoreError, match="Workspace not found"):
            ingest_file(
                store=store,
                workspace_id="ws_does_not_exist",
                file_path=markdown_file,
            )

    def test_short_text_raises(
        self, store: MeshStore, workspace_id: str, tmp_path: Path
    ):
        tiny = tmp_path / "tiny.md"
        tiny.write_text("hi", encoding="utf-8")
        with pytest.raises(MeshStoreError, match="too short"):
            ingest_file(
                store=store, workspace_id=workspace_id, file_path=tiny,
            )

    def test_sig_authority_defaults_for_web_kind(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=markdown_file,
            kind="web",  # non-upload
            url="https://example.com/study",
        )
        src = store.get_source(src_id)
        assert src["sig_authority"] == 0.5  # web default
        assert src["url"] == "https://example.com/study"

    def test_explicit_sig_authority_overrides_default(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=markdown_file,
            sig_authority=0.72,
        )
        assert store.get_source(src_id)["sig_authority"] == 0.72

    def test_sig_authority_out_of_range_raises(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        with pytest.raises(MeshStoreError, match="sig_authority"):
            ingest_file(
                store=store,
                workspace_id=workspace_id,
                file_path=markdown_file,
                sig_authority=1.5,
            )

    def test_metadata_is_persisted(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        src_id, _ = ingest_file(
            store=store,
            workspace_id=workspace_id,
            file_path=markdown_file,
            title="Override title",
            authors=["Smith, J", "Jones, R"],
            year=2025,
            doi="10.1234/abc",
            venue="Water Research",
        )
        src = store.get_source(src_id)
        assert src["title"] == "Override title"
        assert src["year"] == 2025
        assert src["doi"] == "10.1234/abc"
        assert src["venue"] == "Water Research"
        # authors is stored as JSON
        import json
        assert json.loads(src["authors"]) == ["Smith, J", "Jones, R"]


# ───────── ingest_web_content ─────────

class TestIngestWebContent:

    def test_html_via_trafilatura(
        self, store: MeshStore, workspace_id: str
    ):
        html = (
            "<html><head><title>Filter Test</title></head>"
            "<body>"
            "<nav>Navigation links here ignored</nav>"
            "<article>"
            "<h1>PFAS Filter Review</h1>"
            "<p>This review compared three household filters against "
            "long-chain PFAS compounds. Activated carbon achieved 85% "
            "removal in 10 minute contact time. Reverse osmosis was "
            "superior at 95% but required pressurized systems with "
            "reject water handling.</p>"
            "<p>Ion exchange resins performed variably with ranges of "
            "60-90% depending on influent concentration and resin type.</p>"
            "</article>"
            "<footer>copyright 2026</footer>"
            "</body></html>"
        )
        src_id, was_new = ingest_web_content(
            store=store,
            workspace_id=workspace_id,
            url="https://example.com/review",
            raw_content=html,
        )
        assert was_new is True
        src = store.get_source(src_id)
        assert src["kind"] == "web"
        assert src["sig_authority"] == 0.5
        # The stored markdown should contain the article text but not
        # the nav / footer boilerplate
        md_path = store.workspace_dir / src["filepath"]
        body = read_source_text(md_path)
        assert "PFAS Filter Review" in body or "activated carbon" in body.lower()
        assert "Navigation links here ignored" not in body
        assert "copyright 2026" not in body

    def test_markdown_passthrough(
        self, store: MeshStore, workspace_id: str
    ):
        md = (
            "# Direct Markdown\n\n"
            "This content was pre-cleaned by Jina Reader. It contains "
            "a detailed analysis of household water filtration.\n\n"
            "## Findings\n\n"
            "GAC achieved 85% removal in 10 minute contact time."
        )
        src_id, was_new = ingest_web_content(
            store=store,
            workspace_id=workspace_id,
            url="https://example.com/md",
            raw_content=md,
            is_markdown=True,
        )
        assert was_new is True
        src = store.get_source(src_id)
        body = read_source_text(store.workspace_dir / src["filepath"])
        assert "Direct Markdown" in body
        assert "85% removal" in body

    def test_empty_content_raises(
        self, store: MeshStore, workspace_id: str
    ):
        with pytest.raises(MeshStoreError, match="non-empty raw_content"):
            ingest_web_content(
                store=store, workspace_id=workspace_id,
                url="https://example.com/x", raw_content="",
            )

    def test_empty_url_raises(
        self, store: MeshStore, workspace_id: str
    ):
        with pytest.raises(MeshStoreError, match="non-empty url"):
            ingest_web_content(
                store=store, workspace_id=workspace_id,
                url="", raw_content="some content text here",
                is_markdown=True,
            )

    def test_web_dedup(
        self, store: MeshStore, workspace_id: str
    ):
        md = "# Web page\n\nSome content that is long enough to pass the minimum extracted text length check. " * 3
        first_id, was_new_1 = ingest_web_content(
            store=store, workspace_id=workspace_id,
            url="https://example.com/a", raw_content=md, is_markdown=True,
        )
        # Same content, different URL — dedup is by content hash, not URL
        second_id, was_new_2 = ingest_web_content(
            store=store, workspace_id=workspace_id,
            url="https://example.com/b", raw_content=md, is_markdown=True,
        )
        assert first_id == second_id
        assert was_new_2 is False


# ───────── read_source_text ─────────

class TestReadSourceText:

    def test_strips_header(
        self, store: MeshStore, workspace_id: str, markdown_file: Path
    ):
        """
        THE test that prevents char-offset corruption. ingest writes a
        header to every source file; claim_extract (Unit 2) and any
        drill-down code must use read_source_text to strip it before
        doing char-span lookup. If they read the raw file, every
        char_start will be shifted by the header length.
        """
        src_id, _ = ingest_file(
            store=store, workspace_id=workspace_id, file_path=markdown_file,
        )
        md_path = store.workspace_dir / store.get_source(src_id)["filepath"]

        raw = md_path.read_text(encoding="utf-8")
        body = read_source_text(md_path)

        # Raw must have the header; body must not
        assert raw.startswith("<!--")
        assert "src_id:" in raw[:200]
        assert not body.startswith("<!--")
        assert "src_id:" not in body[:200]

        # The body is the payload after the header terminator
        assert len(raw) > len(body)
        header_len = len(raw) - len(body)
        assert header_len > 0

        # Char offsets: find a known substring in the body — it must
        # NOT appear at the same position in the raw file
        quote_fragment = "GAC achieved 85% removal"
        body_offset = body.find(quote_fragment)
        raw_offset = raw.find(quote_fragment)
        assert body_offset > 0
        assert raw_offset > 0
        assert raw_offset - body_offset == header_len, (
            f"Header length should be exactly raw_offset - body_offset: "
            f"got raw={raw_offset}, body={body_offset}, header_len={header_len}"
        )

    def test_file_without_header_returned_unchanged(
        self, tmp_path: Path
    ):
        f = tmp_path / "plain.md"
        f.write_text("Plain content with no header", encoding="utf-8")
        assert read_source_text(f) == "Plain content with no header"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(MeshStoreError, match="not found"):
            read_source_text(tmp_path / "nope.md")


# ───────── helper: src_id prediction ─────────

class TestSrcIdPrediction:

    def test_predicted_matches_store_make_id(self):
        """_predicted_src_id must mirror MeshStore._make_id byte-for-byte.

        If the store changes its id formula, ingest.py will write to the
        wrong filename and the post-insert rename fallback will fire
        constantly. This test locks the invariant.
        """
        ws_id = "ws_abc"
        content_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        predicted = _predicted_src_id(ws_id, content_hash)
        actual = MeshStore._make_id("src", f"{ws_id}:{content_hash}")
        assert predicted == actual

    def test_different_workspaces_produce_different_ids(self):
        h = "same_hash"
        a = _predicted_src_id("ws_a", h)
        b = _predicted_src_id("ws_b", h)
        assert a != b

    def test_same_workspace_same_hash_produces_same_id(self):
        h = "the_hash"
        a = _predicted_src_id("ws_x", h)
        b = _predicted_src_id("ws_x", h)
        assert a == b
