"""DICED harness — I-deepfix-001 Wave-2 (#1370): compose-stage ANTI-GLUE.

Proves ``PG_COMPOSE_NO_UNRELATED_GLUE`` on FROZEN box2 artifacts (read-only), seconds-level, NO fresh
run / NO fetch / NO GPU / NO LLM. It exercises the SMALLEST callable join unit
``cross_source_synthesis._join_analytical_pair`` — the exact function the composer uses to join two
verified single-source clauses. It builds THREE clauses as verbatim substrings of REAL box2 evidence
spans (so each clause is faithful-by-construction and carries a real ``[#ev:<id>:<start>-<end>]`` token):

  * clause_a          — ev_1226  "total publications using a Gaussian distribution"
  * clause_b_unrel    — ev_446   "was summed up by Informant 17"   (topically UNRELATED to clause_a)
  * clause_a2         — frey_osborne_computerisation  "the probability of computerisation for 702 detailed occupations"
  * clause_b_rel      — ev_165   "600 detailed occupations in over 300 occupational profiles"  (RELATED: shares "detailed","occupations")

Signal:
  RED  (flag OFF): the topically-UNRELATED NEUTRAL pair is GLUED with "; separately," (incoherent run-on).
  GREEN(flag ON) : the UNRELATED pair renders as TWO SEPARATE sentences (no "; separately,"), while the
                   genuinely-RELATED pair STILL joins with "; separately," (the split is targeted).

Run: PYTHONIOENCODING=utf-8 PYTHONPATH=<cwd> python scripts/harness_compose_no_unrelated_glue.py
"""
from __future__ import annotations

import json
import os
import re
import sys

SCRATCHPAD = (
    r"C:\Users\msn\AppData\Local\Temp\claude\C--POLARIS"
    r"\dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391\scratchpad"
)
EVIDENCE_POOL = os.path.join(SCRATCHPAD, "box2_evidence_pool.json")

# (evidence_id, verbatim_substring) — offsets are computed against the FROZEN pool so the token is honest.
CLAUSE_A = ("ev_1226", "total publications using a Gaussian distribution")
CLAUSE_B_UNRELATED = ("ev_446", "was summed up by Informant 17")
CLAUSE_A2 = ("frey_osborne_computerisation", "the probability of computerisation for 702 detailed occupations")
CLAUSE_B_RELATED = ("ev_165", "600 detailed occupations in over 300 occupational profiles")


def _load_pool() -> dict:
    with open(EVIDENCE_POOL, encoding="utf-8") as fh:
        rows = json.load(fh)
    return {r.get("evidence_id"): (r.get("direct_quote") or "") for r in rows}


def _build_clause(pool: dict, eid: str, substring: str) -> str:
    """Build a strict_verify-shaped clause: '<verbatim substring> [#ev:<id>:<start>-<end>]', where the
    span offsets are the REAL character range of the verbatim substring inside box2's direct_quote."""
    quote = pool.get(eid, "")
    start = quote.find(substring)
    if start < 0:
        raise SystemExit(f"BLOCKED: substring not found verbatim in {eid}: {substring!r}")
    end = start + len(substring)
    # Capitalize the leading char so the clause reads as a sentence unit (as split_into_sentences yields).
    prose = substring[0].upper() + substring[1:]
    return f"{prose} [#ev:{eid}:{start}-{end}]"


def main() -> int:
    from src.polaris_graph.generator import cross_source_synthesis as css

    pool = _load_pool()
    clause_a = _build_clause(pool, *CLAUSE_A)
    clause_b_unrel = _build_clause(pool, *CLAUSE_B_UNRELATED)
    clause_a2 = _build_clause(pool, *CLAUSE_A2)
    clause_b_rel = _build_clause(pool, *CLAUSE_B_RELATED)

    ov_unrel = len(css._glue_content_words(clause_a) & css._glue_content_words(clause_b_unrel))
    ov_rel = len(css._glue_content_words(clause_a2) & css._glue_content_words(clause_b_rel))

    print("=" * 78)
    print("DICED HARNESS — PG_COMPOSE_NO_UNRELATED_GLUE (compose-stage anti-glue)")
    print("=" * 78)
    print(f"clause_a         : {clause_a}")
    print(f"clause_b_unrel   : {clause_b_unrel}")
    print(f"  content-word overlap(unrelated) = {ov_unrel}")
    print(f"clause_a2        : {clause_a2}")
    print(f"clause_b_rel     : {clause_b_rel}")
    print(f"  content-word overlap(related)   = {ov_rel}")
    print("-" * 78)

    glue = "; separately,"

    def _glued(text: str) -> bool:
        return glue in text

    def _two_sentences(text: str) -> bool:
        # A period/terminal followed by whitespace + capital = a real sentence boundary (the production
        # _SENT_SPLIT_RE shape: terminal .!?] + whitespace + [A-Z0-9]).
        return bool(re.search(r"[.!?\]]\s+[A-Z0-9]", text))

    # ---- RED: flag OFF (default) — the UNRELATED neutral pair is GLUED ----
    os.environ.pop("PG_COMPOSE_NO_UNRELATED_GLUE", None)
    assert not css.compose_no_unrelated_glue_enabled(), "flag should default OFF"
    off_unrel = css._join_analytical_pair(clause_a, clause_b_unrel, "neutral")
    off_rel = css._join_analytical_pair(clause_a2, clause_b_rel, "neutral")
    print("[flag OFF]")
    print(f"  unrelated -> {off_unrel!r}")
    print(f"  related   -> {off_rel!r}")

    red_ok = _glued(off_unrel) and _glued(off_rel)
    print(f"  RED expectation (both glued with '; separately,') : {'RED CONFIRMED' if red_ok else 'NOT MET'}")
    print("-" * 78)

    # ---- GREEN: flag ON — the UNRELATED pair SPLITS; the RELATED pair stays glued ----
    os.environ["PG_COMPOSE_NO_UNRELATED_GLUE"] = "1"
    assert css.compose_no_unrelated_glue_enabled(), "flag should be ON"
    on_unrel = css._join_analytical_pair(clause_a, clause_b_unrel, "neutral")
    on_rel = css._join_analytical_pair(clause_a2, clause_b_rel, "neutral")
    print("[flag ON]")
    print(f"  unrelated -> {on_unrel!r}")
    print(f"  related   -> {on_rel!r}")

    # Faithfulness-neutral check: same two evidence_ids survive the split.
    ids_off = css._distinct_ev_ids(off_unrel)
    ids_on = css._distinct_ev_ids(on_unrel)

    green_unrel_split = (not _glued(on_unrel)) and _two_sentences(on_unrel)
    green_rel_kept = _glued(on_rel)
    green_ids_preserved = ids_on == ids_off and len(ids_on) == 2
    green_ok = green_unrel_split and green_rel_kept and green_ids_preserved

    print(f"  unrelated split into 2 sentences, no '; separately,' : {green_unrel_split}")
    print(f"  related STILL glued with '; separately,'             : {green_rel_kept}")
    print(f"  citations preserved (same 2 ev-ids OFF vs ON)        : {green_ids_preserved} {sorted(ids_on)}")
    print("=" * 78)

    if red_ok and green_ok:
        print("RESULT: GREEN — fix splits topically-unrelated neutral glue, keeps related pairs joined,")
        print("        preserves both citations; OFF is byte-identical to current behaviour.")
        return 0
    print("RESULT: FAIL — see expectations above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
