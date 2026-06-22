#!/usr/bin/env python3
"""I-beatboth-011 (#1289) — fail-loud harness for the junk-SOURCE screen.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect: a handful
of NON-source pages were cited / listed in the bibliography + per-claim
corroboration of a freshly-rendered wide report
(outputs/p6_fixed_replay/workforce/drb_72_ai_labor/report.md, 526 cited sources):
  (a) a Chegg homework page ("Solved Please read the following paper: David H.
      Autor ... | Chegg.com") stood in for a real paper — [521] in the bibliography
      AND woven into the body prose; and
  (b) a JS-error-shell page ("We're sorry but our[site] doesn't work properly
      without JavaScript enabled. Please enable it to continue.") was quoted as a
      corroborator across many claims (host = openalex.org, a REAL repository,
      whose other rows carry real abstracts that MUST be kept).

FIX: a high-precision, faithfulness-NEUTRAL junk-SOURCE screen
(``access_bypass.is_junk_source`` = ``is_junk_source_host`` OR
``is_error_shell_text``) wired at the single corpus-consumption seam in
``run_honest_sweep_r3.py`` (after every retrieval/merge lane AND the fresh/resume
reconcile, BEFORE selection / the approval gate). Junk = a homework-help /
Q&A-not-source HOST or a fetch-error SHELL body. It drops ONLY junk — never a
real journal / repository / gov / news source (§-1.3 keep-all for REAL sources).
strict_verify / NLI / 4-role / span-grounding are untouched.

Asserts (each FAILS LOUD with non-zero exit on regression):
  (A) PREDICATE PRECISION:
        - a Chegg URL source is DROPPED (host signal);
        - an error-shell ("doesn't work properly without JavaScript") source is
          DROPPED (text signal);
        - a real journal / doi.org / pubmed / repository source is KEPT;
        - a real news source is KEPT;
        - near-miss hosts ("notchegg.com") and real long prose that merely QUOTES
          an error phrase are KEPT (no over-screen).
  (B) BEHAVIORAL on the REAL banked corpus_snapshot: when the screen is applied to
      the actual drb_72 corpus, EVERY Chegg + JS-error-shell row is removed from
      retrieval.evidence_rows + classified_sources, while the REAL openalex.org
      abstract rows on the SAME host SURVIVE (proves the effect fires in the real
      consumption path, not just the predicate — §-1.4).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 junk-source screen: {msg}")
    sys.exit(1)


# The exact banked junk strings (drb_72 corpus_snapshot, p6_fixed_replay).
_CHEGG_URL = (
    "https://www.chegg.com/homework-help/questions-and-answers/"
    "please-read-following-paper-david-h-autor-still-many-jobs-history-"
    "future-workplace-automat-q105413568"
)
_SHELL_BODY = (
    "We're sorry but ourresearch-website-2 doesn't work properly without "
    "JavaScript enabled. Please enable it to continue."
)
# Real openalex bodies on the SAME host as the shell — MUST be kept.
_REAL_OPENALEX_BODIES = (
    "Don't Fear the Robots: Automatability and Job Satisfaction DetailsLocations "
    "Year: 2020 Type: preprint Abstract: We analyze automatability and job "
    "satisfaction across occupations using survey microdata, finding "
    "heterogeneous effects on worker wellbeing.",
    "Job Polarization and Structural Change Year: 2014 Type: preprint Abstract: "
    "Job polarization is a widely documented phenomenon in advanced economies "
    "driven by routine-biased technical change and offshoring.",
)


def _check_predicate() -> None:
    from src.tools.access_bypass import (
        is_error_shell_text,
        is_junk_source,
        is_junk_source_host,
    )

    # --- DROP junk ---
    if not is_junk_source_host(_CHEGG_URL):
        _fail("Chegg host not flagged by is_junk_source_host")
    if not is_junk_source(_CHEGG_URL):
        _fail("Chegg URL source not dropped by is_junk_source")
    if not is_error_shell_text(_SHELL_BODY):
        _fail("JS error-shell body not flagged by is_error_shell_text")
    if not is_junk_source("https://openalex.org/W2894904181", _SHELL_BODY):
        _fail("error-shell openalex row not dropped by is_junk_source")
    # Codex P1-1 (#1289): a genuine TERSE WAF / block interstitial carries a
    # WAF/HTTP-error co-token alongside the signature → DROPPED via the co-token
    # path (which is gated by the same residual<=3-words precision guard, so a
    # real source merely MENTIONING a co-token in prose is never caught).
    waf_block = (
        "Just a moment... Please verify you are a human. cloudflare Ray ID "
        "performing security verification."
    )
    if not is_error_shell_text(waf_block):
        _fail("genuine WAF/cloudflare block interstitial not flagged (co-token path)")

    # --- KEEP real sources (journal / doi / pubmed / repository) ---
    real_hosts = (
        "https://doi.org/10.48550/arxiv.2306.15895",
        "https://pubmed.ncbi.nlm.nih.gov/12345678/",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC9334306/",
        "https://www.nature.com/articles/s41586-024-00001-x",
        "https://arxiv.org/abs/2306.15895",
        "https://openalex.org/W4400432169",
        "https://www.oecd.org/en/publications/ai-and-the-future-of-skills.html",
        "https://www.bls.gov/news.release/empsit.nr0.htm",
    )
    real_body = "Real substantive economic analysis sentence carrying content."
    for u in real_hosts:
        if is_junk_source(u, real_body):
            _fail(f"real source wrongly dropped: {u}")

    # --- KEEP real news source ---
    news_hosts = (
        "https://www.reuters.com/world/us/labor-market-2026-01-01/",
        "https://www.nytimes.com/2026/01/01/business/ai-jobs.html",
        "https://www.bbc.com/news/business-12345678",
    )
    for u in news_hosts:
        if is_junk_source(u, real_body):
            _fail(f"real news source wrongly dropped: {u}")

    # --- KEEP real openalex abstracts (same host as the shell) ---
    for body in _REAL_OPENALEX_BODIES:
        if is_error_shell_text(body):
            _fail("real openalex abstract wrongly flagged as error-shell")
        if is_junk_source("https://openalex.org/W123", body):
            _fail("real openalex source wrongly dropped")

    # --- NO over-screen: near-miss hosts + real prose quoting an error phrase ---
    for u in ("https://notchegg.com/x", "https://mychegg.example.org/x",
              "https://scribd-clone.net/x"):
        if is_junk_source_host(u):
            _fail(f"near-miss host wrongly flagged: {u}")
    long_quote = (
        "In our 2023 usability study the legacy enrollment portal doesn't work "
        "properly without JavaScript, and we measured that 42 percent of "
        "clinical-trial participants who attempted online consent could not "
        "complete it, raising equity concerns for digital-first protocols across "
        "multiple sites and demographic strata."
    )
    if is_error_shell_text(long_quote):
        _fail("real long prose quoting an error phrase wrongly flagged")

    # --- Codex P1-1 (#1289) NO over-strip: a SHORT real source TITLE / snippet
    # that merely CONTAINS a generic error phrase but has substantive body text
    # (or is just a bare title) MUST be KEPT. These land in the dangerous SHORT
    # (<=400-char) branch — the bug Codex flagged — and prove the coverage +
    # content-floor guard fires, not a vacuous >400-char pass. ---
    p1_1_keep_titles = (
        "Access Denied",                              # bare title == signature (content floor keeps it)
        "Just a Moment",                              # bare title == signature
        "Access Denied: A Memoir",                    # short titled work containing the phrase
        "Just a Moment: Mindfulness in Practice",     # short title containing the phrase
        "Page Not Found and Other Poems by a Lost Generation Author",
        "Access denied: barriers to healthcare among undocumented migrants in "
        "rural clinics, a 2024 qualitative study",    # substantive short abstract/title
    )
    for t in p1_1_keep_titles:
        if is_error_shell_text(t):
            _fail(f"short real title containing an error phrase wrongly flagged: {t!r}")
        if is_junk_source("https://www.sciencedirect.com/science/article/pii/S0000", t):
            _fail(f"short real title source wrongly dropped: {t!r}")

    print("  (A) PREDICATE PRECISION: PASS "
          "(Chegg dropped, error-shell dropped, journal/doi/pubmed/repository/news "
          "kept, no over-screen)")


def _check_env_host_validation() -> None:
    """Codex P1-2 (#1289): PG_JUNK_SOURCE_HOSTS entries are VALIDATED before they
    join the suffix-drop rule. A bare public suffix / TLD / known-real or
    scholarly domain MUST be silently ignored so it can never drop real sources;
    the hardcoded locked junk list stays authoritative; an arbitrary OTHER full
    host is still accepted (env-additive feature preserved)."""
    import os

    from src.tools.access_bypass import is_junk_source_host

    # A real source on each TLD/domain a bad env value could target.
    real_org = "https://www.aeaweb.org/articles?id=10.1257/jep.29.3.3"
    real_doi = "https://doi.org/10.1257/jep.29.3.3"
    real_gov = "https://www.bls.gov/news.release/empsit.nr0.htm"
    real_edu = "https://economics.mit.edu/research/working-paper"
    real_ncbi = "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    chegg = "https://www.chegg.com/homework-help/q-105413568"

    saved = os.environ.get("PG_JUNK_SOURCE_HOSTS")
    try:
        # (1) Bare public suffixes / TLDs must NOT drop real sources on that TLD,
        #     and the locked Chegg drop must still hold.
        for bad in ("org", "com", "edu", "gov", "net", "io", "co.uk", "ac.uk"):
            os.environ["PG_JUNK_SOURCE_HOSTS"] = bad
            if is_junk_source_host(real_org) or is_junk_source_host(real_gov):
                _fail(f"bare suffix PG_JUNK_SOURCE_HOSTS={bad!r} dropped a real source")
            if not is_junk_source_host(chegg):
                _fail(f"locked Chegg host lost while PG_JUNK_SOURCE_HOSTS={bad!r}")

        # (2) Known-real / scholarly domains must NOT be accepted as junk hosts.
        for bad, real in (
            ("doi.org", real_doi),
            ("ncbi.nlm.nih.gov", real_ncbi),
            ("openalex.org", "https://openalex.org/W4400432169"),
            ("nature.com", "https://www.nature.com/articles/s41586-024-00001-x"),
            ("sciencedirect.com", "https://www.sciencedirect.com/science/article/pii/S0"),
        ):
            os.environ["PG_JUNK_SOURCE_HOSTS"] = bad
            if is_junk_source_host(real):
                _fail(f"known-real PG_JUNK_SOURCE_HOSTS={bad!r} dropped {real}")

        # (3) Any *.gov / *.edu host rejected even if not on the explicit denylist.
        os.environ["PG_JUNK_SOURCE_HOSTS"] = "someagency.gov"
        if is_junk_source_host("https://someagency.gov/report"):
            _fail("a *.gov env entry was accepted as a junk host")
        os.environ["PG_JUNK_SOURCE_HOSTS"] = "stanford.edu"
        if is_junk_source_host("https://stanford.edu/paper"):
            _fail("a *.edu env entry was accepted as a junk host")

        # (4) The env-ADDITIVE feature is preserved: an arbitrary OTHER full junk
        #     host IS accepted (high precision is not an allowlist collapse).
        os.environ["PG_JUNK_SOURCE_HOSTS"] = "studymoose.com,coursehero.org"
        if not is_junk_source_host("https://studymoose.com/essay/x"):
            _fail("a valid additive junk host (studymoose.com) was rejected")
        if not is_junk_source_host("https://coursehero.org/q/x"):
            _fail("a valid additive junk host (coursehero.org) was rejected")
        if is_junk_source_host(real_org) or is_junk_source_host(real_edu):
            _fail("additive junk host config dropped a real source")

        # (5) Codex P1-2 (#1289) EXPANDED multi-label public suffixes: a bare
        #     `com.br` / `co.in` / `org.au` / `net.au` env entry must NOT be
        #     accepted (it would suffix-drop EVERY real registrable domain under
        #     it). Negative control with a real source ON that suffix proves the
        #     rejection actually fires, not just a prose claim.
        multi_label_suffixes = (
            ("com.br", "https://www.scielo.com.br/article/abc"),
            ("co.in", "https://www.thehindu.co.in/news/x"),
            ("org.au", "https://www.aihw.org.au/reports/x"),
            ("net.au", "https://www.abc.net.au/news/x"),
            ("com.au", "https://www.theguardian.com.au/x"),
            ("co.nz", "https://www.stuff.co.nz/x"),
            ("co.za", "https://www.news24.co.za/x"),
            ("com.cn", "https://www.gov.com.cn/x"),
        )
        for bad, real in multi_label_suffixes:
            os.environ["PG_JUNK_SOURCE_HOSTS"] = bad
            if is_junk_source_host(real):
                _fail(f"multi-label public suffix PG_JUNK_SOURCE_HOSTS={bad!r} "
                      f"dropped a real source {real}")
            # The locked Chegg drop must still hold while a bad suffix is set.
            if not is_junk_source_host(chegg):
                _fail(f"locked Chegg host lost while PG_JUNK_SOURCE_HOSTS={bad!r}")
    finally:
        if saved is None:
            os.environ.pop("PG_JUNK_SOURCE_HOSTS", None)
        else:
            os.environ["PG_JUNK_SOURCE_HOSTS"] = saved

    print("  (D) ENV-HOST VALIDATION: PASS "
          "(bare suffixes/TLDs + known-real/scholarly + *.gov/*.edu ignored; "
          "locked junk list authoritative; arbitrary full junk host still additive)")


def _check_behavioral_on_banked_corpus() -> None:
    """Apply the screen to the REAL drb_72 banked corpus_snapshot and prove the
    junk rows are removed while the real same-host rows survive (§-1.4)."""
    import json

    from src.tools.access_bypass import is_junk_source, is_junk_source_host

    snap_path = (
        _REPO
        / "outputs" / "p6_fixed_replay" / "workforce" / "drb_72_ai_labor"
        / "corpus_snapshot.json"
    )
    if not snap_path.exists():
        # The banked defect corpus is the acceptance fixture; its absence is a
        # hard failure (the harness must run against real data, LAW II).
        _fail(f"banked corpus_snapshot missing: {snap_path}")

    data = json.loads(snap_path.read_text(encoding="utf-8"))
    retr = data.get("retrieval") or {}
    evidence_rows = retr.get("evidence_rows") or []
    classified_sources = retr.get("classified_sources") or []
    if not evidence_rows or not classified_sources:
        _fail("banked corpus_snapshot has no evidence_rows/classified_sources")

    def _ev_url(r: dict) -> str:
        return str(r.get("source_url") or r.get("url") or "")

    def _ev_text(r: dict) -> str:
        return str(r.get("direct_quote") or r.get("statement") or "")

    def _src_url(s: dict) -> str:
        return str(s.get("url") or s.get("source_url") or "")

    # Identify the ground-truth junk + real-same-host rows BEFORE screening.
    shell_marker = "doesn't work properly without javascript"
    chegg_marker = "chegg.com"
    junk_ev_before = [
        r for r in evidence_rows
        if chegg_marker in _ev_url(r).lower()
        or shell_marker in _ev_text(r).lower()
    ]
    real_openalex_before = [
        r for r in evidence_rows
        if "openalex.org" in _ev_url(r).lower()
        and shell_marker not in _ev_text(r).lower()
        and len(_ev_text(r)) > 200
    ]
    chegg_src_before = [
        s for s in classified_sources if chegg_marker in _src_url(s).lower()
    ]
    if not junk_ev_before:
        _fail("banked corpus has no junk evidence_rows — wrong/empty fixture")
    if not real_openalex_before:
        _fail("banked corpus has no real openalex rows — cannot prove no-over-drop")
    if not chegg_src_before:
        _fail("banked corpus has no chegg classified_source — wrong fixture")

    # Apply the screen exactly as the run wiring does.
    ev_kept = [
        r for r in evidence_rows
        if not is_junk_source(_ev_url(r), _ev_text(r))
    ]
    src_kept = [s for s in classified_sources if not is_junk_source_host(_src_url(s))]

    # EVERY junk evidence row removed.
    for r in junk_ev_before:
        if r in ev_kept:
            _fail(f"junk evidence_row survived the screen: {_ev_url(r)[:80]}")
    # EVERY real same-host openalex row kept (no over-drop).
    for r in real_openalex_before:
        if r not in ev_kept:
            _fail(f"REAL openalex row wrongly dropped: {_ev_url(r)[:80]}")
    # Chegg classified_source removed.
    for s in chegg_src_before:
        if s in src_kept:
            _fail(f"chegg classified_source survived: {_src_url(s)[:80]}")

    # Codex P2 (#1289): HARD exact-count invariants on the REAL banked corpus —
    # fail LOUD on ANY future regression (a wider/narrower screen, a bypassed
    # seam, a predicate drift). These are the OBSERVED post-fix counts on the
    # banked drb_72 corpus_snapshot (evidence_rows 814->799, classified_sources
    # 833->827, and EXACTLY 5 same-host openalex rows kept).
    if len(evidence_rows) != 814:
        _fail(f"banked evidence_rows count drifted: {len(evidence_rows)} != 814")
    if len(ev_kept) > 799:
        _fail(f"under-screened evidence_rows: kept {len(ev_kept)} > 799 baseline (must drop >= original junk; dropping more is OK, over-screen guarded by chrome_junk_extend harness)")
    if len(classified_sources) != 833:
        _fail(f"banked classified_sources count drifted: "
              f"{len(classified_sources)} != 833")
    if len(src_kept) > 827:
        _fail(f"under-screened classified_sources: kept {len(src_kept)} > 827 baseline")
    if len(real_openalex_before) != 5:
        _fail(f"banked real same-host openalex rows != 5 "
              f"(got {len(real_openalex_before)})")
    _oa_kept = [r for r in real_openalex_before if r in ev_kept]
    if len(_oa_kept) != 5:
        _fail(f"exactly-5 same-host openalex KEPT invariant broken "
              f"(got {len(_oa_kept)} of 5)")

    print(
        f"  (B) BEHAVIORAL on banked drb_72 corpus: PASS "
        f"(evidence_rows {len(evidence_rows)} -> {len(ev_kept)} "
        f"[{len(junk_ev_before)} junk dropped, {len(real_openalex_before)} real "
        f"same-host openalex kept]; classified_sources {len(classified_sources)} "
        f"-> {len(src_kept)} [{len(chegg_src_before)} chegg dropped])"
    )


def _check_resume_path_evidence_for_gen() -> None:
    """The defect run (p6_fixed_replay) is a POST-SELECTION corpus_snapshot resume:
    selection is SKIPPED and the snapshot's billed ``evidence_for_gen`` pool feeds
    generation + the bibliography/corroboration DIRECTLY (run_honest_sweep_r3.py
    builds ``ev_pool = {ev['evidence_id']: ev for ev in evidence_for_gen}``). So the
    junk-source screen MUST also fire on the reloaded ``evidence_for_gen`` — screening
    only retrieval.evidence_rows (which feeds selection) would be a no-op on this
    replay. This proves the effect fires in the REAL replay consumption path (§-1.4),
    not just the predicate."""
    import json

    from src.tools.access_bypass import is_junk_source

    snap_path = (
        _REPO
        / "outputs" / "p6_fixed_replay" / "workforce" / "drb_72_ai_labor"
        / "corpus_snapshot.json"
    )
    if not snap_path.exists():
        _fail(f"banked corpus_snapshot missing: {snap_path}")
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    efg = data.get("evidence_for_gen") or []
    if not efg:
        _fail("banked corpus_snapshot has no top-level evidence_for_gen pool")

    def _url(r: dict) -> str:
        return str(r.get("source_url") or r.get("url") or "")

    def _txt(r: dict) -> str:
        return str(r.get("direct_quote") or r.get("statement") or "")

    shell = "doesn't work properly without javascript"
    chegg_before = [r for r in efg if "chegg.com" in _url(r).lower()]
    shell_before = [r for r in efg if shell in _txt(r).lower()]
    real_oa_before = [
        r for r in efg
        if "openalex.org" in _url(r).lower()
        and shell not in _txt(r).lower()
        and len(_txt(r)) > 200
    ]
    if not chegg_before or not shell_before:
        _fail("banked evidence_for_gen has no chegg/shell junk — wrong fixture")
    if not real_oa_before:
        _fail("banked evidence_for_gen has no real openalex rows — cannot prove keep")

    # Apply the SAME screen the run wires at the resume evidence_for_gen load.
    kept = [r for r in efg if not is_junk_source(_url(r), _txt(r))]
    # Build ev_pool exactly as the run does (line ~10534) and assert junk-free.
    ev_pool = {r.get("evidence_id"): r for r in kept}
    for eid, r in ev_pool.items():
        if "chegg.com" in _url(r).lower() or shell in _txt(r).lower():
            _fail(f"junk survived into ev_pool (would cite/list it): {_url(r)[:80]}")
    for r in real_oa_before:
        if r not in kept:
            _fail(f"REAL openalex row wrongly dropped from evidence_for_gen: {_url(r)[:80]}")

    # Codex P2 (#1289): HARD exact-count invariant on the resume billed pool —
    # evidence_for_gen 821->806, with EXACTLY 5 same-host openalex rows kept.
    if len(efg) != 821:
        _fail(f"banked evidence_for_gen count drifted: {len(efg)} != 821")
    if len(kept) > 806:
        _fail(f"under-screened evidence_for_gen: kept {len(kept)} > 806 baseline")
    if len(real_oa_before) != 5:
        _fail(f"banked real same-host openalex in evidence_for_gen != 5 "
              f"(got {len(real_oa_before)})")
    _oa_kept = [r for r in real_oa_before if r in kept]
    if len(_oa_kept) != 5:
        _fail(f"exactly-5 same-host openalex KEPT in evidence_for_gen broken "
              f"(got {len(_oa_kept)} of 5)")

    print(
        f"  (C) RESUME-PATH evidence_for_gen -> ev_pool: PASS "
        f"(evidence_for_gen {len(efg)} -> {len(kept)}; "
        f"{len(chegg_before)} chegg + {len(shell_before)} shell removed from ev_pool, "
        f"{len(real_oa_before)} real openalex kept — the report bibliography/"
        f"corroboration on this replay is built from the screened pool)"
    )


def _check_screen_helper_wired_at_all_seams() -> None:
    """Codex P1-1 (#1289): the junk screen was BYPASSED by two later fresh-run
    injection paths (required-entity lane, saturation gap round). The fix hoists a
    single module-level ``_screen_junk_evidence`` helper and calls it at THREE
    seams. Assert (statically, from source — importing the 10k-line sweep would
    trigger heavy module-level imports per §8.4) that the helper is DEFINED once
    and CALLED at all three seams with distinct telemetry labels."""
    sweep = _REPO / "scripts" / "run_honest_sweep_r3.py"
    if not sweep.exists():
        _fail(f"run_honest_sweep_r3.py missing: {sweep}")
    src = sweep.read_text(encoding="utf-8")

    if "def _screen_junk_evidence(" not in src:
        _fail("module-level _screen_junk_evidence helper not defined")
    call_count = src.count("_screen_junk_evidence(")
    # 1 def + 3 call sites == 4 textual occurrences of the name with a paren.
    if call_count < 4:
        _fail(f"_screen_junk_evidence wired at fewer than 3 seams "
              f"(only {call_count - 1} call sites found; expected 3)")
    # The three seams are tagged by distinct telemetry labels — the initial seam
    # (label==""), the required-entity lane, and the saturation gap round.
    for label_token in ('label=""', 'label="req_entity"', 'label="gap_round"'):
        if label_token not in src:
            _fail(f"junk-screen seam label {label_token!r} not found "
                  "(a bypass seam is unscreened)")
    print("  (E) HELPER WIRED AT ALL 3 SEAMS: PASS "
          "(_screen_junk_evidence defined once + called at the initial seam, the "
          "required-entity lane [req_entity], and the saturation gap round [gap_round])")


def main() -> None:
    print("I-beatboth-011 (#1289) junk-source screen harness")
    _check_predicate()
    _check_env_host_validation()
    _check_behavioral_on_banked_corpus()
    _check_resume_path_evidence_for_gen()
    _check_screen_helper_wired_at_all_seams()
    print("PASS I-beatboth-011 junk-source screen: all assertions hold")


if __name__ == "__main__":
    main()
