"""M-52 tests: generator-side pull from live_corpus when
evidence_pool lacks anchor-matched primary.

V29 cycle 1, item 2 of 3. Belt-and-suspenders companion to M-51
selector custody. Codex plan pass-1 CONDITIONAL-no-blockers
revisions #4-5 woven in:
- Preserve existing live-corpus evidence_id when present + not colliding
- Fallback ev_from_corpus_{anchor_slug}_{n} only for missing/collisions
- Pulled rows must have all strict_verify-essential fields
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    _m52_pull_from_live_corpus,
)


def _nejm_primary_row(
    ev_id: str,
    anchor: str,
    quote: str = None,
) -> dict:
    return {
        "evidence_id": ev_id,
        "source_url": f"https://www.nejm.org/doi/{ev_id}",
        "title": f"{anchor}: Primary publication",
        "direct_quote": quote or (f"{anchor} primary quote " * 20),
        "tier": "T1",
        "source": "serper",
    }


def _minimal_primary_row(**kwargs) -> dict:
    """Row with fields strict_verify + bibliography need."""
    base = {
        "direct_quote": "x" * 200,
        "tier": "T1",
    }
    base.update(kwargs)
    return base


class TestM52PullMissingPrimary:
    def test_pulls_primary_from_corpus_when_pool_lacks(self) -> None:
        pool = {
            "ev_r1": {"evidence_id": "ev_r1", "title": "review",
                      "direct_quote": "x"*100, "tier": "T2"},
        }
        corpus = [
            pool["ev_r1"],  # already in pool
            _nejm_primary_row("ev_s4", "SURPASS-4"),
        ]
        pulled = _m52_pull_from_live_corpus(
            pool, corpus, ["SURPASS-4"],
        )
        assert len(pulled) == 1
        assert pulled[0]["anchor"] == "SURPASS-4"
        assert pulled[0]["evidence_id"] == "ev_s4"  # preserved ID
        assert "ev_s4" in pool
        # Row correctly added to pool
        assert pool["ev_s4"]["title"].startswith("SURPASS-4")

    def test_no_corpus_is_noop(self) -> None:
        pool = {}
        assert _m52_pull_from_live_corpus(pool, None, ["SURPASS-4"]) == []
        assert _m52_pull_from_live_corpus(pool, [], ["SURPASS-4"]) == []
        assert pool == {}

    def test_no_anchors_is_noop(self) -> None:
        pool = {}
        corpus = [_nejm_primary_row("ev_s4", "SURPASS-4")]
        assert _m52_pull_from_live_corpus(pool, corpus, []) == []
        assert _m52_pull_from_live_corpus(pool, corpus, None) == []
        assert pool == {}

    def test_primary_already_in_pool_is_skipped(self) -> None:
        primary = _nejm_primary_row("ev_s4", "SURPASS-4")
        pool = {"ev_s4": primary}
        corpus = [primary, _nejm_primary_row("ev_other", "SURPASS-4")]
        # Pool already has a SURPASS-4 primary → no pull even though
        # corpus has more
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled == []

    def test_multi_anchor_multi_primary(self) -> None:
        pool = {}
        corpus = [
            _nejm_primary_row("ev_s4", "SURPASS-4"),
            _nejm_primary_row("ev_cvot", "SURPASS-CVOT"),
        ]
        pulled = _m52_pull_from_live_corpus(
            pool, corpus, ["SURPASS-4", "SURPASS-CVOT"],
        )
        assert len(pulled) == 2
        assert {p["anchor"] for p in pulled} == {"SURPASS-4", "SURPASS-CVOT"}
        assert "ev_s4" in pool and "ev_cvot" in pool


class TestM52EvIdStrategy:
    """Codex revision #4: preserve existing ID when safe; prefixed
    fallback only for missing/collisions."""

    def test_preserves_live_corpus_evidence_id(self) -> None:
        pool = {}
        corpus = [_nejm_primary_row("ev_0421", "SURPASS-4")]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled[0]["evidence_id"] == "ev_0421"  # preserved
        assert pulled[0]["preserved_live_corpus_id"] is True
        assert "ev_0421" in pool

    def test_missing_evidence_id_uses_prefixed_fallback(self) -> None:
        pool = {}
        row = _nejm_primary_row("tmp_remove", "SURPASS-4")
        row.pop("evidence_id")
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled[0]["evidence_id"].startswith("ev_from_corpus_surpass_4")
        assert not pulled[0]["preserved_live_corpus_id"]

    def test_evidence_id_collision_uses_prefixed_fallback(self) -> None:
        """Pool has `ev_s4` as DIFFERENT row. Corpus has SURPASS-4 primary
        with same `ev_s4` ID. Collision detected; prefixed fallback used."""
        pool = {
            "ev_s4": {
                "evidence_id": "ev_s4",
                "title": "Different paper",
                "source_url": "https://different.example/s4",
                "direct_quote": "x"*150,
                "tier": "T4",
            },
        }
        corpus = [_nejm_primary_row("ev_s4", "SURPASS-4")]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert len(pulled) == 1
        # Collision → fallback
        assert pulled[0]["evidence_id"].startswith("ev_from_corpus_surpass_4")
        assert not pulled[0]["preserved_live_corpus_id"]

    def test_fallback_prefix_uniqueness(self) -> None:
        """Multiple fallbacks for same anchor get sequential suffixes."""
        pool = {
            "ev_from_corpus_surpass_4": {
                "evidence_id": "ev_from_corpus_surpass_4",
                "title": "pre-existing placeholder",
                "source_url": "https://x/y",
                "direct_quote": "x"*150,
                "tier": "T4",
            },
        }
        row = _nejm_primary_row("tmp", "SURPASS-4")
        row.pop("evidence_id")
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled[0]["evidence_id"].startswith("ev_from_corpus_surpass_4_")
        # Suffix with _1 or higher
        assert pulled[0]["evidence_id"] != "ev_from_corpus_surpass_4"


class TestM52MutationContract:
    """Codex revision #5: pulled row must carry strict_verify-
    essential fields. Missing field → skip (fail-loud)."""

    def test_row_without_direct_quote_skipped(self) -> None:
        pool = {}
        row = {
            "evidence_id": "ev_x",
            "title": "SURPASS-4 primary",
            "source_url": "https://nejm.org/x",
            "tier": "T1",
            # NO direct_quote
        }
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled == []
        assert pool == {}

    def test_row_without_tier_skipped(self) -> None:
        pool = {}
        row = {
            "evidence_id": "ev_x",
            "title": "SURPASS-4 primary",
            "source_url": "https://nejm.org/x",
            "direct_quote": "x"*200,
            # NO tier
        }
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled == []

    def test_row_without_url_skipped(self) -> None:
        pool = {}
        row = {
            "evidence_id": "ev_x",
            "title": "SURPASS-4 primary",
            "direct_quote": "x"*200,
            "tier": "T1",
            # NO source_url / url
        }
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert pulled == []

    def test_url_aliased_as_url_not_source_url(self) -> None:
        """Some retrievers use `url` instead of `source_url`. Accept
        either."""
        pool = {}
        row = {
            "evidence_id": "ev_x",
            "title": "SURPASS-4 primary",
            "url": "https://nejm.org/x",  # `url` alias
            "direct_quote": "x"*200,
            "tier": "T1",
        }
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert len(pulled) == 1
        # Pulled row's source_url was populated from `url`
        assert pool["ev_x"]["source_url"] == "https://nejm.org/x"

    def test_live_row_title_fallback_to_statement(self) -> None:
        """M-48 pass-2 live-row schema: title absent but statement
        present. Title populated from statement during pull."""
        pool = {}
        row = {
            "evidence_id": "ev_x",
            "source_url": "https://nejm.org/x",
            "statement": "SURPASS-4: primary publication on phase-3",
            "direct_quote": "x"*200,
            "tier": "T1",
        }
        corpus = [row]
        pulled = _m52_pull_from_live_corpus(pool, corpus, ["SURPASS-4"])
        assert len(pulled) == 1
        assert "SURPASS-4" in pool["ev_x"]["title"]
