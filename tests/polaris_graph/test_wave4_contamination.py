"""I-deepfix-001 Wave-4 CONTAMINATION (#1344) — RED/GREEN unit tests for the drb_72 SCOPE/DATE
contamination kill (a wrong OpenAlex title-search paper fooled the pub-date/window screen; general-web
/ PDF sources arrived UNDATED). Three additive, faithfulness-NEUTRAL, default-OFF levers:

  (A) PG_OPENALEX_MATCH_VALIDATE — validate the OpenAlex title-SEARCH work actually matches OUR source
      (DOI agreement OR title-token overlap) BEFORE attaching its metadata. On MISMATCH the enrichment
      is WITHHELD (``_openalex_enrich`` returns {}) so the source keeps its own weight (§-1.3
      demote-not-drop). The exact /works/doi path stays TRUSTED. Default OFF => byte-identical.
  (B) AUTHORITY_CACHE_SCHEMA_VERSION bumped 3 -> 4 so pre-validation cache entries are re-fetched.
  (C) PG_RESOLVE_PUBDATE_FROM_HTML — ACTIVATE the DARK publication_date_resolver at the row-build seam:
      fill a date from ALREADY-fetched content when the source's OpenAlex date is missing/unreliable.
      FAIL-OPEN (a resolver fault leaves the row date unchanged, never masks a source). Default OFF.

Plus the run_gate_b activation canary contract: the two HONEST realized-effect markers
(``openalex_match_validate: checked=N rejected=N`` / ``pubdate_html_resolve: resolved=N unresolved=N``)
are ACCEPTED at count=0 (ran-ok-zero, §-1.3 never gate on a count) and REJECTED on the distinct
``unavailable_failopen`` degrade / when the flag is ON but no marker fired (dark).

Imports are narrow (no heavy models / no live network): the OpenAlex HTTP client is monkeypatched, the
date resolver is stubbed, and the canary is pure string logic.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.polaris_graph.retrieval import live_retriever as lr

# The canary lives in run_gate_b; importing it is offline (no client/socket at import). Bootstrap the
# repo root onto sys.path exactly like the sibling test_wave3_coverage.py so the import resolves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.environ.setdefault("PG_VERIFICATION_MODE", "off")  # deterministic import, no judge calls

import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles: a fake OpenAlex HTTP client (no network) for _openalex_enrich.
# ─────────────────────────────────────────────────────────────────────────────
class _FakeResp:
    def __init__(self, status: int, payload: dict) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _install_fake_openalex(monkeypatch, work: dict, *, doi_status: int = 200) -> list:
    """Stub the enrich's cache + /sources fetch + httpx client so ``_openalex_enrich`` runs offline.

    The fake ``.get`` returns ``work`` as a single-work response for the exact ``/doi:`` lookup and as
    ``{"results": [work]}`` for the title-SEARCH endpoint. Returns the list of ``_authority_cache_put``
    calls so a test can assert a WITHHELD (rejected) match is NOT cached."""
    monkeypatch.setattr(lr, "_authority_cache_get", lambda key: None)
    puts: list = []
    monkeypatch.setattr(lr, "_authority_cache_put", lambda key, payload: puts.append((key, payload)))
    monkeypatch.setattr(lr, "_openalex_fetch_source", lambda c, source_id: {})

    class _FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            if "/doi:" in url:
                return _FakeResp(doi_status, work)
            return _FakeResp(200, {"results": [work]})

    monkeypatch.setattr(lr.httpx, "Client", _FakeClient)
    return puts


# ═════════════════════════════════════════════════════════════════════════════
# (A) PG_OPENALEX_MATCH_VALIDATE — the pure title-search match validator
# ═════════════════════════════════════════════════════════════════════════════
def test_a_validate_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_OPENALEX_MATCH_VALIDATE", raising=False)
    assert lr._openalex_match_validate_enabled() is False
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    assert lr._openalex_match_validate_enabled() is True
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "0")
    assert lr._openalex_match_validate_enabled() is False


def test_a_wrong_title_search_match_rejected():
    """A search that surfaced a DIFFERENT paper (few shared content tokens, no DOI agreement) is a
    MISMATCH — the validator returns False so the caller WITHHOLDS the wrong metadata."""
    work = {"display_name": "Blockchain provenance in agricultural supply chains", "doi": ""}
    assert lr._openalex_search_match_ok(
        our_title="Generative AI and the future of work in call centers",
        our_doi="", work=work,
    ) is False


def test_a_truncated_correct_title_matches():
    """A correct-but-TRUNCATED source title is a near-subset of the full OpenAlex display_name (overlap
    coefficient ≈ 1.0) — the validator returns True (a legitimate match is never withheld)."""
    work = {
        "display_name": "Generative AI and the future of work in call centers: a field experiment",
        "doi": "",
    }
    assert lr._openalex_search_match_ok(
        our_title="Generative AI future work call centers", our_doi="", work=work,
    ) is True


def test_a_doi_agreement_trusts_despite_title_divergence():
    """DOI agreement is the strongest signal: even if the titles read differently (formatting / variant),
    an exact DOI match confirms the paper — validator returns True."""
    work = {"display_name": "A totally different-looking title string", "doi": "https://doi.org/10.1000/xyz"}
    assert lr._openalex_search_match_ok(our_title="mismatch", our_doi="10.1000/XYZ", work=work) is True


def test_a_unvalidatable_no_title_no_doi_is_withheld():
    """No comparable title on either side AND no DOI agreement => the match is UNVALIDATABLE => False so
    the caller WITHHOLDS (§-1.3 demote the unconfirmable metadata's trust, keep the source)."""
    work = {"display_name": "", "doi": ""}
    assert lr._openalex_search_match_ok(our_title="", our_doi="", work=work) is False


def test_a_threshold_is_env_overridable(monkeypatch):
    """LAW VI: the overlap threshold is env-overridable. A borderline overlap that passes at 0.5 is
    REJECTED when the operator raises PG_OPENALEX_MATCH_MIN_TITLE_OVERLAP to 0.95."""
    work = {"display_name": "diabetes glp1 receptor agonists cardiovascular outcomes elderly patients",
            "doi": ""}
    our = "diabetes glp1 receptor agonists renal"  # shares 3 of 4 content tokens
    assert lr._openalex_search_match_ok(our_title=our, our_doi="", work=work, min_overlap=0.5) is True
    monkeypatch.setenv("PG_OPENALEX_MATCH_MIN_TITLE_OVERLAP", "0.95")
    assert lr._openalex_search_match_ok(our_title=our, our_doi="", work=work) is False


def test_a_explicit_doi_conflict_rejected_despite_title_overlap():
    """Wave-4 Issue-2 (#1344): a KNOWN DOI CONFLICT — our DOI and the returned work's DOI are BOTH present
    and DIFFERENT — is a HARD NEGATIVE for the mis-attach class. Even when the titles overlap strongly
    (coefficient ≈ 1.0, e.g. a DOI-fallback search that surfaced a same-topic-but-different paper), the
    conflicting DOI must short-circuit to False BEFORE title-overlap validation."""
    work = {
        "display_name": "Generative AI and the future of work in call centers: a field experiment",
        "doi": "https://doi.org/10.9999/different-paper",
    }
    assert lr._openalex_search_match_ok(
        our_title="Generative AI future work call centers",
        our_doi="10.1000/our-real-paper", work=work,
    ) is False


def test_a_doi_conflict_still_trusts_exact_agreement():
    """Guard on Issue-2: the conflict-reject must NOT fire when the DOIs AGREE (scheme/case differ only) —
    exact DOI agreement remains the strongest positive signal and returns True."""
    work = {"display_name": "unrelated-looking title", "doi": "HTTPS://DOI.ORG/10.1000/Same"}
    assert lr._openalex_search_match_ok(
        our_title="whatever", our_doi="10.1000/same", work=work,
    ) is True


def test_a_enrich_withholds_wrong_title_search_but_does_not_cache(monkeypatch):
    """END-TO-END (A): with the flag ON, a title-SEARCH enrich that returns a WRONG paper is WITHHELD
    (``_openalex_enrich`` returns {} — the source keeps its own weight, §-1.3), the checked+rejected
    counters increment, and the withheld {} is NOT written to the authority cache (no stale contamination)."""
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    work = {"display_name": "Blockchain provenance in agricultural supply chains 2019",
            "doi": "", "id": "https://openalex.org/W_wrong", "publication_year": 2019}
    puts = _install_fake_openalex(monkeypatch, work)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich(
        "https://www.example.org/news/genai-jobs",  # no embedded DOI => title-search path
        "Generative AI and the future of work in call centers",
    )
    snap1 = lr._match_validate_snapshot()
    assert out == {}  # metadata WITHHELD (the 2019 mis-attach class is not attached)
    assert snap1["checked"] - snap0["checked"] == 1
    assert snap1["rejected"] - snap0["rejected"] == 1
    assert puts == []  # withheld result is NOT cached


def test_a_enrich_trusts_exact_doi_no_validation(monkeypatch):
    """END-TO-END (A): the exact /works/doi path is TRUSTED — never validated. With the flag ON, a
    DOI-embedded URL attaches the OpenAlex metadata (returns non-empty carrying the work's title) and the
    checked counter does NOT increment (the search-only validator never runs on the exact path)."""
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    work = {"display_name": "The real indexed paper", "doi": "https://doi.org/10.1000/real",
            "id": "https://openalex.org/W_real", "type": "article", "publication_year": 2022,
            "publication_date": "2022-05-10"}
    _install_fake_openalex(monkeypatch, work)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich("https://doi.org/10.1000/real", "irrelevant title")
    snap1 = lr._match_validate_snapshot()
    assert out  # metadata ATTACHED (trusted DOI path)
    assert out.get("openalex_full_title") == "The real indexed paper"
    assert snap1["checked"] - snap0["checked"] == 0  # exact-DOI path is never validated


def test_a_enrich_off_is_byte_identical_attaches_even_wrong_match(monkeypatch):
    """OFF byte-identical: with the flag OFF the wrong title-search paper's metadata is attached exactly
    as before (no validation, no withhold) — the pre-Wave-4 behaviour is unchanged."""
    monkeypatch.delenv("PG_OPENALEX_MATCH_VALIDATE", raising=False)
    work = {"display_name": "Blockchain provenance in agricultural supply chains 2019",
            "doi": "", "id": "https://openalex.org/W_wrong", "publication_year": 2019}
    _install_fake_openalex(monkeypatch, work)
    out = lr._openalex_enrich(
        "https://www.example.org/news/genai-jobs",
        "Generative AI and the future of work in call centers",
    )
    assert out  # OFF path attaches (byte-identical to the pre-validation behaviour)
    assert out.get("openalex_full_title") == "Blockchain provenance in agricultural supply chains 2019"


# ─────────────────────────────────────────────────────────────────────────────
# (A) Issue-1: VALIDATION-AWARE cache read — a stale UNvalidated v4 cache hit is
# revalidated (or exact-DOI-trusted) on read so a force-ON run cannot serve wrong
# metadata with a false-green checked=0/rejected=0 canary.
# ─────────────────────────────────────────────────────────────────────────────
def _install_cache_hit(monkeypatch, cached_payload: dict) -> None:
    """Stub the authority cache to HIT with ``cached_payload`` and make the httpx client EXPLODE if the
    enrich ever falls through to the network — a cache hit (attach OR withhold) must be decided offline
    from the frozen payload, never a fresh round-trip."""
    monkeypatch.setattr(lr, "_authority_cache_get", lambda key: dict(cached_payload))
    monkeypatch.setattr(lr, "_authority_cache_put", lambda key, payload: None)

    class _NoNetClient:
        def __init__(self, *a, **k) -> None:
            raise AssertionError("a cache hit must not open a network client")

    monkeypatch.setattr(lr.httpx, "Client", _NoNetClient)


def test_a_cache_hit_revalidated_withholds_contaminated_entry(monkeypatch):
    """END-TO-END (Issue-1): with the flag ON, a CACHE HIT carrying UNvalidated title-search metadata (a
    prior flag-OFF run cached a WRONG 2019 paper as v4) is REVALIDATED on read — no DOI agreement + zero
    title overlap => WITHHELD ({}, the source keeps its own weight, §-1.3) and checked+rejected increment.
    This kills the false-green where the force-ON run served the stale cache hit with checked=0/rejected=0."""
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    cached = {"openalex_full_title": "Blockchain provenance in agricultural supply chains 2019",
              "doi": "", "openalex_id": "https://openalex.org/W_wrong", "is_peer_reviewed": True}
    _install_cache_hit(monkeypatch, cached)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich(
        "https://www.example.org/news/genai-jobs",  # no embedded DOI => title-search-derived cache entry
        "Generative AI and the future of work in call centers",
    )
    snap1 = lr._match_validate_snapshot()
    assert out == {}  # stale wrong metadata WITHHELD on read
    assert snap1["checked"] - snap0["checked"] == 1
    assert snap1["rejected"] - snap0["rejected"] == 1


def test_a_cache_hit_doi_agreement_trusted_not_revalidated(monkeypatch):
    """Issue-1 guard: a CACHE HIT whose cached DOI AGREES with the url-embedded DOI is the exact-DOI path —
    TRUSTED, never revalidated. The cached metadata is served (non-empty) and checked does NOT increment,
    so a legitimate exact-DOI cache entry is never withheld and the exact-DOI-trust invariant holds on read."""
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    cached = {"openalex_full_title": "The real indexed paper", "doi": "10.1000/real",
              "openalex_id": "https://openalex.org/W_real", "is_peer_reviewed": True}
    _install_cache_hit(monkeypatch, cached)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich("https://doi.org/10.1000/real", "irrelevant title")
    snap1 = lr._match_validate_snapshot()
    assert out.get("openalex_full_title") == "The real indexed paper"  # served (exact-DOI trusted)
    assert snap1["checked"] - snap0["checked"] == 0  # exact-DOI cache hit is never validated


def test_a_cache_hit_legit_title_match_served(monkeypatch):
    """Issue-1: a CACHE HIT that is a LEGITIMATE title-search match (our truncated title is a near-subset of
    the cached full display_name, no DOI on either side) REVALIDATES and PASSES — the metadata is served
    (a correct cached entry is never withheld); checked increments (honest liveness) but rejected does not."""
    monkeypatch.setenv("PG_OPENALEX_MATCH_VALIDATE", "1")
    cached = {"openalex_full_title": "Generative AI and the future of work in call centers: a field study",
              "doi": "", "openalex_id": "https://openalex.org/W_ok"}
    _install_cache_hit(monkeypatch, cached)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich(
        "https://www.example.org/news/genai-jobs",
        "Generative AI future work call centers",
    )
    snap1 = lr._match_validate_snapshot()
    assert out.get("openalex_full_title") == "Generative AI and the future of work in call centers: a field study"
    assert snap1["checked"] - snap0["checked"] == 1
    assert snap1["rejected"] - snap0["rejected"] == 0


def test_a_cache_hit_off_is_byte_identical_serves_contaminated_entry(monkeypatch):
    """OFF byte-identical: with the flag OFF a CACHE HIT is served exactly as before — even a contaminated
    title-search entry is returned unchanged and the validator counters do NOT move (no read-path validation)."""
    monkeypatch.delenv("PG_OPENALEX_MATCH_VALIDATE", raising=False)
    cached = {"openalex_full_title": "Blockchain provenance in agricultural supply chains 2019",
              "doi": "", "openalex_id": "https://openalex.org/W_wrong"}
    _install_cache_hit(monkeypatch, cached)
    snap0 = lr._match_validate_snapshot()
    out = lr._openalex_enrich(
        "https://www.example.org/news/genai-jobs",
        "Generative AI and the future of work in call centers",
    )
    snap1 = lr._match_validate_snapshot()
    assert out.get("openalex_full_title") == "Blockchain provenance in agricultural supply chains 2019"
    assert snap1["checked"] - snap0["checked"] == 0  # OFF: cache read never validates


# ═════════════════════════════════════════════════════════════════════════════
# (B) AUTHORITY_CACHE_SCHEMA_VERSION bumped 3 -> 4
# ═════════════════════════════════════════════════════════════════════════════
def test_b_authority_cache_schema_version_bumped_to_4():
    """The single-constant bump invalidates every enrich payload written under the pre-validation match
    logic so a cached WRONG-paper row is re-fetched (and re-validated) rather than served stale."""
    assert lr.AUTHORITY_CACHE_SCHEMA_VERSION == 4


# ═════════════════════════════════════════════════════════════════════════════
# (C) PG_RESOLVE_PUBDATE_FROM_HTML — ACTIVATE the dark resolver at the row-build seam
# ═════════════════════════════════════════════════════════════════════════════
def test_c_resolve_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_RESOLVE_PUBDATE_FROM_HTML", raising=False)
    assert lr._resolve_pubdate_from_html_enabled() is False
    monkeypatch.setenv("PG_RESOLVE_PUBDATE_FROM_HTML", "1")
    assert lr._resolve_pubdate_from_html_enabled() is True
    monkeypatch.setenv("PG_RESOLVE_PUBDATE_FROM_HTML", "0")
    assert lr._resolve_pubdate_from_html_enabled() is False


def test_c_resolvable_html_date_is_used():
    """A resolvable JSON-LD ``datePublished`` fills BOTH the month-precision ``pub_date`` and the
    ``pub_year`` on an otherwise-undated row (resolved=True)."""
    html = '<script type="application/ld+json">{"datePublished":"2022-05-10"}</script>'
    pub_date, pub_year, resolved, failopen = lr._resolve_row_pubdate_backfill(
        content=html, jsonld="", url="https://x/a", metadata=None, pub_date=None, pub_year=None,
    )
    assert (pub_date, pub_year) == ("2022-05", 2022)
    assert resolved is True and failopen is False


def test_c_resolver_failure_fails_open_source_unchanged(monkeypatch):
    """FAIL-OPEN: if the resolver raises, BOTH date fields are left UNCHANGED (an undated source is never
    masked, §-1.3) and failopen=True (so the distinct degrade marker fires)."""
    def _boom(**_k):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(lr, "resolve_publication_date", _boom)
    pub_date, pub_year, resolved, failopen = lr._resolve_row_pubdate_backfill(
        content="whatever", jsonld="", url="https://x/a", metadata=None,
        pub_date=None, pub_year=2021,
    )
    assert (pub_date, pub_year) == (None, 2021)  # unchanged (source's existing handling preserved)
    assert resolved is False and failopen is True


def test_c_unresolvable_leaves_row_undated():
    """Nothing structured to find => the row stays honestly UNDATED (None, None), resolved=False,
    failopen=False (a clean ran-ok-zero, not a fault)."""
    pub_date, pub_year, resolved, failopen = lr._resolve_row_pubdate_backfill(
        content="no date anywhere in this body", jsonld="", url="https://x/a",
        metadata=None, pub_date=None, pub_year=None,
    )
    assert (pub_date, pub_year) == (None, None)
    assert resolved is False and failopen is False


def test_c_does_not_override_existing_month_pub_date():
    """When the row ALREADY carries a month-precision pub_date the seam does not even call the resolver
    (its guard is ``_pub_date is None``); the helper here likewise never overwrites an existing pub_date."""
    html = '<script type="application/ld+json">{"datePublished":"2000-01-01"}</script>'
    pub_date, pub_year, _r, _f = lr._resolve_row_pubdate_backfill(
        content=html, jsonld="", url="https://x/a", metadata=None,
        pub_date="2022-06", pub_year=2022,
    )
    assert pub_date == "2022-06"  # existing OpenAlex month-precision date preserved


# ═════════════════════════════════════════════════════════════════════════════
# Activation-canary contract for BOTH new markers (run_gate_b)
# ═════════════════════════════════════════════════════════════════════════════
_LOG_PREFIX = "2026-07-06 12:00:00,000 INFO src.polaris_graph - "


def _run_canary(monkeypatch, on_flag: str, *marker_lines):
    """Drive rg.assert_activation_markers_fired over a run-log carrying ``marker_lines`` with the canary
    opt-in + ``on_flag`` ON and every SIBLING coverage/contamination flag OFF, so ONLY ``on_flag``'s spec
    is asserted (every other module flag defaults OFF => self-scoped out)."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.setenv(on_flag, "1")
    for sibling in (
        "PG_OPENALEX_MATCH_VALIDATE", "PG_RESOLVE_PUBDATE_FROM_HTML",
        "PG_OPENALEX_DATE_FILTER", "PG_LANDMARK_EXPANDER",
    ):
        if sibling != on_flag:
            monkeypatch.delenv(sibling, raising=False)
    monkeypatch.delenv("PG_QGEN_PARALLEL_QUERIES", raising=False)  # numeric spec self-skips (<2)
    if on_flag != "PG_RENDER_SUMMARY_TABLE":
        # summary_table is DEFAULT-ON (flag_default_on) — an UNSET flag stays ON and would over-demand its
        # marker on these no-table logs; set explicit "0" (delenv would leave the default-on path ON).
        monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
        monkeypatch.setenv("PG_DEBATE_CON_BASKET_CONSOLIDATION", "0")  # default-ON sibling (Wave-9 P1): explicit OFF
    log_text = "".join(_LOG_PREFIX + m + "\n" for m in marker_lines)
    rg.assert_activation_markers_fired(log_text)


# ── (A) openalex_match_validate ──────────────────────────────────────────────
def test_canary_accepts_ran_ok_zero_match_validate(monkeypatch):
    """§-1.3 no-threshold: checked=0 rejected=0 (every enrich was an exact-DOI / cache hit, nothing to
    validate) is an ACCEPTED eligible-yet-zero fire — the canary must NOT raise."""
    _run_canary(monkeypatch, "PG_OPENALEX_MATCH_VALIDATE",
                "[activation] openalex_match_validate: checked=0 rejected=0")


def test_canary_accepts_nonzero_match_validate(monkeypatch):
    _run_canary(monkeypatch, "PG_OPENALEX_MATCH_VALIDATE",
                "[activation] openalex_match_validate: checked=7 rejected=2")


def test_canary_rejects_absent_match_validate(monkeypatch):
    """Flag ON but no positive marker => the validator went dark => the canary RAISES (MARKER ABSENT)."""
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "PG_OPENALEX_MATCH_VALIDATE",
                    "[activation] some_other_module: fired")


def test_canary_rejects_failopen_match_validate(monkeypatch):
    """The distinct ``unavailable_failopen`` degrade marker (a validator FAULT) must FAIL the canary even
    though the positive marker co-occurs (belt-and-suspenders on the OLD/DEGRADE-MARKER-PRESENT leg)."""
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "PG_OPENALEX_MATCH_VALIDATE",
                    "[activation] openalex_match_validate: checked=3 rejected=1",
                    "[activation] openalex_match_validate: unavailable_failopen")


# ── (C) pubdate_html_resolve ─────────────────────────────────────────────────
def test_canary_accepts_ran_ok_zero_pubdate(monkeypatch):
    """§-1.3 no-threshold: resolved=0 unresolved=0 (every fetched row already carried a reliable date)
    is an ACCEPTED eligible-yet-zero fire — the canary must NOT raise."""
    _run_canary(monkeypatch, "PG_RESOLVE_PUBDATE_FROM_HTML",
                "[activation] pubdate_html_resolve: resolved=0 unresolved=0")


def test_canary_accepts_nonzero_pubdate(monkeypatch):
    _run_canary(monkeypatch, "PG_RESOLVE_PUBDATE_FROM_HTML",
                "[activation] pubdate_html_resolve: resolved=12 unresolved=40")


def test_canary_rejects_absent_pubdate(monkeypatch):
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "PG_RESOLVE_PUBDATE_FROM_HTML",
                    "[activation] some_other_module: fired")


def test_canary_rejects_failopen_pubdate(monkeypatch):
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "PG_RESOLVE_PUBDATE_FROM_HTML",
                    "[activation] pubdate_html_resolve: resolved=5 unresolved=3",
                    "[activation] pubdate_html_resolve: unavailable_failopen")


# ═════════════════════════════════════════════════════════════════════════════
# ANTI-DARK slate wiring: both flags quad-pinned; canary specs registered.
# ═════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("flag", ["PG_OPENALEX_MATCH_VALIDATE", "PG_RESOLVE_PUBDATE_FROM_HTML"])
def test_flag_quad_pinned_into_all_four_slate_structures(flag):
    """Each BOOLEAN contamination-kill flag is quad-wired: slate "1" + FORCE_ON + REQUIRED + ALLOWLIST,
    so a stray operator/.env =0 fails the run CLOSED before spend and SLATE-PURITY still passes."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert flag in rg._WINNER_FLAG_ALLOWLIST


def test_slate_purity_still_clean_after_wave4():
    """Every force-on flag maps to an allowlist entry — no SLATE-PURITY impurity introduced by Wave-4."""
    unrecognized = sorted(set(rg._BENCHMARK_FORCE_ON_FLAGS) - set(rg._WINNER_FLAG_ALLOWLIST))
    assert unrecognized == []


def test_canary_specs_registered_in_wave3_registry():
    """Both markers are registered as run_gate_b activation specs with the whitelist producer predicate,
    a positive count-shaped regex (checked=0 / resolved=0 must pass), and the failopen degrade tripwire."""
    by_name = {s.name: s for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}
    assert "openalex_match_validate" in by_name
    assert "pubdate_html_resolve" in by_name
    mv = by_name["openalex_match_validate"]
    assert mv.env_flag == "PG_OPENALEX_MATCH_VALIDATE"
    assert mv.flag_whitelist == ("1", "true", "on", "yes")
    assert mv.bool_checks == () and mv.exact_fields == ()  # never a count>0 gate (ran-ok-zero passes)
    assert mv.positive_re.search("[activation] openalex_match_validate: checked=0 rejected=0")
    assert mv.absent_markers == ("[activation] openalex_match_validate: unavailable_failopen",)
    pd = by_name["pubdate_html_resolve"]
    assert pd.env_flag == "PG_RESOLVE_PUBDATE_FROM_HTML"
    assert pd.flag_whitelist == ("1", "true", "on", "yes")
    assert pd.bool_checks == () and pd.exact_fields == ()
    assert pd.positive_re.search("[activation] pubdate_html_resolve: resolved=0 unresolved=0")
    assert pd.absent_markers == ("[activation] pubdate_html_resolve: unavailable_failopen",)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
