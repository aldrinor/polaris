#!/usr/bin/env python3
"""I-beatboth-011 idx49 (#1289) — behavioral replay-harness for the fetch-shell
EVIDENCE-PATH leak (§-1.4 fail-loud).

THE DEFECT this proves the fix for: ``clean_fetch_body`` returns
``CleanedFetch(cleaned_text, shell_reason)``. ``shell_reason`` is set (non-None)
when the WHOLE cleaned body is a fetch SHELL (boilerplate / soft-404 / a wholly
chrome reference-listing page that cleans to empty). The FRAME-ENTITY path already
consumes this signal and routes a shell to its METADATA_ONLY gap branch. But the
two EVIDENCE-path consumers in ``live_retriever`` discarded ``shell_reason``
(``clean_fetch_body(content).cleaned_text``) and built a cited ``direct_quote`` /
evidence row from the junk anyway. On the drb_72 run this leaked junk (e.g. the
scirp.org reference-listing page below) into the cited evidence pool.

THE FIX consumes the EXISTING ``shell_reason`` signal at BOTH evidence-path sites
(``refetch_for_extraction_with_diagnostics`` ~L2078 and the ``run_live_retrieval``
per-URL row builder ~L4561) and routes a shell row to the EXISTING skip/gap branch
(NOT a cited evidence row). No new drop/cap/threshold; the existing 1200-char gate
is untouched; the faithfulness engine is untouched.

This is a BEHAVIORAL end-to-end harness (NOT a flag-set / unit-of-clean_fetch_body
check). It drives the REAL consumers and asserts on the EMITTED evidence:
  • Case A (EXCLUDED): a wholly-junk shell body is NOT emitted as a cited evidence
    row / direct_quote — it is routed to the existing skip/gap branch.
  • Case B (KEPT): a real article body IS emitted as a normal evidence row — the
    fix never drops a real source (§-1.3 removes only confirmed fetch-junk).

Both fixture bodies are ADAPTED from REAL bodies in the drb_72 evidence pool
(``outputs/audits/drb_72_2026_06_12/runA_final/evidence_pool.json``) — same source,
same shape, lightly trimmed/representative (not byte-verbatim):
  • JUNK  = a scirp.org reference-listing page (all markdown link-chrome) that
            ``clean_fetch_body`` cleans to empty → ``shell_reason='empty_after_clean'``.
            The stored scirp quote in that pool re-cleans to empty under the current
            chrome-stripper; this is the genuine fetch-junk the SITE-2 fix removes.
  • REAL  = the AEA ``jep.33.2.3`` automation/labor article body → ``shell_reason=None``.

SCOPE — what this fix does and does NOT close (honest, per §-1.1):
  • Closes the EMPTY-after-clean / boilerplate-dominated error-stub shell class at
    BOTH evidence-path sites (e.g. the scirp reference-listing page).
  • Does NOT close the longer Cloudflare/CAPTCHA INTERSTITIAL class named in the
    issue — the IMF elibrary "solve a puzzle" and BMJ "you have been blocked" bodies
    (~500-780 chars) fire neither ``clean_fetch_body.shell_reason`` NOR frame_fetcher's
    ``_is_fetch_shell`` and REMAIN cited. Catching that class needs a NEW phrase
    detector, which is a NEW drop rule (forbidden here by §-1.3 / the no-new-threshold
    constraint) → tracked as a separate follow-up, NOT this PR.
  • Site-1 note: for the empty-cleaning scirp fixture, site 1 ALREADY excluded it
    pre-fix via the ``thin_content`` length gate; the idx49 fix re-labels that
    exclusion ``fetch_shell`` (honest attribution). The genuine NEW exclusion is at
    site 2, whose per-URL row builder has no length gate before the append.

FAIL-LOUD: any assertion failure exits non-zero. PASS exits 0.

Run:  python scripts/iarch_beatboth011_idx49_fetchshell_evidence_harness.py
"""
from __future__ import annotations

import os
import sys

# Repo root on sys.path so ``src...`` imports resolve when run directly.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.tools.access_bypass import clean_fetch_body  # noqa: E402
from src.polaris_graph.retrieval import live_retriever as lr  # noqa: E402


# ── Fixtures ADAPTED from real drb_72 evidence-pool bodies (not byte-verbatim) ──
#
# JUNK: a scirp.org "reference list" page (its ABSTRACT tail trimmed for the
# fixture). Every line is markdown link-chrome (TITLE/AUTHORS/KEYWORDS/JOURNAL
# NAME all point at ``../journal/...`` slugs). ``strip_web_boilerplate`` strips
# the link-chrome and the whole unit cleans to empty → ``clean_fetch_body``
# returns ``shell_reason='empty_after_clean'``. On the RAW body it is NOT content-
# starved and NOT a landing page, so at SITE 2 (the per-URL row builder, which has
# no length gate before the append) NO prior gate excludes it — only the idx49 fix
# does. The stored scirp quote in the drb_72 pool re-cleans to empty the same way.
_JUNK_SHELL_BODY = (
    "TITLE: [ Technological Advances and the Changing Nature of Work: Deriving a "
    "Future Skills Set](../journal/paperinformation?paperid=95586) AUTHORS: "
    "[Yasmin Danuser](../journal/articles?searchcode=Yasmin+Danuser&searchfield="
    "authors&page=1), [Michael J. Kendzia](../journal/articles?searchcode="
    "Michael+J.+Kendzia&searchfield=authors&page=1) KEYWORDS: [Destruction Effect]"
    "(../journal/articles?searchcode=Destruction+Effect&searchfield=keyword&page=1), "
    "[Capitalization Effect](../journal/articles?searchcode=Capitalization+Effect&"
    "searchfield=keyword&page=1), [Soft Skills](../journal/articles?searchcode="
    "Soft+Skills&searchfield=keyword&page=1) JOURNAL NAME: [Advances in Applied "
    "Sociology](../journal/home?journalid=1002), [Vol.9 No.10](../journal/home?"
    "issueid=13047), October 10, 2019"
)

# REAL: representative prose from the AEA Journal of Economic Perspectives
# automation/labor article (jep.33.2.3) — its abstract head, lightly extended for
# the fixture so it reads as a full body. Long real prose; ``clean_fetch_body``
# leaves it intact with ``shell_reason=None``. This row MUST survive the fix as a
# cited evidence row (§-1.3: the fix never drops a real source).
_REAL_ARTICLE_BODY = (
    "We present a framework for understanding the effects of automation and other "
    "types of technological changes on labor demand, and use it to interpret "
    "changes in US employment over the recent past. At the center of our framework "
    "is the allocation of tasks to capital and labor. Automation, which allows "
    "capital to replace labor in tasks it was previously engaged in, shifts the "
    "task content of production against labor because of a displacement effect. "
    "The displacement effect can be offset by a countervailing reinstatement "
    "effect that creates new tasks in which labor has a comparative advantage. "
    "We argue that the recent stagnation of labor demand is explained by an "
    "acceleration of the displacement effect, a weaker reinstatement effect, and "
    "slower productivity growth than in previous decades. We document that the "
    "real wages of workers without a college degree fell over this period, while "
    "the task content of production shifted away from labor in manufacturing and "
    "several other sectors of the US economy across the enrolled study period."
)

_SEED_URL_JUNK = "https://www.scirp.org/reference/referencespapers?referenceid=2601244"
_SEED_URL_REAL = "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture sanity: confirm clean_fetch_body really classifies our two REAL bodies
# the way the rest of the harness depends on. If the detector ever changes such
# that the junk no longer reports a shell (or the real body starts to), this
# fails LOUD here rather than silently passing a meaningless behavioral check.
# ─────────────────────────────────────────────────────────────────────────────
def _check_fixture_signals() -> None:
    junk_cf = clean_fetch_body(_JUNK_SHELL_BODY)
    if not junk_cf.shell_reason:
        _fail(
            "fixture JUNK body did not report a shell_reason — the harness can no "
            f"longer exercise the fix (clean_fetch_body returned shell_reason="
            f"{junk_cf.shell_reason!r}, cleaned_len={len(junk_cf.cleaned_text)})"
        )
    real_cf = clean_fetch_body(_REAL_ARTICLE_BODY)
    if real_cf.shell_reason:
        _fail(
            "fixture REAL article body was wrongly reported as a shell "
            f"(shell_reason={real_cf.shell_reason!r}) — a real source would be "
            "dropped; the fix must NEVER drop a real source (§-1.3)"
        )
    print(
        f"  fixture signals OK: JUNK shell_reason={junk_cf.shell_reason!r}, "
        f"REAL shell_reason={real_cf.shell_reason!r}"
    )


def _stub_fetch_content_factory(body: str):
    """Return a ``_fetch_content`` stub yielding ``body`` for every URL.

    Mirrors the real ``_fetch_content`` 5-tuple
    ``(content, ok, title, body_type, jsonld)``. ``ok=True`` + a non-empty body
    is the NORMAL fetch verdict, so the body flows straight into the per-URL
    ``if content:`` row-builder path — exactly where the idx49 guard lives. We do
    NOT use the degraded ``ok=False`` path so the ONLY thing that can exclude the
    junk row is the new shell guard (not a pre-existing stub/starvation gate).
    """

    def _stub(url, max_chars, *args, **kwargs):
        return (body, True, "Fixture source", "full_text", "")

    return _stub


def _run_seed_only(monkeypatch_env, *, body: str, seed_url: str) -> list:
    """Drive the REAL ``run_live_retrieval`` seed_only loop on one URL whose
    fetched body is ``body``. Returns the emitted ``evidence_rows``.

    The redesign flag is ON — that is the cert config where the junk leaked, and
    it is the ONLY config under which a row reaches the down-weight-and-KEEP
    branch (so the idx49 guard must pre-empt it). Offline + cheap: OA resolver
    off, OpenAlex enrichment stubbed, serial fetch.
    """
    saved = {}
    for k, v in monkeypatch_env.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    orig_fetch = lr._fetch_content
    orig_enrich = getattr(lr, "_bounded_openalex_enrich", None)
    try:
        lr._fetch_content = _stub_fetch_content_factory(body)
        if orig_enrich is not None:
            lr._bounded_openalex_enrich = lambda *a, **k: {}
        result = lr.run_live_retrieval(
            research_question="ai automation labor demand future skills",
            seed_urls=[seed_url],
            seed_only=True,
            enable_openalex_enrich=False,
            enable_prefetch_filter=False,
            anchor_seed=False,
        )
        return result.evidence_rows
    finally:
        lr._fetch_content = orig_fetch
        if orig_enrich is not None:
            lr._bounded_openalex_enrich = orig_enrich
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


_ENV = {
    # Serial fetch so the stubbed _fetch_content is the seam.
    "PG_USE_PARALLEL_FETCH": "0",
    # Redesign ON: the cert config where the junk leaked + the only path that
    # reaches the down-weight-and-keep branch the guard must pre-empt.
    "PG_SWEEP_CREDIBILITY_REDESIGN": "1",
    # Keep the loop offline + cheap.
    "PG_ENABLE_LIVE_OA_RESOLVER": "0",
}


def test_site2_junk_shell_excluded_from_cited_evidence() -> None:
    """Case A — the wholly-junk reference-listing shell is NOT emitted as a cited
    evidence row (routed to the existing skip/gap branch instead)."""
    rows = _run_seed_only(_ENV, body=_JUNK_SHELL_BODY, seed_url=_SEED_URL_JUNK)
    if rows:
        _fail(
            "junk fetch-shell was EMITTED as a cited evidence row "
            f"(expected 0 rows, got {len(rows)}): "
            f"{[r.get('source_url') for r in rows]!r} — the idx49 guard did not "
            "fire on the real-output path"
        )
    print("  [site2] PASS: junk fetch-shell excluded from cited evidence (0 rows)")


def test_site2_real_article_still_emitted() -> None:
    """Case B — a real article body IS emitted as a normal evidence row with a
    populated direct_quote. The fix must never drop a real source."""
    rows = _run_seed_only(_ENV, body=_REAL_ARTICLE_BODY, seed_url=_SEED_URL_REAL)
    if len(rows) != 1:
        _fail(
            f"real article was not emitted as exactly one evidence row "
            f"(got {len(rows)} rows) — the fix dropped a real source"
        )
    row = rows[0]
    if not row.get("direct_quote") or len(row["direct_quote"]) < 100:
        _fail(
            "real article evidence row has no usable direct_quote "
            f"(len={len(row.get('direct_quote', ''))})"
        )
    if "displacement effect" not in row["direct_quote"].lower():
        _fail("real article direct_quote did not carry the source prose")
    print("  [site2] PASS: real article emitted as a normal cited evidence row")


def test_site1_junk_shell_not_extractable() -> None:
    """Case A for site 1 — ``refetch_for_extraction_with_diagnostics`` returns an
    EMPTY quote + ``failure_mode='fetch_shell'`` for a junk shell body (routed to
    the existing not-extractable failure branch, NOT cited)."""
    orig_fetch = lr._fetch_content
    try:
        lr._fetch_content = _stub_fetch_content_factory(_JUNK_SHELL_BODY)
        quote, diag = lr.refetch_for_extraction_with_diagnostics(
            "https://www.scirp.org/reference/referencespapers?referenceid=2601244"
        )
    finally:
        lr._fetch_content = orig_fetch
    if quote:
        _fail(
            "site1: junk fetch-shell produced a NON-empty extraction quote "
            f"(len={len(quote)}) — it would be cited as evidence"
        )
    if diag.get("failure_mode") != "fetch_shell":
        _fail(
            "site1: junk fetch-shell did not record failure_mode='fetch_shell' "
            f"(got {diag.get('failure_mode')!r})"
        )
    print("  [site1] PASS: junk fetch-shell -> empty quote, failure_mode='fetch_shell'")


def test_site1_real_article_extractable() -> None:
    """Case B for site 1 — a real article body still yields a non-empty extraction
    quote (eligible). The fix never drops a real source."""
    orig_fetch = lr._fetch_content
    try:
        lr._fetch_content = _stub_fetch_content_factory(_REAL_ARTICLE_BODY)
        quote, diag = lr.refetch_for_extraction_with_diagnostics(
            "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3"
        )
    finally:
        lr._fetch_content = orig_fetch
    if not quote or len(quote) < 100:
        _fail(
            "site1: real article did not yield a usable extraction quote "
            f"(len={len(quote)}) — the fix dropped a real source"
        )
    if diag.get("failure_mode"):
        _fail(
            "site1: real article recorded a failure_mode "
            f"({diag.get('failure_mode')!r}) — it must be eligible"
        )
    print("  [site1] PASS: real article -> non-empty extraction quote, eligible")


def main() -> int:
    print("I-beatboth-011 idx49 — fetch-shell evidence-path behavioral harness")
    print("Fixtures: REAL drb_72 bodies (scirp.org junk shell + AEA jep.33.2.3 article)")
    print()
    _check_fixture_signals()
    print()
    # Site 2 (run_live_retrieval per-URL row builder) — the persisted cited path.
    test_site2_junk_shell_excluded_from_cited_evidence()
    test_site2_real_article_still_emitted()
    # Site 1 (refetch_for_extraction_with_diagnostics) — the extraction quote path.
    test_site1_junk_shell_not_extractable()
    test_site1_real_article_extractable()
    print()
    print("ALL CHECKS PASSED — fetch-shell excluded from cited evidence at BOTH "
          "sites; real sources still emitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
