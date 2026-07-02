"""Standalone tests for the mis-attribution disclosure guard (I-deepfix-001).

Covers the leaf guard (`attribution_origin_reason`) AND its integration into
`verify_sentence_provenance` (the sole strict_verify gate). The forced-positive
case injects the EXACT live bad evidence from
`outputs/iwire009_certify_local/report.md:1111-1113` — an
"International Labour Organization and Poland's National Research Institute found
that 3.5% ..." claim cited to `unric.org` (a re-reporting UN Regional Information
Centre), which every existing faithfulness gate passes because the secondary
source's span verbatim restates the attribution clause.

Faithfulness-safety asserts (§-1.3): the guard is DISCLOSURE-ONLY — it appends a
soft-warning, it NEVER drops the sentence, NEVER flips is_verified, NEVER touches
strict_verify / NLI / D8. Negative controls prove a PRIMARY-source citation, a
no-finder claim, and an opaque-domain citation are NOT flagged, and that on-topic
distinct content is never withheld or merged.

Run: PYTHONPATH=. python -m pytest tests/polaris_graph/test_attribution_origin_guard.py -q
"""

from __future__ import annotations

import os

from src.polaris_graph.generator.attribution_origin_guard import (
    _domain_signature,
    attribution_origin_reason,
)
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)

# The exact live claim (mis-attribution): names ILO + Poland's National Research
# Institute as the finders. The cited source is a re-reporting secondary.
_CLAIM = (
    "International Labour Organization and Poland's National Research Institute "
    "found that 3.5% of men's jobs are at high risk from automation"
)
_SECONDARY_SPAN = (
    "Poland's National Research Institute found that 3.5% of men's jobs are at "
    "high risk from automation, according to a new report."
)


def _pool(ev_id: str, url: str, span: str) -> dict:
    return {ev_id: {"direct_quote": span, "source_url": url, "statement": span}}


def _tokened(sentence: str, ev_id: str, span: str) -> str:
    """Append a full-span provenance token so strict_verify has a valid cite."""
    return f"{sentence}. [#ev:{ev_id}:0-{len(span)}]"


# ─────────────────────────────────────────────────────────────────────────────
# Leaf-guard unit tests.
# ─────────────────────────────────────────────────────────────────────────────
def test_domain_signature_extracts_publisher_identity() -> None:
    assert _domain_signature("https://unric.org/en/ilo-report") == {"unric"}
    assert _domain_signature("https://www.ilo.org/global/x") == {"ilo"}
    assert _domain_signature("https://www.who.int/news/x") == {"who"}
    assert _domain_signature("https://www.bls.gov/report") == {"bls"}
    # Opaque publisher identity -> empty signature (fail-open triggers).
    assert _domain_signature("https://gov.pl/report") == set()
    assert _domain_signature("https://doi.org/10.1086/705716") == set()
    assert _domain_signature("") == set()


def test_forced_positive_secondary_reporter_flagged() -> None:
    """FORCED POSITIVE: ILO/Poland-NRI finding cited to unric.org -> disclosure."""
    reason = attribution_origin_reason(_CLAIM, ["https://unric.org/en/ilo-report"])
    assert reason is not None, "mis-attribution to a re-reporting domain must flag"
    assert reason.startswith("attribution_origin_unverified:")
    assert "unric" in reason


def test_control_primary_source_not_flagged() -> None:
    """NEGATIVE CONTROL: same claim cited to the PRIMARY ilo.org -> no disclosure."""
    reason = attribution_origin_reason(_CLAIM, ["https://www.ilo.org/global/report"])
    assert reason is None, "a citation to the named org's own domain must not flag"


def test_control_no_named_finder_not_flagged() -> None:
    """NEGATIVE CONTROL: a claim with no named org finder -> inert (no false fire)."""
    benign = "Approximately 3.5% of men's jobs are at high risk from automation"
    reason = attribution_origin_reason(benign, ["https://unric.org/en/ilo-report"])
    assert reason is None


def test_control_opaque_domain_fail_open() -> None:
    """NEGATIVE CONTROL: opaque publisher domain -> FAIL-OPEN (never flag)."""
    reason = attribution_origin_reason(_CLAIM, ["https://gov.pl/report"])
    assert reason is None, "an opaque domain cannot be ruled out as the actor"


def test_control_multi_source_one_matching_primary_not_flagged() -> None:
    """NEGATIVE CONTROL: when a co-cited PRIMARY (ilo.org) is present, no flag."""
    reason = attribution_origin_reason(
        _CLAIM,
        ["https://unric.org/en/ilo-report", "https://www.ilo.org/global/report"],
    )
    assert reason is None


def test_internal_and_org_name_matched_by_true_acronym() -> None:
    """PRECISION: 'Food and Drug Administration' cited to fda.gov must NOT flag
    (the internal 'and' must not mangle the acronym into a false mismatch)."""
    claim = "The Food and Drug Administration reported that 12% of devices failed"
    reason = attribution_origin_reason(claim, ["https://www.fda.gov/news/x"])
    assert reason is None
    # ...but the SAME claim cited to an unrelated re-publisher DOES flag.
    reason2 = attribution_origin_reason(claim, ["https://www.example-news.com/x"])
    assert reason2 is not None
    assert reason2.startswith("attribution_origin_unverified:")


def test_guard_disabled_is_inert() -> None:
    prev = os.environ.get("PG_ATTRIBUTION_ORIGIN_GUARD")
    os.environ["PG_ATTRIBUTION_ORIGIN_GUARD"] = "0"
    try:
        assert attribution_origin_reason(_CLAIM, ["https://unric.org/x"]) is None
    finally:
        if prev is None:
            os.environ.pop("PG_ATTRIBUTION_ORIGIN_GUARD", None)
        else:
            os.environ["PG_ATTRIBUTION_ORIGIN_GUARD"] = prev


# ─────────────────────────────────────────────────────────────────────────────
# Integration into the sole strict_verify gate (verify_sentence_provenance).
# Entailment judge is turned OFF so the test is fully offline/deterministic and
# exercises the mechanical checks + the additive disclosure leg.
# ─────────────────────────────────────────────────────────────────────────────
def _verify_offline(sentence: str, pool: dict):
    prev = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT")
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"
    try:
        return verify_sentence_provenance(sentence, pool)
    finally:
        if prev is None:
            os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)
        else:
            os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = prev


def test_integration_disclosure_appended_never_dropped() -> None:
    """The soft-warning is surfaced AND the sentence is NOT dropped (disclosure,
    not a hard drop) — content is never withheld (§-1.3 faithfulness-safety)."""
    pool = _pool("e1", "https://unric.org/en/ilo-report", _SECONDARY_SPAN)
    sv = _verify_offline(_tokened(_CLAIM, "e1", _SECONDARY_SPAN), pool)
    assert sv.is_verified, "disclosure must NOT drop a span-supported sentence"
    attr = [w for w in sv.soft_warnings if w.startswith("attribution_origin_unverified:")]
    assert attr, f"expected an attribution disclosure warning, got {sv.soft_warnings}"
    # The disclosure is NEVER a failure reason (never routes to the drop path).
    assert not any("attribution_origin" in r for r in sv.failure_reasons)


def test_integration_primary_source_no_disclosure() -> None:
    """NEGATIVE CONTROL: a distinct PRIMARY source (ilo.org) verifying the SAME
    on-topic claim is NOT flagged and NOT withheld."""
    pool = _pool("e1", "https://www.ilo.org/global/report", _SECONDARY_SPAN)
    sv = _verify_offline(_tokened(_CLAIM, "e1", _SECONDARY_SPAN), pool)
    assert sv.is_verified
    assert not any(
        w.startswith("attribution_origin_unverified:") for w in sv.soft_warnings
    )


if __name__ == "__main__":  # pragma: no cover - manual smoke
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL PASS")
