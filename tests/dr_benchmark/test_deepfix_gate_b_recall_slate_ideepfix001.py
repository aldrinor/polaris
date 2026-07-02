"""I-deepfix-001 (Codex P1) — Gate-B recall-lift slate wiring (U11) + U31 content cap.

Codex found three recall-lift fixes DARK on the Gate-B paid run because ``run_gate_b``
sets the slate env before the sweep import, so a code default that was never slate-pinned
never fired:
  * U11 evidence-type query expansion was default-OFF (never activated in the slate), the
    S2 hit cap stayed 20, and WRRF ran with NO academic-engine weights;
  * U31 raised the ``live_retriever`` content cap code default to 300000 but the slate
    pinned ``PG_LIVE_CONTENT_MAX=50000``, so long clinical papers were still truncated.

These tests assert the slate now activates each fix. Source-inspection only (offline).
"""
from __future__ import annotations

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_EXACT_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    _WINNER_FLAG_ALLOWLIST,
)


# ── P1 #2: U11 recall lift (evidence-type expansion + hit caps + WRRF weights) ──────

def test_evidence_type_query_expansion_activated():
    """The U11 kill-switch is default-OFF in code; the slate must ACTIVATE it."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE["PG_EVIDENCE_TYPE_QUERY_EXPANSION"] == "1"


def test_s2_hit_cap_raised_above_default_20():
    """DEFAULT_MAX_S2 = int(getenv('PG_LIVE_MAX_S2', '20')); U11 raises the primary-lit cap."""
    assert int(_FULL_CAPABILITY_BENCHMARK_SLATE["PG_LIVE_MAX_S2"]) >= 40


def test_domain_backend_hit_cap_raised_above_default_10():
    """PG_DOMAIN_MAX_HITS default 10; raise so europe_pmc / openalex / arxiv return more."""
    assert int(_FULL_CAPABILITY_BENCHMARK_SLATE["PG_DOMAIN_MAX_HITS"]) >= 40


def test_wrrf_weights_set_and_lift_academic_engines():
    """WRRF (W3) is enabled but shipped with no weights; the slate must weight the
    academic / clinical engines Codex named (openalex / europe_pmc / semantic_scholar)
    ABOVE generic web (serper)."""
    raw = _FULL_CAPABILITY_BENCHMARK_SLATE["PG_SEARCH_FUSION_WRRF_WEIGHTS"]
    assert raw and ":" in raw
    weights: dict[str, float] = {}
    for part in raw.split(","):
        name, _, val = part.partition(":")
        weights[name.strip().lower()] = float(val)
    serper = weights.get("serper", 1.0)
    for eng in ("openalex", "europe_pmc"):
        assert weights[eng] > serper, eng
    assert weights.get("semantic_scholar", weights.get("s2", 0.0)) > serper


def test_wrrf_weights_is_force_exact_and_allowlisted():
    """A non-numeric STRING slate value MUST be force-EXACT (else the numeric-floor path
    in apply_full_capability_benchmark_slate crashes on float()) and, being a non-numeric
    string pin, MUST be in the winners-only SLATE-PURITY allowlist (it is the config for
    the W3 WRRF fusion winner) or the run's own preflight fails closed."""
    assert "PG_SEARCH_FUSION_WRRF_WEIGHTS" in _BENCHMARK_FORCE_EXACT_FLAGS
    assert "PG_SEARCH_FUSION_WRRF_WEIGHTS" in _WINNER_FLAG_ALLOWLIST


# ── P1 #3: U31 content cap (no more 50k truncation of long clinical papers) ──────────

def test_live_content_max_matches_u31_default():
    """The slate previously pinned 50000, ACTIVELY truncating below the U31 code default
    (DEFAULT_CONTENT_MAX_CHARS = getenv('PG_LIVE_CONTENT_MAX', '300000')). Match it."""
    assert int(_FULL_CAPABILITY_BENCHMARK_SLATE["PG_LIVE_CONTENT_MAX"]) >= 300000
