"""I-qgen-001 (#1373): validator-status message leaked into the {topic} slot of generated queries.

drb_72 forensic (ev_1091 provenance trace): the query actually sent to Serper was

    "What are the positive views in academic literature published before June 2023
     regarding the impact of Temporal constraint violation: The research question
     requires literature"

— the {topic} slot got a temporal-constraint VALIDATOR message instead of the subject
("Generative AI on employment"), and scope_query_validator rubber-stamped it
("1 kept / 0 dropped" x50) because the status prose shares anchor tokens with the
question. Sibling leaks: "Insufficient pre-June ...", "Lack of specific ...".

FIX under test (all offline, $0, no LLM/network):
  1. scope_query_validator DROPS a query that is or embeds validator/status prose
     (reason `validator_status_leak`) and KEEPS the clean equivalent.
  2. KEEP-BEST-N cannot rescue a status leak.
  3. CHANNEL SEPARATION: the FS-Researcher query-gen path can no longer interpolate a
     validator message into the SUB-TOPIC {topic} slot — status lines are screened out
     of the todo queue (TOC + checklist critic) and the derived-query output channel.
  4. The expert-facet planner screens status lines out of the {facet} slot.
  5. Subject-exemption: a question genuinely ABOUT e.g. "temporal constraint" keeps
     its own queries; PG_QUERY_META_STATUS_SCREEN=0 kill-switch reverts byte-identical.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr
from src.polaris_graph.retrieval.expert_facet_planner import plan_expert_facets
from src.polaris_graph.retrieval.scope_query_validator import (
    is_meta_status_clause,
    validate_amplified_queries,
)

# The drb_72 question (subject: impact of generative AI on employment, pre-June-2023
# academic literature) — the anchor the corrupted query overlapped with.
QUESTION = (
    "I am researching the impact of generative AI on the future labor market. "
    "The report must summarize the existing academic literature's positive views, "
    "negative views, specific challenges, and future opportunities regarding "
    "generative artificial intelligence's impact on employment, based on academic "
    "literature published before June 2023."
)

# The EXACT corrupted query from the ev_1091 provenance trace.
CORRUPTED = (
    "What are the positive views in academic literature published before June 2023 "
    "regarding the impact of Temporal constraint violation: The research question "
    "requires literature"
)

# The clean equivalent — the {topic} slot carries the real subject.
CLEAN = (
    "What are the positive views in academic literature published before June 2023 "
    "regarding the impact of Generative AI on employment"
)

# Sibling corrupt queries observed in the same run.
SIBLING_LEAKS = [
    "Insufficient pre-June 2023 academic literature on generative AI employment effects",
    "Lack of specific peer-reviewed studies on generative AI wage effects",
]

PROTOCOL = {"research_question": QUESTION}


# ── 1. Validator drops the corrupted query, keeps the clean one ──────────────────

def test_corrupted_query_dropped_by_validator(monkeypatch):
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)  # default ON
    # always_keep_anchor=False mirrors the per-query FS-Researcher lane
    # (run_live_retrieval(amplified_queries=[generated], anchor_seed=False)).
    result = validate_amplified_queries([CORRUPTED], PROTOCOL, always_keep_anchor=False)
    assert CORRUPTED not in result.kept, (
        "the validator rubber-stamped the corrupted query again (the #1373 bug)"
    )
    assert result.kept == [], f"nothing should survive, got {result.kept}"
    assert len(result.dropped) == 1
    q, sim, reason = result.dropped[0]
    assert q == CORRUPTED
    assert reason == "validator_status_leak", f"wrong drop reason: {reason}"


def test_sibling_status_leaks_dropped(monkeypatch):
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    result = validate_amplified_queries(SIBLING_LEAKS, PROTOCOL, always_keep_anchor=False)
    assert result.kept == [], f"sibling status leaks kept: {result.kept}"
    reasons = {d[2] for d in result.dropped}
    assert reasons == {"validator_status_leak"}


def test_clean_query_kept(monkeypatch):
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    result = validate_amplified_queries([CLEAN], PROTOCOL, always_keep_anchor=False)
    assert CLEAN in result.kept, f"clean on-topic query wrongly dropped: {result.dropped}"
    assert result.dropped == []


def test_keep_best_n_cannot_rescue_status_leak(monkeypatch):
    """The anti-empty-round rescue (PG_SCOPE_KEEP_BEST_N) must NOT resurrect a status
    leak: the leak is dropped BEFORE the floor loop, so it never enters below_floor."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    monkeypatch.setenv("PG_SCOPE_KEEP_BEST_N", "3")
    result = validate_amplified_queries([CORRUPTED], PROTOCOL, always_keep_anchor=False)
    assert result.kept == [], "KEEP-BEST-N rescued a validator-status leak"


def test_kill_switch_reverts_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_QUERY_META_STATUS_SCREEN", "0")
    result = validate_amplified_queries([CORRUPTED], PROTOCOL, always_keep_anchor=False)
    # legacy (bug) behaviour: high token overlap with the anchor -> kept
    assert CORRUPTED in result.kept


# ── 2. Subject-exemption: genuine subjects are never self-dropped ────────────────

def test_subject_exemption_for_genuine_topic():
    scheduling_q = "How do temporal constraint networks improve scheduling algorithms?"
    topic = "temporal constraint propagation in scheduling"
    assert is_meta_status_clause(topic, scheduling_q) is False
    # without the subject context the same text reads as validator vocabulary
    assert is_meta_status_clause(topic, QUESTION) is True


def test_insufficient_opener_exempt_when_subject():
    sleep_q = "What is the effect of insufficient sleep on adolescent obesity?"
    assert is_meta_status_clause("insufficient sleep and obesity in adolescents", sleep_q) is False
    assert is_meta_status_clause("Insufficient pre-June 2023 sources on X", QUESTION) is True


def test_opener_exemption_requires_multiword_span(monkeypatch):
    """Codex iter-2 P1: a lone first-word hit in the subject must NOT disarm the
    status-opener screen. Subject 'insufficient sleep and cognition' shares only the
    single word 'insufficient' with the 'Insufficient pre-June 2023 literature'
    verdict — the multi-word span 'insufficient pre-june' is NOT in the subject, so
    the verdict is still dropped."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)  # default ON
    subject = "insufficient sleep and cognition"
    verdict = "Insufficient pre-June 2023 literature"
    assert is_meta_status_clause(verdict, subject) is True
    result = validate_amplified_queries(
        [verdict], {"research_question": subject}, always_keep_anchor=False
    )
    assert verdict not in result.kept, "single stopword-ish hit disarmed the opener screen"
    assert result.kept == []
    assert result.dropped[0][2] == "validator_status_leak"
    # genuine multi-word subject match STILL exempt: the question is truly about
    # insufficient sleep, so an 'Insufficient sleep ...' query survives.
    genuine = "Insufficient sleep duration and cognitive decline"
    assert is_meta_status_clause(genuine, subject) is False
    kept_genuine = validate_amplified_queries(
        [genuine], {"research_question": subject}, always_keep_anchor=False
    )
    assert genuine in kept_genuine.kept, kept_genuine.dropped


def test_pico_no_intervention_does_not_exempt_no_relevant(monkeypatch):
    """Codex iter-2 P1: the PICO comparator 'no intervention' contributes the
    stopword 'no' to the subject text — that must NOT exempt the 'No relevant
    studies found' status verdict (span 'no relevant studies' is not in the
    subject), so the verdict is dropped."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)  # default ON
    protocol = {
        "research_question": "Does exercise therapy reduce chronic low back pain?",
        "intervention": "exercise therapy",
        "comparator": "no intervention",
        "outcome": "pain reduction",
    }
    verdict = "No relevant studies found"
    subject = " ".join(
        str(protocol[f]) for f in ("research_question", "intervention", "comparator", "outcome")
    )
    assert is_meta_status_clause(verdict, subject) is True
    result = validate_amplified_queries([verdict], protocol, always_keep_anchor=False)
    assert verdict not in result.kept, "PICO 'no intervention' disarmed the opener screen"
    assert result.kept == []
    assert result.dropped[0][2] == "validator_status_leak"


# ── 3. Channel separation in the FS-Researcher query-gen path ───────────────────

LEAK_LINE = (
    "Temporal constraint violation: The research question requires literature "
    "published before June 2023"
)
CLEAN_TOPIC = "generative AI adoption and job displacement in manufacturing"


def _stub_retrieve(issued):
    def retrieve(*, research_question: str, **_kw):
        issued.append(research_question)
        return SimpleNamespace(evidence_rows=[])
    return retrieve


def test_toc_status_leak_never_reaches_topic_slot(monkeypatch):
    """A validator message in the TOC reply must never occupy the SUB-TOPIC slot of the
    query-derivation prompt, and must never be searched — the channels are separated."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    monkeypatch.delenv("PG_EXPERT_FACET_PLANNER", raising=False)  # legacy todo loop
    monkeypatch.delenv("PG_FS_RESEARCHER_SCOPE_ANCHOR", raising=False)  # default ON

    prompts: list[str] = []
    issued: list[str] = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        if "Deconstruct" in prompt:
            return f"{LEAK_LINE}\n{CLEAN_TOPIC}"
        if "search query" in prompt:
            # channel-separation assert: the {topic} slot must never carry the leak
            assert "constraint violation" not in prompt.lower(), (
                "validator message interpolated into the SUB-TOPIC {topic} slot"
            )
            return "generative AI job displacement manufacturing academic study"
        return "NONE"

    queries, _ = fsr.plan_fs_researcher_queries(
        QUESTION, llm, _stub_retrieve(issued), max_queries=5, max_rounds=1,
    )
    joined = " || ".join(issued).lower()
    assert "constraint violation" not in joined, f"leak searched: {issued}"
    assert "the research question requires" not in joined
    # the clean sub-topic still produced a real search (the round was not aborted)
    assert issued == ["generative AI job displacement manufacturing academic study"]
    assert queries == issued


def test_checklist_status_verdicts_screened(monkeypatch):
    """The 6-item checklist critic phrases deficiencies as validation verdicts —
    they must be screened out of the next round's todo queue."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    monkeypatch.delenv("PG_EXPERT_FACET_PLANNER", raising=False)
    monkeypatch.delenv("PG_FS_RESEARCHER_SCOPE_ANCHOR", raising=False)

    issued: list[str] = []
    state = {"round": 0}

    def llm(prompt: str) -> str:
        if "Deconstruct" in prompt:
            return CLEAN_TOPIC
        if "search query" in prompt:
            assert "constraint violation" not in prompt.lower()
            assert "insufficient pre-june" not in prompt.lower()
            # derive a distinct query per round so dedup does not end the loop
            return f"round {state['round']} " + prompt.strip().splitlines()[-1][:60]
        # checklist critic: first call returns two status verdicts + one clean topic
        state["round"] += 1
        if state["round"] == 1:
            return (
                f"{LEAK_LINE}\n"
                "Insufficient pre-June 2023 sources on wage polarization\n"
                "generative AI wage polarization academic studies"
            )
        return "NONE"

    fsr.plan_fs_researcher_queries(
        QUESTION, llm, _stub_retrieve(issued), max_queries=10, max_rounds=3,
    )
    joined = " || ".join(issued).lower()
    assert "constraint violation" not in joined
    assert "insufficient pre-june" not in joined
    # the clean deficiency topic still fired a round-2 search
    assert any("wage polarization" in q.lower() for q in issued), issued


def test_derived_query_status_leak_aborted(monkeypatch):
    """If the derivation LLM itself replies with a status message, that facet's query
    is ABORTED (skipped), never searched."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    monkeypatch.delenv("PG_EXPERT_FACET_PLANNER", raising=False)

    issued: list[str] = []

    def llm(prompt: str) -> str:
        if "Deconstruct" in prompt:
            return CLEAN_TOPIC
        if "search query" in prompt:
            return "Error: temporal constraint cannot be satisfied by the knowledge base"
        return "NONE"

    queries, _ = fsr.plan_fs_researcher_queries(
        QUESTION, llm, _stub_retrieve(issued), max_queries=5, max_rounds=1,
    )
    assert issued == [], f"status-leak derived query was searched: {issued}"
    assert queries == []


def test_all_status_toc_falls_back_to_question(monkeypatch):
    """When EVERY TOC line is a status verdict, the todo queue falls back to the
    question itself (never an empty round on the seed pass)."""
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)
    monkeypatch.delenv("PG_EXPERT_FACET_PLANNER", raising=False)

    issued: list[str] = []

    def llm(prompt: str) -> str:
        if "Deconstruct" in prompt:
            return LEAK_LINE
        if "search query" in prompt:
            assert "constraint violation" not in prompt.lower()
            return "generative AI employment impact academic literature pre-2023"
        return "NONE"

    fsr.plan_fs_researcher_queries(
        QUESTION, llm, _stub_retrieve(issued), max_queries=5, max_rounds=1,
    )
    assert issued == ["generative AI employment impact academic literature pre-2023"]


# ── 4. Expert-facet planner screens the {facet} slot ─────────────────────────────

def test_facet_planner_screens_status_lines(monkeypatch):
    monkeypatch.delenv("PG_QUERY_META_STATUS_SCREEN", raising=False)

    def llm(prompt: str) -> str:
        return f"{LEAK_LINE}\nlabor market displacement from generative AI"

    facets = plan_expert_facets(QUESTION, llm)
    names = [f.name.lower() for f in facets]
    assert not any("constraint violation" in n for n in names), names
    assert any("labor market displacement" in n for n in names), names
    for f in facets:
        for q in f.queries:
            assert "constraint violation" not in q.lower(), (
                f"status leak reached a templated facet-angle query: {q}"
            )
