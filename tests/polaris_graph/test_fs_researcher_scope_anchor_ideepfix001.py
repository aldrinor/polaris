"""I-deepfix-001 (#1344): FS-Researcher sub-query scope-anchor fix.

drb_72 v2 exposed a retrieval drift: the FS-Researcher decomposed the question into a bare
sub-topic ('manufacturing and supply chain automation') and then wrote a search query from that
sub-topic ALONE — dropping the question's 'AI + labor market' framing — so the search generalised
into the sub-topic's broad field (industrial-automation engineering) and pulled ~500 off-topic +
predatory-journal sources into the corpus.

FIX (default-ON, PG_FS_RESEARCHER_SCOPE_ANCHOR): carry the RESEARCH QUESTION into both the TOC
deconstruction and the per-todo query-derivation so every sub-query stays on-subject.

Faithfulness-neutral: only the SEARCH query text changes; tiering / verification / citation and the
faithfulness gate are untouched, and ZERO fetched sources are dropped (§-1.3 — retrieval scoping,
not a filter/cap). Kill-switch OFF => the legacy bare prompt, byte-for-byte.
"""
from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr

QUESTION = (
    "Please write a literature review on the restructuring impact of Artificial Intelligence (AI) "
    "on the labor market."
)
SUBTOPIC = "manufacturing and supply chain automation"
_LEGACY_PERQ = "Write ONE search query for this sub-topic. Query only.\n\n" + SUBTOPIC


class _StubResult:
    evidence_rows: list = []


def _make_stub_llm(recorder):
    def _llm(prompt):
        recorder.append(prompt)
        if "Deconstruct" in prompt:
            return SUBTOPIC + "\n"          # TOC -> one bare sub-topic
        if "search query" in prompt:
            return SUBTOPIC + "\n"          # per-todo query text (unused by asserts)
        return "NONE\n"                     # checklist critic -> stop
    return _llm


def _run(monkeypatch, anchor_env):
    if anchor_env is None:
        monkeypatch.delenv("PG_FS_RESEARCHER_SCOPE_ANCHOR", raising=False)  # default-ON
    else:
        monkeypatch.setenv("PG_FS_RESEARCHER_SCOPE_ANCHOR", anchor_env)
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "1")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_ROUNDS", "1")
    recorder: list = []
    fsr.plan_fs_researcher_queries(
        QUESTION,
        _make_stub_llm(recorder),
        lambda research_question, **kw: _StubResult(),
    )
    return recorder


def test_scope_anchor_default_on_injects_research_question(monkeypatch):
    prompts = _run(monkeypatch, None)  # default-ON
    toc = next(p for p in prompts if "Deconstruct" in p)
    perq = next(p for p in prompts if "search query" in p)
    # the per-todo query prompt carries the FULL research question (scope anchor)
    assert QUESTION in perq, "scope-anchor ON must inject the research question into the query prompt"
    assert "RESEARCH QUESTION" in perq and "SUB-TOPIC" in perq
    assert "do NOT broaden" in perq
    # the TOC prompt keeps sub-topics scoped
    assert "stay within the scope" in toc


def test_scope_anchor_off_is_byte_identical_legacy(monkeypatch):
    prompts = _run(monkeypatch, "0")
    perq = next(p for p in prompts if "Write ONE search query for this sub-topic" in p)
    # legacy bare prompt, byte-for-byte; NO research question injected
    assert perq == _LEGACY_PERQ
    assert QUESTION not in perq
    toc = next(p for p in prompts if "Deconstruct" in p)
    assert "stay within the scope" not in toc
