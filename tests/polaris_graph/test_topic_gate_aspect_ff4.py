"""I-deepfix-001 FF4-ASPECT (v2, forensic-corrected) — aspect-scoped topic gate.

ROOT DEFECT (inv_0_aspect-blind-topicality-gate + FORENSIC_VERDICTS off-topic):
the topic gate's ``_build_batch_prompt`` asked the model a purely ENTITY-level
question ("is this a DIFFERENT subject / field / population?"). A same-entity but
WRONG-ASPECT source — a GenAI-in-education / L2-writing paper judged for a
GenAI-labor-market question — shares the entity ("generative AI"), so it is NOT a
different field, and the fail-open kept it ON. It then flowed to citation and
grounded the Abstract + OPPORTUNITIES lead. The class is query-ASPECT mismatch
surviving an entity-overlap relevance gate.

THE FIX (FF4-ASPECT v2): rewrite the entity-level instruction block into a
two-part FACET-SCOPED rubric that makes the model name the question's SUBJECT
ENTITY *and* its SPECIFIC ASPECT and mark a source ON only if it bears on BOTH; a
same-entity / different-aspect source is OFF ("same subject, wrong question").

FORENSIC ADJUSTMENT #2 (mandatory, off-topic fix_change_needed): the naming
reasoning MUST stay INTERNAL and the output MUST be strictly verdict-only —
exactly one ``<index>: ON|OFF`` line per source, nothing else. The parser
(``_parse_batch_verdicts``, unchanged) recognises ONLY that shape; inline
reasoning on a verdict line (e.g. "1: this is about L2 writing, OFF") is
unrecognised -> count mismatch -> the WHOLE batch fails OPEN -> the off-aspect
source silently survives. So the rewritten prompt hardens the output contract
rather than relaxing the parser (§-1.3: fix the prompt, not the contract).

Domain-agnostic (LAW VI — the aspect is derived at runtime from the RESEARCH
QUESTION, nothing domain-specific is hardcoded).

RED/GREEN COUPLING (offline, no model spend): the ``_aspect_aware_llm`` stub below
simulates a competent model judging under WHATEVER rubric the prompt actually
gives it. Under the pre-fix entity-only prompt it marks the L2-writing source ON
(the documented blind spot); under the post-fix facet-scoped prompt it marks it
OFF. So the behavioral test FAILS on the old prompt (n_demoted_offtopic == 0) and
PASSES on the new prompt (n_demoted_offtopic == 1) — the change in
``_build_batch_prompt`` is the only thing that flips it.

FAITHFULNESS-NEUTRAL: this touches only the selection-side topic-gate PROMPT text.
The gate's DEFAULT keep-all + demote path is unchanged; strict_verify / NLI / the
4-role D8 audit / provenance span-grounding are byte-for-byte untouched.

VALIDATION NOTE (forensic adjustment #1): the topic gate is guarded
``if (not _resume_active)`` at run_honest_sweep_r3.py:12942 and a corpus_snapshot
does NOT persist the demote sidecar — so an END-TO-END effect of FF4 can ONLY be
validated on a FRESH front-half run (or a fetch_snapshot post-fetch resume), never
a corpus_snapshot replay. These offline unit tests validate the PROMPT LOGIC only.
"""

from __future__ import annotations

from src.polaris_graph.generator.weighted_enrichment import _is_confirmed_offtopic
from src.polaris_graph.retrieval.topic_relevance_gate import (
    _build_batch_prompt,
    _parse_batch_verdicts,
    classify_topic_relevance,
)

# The exact research question and the two contrasting sources from the brief's
# RED/GREEN plan. R1 is the surviving-defect source ([21] in the drb_72 run).
_RESEARCH_QUESTION = "the impact of generative AI on the labor market / employment"

_ON_ASPECT_TITLE = (
    "Generative AI and employment: wage effects and job displacement estimates"
)
_OFF_ASPECT_TITLE = (
    "Students' Perceptions of Generative Artificial Intelligence (GenAI) used "
    "dishonestly in L2 writing"
)
_OFF_ASPECT_SNIPPET = (
    "Aim of Research - RQ1: how do students perceive the use of generative AI "
    "dishonestly in L2 writing"
)


def _rows():
    """Fresh row dicts per test (classify_topic_relevance mutates the demoted
    row's ``topic_offtopic_demoted`` sidecar, so never share objects)."""
    return [
        {"title": _ON_ASPECT_TITLE, "source_url": "https://doi.org/10.0000/labor"},
        {
            "title": _OFF_ASPECT_TITLE,
            "snippet": _OFF_ASPECT_SNIPPET,
            "source_url": "https://doi.org/10.0000/l2writing",
        },
    ]


def _aspect_aware_llm(prompt: str) -> str:
    """A competent-model stub that judges under whatever rubric the prompt gives.

    It reads the SOURCES block the gate built and returns one ``<idx>: ON|OFF``
    line per source (verdict-only, honouring the output contract). Decision:
      * a labor/employment (on-aspect) source is ALWAYS ON;
      * a same-entity but wrong-aspect (L2-writing) source is OFF **only when the
        prompt is FACET-SCOPED** (names a SPECIFIC ASPECT and the "same subject,
        wrong question" rule) — i.e. only after FF4-ASPECT lands;
      * otherwise (entity-only prompt, or genuinely unsure) it answers ON
        (fail-open), reproducing the pre-fix survival.
    """
    low_prompt = prompt.lower()
    aspect_scoped = (
        "same subject, wrong question" in low_prompt
        and "specific aspect" in low_prompt
    )
    labor_markers = (
        "employment", "labor market", "labour", "wage", "job displacement",
    )
    off_aspect_markers = ("l2 writing", "dishonest", "perceptions")

    verdicts: list[str] = []
    in_sources = False
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if line == "SOURCES:":
            in_sources = True
            continue
        if not in_sources or ":" not in line:
            continue
        idx_part, _, text = line.partition(":")
        idx_token = idx_part.strip()
        if not idx_token.isdigit():
            continue  # skips the trailing "VERDICTS (...)" trailer line
        low_text = text.lower()
        if any(k in low_text for k in labor_markers):
            verdict = "ON"                       # on-aspect -> keep
        elif aspect_scoped and any(k in low_text for k in off_aspect_markers):
            verdict = "OFF"                      # same entity, wrong aspect -> OFF
        else:
            verdict = "ON"                       # entity-only / unsure -> fail-open
        verdicts.append(f"{idx_token}: {verdict}")
    return "\n".join(verdicts)


# ── RED->GREEN: the load-bearing behavioral toggle ────────────────────────────

def test_aspect_scoped_prompt_demotes_wrong_aspect_source():
    """GREEN (post-fix): under the facet-scoped prompt the aspect-aware model
    marks the L2-writing GenAI-education source OFF, so it is DEMOTED (kept +
    disclosed, §-1.3), and every downstream consumer that keys on
    ``_is_confirmed_offtopic`` now suppresses it — while the on-aspect labor
    source is untouched.

    This SAME assertion is the RED reproduction: run against the pre-fix
    entity-only prompt, ``_aspect_aware_llm`` returns "0: ON\\n1: ON", so
    ``n_demoted_offtopic == 0`` and this test FAILS. The prompt rewrite in
    ``_build_batch_prompt`` is the only thing that flips it to pass.
    """
    r0, r1 = _rows()
    result = classify_topic_relevance([r0, r1], _RESEARCH_QUESTION, _aspect_aware_llm)

    assert result.n_in == 2
    # §-1.3 WEIGHT-not-FILTER: demote, never hard-drop, keep-all.
    assert result.n_dropped_offtopic == 0
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 1

    # R1 (the wrong-aspect source) carries the confirmed-off sidecar; R0 does not.
    assert r1.get("topic_offtopic_demoted") is True
    assert r0.get("topic_offtopic_demoted") is not True
    assert any("L2 writing" in t for t in result.demoted_titles)

    # Downstream reader (the single pivot the cite-suppression / section hold-out /
    # compose-demote all key on) now confirms R1 off-topic and leaves R0 alone.
    assert _is_confirmed_offtopic(r1) is True
    assert _is_confirmed_offtopic(r0) is False


def test_entity_only_prompt_would_keep_wrong_aspect_source():
    """RED mechanism, made explicit and deterministic: reconstruct the pre-fix
    ENTITY-ONLY prompt and show the SAME competent model keeps the L2-writing
    source ON — i.e. the defect is the PROMPT, not the model. This documents why
    the fix is load-bearing (it is not asserting current source; it feeds a
    hand-built legacy prompt to the stub)."""
    legacy_prompt = "\n".join(
        [
            "You are a strict topic-relevance classifier for a research report.",
            "",
            f"RESEARCH QUESTION:\n{_RESEARCH_QUESTION}",
            "",
            "For EACH numbered source below, decide whether it is ON-TOPIC for "
            "the research question's subject domain. A source is OFF-TOPIC only "
            "if it is clearly about a DIFFERENT subject (different disease, "
            "different field, different population) — credible but irrelevant. "
            "When in doubt, answer ON.",
            "",
            "SOURCES:",
            f"0: {_ON_ASPECT_TITLE}",
            f"1: {_OFF_ASPECT_TITLE} — {_OFF_ASPECT_SNIPPET}",
            "",
            "VERDICTS (one `<index>: ON|OFF` line per source):",
        ]
    )
    assert _aspect_aware_llm(legacy_prompt) == "0: ON\n1: ON"


# ── the fix actually rewrote the prompt (structural GREEN) ─────────────────────

def test_build_batch_prompt_is_facet_scoped():
    """The rewritten prompt names a SPECIFIC ASPECT, states the same-subject /
    wrong-question rule, carries a domain-neutral exemplar, preserves the explicit
    fail-open, and keeps the exact ``<index>: ON|OFF`` output contract. Contains
    NO hardcoded domain term (LAW VI)."""
    prompt = _build_batch_prompt(
        _RESEARCH_QUESTION, [(0, _OFF_ASPECT_TITLE, _OFF_ASPECT_SNIPPET)]
    )
    low = prompt.lower()
    assert "specific aspect" in low
    assert "same subject, wrong question" in low
    assert "entity x" in low and "aspect a" in low  # domain-neutral exemplar
    assert "when in doubt, answer on" in low        # fail-open preserved
    assert "`<index>: ON`" in prompt and "`<index>: OFF`" in prompt
    # LAW VI: the rubric itself hardcodes no domain-specific aspect. The only
    # domain text is the caller-supplied RESEARCH QUESTION (derived at runtime).
    # Isolate the instruction rubric = text AFTER the interpolated question and
    # BEFORE the SOURCES block, and assert it names no concrete domain.
    rubric = prompt.split(_RESEARCH_QUESTION, 1)[1].split("SOURCES:", 1)[0]
    assert "labor market" not in rubric.lower()
    assert "employment" not in rubric.lower()


def test_prompt_forces_silent_reasoning_and_verdict_only_output():
    """FORENSIC ADJUSTMENT #2: the prompt must force the entity/aspect naming to
    stay INTERNAL and demand a strictly verdict-only output, so the model does not
    emit inline reasoning that the (unchanged) parser fails OPEN on. Asserts the
    hardened output-contract language is present."""
    prompt = _build_batch_prompt(
        _RESEARCH_QUESTION, [(0, _OFF_ASPECT_TITLE, _OFF_ASPECT_SNIPPET)]
    )
    low = prompt.lower()
    # STEP 1 reasoning is explicitly silent / must not appear in the output.
    assert "silently" in low
    assert "must not appear" in low
    # Output is strictly verdict-only, nothing else.
    assert "output only the verdict lines" in low
    assert "do not write" in low


def test_inline_reasoning_verdict_line_fails_open_the_parser():
    """Adjustment-#2 MOTIVATION, proven against the REAL parser (unchanged): a
    clean verdict-only response parses, but the SAME verdicts with naming prose on
    a verdict line are unrecognised -> count mismatch -> fail-OPEN (None) -> the
    off-aspect source silently survives. This is exactly the failure the hardened
    verdict-only output contract prevents; the parser is deliberately left as-is
    (§-1.3: fix the prompt, not the contract)."""
    # Clean, verdict-only -> parses to {idx: is_offtopic}.
    assert _parse_batch_verdicts("0: ON\n1: OFF", [0, 1]) == {0: False, 1: True}
    # Naming prose on the OFF line -> token not recognised -> whole batch None.
    polluted = "0: ON\n1: this source is about L2 writing dishonesty, OFF"
    assert _parse_batch_verdicts(polluted, [0, 1]) is None


# ── §-1.3 guardrail + fail-open still hold through the new prompt ──────────────

def test_on_aspect_low_cred_source_is_kept_undemoted():
    """WEIGHT-not-FILTER: an ON-aspect source is kept un-demoted regardless of
    credibility. The aspect rubric must not over-filter genuinely on-aspect
    material."""
    low_cred = {
        "title": "How generative AI is reshaping employment and wages (blog)",
        "source_url": "https://someblog.example/genai-jobs",
    }
    result = classify_topic_relevance([low_cred], _RESEARCH_QUESTION, _aspect_aware_llm)
    assert result.n_demoted_offtopic == 0
    assert result.n_dropped_offtopic == 0
    assert low_cred.get("topic_offtopic_demoted") is not True
    assert _is_confirmed_offtopic(low_cred) is False


def test_fail_open_on_empty_question():
    """Empty research_question -> nothing to anchor the aspect on -> keep all."""
    r0, r1 = _rows()
    result = classify_topic_relevance([r0, r1], "   ", _aspect_aware_llm)
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 0
    assert result.n_dropped_offtopic == 0


def test_fail_open_on_llm_error():
    """A raising llm_callable -> keep the whole batch (never demote on error)."""
    r0, r1 = _rows()

    def _boom(prompt: str) -> str:
        raise RuntimeError("LLM down")

    result = classify_topic_relevance([r0, r1], _RESEARCH_QUESTION, _boom)
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 0
    assert result.n_dropped_offtopic == 0


def test_fail_open_on_count_mismatch():
    """Wrong number of verdict lines -> keep the whole batch."""
    r0, r1 = _rows()

    def _short(prompt: str) -> str:
        return "1: OFF"  # one verdict for two sources

    result = classify_topic_relevance([r0, r1], _RESEARCH_QUESTION, _short)
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 0


def test_fail_open_on_garbage():
    """Unparseable prose -> keep the whole batch."""
    r0, r1 = _rows()

    def _garbage(prompt: str) -> str:
        return "The first looks relevant, the second is about something else."

    result = classify_topic_relevance([r0, r1], _RESEARCH_QUESTION, _garbage)
    assert result.n_kept == 2
    assert result.n_demoted_offtopic == 0
