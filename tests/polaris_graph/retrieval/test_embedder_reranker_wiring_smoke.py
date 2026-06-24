"""Offline $0 smoke test for the recency-completion embedder + reranker WIRING (I-recency-001 #1296).

Proves the flag-gated SELECTION wiring for three picks WITHOUT any model load, network, GPU, or
paid call:

  1. ``EmbeddingConfig.from_env`` — default => all-MiniLM-L6-v2 / 384-dim; PG_EMBEDDER_MODEL=qwen3
     => Qwen/Qwen3-Embedding-8B / 4096-dim.
  2. ``CrossEncoderConfig.from_env`` — default => ms-marco-MiniLM; PG_RERANKER_MODEL=qwen3 =>
     Qwen/Qwen3-Reranker-4B.
  3. ``evidence_selector._maybe_rerank_selection`` — pure IDENTITY when PG_RERANKER_MODEL unset
     (with ``sentence_transformers.CrossEncoder`` patched to a sentinel that RAISES if constructed,
     mechanically proving NO model load on the OFF path); a genuine REORDER when ON (with a stub
     CrossEncoder, still $0 — no real weights).
  4. ``importlib.reload(src.utils.embedding_service)`` with PG_EMBEDDER_MODEL set flips the
     module-level ``EMBEDDING_MODEL_NAME`` constant WITHOUT constructing a SentenceTransformer
     (the import is lazy inside ``EmbeddingService.__init__``, never reached at module import).

Every model class is patched/stubbed; the GPU models load ONLY in the operator-FORBIDDEN e2e.
This test proves SELECTION/wiring, never a model load. Cost: $0.
"""
from __future__ import annotations

import importlib
import os
import sys
from contextlib import contextmanager

from src.config.core import CrossEncoderConfig, EmbeddingConfig


@contextmanager
def _env(name: str, value: str | None):
    """Set (or pop) an env var for the duration of the block, restoring it after."""
    prev = os.environ.get(name)
    try:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        yield
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev


# ── 1. EmbeddingConfig.from_env ──────────────────────────────────────────────

def test_embedding_config_default_is_minilm_384():
    """Unset PG_EMBEDDER_MODEL => current behaviour: all-MiniLM-L6-v2 / 384-dim."""
    with _env("PG_EMBEDDER_MODEL", None):
        cfg = EmbeddingConfig.from_env()
    assert cfg.model == "all-MiniLM-L6-v2", cfg.model
    assert cfg.dimension == 384, cfg.dimension


def test_embedding_config_qwen3_flag_flips_to_qwen3_8b_4096():
    """PG_EMBEDDER_MODEL=qwen3 => Qwen/Qwen3-Embedding-8B / 4096-dim (selection only)."""
    with _env("PG_EMBEDDER_MODEL", "qwen3"):
        cfg = EmbeddingConfig.from_env()
    assert cfg.model == "Qwen/Qwen3-Embedding-8B", cfg.model
    assert cfg.dimension == 4096, cfg.dimension
    assert cfg.max_seq_length == 8192, cfg.max_seq_length


# ── 2. CrossEncoderConfig.from_env ───────────────────────────────────────────

def test_cross_encoder_config_default_is_ms_marco_minilm():
    """Unset PG_RERANKER_MODEL => current behaviour: ms-marco-MiniLM cross-encoder."""
    with _env("PG_RERANKER_MODEL", None):
        cfg = CrossEncoderConfig.from_env()
    assert cfg.model == "cross-encoder/ms-marco-MiniLM-L-6-v2", cfg.model


def test_cross_encoder_config_qwen3_flag_flips_to_qwen3_reranker_4b():
    """PG_RERANKER_MODEL=qwen3 => Qwen/Qwen3-Reranker-4B (selection only)."""
    with _env("PG_RERANKER_MODEL", "qwen3"):
        cfg = CrossEncoderConfig.from_env()
    assert cfg.model == "Qwen/Qwen3-Reranker-4B", cfg.model


def test_cross_encoder_config_truthy_aliases_select_qwen3():
    """The documented truthy aliases (1 / true / on / yes / qwen3-reranker-4b) all select Qwen3."""
    for val in ("1", "true", "on", "yes", "qwen3-reranker-4b"):
        with _env("PG_RERANKER_MODEL", val):
            cfg = CrossEncoderConfig.from_env()
        assert cfg.model == "Qwen/Qwen3-Reranker-4B", f"{val!r} -> {cfg.model}"


# ── 3. evidence_selector._maybe_rerank_selection ─────────────────────────────

def _rows():
    """Three selected evidence rows (already tier-balanced upstream)."""
    return [
        {"evidence_id": "ev_000", "statement": "alpha about cats", "direct_quote": "cats"},
        {"evidence_id": "ev_001", "statement": "beta about dogs", "direct_quote": "dogs"},
        {"evidence_id": "ev_002", "statement": "gamma about birds", "direct_quote": "birds"},
    ]


class _ExplodingCrossEncoder:
    """Sentinel: constructing this is a test FAILURE — proves NO model load on the OFF path."""

    def __init__(self, *a, **k):  # noqa: D401
        raise AssertionError(
            "CrossEncoder was constructed on the OFF path — a model load / spend would occur."
        )


class _StubCrossEncoder:
    """ON-path stub: returns deterministic scores so we can assert a real reorder. $0 (no weights)."""

    def __init__(self, model_name, *a, **k):
        self.model_name = model_name

    def predict(self, pairs):
        # Score by the row text so ev_002 ('gamma...birds') sorts FIRST, ev_000 LAST.
        # pairs are [question, statement+direct_quote]; rank descending by a marker.
        out = []
        for _q, doc in pairs:
            if "birds" in doc:
                out.append(0.9)
            elif "dogs" in doc:
                out.append(0.5)
            else:
                out.append(0.1)
        return out


def test_rerank_helper_is_identity_when_off(monkeypatch):
    """OFF (PG_RERANKER_MODEL unset): identity no-op AND the CrossEncoder is NEVER constructed."""
    from src.polaris_graph.retrieval import evidence_selector as es

    # Patch the lazily-imported symbol so ANY construction raises — proving no model load.
    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _ExplodingCrossEncoder)

    with _env("PG_RERANKER_MODEL", None):
        rows = _rows()
        out = es._maybe_rerank_selection(rows, "what about birds?")
    assert out is rows, "OFF path must return the SAME list object (pure identity)"
    assert [r["evidence_id"] for r in out] == ["ev_000", "ev_001", "ev_002"]


def test_rerank_helper_reorders_when_on(monkeypatch):
    """ON (PG_RERANKER_MODEL=qwen3): rows are REORDERED by the (stub) cross-encoder, same set."""
    from src.polaris_graph.retrieval import evidence_selector as es

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _StubCrossEncoder)

    with _env("PG_RERANKER_MODEL", "qwen3"):
        rows = _rows()
        out = es._maybe_rerank_selection(rows, "what about birds?")
    # Reorder ONLY: same set of evidence_ids, none added or dropped.
    assert {r["evidence_id"] for r in out} == {"ev_000", "ev_001", "ev_002"}
    assert len(out) == len(rows)
    # Stub scored birds(0.9) > dogs(0.5) > cats(0.1) => ev_002, ev_001, ev_000.
    assert [r["evidence_id"] for r in out] == ["ev_002", "ev_001", "ev_000"]


def test_rerank_helper_loud_fallback_on_failure(monkeypatch):
    """ON but the cross-encoder load/scoring blows up => LOUD fallback to the original order."""
    from src.polaris_graph.retrieval import evidence_selector as es

    class _BoomCrossEncoder:
        def __init__(self, *a, **k):
            raise RuntimeError("simulated load failure")

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _BoomCrossEncoder)

    with _env("PG_RERANKER_MODEL", "qwen3"):
        rows = _rows()
        out = es._maybe_rerank_selection(rows, "what about birds?")
    # Fallback returns the ORIGINAL order (a valid result), never an empty/dropped set.
    assert [r["evidence_id"] for r in out] == ["ev_000", "ev_001", "ev_002"]


def test_rerank_flag_helper_default_off():
    """The flag predicate itself: unset => OFF; qwen3 => ON."""
    from src.polaris_graph.retrieval import evidence_selector as es

    with _env("PG_RERANKER_MODEL", None):
        assert es._reranker_selection_enabled() is False
    with _env("PG_RERANKER_MODEL", "qwen3"):
        assert es._reranker_selection_enabled() is True


# ── 3b. END-TO-END WIRING: the wrap at the FINAL return is actually INVOKED ────
# This is the load-bearing wiring proof (§-1.4 "committed+green ≠ wired"): the
# isolated-helper tests above would all stay green even if the one-line wrap at the
# final return were deleted. This test calls select_evidence_for_generation through
# the tier-balanced TRUNCATING path (relevance_floor=None, pool > max_rows) and
# asserts the rerank FIRED — the returned ORDER changes ON vs OFF — AND the
# selection CONTRACT (selected_counts / dropped_count) is byte-identical ON vs OFF.

def _e2e_rows():
    """Six same-tier evidence rows so the tier-balanced truncating path keeps a
    deterministic subset (pool 6 > max_rows 4) whose ORDER the reranker can permute."""
    return [
        {"evidence_id": f"ev_{i:03d}", "source_url": f"https://ex/{i}",
         "tier": "T1", "statement": txt, "direct_quote": txt}
        for i, txt in enumerate([
            "alpha cats", "beta dogs", "gamma birds",
            "delta cats", "epsilon dogs", "zeta birds",
        ])
    ]


def _classified(rows):
    return [{"url": r["source_url"], "tier": "T1"} for r in rows]


def test_select_evidence_rerank_is_wired_at_final_return(monkeypatch):
    """select_evidence_for_generation INVOKES the rerank wrap on the tier-balanced path.

    ON (PG_RERANKER_MODEL=qwen3, stub cross-encoder) the selected_rows ORDER differs
    from OFF, proving the one-line wrap at the final return actually fires; AND the
    selected_counts / dropped_count are identical ON vs OFF, proving the wrap is a
    pure reorder (the tier-balance CONTRACT is untouched). $0 — stub, no model load.
    """
    from src.polaris_graph.retrieval import evidence_selector as es

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _StubCrossEncoder)

    common = dict(
        research_question="what about birds?",
        protocol=None,
        max_rows=4,
        primary_trial_anchors=None,
        relevance_floor=None,   # tier-balanced truncating path (NOT the floor path)
        sub_queries=None,
    )

    rows_off = _e2e_rows()
    with _env("PG_RERANKER_MODEL", None):
        sel_off = es.select_evidence_for_generation(
            classified_sources=_classified(rows_off),
            evidence_rows=rows_off,
            **common,
        )

    rows_on = _e2e_rows()
    with _env("PG_RERANKER_MODEL", "qwen3"):
        sel_on = es.select_evidence_for_generation(
            classified_sources=_classified(rows_on),
            evidence_rows=rows_on,
            **common,
        )

    off_ids = [r["evidence_id"] for r in sel_off.selected_rows]
    on_ids = [r["evidence_id"] for r in sel_on.selected_rows]

    # Same SET of rows kept (reorder only — wrap added/dropped nothing).
    assert set(off_ids) == set(on_ids), (off_ids, on_ids)
    assert len(on_ids) == len(off_ids) == 4
    # The rerank FIRED: ON ordering differs from OFF (the stub ranks birds>dogs>cats,
    # so the OFF tier/relevance order is genuinely permuted). This is the wiring proof.
    assert on_ids != off_ids, (
        "reranker wrap did NOT fire at the final return — ON order == OFF order"
    )
    # CONTRACT invariant: counts + drop are identical (derive from selection, not order).
    assert sel_on.selected_counts == sel_off.selected_counts
    assert sel_on.dropped_count == sel_off.dropped_count


# ── 3c. RELEVANCE-FLOOR PATH: the rerank wrap fires on the PRODUCTION return ───
# The production live call (`scripts/run_honest_sweep_r3.py` ~:8365) passes
# `relevance_floor`, so `select_evidence_for_generation` returns EARLY via
# `_relevance_floor_selection` and NEVER reaches the tier-balanced final-return
# wrap exercised in 3b. Before I-recency-001 wiring fix the reranker therefore
# never fired on the real run. These tests drive the function DOWN THE
# RELEVANCE-FLOOR PATH (`relevance_floor` set) and prove:
#   OFF  => floor return is BYTE-IDENTICAL (same rows + order + counts +
#           dropped_count) AND the CrossEncoder is NEVER constructed ($0).
#   ON   => SAME rows, REORDERED, with counts/dropped UNCHANGED — the
#           consolidate/KEEP-ALL contract is a pure permutation (no drop/add).


def _floor_rows():
    """Three same-tier rows. relevance_floor=0.0 => keep-ALL in BOTH redesign +
    legacy modes (every non-negative score passes), so this is a true keep-all
    fixture. The floor sort (relevance x authority x retrieval_weight, then tier,
    then original index) is DETERMINISTIC, so the OFF order is fixed; the OFF test
    captures that baseline ORDER and asserts the wrap leaves it byte-identical
    (it does not hardcode a guessed order). The ON test asserts a DIFFERENT,
    reranker-driven permutation of the SAME rows."""
    return [
        {"evidence_id": "ev_000", "source_url": "https://ex/0", "tier": "T1",
         "statement": "alpha cats", "direct_quote": "cats", "authority_score": 1.0},
        {"evidence_id": "ev_001", "source_url": "https://ex/1", "tier": "T1",
         "statement": "beta dogs", "direct_quote": "dogs", "authority_score": 1.0},
        {"evidence_id": "ev_002", "source_url": "https://ex/2", "tier": "T1",
         "statement": "gamma birds", "direct_quote": "birds", "authority_score": 1.0},
    ]


def _floor_classified(rows):
    return [{"url": r["source_url"], "tier": "T1"} for r in rows]


def _floor_common():
    return dict(
        research_question="what about birds?",
        protocol=None,
        max_rows=0,           # floor mode ignores max_rows (no cap) — keep-all
        primary_trial_anchors=None,
        relevance_floor=0.0,  # FLOOR PATH (not None) => the production return seam
        sub_queries=None,
    )


def test_select_floor_path_rerank_is_identity_when_off(monkeypatch):
    """OFF (PG_RERANKER_MODEL unset): the relevance-floor return is BYTE-IDENTICAL
    (same rows, same order, same counts) AND the CrossEncoder is NEVER constructed."""
    from src.polaris_graph.retrieval import evidence_selector as es

    # Exploding sentinel: if the OFF path ever constructs a CrossEncoder, FAIL.
    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _ExplodingCrossEncoder)

    rows_a = _floor_rows()
    with _env("PG_RERANKER_MODEL", None):
        sel_a = es.select_evidence_for_generation(
            classified_sources=_floor_classified(rows_a),
            evidence_rows=rows_a,
            **_floor_common(),
        )
        # Second OFF call: prove the floor order is DETERMINISTIC (the byte-
        # identity baseline the ON test diverges from). If the exploding
        # sentinel ever constructs, this raises — the $0 / no-model-load proof.
        rows_b = _floor_rows()
        sel_b = es.select_evidence_for_generation(
            classified_sources=_floor_classified(rows_b),
            evidence_rows=rows_b,
            **_floor_common(),
        )
    ids_a = [r["evidence_id"] for r in sel_a.selected_rows]
    ids_b = [r["evidence_id"] for r in sel_b.selected_rows]
    # keep-ALL: every input row survives the floor (relevance_floor=0.0).
    assert len(sel_a.selected_rows) == len(rows_a) == 3, ids_a
    # Byte-identical ORDER on the OFF path: deterministic, repeatable, no reorder.
    assert ids_a == ids_b, (ids_a, ids_b)
    assert set(ids_a) == {"ev_000", "ev_001", "ev_002"}, ids_a
    # The floor strategy id is preserved (the wrap did not swap the dataclass).
    assert sel_a.selection_strategy.startswith("relevance_floor"), sel_a.selection_strategy
    # dropped_count is the floor's own count, untouched by the (no-op) wrap.
    assert sel_a.dropped_count == 0, sel_a.dropped_count


def test_select_floor_path_rerank_reorders_when_on(monkeypatch):
    """ON (PG_RERANKER_MODEL=qwen3, stub cross-encoder): the relevance-floor return
    keeps the SAME rows but REORDERS them, and counts/dropped are UNCHANGED —
    proving the reranker fires on the PRODUCTION (floor) path as a pure permutation
    that preserves the consolidate/keep-all contract. $0 — stub, no model load."""
    from src.polaris_graph.retrieval import evidence_selector as es

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "CrossEncoder", _StubCrossEncoder)

    rows_off = _floor_rows()
    with _env("PG_RERANKER_MODEL", None):
        sel_off = es.select_evidence_for_generation(
            classified_sources=_floor_classified(rows_off),
            evidence_rows=rows_off,
            **_floor_common(),
        )

    rows_on = _floor_rows()
    with _env("PG_RERANKER_MODEL", "qwen3"):
        sel_on = es.select_evidence_for_generation(
            classified_sources=_floor_classified(rows_on),
            evidence_rows=rows_on,
            **_floor_common(),
        )

    off_ids = [r["evidence_id"] for r in sel_off.selected_rows]
    on_ids = [r["evidence_id"] for r in sel_on.selected_rows]

    # KEEP-ALL preserved: SAME set of rows, none dropped/added (pure permutation).
    assert set(on_ids) == set(off_ids) == {"ev_000", "ev_001", "ev_002"}, (off_ids, on_ids)
    assert len(on_ids) == len(off_ids) == 3
    # The rerank FIRED on the floor path: ON order differs from OFF. The stub
    # scores birds(0.9) > dogs(0.5) > cats(0.1) => ev_002, ev_001, ev_000.
    assert on_ids != off_ids, (
        "reranker wrap did NOT fire on the relevance-floor (production) path — "
        "ON order == OFF order"
    )
    assert on_ids == ["ev_002", "ev_001", "ev_000"], on_ids
    # CONTRACT invariant: counts + dropped are byte-identical ON vs OFF — the
    # rerank ONLY reordered, it did not drop/add a corroborator (keep-all).
    assert sel_on.selected_counts == sel_off.selected_counts, (
        sel_on.selected_counts, sel_off.selected_counts,
    )
    assert sel_on.dropped_count == sel_off.dropped_count == 0
    # The floor strategy + notes survive the reorder (dataclasses.replace kept
    # every non-row field), so the keep-all telemetry is unchanged.
    assert sel_on.selection_strategy == sel_off.selection_strategy
    assert sel_on.notes == sel_off.notes


# ── 4. embedding_service module reload flips EMBEDDING_MODEL_NAME (no model build) ──

def test_embedding_service_reload_flips_model_name_no_construction(monkeypatch):
    """importlib-reload embedding_service with PG_EMBEDDER_MODEL=qwen3 flips the module
    constant WITHOUT constructing a SentenceTransformer (the import is lazy inside __init__).

    We patch sentence_transformers.SentenceTransformer with a sentinel that RAISES if
    constructed — module reload must NOT trip it (proving $0 / no model load)."""
    import src.utils.embedding_service as emb

    class _ExplodingSentenceTransformer:
        def __init__(self, *a, **k):
            raise AssertionError(
                "SentenceTransformer constructed during module reload — a model load would occur."
            )

    import sentence_transformers
    monkeypatch.setattr(
        sentence_transformers, "SentenceTransformer", _ExplodingSentenceTransformer
    )

    try:
        # Default reload => MiniLM / 384.
        with _env("PG_EMBEDDER_MODEL", None):
            reloaded = importlib.reload(emb)
        assert reloaded.EMBEDDING_MODEL_NAME == "all-MiniLM-L6-v2", reloaded.EMBEDDING_MODEL_NAME
        assert reloaded.EMBEDDING_DIMENSIONS == 384

        # qwen3 reload => Qwen3-Embedding-8B / 4096 (constant flips, still no construction).
        with _env("PG_EMBEDDER_MODEL", "qwen3"):
            reloaded = importlib.reload(emb)
        assert reloaded.EMBEDDING_MODEL_NAME == "Qwen/Qwen3-Embedding-8B", reloaded.EMBEDDING_MODEL_NAME
        assert reloaded.EMBEDDING_DIMENSIONS == 4096
    finally:
        # Restore the module to its clean (unset / MiniLM) state so later tests are unpolluted.
        os.environ.pop("PG_EMBEDDER_MODEL", None)
        importlib.reload(emb)


if __name__ == "__main__":
    # Lightweight self-run (no pytest fixtures): exercise the non-monkeypatch tests.
    test_embedding_config_default_is_minilm_384()
    test_embedding_config_qwen3_flag_flips_to_qwen3_8b_4096()
    test_cross_encoder_config_default_is_ms_marco_minilm()
    test_cross_encoder_config_qwen3_flag_flips_to_qwen3_reranker_4b()
    test_cross_encoder_config_truthy_aliases_select_qwen3()
    test_rerank_flag_helper_default_off()
    print("PASS — embedder + reranker config/flag wiring smoke ($0, no model load)")
