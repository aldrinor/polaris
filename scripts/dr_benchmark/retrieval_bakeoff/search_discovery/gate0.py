"""search_discovery bake-off — GATE-0 validity harness (anti-drb_72).

I-ret-002 (#1294), layer 1 of 7. NO candidate score is trusted until BOTH families of canary
pass: (A) the SCORER-MATH canaries (known input -> known score) and (B) the per-candidate
LIVENESS canary (a stub / empty / load-fail / keyless candidate FAILS LOUD with a non-zero
exit, never a believable-low score). FAIL LOUD: any canary failure raises GateZeroError and the
CLI exits non-zero.

SCORER-MATH canaries (the brief's four + the two the metric was CORRECTED to require):
  1. POSITIVE — a ranked list containing a gold source -> recall 1.000 exactly.
  2. NEGATIVE — a junk-only ranked list (unrelated domains) -> recall 0.000 exactly.
  3. NORMALIZATION — the gold DOI as a publisher-mirror / ?utm= / trailing-slash variant still
     matches (recall 1.0): the normalizer is not silently MISSING real hits.
  4. LINEAGE — reuse gate0_lineage idx binding: launched == packed == answered == canonical, so
     recall is scored against the RIGHT task's findings.
  5. SET-OR PARTIAL-HIT (corrected-metric §-1.3) — gold(f) is a SET; a candidate that returns
     ONLY ONE member of a multi-member set STILL scores recall 1.0. An off-by-one requiring all
     members (or the "primary") silently breaks basket faithfulness — this guards it.
  6. SAME-DOMAIN-DIFFERENT-PAGE NEGATIVE (corrected-metric, the headline guard) — a DIFFERENT
     page on a gold page_report source's registered domain scores 0 (registered-domain alone is
     necessary-but-not-sufficient; "any fda.gov page counting" is the failure this kills).

LIVENESS canary (the highest-priority anti-drb_72 check, the brief's #1):
  - Each candidate DECLARED runnable must return a non-empty AND NON-CONSTANT ranked list across
    TWO distinct easy known queries (a stub returning a fixed believable list is caught by the
    non-constant check), with the obvious-correct URL present.
  - A candidate DECLARED no_key is SKIPPED + recorded (never run, never failed).
  - A candidate DECLARED runnable that returns keyless/stub/empty FAILS LOUD (non-zero exit).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, Callable

from scripts.dr_benchmark.gate0_lineage import (
    GateZeroLineageError,
    assert_no_split_brain,
    canonical_question_for_slug,
)
from scripts.dr_benchmark.retrieval_bakeoff.search_discovery.build_fixture import (
    GoldSource,
    finding_recall,
)


class GateZeroError(RuntimeError):
    """Raised fail-loud when a GATE-0 canary fails. A run that raises this is INVALID."""


# ---------------------------------------------------------------------------
# (A) SCORER-MATH canaries.
# ---------------------------------------------------------------------------

# A synthetic multi-member DOI gold SET (two valid alternate sources for ONE study).
_GOLD_DOI_PRIMARY = GoldSource(
    kind="doi_pmid", doi="10.1234/example.2025.001",
    canonical_url="https://doi.org/10.1234/example.2025.001", title="Example study",
)
_GOLD_DOI_MIRROR = GoldSource(
    kind="doi_pmid", doi="10.5555/mirror.2025.002",
    canonical_url="https://doi.org/10.5555/mirror.2025.002", title="Example study (mirror)",
)
# A gov page_report gold source: domain + the SPECIFIC report path.
_GOLD_PAGE = GoldSource(
    kind="page_report", canonical_url="https://www.fda.gov/media/12345/download",
    domain="fda.gov", path_slug="media/12345/download", title="FDA report 12345",
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise GateZeroError(msg)


def canary_positive() -> None:
    """A ranked list containing a gold source -> recall 1.0 exactly."""
    ranked = [
        "https://example.com/unrelated",
        "https://doi.org/10.1234/example.2025.001",  # the gold DOI
    ]
    r = finding_recall(ranked, [_GOLD_DOI_PRIMARY])
    _assert(r == 1, f"POSITIVE canary: expected recall=1, got {r}")


def canary_negative() -> None:
    """A junk-only ranked list (unrelated domains) -> recall 0.0 exactly (no fake credit)."""
    ranked = [
        "https://news.example.org/story",
        "https://blog.spam-seo.net/post/42",
        "https://random.io/page",
    ]
    r = finding_recall(ranked, [_GOLD_DOI_PRIMARY])
    _assert(r == 0, f"NEGATIVE canary: expected recall=0, got {r}")


def canary_normalization() -> None:
    """The gold DOI as a publisher-mirror / ?utm= / trailing-slash variant still matches."""
    variants = [
        "https://onlinelibrary.publisher.com/doi/10.1234/example.2025.001?utm_source=alert",
        "http://dx.doi.org/10.1234/example.2025.001/",
        "https://www.doi.org/10.1234/example.2025.001#abstract",
    ]
    for v in variants:
        r = finding_recall([v], [_GOLD_DOI_PRIMARY])
        _assert(r == 1, f"NORMALIZATION canary: variant {v!r} expected recall=1, got {r}")


def canary_lineage(
    slug: str = "drb_72_ai_labor", tasks_path: str | None = None
) -> None:
    """Reuse gate0_lineage idx binding: launched == packed == answered == canonical."""
    kwargs: dict[str, Any] = {}
    if tasks_path:
        kwargs["tasks_path"] = tasks_path
    canonical = canonical_question_for_slug(slug, **kwargs)
    # The split-brain guard must PASS when packed==answered==canonical, and FAIL when they drift.
    assert_no_split_brain(slug, canonical, canonical, **kwargs)
    drifted = False
    try:
        assert_no_split_brain(slug, canonical, canonical + " (drifted)", **kwargs)
    except GateZeroLineageError:
        drifted = True
    _assert(drifted, "LINEAGE canary: split-brain guard did NOT fail on a drifted answer")


def canary_set_or_partial_hit() -> None:
    """gold(f) is a SET; returning ONLY ONE member still scores recall 1.0 (basket faithfulness).

    The mirror DOI alone (not the primary) must satisfy the finding — proves the scorer is a
    SET-OR membership test, not an all-members / primary-only test.
    """
    gold_set = [_GOLD_DOI_PRIMARY, _GOLD_DOI_MIRROR]
    only_mirror = ["https://doi.org/10.5555/mirror.2025.002"]
    r = finding_recall(only_mirror, gold_set)
    _assert(r == 1, f"SET-OR canary: single-member hit expected recall=1, got {r}")
    # And a list with NEITHER member scores 0.
    r0 = finding_recall(["https://doi.org/10.9999/other.2025.003"], gold_set)
    _assert(r0 == 0, f"SET-OR canary: non-member expected recall=0, got {r0}")


def canary_same_domain_different_page_negative() -> None:
    """A DIFFERENT page on a gold page_report domain scores 0 (broad-domain-false-positive guard).

    The headline §-1.3 worry: "any fda.gov page counting". The correct report path matches (1.0);
    a different fda.gov page must NOT match (0.0).
    """
    correct = ["https://www.fda.gov/media/12345/download"]
    _assert(
        finding_recall(correct, [_GOLD_PAGE]) == 1,
        "SAME-DOMAIN canary: the correct report page should match (recall=1)",
    )
    different_page = [
        "https://www.fda.gov/drugs/drug-approvals-and-databases/index",
        "https://www.fda.gov/news-events/press-announcements/some-unrelated-release",
    ]
    r = finding_recall(different_page, [_GOLD_PAGE])
    _assert(
        r == 0,
        f"SAME-DOMAIN canary: a DIFFERENT fda.gov page must NOT match (expected 0, got {r}) — "
        f"registered-domain alone is necessary but NOT sufficient",
    )


def run_scorer_math_canaries(tasks_path: str | None = None) -> list[str]:
    """Run all six scorer-math canaries; return the names that passed. FAIL LOUD on any failure."""
    passed: list[str] = []
    for name, fn in (
        ("positive", canary_positive),
        ("negative", canary_negative),
        ("normalization", canary_normalization),
        ("set_or_partial_hit", canary_set_or_partial_hit),
        ("same_domain_different_page_negative", canary_same_domain_different_page_negative),
    ):
        fn()
        passed.append(name)
    # Lineage needs the gold file; run it last and let it fail loud if the file is absent.
    canary_lineage(tasks_path=tasks_path)
    passed.append("lineage")
    return passed


# ---------------------------------------------------------------------------
# (B) per-candidate LIVENESS canary.
# ---------------------------------------------------------------------------

# Two distinct EASY known queries with an obvious-correct URL expected for each. The liveness
# check asserts non-empty + NON-CONSTANT across the two + the obvious URL present.
LIVENESS_PROBES: tuple[dict[str, str], ...] = (
    {"query": "World Health Organization official website",
     "expect_substr": "who.int"},
    {"query": "National Institutes of Health official website",
     "expect_substr": "nih.gov"},
)


@dataclass
class LivenessResult:
    name: str
    status: str  # "live" | "skipped_no_key" | "FAILED"
    detail: str


def _ranked_urls(provider: Any, query: str) -> list[str]:
    rows = provider.search(query) or []
    return [(r.get("url") or "").strip() for r in rows if (r.get("url") or "").strip()]


def liveness_check_one(provider: Any) -> LivenessResult:
    """Run the liveness canary for a single provider.

    no_key -> skipped+recorded. runnable -> must return non-empty + non-constant across two
    probes + expected substring present; otherwise FAIL LOUD (status FAILED).
    """
    runnable = getattr(provider, "runnable", "yes")
    name = getattr(provider, "name", provider.__class__.__name__)

    if runnable == "no_key":
        return LivenessResult(name, "skipped_no_key", "registered, no key held — skipped (not faked)")

    results: list[list[str]] = []
    for probe in LIVENESS_PROBES:
        try:
            urls = _ranked_urls(provider, probe["query"])
        except Exception as exc:  # noqa: BLE001 — a load/keyless failure is a LOUD gate failure
            return LivenessResult(name, "FAILED", f"search raised: {exc}")
        if not urls:
            return LivenessResult(
                name, "FAILED",
                f"query {probe['query']!r} returned an EMPTY ranked list (stub/keyless)",
            )
        results.append(urls)

    # NON-CONSTANT across the two probes: a stub returning one fixed list is caught here.
    if results[0] == results[1]:
        return LivenessResult(
            name, "FAILED",
            "ranked list is CONSTANT across two distinct queries (stub/canned response)",
        )

    # Obvious-correct URL present for at least one probe (relevance signal, not just liveness).
    any_expected = any(
        any(probe["expect_substr"] in u.lower() for u in urls)
        for probe, urls in zip(LIVENESS_PROBES, results)
    )
    if not any_expected:
        return LivenessResult(
            name, "FAILED",
            "no probe surfaced its obvious-correct URL "
            f"({[p['expect_substr'] for p in LIVENESS_PROBES]}) — not a real backend",
        )

    return LivenessResult(name, "live", f"{len(results[0])}/{len(results[1])} urls, non-constant, relevant")


def run_liveness_canaries(providers: list[Any]) -> list[LivenessResult]:
    """Run liveness for every provider. Raise GateZeroError if any DECLARED-runnable one FAILED."""
    results = [liveness_check_one(p) for p in providers]
    failed = [r for r in results if r.status == "FAILED"]
    if failed:
        lines = "\n".join(f"  - {r.name}: {r.detail}" for r in failed)
        raise GateZeroError(
            "GATE-0 LIVENESS FAILED for declared-runnable candidate(s) — "
            "a stub/empty/keyless candidate must FAIL LOUD, never score low:\n" + lines
        )
    return results


def run_gate0(
    providers: list[Any] | None = None,
    tasks_path: str | None = None,
) -> dict[str, Any]:
    """Run BOTH canary families. Returns a green report or raises GateZeroError (fail loud)."""
    scorer_passed = run_scorer_math_canaries(tasks_path=tasks_path)
    liveness = run_liveness_canaries(providers or [])
    return {
        "gate0": "GREEN",
        "scorer_math_canaries_passed": scorer_passed,
        "liveness": [
            {"name": r.name, "status": r.status, "detail": r.detail} for r in liveness
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="search_discovery GATE-0 validity harness")
    parser.add_argument("--tasks-path", default=None)
    parser.add_argument(
        "--scorer-only", action="store_true",
        help="run only the scorer-math canaries (no providers needed)",
    )
    args = parser.parse_args(argv)

    try:
        if args.scorer_only:
            passed = run_scorer_math_canaries(tasks_path=args.tasks_path)
            print(f"GATE-0 scorer-math GREEN: {passed}")
            return 0
        from scripts.dr_benchmark.retrieval_bakeoff.search_discovery.run_bakeoff import (
            default_providers,
        )

        report = run_gate0(default_providers(), tasks_path=args.tasks_path)
        print(report)
        return 0
    except (GateZeroError, GateZeroLineageError) as exc:
        print(f"GATE-0 FAILED (fail loud): {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
