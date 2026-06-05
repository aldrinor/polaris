"""I-ready-014 (#1083) — anti-overcomplication / sharp-reporter concision.

Offline, spend-free, no-network smoke for the `PG_ANTI_VERBOSITY` env-flag-gated
front-loading + information-density section-prompt variant. Proves BOTH halves of
the task:
  (1) front-loading directive present when the flag is ON, absent when OFF;
  (2) the length-maximizing language ("match GPT-5.4 / Gemini density",
      "50-200 citations", the Mechanism "TARGET 20-35 sentences") is REPLACED
      when ON.

Default OFF is byte-identical: the selector returns the ORIGINAL template OBJECT
(identity-equal) so the locked 5-question benchmark is unchanged until the flag is
set. No strict_verify / provenance / 4-role seam is touched — this is prompt text
only.

Serialized + spend-free (§8.4): no `unittest.mock`, no live client, no GPU. Every
check calls the pure selector / transform directly.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_SYSTEM_PROMPT_TEMPLATE_CONCISE,
    SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC_CONCISE,
    _anti_verbosity_enabled,
    _build_concise_variant,
    _select_section_system_prompt,
)

# The length-maximizing clauses the finding flags; ON must NOT contain any of
# these, OFF must still contain them (byte-identical wall).
_LENGTH_BIAS_PHRASES_CLINICAL = (
    "match that depth",
    "50-200 citations",
    "TARGET 20-35 sentences",
    "TARGET 15-20 sentences",  # M-42c mid-pool floor — must also be tempered
    "TARGET 10-15 sentences",  # M-42c thin-pool floor — must also be tempered
    "routinely reaches 50-200 citations",
    "rule #8 target of 10-18 sentences applies as usual",  # stale back-ref
)
_LENGTH_BIAS_PHRASES_FIELD_AGNOSTIC = (
    "match it where the evidence supports",
    "Top-tier Deep Research reports reach this density",
)

_FRONT_LOAD_LEAD = "FRONT-LOADING (inverted pyramid):"
_DENSITY_RULE = "Length is earned by distinct facts, not sentence count"


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the flag UNSET (default OFF)."""
    monkeypatch.delenv("PG_ANTI_VERBOSITY", raising=False)


# ─────────────────────────────────────────────────────────────────────────────
# OFF = byte-identical (identity-equal to the original template object).
# ─────────────────────────────────────────────────────────────────────────────

def test_off_returns_original_template_object_identity() -> None:
    # Default arg (anti_verbosity omitted) AND explicit False both return the
    # ORIGINAL object — the strongest possible byte-identity proof.
    assert _select_section_system_prompt(False) is SECTION_SYSTEM_PROMPT_TEMPLATE
    assert (
        _select_section_system_prompt(False, anti_verbosity=False)
        is SECTION_SYSTEM_PROMPT_TEMPLATE
    )
    assert (
        _select_section_system_prompt(True)
        is SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC
    )
    assert (
        _select_section_system_prompt(True, anti_verbosity=False)
        is SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC
    )


def test_off_clinical_template_keeps_length_bias_unchanged() -> None:
    off = _select_section_system_prompt(False)
    for phrase in _LENGTH_BIAS_PHRASES_CLINICAL:
        assert phrase in off, f"OFF clinical template lost {phrase!r}"
    assert _FRONT_LOAD_LEAD not in off, "OFF must NOT carry the front-load lead"


def test_off_field_agnostic_template_keeps_length_bias_unchanged() -> None:
    off = _select_section_system_prompt(True)
    for phrase in _LENGTH_BIAS_PHRASES_FIELD_AGNOSTIC:
        assert phrase in off, f"OFF field-agnostic template lost {phrase!r}"
    assert _FRONT_LOAD_LEAD not in off


# ─────────────────────────────────────────────────────────────────────────────
# ON = front-loading present + length-maximizing language REPLACED.
# ─────────────────────────────────────────────────────────────────────────────

def test_on_clinical_variant_front_loads_and_drops_length_bias() -> None:
    on = _select_section_system_prompt(False, anti_verbosity=True)
    assert on is SECTION_SYSTEM_PROMPT_TEMPLATE_CONCISE
    # Front-loading directive is present AND is the very first content.
    assert on.startswith(_FRONT_LOAD_LEAD)
    assert _DENSITY_RULE in on
    # Every length-bias phrase is gone (the REPLACE half of the task).
    for phrase in _LENGTH_BIAS_PHRASES_CLINICAL:
        assert phrase not in on, f"ON clinical variant still contains {phrase!r}"
    # The multi-source-CITATION behavior (a faithfulness/citation rule, not a
    # length rule) is preserved — only the length-bias tail was dropped.
    assert "cite ALL of them" in on


def test_on_field_agnostic_variant_front_loads_and_drops_length_bias() -> None:
    on = _select_section_system_prompt(True, anti_verbosity=True)
    assert on is SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC_CONCISE
    assert on.startswith(_FRONT_LOAD_LEAD)
    assert _DENSITY_RULE in on
    for phrase in _LENGTH_BIAS_PHRASES_FIELD_AGNOSTIC:
        assert phrase not in on, (
            f"ON field-agnostic variant still contains {phrase!r}"
        )
    # The field-agnostic multi-source citation rule is preserved.
    assert "cite ALL of them" in on


# ─────────────────────────────────────────────────────────────────────────────
# Env-flag helper: default OFF, parses truthy/falsey at CALL TIME.
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_ANTI_VERBOSITY", raising=False)
    assert _anti_verbosity_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "On"])
def test_flag_truthy_values_enable(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PG_ANTI_VERBOSITY", value)
    assert _anti_verbosity_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no", "  "])
def test_flag_falsey_values_keep_off(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PG_ANTI_VERBOSITY", value)
    assert _anti_verbosity_enabled() is False


# ─────────────────────────────────────────────────────────────────────────────
# Seam coherence: the surgical replacements must not orphan list headers or
# leave a dangling connector. Guards against the "absent-phrase but garbled-text"
# blind spot — the ON clinical prompt is the §-1.1 patient-safety path.
# ─────────────────────────────────────────────────────────────────────────────

def test_concise_clinical_variant_has_no_orphaned_seams() -> None:
    concise = SECTION_SYSTEM_PROMPT_TEMPLATE_CONCISE
    # The Mechanism list header "approximate priority order):" must not survive as
    # an orphan after its "TARGET 20-35 ... covering (in" lead was replaced.
    assert "order):" not in concise
    # Rule #10 must close on a period, not a dangling em-dash before the next rule.
    rule_10_start = concise.find("10. **Multi-source citation")
    rule_11_start = concise.find("11. **Jurisdictional precision", rule_10_start)
    rule_10_body = concise[rule_10_start:rule_11_start].rstrip()
    assert rule_10_body.endswith("where evidence supports it."), (
        f"rule #10 did not close cleanly: {rule_10_body[-60:]!r}"
    )


def test_concise_variant_introduces_no_new_dangling_em_dash_lines() -> None:
    # My transform must not create a line that ENDS in a bare em-dash with nothing
    # after it. The pre-existing M-47 worked-example line (whose explanation wraps
    # to the next physical line) is original content and is excluded by the
    # set-difference: only lines NEW to the concise variant are checked.
    em_dash = "—"

    def em_dash_terminated_lines(text: str) -> set[str]:
        return {ln for ln in text.splitlines() if ln.rstrip().endswith(em_dash)}

    for original, concise in (
        (SECTION_SYSTEM_PROMPT_TEMPLATE, SECTION_SYSTEM_PROMPT_TEMPLATE_CONCISE),
        (
            SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
            SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC_CONCISE,
        ),
    ):
        new_dangling = em_dash_terminated_lines(concise) - em_dash_terminated_lines(
            original
        )
        assert not new_dangling, (
            f"concise variant introduced dangling em-dash line(s): {new_dangling}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wiring: _call_section feeds the benchmark; assert it honors the flag at the
# real call site, not just the selector in isolation (closes the "built but not
# wired" failure mode). No network — the OpenRouter client is never constructed
# because the assertion fails BEFORE any LLM call would fire.
# ─────────────────────────────────────────────────────────────────────────────

def test_call_section_reads_flag_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import src.polaris_graph.generator.multi_section_generator as msg

    # Sentinel raised by the patched selector AFTER it records the flag value, so
    # the call site is exercised through the selector call but no network fires.
    class _StopAfterSelect(RuntimeError):
        pass

    selected: dict[str, object] = {}

    def _spy(use_field_agnostic: bool, anti_verbosity: bool = False) -> str:
        selected["anti_verbosity"] = anti_verbosity
        raise _StopAfterSelect

    monkeypatch.setattr(msg, "_select_section_system_prompt", _spy)

    # Empty evidence subset -> the wrap loop is skipped and the selector is the
    # next call, so the stop lands exactly where we want it.
    section = msg.SectionPlan(title="Efficacy", focus="x", ev_ids=[])

    # Flag ON -> the call site must pass anti_verbosity=True down to the selector.
    monkeypatch.setenv("PG_ANTI_VERBOSITY", "on")
    with pytest.raises(_StopAfterSelect):
        asyncio.run(msg._call_section(section, [], "m", 0.0, 100))
    assert selected["anti_verbosity"] is True

    # Flag OFF -> the call site must pass anti_verbosity=False (byte-identical).
    selected.clear()
    monkeypatch.setenv("PG_ANTI_VERBOSITY", "0")
    with pytest.raises(_StopAfterSelect):
        asyncio.run(msg._call_section(section, [], "m", 0.0, 100))
    assert selected["anti_verbosity"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Template-drift guard: the transform FAILS LOUD if the required anchor is gone.
# ─────────────────────────────────────────────────────────────────────────────

def test_transform_fails_loud_on_missing_required_anchor() -> None:
    # A template with no "Target 10-18 sentences ..." rule-8 anchor must raise —
    # so a future template edit cannot silently no-op the anti-verbosity
    # transform (I-cap-005 import-time-cache / silent-no-op lesson).
    with pytest.raises(RuntimeError, match="anti-verbosity transform anchor"):
        _build_concise_variant("CRITICAL RULES:\n1. Use ONLY facts.\n")
