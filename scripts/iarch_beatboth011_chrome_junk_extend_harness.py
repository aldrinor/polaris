#!/usr/bin/env python
"""I-beatboth-011 drb_78 (#1289) — fail-loud behavioral replay harness.

Loads the BANKED drb_78 corpus + report and asserts that the EXTENDED junk/chrome
screens now EXCLUDE the social/login junk sources and the garbled scraped headers,
while KEEPING every real clinical/journal source and every legitimate section
header (the §-1.1/§-1.3 negative controls — over-strip is worse than a leak).

This is the §-1.4 behavioral gate: it exercises the REAL screen functions
(``is_junk_source`` / ``is_junk_source_host`` from access_bypass, and
``_screen_garbled_headers`` / ``_header_line_is_garbled`` from the sweep runner)
against the real banked artifact, and FAILS LOUD (non-zero exit) if the effect
did not fire OR if a negative control regressed. It does NOT re-fetch and does NOT
touch strict_verify / NLI / 4-role / span-grounding.

Run:  python scripts/iarch_beatboth011_chrome_junk_extend_harness.py
Exit: 0 iff every assertion passes; 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CORPUS_DIR = REPO_ROOT / "outputs" / "p7_clean_audit" / "drb_78_parkinsons_dbs"
CORPUS_SNAPSHOT = CORPUS_DIR / "corpus_snapshot.json"
REPORT_MD = CORPUS_DIR / "report.md"

from src.tools.access_bypass import is_junk_source, is_junk_source_host  # noqa: E402
from scripts.run_honest_sweep_r3 import (  # noqa: E402
    _header_line_is_garbled,
    _low_quality_ev_row_url,
    _screen_garbled_headers,
    _screen_junk_evidence,
)
from src.polaris_graph.generator.corpus_snapshot import (  # noqa: E402
    load_corpus_snapshot,
    reconstruct_retrieval,
)


class HarnessError(AssertionError):
    """A behavioral assertion failed — the screen did not fire as required."""


def _row_url(row: dict) -> str:
    return str(row.get("source_url") or row.get("url") or "")


def _row_text(row: dict) -> str:
    return str(row.get("direct_quote") or row.get("statement") or "")


def main() -> int:
    if not CORPUS_SNAPSHOT.exists():
        raise HarnessError(f"banked corpus missing: {CORPUS_SNAPSHOT}")
    if not REPORT_MD.exists():
        raise HarnessError(f"banked report missing: {REPORT_MD}")

    corpus = json.loads(CORPUS_SNAPSHOT.read_text(encoding="utf-8"))
    rows = corpus.get("evidence_for_gen") or []
    if not isinstance(rows, list) or not rows:
        raise HarnessError("evidence_for_gen empty/missing in banked corpus")

    failures: list[str] = []

    # ── POSITIVE: the social/login junk HOSTS now drop (host screen). ─────────
    JUNK_HOSTS = (
        "https://www.facebook.com/parkinsondotorg/posts/x",
        "https://www.facebook.com/login/device-based/regular/login/?login_attempt=1",
        "https://www.reddit.com/r/doctorsUK/comments/1833qh6/x",
        "https://www.linkedin.com/posts/anniebrookswallis_x",
        "https://twitter.com/some/status/123",
        "https://x.com/some/status/123",
        "https://www.instagram.com/p/abc/",
        "https://www.youtube.com/watch?v=abc",
        "https://quizlet.com/66336379/deep-brain-stimulation-flash-cards/",
    )
    for u in JUNK_HOSTS:
        if not is_junk_source_host(u):
            failures.append(f"POSITIVE host-screen MISS: {u} not flagged junk")

    # ── POSITIVE (REAL RE-RENDER PATH, §-1.4): exercise the ACTUAL resume seam ─
    # load_corpus_snapshot -> reconstruct_retrieval -> _screen_junk_evidence, the
    # exact wiring a `--resume` re-render runs (reconstruct 6399 -> screen 7236 ->
    # bib build). This is STRONGER than the bare predicate: it proves the
    # reconstructed rows carry source_url in the shape the screen reads AND that the
    # screen actually removes the junk hosts on this banked corpus. No models / no
    # network (pure local). FAILS LOUD if any junk host survives the real screen or
    # a real journal is dropped.
    realpath_survivors: list[str] = []
    realpath_dropped = 0
    realpath_real_kept = 0
    try:
        payload = load_corpus_snapshot(CORPUS_DIR)
        retr = reconstruct_retrieval(payload)
        n_in = len(retr.evidence_rows)
        kept_rows, _kept_srcs, _telem = _screen_junk_evidence(
            retr.evidence_rows, retr.classified_sources, log=None, run_dir=None, label=""
        )
        realpath_dropped = n_in - len(kept_rows)
        realpath_survivors = [
            _low_quality_ev_row_url(r) for r in kept_rows
            if any(
                s in _low_quality_ev_row_url(r).lower()
                for s in ("facebook.com", "reddit.com", "linkedin.com", "quizlet.com",
                          "twitter.com", "instagram.com", "youtube.com")
            )
        ]
        realpath_real_kept = sum(
            1 for r in kept_rows
            if any(
                s in _low_quality_ev_row_url(r).lower()
                for s in ("doi.org", "nature.com", "frontiersin.org", "pmc.ncbi.nlm.nih.gov")
            )
        )
        if realpath_survivors:
            failures.append(
                f"POSITIVE (real path): {len(realpath_survivors)} junk host(s) SURVIVED "
                f"reconstruct->_screen_junk_evidence: {realpath_survivors[:5]}"
            )
        if realpath_dropped <= 0:
            failures.append(
                "POSITIVE (real path): _screen_junk_evidence dropped ZERO rows on the "
                "reconstructed corpus — the screen did not fire"
            )
        if realpath_real_kept == 0:
            failures.append(
                "NEGATIVE (real path): no real journals (doi.org/nature/frontiersin) "
                "survived the screen — over-strip regression"
            )
    except Exception as exc:  # FAIL LOUD — the real path must be exercisable
        failures.append(
            f"POSITIVE (real path): reconstruct->screen RAISED {type(exc).__name__}: {exc}"
        )

    # The actual banked social rows must now drop through is_junk_source (host OR body).
    social_rows = [
        r for r in rows
        if isinstance(r, dict)
        and any(
            s in _row_url(r).lower()
            for s in ("facebook.com", "reddit.com", "linkedin.com", "quizlet.com")
        )
    ]
    if not social_rows:
        failures.append("no banked social rows found — corpus changed?")
    dropped_social = [r for r in social_rows if is_junk_source(_row_url(r), _row_text(r))]
    if len(dropped_social) != len(social_rows):
        kept = [
            _row_url(r) for r in social_rows
            if not is_junk_source(_row_url(r), _row_text(r))
        ]
        failures.append(
            f"POSITIVE: {len(social_rows) - len(dropped_social)}/{len(social_rows)} "
            f"social rows NOT dropped: {kept[:5]}"
        )

    # ── POSITIVE: the garbled scraped HEADERS drop (render header-sanity). ────
    GARBLED_HEADERS = (
        "# Parkinson’s disease affects... - Parkinson's Foundation [Log In]"
        "(https://www.facebook.com/login/device-based/regular/login/?login_attempt=1).[39].[41]",
        "## Adverse events The model accounted for both treatment-speci [...] "
        "associated with increasing postural instability.",
        "### Some heading https://example.com/page",
        "## Heading with a citation token [12]",
    )
    for h in GARBLED_HEADERS:
        if not _header_line_is_garbled(h):
            failures.append(f"POSITIVE header-screen MISS: {h[:80]!r} not flagged garbled")

    # The screen must actually REMOVE the garbled headers from a report slice.
    report_md = REPORT_MD.read_text(encoding="utf-8")
    screened = _screen_garbled_headers(report_md)
    leaked = [
        ln for ln in screened.split("\n")
        if _header_line_is_garbled(ln)
    ]
    if leaked:
        failures.append(
            f"POSITIVE: {len(leaked)} garbled header(s) survived the screen: "
            f"{[l[:70] for l in leaked[:3]]}"
        )
    # And specifically the catastrophic facebook-login HEADER (drb_78 L60) must be gone.
    # NOTE (scope, per §-1.4 + advisor): the header screen removes garbled HEADER LINES only.
    # A facebook-login URL fragment that is MASHED MID-SENTENCE inside a verified body span is
    # NOT a header and is intentionally NOT mutated here (rewriting verified span prose is a
    # composition defect, out of scope). On a fresh RE-RENDER it does not re-form anyway, because
    # the SOURCE producing it (the facebook-post evidence row) is host-dropped by the extended
    # junk-host screen before it ever enters the corpus. So we assert (a) no HEADER line carries
    # the login URL, and (b) the source-drop mechanism removes the facebook rows (asserted above).
    fb_login_headers = [
        ln for ln in screened.split("\n")
        if ln.lstrip().startswith("#") and "facebook.com/login/device-based" in ln
    ]
    if fb_login_headers:
        failures.append(
            f"POSITIVE: facebook login-wall HEADER still present after screen: "
            f"{[h[:70] for h in fb_login_headers]}"
        )
    # The facebook-post SOURCES (which produced that header span) must be host-dropped so a
    # re-render never re-forms the login-wall header.
    fb_source_rows = [
        r for r in rows
        if isinstance(r, dict) and "facebook.com" in _row_url(r).lower()
    ]
    fb_undropped = [
        _row_url(r) for r in fb_source_rows
        if not is_junk_source(_row_url(r), _row_text(r))
    ]
    if fb_undropped:
        failures.append(
            f"POSITIVE: {len(fb_undropped)} facebook-post source(s) NOT host-dropped "
            f"(login-wall header would re-form on re-render): {fb_undropped[:3]}"
        )

    # ── NEGATIVE: real journals / gov / news hosts are NEVER host-dropped. ────
    REAL_HOSTS = (
        "https://doi.org/10.1136/jnnp.62.1.2",
        "https://www.nature.com/articles/x",
        "https://www.frontiersin.org/articles/10.3389/x",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
        "https://www.fda.gov/x",
        "https://clinicaltrials.gov/study/NCT000",
        "https://oatext.com/x",       # contains "x.com" substring — must NOT match x.com
        "https://www.exponent.com/x",  # contains "x.com" substring — must NOT match x.com
        "https://www.michaeljfox.org/x",
        "https://www.thelancet.com/x",
    )
    for u in REAL_HOSTS:
        if is_junk_source_host(u):
            failures.append(f"NEGATIVE host-screen REGRESSION: real host {u} flagged junk")

    # ── NEGATIVE: a real journal row whose BODY carries login/subscribe chrome ─
    #     (ev_148, doi.org/BMJ) must NOT be host-dropped — only the chrome STRING
    #     is stripped elsewhere; the SOURCE stays.
    ev148 = next((r for r in rows if isinstance(r, dict) and r.get("evidence_id") == "ev_148"), None)
    if ev148 is None:
        failures.append("ev_148 (real BMJ row w/ chrome body) missing — corpus changed?")
    else:
        if is_junk_source(_row_url(ev148), _row_text(ev148)):
            failures.append(
                "NEGATIVE: ev_148 (real doi.org/BMJ source w/ login-CTA body) was "
                "host/junk-dropped — a real source must be KEPT, only its chrome stripped"
            )
        # The chrome STRING must be removed from its body while the prose survives.
        from src.tools.access_bypass import clean_fetch_body  # noqa: PLC0415
        cleaned = clean_fetch_body(_row_text(ev148)).cleaned_text
        if "[Log In]" in cleaned or "[Subscribe]" in cleaned:
            failures.append(
                "NEGATIVE/POSITIVE: ev_148 login-CTA chrome NOT stripped from body: "
                f"{cleaned[:160]!r}"
            )
        if "parkinson" not in cleaned.lower():
            failures.append(
                "NEGATIVE: ev_148 real prose ('Parkinson') lost after chrome-strip"
            )

    # ── NEGATIVE: every CLEAN section header in the banked report is KEPT. ─────
    import re  # noqa: PLC0415
    hdr_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    clean_headers = []
    for ln in report_md.split("\n"):
        m = hdr_re.match(ln)
        if not m:
            continue
        if _header_line_is_garbled(ln):
            continue  # garbled — expected to drop
        clean_headers.append(ln)
    if not clean_headers:
        failures.append("no clean headers found in banked report — parse error?")
    screened_set = set(screened.split("\n"))
    dropped_clean = [h for h in clean_headers if h not in screened_set]
    if dropped_clean:
        failures.append(
            f"NEGATIVE: {len(dropped_clean)} CLEAN header(s) wrongly dropped: "
            f"{[h[:70] for h in dropped_clean[:5]]}"
        )

    # Specific clean controls that MUST survive (real long titles + the H1 title).
    CLEAN_CONTROLS = (
        "# Research report:",  # H1 title prefix (exempt)
        "Research Gaps, Policy Implications, and Future Directions for Family-Centered PD and DBS Care",
        "Regulatory Frameworks Governing DBS Device Safety, Adverse Event Reporting",
        "Caregiver Roles in DBS Management: Device Operation Boundaries, Liability",
    )
    for ctrl in CLEAN_CONTROLS:
        present = any(ctrl in ln for ln in screened.split("\n"))
        if not present:
            failures.append(f"NEGATIVE: clean control header dropped: {ctrl[:70]!r}")
    # A long title that ends with no period and carries no chrome must NOT be garbled.
    if _header_line_is_garbled(
        "### Research Gaps, Policy Implications, and Future Directions for "
        "Family-Centered PD and DBS Care"
    ):
        failures.append("NEGATIVE: a real 13-word section title flagged garbled (word-count regression)")

    # ── REPORT ────────────────────────────────────────────────────────────────
    result = {
        "ok": not failures,
        "banked_evidence_rows": len(rows),
        "realpath_rows_dropped": realpath_dropped,
        "realpath_junk_survivors": len(realpath_survivors),
        "realpath_real_journals_kept": realpath_real_kept,
        "social_rows_found": len(social_rows),
        "social_rows_dropped": len(dropped_social),
        "garbled_headers_in_report_before": sum(
            1 for ln in report_md.split("\n") if _header_line_is_garbled(ln)
        ),
        "garbled_headers_after_screen": len(leaked),
        "clean_headers_kept": len(clean_headers) - len(dropped_clean),
        "clean_headers_total": len(clean_headers),
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        print(f"\nHARNESS FAILED: {len(failures)} assertion(s) did not hold.", file=sys.stderr)
        return 1
    print("\nHARNESS PASSED: junk hosts + garbled headers excluded; real sources + clean headers kept.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
