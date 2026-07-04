"""R2 (I-deepfix-001, #1344) — per-task facet checklist drives the completeness/expansion loop.

Proves the EFFECT: a per-task facet checklist measures which facets the corpus covers and fires
targeted expansion RETRIEVAL for the UNCOVERED facets, stopping on a source-yield SATURATION (not a
fixed count). Contrasts against the control where all facets are already covered (no expansion —
the fix is not a tautology that always fires). Faithfulness untouched: zero sources dropped.
"""
from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr
from src.polaris_graph.retrieval.expert_facet_planner import Facet
from src.polaris_graph.retrieval import facet_completeness as fc


def _facets():
    return [
        Facet(name="manufacturing automation", queries=[
            "manufacturing automation how it works drivers ai labor",
            "manufacturing automation criticism limitations ai labor",
        ]),
        Facet(name="worker reskilling programs", queries=[
            "worker reskilling programs stakeholders impact ai labor",
            "worker reskilling programs recent trends ai labor",
        ]),
    ]


def _rows(*subjects):
    return [{"source_url": f"https://s/{i}", "statement": s} for i, s in enumerate(subjects)]


# ── coverage measurement ──────────────────────────────────────────────────────

def test_measure_coverage_flags_uncovered_facet():
    facets = _facets()
    # corpus covers 'manufacturing automation' only.
    corpus = _rows(
        "automation in manufacturing raised output",
        "manufacturing plants deployed robots",
    )
    coverage = fc.measure_facet_coverage(facets, corpus, min_hits=1)
    by_name = {c.facet.name: c for c in coverage}
    assert by_name["manufacturing automation"].covered is True
    assert by_name["worker reskilling programs"].covered is False
    assert [f.name for f in fc.uncovered_facets(coverage)] == ["worker reskilling programs"]


def test_generic_angle_words_do_not_cover_a_facet():
    """A facet is covered by its SUBJECT keywords only — generic lens words never mark it covered."""
    facets = [Facet(name="quantum error correction", queries=["quantum error correction mechanism"])]
    # rows full of generic angle-lens words but NONE of the facet subject tokens.
    corpus = _rows("recent trends stakeholders impact mechanism drivers criticism")
    coverage = fc.measure_facet_coverage(facets, corpus, min_hits=1)
    assert coverage[0].covered is False


# ── expansion loop fires on real gaps ─────────────────────────────────────────

def test_expansion_fires_for_uncovered_and_stops_all_covered():
    facets = _facets()
    seed = _rows("automation in manufacturing raised output")  # only facet 1 covered

    def retrieve(research_question, **kw):
        class _R:
            # any reskilling query returns a row that COVERS the reskilling facet
            evidence_rows = [{
                "source_url": f"https://exp/{research_question[:12]}",
                "statement": "worker reskilling programs expanded across firms",
            }]
        return _R()

    result = fc.run_facet_expansion(facets, seed, retrieve, max_rounds=5)
    # expansion fired for the uncovered facet's queries...
    assert result.expansion_queries, "expansion must fire for the uncovered facet"
    assert any("reskilling" in q for q in result.expansion_queries)
    # ...and stopped because coverage closed (not because it hit max_rounds).
    assert result.stop_reason == "all_covered"
    # coverage trace shows the uncovered count going to zero.
    assert result.coverage_trace[0] >= 1 and result.coverage_trace[-1] == 0


def test_no_expansion_when_all_facets_already_covered():
    """Control: full coverage => ZERO expansion. The loop fires only on genuine gaps."""
    facets = _facets()
    seed = _rows(
        "automation in manufacturing raised output",
        "worker reskilling programs expanded",
    )
    fired: list = []

    def retrieve(research_question, **kw):
        fired.append(research_question)
        class _R:
            evidence_rows: list = []
        return _R()

    result = fc.run_facet_expansion(facets, seed, retrieve, max_rounds=5)
    assert result.expansion_queries == []
    assert fired == [], "no retrieval when there is no gap"
    assert result.stop_reason == "all_covered"


# ── saturation is yield-keyed, not a count ────────────────────────────────────

def test_expansion_stops_on_yield_saturation_not_count():
    """The stop is keyed to NEW-source yield: a round adding too few new sources ends the loop."""
    facets = [Facet(name="rare uncoverable topic", queries=[
        "rare uncoverable topic mechanism", "rare uncoverable topic criticism",
    ])]
    seed = _rows("baseline source one", "baseline source two", "baseline source three")

    def retrieve(research_question, **kw):
        class _R:
            # returns a row that does NOT cover the facet and re-uses an existing source url
            # -> the round adds ZERO new distinct sources -> yield saturates immediately.
            evidence_rows = [{"source_url": "https://s/0", "statement": "unrelated filler"}]
        return _R()

    result = fc.run_facet_expansion(
        facets, seed, retrieve, max_rounds=9, saturation_min_new_fraction=0.10,
    )
    assert result.stop_reason == "yield_saturated"
    assert result.rounds_run < 9, "must stop on saturation well before the compute max-rounds bound"


def test_expansion_drops_zero_sources():
    """Faithfulness-neutral: every retrieved result is returned; nothing is dropped."""
    facets = _facets()
    seed = _rows("automation in manufacturing raised output")

    def retrieve(research_question, **kw):
        class _R:
            evidence_rows = [{"source_url": f"https://exp/{len(research_question)}", "statement": "x"}]
        return _R()

    result = fc.run_facet_expansion(facets, seed, retrieve, max_rounds=3)
    assert len(result.results) == len(result.expansion_queries)


# ── end-to-end through the FS-Researcher planner (R1 seed + R2 expansion) ──────

def test_r1_r2_integration_seed_plus_expansion(monkeypatch):
    """Both flags ON: the frontier = R1 facet-angle seeds + R2 expansion on the uncovered facet."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_FACET_COMPLETENESS", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_SEED_ANGLES", "1")  # 1 seed angle/facet -> reserve exists
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")    # isolate from R5

    facet_tree = "manufacturing automation\nworker reskilling programs"

    def llm(prompt):
        if "expert research planner" in prompt:
            return facet_tree + "\n"
        return "NONE\n"

    fetched: list = []

    def retrieve(research_question, **kw):
        fetched.append(research_question)
        # seed queries about 'manufacturing' cover facet 1; NOTHING covers 'reskilling' at seed
        # time (the reskilling seed row is deliberately off-subject), so R2 MUST fire expansion
        # reserve-angle queries for it — and those DO surface the reskilling subject.
        if "manufacturing" in research_question:
            stmt = "manufacturing automation output rose"
        elif "reskilling" in research_question and "criticism" in research_question:
            # a RESERVE angle (counter-evidence lens) finally surfaces the reskilling subject
            stmt = "worker reskilling programs grew across firms"
        else:
            stmt = "generic macro commentary unrelated to the facet subject"
        class _R:
            evidence_rows = [{"source_url": f"https://s/{len(fetched)}", "statement": stmt}]
        return _R()

    queries, results = fsr.plan_fs_researcher_queries("AI and the labor market", llm, retrieve)
    # R1 produced facet-angle seeds for BOTH facets...
    assert any("manufacturing" in q for q in queries)
    assert any("reskilling" in q for q in queries)
    # ...R2 expansion issued MORE than one reskilling query (seed angle + reserve angles),
    # proving the completeness loop fired for the uncovered facet (not just the seed).
    assert sum(1 for q in queries if "reskilling" in q) > 1, (
        "R2 must issue reskilling RESERVE-angle queries beyond the single seed angle"
    )
    # ...and the loop issued a retrieval per query, keeping every result (zero dropped).
    assert len(results) == len(queries) == len(fetched)
    assert len(queries) >= 4, "seed frontier for two facets across angles"


# ── WIRED-PATH effect proof of R2 (Codex/Fable P1): expansion actually FIRES ───

def test_r2_wired_expansion_fires_for_uncovered_facet(monkeypatch):
    """Through ``plan_fs_researcher_queries``, when a facet stays UNCOVERED after the seed
    pass, the R2 completeness loop issues real expansion queries from that facet's RESERVE
    angles.

    RED on the pre-fix code: every angle was registered as a seed, so ``run_facet_expansion``
    read ``frontier_exhausted`` and returned ZERO expansion queries (the exact P1 both gates
    flagged — "the integration test never asserts an expansion query actually fired").
    """
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_FACET_COMPLETENESS", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_SEED_ANGLES", "1")  # 1 seed angle -> 4 reserve angles
    monkeypatch.setenv("PG_EXPERT_FACET_ANGLES", "5")
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")    # isolate R2 from R5

    def llm(prompt):
        if "expert research planner" in prompt:
            return "worker reskilling programs\n"
        return "NONE\n"

    fetched: list = []

    def retrieve(research_question, **kw):
        fetched.append(research_question)
        class _R:
            # a NEW distinct source each round, none mentioning the facet SUBJECT, so the facet
            # stays uncovered and the expansion loop keeps firing reserve angles (until the
            # facet's angle frontier is exhausted).
            evidence_rows = [{
                "source_url": f"https://s/{len(fetched)}",
                "statement": "unrelated macro commentary",
            }]
        return _R()

    # Spy on the R2 expansion so we can assert it did real work on the WIRED path.
    captured: dict = {}
    real_expand = fc.run_facet_expansion

    def _spy(*a, **k):
        r = real_expand(*a, **k)
        captured["result"] = r
        return r

    monkeypatch.setattr(fc, "run_facet_expansion", _spy)

    queries, results = fsr.plan_fs_researcher_queries("AI and the labor market", llm, retrieve)

    assert "result" in captured, "R2 expansion loop was never reached on the wired path"
    exp = captured["result"]
    assert exp.expansion_queries, (
        "R2 must issue expansion queries for the uncovered facet post-seed "
        "(pre-fix: every angle pre-registered as a seed -> frontier_exhausted -> zero)"
    )
    # the expansion queries genuinely reached the issued frontier...
    for q in exp.expansion_queries:
        assert q in queries, "expansion query must reach the issued frontier"
    # ...and every issued query retrieved (zero dropped) — faithfulness-neutral.
    assert len(results) == len(queries) == len(fetched)
    assert len(queries) > 1, "seed(1 angle) + expansion(reserve angles) > a single seed query"


def test_r2_wired_no_expansion_when_seed_covers_facet(monkeypatch):
    """Tautology guard on the wired path: when the seed pass ALREADY covers the facet, the R2
    loop issues ZERO expansion queries (gap-driven, never always-on)."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_FACET_COMPLETENESS", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_SEED_ANGLES", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_ANGLES", "5")
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")

    def llm(prompt):
        if "expert research planner" in prompt:
            return "worker reskilling programs\n"
        return "NONE\n"

    def retrieve(research_question, **kw):
        # echo the query subject so EVERY facet's seed row covers that facet (the planner's
        # deterministic floor also adds a whole-question facet — its seed row covers it too).
        class _R:
            evidence_rows = [{
                "source_url": f"https://s/{abs(hash(research_question)) % 100000}",
                "statement": research_question,
            }]
        return _R()

    captured: dict = {}
    real_expand = fc.run_facet_expansion

    def _spy(*a, **k):
        r = real_expand(*a, **k)
        captured["result"] = r
        return r

    monkeypatch.setattr(fc, "run_facet_expansion", _spy)

    fsr.plan_fs_researcher_queries("AI and the labor market", llm, retrieve)
    assert "result" in captured
    assert captured["result"].expansion_queries == [], (
        "R2 must NOT fire expansion when the seed corpus already covers the facet"
    )
    assert captured["result"].stop_reason == "all_covered"
