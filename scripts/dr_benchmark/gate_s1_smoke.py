"""S1 SMOKE audit — compile stratified DRB prompts through the Research Planning
Gate in AUTONOMOUS mode and assert the two S1 acceptance properties:

  1. NO invented hard constraint  — every ``force==hard`` term in the compiled
     contract carries origin in {explicit, user_answer, user_edit} AND a
     quote-verified prompt span (validate_contract returns clean).
  2. An ASSUMPTION record for every inferred term — every inferred /
     policy_default term that carries a value is disclosed in the contract's
     ``assumptions`` (the autonomous sweep backfills any the compiler omitted).

It also asserts the load-bearing autonomous invariant (``needs_input`` is always
False; state is ``auto_pinned`` or ``unsatisfiable``).

Two run modes
-------------
* **OFFLINE (default, spend-free, in-workflow safe).** A deterministic compiler
  STUB derives the contract from the REAL S0 candidate adapter output (promoting
  only span-verified hard candidates; everything else preference/open; disclosing
  inferred terms). This exercises the whole gate machinery — candidate seeding →
  contract parse → autonomous disclosure → deterministic validation → hashing —
  without a network call, so it runs inside the 10-min workflow cap.

* **LIVE (monitored job only).** ``--live`` drops the stub and lets the gate call
  the real small policy model (``PG_PLANNING_GATE_LIVE=1``). This is the FULL
  100-prompt audit path; it is DEFERRED to a monitored job (do not run it in the
  capped workflow). This script is the documented harness for it.

Usage
-----
    python3 scripts/dr_benchmark/gate_s1_smoke.py            # offline, 8 prompts
    python3 scripts/dr_benchmark/gate_s1_smoke.py --all      # offline, 100 prompts
    PG_PLANNING_GATE_LIVE=1 python3 scripts/dr_benchmark/gate_s1_smoke.py --live --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# repo root on sys.path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.planning.candidate_adapter import reconcile_candidates  # noqa: E402
from src.polaris_graph.planning.planning_gate_schema import (  # noqa: E402
    DISCLOSURE_ORIGINS,
    HARD_ELIGIBLE_ORIGINS,
    validate_contract,
)
from src.polaris_graph.planning.research_planning_gate import (  # noqa: E402
    run_research_planning_gate,
)

_QUERY_JSONL = _REPO / "third_party/deep_research_bench/data/prompt_data/query.jsonl"

# The 8 stratified DRB ids (spanning narrow / compound / non-English / source-
# restricted / format-heavy / comparison), chosen from the real corpus.
_SMOKE_IDS = {
    "72",  # source-restricted (English-only journal literature review) — en
    "30",  # non-Western academic theory (named lenses) — zh
    "4",   # format-heavy (mind map + forecast, 2010→present) — zh
    "76",  # compound health (folded questions, entities) — en
    "41",  # comparison + top-ten (exact count + dimensions) — zh
    "90",  # compound legal (jurisdiction-sensitive) — en
    "77",  # narrow single-question — en
    "62",  # compound scientific (ion-trap scaling) — en
}


# ---------------------------------------------------------------------------
# OFFLINE deterministic compiler stub — derives a contract from S0 candidates
# ---------------------------------------------------------------------------

class _OfflineStubClient:
    """Deterministic, no-network compiler. Returns a contract built ONLY from the
    span-verified S0 candidates for the prompt (never inventing a hard term), then
    a minimal plan. Mimics a well-behaved compiler so the smoke exercises the real
    validation + autonomous-disclosure + hashing path.
    """

    def __init__(self, prompt: str) -> None:
        self._prompt = prompt
        self._candidates = reconcile_candidates(prompt)

    async def generate(self, prompt, system="", max_tokens=4096, temperature=0.0, **_):
        class _R:
            def __init__(self, c):
                self.content = c

        if system.startswith("You are the POLARIS Research Contract"):
            return _R(json.dumps(self._build_contract()))
        return _R(json.dumps(self._build_plan()))

    def _build_contract(self) -> dict:
        p = self._prompt
        objective = [{
            "term_id": "objective.question", "dimension": "objective.question",
            "value": p.strip(), "origin": "explicit", "force": "open",
            "spans": [{"start": 0, "end": len(p), "quote": p}],
        }]
        scope, coverage, assumptions = [], [], []
        n = 0
        for c in self._candidates:
            n += 1
            tid = f"scope.cand_{n}"
            # a candidate is span-verified iff it carries a verbatim prompt span
            span_ok = bool(c.spans) and all(
                p[s.start:s.end] == s.quote for s in c.spans
            )
            # HARD only when the deterministic source marked hard AND we have a
            # real span; else preference. (No invention.)
            force = "hard" if (c.force == "hard" and span_ok) else "preference"
            origin = "explicit" if span_ok else "inferred"
            spans = [{"start": s.start, "end": s.end, "quote": s.quote} for s in c.spans]
            term = {
                "term_id": tid, "dimension": c.dimension, "value": c.value,
                "origin": origin, "force": force, "spans": spans,
                "rationale": f"S0 candidate ({c.origin})",
            }
            if c.dimension.startswith("content"):
                coverage.append({
                    "requirement_id": tid, "kind": "topic",
                    "statement": term, "required": False,
                })
            else:
                scope.append(term)
            if origin in ("inferred", "policy_default"):
                assumptions.append({
                    "assumption_id": f"asm_{n}",
                    "statement": f"kept {c.dimension}={c.value!r} as open/preference "
                                 f"(no verbatim span to make it explicit)",
                    "affected_term_ids": [tid], "origin": "inferred",
                })
        return {"contract": {
            "objective": objective, "scope": scope, "coverage": coverage,
            "assumptions": assumptions, "complexity": "smoke",
        }}

    def _build_plan(self) -> dict:
        return {"plan": {"threads": [], "query_intents": [], "coverage_matrix": [],
                         "budget": {}, "stop_conditions": []}}


# ---------------------------------------------------------------------------
# Audit one prompt
# ---------------------------------------------------------------------------

def _audit_one(prompt_id: str, prompt: str, *, live: bool) -> dict:
    client = None if live else _OfflineStubClient(prompt)
    result = asyncio.run(run_research_planning_gate(
        prompt, mode="autonomous", client=client,
    ))
    contract = result.contract

    # PROPERTY 1: no invented hard constraint (deterministic validator clean of
    # the no-invention/span codes).
    errors = validate_contract(contract, prompt)
    invention_codes = {"hard_not_explicit", "explicit_without_span", "span_quote_mismatch"}
    invented = [e.to_dict() for e in errors if e.code in invention_codes]

    hard_terms = contract.hard_terms()
    bad_hard = [
        t.term_id for t in hard_terms
        if t.origin not in HARD_ELIGIBLE_ORIGINS
        or (t.origin == "explicit" and not any(s.matches_prompt(prompt) for s in t.spans))
    ]

    # PROPERTY 2: every inferred term with a value has an assumption record.
    disclosed = set()
    for a in contract.assumptions:
        disclosed.update(a.affected_term_ids)
    undisclosed = [
        t.term_id for t in contract.all_terms()
        if t.origin in DISCLOSURE_ORIGINS
        and t.value not in (None, "", [], {})
        and t.term_id
        and t.term_id not in disclosed
    ]

    # autonomous invariant
    autonomous_ok = (result.needs_input is False and result.state in ("auto_pinned", "unsatisfiable"))

    passed = not invented and not bad_hard and not undisclosed and autonomous_ok
    return {
        "id": prompt_id,
        "prompt_head": prompt[:60].replace("\n", " "),
        "state": result.state,
        "needs_input": result.needs_input,
        "n_terms": len(contract.all_terms()),
        "n_hard": len(hard_terms),
        "n_assumptions": len(contract.assumptions),
        "n_coverage": len(contract.coverage),
        "compiler_degraded": contract.compiler_degraded,
        "invented_hard": invented + [{"bad_hard_term": t} for t in bad_hard],
        "undisclosed_inferred": undisclosed,
        "autonomous_ok": autonomous_ok,
        "PASS": passed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="all 100 prompts (else the 8 smoke ids)")
    ap.add_argument("--live", action="store_true", help="use the real policy model (monitored job only)")
    args = ap.parse_args()

    rows = [json.loads(l) for l in _QUERY_JSONL.read_text().splitlines() if l.strip()]
    if not args.all:
        rows = [r for r in rows if str(r["id"]) in _SMOKE_IDS]

    results = [_audit_one(str(r["id"]), r["prompt"], live=args.live) for r in rows]

    n_pass = sum(1 for r in results if r["PASS"])
    print(json.dumps({
        "mode": "LIVE" if args.live else "OFFLINE_STUB",
        "n_prompts": len(results),
        "n_pass": n_pass,
        "n_fail": len(results) - n_pass,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
