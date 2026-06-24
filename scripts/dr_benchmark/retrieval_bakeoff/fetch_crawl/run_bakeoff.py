"""I-ret-002 (#1294) layer 2 (fetch_crawl) — bake-off runner + scorer.

CANDIDATE ENGINES (exact pip / API ids, web-verified 2026-06-23):
  * crawl4ai (BASELINE)  — pip ``crawl4ai`` (>=0.6); Playwright-Chromium markdown extractor.
                           Wired in prod via ``AccessBypass._try_crawl4ai``.
  * zyte                 — pip ``zyte-api`` (``from zyte_api import ZyteAPI``); browserHtml
                           anti-bot solver. Needs ``ZYTE_API_KEY`` (no_key => registered-but-skipped,
                           NEVER faked). Wired in prod via ``AccessBypass._try_zyte``.
  * firecrawl            — pip ``firecrawl-py`` (``from firecrawl import FirecrawlApp``). Needs
                           ``FIRECRAWL_API_KEY`` (no_key => skipped). Hosted scrape API.
  * playwright           — pip ``playwright`` (``playwright install chromium``). Headless browser.
                           ``needs_gpu`` is FALSE for fetch, but it ``needs_browser`` (a Chromium
                           runtime) — gated behind a runtime check, honestly skipped if absent.

METRIC (per brief, §-1.1-compliant — REAL engine output vs LABELED ground truth):
  Per-URL recovery verdict {RECOVERED / WALLED / SOFT_STUB / FETCH_FAIL} scored vs the gold
  ``recovery_class`` (recovery-verdict accuracy + a RECOVERED-recall view), PLUS main-content
  reference-recall: the Jaccard / recall of the engine body's content-token SET against the gold
  ``reference_tokens`` SET. NEVER a length floor — a long junk page recalls ~0 of the gold tokens;
  a short faithful extract recalls high. The composite score is recovery-correctness gated by
  reference-recall on the RECOVERED rows (a believable verdict that recovers none of the gold body
  is not a real recovery).

HONEST SCOPE (LAW II): a missing-key engine is ``no_key`` (registered, listed, SKIPPED — its score
is ``null`` with ``status=no_key``, never a believable-low number). A missing browser runtime is
``needs_browser`` (skipped). The GATE-0 per-engine liveness canary (gate0.py) is what FAILS LOUD
on a keyless/stub engine; this runner records the honest status so a skipped engine is never ranked
above a real one.

WEIGHT-NOT-FILTER: this layer changes NO production drop. ``tier`` rides along as a surfaced weight.
Faithfulness engine untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from _polaris_root import ensure_on_syspath

_POLARIS_ROOT = ensure_on_syspath()

# Reuse the fixture loader + the recovery rubric + the content-token tokenizer (single source).
from build_fixture import (  # noqa: E402
    FETCH_FAIL,
    RECOVERED,
    RECOVERY_CLASSES,
    SOFT_STUB,
    WALLED,
    classify_recovery,
    content_tokens,
    load_fixture,
)

# ── Status vocabulary for an engine's run on a URL / overall ────────────────────────────
STATUS_SCORED = "scored"
STATUS_NO_KEY = "no_key"            # registered but missing API key — SKIPPED, never faked.
STATUS_NEEDS_BROWSER = "needs_browser"  # missing Chromium/Playwright runtime — SKIPPED.
STATUS_LOAD_FAIL = "load_fail"      # the engine package failed to import — SKIPPED, surfaced loud.

# Default fixture + results paths (this layer's directory only).
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_FIXTURE = os.path.join(_HERE, "fetch_crawl_refbody_fixture.jsonl")
_DEFAULT_RESULTS = os.path.join(_HERE, "fetch_crawl_bakeoff_results.json")

# Reference-recall floor below which a "RECOVERED" verdict is NOT counted as a true recovery (the
# body recovered too little of the gold main content to be the article). A *recall* threshold on a
# TOKEN-SET overlap, NOT a length floor: a faithful short extract clears it; a long junk page fails
# it. LAW VI env-overridable. This gates the recovery verdict; it never drops a candidate.
_ENV_REFRECALL_MIN = "PG_FETCH_REFRECALL_MIN"
_DEFAULT_REFRECALL_MIN = 0.30


def _refrecall_min() -> float:
    try:
        v = float(os.environ.get(_ENV_REFRECALL_MIN, _DEFAULT_REFRECALL_MIN) or _DEFAULT_REFRECALL_MIN)
    except (TypeError, ValueError):
        return _DEFAULT_REFRECALL_MIN
    return v if 0.0 <= v <= 1.0 else _DEFAULT_REFRECALL_MIN


# ── The scorer math (also imported by gate0.py + smoke_test.py) ─────────────────────────

def reference_recall(engine_body: str, gold_tokens: set[str]) -> float:
    """Recall of the gold reference-token SET by the engine body's content-token SET.

    = |gold ∩ engine| / |gold|. A pure SET overlap (the §-1.1 "real output vs labeled gold"),
    NOT a length comparison. Empty gold => 0.0 (cannot measure recall of nothing).
    """
    if not gold_tokens:
        return 0.0
    eng = set(content_tokens(engine_body or ""))
    if not eng:
        return 0.0
    hit = len(gold_tokens & eng)
    return hit / len(gold_tokens)


def score_url(
    engine_body: str,
    gold_recovery_class: str,
    gold_tokens: set[str],
    reference_trustworthy: bool | None = None,
) -> dict[str, Any]:
    """Score one engine fetch of one URL — RECOVER-AS-MUCH-AS-POSSIBLE framing.

    THE OBJECTIVE IS RECOVERY, NOT REPRODUCING THE INCUMBENT. The gold body is the incumbent
    (crawl4ai-first AccessBypass) fetch outcome, so a gold-WALLED / gold-SOFT_STUB / gold-FETCH_FAIL
    row is one the INCUMBENT FAILED on — there is NO trustworthy reference body for it. An engine
    that turns such a row into RECOVERED real content is a WIN (the crown-jewel discriminator: Zyte
    beating a paywall), NEVER scored wrong. Scoring "engine == incumbent gold" would reward
    reproducing the incumbent and PUNISH beating it — a §-1.3 inversion (penalizing a valid better
    source). So:

      * ``recovered``  : the engine returned RECOVERED real content (the per-URL recovery WIN).
      * ``wall_broken``: the engine RECOVERED a row the incumbent did NOT (gold != RECOVERED) — the
                         discriminator that the whole bake-off (and Zyte as a candidate) exists for.
      * ``reference_recall`` : main-content fidelity vs the gold body — MEANINGFUL ONLY where the
                         reference is trustworthy (gold == RECOVERED, the incumbent got full text).
                         On a non-trustworthy row the gold body is a shell, so recall vs it is
                         intentionally NOT used to judge the engine (set ``reference_meaningful``).

    ``reference_trustworthy`` defaults to (gold_recovery_class == RECOVERED) when not given.
    A predicted RECOVERED that, on a TRUSTWORTHY row, recovers too little of the trustworthy
    reference is downgraded to SOFT_STUB (it returned a long wrong-page, not the article). On a
    non-trustworthy row there is no trustworthy reference to fall below, so no downgrade applies.
    """
    if reference_trustworthy is None:
        reference_trustworthy = gold_recovery_class == RECOVERED
    predicted = classify_recovery(engine_body)
    recall = reference_recall(engine_body, gold_tokens)
    effective = predicted
    # Only a TRUSTWORTHY reference can fail a RECOVERED prediction down to SOFT_STUB (wrong-page
    # guard). Against a shell gold body, low recall is EXPECTED for a real article and must NOT
    # downgrade the engine (that was the inversion).
    if predicted == RECOVERED and reference_trustworthy and recall < _refrecall_min():
        effective = SOFT_STUB
    recovered = effective == RECOVERED
    wall_broken = recovered and (gold_recovery_class != RECOVERED)
    return {
        "predicted_recovery_class": predicted,
        "effective_recovery_class": effective,
        "reference_recall": round(recall, 4),
        "reference_meaningful": bool(reference_trustworthy),
        "recovered": bool(recovered),
        "wall_broken": bool(wall_broken),
        "gold_recovery_class": gold_recovery_class,
    }


def aggregate(per_url: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-URL scores into an engine's layer metric (recover-as-much-as-possible).

    Headline metrics (none rewards reproducing the incumbent; all reward MORE recovery):
      * ``recovery_rate``           — fraction of ALL URLs the engine returns RECOVERED content for.
                                      This is the bake-off objective: recover as much as possible.
      * ``wall_break_rate``         — of the incumbent-FAILED rows (gold != RECOVERED), the fraction
                                      the engine turns into RECOVERED. The crown-jewel discriminator.
      * ``recovered_refrecall_macro`` — main-content fidelity on the rows with a TRUSTWORTHY
                                      reference (gold == RECOVERED): did the engine recover the
                                      actual article body, not a wrong long page.

    ``score`` = recovery_rate blended with fidelity-where-measurable, so an engine that recovers
    many bodies AND keeps high main-content fidelity wins; an engine that returns long wrong pages
    (high recovery_rate, low fidelity) is penalized, and an engine that reproduces incumbent walls
    (low recovery_rate) loses. Beating a wall can only ever HELP a score, never hurt it.
    """
    if not per_url:
        return {
            "n": 0,
            "recovery_rate": 0.0,
            "wall_break_rate": 0.0,
            "n_incumbent_failed": 0,
            "recovered_refrecall_macro": 0.0,
            "score": 0.0,
            "verdict_distribution": {c: 0 for c in RECOVERY_CLASSES},
        }
    n = len(per_url)
    recovery_rate = sum(1 for r in per_url if r["recovered"]) / n

    incumbent_failed = [r for r in per_url if r["gold_recovery_class"] != RECOVERED]
    if incumbent_failed:
        wall_break_rate = sum(1 for r in incumbent_failed if r["wall_broken"]) / len(incumbent_failed)
    else:
        wall_break_rate = 0.0

    # Fidelity only where a trustworthy reference exists (gold RECOVERED rows).
    trustworthy = [r for r in per_url if r["reference_meaningful"]]
    if trustworthy:
        recovered_refrecall = sum(r["reference_recall"] for r in trustworthy) / len(trustworthy)
    else:
        recovered_refrecall = 0.0

    # Verdict distribution of the ENGINE's effective classes (audit surface, NOT a quality-by-count
    # proxy: it is the engine's own output-class breakdown, used to read the recovery profile).
    verdict_distribution: dict[str, int] = {c: 0 for c in RECOVERY_CLASSES}
    for r in per_url:
        e = r["effective_recovery_class"]
        if e in verdict_distribution:
            verdict_distribution[e] += 1

    # Composite: recovery_rate is the objective; fidelity gates it so a wrong-page flood cannot win.
    score = round(0.6 * recovery_rate + 0.4 * recovered_refrecall, 4)
    return {
        "n": n,
        "recovery_rate": round(recovery_rate, 4),
        "wall_break_rate": round(wall_break_rate, 4),
        "n_incumbent_failed": len(incumbent_failed),
        "recovered_refrecall_macro": round(recovered_refrecall, 4),
        "score": score,
        "verdict_distribution": verdict_distribution,
    }


# ── Engine registry ─────────────────────────────────────────────────────────────────────

@dataclass
class EngineSpec:
    """An engine candidate: how to identify it, gate it, and (if live) fetch with it."""

    name: str
    pip_id: str
    import_name: str
    is_baseline: bool = False
    needs_key_env: str | None = None        # e.g. ZYTE_API_KEY / FIRECRAWL_API_KEY
    needs_browser: bool = False             # requires a Chromium runtime
    # fetch(url) -> body str; set at availability time. Returns "" on a genuine FETCH_FAIL.
    fetch: Callable[[str], str] | None = field(default=None, repr=False)


# Exact, web-verified ids. crawl4ai is the BASELINE (prod default free cascade).
def engine_specs() -> list[EngineSpec]:
    return [
        EngineSpec(name="crawl4ai", pip_id="crawl4ai>=0.6.0", import_name="crawl4ai",
                   is_baseline=True, needs_browser=True),
        EngineSpec(name="zyte", pip_id="zyte-api>=0.7.0", import_name="zyte_api",
                   needs_key_env="ZYTE_API_KEY"),
        EngineSpec(name="firecrawl", pip_id="firecrawl-py>=2.0.0", import_name="firecrawl",
                   needs_key_env="FIRECRAWL_API_KEY"),
        EngineSpec(name="playwright", pip_id="playwright>=1.45.0", import_name="playwright",
                   needs_browser=True),
    ]


def _module_importable(import_name: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def engine_availability(spec: EngineSpec) -> str:
    """Honest availability status for an engine WITHOUT running it (LAW II).

    Order: missing key (no_key) > package not importable (load_fail) > browser engine with no
    browser runtime (needs_browser) > scored (runnable). A no_key / load_fail / needs_browser engine
    is SKIPPED and recorded as such — never faked, never a believable-low score.
    """
    if spec.needs_key_env and not os.environ.get(spec.needs_key_env):
        return STATUS_NO_KEY
    if not _module_importable(spec.import_name):
        return STATUS_LOAD_FAIL
    if spec.needs_browser and not _chromium_runtime_present():
        return STATUS_NEEDS_BROWSER
    return STATUS_SCORED


def _chromium_runtime_present() -> bool:
    """True iff a Playwright/crawl4ai Chromium runtime is installed (best-effort, no launch)."""
    try:
        import importlib.util

        if importlib.util.find_spec("playwright") is None:
            return False
        # The browser binaries live under ms-playwright; existence of the install dir is the cheap
        # runtime check (we do NOT launch a browser here — that is the live run's job, not the gate's).
        from playwright._impl._driver import compute_driver_executable  # type: ignore

        driver = compute_driver_executable()
        return bool(driver)
    except Exception:  # noqa: BLE001 — any failure means "no usable browser runtime".
        return False


# ── Live fetch adapters (only invoked for a SCORED engine on the real VM run) ────────────
# These are intentionally thin and import lazily so the runner imports cleanly offline. They are
# NOT exercised by the offline smoke (which mocks them). They reuse the production fetch seams.

def _fetch_via_polaris_zyte(url: str) -> str:
    """Zyte browser fetch via the production AccessBypass seam (reuse, no fork)."""
    from src.polaris_graph.retrieval.live_retriever import _force_zyte_refetch

    return _force_zyte_refetch(url)


def _fetch_via_crawl4ai(url: str) -> str:
    """crawl4ai fetch via the production AccessBypass seam."""
    from src.tools.access_bypass import AccessBypass, polaris_asyncio_run

    bypass = AccessBypass()

    async def _run() -> Any:
        return await bypass._try_crawl4ai(url)

    res = polaris_asyncio_run(_run())
    return str(getattr(res, "content", "") or "") if getattr(res, "success", False) else ""


def _fetch_via_firecrawl(url: str) -> str:
    """Firecrawl hosted scrape (markdown). Lazy import; key already asserted by availability."""
    from firecrawl import FirecrawlApp  # type: ignore

    app = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])
    doc = app.scrape_url(url, params={"formats": ["markdown"]})
    if isinstance(doc, dict):
        return str(doc.get("markdown") or doc.get("content") or "")
    return str(getattr(doc, "markdown", "") or "")


def _fetch_via_playwright(url: str) -> str:
    """Raw Playwright headless fetch (page text). Lazy import; browser asserted by availability."""
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            return page.inner_text("body")
        finally:
            browser.close()


_FETCH_ADAPTERS: dict[str, Callable[[str], str]] = {
    "crawl4ai": _fetch_via_crawl4ai,
    "zyte": _fetch_via_polaris_zyte,
    "firecrawl": _fetch_via_firecrawl,
    "playwright": _fetch_via_playwright,
}


# ── Run loop ────────────────────────────────────────────────────────────────────────────

def run_engine(
    spec: EngineSpec,
    fixture: list[dict[str, Any]],
    fetch_override: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Run one engine across the fixture. Honest: a non-scored engine is recorded SKIPPED.

    ``fetch_override`` lets the smoke test inject a mocked fetch (so no network). For the real run,
    the adapter from ``_FETCH_ADAPTERS`` is used.
    """
    status = STATUS_SCORED if fetch_override is not None else engine_availability(spec)
    if status != STATUS_SCORED:
        return {
            "engine": spec.name,
            "pip_id": spec.pip_id,
            "is_baseline": spec.is_baseline,
            "status": status,
            "score": None,            # never a believable-low number for a skipped engine
            "metric": None,
            "note": _skip_note(spec, status),
        }

    fetch = fetch_override or _FETCH_ADAPTERS[spec.name]
    per_url: list[dict[str, Any]] = []
    for row in fixture:
        url = row["url"]
        gold_class = row["recovery_class"]
        gold_tokens = set(row.get("reference_tokens") or [])
        t0 = time.time()
        try:
            body = fetch(url)
        except Exception as exc:  # noqa: BLE001 — a fetch error is a FETCH_FAIL for THIS url, never aborts.
            body = ""
            err = f"{type(exc).__name__}: {exc}"
        else:
            err = ""
        # A trustworthy reference body exists only where the INCUMBENT got full text (gold RECOVERED).
        reference_trustworthy = gold_class == RECOVERED
        scored = score_url(body, gold_class, gold_tokens, reference_trustworthy=reference_trustworthy)
        scored.update({"url": url, "source_type": row.get("source_type"),
                       "tier": row.get("tier"), "elapsed_s": round(time.time() - t0, 3),
                       "fetch_error": err})
        per_url.append(scored)

    metric = aggregate(per_url)
    return {
        "engine": spec.name,
        "pip_id": spec.pip_id,
        "is_baseline": spec.is_baseline,
        "status": STATUS_SCORED,
        "score": metric["score"],
        "metric": metric,
        "per_url": per_url,
    }


def _skip_note(spec: EngineSpec, status: str) -> str:
    if status == STATUS_NO_KEY:
        return (f"SKIPPED: {spec.needs_key_env} is unset — engine registered but not run (no faked "
                f"score). Set the key on the VM to score it.")
    if status == STATUS_LOAD_FAIL:
        return (f"SKIPPED: package {spec.pip_id!r} (import {spec.import_name!r}) is not importable — "
                f"install it on the VM to score it.")
    if status == STATUS_NEEDS_BROWSER:
        return (f"SKIPPED: a Chromium runtime is absent — run `playwright install chromium` on the "
                f"VM to score this browser engine.")
    return "SKIPPED."


def rank_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank SCORED engines by score desc; skipped engines listed after (score None never ranks high)."""
    scored = [r for r in results if r["status"] == STATUS_SCORED and r["score"] is not None]
    skipped = [r for r in results if not (r["status"] == STATUS_SCORED and r["score"] is not None)]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored + skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fetch_crawl bake-off and write ranked results.")
    parser.add_argument("--fixture", default=_DEFAULT_FIXTURE, help="labeled fixture JSONL")
    parser.add_argument("--out", default=_DEFAULT_RESULTS, help="ranked results JSON output")
    args = parser.parse_args(argv)

    fixture = load_fixture(args.fixture)
    results = [run_engine(spec, fixture) for spec in engine_specs()]
    ranked = rank_results(results)

    payload = {
        "layer": "fetch_crawl",
        "issue": "I-ret-002 (#1294)",
        "fixture": args.fixture,
        "fixture_n": len(fixture),
        "refrecall_min": _refrecall_min(),
        "ranked": [
            {k: v for k, v in r.items() if k != "per_url"} for r in ranked
        ],
        "detail": {r["engine"]: r.get("per_url") for r in ranked if r.get("per_url")},
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    print(f"[run_bakeoff] fixture_n={len(fixture)} -> {args.out}")
    for r in ranked:
        print(f"  {r['engine']:<12} status={r['status']:<14} score={r['score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
