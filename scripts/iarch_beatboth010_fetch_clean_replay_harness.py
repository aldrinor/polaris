#!/usr/bin/env python3
"""I-beatboth-010 (#1288) FIX-A — fail-loud replay harness for the crawl-header leak.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect: the crawl-reader
chrome headers (`Title:`, `URL Source:`, `Published Time:`, `Number of Pages:`,
`Markdown Content:`, `Warning: Target URL returned error NNN`) emitted by the Jina/Crawl4AI
fetch path leak verbatim into the persisted, CITED `evidence_for_gen[*].direct_quote` rows
(built by `live_retriever._build_provenance_quote`) and then into `report.md` under the
"verbatim, span-verified" label. The existing `strip_web_boilerplate` allowlist catches
`URL Source:/Markdown Content:/Title:` but MISSES `Published Time:`/`Number of Pages:`/the
`Warning:` error line, and — critically — was NEVER CALLED on any fetch/clean path.

This harness loads the BANKED v3 corpus (no pipeline run) and:
  (A) RED EVIDENCE — asserts the banked `direct_quote` rows currently DO carry the header
      tokens (proves the defect actually fired in real output: 335/586 rows).
  (B) GREEN GATE — runs the NEW `access_bypass.clean_fetch_body` over each banked
      `direct_quote` and asserts ZERO header tokens remain. Before FIX-A this fails
      (clean_fetch_body absent / allowlist incomplete); after FIX-A it passes.

FAITHFULNESS UNTOUCHED: `clean_fetch_body` is allowlist-only, whole-line-anchored input
hygiene — it deletes only confirmed crawl-chrome lines, never assertional prose. strict_verify
/ NLI / 4-role / span-grounding are not touched. In a fresh run the strip happens BEFORE the
direct_quote is built, so provenance offsets are computed on the cleaned content and stay
self-consistent.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_DD = _REPO / "outputs" / "p6_fresh_glm52_v3" / "workforce" / "drb_72_ai_labor"
_SNAPSHOT = _DD / "corpus_snapshot.json"
_REPORT = _DD / "report.md"

# High-precision crawl-reader (Jina/Crawl4AI) header tokens (NOT `Forbidden`/`subscribers`,
# which appear in real prose). These are unique fetch-reader artifacts that must NOT survive
# into a cited body. Matched as substrings (NOT line-anchored) because the banked data shows
# two formats: a few rows keep the headers on their own lines, but ~330/335 collapse them into
# an INLINE preamble (`Title: X URL Source: Y Published Time: Z Markdown Content: <body>`), so a
# line-anchored check would miss 98% of the real leak.
_HEADER_TOKENS = re.compile(
    r"|".join([
        r"URL Source\s*:",
        r"Markdown Content\s*:",
        r"Published Time\s*:",
        r"Number of Pages\s*:",
        r"Warning:\s*Target URL returned error \d+",
    ]),
    re.IGNORECASE,
)

# I-beatboth-011 idx 46/68 (#1289): high-precision BODY social-chrome (Scribd / Facebook / YouTube)
# + journal masthead/ISSN. These sit AFTER ``Markdown Content:`` so the FIX-A preamble drop misses
# them — only the extended whole-line allowlist catches them. ALL multi-token (a bare
# "Share"/"subscribers"/"cite" in real prose is never matched) so this token set is a faithful
# leak detector.
_SOCIAL_CHROME_TOKENS = re.compile(
    r"|".join([
        r"Like Comment Share",
        r"Download free for \d+ days",
        r"Upload Document",
        r"Tap to unmute",
        r"\bsubscribers\s+Subscribed\b",
        r"Share Save Download",
        r"Cite this paper as",
        r"\bISSN\s*:?\s*\d{4}-\d{3}[\dXx]\b",
    ]),
    re.IGNORECASE,
)


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-010 FIX-A replay: {msg}")
    sys.exit(1)


def _count_hits(text: str) -> int:
    return len(_HEADER_TOKENS.findall(text or ""))


def main() -> None:
    if not _SNAPSHOT.exists():
        _fail(f"banked corpus_snapshot.json not found at {_SNAPSHOT}")
    snap = json.loads(_SNAPSHOT.read_text(encoding="utf-8", errors="replace"))
    efg = snap.get("evidence_for_gen") or []
    if not efg:
        _fail("corpus_snapshot.json has no evidence_for_gen rows")

    dirty_rows = [e for e in efg if _HEADER_TOKENS.search(e.get("direct_quote", "") or "")]
    total_dq_hits = sum(_count_hits(e.get("direct_quote", "") or "") for e in efg)

    # (A) RED EVIDENCE — the defect must be present in the banked output, else the harness is vacuous.
    print(
        f"RED evidence: {len(dirty_rows)}/{len(efg)} evidence_for_gen.direct_quote rows carry "
        f"crawl-reader header tokens ({total_dq_hits} total hits)."
    )
    if len(dirty_rows) < 50:
        _fail(
            f"expected the banked corpus to be DIRTY (>=50 rows with header tokens) to prove the "
            f"defect fired; found only {len(dirty_rows)} — wrong corpus or already-clean."
        )

    # (B) GREEN GATE — the NEW clean_fetch_body must remove EVERY header token from EVERY direct_quote.
    try:
        from src.tools.access_bypass import clean_fetch_body
    except Exception as exc:  # noqa: BLE001 — pre-fix this is the RED state
        _fail(
            f"clean_fetch_body not importable yet (FIX-A not built): {exc!r}. "
            f"This is the expected RED state before the fix."
        )

    residual_rows = 0
    residual_hits = 0
    sample_miss = None
    for e in efg:
        dq = e.get("direct_quote", "") or ""
        if not dq:
            continue
        cleaned = clean_fetch_body(dq).cleaned_text
        h = _count_hits(cleaned)
        if h:
            residual_rows += 1
            residual_hits += h
            if sample_miss is None:
                m = _HEADER_TOKENS.search(cleaned)
                sample_miss = (e.get("evidence_id"), m.group(0)[:60] if m else "?")

    if residual_rows:
        _fail(
            f"clean_fetch_body left header tokens in {residual_rows} direct_quote rows "
            f"({residual_hits} hits). Sample miss: {sample_miss}. The allowlist is incomplete "
            f"or clean_fetch_body did not run whole-line strip."
        )

    # Secondary: a real journal body must KEEP its assertional prose (faithfulness-neutral check).
    probe = next(
        (e for e in dirty_rows if "acemoglu" in (e.get("evidence_id", "") or "").lower()),
        dirty_rows[0],
    )
    cleaned_probe = clean_fetch_body(probe.get("direct_quote", "")).cleaned_text
    if len(cleaned_probe) < 200:
        _fail(
            f"clean_fetch_body over-stripped a real journal body (evidence_id={probe.get('evidence_id')}): "
            f"cleaned to {len(cleaned_probe)} chars — the strip must remove ONLY chrome lines, never prose."
        )

    print(
        f"GREEN ok: clean_fetch_body removed ALL crawl-reader header tokens from all "
        f"{len(efg)} direct_quote rows (was {len(dirty_rows)} dirty / {total_dq_hits} hits); "
        f"real prose preserved (probe {probe.get('evidence_id')} -> {len(cleaned_probe)} chars)."
    )

    # (C) idx 46/68 — the EXTENDED allowlist strips Scribd/FB/YouTube body social-chrome + masthead/ISSN
    # (deterministic: these phrases may not be in THIS banked AI-labor corpus, so a synthetic body proves
    # recall) while keeping real prose with the same bare words (precision). Plus: ZERO social-chrome
    # survives in any cleaned banked row.
    _social_chrome = [
        "Like Comment Share",
        "Download free for 30 days",
        "Upload Document",
        "Tap to unmute",
        "2.75K subscribers Subscribed 0 Share Save Download",
        "Share Save Download 1.2M views",
        "Cite this paper as: Smith et al. 2024",
        "ISSN: 0002-8282",
    ]
    _real_prose = [
        "Researchers share the view that automation displaced routine workers [1].",
        "You can download the dataset from the appendix to reproduce the results.",
        "The journal reported 50000 subscribers in 2023, a record figure.",
        "Firms cite labor costs as the primary driver of AI adoption.",
    ]
    cleaned_social = clean_fetch_body("\n".join(_social_chrome + _real_prose)).cleaned_text
    surviving_chrome = [c for c in _social_chrome if c in cleaned_social]
    dropped_prose = [p for p in _real_prose if p not in cleaned_social]
    if surviving_chrome:
        _fail(f"(C) idx46 social-chrome SURVIVED clean_fetch_body: {surviving_chrome}")
    if dropped_prose:
        _fail(f"(C) idx46 over-strip — real prose dropped: {dropped_prose}")
    residual_social = sum(
        1 for e in efg
        if _SOCIAL_CHROME_TOKENS.search(clean_fetch_body(e.get("direct_quote", "") or "").cleaned_text)
    )
    if residual_social:
        _fail(f"(C) idx46: {residual_social} cleaned banked rows still carry social-chrome tokens")
    print(
        f"(C) idx46 ok: all {len(_social_chrome)} social-chrome lines stripped, all {len(_real_prose)} "
        f"real-prose lines kept; 0 social-chrome residual across {len(efg)} cleaned banked rows."
    )

    # (D) idx 45 — BASKET-LAYER propagation. The basket member's source span is
    # credibility_pass._row_span_text(row) = row['direct_quote'] (or 'statement'); the claim-local span
    # is a SUBSTRING of it. So a fetch-cleaned row -> a clean member span by construction. Prove it on
    # the real function: for every banked row, the member source resolved from the CLEANED row carries
    # ZERO header AND social chrome (today's harness stopped at corpus_snapshot, never the basket layer).
    from src.polaris_graph.synthesis.credibility_pass import _row_span_text  # noqa: PLC0415
    basket_dirty = 0
    sample = None
    for e in efg:
        dq = e.get("direct_quote", "") or ""
        if not dq:
            continue
        cleaned_row = {"direct_quote": clean_fetch_body(dq).cleaned_text}
        member_src = _row_span_text(cleaned_row)
        if _HEADER_TOKENS.search(member_src) or _SOCIAL_CHROME_TOKENS.search(member_src):
            basket_dirty += 1
            if sample is None:
                sample = e.get("evidence_id")
    if basket_dirty:
        _fail(
            f"(D) idx45: {basket_dirty} basket-member source spans (credibility_pass._row_span_text on "
            f"the cleaned row) still carry chrome (sample {sample}); the clean does not propagate to the "
            f"basket layer."
        )
    print(
        f"(D) idx45 ok: all {len(efg)} basket-member source spans (via credibility_pass._row_span_text on "
        f"the cleaned rows) carry ZERO header/social chrome — the fetch clean propagates to the basket layer."
    )

    print(
        "PASS I-beatboth-010 FIX-A (+ I-beatboth-011 idx 45/46): the banked corpus proves the crawl-header "
        "leak fired in the cited direct_quote rows (RED); clean_fetch_body strips every header token AND the "
        "extended Scribd/FB/YouTube/masthead social-chrome whole-line while preserving assertional prose "
        "(GREEN); and the cleaned span propagates chrome-free to the basket-member layer (idx45). "
        "Faithfulness gates untouched."
    )


if __name__ == "__main__":
    main()
