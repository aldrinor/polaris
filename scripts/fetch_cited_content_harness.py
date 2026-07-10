#!/usr/bin/env python3
"""Fast fetch cited-content harness (I-deepfix-004 / Fable design 2026-07-09).

Proves in ~5 min (parallel) whether the fetch/search module returns the CITED
article for a labeled set of real URLs — replacing the hours-long full-pipeline
loop. It exercises ONE production seam:

    ``refetch_for_extraction_with_diagnostics(url, max_chars)`` (live_retriever)

which runs the whole chain (``_fetch_content`` -> AccessBypass cascade -> DOI
redirect / ``#page`` anchor / fitz page-slice / Zyte / PDF extractors ->
``clean_fetch_body`` -> fetch-shell screen -> step-D front-matter screen ->
provenance quote) and returns ``(quote, diagnostics)``.

The verdict oracle here is HARNESS-OWNED and INDEPENDENT: it NEVER imports the
production predicate under test (``is_issue_front_matter`` / shell detectors) —
I-wire-013 independence, so a production regression cannot mask itself. The
oracle re-derives front-matter / collision structure from its own rules.

Exit codes: 0 green (no FAIL / UNREACHABLE), 1 any FAIL / UNREACHABLE,
2 VOID (a required fix-flag is OFF or ZYTE_API_KEY is empty — no PASS is ever
written), 3 internal harness error.

No mocks: the live network IS the test (§-1.1 — the span text is the proof,
never a count). The only offline part is ``tests/.../test_fetch_harness_oracle.py``,
which unit-tests the oracle functions below against the real banked span heads.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

import yaml

# Make ``src`` importable when run directly (sys.path[0] is scripts/, not root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_CASES_PATH = _REPO_ROOT / "config" / "fetch_harness_cases.yaml"
_OUTPUT_ROOT = _REPO_ROOT / "outputs" / "fetch_harness"

# ── Verdict labels ──────────────────────────────────────────────────────────
PASS = "PASS"
FAIL = "FAIL"
UNREACHABLE = "UNREACHABLE"
DEGRADED_OK = "DEGRADED_OK"
VOID = "VOID"

# ── Oracle tuning (harness-owned; deliberately distinct from production) ─────
ELIGIBLE_MIN_CHARS = 200            # a quote < 200 chars is a refusal, not a span
ORACLE_DOT_LEADER_MIN = 3           # >=3 dot-leader TOC lines => front matter
GOOD_CONTROLS = (
    "good_arxiv_html", "good_feds_note", "good_oa_pdf_nber", "good_oecd_fullreport",
)
# Failure modes that mean "could not reach the source" (block green for `article`).
_UNREACHABLE_MODES = frozenset({"fetch_failed", "timeout", "exception"})
# Failure modes that are an HONEST degrade for `article_or_degrade` /
# `recover_or_disclose` (recover-or-disclose, never a silent wrong span).
_DEGRADE_OK_MODES = frozenset({
    "wrong_content_front_matter", "fetch_shell", "paywall_shell",
    "thin_content", "fetch_failed", "timeout",
})

# Dot-leader run (three-or-more dots) then a page number — the canonical TOC line
# shape, robust to space-collapsed single-line PDF extraction. Runs on RAW text
# (squash strips the dots). High precision: never occurs in real article prose.
_ORACLE_DOT_LEADER_RE = re.compile(r"\.{3,}\s*[ivxlcdm\d]{1,5}\b", re.IGNORECASE)


# ── Oracle primitives (pure; imported by the offline unit tests) ────────────
def squash(text: Optional[str]) -> str:
    """NFKD -> strip combining marks -> casefold -> keep letters+digits only.

    Survives PDF hyphen-breaks, diacritics, case, and whitespace. Idempotent, so
    the yaml fingerprints (already squashed) can be squashed again at load time.
    """
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return "".join(ch for ch in no_marks.casefold() if ch.isalnum())


def contains_any(squashed_text: str, needles: Iterable[str]) -> bool:
    """True iff ANY squashed needle is a substring. Empty needle-set => True
    (vacuous — ``contains_any-where-listed`` per the design)."""
    needle_list = [n for n in (needles or []) if n]
    if not needle_list:
        return True
    return any(n in squashed_text for n in needle_list)


def contains_none(squashed_text: str, forbidden: Iterable[str]) -> bool:
    """True iff NO squashed forbidden fingerprint is a substring. Empty => True."""
    return not any(f in squashed_text for f in (forbidden or []) if f)


def front_matter_structural(quote: Optional[str]) -> bool:
    """INDEPENDENT front-matter detector (does NOT import the production predicate).

    Fires on any one high-precision signal:
      1. >= ORACLE_DOT_LEADER_MIN dot-leader-then-page TOC lines (on RAW text).
      2. Cyrillic editorial-board masthead (``редакционная коллегия``).
      3. ``table of contents``.
      4. ``editorial board`` AND an ``issn`` marker co-occur.

    Deliberately does NOT fire on a lone ``содержание`` — real poultry-article
    prose ("содержание белка" = protein content) carries that word.
    """
    raw = quote or ""
    if len(_ORACLE_DOT_LEADER_RE.findall(raw)) >= ORACLE_DOT_LEADER_MIN:
        return True
    sq = squash(raw)
    if "редакционнаяколлегия" in sq:
        return True
    if "tableofcontents" in sq:
        return True
    if "editorialboard" in sq and "issn" in sq:
        return True
    return False


def _work_id(case: dict) -> str:
    """Cited-WORK identity for the collision oracle: DOI when present, else URL."""
    doi = str(case.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return "url:" + str(case.get("url") or "").strip().lower()


def identical_span_collision(entries: list[dict]) -> set[str]:
    """Global content-identity collision: group ELIGIBLE entries by squashed span;
    any group whose entries cite >= 2 DIFFERENT works (DOIs/URLs) is a single
    multi-article CONTAINER blob laundered into distinct citations — FAIL them all.

    ``entries`` are dicts with keys: name, work_id, squashed_quote, eligible.
    Returns the set of flagged case names.
    """
    by_span: dict[str, list[dict]] = {}
    for e in entries:
        if not e.get("eligible") or not e.get("squashed_quote"):
            continue
        by_span.setdefault(e["squashed_quote"], []).append(e)
    flagged: set[str] = set()
    for group in by_span.values():
        works = {e["work_id"] for e in group}
        if len(works) >= 2:
            flagged.update(e["name"] for e in group)
    return flagged


def group_distinctness_violations(entries: list[dict]) -> set[str]:
    """Within each declared ``distinct_group``, every ELIGIBLE pair must differ
    after squash. Two same-group entries sharing a squashed span are the same
    laundered blob — flag them. Returns the set of flagged case names."""
    by_group: dict[str, list[dict]] = {}
    for e in entries:
        grp = e.get("group")
        if not grp or not e.get("eligible") or not e.get("squashed_quote"):
            continue
        by_group.setdefault(grp, []).append(e)
    flagged: set[str] = set()
    for members in by_group.values():
        seen: dict[str, str] = {}
        for e in members:
            sq = e["squashed_quote"]
            if sq in seen and seen[sq] != e["name"]:
                flagged.add(e["name"])
                flagged.add(seen[sq])
            seen.setdefault(sq, e["name"])
    return flagged


# ── Per-class verdict ───────────────────────────────────────────────────────
def verdict_for(expect: str, quote: str, diag: dict, case: dict) -> tuple[str, dict]:
    """Return (verdict, checks). Pure — depends only on the quote/diagnostics and
    the case labels, never on the production predicate."""
    fm = diag.get("failure_mode", "") or ""
    sq = squash(quote)
    eligible = len(quote or "") >= ELIGIBLE_MIN_CHARS
    c_any = contains_any(sq, case.get("contains_squashed") or [])
    c_none = contains_none(sq, case.get("not_contains_squashed") or [])
    fms = front_matter_structural(quote)
    checks = {
        "eligible": eligible, "contains_any": c_any,
        "contains_none": c_none, "front_matter_structural": fms,
    }
    article_pass = (fm == "" and eligible and c_any and c_none and not fms)
    has_positive = bool(case.get("contains_squashed"))

    if expect == "article":
        if article_pass:
            return PASS, checks
        if fm in _UNREACHABLE_MODES:
            return UNREACHABLE, checks
        return FAIL, checks

    if expect in ("article_or_degrade", "recover_or_disclose"):
        if article_pass:
            return PASS, checks
        if fm in _DEGRADE_OK_MODES:
            return DEGRADED_OK, checks
        return FAIL, checks

    if expect == "no_front_matter_span":
        if fm == "wrong_content_front_matter":
            return PASS, checks           # production screen caught it — best case
        if eligible:
            if fms or not c_none:
                return FAIL, checks       # adopted a cover / TOC / masthead / banned head
            if has_positive and not c_any:
                return FAIL, checks       # adopted a non-front-matter but wrong-work span
            return PASS, checks           # recovered a real non-front-matter span
        return DEGRADED_OK, checks        # honest refusal — no bad span adopted

    if expect == "refused":
        return (FAIL if eligible else PASS), checks

    return FAIL, checks                   # unknown expect class => fail loud


# ── Flag gate (can't fake a pass) ───────────────────────────────────────────
def _falsey(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("0", "false", "off", "no", "disabled")


def check_flags() -> tuple[bool, dict]:
    """Assert every fix-flag is ON and ZYTE_API_KEY is present. Returns
    (ok, flag_states). Any OFF => not ok => the caller writes RESULT VOID."""
    from src.tools.access_bypass import pdf_cited_work_slice_enabled
    from src.polaris_graph.retrieval.shell_detector import (
        cited_span_shell_detect_enabled, span_cited_work_screen_enabled,
    )
    states = {
        "pdf_cited_work_slice_enabled": bool(pdf_cited_work_slice_enabled()),
        "span_cited_work_screen_enabled": bool(span_cited_work_screen_enabled()),
        "cited_span_shell_detect_enabled": bool(cited_span_shell_detect_enabled()),
        "PG_REFETCH_FULL_BODY_on": not _falsey(os.environ.get("PG_REFETCH_FULL_BODY", "1")),
        "PG_DISABLE_ACCESS_BYPASS_off": os.environ.get("PG_DISABLE_ACCESS_BYPASS", "0") != "1",
        "ZYTE_API_KEY_present": bool((os.environ.get("ZYTE_API_KEY") or "").strip()),
    }
    return all(states.values()), states


def _load_seam() -> Callable[..., tuple[str, dict]]:
    from src.polaris_graph.retrieval.live_retriever import (
        refetch_for_extraction_with_diagnostics,
    )
    return refetch_for_extraction_with_diagnostics


# ── Case loading ────────────────────────────────────────────────────────────
def load_cases(path: Path = _CASES_PATH) -> list[dict]:
    """Load + normalize the labeled cases. Squashes every fingerprint at load
    (idempotent) so the oracle compares like-for-like."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[dict] = []
    for entry in raw.get("cases", []):
        case = dict(entry)
        case["contains_squashed"] = [squash(x) for x in (entry.get("contains") or [])]
        case["not_contains_squashed"] = [squash(x) for x in (entry.get("not_contains") or [])]
        cases.append(case)
    return cases


def _select(cases: list[dict], only: Optional[list[str]]) -> list[dict]:
    if not only:
        return cases
    wanted = {w.strip() for chunk in only for w in chunk.split(",") if w.strip()}
    sel = [c for c in cases if c.get("name") in wanted or str(c.get("ev") or "") in wanted]
    return sel


# ── Run one case ────────────────────────────────────────────────────────────
def run_case(case: dict, seam: Callable[..., tuple[str, dict]], quote_max: int,
             dump_bodies: bool = False) -> dict:
    start = time.monotonic()
    try:
        quote, diag = seam(case["url"], max_chars=quote_max)
    except Exception as exc:               # seam-level exception -> honest failure
        quote, diag = "", {
            "failure_mode": "exception", "exception_type": type(exc).__name__,
            "method": "none", "raw_char_count": 0,
        }
    elapsed = round(time.monotonic() - start, 2)
    verdict, checks = verdict_for(case["expect"], quote, diag, case)
    result = {
        "name": case["name"],
        "ev": case.get("ev", ""),
        "url": case["url"],
        "doi": case.get("doi", ""),
        "group": case.get("group", ""),
        "expect": case["expect"],
        "verdict": verdict,
        "failure_mode": diag.get("failure_mode", "") or "",
        "access_method": diag.get("method", "none"),
        "raw_char_count": int(diag.get("raw_char_count", 0) or 0),
        "elapsed_s": elapsed,
        "quote_head": (quote or "")[:300],
        "quote_len": len(quote or ""),
        "checks": checks,
        "work_id": _work_id(case),
        "squashed_quote": squash(quote),
        "eligible": checks["eligible"],
        "collision_reason": "",
    }
    if dump_bodies:                        # bridge: retain the FULL recovered body
        result["quote_full"] = quote or ""
    return result


def _timeout_result(case: dict, elapsed_s: float = 0.0) -> dict:
    """UNREACHABLE(timeout) result for a case abandoned at the total wall-clock
    deadline or on a wedged seam. Same shape as ``run_case`` output so the
    collision + reporting stages treat it uniformly."""
    return {
        "name": case["name"], "ev": case.get("ev", ""), "url": case["url"],
        "doi": case.get("doi", ""), "group": case.get("group", ""),
        "expect": case["expect"], "verdict": UNREACHABLE,
        "failure_mode": "timeout", "access_method": "none",
        "raw_char_count": 0, "elapsed_s": round(float(elapsed_s), 2),
        "quote_head": "", "quote_len": 0,
        "checks": {"eligible": False, "contains_any": False,
                   "contains_none": True, "front_matter_structural": False},
        "work_id": _work_id(case), "squashed_quote": "",
        "eligible": False, "collision_reason": "",
    }


def run_all(cases: list[dict], max_parallel: int, case_timeout: int,
            total_timeout: int, quote_max: int,
            dump_bodies: bool = False) -> list[dict]:
    """Run every case on a bounded pool of DAEMON worker threads under a HARD
    total wall-clock deadline.

    A wedged seam thread can NEVER keep the harness alive past ``total_timeout``:
    the workers are daemon threads (abandoned at interpreter exit, never joined)
    and the collector stops waiting at the deadline instead of relying on a
    ``ThreadPoolExecutor`` context-manager exit — whose ``shutdown(wait=True)``,
    plus the executor's atexit join of its NON-daemon workers, would otherwise
    block the whole process on the wedged thread until it finished (Codex P1-2).

    Per-case ``case_timeout`` still bounds an individual case, and concurrency is
    still capped at ``max_parallel`` via a semaphore, so no behaviour is lost.
    """
    seam = _load_seam()
    deadline = time.monotonic() + float(total_timeout)
    results: dict[str, dict] = {}
    result_lock = threading.Lock()
    done_events: dict[str, threading.Event] = {c["name"]: threading.Event() for c in cases}
    sem = threading.BoundedSemaphore(max(1, min(max_parallel, len(cases))))

    def _worker(case: dict) -> None:
        name = case["name"]
        started = time.monotonic()
        try:
            with sem:
                if time.monotonic() >= deadline:      # deadline blew while queued
                    result = _timeout_result(case)
                else:
                    result = run_case(case, seam, quote_max, dump_bodies)
        except BaseException:                          # noqa: BLE001 — never die silently
            result = _timeout_result(case, time.monotonic() - started)
        with result_lock:
            results.setdefault(name, result)           # first writer wins
        done_events[name].set()

    threads = [threading.Thread(target=_worker, args=(c,),
                                name=f"harness-{c['name']}", daemon=True) for c in cases]
    for t in threads:
        t.start()

    # Collect in submission order; each case waits at most case_timeout AND never
    # past the total deadline. A case still unfinished at the deadline is recorded
    # UNREACHABLE(timeout) and its daemon worker is abandoned (never joined).
    for case in cases:
        name = case["name"]
        remaining = min(float(case_timeout), deadline - time.monotonic())
        if not done_events[name].wait(timeout=max(0.0, remaining)):
            with result_lock:
                results.setdefault(name, _timeout_result(case, float(case_timeout)))

    for case in cases:                                 # backstop: fill any gap
        with result_lock:
            results.setdefault(case["name"], _timeout_result(case))

    ordered = [results[c["name"]] for c in cases]
    _apply_collisions(ordered)
    return ordered


def _apply_collisions(results: list[dict]) -> None:
    """Override to FAIL any case whose eligible span collides across works
    (global) or within its distinct-group. Mutates results in place."""
    flagged = identical_span_collision(results) | group_distinctness_violations(results)
    for r in results:
        if r["name"] in flagged and r["verdict"] in (PASS, DEGRADED_OK):
            r["verdict"] = FAIL
            r["collision_reason"] = "container_collision"


# ── Reporting ───────────────────────────────────────────────────────────────
def _summarize(results: list[dict]) -> dict:
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    good_pass = all(
        any(r["name"] == g and r["verdict"] == PASS for r in results)
        for g in GOOD_CONTROLS
    )
    no_fail = not any(r["verdict"] in (FAIL, UNREACHABLE) for r in results)
    return {"tally": tally, "good_controls_all_pass": good_pass, "no_fail": no_fail,
            "authorize_full_pipeline": no_fail and good_pass}


def write_outputs(results: list[dict], flag_states: dict, run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = _summarize(results)
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "flag_states": flag_states,
        "summary": summary,
        "cases": results,
    }
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Fetch cited-content harness report",
        f"generated_utc: {payload['generated_utc']}",
        "",
        "## Flag states",
    ]
    for k, v in flag_states.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## Summary",
        f"- tally: {summary['tally']}",
        f"- all 4 good controls PASS: {summary['good_controls_all_pass']}",
        f"- no FAIL / UNREACHABLE: {summary['no_fail']}",
        f"- AUTHORIZE full pipeline: {summary['authorize_full_pipeline']}",
        "",
        "## Cases",
    ]
    for r in results:
        lines.append(
            f"- [{r['verdict']}] {r['name']} ({r['ev'] or '-'}) expect={r['expect']} "
            f"mode={r['failure_mode'] or 'ok'} via={r['access_method']} "
            f"chars={r['raw_char_count']} {r['elapsed_s']}s"
            + (f" collision={r['collision_reason']}" if r["collision_reason"] else "")
        )
    fails = [r for r in results if r["verdict"] in (FAIL, UNREACHABLE)]
    if fails:
        lines += ["", "## FAIL / UNREACHABLE — offending span heads (first 300 chars)"]
        for r in fails:
            lines.append(f"\n### {r['name']} [{r['verdict']}] mode={r['failure_mode'] or 'ok'}")
            lines.append(f"checks={r['checks']}")
            lines.append(f"span={r['quote_head']!r}")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


# ── Content bridge (fetch -> compose): --dump-bodies ────────────────────────
def bodies_from_results(results: list[dict]) -> list[dict]:
    """PURE, non-mutating. Project each result to the bridge row the compose
    harness consumes: ``{name, ev, url, verdict, access_method, quote}`` where
    ``quote`` is the FULL recovered body (``quote_full``, captured only under
    ``--dump-bodies``); falls back to the 300-char ``quote_head`` (and to "" for
    timeout rows that carry neither). Imported by the offline unit test."""
    rows: list[dict] = []
    for r in results:
        rows.append({
            "name": r.get("name", ""),
            "ev": r.get("ev", ""),
            "url": r.get("url", ""),
            "verdict": r.get("verdict", ""),
            "access_method": r.get("access_method", "none"),
            "quote": r.get("quote_full", r.get("quote_head", "")) or "",
        })
    return rows


def write_bodies(results: list[dict], run_dir: Path) -> Path:
    """Write ``bodies.json`` (the bridge file) into the run dir; return its path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "bodies.json"
    path.write_text(
        json.dumps(bodies_from_results(results), indent=2, ensure_ascii=False),
        encoding="utf-8")
    return path


# ── CLI ─────────────────────────────────────────────────────────────────────
def _build_url_case(url: str, expect: str, contains: Optional[list[str]]) -> dict:
    stems: list[str] = []
    for chunk in (contains or []):
        stems.extend(s for s in chunk.split(",") if s.strip())
    return {
        "name": "adhoc_url", "url": url, "expect": expect,
        "contains": stems, "not_contains": [],
        "contains_squashed": [squash(s) for s in stems], "not_contains_squashed": [],
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch cited-content harness")
    ap.add_argument("--only", action="append", help="case name(s) or ev id(s), comma-ok")
    ap.add_argument("--rerun-failures", metavar="RESULTS_JSON",
                    help="rerun only FAIL/UNREACHABLE cases from a prior results.json")
    ap.add_argument("--list", action="store_true", help="list cases and exit")
    ap.add_argument("--url", help="ad-hoc single URL (needs --expect)")
    ap.add_argument("--expect", help="expect class for --url")
    ap.add_argument("--contains", action="append", help="fingerprint stem(s) for --url")
    ap.add_argument("--dump-bodies", action="store_true",
                    help="bridge: also write outputs/fetch_harness/<utc>/bodies.json "
                         "with the FULL recovered body per case (lifts quote_max to "
                         ">=20000 and forces PG_REFETCH_FULL_BODY=1 for this run)")
    args = ap.parse_args(argv)

    # Bridge run: force full-body refetch BEFORE the flag gate so an operator's
    # PG_REFETCH_FULL_BODY=0 cannot VOID a dump; the default path is untouched.
    if args.dump_bodies:
        os.environ["PG_REFETCH_FULL_BODY"] = "1"

    try:
        all_cases = load_cases()
    except Exception as exc:               # noqa: BLE001 — surface load errors as exit 3
        print(f"RESULT ERROR - could not load cases: {exc}", file=sys.stderr)
        return 3

    if args.list:
        for c in all_cases:
            print(f"{c['name']:<22} {c['expect']:<20} {c.get('ev', '-'):<8} {c['url']}")
        return 0

    if args.url:
        if not args.expect:
            print("ERROR: --url requires --expect", file=sys.stderr)
            return 3
        cases = [_build_url_case(args.url, args.expect, args.contains)]
    elif args.rerun_failures:
        try:
            prior = json.loads(Path(args.rerun_failures).read_text(encoding="utf-8"))
        except Exception as exc:           # noqa: BLE001
            print(f"RESULT ERROR - bad --rerun-failures file: {exc}", file=sys.stderr)
            return 3
        fail_names = {c["name"] for c in prior.get("cases", [])
                      if c.get("verdict") in (FAIL, UNREACHABLE)}
        cases = [c for c in all_cases if c["name"] in fail_names]
    else:
        cases = _select(all_cases, args.only)

    if not cases:
        print("ERROR: no cases selected", file=sys.stderr)
        return 3

    ok, flag_states = check_flags()
    if not ok:
        off = [k for k, v in flag_states.items() if not v]
        print(f"RESULT VOID - FIX FLAGS OFF: {off}", file=sys.stderr)
        return 2

    max_parallel = _env_int("PG_HARNESS_MAX_PARALLEL", 12)
    case_timeout = _env_int("PG_HARNESS_CASE_TIMEOUT_S", 240)
    total_timeout = _env_int("PG_HARNESS_TOTAL_TIMEOUT_S", 900)
    quote_max = _env_int("PG_HARNESS_QUOTE_MAX", 2000)
    if args.dump_bodies:                   # bridge needs the full body, not a head
        quote_max = max(quote_max, 20000)

    try:
        results = run_all(cases, max_parallel, case_timeout, total_timeout,
                          quote_max, args.dump_bodies)
    except Exception as exc:               # noqa: BLE001 — harness bug, not a data FAIL
        print(f"RESULT ERROR - harness crashed: {exc}", file=sys.stderr)
        return 3

    run_dir = _OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bodies_path = None
    if args.dump_bodies:                   # write bodies.json, THEN strip quote_full
        bodies_path = write_bodies(results, run_dir)   # so results.json stays lean
        for r in results:
            r.pop("quote_full", None)
    summary = write_outputs(results, flag_states, run_dir)

    for r in results:
        print(f"[{r['verdict']:<11}] {r['name']:<22} expect={r['expect']:<20} "
              f"mode={r['failure_mode'] or 'ok'}")
    print(f"\ntally={summary['tally']}  good_controls_all_pass="
          f"{summary['good_controls_all_pass']}  "
          f"authorize={summary['authorize_full_pipeline']}")
    print(f"report: {run_dir / 'report.md'}")
    if bodies_path is not None:
        print(f"bodies: {bodies_path}  (full-body dump; verdicts computed at "
              f"quote_max={quote_max} and MAY differ from a default-cap run)")
    return 0 if summary["no_fail"] else 1


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


if __name__ == "__main__":
    raise SystemExit(main())
