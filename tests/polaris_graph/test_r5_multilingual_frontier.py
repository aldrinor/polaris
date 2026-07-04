"""R5 (I-deepfix-001 #1344) — language-profile multilingual / cross-lingual frontier.

FAIL-LOUD behavioral tests proving the EFFECT of R5, not a flag tautology:

1. On a non-English (zh) task, the language profile detects the native language
   and the query expansion ADDS native-language queries (the English queries stay
   first + unchanged). On an English-only task the expansion is byte-identical.
2. Wired into the FS-Researcher facet frontier: with the multilingual flag ON, a
   zh question's ISSUED retrieval query set contains at least one native-script
   (Chinese) query — the real recall lever. With the flag OFF it is byte-identical
   to English-only fanout.

Offline / $0 / no network; the LLM + retrieval are deterministic stubs.
"""
from __future__ import annotations

from src.polaris_graph.retrieval import language_profile as lp
from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text or "")


# ---------------------------------------------------------------------------
# 1. language_profile module — detection + expansion
# ---------------------------------------------------------------------------

def test_english_only_profile_is_not_multilingual():
    profile = lp.detect_language_profile(
        "How does AI automation affect the labor market?"
    )
    assert profile.is_multilingual is False
    assert profile.languages == ("en",)


def test_chinese_question_detected_as_multilingual():
    profile = lp.detect_language_profile("人工智能对劳动力市场的影响是什么？")
    assert profile.is_multilingual is True
    assert "zh" in profile.non_english
    assert profile.primary == "zh"
    # English is ALWAYS retained as a query language (never lose English recall).
    assert "en" in profile.languages


def test_explicit_answer_in_chinese_instruction_routes_native(monkeypatch):
    profile = lp.detect_language_profile(
        "Summarize the AI labor market literature. Answer in Chinese."
    )
    assert profile.is_multilingual is True
    assert "zh" in profile.non_english


def test_expansion_byte_identical_for_english_only(monkeypatch):
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    base = ["ai automation labor effect", "ai wage inequality mechanism"]
    profile = lp.detect_language_profile("english only question about ai")
    out = lp.expand_queries_for_profile(base, profile, "english only question about ai")
    assert out == base, "English-only expansion must be byte-identical"


def test_expansion_adds_native_queries_for_chinese(monkeypatch):
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    question = "人工智能对劳动力市场的影响"
    base = ["ai automation labor market effect", "ai wage inequality"]
    profile = lp.detect_language_profile(question)
    out = lp.expand_queries_for_profile(base, profile, question)

    # English queries preserved FIRST and unchanged.
    assert out[: len(base)] == base
    # At least one ADDED query carries native (Chinese) script.
    added = out[len(base):]
    assert added, "multilingual expansion must add queries"
    assert any(_has_cjk(q) for q in added), (
        "R5 must add native-language (Chinese) queries so native-language "
        "primaries are actually searched"
    )
    # Zero input queries dropped.
    for q in base:
        assert q in out


def test_expansion_never_drops_input_seeds_under_small_cap(monkeypatch):
    """Fable P2: the compute-safety cap applies to the multilingual ADDITIONS only — it must
    NEVER truncate the input English seeds (the 'DROPS ZERO input queries' contract). RED on
    the pre-fix code where step-1 capped mid-base and returned a truncated seed list."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    question = "人工智能对劳动力市场的影响"
    base = [f"english seed query number {i}" for i in range(6)]
    profile = lp.detect_language_profile(question)
    out = lp.expand_queries_for_profile(base, profile, question, max_queries=3)
    # cap=3 < len(base)=6, yet every input seed must survive (cap bounds additions only).
    for q in base:
        assert q in out, "input English seed dropped by the multilingual cap (Fable P2)"


def test_multilingual_additions_never_exceed_ceiling(monkeypatch):
    """Codex P2 (off-by-one): the additions ceiling is ``max(cap, len(base))`` and the
    total emitted queries must NEVER exceed it. RED on the pre-fix ``_add`` which
    appended BEFORE testing the ceiling, so with ``cap <= len(base)`` the frontier was
    already full yet still emitted one extra multilingual addition (ceiling + 1).

    This is a compute-safety bound on ADDITIONS only — it drops zero input seeds, so it
    is a weight/compute cap, not a breadth filter (DNA-safe)."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    question = "人工智能对劳动力市场的影响"
    base = ["english seed alpha", "english seed beta"]
    profile = lp.detect_language_profile(question)

    # cap=1 <= len(base)=2  ->  ceiling = max(1, 2) = 2. There is NO room for any
    # addition; the pre-fix code still appended the native phrase (total 3 > 2).
    out = lp.expand_queries_for_profile(base, profile, question, max_queries=1)
    ceiling = max(1, len(base))
    assert len(out) <= ceiling, (
        f"multilingual additions overshot the compute ceiling: "
        f"{len(out)} > {ceiling} (Codex P2 off-by-one)"
    )
    # No room for additions -> the base seeds are returned verbatim.
    assert out == base
    # And every input seed is preserved regardless (the standing DROPS-ZERO contract).
    for q in base:
        assert q in out


def test_expansion_flag_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")
    question = "人工智能对劳动力市场的影响"
    base = ["ai automation labor market effect"]
    profile = lp.detect_language_profile(question)
    out = lp.expand_queries_for_profile(base, profile, question)
    assert out == base, "flag OFF must be a byte-identical no-op even on a zh task"


def test_injected_translator_adds_true_translations(monkeypatch):
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    question = "人工智能对劳动力市场的影响"
    base = ["ai labor effect"]
    profile = lp.detect_language_profile(question)

    def _translate(query, lang):
        return f"[{lang}]译文-{query}"

    out = lp.expand_queries_for_profile(
        base, profile, question, translate_fn=_translate
    )
    assert any("译文" in q for q in out), "injected translator output must appear"


# ---------------------------------------------------------------------------
# 2. Wired into the FS-Researcher facet frontier (the R1 path)
# ---------------------------------------------------------------------------

class _Facet:
    def __init__(self, queries):
        self.name = "facet"
        self.queries = queries


def _wire_stubs(monkeypatch, english_facet_queries):
    """Stub the expert-facet planner + per-query retrieve so the frontier is
    deterministic and offline. Returns the list that captures ISSUED queries."""
    from src.polaris_graph.retrieval import expert_facet_planner as efp
    from src.polaris_graph.retrieval import facet_completeness as fc

    monkeypatch.setattr(
        efp, "plan_expert_facets",
        lambda question, llm: [_Facet(list(english_facet_queries))],
    )
    # Keep the R2 expansion loop out of the way so we test the R5 seed frontier.
    monkeypatch.setattr(fc, "facet_completeness_enabled", lambda: False)

    issued: list[str] = []

    class _Result:
        evidence_rows: list = []

    def _retrieve(*, research_question, **kwargs):
        issued.append(research_question)
        return _Result()

    return issued, _retrieve


def test_fs_researcher_issues_native_queries_on_chinese_task(monkeypatch):
    """With multilingual ON, a zh question's ISSUED query set includes a native
    (Chinese) query — proving R5 fires in the real retrieval query path."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    english_facets = ["ai automation labor market", "ai wage inequality mechanism"]
    issued, retrieve = _wire_stubs(monkeypatch, english_facets)

    question = "人工智能对劳动力市场的影响是什么"
    fsr._plan_expert_facet_queries(
        question,
        llm=lambda prompt: "",
        per_query_retrieve=retrieve,
    )

    assert issued, "no queries were issued"
    assert any(_has_cjk(q) for q in issued), (
        "R5 wiring must issue at least one native-language query on a zh task"
    )
    # English facet queries still issued (English recall not lost).
    for q in english_facets:
        assert q in issued


def test_fs_researcher_english_task_unaffected(monkeypatch):
    """An English task issues exactly the English facet queries — R5 adds nothing."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    english_facets = ["ai automation labor market", "ai wage inequality mechanism"]
    issued, retrieve = _wire_stubs(monkeypatch, english_facets)

    question = "What is the impact of AI on the labor market?"
    fsr._plan_expert_facet_queries(
        question,
        llm=lambda prompt: "",
        per_query_retrieve=retrieve,
    )

    assert issued == english_facets, "English task must be byte-identical (no native adds)"


def test_fs_researcher_issues_native_query_on_explicit_language_instruction(monkeypatch):
    """Codex P1: an ALL-ASCII English question that DEMANDS a non-English answer
    ('Answer in Chinese') must STILL issue a native-language query on the production
    path. The question body has no native script, so the ONLY native-query source is
    a true translation — proving the injected production translator actually fires.

    RED on the pre-fix code: `_plan_expert_facet_queries` called
    `expand_queries_for_profile` with NO `translate_fn`, so an explicit-language
    English task stayed English-only and no native query was ever issued."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    english_facets = ["ai automation labor market", "ai wage inequality"]
    issued, retrieve = _wire_stubs(monkeypatch, english_facets)

    def _llm(prompt):
        # The production translator asks for a numbered per-line translation.
        if "Translate" in prompt:
            return "1. 人工智能自动化劳动力市场\n2. 人工智能工资不平等"
        return ""

    question = "Summarize the AI labor market literature. Answer in Chinese."
    fsr._plan_expert_facet_queries(
        question, llm=_llm, per_query_retrieve=retrieve
    )

    assert issued, "no queries were issued"
    assert any(_has_cjk(q) for q in issued), (
        "R5 must issue a native-language query for an explicit-language task even when "
        "the question body has no native script (translation path was never wired)"
    )
    # English facet queries still issued (English recall not lost).
    for q in english_facets:
        assert q in issued


def test_fs_researcher_native_survives_wide_english_frontier(monkeypatch):
    """Codex/Fable P1: a WIDE English R1 frontier must NOT starve the task's own
    language out of the issued set. With a query budget smaller than the English
    frontier, at least one native query must STILL be issued (the reserve).

    RED on the pre-fix code: native additions were appended AFTER every English seed,
    so the seed issue loop hit `max_queries` on English alone and issued ZERO native
    queries on a zh task."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "1")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "12")  # tight budget
    # A wide English frontier that would fill the whole budget on its own.
    english_facets = [f"english facet query number {i}" for i in range(30)]
    issued, retrieve = _wire_stubs(monkeypatch, english_facets)

    question = "人工智能对劳动力市场的影响是什么"  # zh script -> native query source
    fsr._plan_expert_facet_queries(
        question, llm=lambda p: "", per_query_retrieve=retrieve
    )

    assert len(issued) <= 12, "the compute-safety query budget must still bound issue"
    assert any(_has_cjk(q) for q in issued), (
        "a wide English frontier must NOT starve the task's own language: at least one "
        "native query must be issued within the budget (Codex/Fable P1)"
    )
    # English breadth is still represented (both dimensions survive the reserve).
    assert any(q in english_facets for q in issued), "English breadth fully displaced"


def test_fs_researcher_flag_off_no_native_queries(monkeypatch):
    """With multilingual OFF, even a zh task issues only the English facet queries."""
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")
    english_facets = ["ai automation labor market"]
    issued, retrieve = _wire_stubs(monkeypatch, english_facets)

    question = "人工智能对劳动力市场的影响是什么"
    fsr._plan_expert_facet_queries(
        question,
        llm=lambda prompt: "",
        per_query_retrieve=retrieve,
    )

    assert issued == english_facets
    assert not any(_has_cjk(q) for q in issued)
