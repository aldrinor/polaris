"""
Unit tests for wiki mesh claim extraction (Unit 2).

The parser (`_parse_batch_to_claims`) is a pure function and gets the
most coverage — it's where filtering, tier assignment, char-span lookup,
and has_numeric detection live. The orchestrator
(`extract_claims_from_source`) is tested once end-to-end with a mocked
LLM client to verify the transaction + store integration.

Covers:
  - Parser: the advisor's killer 5-fact test (GOLD, filtered×2, BRONZE, has_numeric)
  - Parser: short statement filter
  - Parser: short quote filter
  - Parser: URL fragment filter
  - Parser: cookie boilerplate filter
  - Parser: analyses for other source_urls are ignored
  - Parser: no matching source URL → empty result
  - Tier: all 4 branches of _assign_tier
  - Char span: quote found → correct body offsets
  - Char span: quote not found → sentinel (0, 1)
  - Has-numeric: 6 positive patterns + 1 negative
  - Orchestrator: LLM mock → claims inserted atomically
  - Orchestrator: missing source_page raises
  - Orchestrator: wrong workspace_id raises
  - Orchestrator: transaction rolls back if one claim insert fails

Run:
    python -m pytest tests/unit/test_mesh_claim_extract.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.polaris_graph.schemas import (
    AtomicFact,
    SourceAnalysis,
    SourceAnalysisBatch,
)
from src.polaris_graph.wiki.mesh import MeshStore, MeshStoreError
from src.polaris_graph.wiki.mesh.claim_extract import (
    _NUMERIC_PATTERN,
    _assign_tier,
    _locate_quote,
    _parse_batch_to_claims,
    extract_claims_from_source,
    UNVERIFIED_CHAR_START,
    UNVERIFIED_CHAR_END,
)
from src.polaris_graph.wiki.mesh.ingest import ingest_file


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
        name="extract_test",
        root_question="How do PFAS filters work?",
    )


# Body text we'll pretend was extracted from the source. Claims will
# try to locate substrings of this. Every quote used in the tests below
# must either (a) appear verbatim here so _locate_quote returns
# verified=True, or (b) deliberately not appear here to test the
# unverified-span path.
#
# PG_MIN_QUOTE_WORDS = 5 (lowered from 15 after preflight showed LLMs
# produce shorter quotes). Valid quotes must be 5+ words. We write
# long quotes for the positive tests and very short ones (<5 words)
# for the filter test.
SOURCE_BODY = (
    "This study evaluates household PFAS filtration approaches and "
    "methods. GAC achieved 85% removal of long-chain PFAS compounds in "
    "10 minute contact time across independent trials at typical "
    "residential concentrations over twelve months of observation. "
    "Reverse osmosis membranes performed better at 95% CI 91-97% but "
    "required pressurization and produced substantial reject water "
    "volumes during normal household operation cycles. Ion exchange "
    "resins showed variable performance with n=12 trials producing "
    "results from 60% to 90% removal efficiency, with statistical "
    "significance p<0.01 in the pooled analysis."
)
SOURCE_URL = "https://example.com/study"


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "study.md"
    path.write_text(SOURCE_BODY, encoding="utf-8")
    return path


def _build_batch(
    facts: list[dict],
    source_url: str = SOURCE_URL,
    source_quality: float = 0.7,
) -> SourceAnalysisBatch:
    """
    Build a SourceAnalysisBatch from a list of fact dicts.

    MUST go through `model_validate` with dict input — the batch's
    `filter_invalid_analyses` validator runs in `mode="before"` and
    expects `data["analyses"]` to be a list of dicts. If we pass
    pre-instantiated `SourceAnalysis` objects, the validator sees
    non-dict items, logs "dropped %d/%d analyses", and returns an
    empty batch. This is a production validator quirk we have to
    work around in tests — do NOT change it.
    """
    return SourceAnalysisBatch.model_validate({
        "analyses": [
            {
                "source_url": source_url,
                "source_title": "Test Study",
                "source_type": "journal_article",
                "source_quality": source_quality,
                "overall_relevance": 0.7,
                "atomic_facts": facts,
            }
        ]
    })


# ───────── the killer 5-fact parser test ─────────

class TestParserKillerTest:
    """
    The advisor's specific recommendation: one test that covers 6 code
    paths by running 5 different facts through the parser and verifying
    filter counts, tier assignments, has_numeric flags, and char spans.
    """

    def test_five_fact_integration(self):
        facts = [
            # Fact 1: GOLD — relevance 0.9, locatable verbatim quote (20 words),
            # source_quality 0.7 (batch default) → GOLD
            {
                "statement": "GAC achieved 85% removal of long-chain PFAS compounds in 10 minute contact time across independent trials",
                "direct_quote": "GAC achieved 85% removal of long-chain PFAS compounds in 10 minute contact time across independent trials at typical residential concentrations",
                "relevance_score": 0.9,
                "confidence": 0.9,
            },
            # Fact 2: FILTERED — quote too short (3 words < PG_MIN_QUOTE_WORDS=5)
            {
                "statement": "GAC removes PFAS compounds effectively from water",
                "direct_quote": "GAC removes PFAS",
                "relevance_score": 0.8,
                "confidence": 0.7,
            },
            # Fact 3: FILTERED — cookie boilerplate (18 words, passes length filter,
            # contains "cookies", "track the user", "advertising", "privacy policy")
            {
                "statement": "The site uses cookies to track user behavior for advertising and analytics",
                "direct_quote": "This site uses cookies to track the user across advertising services and our privacy policy applies to all visitors worldwide",
                "relevance_score": 0.5,
                "confidence": 0.5,
            },
            # Fact 4: BRONZE — relevance 0.3 (< 0.5), quote NOT in body → unverified,
            # tier rule: not GOLD, not SILVER (relevance < 0.5), → BRONZE
            {
                "statement": "An unrelated claim about solar panel efficiency in residential deployment",
                "direct_quote": "Solar panels typically generate approximately twelve to fifteen percent of a typical rooftop's maximum theoretical energy capacity under clear conditions",
                "relevance_score": 0.3,
                "confidence": 0.4,
            },
            # Fact 5: has_numeric=True — quote contains 95% CI AND is verbatim in body (17 words)
            {
                "statement": "Reverse osmosis membranes performed at 95% CI with narrow confidence intervals",
                "direct_quote": "Reverse osmosis membranes performed better at 95% CI 91-97% but required pressurization and produced substantial reject water volumes",
                "relevance_score": 0.85,
                "confidence": 0.9,
            },
        ]
        batch = _build_batch(facts)
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )

        # Expected: 3 claims survive (1, 4, 5) — 2 and 3 get filtered
        assert len(claims) == 3, f"Expected 3 claims, got {len(claims)}: {[c['statement'][:40] for c in claims]}"

        # Skip counts
        assert result.skipped["short_quote"] == 1
        assert result.skipped["cookie_text"] == 1
        assert result.skipped["short_statement"] == 0
        assert result.skipped["url_fragment"] == 0
        assert result.total_facts_seen == 5

        # Tiers in order:
        #   fact 1: relevance 0.9, source_quality 0.7, verified → GOLD
        #   fact 4: relevance 0.3, unverified → BRONZE
        #   fact 5: relevance 0.85, source_quality 0.7, verified → GOLD
        tiers = [c["tier"] for c in claims]
        assert tiers == ["GOLD", "BRONZE", "GOLD"], f"Tier mismatch: {tiers}"

        # has_numeric flags:
        #   fact 1: no CI / p / n in quote → False
        #   fact 4: "twelve to fifteen percent" (no digits in pattern) → False
        #   fact 5: "95% CI 91-97%" → True
        has_nums = [c["has_numeric"] for c in claims]
        assert has_nums == [False, False, True], f"has_numeric mismatch: {has_nums}"

        # Char spans: fact 1 and 5 are verified (body search hits), fact 4 is sentinel
        assert claims[0]["char_start"] != UNVERIFIED_CHAR_START
        assert claims[0]["char_end"] != UNVERIFIED_CHAR_END
        # fact 4 is NOT in SOURCE_BODY → sentinel
        assert claims[1]["char_start"] == UNVERIFIED_CHAR_START
        assert claims[1]["char_end"] == UNVERIFIED_CHAR_END
        # fact 5 verified
        assert claims[2]["char_start"] != UNVERIFIED_CHAR_START

        # The verified spans must actually point at the quote in the body
        f1 = claims[0]
        assert SOURCE_BODY[f1["char_start"]:f1["char_end"]].lower() == f1["direct_quote"][:f1["char_end"] - f1["char_start"]].lower()


# ───────── individual filters ─────────

class TestParserFilters:

    def test_short_statement_filtered(self):
        batch = _build_batch([
            {"statement": "too short", "direct_quote": "x", "relevance_score": 0.9},
        ])
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.skipped["short_statement"] == 1

    def test_short_quote_filtered(self):
        batch = _build_batch([
            {
                "statement": "This is a statement that is definitely long enough",
                "direct_quote": "only three words",
                "relevance_score": 0.9,
            },
        ])
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.skipped["short_quote"] == 1

    def test_url_fragment_filtered(self):
        batch = _build_batch([
            {
                "statement": "Some claim about a web resource with enough statement length",
                "direct_quote": "the standard reference library located at https://example.com/docs/published catalogs all available research articles for academic review purposes",
                "relevance_score": 0.7,
            },
        ])
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.skipped["url_fragment"] == 1

    def test_cookie_fragment_filtered(self):
        batch = _build_batch([
            {
                "statement": "A substantial claim long enough to pass statement length check",
                "direct_quote": "By clicking accept you consent to our use of cookies for advertising purposes across all pages and services worldwide",
                "relevance_score": 0.7,
            },
        ])
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.skipped["cookie_text"] == 1

    def test_wrong_source_url_ignored(self):
        """
        Analyses in the batch that don't match source_url are ignored.
        The killer test didn't cover this because the batch only has one
        analysis — make an explicit test.
        """
        batch = _build_batch(
            facts=[{
                "statement": "This claim should be ignored because it comes from the wrong source",
                "direct_quote": "this quote comes from a different source entirely and must not appear in the parsed result at all under any conditions",
                "relevance_score": 0.9,
            }],
            source_url="https://other.com/nope",
        )
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.total_facts_seen == 0  # we only counted analyses that matched

    def test_empty_batch_returns_empty(self):
        batch = SourceAnalysisBatch.model_validate({"analyses": []})
        claims, result = _parse_batch_to_claims(
            parsed=batch, source_body=SOURCE_BODY, source_url=SOURCE_URL,
        )
        assert claims == []
        assert result.total_facts_seen == 0


# ───────── tier assignment ─────────

class TestAssignTier:

    def test_gold_requires_verified_high_relevance_high_quality(self):
        assert _assign_tier(relevance=0.9, source_quality=0.8, verified=True) == "GOLD"
        assert _assign_tier(relevance=0.7, source_quality=0.6, verified=True) == "GOLD"

    def test_verified_but_low_quality_is_silver(self):
        assert _assign_tier(relevance=0.9, source_quality=0.3, verified=True) == "SILVER"

    def test_verified_but_low_relevance_is_silver_if_above_04(self):
        assert _assign_tier(relevance=0.4, source_quality=0.9, verified=True) == "SILVER"

    def test_unverified_high_relevance_is_silver(self):
        assert _assign_tier(relevance=0.8, source_quality=0.7, verified=False) == "SILVER"

    def test_bronze_catches_everything_else(self):
        assert _assign_tier(relevance=0.3, source_quality=0.3, verified=False) == "BRONZE"
        assert _assign_tier(relevance=0.3, source_quality=0.9, verified=False) == "BRONZE"
        # Unverified + relevance < 0.5 → BRONZE (even if verified at 0.4)
        assert _assign_tier(relevance=0.3, source_quality=0.8, verified=True) == "BRONZE"


# ───────── char-span lookup ─────────

class TestLocateQuote:

    def test_exact_match_returns_correct_offsets(self):
        body = "prefix text HERE is the QUOTE that we want to find and more text"
        quote = "HERE is the QUOTE that we want to find"
        start, end, verified = _locate_quote(quote, body.lower(), body)
        assert verified is True
        assert start == body.find("HERE")
        assert body[start:end].lower() == quote.lower()

    def test_missing_quote_returns_sentinel(self):
        body = "This body does not contain the target text at all."
        quote = "completely unrelated phrase nowhere to be found"
        start, end, verified = _locate_quote(quote, body.lower(), body)
        assert verified is False
        assert start == UNVERIFIED_CHAR_START
        assert end == UNVERIFIED_CHAR_END

    def test_empty_quote_returns_sentinel(self):
        body = "some body text"
        start, end, verified = _locate_quote("", body.lower(), body)
        assert verified is False
        assert (start, end) == (UNVERIFIED_CHAR_START, UNVERIFIED_CHAR_END)

    def test_empty_body_returns_sentinel(self):
        quote = "anything"
        start, end, verified = _locate_quote(quote, "", "")
        assert verified is False


# ───────── has_numeric regex ─────────

class TestNumericPattern:

    @pytest.mark.parametrize("text, expected", [
        ("result was 85% removal in (95% CI: 82-88%)", True),
        ("p < 0.001 for all comparisons", True),
        ("total sample size n=240 participants", True),
        ("effect size ± 2.5 kg baseline", True),
        ("removal efficacy was 78.5%", True),
        ("pooled estimate OR: 2.3 (95% CI)", True),
        ("no numbers in this sentence at all", False),
        ("just text without statistics", False),
    ])
    def test_numeric_detection(self, text, expected):
        assert bool(_NUMERIC_PATTERN.search(text)) is expected


# ───────── orchestrator with mocked client ─────────

class _MockClient:
    """Minimal stand-in for OpenRouterClient with generate_structured."""

    def __init__(self, batch: SourceAnalysisBatch):
        self._batch = batch
        self.calls = 0

    async def generate_structured(
        self, *, prompt: str, schema, system: str,
        max_tokens: int, timeout: int, reasoning_enabled: bool,
    ):
        self.calls += 1
        return self._batch


class TestOrchestrator:

    def test_end_to_end_with_mock_llm(
        self, store: MeshStore, workspace_id: str, source_file: Path
    ):
        # Ingest a real file so we have a source_page row with filepath
        src_id, _ = ingest_file(
            store=store, workspace_id=workspace_id,
            file_path=source_file, kind="upload", url=SOURCE_URL,
        )

        # Mock LLM returns a batch with 2 valid facts
        batch = _build_batch(
            facts=[
                {
                    "statement": "GAC achieved 85% removal of long-chain PFAS compounds",
                    "direct_quote": "GAC achieved 85% removal of long-chain PFAS compounds in 10 minute contact time across independent trials at typical residential concentrations",
                    "relevance_score": 0.9,
                },
                {
                    "statement": "Reverse osmosis showed superior performance at 95% CI",
                    "direct_quote": "Reverse osmosis membranes performed better at 95% CI 91-97% but required pressurization and produced substantial reject water volumes",
                    "relevance_score": 0.85,
                },
            ],
            source_quality=0.8,
        )
        client = _MockClient(batch)

        result = asyncio.run(extract_claims_from_source(
            client=client,
            store=store,
            workspace_id=workspace_id,
            source_page_id=src_id,
            query="How do PFAS filters work?",
        ))

        assert client.calls == 1
        assert len(result.inserted_claim_ids) == 2
        assert result.total_facts_seen == 2

        # Workspace counter bumped
        ws = store.get_workspace(workspace_id)
        assert ws["claim_count"] == 2

        # Inserted claims exist in the store with correct char spans
        for clm_id in result.inserted_claim_ids:
            clm = store.get_claim(clm_id)
            assert clm is not None
            assert clm["source_page_id"] == src_id
            assert clm["tier"] == "GOLD"  # both: verified, relevance high, source_quality 0.8
            # Char span should be a valid range pointing into the body
            assert clm["char_start"] >= 0
            assert clm["char_end"] > clm["char_start"]

        # CP-C fix: verify vectors were inserted alongside claims.
        # Without this check, we could silently ship claims that are
        # invisible to lethal retrieval (Unit 5's entry path).
        vec_count = store._conn.execute(
            "SELECT COUNT(*) AS c FROM vec_claims"
        ).fetchone()["c"]
        assert vec_count == 2, f"Expected 2 vectors, got {vec_count}"

        # And verify they are queryable via KNN — a real query for the
        # first claim statement must retrieve that claim at distance ~0.
        from src.utils.embedding_service import embed_texts
        q_vec = embed_texts([
            "GAC achieved 85% removal of long-chain PFAS compounds"
        ])[0]
        import numpy as np
        q_arr = np.asarray(q_vec, dtype=np.float32)
        hits = store.search_claims_by_vector(
            workspace_id=workspace_id, query_embedding=q_arr, k=5,
        )
        assert len(hits) == 2
        # The GAC claim should be the closest match
        top_claim_id = hits[0][0]
        top_claim = store.get_claim(top_claim_id)
        assert "GAC" in top_claim["statement"]

    def test_missing_source_raises(
        self, store: MeshStore, workspace_id: str
    ):
        empty = SourceAnalysisBatch.model_validate({"analyses": []})
        client = _MockClient(empty)
        with pytest.raises(MeshStoreError, match="Source not found"):
            asyncio.run(extract_claims_from_source(
                client=client, store=store,
                workspace_id=workspace_id,
                source_page_id="src_does_not_exist",
                query="q",
            ))

    def test_wrong_workspace_raises(
        self, store: MeshStore, workspace_id: str, source_file: Path
    ):
        # Ingest into workspace A
        src_id, _ = ingest_file(
            store=store, workspace_id=workspace_id, file_path=source_file,
        )
        # Create a second workspace and try to extract the source from THAT workspace
        ws_b = store.create_workspace(name="other_ws")
        empty = SourceAnalysisBatch.model_validate({"analyses": []})
        client = _MockClient(empty)
        with pytest.raises(MeshStoreError, match="belongs to workspace"):
            asyncio.run(extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_b,
                source_page_id=src_id,
                query="q",
            ))

    def test_atomic_batch_insert(
        self, store: MeshStore, workspace_id: str, source_file: Path
    ):
        """All valid claims from a single extraction are in one transaction.

        If any insert mid-batch fails, none of the batch is committed.
        We simulate a failure by monkey-patching store.insert_claim on
        the second call.
        """
        src_id, _ = ingest_file(
            store=store, workspace_id=workspace_id,
            file_path=source_file, url=SOURCE_URL,
        )
        batch = _build_batch(
            facts=[
                {
                    "statement": "GAC achieved 85% removal of long-chain PFAS compounds",
                    "direct_quote": "GAC achieved 85% removal of long-chain PFAS compounds in 10 minute contact time across independent trials at typical residential concentrations",
                    "relevance_score": 0.9,
                },
                {
                    "statement": "Reverse osmosis showed superior performance at 95% CI",
                    "direct_quote": "Reverse osmosis membranes performed better at 95% CI 91-97% but required pressurization and produced substantial reject water volumes",
                    "relevance_score": 0.85,
                },
            ],
            source_quality=0.8,
        )
        client = _MockClient(batch)

        # Patch insert_claim to raise on the 2nd call
        original = store.insert_claim
        call_count = {"n": 0}
        def failing_insert(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise MeshStoreError("simulated failure")
            return original(**kwargs)
        store.insert_claim = failing_insert  # type: ignore

        with pytest.raises(MeshStoreError, match="simulated failure"):
            asyncio.run(extract_claims_from_source(
                client=client, store=store,
                workspace_id=workspace_id,
                source_page_id=src_id,
                query="q",
            ))

        # Restore
        store.insert_claim = original  # type: ignore

        # Zero claims in the db — the failed batch rolled back
        row = store._conn.execute("SELECT COUNT(*) AS c FROM claims").fetchone()
        assert row["c"] == 0
        ws = store.get_workspace(workspace_id)
        assert ws["claim_count"] == 0
