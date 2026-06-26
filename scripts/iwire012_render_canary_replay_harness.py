"""I-wire-012 (#1326) OFFLINE replay harness — render/screen/canary/depth/contradiction.

NO live calls, NO model load, NO network. Proves the five acceptance points:
  1. a chrome unit is screened out of EVERY claim-emitting composer (incl. Corroborated
     Weighted Findings, the verified-compose section body, and the Key-Findings lift);
  2. a complete supported claim STILL renders (the precision guard — over-strip is worse
     than a leak);
  3. the chrome-as-claim CANARY trips on a forced chrome bullet (and passes clean);
  4. depth emits >0 key_findings on a report that ships a ``## Key Findings`` block;
  5. a numeric-noise (bare-year) "contradiction" is suppressed under the env flag, and the
     OFF path is byte-identical (the year-noise record is a possible_metric_mismatch).

Run: ``python scripts/iwire012_render_canary_replay_harness.py`` (exit 0 = all pass).
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

# Default-ON screen for the harness (the run slate sets the same).
os.environ.setdefault("PG_RENDER_CHROME_SCREEN", "1")

from src.polaris_graph.generator import verified_compose, weighted_enrichment
from src.polaris_graph.generator.key_findings import (
    _first_verified_sentences,
    build_depth_layer,
    build_key_findings,
)
from src.polaris_graph.generator.analytical_depth import (
    evaluate_analytical_depth,
    split_report_into_sections,
)
from src.polaris_graph.generator.weighted_enrichment import (
    build_verified_span_draft,
    evaluate_render_chrome_canary,
    is_render_chrome_or_unrenderable,
    render_chrome_canary_mode,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    ExtractedNumericClaim,
    _group_is_year_noise,
    detect_contradictions,
)

_REAL_CLAIM = (
    "Tirzepatide reduced body weight by 20.9 percent at week 72 in the SURMOUNT-1 trial."
)
_CHROME_UNITS = [
    "Economic Perspectives Volume 33, Number 2 Pages 3-30 ISSN: 1234-5678",
    "Licensed under a Creative Commons Attribution 4.0 International License.",
    "Jane Doe 0000-0002-1825-0097, John Roe 0000-0001-5109-3700",
    "10.1016/j.jclinepi.2020.03.001",
    "Abstract",
    "CITATIONS 12 READS 340",
    "comprehensi [...",
]

_failures: list[str] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        _failures.append(f"{name} {detail}".strip())


def test_shared_predicate_and_precision() -> None:
    print("1+2) shared predicate screens chrome / keeps a real claim")
    # 2) precision guard: a complete supported claim is NEVER chrome.
    _check("real claim not screened", not is_render_chrome_or_unrenderable(_REAL_CLAIM))
    _check(
        "real claim not screened (sentence-form)",
        not is_render_chrome_or_unrenderable(_REAL_CLAIM + " [1]", require_sentence_form=True),
    )
    # 1) every chrome unit screened.
    for u in _CHROME_UNITS:
        _check(f"chrome screened: {u[:32]!r}", bool(is_render_chrome_or_unrenderable(u)))


def test_corroborated_weighted_findings_composer() -> None:
    print("1) Corroborated Weighted Findings (weighted_enrichment.build_verified_span_draft)")
    pool = {
        "real": {"evidence_id": "real", "direct_quote": _REAL_CLAIM},
        "chrome": {
            "evidence_id": "chrome",
            "direct_quote": "Economic Perspectives Volume 33, Number 2 Pages 3-30 ISSN: 1234-5678",
        },
    }
    draft = build_verified_span_draft(["chrome", "real"], pool)
    _check("real span rendered", "20.9 percent" in (draft or ""), repr(draft)[:120])
    _check("chrome span dropped", "ISSN" not in (draft or "") and "Volume 33" not in (draft or ""))


def test_section_body_composer() -> None:
    print("1) section-body composer (verified_compose._compose_junk_screen)")
    _check("chrome screened by compose", verified_compose._compose_junk_screen(_CHROME_UNITS[0]))
    _check("real kept by compose", not verified_compose._compose_junk_screen(_REAL_CLAIM))


def test_key_findings_composer() -> None:
    print("1+2) Key-Findings / Abstract / Conclusion lift (_first_verified_sentences)")
    real = _REAL_CLAIM + "[1]"
    chrome = "Economic Perspectives Volume 33, Number 2 Pages 3-30 ISSN: 1234.[1]"
    _check("real finding lifted", _first_verified_sentences(real, 1) == [real])
    _check("chrome finding excluded", _first_verified_sentences(chrome, 1) == [])


def test_canary_trips_and_passes() -> None:
    print("3) chrome-as-claim canary trips on a forced chrome bullet, passes clean")
    os.environ["PG_RENDER_CHROME_CANARY"] = "enforce"
    os.environ["PG_RENDER_CHROME_CANARY_FLOOR"] = "0.0"
    chrome_report = (
        "## Key Findings\n\n"
        f"- **Efficacy.** {_REAL_CLAIM}[1]\n"
        "- **Masthead.** Economic Perspectives Volume 33, Number 2 Pages 3-30 ISSN: 1234[2]\n"
    )
    res = evaluate_render_chrome_canary(chrome_report)
    _check("forced chrome bullet trips", res["verdict"] == "fail", str(res))
    _check("chrome bullet counted", res["chrome_claim_bullets"] == 1, str(res))
    clean_report = (
        "## Key Findings\n\n"
        f"- **Efficacy.** {_REAL_CLAIM}[1]\n"
        f"- **Safety.** Nausea occurred in 12 percent of treated patients at week 24.[2]\n"
    )
    res_clean = evaluate_render_chrome_canary(clean_report)
    _check("clean report passes", res_clean["verdict"] == "pass", str(res_clean))
    _check("clean rate zero", res_clean["chrome_as_claim_rate"] == 0.0, str(res_clean))
    os.environ.pop("PG_RENDER_CHROME_CANARY", None)
    os.environ.pop("PG_RENDER_CHROME_CANARY_FLOOR", None)


def test_canary_default_enforce_and_modes() -> None:
    print("3b) I-wire-013 (#1327): canary DEFAULTS to enforce; off|warn telemetry-only; invalid RAISES")
    # An above-DEFAULT-floor (0.05) chrome report: 1 chrome of 2 claim bullets => rate 0.5.
    above_floor_report = (
        "## Key Findings\n\n"
        f"- **Efficacy.** {_REAL_CLAIM}[1]\n"
        "- **Masthead.** Economic Perspectives Volume 33, Number 2 Pages 3-30 ISSN: 1234[2]\n"
    )
    # 1) env UNSET => mode == enforce (the I-wire-013 default flip), default floor applies.
    os.environ.pop("PG_RENDER_CHROME_CANARY", None)
    os.environ.pop("PG_RENDER_CHROME_CANARY_FLOOR", None)
    _check("env-unset mode == enforce", render_chrome_canary_mode() == "enforce", render_chrome_canary_mode())
    res_default = evaluate_render_chrome_canary(above_floor_report)
    # 2) above-floor chrome report => verdict fail BY DEFAULT (the caller's pre-existing I-wire-012 branch
    #    at run_honest_sweep_r3.py:13971 keys on verdict=='fail' to flip status -> report_redaction_failed
    #    + withhold release; verdict=='fail' here IS that downgrade signal, no env set).
    _check("default (unset) enforce trips above floor", res_default["verdict"] == "fail", str(res_default))
    _check("default floor is 0.05", res_default["floor"] == 0.05, str(res_default["floor"]))
    # 3) invalid mode => ValueError (fail-loud, mirrors render_chrome_canary_floor; not a silent fallback).
    os.environ["PG_RENDER_CHROME_CANARY"] = "telemetry"  # not in {off,warn,enforce}
    raised = False
    try:
        render_chrome_canary_mode()
    except ValueError:
        raised = True
    _check("invalid mode raises ValueError", raised)
    # 4) all three modes' verdict on the SAME above-floor report (off|warn never trip; only enforce does).
    os.environ["PG_RENDER_CHROME_CANARY"] = "off"
    _check("off => verdict pass (no enforce; caller suppresses telemetry)", evaluate_render_chrome_canary(above_floor_report)["verdict"] == "pass")
    os.environ["PG_RENDER_CHROME_CANARY"] = "warn"
    _check("warn => verdict pass (telemetry-only)", evaluate_render_chrome_canary(above_floor_report)["verdict"] == "pass")
    os.environ["PG_RENDER_CHROME_CANARY"] = "enforce"
    _check("enforce => verdict fail", evaluate_render_chrome_canary(above_floor_report)["verdict"] == "fail")
    os.environ.pop("PG_RENDER_CHROME_CANARY", None)


def _section(title: str, verified_text: str) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        verified_text=verified_text,
        dropped_due_to_failure=False,
        is_gap_stub=False,
        sentences_verified=1,
    )


def test_depth_emits_key_findings() -> None:
    print("4) depth emits >0 key_findings on a report that ships a Key-Findings block")
    sections = [
        _section("Efficacy", _REAL_CLAIM + "[1]"),
        _section(
            "Safety",
            "Nausea occurred in 12 percent of treated patients at week 24.[2] "
            "However, the discontinuation rate diverged across the two trials.[3]",
        ),
    ]
    kf_block = build_key_findings(sections)
    _check("key-findings block built", kf_block.startswith("## Key Findings"), kf_block[:60])
    depth = evaluate_analytical_depth(split_report_into_sections(kf_block))
    _check("analytical_depth key_findings > 0", depth["key_findings"] > 0, str(depth["key_findings"]))
    # synthesis pass: the depth layer surfaces a verbatim cross-source tension when present.
    os.environ["PG_SWEEP_DEPTH_LAYER"] = "1"
    layer = build_depth_layer(sections)
    os.environ.pop("PG_SWEEP_DEPTH_LAYER", None)
    _check("depth layer surfaces a Tension line", "**Tension**" in layer, layer[:120])


def test_year_noise_contradiction_suppressed() -> None:
    print("5) bare-year numeric-noise contradiction suppressed (default-OFF byte-identical)")
    claims = [
        ExtractedNumericClaim(
            evidence_id="a", subject="gdp", predicate="growth", value=2019.0,
            unit="", context_snippet="...", source_url="http://a.example",
        ),
        ExtractedNumericClaim(
            evidence_id="b", subject="gdp", predicate="growth", value=2023.0,
            unit="", context_snippet="...", source_url="http://b.example",
        ),
    ]
    _check("helper flags bare-year group", _group_is_year_noise(claims))
    _check(
        "helper does NOT flag a unit-bearing group",
        not _group_is_year_noise([
            ExtractedNumericClaim(
                evidence_id="c", subject="gdp", predicate="growth", value=3.2,
                unit="percent", context_snippet="...", source_url="http://c.example",
            ),
            claims[0],
        ]),
    )
    # OFF (default): the record is a possible_metric_mismatch (byte-identical behaviour).
    os.environ.pop("PG_CONTRADICTION_DROP_YEAR_NOISE", None)
    off = detect_contradictions(claims, rel_threshold=0.0001, abs_threshold=1.0, is_clinical=False)
    _check(
        "OFF: possible_metric_mismatch present",
        any("possible_metric_mismatch" in r.predicate for r in off),
        str([r.predicate for r in off]),
    )
    # ON: suppressed to not_comparable (year_noise), kept out of the headline contradiction count.
    os.environ["PG_CONTRADICTION_DROP_YEAR_NOISE"] = "1"
    on = detect_contradictions(claims, rel_threshold=0.0001, abs_threshold=1.0, is_clinical=False)
    os.environ.pop("PG_CONTRADICTION_DROP_YEAR_NOISE", None)
    _check(
        "ON: relabeled not_comparable year_noise",
        any(r.not_comparable and "year_noise" in r.incommensurable_reason for r in on),
        str([(r.predicate, r.not_comparable) for r in on]),
    )
    _check(
        "ON: no possible_metric_mismatch surfaced",
        not any("possible_metric_mismatch" in r.predicate for r in on),
    )


def main() -> int:
    test_shared_predicate_and_precision()
    test_corroborated_weighted_findings_composer()
    test_section_body_composer()
    test_key_findings_composer()
    test_canary_trips_and_passes()
    test_canary_default_enforce_and_modes()
    test_depth_emits_key_findings()
    test_year_noise_contradiction_suppressed()
    print()
    if _failures:
        print(f"RESULT: FAIL ({len(_failures)} check(s) failed)")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS (all I-wire-012 acceptance checks green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
