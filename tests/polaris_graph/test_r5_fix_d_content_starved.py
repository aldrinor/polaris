"""
R-5 Fix D regression tests: filter content-starved evidence.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.live_retriever import is_content_starved


def test_r5_empty_content_is_starved() -> None:
    assert is_content_starved("") is True
    assert is_content_starved("   \n\n  ") is True


def test_r5_very_short_content_is_starved() -> None:
    assert is_content_starved("Too short.") is True
    assert is_content_starved("a" * 100) is True  # below 200 char min


def test_r5_normal_prose_not_starved() -> None:
    prose = (
        "Semaglutide 2.4 mg once weekly produces a mean weight loss of "
        "14.9% at week 68 in adults with overweight or obesity. This "
        "result was statistically significant compared with placebo. "
        "The most common adverse events were gastrointestinal. "
        "Long-term safety data from STEP 5 extended to 104 weeks. "
        "Multiple regulatory agencies including FDA and EMA have "
        "approved the 2.4 mg dose for chronic weight management."
    )
    assert is_content_starved(prose) is False


def test_r5_pdf_metadata_detected() -> None:
    fake_pdf = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog >> endobj\n"
        "2 0 obj << /Type /Pages /Count 1 >> endobj\n"
        "3 0 obj\nstream\n" + "x" * 500 + "\nendstream endobj\n"
        "xref\ntrailer << /Root 1 0 R >>\nstartxref\n"
    )
    assert is_content_starved(fake_pdf) is True


def test_r5_formatting_noise_detected() -> None:
    # Lots of angle-bracket dictionary markers, minimal prose
    noise = (
        "<< /Contents 1 0 R /MediaBox [0 0 612 792] /Font << /F1 2 0 R "
        ">> >> \nstream\n << /Contents 3 0 R >> << /Font << /F2 4 0 R "
        ">> >> stream\n << /Contents 5 0 R >> \nstream\n << /Contents "
        "7 0 R >> stream\n << /Contents 9 0 R >> \nstream\n" * 5
    )
    assert is_content_starved(noise) is True


def test_r5_high_alpha_ratio_not_starved() -> None:
    # High alpha content even if short lines — prose, not metadata
    text = (
        "Semaglutide is a GLP-1 receptor agonist indicated for chronic "
        "weight management in adults with obesity. In clinical trials, "
        "mean weight loss at week 68 exceeded placebo by a significant "
        "margin across multiple populations. Safety findings included "
        "gastrointestinal adverse events that were generally transient."
    )
    assert is_content_starved(text) is False


def test_r5_low_alpha_ratio_is_starved() -> None:
    # Mostly numbers and punctuation, low alphabetic ratio
    numeric = (
        "1 0 0 0 0 0 0 0 0 0 0 1 1 2 3 5 8 13 21 34 55 89 144 233 "
        "377 610 987 1597 2584 4181 6765 10946 17711 28657 46368 75025"
    ) * 10
    assert is_content_starved(numeric) is True


def test_r5_custom_min_threshold() -> None:
    text = "Some short prose here with extra padding to clear 200 chars. " * 5
    # Default 200 char threshold — 305 chars now
    assert len(text) > 200
    assert is_content_starved(text) is False
    # Raise the threshold
    assert is_content_starved(text, min_useful_chars=500) is True
