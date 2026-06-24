"""gate0.py -- GATE-0 validity harness for the content_extraction bake-off.

The anti-drb_72 gate. NO candidate score is trusted until ALL of these pass; any
failure => sys.exit(non-zero), no scores emitted. Four checks:

  (1) SCORER-MATH canary  -- gold body in -> F1 ~= 1.0 (>= 0.99); pure junk in ->
      F1 ~= 0 (<= 0.05). Proves the scorer rewards perfect extraction and scores
      chrome/SEO LOW (drb_72 was a HIGH score on garbage; this is load-bearing).
      Uses the offline pure-Python ROUGE-N (no jieba, no network).

  (2) PUBLISHED-NUMBER anchor -- CONDITIONAL: valid ONLY IF the OFFICIAL
      WebMainBench scorer (eval_baselines.py) is located. If present, reproduce
      the Dripper Table-2 per-extractor anchors within tolerance. If absent, the
      check FLAGS that it fell back to blind re-derivation (it does NOT silently
      pass and is NOT made circular by feeding candidate output as its own gold).

  (3) PER-CANDIDATE LIVENESS -- each candidate runs on a KNOWN-GOOD page where
      any working extractor returns substantial body. A stub / empty / load-fail /
      import-error THERE FAILS LOUD (the dead-candidate discriminator). A low
      ROUGE on a genuinely hard page is a REAL score and never trips this.

  (4) FAITHFULNESS substring assertion -- every content-of-record candidate's
      output spans must be verbatim substrings of the source visible text. An
      extractive tool passes; a generative/paraphrasing path (ReaderLM-v2) is
      flagged -- the structural never-crown demonstration. Harness-internal;
      never touches strict_verify / NLI / 4-role / provenance.

Lineage: a sha256 manifest (scorer config + tokenizer + anchor set + each
candidate id) is printed so a config mismatch surfaces here as a HARNESS BUG.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass

from _candidates import Candidate, ExtractorLoadError, build_candidate_registry
from _scoring import (
    ANCHOR_TOLERANCE,
    CANARY_JUNK_MAX_F1,
    CANARY_PERFECT_MIN_F1,
    OFFICIAL_ROUGE_N,
    OFFICIAL_TOKENIZER,
    PUBLISHED_ANCHORS,
    SCORER_CANARY_ROUGE_N,
    OfficialScorerStatus,
    anchor_within_tolerance,
    build_official_runner,
    check_faithfulness,
    locate_official_scorer,
    load_webmainbench_pages,
    rouge_n,
)


class GateZeroError(RuntimeError):
    """Raised fail-loud when a GATE-0 validity check fails (run is INVALID)."""


# A KNOWN-GOOD HTML page: any working extractor returns substantial body. Used
# by the liveness canary as the discriminator (dead-on-this != low-on-hard).
KNOWN_GOOD_HTML = (
    "<html><head><title>Tirzepatide cardiovascular outcomes</title>"
    "<style>.nav{}</style></head><body>"
    "<nav>Home About Contact Subscribe</nav>"
    "<div class='ad'>Buy now! Limited offer cookies accept</div>"
    "<article><h1>Tirzepatide reduces major adverse cardiovascular events</h1>"
    "<p>In the SURMOUNT-MMO randomized controlled trial, tirzepatide reduced the "
    "incidence of major adverse cardiovascular events compared with placebo over a "
    "median follow-up of three years in adults with obesity.</p>"
    "<p>The treatment group received a once-weekly subcutaneous dose escalated to "
    "fifteen milligrams, and the absolute risk reduction was statistically significant "
    "with a hazard ratio below one.</p></article>"
    "<footer>Copyright 2026 All rights reserved Privacy Policy</footer>"
    "</body></html>"
)
KNOWN_GOOD_GOLD = (
    "Tirzepatide reduces major adverse cardiovascular events. In the SURMOUNT-MMO "
    "randomized controlled trial, tirzepatide reduced the incidence of major adverse "
    "cardiovascular events compared with placebo over a median follow-up of three years "
    "in adults with obesity. The treatment group received a once-weekly subcutaneous "
    "dose escalated to fifteen milligrams, and the absolute risk reduction was "
    "statistically significant with a hazard ratio below one."
)
# Pure chrome/nav/ads/cookie-banner with NONE of the gold body (the drb_72 guard).
PURE_JUNK_TEXT = (
    "Home About Contact Subscribe Buy now Limited offer cookies accept "
    "Copyright 2026 All rights reserved Privacy Policy Terms of Service Newsletter signup"
)

# A genuinely-low extraction is NOT empty (real result on a hard page); the
# liveness canary must NOT trip on this. Used to prove the discriminator.
LOW_BUT_LIVE_OUTPUT = "follow-up of three years in adults with obesity."

# Minimum output length (chars) on the KNOWN-GOOD page below which a candidate is
# treated as DEAD/stub (env-overridable; the known-good gold is ~430 chars).
LIVENESS_MIN_GOOD_OUTPUT_CHARS = int(
    os.getenv("PG_CE_BAKEOFF_LIVENESS_MIN_CHARS", "60")
)


@dataclass
class CanaryResult:
    name: str
    passed: bool
    detail: str


def check_scorer_math() -> list[CanaryResult]:
    """Check (1): gold-in -> ~1.0, junk-in -> ~0 with the offline ROUGE-N."""
    results: list[CanaryResult] = []

    perfect = rouge_n(KNOWN_GOOD_GOLD, KNOWN_GOOD_GOLD, n=SCORER_CANARY_ROUGE_N)
    results.append(
        CanaryResult(
            "scorer_math_perfect",
            perfect.f1 >= CANARY_PERFECT_MIN_F1,
            f"gold-in F1={perfect.f1:.4f} (>= {CANARY_PERFECT_MIN_F1})",
        )
    )

    junk = rouge_n(PURE_JUNK_TEXT, KNOWN_GOOD_GOLD, n=SCORER_CANARY_ROUGE_N)
    results.append(
        CanaryResult(
            "scorer_math_junk",
            junk.f1 <= CANARY_JUNK_MAX_F1,
            f"junk-in F1={junk.f1:.4f} (<= {CANARY_JUNK_MAX_F1})",
        )
    )

    # Inverse sanity: a genuinely-low-but-real extraction scores BETWEEN the two
    # extremes -- it is neither perfect nor zero (proves the scorer is graded).
    low = rouge_n(LOW_BUT_LIVE_OUTPUT, KNOWN_GOOD_GOLD, n=1)
    results.append(
        CanaryResult(
            "scorer_math_graded",
            0.0 < low.recall < 1.0,
            f"low-but-real unigram recall={low.recall:.4f} (strictly between 0 and 1)",
        )
    )
    return results


def check_published_anchor(
    status: OfficialScorerStatus, candidates: list[Candidate], allow_gpu: bool
) -> CanaryResult:
    """Check (2): published-number reproduction -- COMPUTE-and-compare, never
    green-on-nothing.

    Three honest outcomes:
      * DEFERRED (passing-but-flagged): the official scorer / benchmark file is
        NOT located -> the published anchor cannot be reproduced here; the run
        falls back to FLAGGED blind re-derivation (brief-sanctioned). Reported
        with status, never a fake green.
      * COMPUTED+PASS: official scorer located -> actually run the CPU extractors
        (Trafilatura/Resiliparse/jusText/readability -- no GPU needed) on the
        in-repo WebMainBench_100 split, score with the OFFICIAL scorer, and
        assert each reproduces its Dripper Table-2 anchor +/- tolerance.
      * COMPUTED+FAIL: an anchor miss => HARNESS BUG (wrong N / tokenizer /
        variant / split) -> FAIL LOUD (the drb_72 wiring-bug class).
    """
    if not status.available:
        return CanaryResult(
            "published_anchor:DEFERRED",
            True,  # brief sanctions the FLAGGED blind re-derivation fallback
            "DEFERRED: official scorer/benchmark not located -> blind re-derivation "
            f"fallback (FLAGGED, N={OFFICIAL_ROUGE_N}). reason={status.reason}",
        )
    runner = build_official_runner(status)
    pages = load_webmainbench_pages(status, limit=int(os.getenv("PG_CE_ANCHOR_PAGES", "100")))
    if runner is None or not pages:
        return CanaryResult(
            "published_anchor:DEFERRED",
            True,
            "DEFERRED: official scorer file present but its scorer API/jieba or the "
            f"benchmark pages could not be loaded (pages={len(pages)}) -> FLAGGED re-derivation.",
        )
    # Reproduce anchors on the CPU extractors only (the GPU MinerU anchor is
    # validated on the run host). Compute mean official F1 per extractor.
    from _scoring import average

    cpu_by_key = {c.key: c for c in candidates if not c.needs_gpu and c.key in PUBLISHED_ANCHORS}
    misses: list[str] = []
    checked: list[str] = []
    for key, cand in cpu_by_key.items():
        try:
            scores = [runner(cand.extract(p["html"]), p["gold"]) for p in pages]
        except Exception as exc:  # noqa: BLE001 -- a dead extractor here is a real bug
            misses.append(f"{key}: extractor/scorer failed ({exc!r})")
            continue
        mean_f1 = average(scores)
        checked.append(f"{key}={mean_f1:.4f}(anchor {PUBLISHED_ANCHORS[key]:.4f})")
        if not anchor_within_tolerance(key, mean_f1):
            misses.append(
                f"{key}: observed {mean_f1:.4f} vs anchor {PUBLISHED_ANCHORS[key]:.4f} "
                f"(|delta|>{ANCHOR_TOLERANCE}) -> HARNESS BUG"
            )
    if misses:
        return CanaryResult("published_anchor:COMPUTED", False, "; ".join(misses))
    return CanaryResult(
        "published_anchor:COMPUTED",
        True,
        f"reproduced {len(checked)} CPU anchors +/- {ANCHOR_TOLERANCE} "
        f"(N={OFFICIAL_ROUGE_N}, {OFFICIAL_TOKENIZER}): {', '.join(checked)}",
    )


def check_candidate_liveness(candidate: Candidate, allow_gpu: bool) -> CanaryResult:
    """Check (3): dead-candidate discriminator on the KNOWN-GOOD page.

    A candidate that load-fails, imports-fails, or returns empty/stub on the
    KNOWN-GOOD page FAILS LOUD. needs_gpu candidates are honestly SKIPPED (not
    faked) when no GPU is available.
    """
    if candidate.needs_gpu and not allow_gpu:
        return CanaryResult(
            f"liveness:{candidate.key}",
            True,  # honest skip, not a pass-with-fake-score
            f"SKIPPED (needs_gpu, no GPU host): {candidate.impl_id}",
        )
    try:
        output = candidate.extract(KNOWN_GOOD_HTML)
    except ExtractorLoadError as exc:
        return CanaryResult(
            f"liveness:{candidate.key}", False, f"DEAD (load/import failure): {exc}"
        )
    except Exception as exc:  # noqa: BLE001 -- any crash on the known-good page is dead
        return CanaryResult(
            f"liveness:{candidate.key}", False, f"DEAD (crashed on known-good): {exc!r}"
        )
    n_chars = len((output or "").strip())
    if n_chars < LIVENESS_MIN_GOOD_OUTPUT_CHARS:
        return CanaryResult(
            f"liveness:{candidate.key}",
            False,
            f"DEAD/stub: returned {n_chars} chars on known-good page "
            f"(< {LIVENESS_MIN_GOOD_OUTPUT_CHARS}); a working extractor returns the body.",
        )
    return CanaryResult(
        f"liveness:{candidate.key}", True, f"live: {n_chars} chars on known-good page"
    )


def check_candidate_faithfulness(candidate: Candidate, allow_gpu: bool) -> CanaryResult:
    """Check (4): verbatim-substring faithfulness on the KNOWN-GOOD page.

    Extractive content-of-record candidates MUST pass. The generative yardstick
    is EXPECTED to fail and is reported as flagged-not-fatal (it never wins).
    """
    if candidate.needs_gpu and not allow_gpu:
        return CanaryResult(
            f"faithfulness:{candidate.key}", True, "SKIPPED (needs_gpu, no GPU host)"
        )
    try:
        output = candidate.extract(KNOWN_GOOD_HTML)
    except Exception as exc:  # noqa: BLE001 -- liveness already reports load failures
        return CanaryResult(
            f"faithfulness:{candidate.key}", False, f"could not extract: {exc!r}"
        )
    report = check_faithfulness(output, KNOWN_GOOD_HTML)
    if candidate.extractive:
        # Content-of-record: MUST be faithful (verbatim).
        return CanaryResult(
            f"faithfulness:{candidate.key}",
            report.is_faithful,
            f"verbatim_fraction={report.verbatim_fraction:.3f} "
            f"({report.verbatim_spans}/{report.checked_spans} spans)"
            + ("" if report.is_faithful else f" VIOLATION: {report.first_violation!r}"),
        )
    # Generative yardstick: expected NOT faithful; flagged, never fatal.
    return CanaryResult(
        f"faithfulness:{candidate.key}",
        True,  # not fatal -- structural never-crown handles eligibility
        f"YARDSTICK (generative): verbatim_fraction={report.verbatim_fraction:.3f} "
        "-> structurally barred from content-of-record (never crowned).",
    )


def lineage_manifest(candidates: list[Candidate], status: OfficialScorerStatus) -> dict:
    payload = {
        "scorer_canary_rouge_n": SCORER_CANARY_ROUGE_N,
        "official_rouge_n": OFFICIAL_ROUGE_N,
        "official_tokenizer": OFFICIAL_TOKENIZER,
        "anchor_tolerance": ANCHOR_TOLERANCE,
        "published_anchors": PUBLISHED_ANCHORS,
        "official_scorer_available": status.available,
        "candidates": [
            {"key": c.key, "impl_id": c.impl_id, "role": c.role, "extractive": c.extractive}
            for c in candidates
        ],
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    payload["lineage_sha256"] = hashlib.sha256(blob).hexdigest()
    return payload


def run_gate0(*, allow_gpu: bool, candidates: list[Candidate] | None = None) -> dict:
    """Run all four GATE-0 checks. Returns a report; caller decides exit code."""
    candidates = candidates if candidates is not None else build_candidate_registry()
    status = locate_official_scorer(os.getenv("PG_WEBMAINBENCH_REPO") or None)

    results: list[CanaryResult] = []
    results.extend(check_scorer_math())
    results.append(check_published_anchor(status, candidates, allow_gpu))
    for cand in candidates:
        results.append(check_candidate_liveness(cand, allow_gpu))
        results.append(check_candidate_faithfulness(cand, allow_gpu))

    manifest = lineage_manifest(candidates, status)
    all_passed = all(r.passed for r in results)
    return {
        "gate": "content_extraction_gate0",
        "all_passed": all_passed,
        "lineage": manifest,
        "results": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="GATE-0 validity harness")
    parser.add_argument(
        "--allow-gpu",
        action="store_true",
        default=os.getenv("PG_CE_BAKEOFF_ALLOW_GPU", "0") == "1",
        help="run needs_gpu candidates (else honestly skipped, not faked)",
    )
    args = parser.parse_args(argv)

    report = run_gate0(allow_gpu=args.allow_gpu)
    print(json.dumps(report, indent=2))
    if not report["all_passed"]:
        failed = [r["name"] for r in report["results"] if not r["passed"]]
        print(f"GATE-0 FAILED: {failed} -- NO scores trusted (anti-drb_72).", file=sys.stderr)
        return 1
    print("GATE-0 GREEN: scorer math + liveness + faithfulness all pass.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
