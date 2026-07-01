"""I-deepfix-001 WS-7 (D3) — the chrome canary now scores PROSE, not just bullets.

Behavioral, offline. Proves the canary is no longer blind to in-prose chrome (drb_72: 0/33 bullets flagged
while prose leaked). MEASUREMENT ONLY — the canary computes a rate/verdict; it never drops a rendered unit.

NOTE: the shared predicate `is_render_chrome_or_unrenderable` catches license/copyright/masthead classes
(used here) but is still blind to some in-prose classes (a leading bare section-header word, an in-text
"(1, 2)" ref marker, a truncated "(YYYY)" subject) — unblinding it is the WS-7 follow-on reconcile with the
in-progress I-wire-013 render seam. This test covers the DENOMINATOR fix (prose is now scored) with a class
the predicate already catches.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    _report_prose_units,
    evaluate_render_chrome_canary,
)

# A report whose ONLY chrome is in PROSE (not a bullet): a clean claim bullet + a license/copyright prose
# leak in a findings section, plus a Bibliography (scaffolding) whose DOI must be EXCLUDED from scoring.
_REPORT = """# Research report: does automation displace labor?

## Key findings

- Automation raised manufacturing output by 12 percent over the decade [1].

Copyright 2024 Elsevier B.V. All rights reserved. Terms and Conditions apply to this article.

## Bibliography

[1] Example et al. — https://doi.org/10.1016/j.jom.2024.01.002 (tier T1)
"""


def _clear(monkeypatch):
    for k in ("PG_RENDER_CHROME_CANARY", "PG_RENDER_CHROME_CANARY_FLOOR", "PG_RENDER_CHROME_CANARY_PROSE"):
        monkeypatch.delenv(k, raising=False)


def test_prose_units_excludes_bullets_headers_scaffolding(monkeypatch):
    _clear(monkeypatch)
    units = _report_prose_units(_REPORT)
    joined = " ".join(units)
    assert any("Copyright 2024 Elsevier" in u for u in units), "a prose paragraph line must be a scored unit"
    assert "Automation raised manufacturing" not in joined, "top-level bullets are NOT prose units (scored separately)"
    assert "doi.org" not in joined, "Bibliography (scaffolding) DOIs must be EXCLUDED from prose units"
    assert "Research report:" not in joined, "the H1 question echo is a header, not a prose unit"


def test_canary_scores_prose_chrome_when_on(monkeypatch):
    _clear(monkeypatch)  # default => prose ON
    res = evaluate_render_chrome_canary(_REPORT)
    assert res["prose_units_scored"] >= 1, "prose units are in the denominator"
    assert res["chrome_claim_bullets"] >= 1, "the in-prose license chrome is now COUNTED (was blind before)"
    assert res["total_claim_units"] > 1, "denominator = bullets + prose"


def test_canary_blind_to_prose_when_off_is_byte_identical(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY_PROSE", "0")
    res = evaluate_render_chrome_canary(_REPORT)
    assert res["prose_units_scored"] == 0, "flag OFF => prose not scored (bullets-only, pre-WS-7)"
    # The one clean bullet is not chrome => 0 chrome when blind to prose.
    assert res["chrome_claim_bullets"] == 0, "OFF => the in-prose chrome is NOT counted (legacy blindness)"


def test_enforce_mode_trips_on_prose_chrome_only_when_scored(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY", "enforce")
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY_FLOOR", "0.05")
    # Prose ON => the prose chrome trips the canary fail-closed.
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY_PROSE", "1")
    assert evaluate_render_chrome_canary(_REPORT)["verdict"] == "fail", "prose chrome trips enforce"
    # Prose OFF => canary blind to prose => passes (the pre-WS-7 miss).
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY_PROSE", "0")
    assert evaluate_render_chrome_canary(_REPORT)["verdict"] == "pass", "blind-to-prose passes (the D3 miss)"


def test_clean_prose_report_passes(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_RENDER_CHROME_CANARY", "enforce")
    clean = "## Key findings\n\nAutomation raised output by twelve percent over the studied decade [1].\n"
    assert evaluate_render_chrome_canary(clean)["verdict"] == "pass", "a clean prose report never trips"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
