"""Residual verified prose may be routed before generation, never dropped after."""

from types import SimpleNamespace

from scripts.compose_agentic_report_s3gear329 import _sections_for_render


def test_legacy_zero_flag_cannot_remove_verified_residual(monkeypatch):
    monkeypatch.setenv("PG_INCLUDE_RESIDUAL_SECTION", "0")
    sections = [
        SimpleNamespace(
            title="Topical body", verified_text="Body [1].", dropped_due_to_failure=False,
        ),
        SimpleNamespace(
            title="Additional Corroborated Findings",
            verified_text="Residual evidence [2].",
            dropped_due_to_failure=False,
        ),
    ]
    rendered = _sections_for_render(sections)
    assert [section.title for section in rendered] == [
        "Topical body", "Additional Corroborated Findings",
    ]


def test_required_title_ordering_keeps_residual_and_every_other_section():
    sections = [
        SimpleNamespace(title="Second", verified_text="B [2].", dropped_due_to_failure=False),
        SimpleNamespace(title="First", verified_text="A [1].", dropped_due_to_failure=False),
        SimpleNamespace(title="Residual", verified_text="C [3].", dropped_due_to_failure=False),
    ]
    rendered = _sections_for_render(sections, ["First", "Second"])
    assert [section.title for section in rendered] == ["First", "Second", "Residual"]


def test_conclusion_is_always_the_final_rendered_section():
    sections = [
        SimpleNamespace(title="Conclusion", verified_text="Close [1].", dropped_due_to_failure=False),
        SimpleNamespace(title="Body", verified_text="Body [2].", dropped_due_to_failure=False),
        SimpleNamespace(title="Limitations", verified_text="Limits.", dropped_due_to_failure=False),
    ]

    rendered = _sections_for_render(sections, ["Conclusion", "Body"])

    assert [section.title for section in rendered] == ["Body", "Limitations", "Conclusion"]
