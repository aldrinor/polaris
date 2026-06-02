"""I-meta-008 P1-3 (#1018) — Phase-7 quantified telemetry `fired` normalization.

The quantified block in run_one_query never aborts the run (broad except), so an error or
spec_produced=False would otherwise complete silently without the differentiator. The manifest now
carries a normalized `fired` boolean so a post-run assertion can detect a silent no-op. SPEND-FREE.
"""
from __future__ import annotations

from scripts.run_honest_sweep_r3 import _normalize_quantified_telemetry


def test_fired_true_when_verified_sentences_positive():
    t = _normalize_quantified_telemetry({"verified_sentences": 3, "spec_produced": True})
    assert t["fired"] is True


def test_fired_false_when_no_verified_sentences():
    # spec_produced=False / no quantified section produced -> NOT fired (visible silent no-op).
    t = _normalize_quantified_telemetry({"verified_sentences": 0, "spec_produced": False})
    assert t["fired"] is False


def test_fired_false_on_broad_except_error_path():
    # the run_one_query error path carries {enabled, error} with NO verified_sentences -> NOT fired.
    t = _normalize_quantified_telemetry({"enabled": True, "error": "boom"})
    assert t["fired"] is False


def test_idempotent_preserves_explicit_fired():
    # setdefault must NOT override an explicitly-set value.
    t = _normalize_quantified_telemetry({"verified_sentences": 0, "fired": True})
    assert t["fired"] is True
