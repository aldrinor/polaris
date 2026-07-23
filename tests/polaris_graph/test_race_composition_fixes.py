from types import SimpleNamespace

from src.polaris_graph.generator import cleaned_output_guard, narrative_consolidation
from src.polaris_graph.generator.cleaned_output_guard import find_malformed_tables
from src.polaris_graph.generator.coverage_obligations import (
    audit_fulfillment,
    build_obligations,
    render_sections_preserving_outline,
    thread_obligations,
)
from src.polaris_graph.generator.multi_section_generator import (
    LIMITATIONS_SYSTEM_PROMPT_READER,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    _render_section_report_blueprint,
    _select_section_system_prompt,
)
from src.polaris_graph.generator.narrative_consolidation import (
    thread_narrative_guidance,
)
from src.polaris_graph.retrieval.exclusive_citation_eligibility import (
    _unknown_row_has_journal_signal,
    known_non_journal_surface,
)


def _section(title: str, text: str, *, dropped: bool = False):
    return SimpleNamespace(
        title=title,
        verified_text=text,
        dropped_due_to_failure=dropped,
        is_gap_stub=False,
    )


def test_narrative_guidance_is_retained_as_pre_generation_instruction():
    plans = [SimpleNamespace(focus="Compare the evidence.")]

    thread_narrative_guidance(plans)

    assert "why they agree, differ, or alter the interpretation of one another" in plans[0].focus
    assert "publication type, representativeness, and risk of bias" in plans[0].focus
    for template in (
        SECTION_SYSTEM_PROMPT_TEMPLATE,
        SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    ):
        assert "why they agree, differ, or alter the interpretation of one another" in template
        assert "rather than implementation vocabulary" in template


def test_section_prompts_lock_writer_native_readability_rules():
    required_rules = (
        "MUST be on its own physical line, preceded and followed by a blank line",
        "State each factual finding or statistic ONCE, at full precision",
        "Use a Markdown table ONLY when genuinely comparable sources",
        "Never mention an internal evidence identifier such as `ev_119` as prose",
        "Write for a reader, not a sentence or citation tally.",
        "Organize the section into coherent paragraphs of about 3-6 sentences",
        "Never reuse this prompt's own working vocabulary in the report.",
        "When reliable metadata is available, name a study or author on first use",
        "A paragraph that only inventories findings, one per sentence, is not synthesis.",
        "The conclusion must be the final section",
    )

    for template in (
        SECTION_SYSTEM_PROMPT_TEMPLATE,
        SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    ):
        for rule in required_rules:
            assert rule in template


def test_report_blueprint_gives_writer_every_section_ownership():
    plans = [
        SimpleNamespace(title="Context", focus="Define the setting."),
        SimpleNamespace(title="Findings", focus="Own the principal measured effects."),
        SimpleNamespace(title="Implications", focus="Explain boundaries and implications."),
    ]

    blueprint = _render_section_report_blueprint(plans, plans[1])

    assert "1. Context [OTHER SECTION] — owns: Define the setting." in blueprint
    assert (
        "2. Findings [CURRENT; followed by: Implications] — owns: "
        "Own the principal measured effects."
    ) in blueprint
    assert "3. Implications [OTHER SECTION] — owns:" in blueprint


def test_post_generation_narrative_surgery_is_not_importable():
    assert not hasattr(narrative_consolidation, "consolidate_sections")
    assert not hasattr(narrative_consolidation, "_apply_sentence_edits")


def test_basket_synthesis_uses_full_section_template(monkeypatch):
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANTI_VERBOSITY", "0")

    prompt = _select_section_system_prompt(use_field_agnostic=True)

    assert "Target 10-18 sentences of source-anchored prose" not in prompt
    assert "50-200 citations" not in prompt
    assert "Write for a reader, not a sentence or citation tally." in prompt
    assert "FRONT-LOADING (inverted pyramid)" not in prompt


def test_reader_register_and_paragraph_preservation_default_on(monkeypatch):
    monkeypatch.delenv("PG_LIMITATIONS_REGISTER", raising=False)
    monkeypatch.delenv("PG_RENDER_BLOCKS", raising=False)

    from src.polaris_graph.generator import multi_section_generator as msg

    assert msg._select_limitations_prompt() is LIMITATIONS_SYSTEM_PROMPT_READER
    assert msg._render_blocks_enabled() is True
    assert "Never mention pipeline stages, telemetry, tier labels" in LIMITATIONS_SYSTEM_PROMPT_READER


def test_active_templates_have_no_length_or_citation_tallies():
    banned = (
        "Target 10-18 sentences",
        "50-200 citations",
        "TARGET 20-35 sentences",
        "TARGET 15-20 sentences",
        "TARGET 10-15 sentences",
        "citation density",
        "cite at least 5 DISTINCT sources",
        "8-10 words",
    )
    for template in (
        SECTION_SYSTEM_PROMPT_TEMPLATE,
        SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    ):
        for phrase in banned:
            assert phrase not in template


def test_coverage_audit_flags_unrendered_required_concept(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_OBLIGATIONS", "1")
    obligations = build_obligations([
        "a named conceptual frame",
        "effects across various settings",
    ])
    plans = [
        SimpleNamespace(title="Context", focus="Set context."),
        SimpleNamespace(title="Conclusion", focus="Conclude."),
    ]
    thread_obligations(plans, obligations)

    audit = audit_fulfillment(
        obligations,
        [_section("Context", "The named conceptual frame is discussed.")],
    )

    assert len(audit["missing"]) == 1
    assert audit["missing"][0]["concept"] == "effects across various settings"
    assert obligations[1].role == "cross-context comparison"
    assert "closing synthesis" in plans[-1].focus


def test_missing_planned_section_is_telemetry_only():
    outline = [
        SimpleNamespace(title="Context"),
        SimpleNamespace(title="Comparative findings"),
    ]
    sections = [
        _section("Context", "Rendered evidence. [1]"),
        _section("Additional evidence", "Additional generated evidence. [2]"),
    ]

    rendered, missing = render_sections_preserving_outline(outline, sections)

    joined = "\n\n".join(rendered)
    assert "Rendered evidence. [1]" in joined
    assert "Additional generated evidence. [2]" in joined
    assert "## Comparative findings" not in joined
    assert "could not be rendered" not in joined
    assert missing == ["Comparative findings"]


def test_cleaned_output_detector_reports_without_repairing():
    markdown = (
        "| Context | Relationship |\n"
        "| --- | --- |\n"
        "| First | A comparison begins\n"
        "and continues outside the row |\n"
    )

    defects = find_malformed_tables(markdown)

    assert any(defect.reason == "multiline_cell" for defect in defects)
    assert not hasattr(cleaned_output_guard, "repair_for_cleaning")
    assert not hasattr(cleaned_output_guard, "_table_to_prose")


def test_cleaned_output_detector_accepts_well_formed_table():
    markdown = "| Context | Relationship |\n| --- | --- |\n| First | Comparison |\n"
    assert find_malformed_tables(markdown) == []


def test_generic_journal_surface_classifiers_remain_available():
    assert known_non_journal_surface({
        "title": "Working paper manuscript",
        "source_url": "https://www.nber.org/papers/w12345",
    }) is True
    assert _unknown_row_has_journal_signal({
        "title": "A supported research article",
        "source_url": "https://journals.example.org/review/articles/10.1234/example/full",
    }) is True
