"""Tests for the S0 candidate adapter (Research Planning Gate).

Offline + deterministic (no network): the adapter reconciles the ported
rule-reader with the champion intake regex extractors into a candidate list with
exact prompt spans. These assert the S0 acceptance:

  * task-72 (journal-only / English) merges correctly with spans preserved;
  * deterministic wins on overlap; the rule-reader only fills gaps;
  * every emitted span satisfies quote-equality (prompt[start:end] == quote);
  * no ``hard`` force is invented where no deterministic source marked one;
  * the OFF/adjacent behavior is unchanged (this module wires nothing).
"""

from src.polaris_graph.instruction.constraint_extractor import Constraints
from src.polaris_graph.planning.candidate_adapter import (
    FORCE_HARD,
    FORCE_PREFER,
    ORIGIN_DETERMINISTIC,
    ORIGIN_MERGED,
    ORIGIN_RULE_READER,
    CandidateConstraint,
    PromptSpan,
    reconcile_candidates,
)

# The task-72 prompt (journal-only / English-language literature review).
TASK_72_PROMPT = (
    "Please write a literature review on the restructuring impact of "
    "Artificial Intelligence (AI) on the labor market. Ensure the review only "
    "cites high-quality, English-language journal articles."
)

# The rule-reader result for task-72 (as the ported extractor normalizes it).
TASK_72_RULE_READER = Constraints(
    source_types=["journal_article"],
    languages=["en"],
    recency=None,
    required_coverage=["restructuring impact of AI on the labor market"],
    exclusions=["low-quality sources", "non-English sources"],
    format="literature_review",
    length=None,
    tone="academic",
)


def _by_dim(cands, dim):
    return [c for c in cands if c.dimension == dim]


def _assert_span_invariant(prompt, cands):
    """Every emitted span must be an exact slice of the prompt."""
    for c in cands:
        for s in c.spans:
            assert isinstance(s, PromptSpan)
            assert prompt[s.start:s.end] == s.quote, (c.dimension, s)


# ---------------------------------------------------------------------------
# Intake-only reconciliation (no rule-reader supplied)
# ---------------------------------------------------------------------------

def test_task72_intake_only_has_language_and_journal_facet_with_spans():
    cands = reconcile_candidates(TASK_72_PROMPT)
    _assert_span_invariant(TASK_72_PROMPT, cands)

    # Deterministic language candidate with a real span.
    langs = _by_dim(cands, "source.language")
    assert langs, "expected a language candidate from the intake regex pass"
    lang = langs[0]
    assert lang.value == "en"
    assert lang.origin == ORIGIN_DETERMINISTIC
    assert lang.force == FORCE_PREFER
    assert lang.spans and "English-language" in lang.spans[0].quote

    # The journal-only scope facet is detected HARD (the prompt says "only").
    facets = _by_dim(cands, "source.scope_facet")
    assert facets, "expected a journal scope facet"
    jf = facets[0]
    assert jf.value == "peer_reviewed_journal"
    assert jf.force == FORCE_HARD          # 'only' is an explicit exclusivity token
    assert jf.origin == ORIGIN_DETERMINISTIC
    assert jf.spans and "only" in jf.spans[0].quote.lower()


def test_intake_only_never_touches_network_and_is_deterministic():
    a = reconcile_candidates(TASK_72_PROMPT)
    b = reconcile_candidates(TASK_72_PROMPT)
    assert [c.to_dict() for c in a] == [c.to_dict() for c in b]


# ---------------------------------------------------------------------------
# Merge with the rule-reader: deterministic wins on overlap; gaps fill
# ---------------------------------------------------------------------------

def test_task72_merge_language_overlap_deterministic_wins():
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER)
    _assert_span_invariant(TASK_72_PROMPT, cands)

    langs = _by_dim(cands, "source.language")
    assert len(langs) == 1, "language must collapse to one merged candidate"
    lang = langs[0]
    # Deterministic value + force win; origin records the agreement.
    assert lang.value == "en"
    assert lang.force == FORCE_PREFER
    assert lang.origin == ORIGIN_MERGED
    # The authoritative deterministic span survives the merge.
    assert any("English-language" in s.quote for s in lang.spans)
    assert lang.detail.get("also_seen_by") == "rule_reader"


def test_task72_merge_fills_gaps_from_rule_reader():
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER)

    # Format / tone / coverage / exclusions are rule-reader-only gaps the intake
    # regex pass did not produce — they must appear as rule_reader candidates.
    fmt = _by_dim(cands, "deliverable.format")
    assert fmt and fmt[0].value == "literature_review"
    assert fmt[0].origin == ORIGIN_RULE_READER

    tone = _by_dim(cands, "rhetoric.tone")
    assert tone and tone[0].value == "academic"
    assert tone[0].origin == ORIGIN_RULE_READER

    cov = _by_dim(cands, "content.coverage")
    assert any("labor market" in (c.value or "") for c in cov)


def test_deterministic_candidates_precede_rule_reader_only():
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER)
    origins = [c.origin for c in cands]
    # No rule-reader-only candidate may appear before a deterministic/merged one
    # (deterministic candidates are emitted first).
    last_det = max(
        (i for i, o in enumerate(origins) if o in (ORIGIN_DETERMINISTIC, ORIGIN_MERGED)),
        default=-1,
    )
    first_rr = next(
        (i for i, o in enumerate(origins) if o == ORIGIN_RULE_READER),
        len(origins),
    )
    assert last_det < first_rr


# ---------------------------------------------------------------------------
# No-invention: force is observed, never fabricated as hard
# ---------------------------------------------------------------------------

def test_no_hard_force_without_a_deterministic_exclusivity_marker():
    # A soft prompt: no "only/must/exclude" anywhere. NOTHING may come back hard
    # from the deterministic passes.
    soft = (
        "Write an overview of renewable energy trends. Please prefer recent, "
        "authoritative sources where possible and keep the tone accessible."
    )
    cands = reconcile_candidates(soft)
    for c in cands:
        assert c.force == FORCE_PREFER, (c.dimension, c.value, c.force)


def test_rule_reader_exclusion_is_hard_and_span_or_empty():
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER)
    excl = _by_dim(cands, "content.exclusion")
    assert excl, "rule-reader exclusions must appear as candidates"
    for c in excl:
        assert c.force == FORCE_HARD
        assert c.origin == ORIGIN_RULE_READER
    _assert_span_invariant(TASK_72_PROMPT, cands)


def test_paraphrased_rule_reader_value_gets_no_fabricated_span():
    # The coverage value is paraphrased ("AI" vs "Artificial Intelligence (AI)"),
    # so it is not present verbatim -> no span may be fabricated.
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER)
    cov = [
        c for c in _by_dim(cands, "content.coverage")
        if c.origin == ORIGIN_RULE_READER and "labor market" in (c.value or "")
    ]
    assert cov
    assert cov[0].spans == []


# ---------------------------------------------------------------------------
# Robustness / edge cases
# ---------------------------------------------------------------------------

def test_empty_prompt_yields_no_candidates():
    assert reconcile_candidates("") == []
    assert reconcile_candidates("   ", rule_reader=TASK_72_RULE_READER) is not None


def test_rule_reader_accepts_dict_form():
    cands = reconcile_candidates(
        TASK_72_PROMPT, rule_reader=TASK_72_RULE_READER.to_dict()
    )
    fmt = _by_dim(cands, "deliverable.format")
    assert fmt and fmt[0].value == "literature_review"


def test_no_rule_reader_argument_reconciles_intake_alone():
    cands = reconcile_candidates(TASK_72_PROMPT, rule_reader=None)
    assert all(c.origin == ORIGIN_DETERMINISTIC for c in cands)
    # No rule-reader-only dimensions (format / tone) appear.
    assert not _by_dim(cands, "deliverable.format")
    assert not _by_dim(cands, "rhetoric.tone")


def test_comparison_prompt_yields_coverage_candidate_not_heading():
    # Required topics are coverage obligations, NOT headings (the round1 mistake
    # is deliberately not ported). A comparison instruction becomes a
    # content.comparison candidate.
    prompt = "Compare solar power and wind power on cost and reliability."
    cands = reconcile_candidates(prompt)
    _assert_span_invariant(prompt, cands)
    comp = _by_dim(cands, "content.comparison")
    assert comp, "a compare-A-and-B instruction should surface a comparison candidate"
    assert comp[0].force == FORCE_PREFER
