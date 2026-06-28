"""I-deepfix-001 (#1344) item 2 — winner-firing fail-closed gate.

Offline (no GPU / no network / no model load) proof that the relevance-layer
winner-firing gate trips ON structural-dark and STAYS QUIET on healthy / CPU-
fallback / not-requested. The gate decision is a PURE function
(``winner_firing_gate.evaluate_winner_firing``), so these tests exercise the
exact production decision logic without touching the heavy retrieval chain.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.winner_firing_gate import (
    WinnerFiringVerdict,
    _w7_reranker_requested,
    evaluate_winner_firing,
)


# ── W6 embedder / B4 semantic scorer ─────────────────────────────────────────
def test_w6_dark_on_false_cache_sentinel_trips_abort():
    """The cached embedder handle is the ``False`` sentinel (load attempted,
    failed) => W6 structurally dark => abort."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},  # W5 healthy
        embedder_cache_sentinel=False,                  # W6 load failed
        w6_requested=True,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is True
    assert "W6_embedder" in v.dark_winners
    assert v.diagnostics, "a dark winner must carry a diagnostic line"


def test_w6_not_dark_on_none_cache_sentinel():
    """``None`` cache == not yet tried (NOT a structural failure) => no trip."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=None,
        w6_requested=True,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is False
    assert "W6_embedder" not in v.dark_winners


def test_w6_dark_on_semantic_fell_back_flag():
    """A loaded handle but a recorded semantic->lexical fallback still trips W6."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=object(),  # truthy handle
        w6_requested=True,
        w5_requested=False,
        w7_requested=False,
        semantic_fell_back=True,
    )
    assert v.abort is True
    assert "W6_embedder" in v.dark_winners


def test_w6_not_checked_when_not_requested():
    """A False sentinel must NOT trip when W6 was never requested (legacy path)."""
    v = evaluate_winner_firing(
        content_relevance=None,
        embedder_cache_sentinel=False,
        w6_requested=False,
        w5_requested=False,
        w7_requested=False,
    )
    assert v.abort is False
    assert v.winners_checked["W6_embedder"] == "not_requested"


# ── W5 content-relevance reranker ────────────────────────────────────────────
def test_w5_dark_on_reranker_device_unavailable():
    """``reranker_device == 'unavailable'`` (load failed -> full weight) trips W5."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "unavailable", "n_scored": 0},
        embedder_cache_sentinel=object(),  # W6 healthy
        w6_requested=True,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is True
    assert "W5_content_relevance" in v.dark_winners


def test_w5_dark_when_requested_but_no_report():
    """Requested but produced NO telemetry report at all => the judge never ran."""
    v = evaluate_winner_firing(
        content_relevance=None,
        embedder_cache_sentinel=object(),
        w6_requested=False,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is True
    assert "W5_content_relevance" in v.dark_winners


def test_w5_cpu_fallback_is_disclosed_not_dark():
    """A CPU fallback is a disclosed degrade — the winner FIRED, just slower. No trip."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cpu", "used_cpu_fallback": True},
        embedder_cache_sentinel=object(),
        w6_requested=True,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is False
    assert v.winners_checked["W5_content_relevance"] == "cpu_fallback_disclosed"


def test_w5_fired_clean_no_trip():
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda", "n_scored": 50},
        embedder_cache_sentinel=object(),
        w6_requested=True,
        w5_requested=True,
        w7_requested=False,
    )
    assert v.abort is False
    assert v.winners_checked["W5_content_relevance"] == "fired"


# ── W7 selection reranker ────────────────────────────────────────────────────
def test_w7_dark_on_explicit_load_failed():
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=object(),
        w6_requested=True,
        w5_requested=True,
        w7_requested=True,
        w7_load_failed=True,
    )
    assert v.abort is True
    assert "W7_reranker" in v.dark_winners


def test_w7_pending_post_seam_does_not_trip():
    """W7 fires after this seam; unknown load state (None) must NOT trip the gate."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=object(),
        w6_requested=True,
        w5_requested=True,
        w7_requested=True,
        w7_load_failed=None,
    )
    assert v.abort is False
    assert v.winners_checked["W7_reranker"] == "pending_post_seam"


# ── all-healthy + multi-dark ─────────────────────────────────────────────────
def test_all_winners_healthy_no_abort():
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda", "n_scored": 80},
        embedder_cache_sentinel=object(),
        w6_requested=True,
        w5_requested=True,
        w7_requested=True,
        w7_load_failed=False,
    )
    assert v.abort is False
    assert v.dark_winners == []


def test_reproduce_drb72_drb76_both_relevance_winners_dark():
    """The exact forensic failure: W6 embedder False-cached AND W5 reranker_device
    ='unavailable' on a winners-ON run => abort BEFORE generation, both surfaced."""
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "unavailable", "n_scored": 0},
        embedder_cache_sentinel=False,
        w6_requested=True,
        w5_requested=True,
        w7_requested=True,
        w7_load_failed=None,  # killed mid-retrieval, never reached
    )
    assert v.abort is True
    assert set(v.dark_winners) == {"W6_embedder", "W5_content_relevance"}
    d = v.to_dict()
    assert d["abort"] is True
    assert d["winners_checked"]["W7_reranker"] == "pending_post_seam"


# ── env-derived requested checks (default OFF path is byte-identical) ─────────
def test_default_env_no_winner_requested_no_trip(monkeypatch):
    """On the default/legacy env (no winner flags), nothing is requested even with a
    False cache + unavailable device, so the gate is a no-op (byte-identical OFF)."""
    for var in (
        "PG_EMBEDDER_MODEL",
        "PG_RERANKER_MODEL",
        "PG_CONTENT_RELEVANCE_JUDGE",
        "PG_SWEEP_CREDIBILITY_REDESIGN",
    ):
        monkeypatch.delenv(var, raising=False)
    # PG_CONTENT_RELEVANCE_JUDGE defaults ON, so force it off for the pure-legacy case.
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "0")
    # Redesign defaults 'on' but PG_EMBEDDER_MODEL unset => W6 not requested.
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "unavailable"},
        embedder_cache_sentinel=False,
    )
    assert v.abort is False


def test_slate_env_requests_winners_and_trips(monkeypatch):
    """The Gate-B slate sets PG_EMBEDDER_MODEL=qwen3 + PG_RERANKER_MODEL=qwen3 +
    PG_CONTENT_RELEVANCE_JUDGE=1 => all three requested => a False cache +
    unavailable device trips (env-derived, no explicit override)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")
    monkeypatch.setenv("PG_EMBEDDER_MODEL", "qwen3")
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "1")
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "unavailable"},
        embedder_cache_sentinel=False,
    )
    assert v.abort is True
    assert "W6_embedder" in v.dark_winners
    assert "W5_content_relevance" in v.dark_winners


def test_verdict_to_dict_shape():
    v = WinnerFiringVerdict(abort=True, dark_winners=["W6_embedder"])
    d = v.to_dict()
    assert set(d) == {"abort", "dark_winners", "diagnostics", "winners_checked"}


# ── I-deepfix-001 P1-1: W7 requested-detection (the slate sets a MODEL NAME) ──
def test_w7_requested_true_for_model_name_qwen3(monkeypatch):
    """The Gate-B slate sets PG_RERANKER_MODEL=qwen3 (a model NAME, not a boolean ON
    value). The prior `in _ON_VALUES` check read this as NOT-requested so W7 was never
    hard-gated. The fix: a non-empty, non-off value => requested."""
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")
    assert _w7_reranker_requested() is True


def test_w7_requested_true_for_full_model_path(monkeypatch):
    """An arbitrary HF model id (the production form) must also read as requested."""
    monkeypatch.setenv("PG_RERANKER_MODEL", "Qwen/Qwen3-Reranker-4B")
    assert _w7_reranker_requested() is True


@pytest.mark.parametrize("off", ["", "0", "false", "no", "off", "  off  ", "FALSE"])
def test_w7_requested_false_for_off_values(monkeypatch, off):
    """Explicit off-values (and unset) keep W7 not-requested => byte-identical OFF."""
    monkeypatch.setenv("PG_RERANKER_MODEL", off)
    assert _w7_reranker_requested() is False


def test_w7_requested_false_when_unset(monkeypatch):
    monkeypatch.delenv("PG_RERANKER_MODEL", raising=False)
    assert _w7_reranker_requested() is False


def test_w7_env_qwen3_load_failed_trips_env_derived(monkeypatch):
    """End-to-end env-derived: the slate model name requests W7, and a caller-supplied
    structural load failure trips it WITHOUT an explicit w7_requested override (proves
    the env detection wired into evaluate_winner_firing, not just the helper)."""
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "0")  # isolate W7
    monkeypatch.delenv("PG_EMBEDDER_MODEL", raising=False)  # isolate W6
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=object(),
        w7_load_failed=True,
    )
    assert v.abort is True
    assert "W7_reranker" in v.dark_winners


# ── I-deepfix-001 P1-2: semantic_fell_back trips W6 on the env-derived slate path ──
def test_semantic_fell_back_trips_w6_env_derived(monkeypatch):
    """The Gate-B slate requests W6 (PG_EMBEDDER_MODEL=qwen3 + redesign on). A recorded
    semantic->lexical fallback (the new LiveRetrievalResult.semantic_relevance_fell_back
    threaded into the gate call) must trip W6 dark even with a truthy embedder handle —
    a requested semantic winner that fell back to lexical is NOT firing."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "on")
    monkeypatch.setenv("PG_EMBEDDER_MODEL", "qwen3")
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "0")  # isolate W6
    monkeypatch.delenv("PG_RERANKER_MODEL", raising=False)  # isolate W7
    v = evaluate_winner_firing(
        content_relevance={"reranker_device": "cuda"},
        embedder_cache_sentinel=object(),  # truthy handle (loaded) — yet it fell back
        semantic_fell_back=True,
    )
    assert v.abort is True
    assert "W6_embedder" in v.dark_winners


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
