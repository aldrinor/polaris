"""S1.b RETRIEVE — breadth resolver + scope->wording + scope->backend-filter contract.

Proves the offline-testable half of the Design 7 §3 lock-down bar (bar #1 budget resolution +
byte-identity; the LIVE union-firing proof is the VM search-only hamster, not this test):

  * breadth resolver: class-per-probe sizing, explicit-env-beats-class, RunConfig-beats-env
    (R9 forward path via a duck-typed mock), abs-ceiling clamp, structural-width class, and
    flag-OFF is a no-op (the spine keeps its raw env reads => 35/12/12/200 byte-identical).
  * scope_directives: the SCOPE DIRECTIVES block wording (D2) and the ADDITIVE backend params
    (D3 — Serper tbs/gl/hl, S2 year/publicationTypes, OpenAlex language/author), plus fail-open
    on garbage input and empty-scope byte-identity.

Fixtures mirror the EXACT dict shapes the scope gate writes into protocol.json:
``UserConstraints.to_dict()`` and ``ScopeConstraints.to_dict()`` (no object-vs-dict drift).
"""

from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import breadth_resolver as br
from src.polaris_graph.retrieval import scope_directives as sd


# ─────────────────────────────────────────────────────────────────────────────
# fixtures — exact protocol.json scope dict shapes
# ─────────────────────────────────────────────────────────────────────────────


def _uc(**over):
    """A UserConstraints.to_dict()-shaped dict (all keys present, like the real to_dict)."""
    base = {
        "date_start_year": None, "date_end_year": None,
        "date_start_month": None, "date_end_month": None,
        "date_start_iso": None, "date_end_iso": None,
        "language": None, "journal_only_dormant": False,
        "timeline_strictness": "weight", "timeline_trigger_span": "",
        "raw_directives": [], "source": "regex",
    }
    base.update(over)
    return base


def _facet(facet_id, dimension, op="prefer", strictness="weight"):
    return {"facet_id": facet_id, "dimension": dimension, "op": op,
            "strictness": strictness, "trigger_span": "", "source": "regex"}


def _sc(facets=None, named_include=None):
    return {
        "facets": facets or [],
        "named_include": named_include or [],
        "named_exclude": [],
        "source": "regex",
    }


# A dated + geo + language + peer-reviewed + named-author scope (the STANDARD scoped probe).
_UC_DATED = _uc(
    date_start_year=2019, date_end_year=2023, date_end_month=6,
    date_start_iso="2019-01-01", date_end_iso="2023-06", language="en",
)
_SC_FULL = _sc(
    facets=[_facet("jurisdiction:US", "geography", op="include"),
            _facet("peer_reviewed_journal", "source_type", op="prefer")],
    named_include=[{"label": "Jane Smith", "op": "include", "strictness": "weight",
                    "identity": {"openalex_author_id": "A5023888391"}, "source": "regex"}],
)


class _MockRunConfig:
    """Duck-typed RunConfig stand-in (WAVE-0 run_config.py not built yet): ``.get(knob_id)`` returns
    a rich ``{'value': N}`` mapping, exactly the shape the resolver must tolerate (R9 forward path)."""

    def __init__(self, values):
        self._values = values

    def get(self, knob_id):
        v = self._values.get(knob_id)
        return {"value": v, "source": "panel"} if v is not None else None


# ─────────────────────────────────────────────────────────────────────────────
# breadth resolver
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_breadth_env(monkeypatch):
    """Every breadth knob env unset by default so a leaked shell/.env value never skews a case."""
    for var in ("PG_BREADTH_RESOLVER", "PG_BREADTH_CLASS",
                "PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "PG_SWEEP_MAX_SERPER",
                "PG_SWEEP_MAX_S2", "PG_SERPER_TOTAL_PER_QUERY", "PG_SWEEP_FETCH_CAP",
                "PG_QGEN_FS_RESEARCHER_MAX_QUERIES_ABS_MAX", "PG_SWEEP_MAX_SERPER_ABS_MAX",
                "PG_SWEEP_MAX_S2_ABS_MAX", "PG_SWEEP_FETCH_CAP_ABS_MAX"):
        monkeypatch.delenv(var, raising=False)
    yield


def test_flag_off_is_a_noop_default():
    assert br.breadth_resolver_enabled() is False


def test_flag_on_toggles(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_RESOLVER", "1")
    assert br.breadth_resolver_enabled() is True


@pytest.mark.parametrize(
    "cls,q,serper_total,fetch_cap",
    [("NARROW", 15, 20, 120), ("STANDARD", 35, 60, 300), ("WIDE", 80, 100, 740)],
)
def test_class_sizing_per_probe(monkeypatch, cls, q, serper_total, fetch_cap):
    monkeypatch.setenv("PG_BREADTH_CLASS", cls)
    plan = br.resolve_breadth("some question", protocol={}, facets=None, run_config=None)
    assert plan.breadth_class == cls
    assert plan.class_source == "env"
    assert plan.query_budget == q
    assert plan.serper_total == serper_total
    assert plan.fetch_cap == fetch_cap
    # serper_k / s2_k held at the historical default across every class (no invented number).
    assert plan.serper_k == 12
    assert plan.s2_k == 12


def test_default_class_is_standard_when_no_signal():
    plan = br.resolve_breadth("q", protocol={}, facets=None, run_config=None)
    assert plan.breadth_class == "STANDARD"
    assert plan.class_source == "default"


def test_explicit_env_beats_class(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_CLASS", "WIDE")   # WIDE fetch_cap would be 740
    monkeypatch.setenv("PG_SWEEP_FETCH_CAP", "999")  # explicit env wins for this knob
    plan = br.resolve_breadth("q", protocol={}, facets=None, run_config=None)
    assert plan.fetch_cap == 999
    assert plan.resolutions["fetch_cap"].source == "env"
    # the un-pinned knobs still come from the WIDE class.
    assert plan.query_budget == 80
    assert plan.resolutions["query_budget"].source == "class:WIDE"


def test_run_config_beats_env(monkeypatch):
    """R9 forward path: a panel/CLI override (RunConfig) beats even an explicit env slate value."""
    monkeypatch.setenv("PG_SWEEP_FETCH_CAP", "999")
    rc = _MockRunConfig({"fetch_cap": 50})
    plan = br.resolve_breadth("q", protocol={}, facets=None, run_config=rc)
    assert plan.fetch_cap == 50
    assert plan.resolutions["fetch_cap"].source == "run_config"


def test_abs_ceiling_clamps_loud(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_FETCH_CAP", "999")
    monkeypatch.setenv("PG_SWEEP_FETCH_CAP_ABS_MAX", "500")
    plan = br.resolve_breadth("q", protocol={}, facets=None, run_config=None)
    assert plan.fetch_cap == 500
    assert plan.resolutions["fetch_cap"].source.endswith("+clamped")


def test_structural_width_wide_on_many_facets():
    plan = br.resolve_breadth("q", protocol={}, facets=list(range(9)), run_config=None)
    assert plan.breadth_class == "WIDE"
    assert plan.class_source == "structural"


def test_structural_width_narrow_on_few_facets():
    plan = br.resolve_breadth("q", protocol={}, facets=list(range(2)), run_config=None)
    assert plan.breadth_class == "NARROW"


def test_structural_width_wide_on_long_window():
    proto = {"user_constraints": {"date_start_year": 2000, "date_end_year": 2024}}
    plan = br.resolve_breadth("q", protocol=proto, facets=list(range(2)), run_config=None)
    assert plan.breadth_class == "WIDE"  # 24-year window widens even with few facets


def test_plan_is_disclosable():
    plan = br.resolve_breadth("q", protocol={}, facets=None, run_config=None)
    d = plan.to_dict()
    assert set(d) >= {"query_budget", "serper_k", "s2_k", "fetch_cap", "breadth_class",
                      "class_source", "rationale", "resolutions"}
    assert d["resolutions"]["query_budget"]["env_var"] == "PG_QGEN_FS_RESEARCHER_MAX_QUERIES"


# ─────────────────────────────────────────────────────────────────────────────
# scope -> query wording (D2)
# ─────────────────────────────────────────────────────────────────────────────


def test_scope_block_carries_every_directive():
    block = sd.scope_directives_block(_UC_DATED, _SC_FULL)
    assert "SCOPE DIRECTIVES" in block
    assert "2019-01-01" in block and "2023-06" in block
    assert "prefer en" in block
    assert "jurisdiction:US" in block
    assert "peer_reviewed_journal" in block
    assert "Jane Smith" in block


def test_scope_block_empty_when_no_scope():
    assert sd.scope_directives_block(_uc(), _sc()) == ""


def test_scope_block_fail_open_on_garbage():
    assert sd.scope_directives_block("not-a-dict", 12345) == ""


# ─────────────────────────────────────────────────────────────────────────────
# scope -> backend filters (D3) — verified API formats
# ─────────────────────────────────────────────────────────────────────────────


def test_serper_scope_params_date_geo_lang():
    p = sd.serper_scope_params(_UC_DATED, _SC_FULL)
    assert p["tbs"] == "cdr:1,cd_min:01/01/2019,cd_max:06/30/2023"
    assert p["gl"] == "us"
    assert p["hl"] == "en"


def test_serper_scope_params_empty_when_no_scope():
    assert sd.serper_scope_params(_uc(), _sc()) == {}


def test_s2_scope_params_year_and_pubtypes():
    p = sd.s2_scope_params(_UC_DATED, _SC_FULL)
    assert p["year"] == "2019-2023"
    assert p["publicationTypes"] == "JournalArticle"


def test_s2_scope_params_open_ended_year():
    assert sd.s2_scope_params(_uc(date_start_year=2020), _sc())["year"] == "2020-"
    assert sd.s2_scope_params(_uc(date_end_year=2020), _sc())["year"] == "-2020"


def test_s2_no_pubtypes_without_peer_reviewed_facet():
    p = sd.s2_scope_params(_UC_DATED, _sc())
    assert "publicationTypes" not in p


def test_openalex_scope_params_language_and_author():
    p = sd.openalex_scope_params(_UC_DATED, _SC_FULL)
    assert p["language"] == "en"
    assert p["author"] == "A5023888391"


def test_openalex_scope_params_no_author_without_id():
    sc = _sc(named_include=[{"label": "No Id Person", "op": "include", "strictness": "weight",
                             "identity": {"host": "example.org"}, "source": "regex"}])
    p = sd.openalex_scope_params(_uc(language="fr"), sc)
    assert p == {"language": "fr"}


def test_backend_params_fail_open_on_garbage():
    assert sd.serper_scope_params("x", 1) == {}
    assert sd.s2_scope_params("x", 1) == {}
    assert sd.openalex_scope_params("x", 1) == {}


def test_activation_marker():
    assert sd.activation_marker("serper", {"gl": "us"}).startswith("[activation] scope_serper: fired")
    assert "eligible_no_scope" in sd.activation_marker("serper", {})


# ─────────────────────────────────────────────────────────────────────────────
# wiring OFF-path byte-identity (the seam helpers leave the legacy path unchanged)
# ─────────────────────────────────────────────────────────────────────────────


def test_qgen_with_scope_off_is_byte_identical():
    from src.polaris_graph.retrieval.fs_researcher_query_gen import _with_scope
    prompt = "Write ONE search query for this sub-topic. Query only.\n\ndiabetes"
    assert _with_scope(prompt, None) == prompt
    assert _with_scope(prompt, "") == prompt
    assert _with_scope(prompt, "   ") == prompt
    assert _with_scope(prompt, "SCOPE DIRECTIVES") == prompt + "\n\nSCOPE DIRECTIVES"


def test_openalex_scope_filter_none_when_no_bound():
    from src.polaris_graph.retrieval.domain_backends import _openalex_scope_filter
    # all bounds absent => None => no `filter` param attached => byte-identical legacy request.
    assert _openalex_scope_filter(None, None, None, None) is None
    # date-only caller (scope flag OFF => language/author None) matches the legacy date filter.
    assert _openalex_scope_filter("2019-01-01", "2023-06-30", None, None) == (
        "from_publication_date:2019-01-01,to_publication_date:2023-06-30"
    )


def test_live_retriever_scope_flags_default_off():
    from src.polaris_graph.retrieval import live_retriever as lr
    assert lr._serper_scope_filter_enabled() is False
    assert lr._s2_scope_filter_enabled() is False
    assert lr._openalex_scope_filter_enabled() is False
