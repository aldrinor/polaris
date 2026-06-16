"""A21a / BUG-22 (#1262) unit tests for the per-CALL TOTAL deadline resolver (ladder edition).

EVERY ``_call_impl`` call gets a total deadline so the retry-stack can never invert the B24
gen<section<run-wall ladder:
  - the generator-model AUXILIARY call_types (distill_map + friends) get the TIGHT budget
    (PG_LLM_CALL_TOTAL_DEADLINE_S, default 2400s — ABOVE the 1924s drb_90 legitimate-distill max,
    BELOW the section rung);
  - everything else (section / generate / outline / a NEW unlisted type) gets the generous SECTION
    tier (PG_LLM_CALL_SECTION_TOTAL_DEADLINE_S, default 9000s), floored at the per-attempt base so a
    full-length section's first attempt is never starved (§9.1.8).
No socket, no spend — pure resolver.
"""

from __future__ import annotations

import src.polaris_graph.llm.openrouter_client as oc

# B24 cert-slate per-attempt base for a reasoning-first generator section.
_SECTION_PER_ATTEMPT = 6500.0


def test_distill_map_is_tight_by_default(monkeypatch):
    monkeypatch.delenv(oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_ENV, raising=False)
    # distill_map must NOT inherit the section per-attempt base; it gets the tight 2400s.
    assert oc._call_total_deadline_seconds("distill_map", _SECTION_PER_ATTEMPT) == 2400.0


def test_aux_call_types_are_tight():
    for ct in ("distill_map", "fact_dedup", "repair", "validate_reasoning"):
        assert oc._call_total_deadline_seconds(ct, _SECTION_PER_ATTEMPT) == 2400.0


def test_tight_default_above_observed_legitimate_distill_max():
    """Forensic guard: drb_90's slowest SUCCEEDING distill_map was 1924s. The tight default MUST
    sit above it so a slow-but-succeeding distill is never fail-louded (the B24 truncation lesson)."""
    assert oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_DEFAULT > 1924.0


def test_section_call_types_get_section_tier():
    # The large-prose / section / outline / generate calls get the generous 9000s section tier,
    # NOT the per-attempt base (so the retry-stack is bounded, not just one attempt).
    for ct in ("contract_slot", "section_reduce", "outline", "generate", "regen",
               "m50_subsection", "limitations", "trial_table", "analyst_synthesis"):
        assert oc._call_total_deadline_seconds(ct, _SECTION_PER_ATTEMPT) == 9000.0


def test_unlisted_call_type_falls_to_section_tier():
    # A NEW, unmapped call_type errs on the never-starve side (the generous section tier).
    assert oc._call_total_deadline_seconds("some_future_call_type", _SECTION_PER_ATTEMPT) == 9000.0


def test_section_tier_floored_at_per_attempt_base():
    """If a caller's per-attempt budget exceeds the section default, the floor keeps the total >=
    one legitimate attempt (never starve a single full-length section)."""
    huge = 12000.0
    assert oc._call_total_deadline_seconds("contract_slot", huge) == huge


def test_section_retry_stack_bounded_below_run_wall():
    """The whole point of the ladder: a section's retry-stack total stays BELOW run-wall (10800s).
    The section tier (9000s) bounds the stack; a naive MAX_RETRIES x per-attempt (~19500s) would
    invert the ladder."""
    section_total = oc._call_total_deadline_seconds("contract_slot", _SECTION_PER_ATTEMPT)
    _RUN_WALL = 10800.0
    assert section_total < _RUN_WALL
    # And it is >= one legitimate full-length attempt (never starves the section itself).
    assert section_total >= _SECTION_PER_ATTEMPT


def test_tight_below_section_below_run_wall_ladder():
    """gen-aux (tight) < section < run-wall — the explicit ladder ordering."""
    tight = oc._call_total_deadline_seconds("distill_map", _SECTION_PER_ATTEMPT)
    section = oc._call_total_deadline_seconds("contract_slot", _SECTION_PER_ATTEMPT)
    assert tight < section < 10800.0


def test_tight_env_override_lowers_budget(monkeypatch):
    monkeypatch.setenv(oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_ENV, "900")
    assert oc._call_total_deadline_seconds("distill_map", _SECTION_PER_ATTEMPT) == 900.0


def test_section_env_override(monkeypatch):
    monkeypatch.setenv(oc._LLM_CALL_SECTION_TOTAL_DEADLINE_ENV, "9500")
    assert oc._call_total_deadline_seconds("contract_slot", _SECTION_PER_ATTEMPT) == 9500.0


def test_tight_env_does_not_touch_section(monkeypatch):
    monkeypatch.setenv(oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_ENV, "600")
    assert oc._call_total_deadline_seconds("contract_slot", _SECTION_PER_ATTEMPT) == 9000.0


def test_nonpositive_overrides_fall_back_to_default(monkeypatch):
    # A non-positive / unparseable override must NOT abort every call (falls back to the tier default).
    monkeypatch.setenv(oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_ENV, "0")
    assert oc._call_total_deadline_seconds("distill_map", _SECTION_PER_ATTEMPT) == 2400.0
    monkeypatch.setenv(oc._LLM_CALL_TOTAL_DEADLINE_TIGHT_ENV, "not-a-number")
    assert oc._call_total_deadline_seconds("distill_map", _SECTION_PER_ATTEMPT) == 2400.0
    monkeypatch.setenv(oc._LLM_CALL_SECTION_TOTAL_DEADLINE_ENV, "-5")
    assert oc._call_total_deadline_seconds("contract_slot", _SECTION_PER_ATTEMPT) == 9000.0
