"""S1.b RETRIEVE offline probe harness (Design 7 §3 hamster loop — OFFLINE half).

Runs the breadth resolver + the scope->wording block + the three scope->backend param builders
over a fixed 6-question probe slate (2 NARROW / 2 STANDARD / 2 WIDE, including one dated, one
geo-scoped, one non-English) and prints, LINE BY LINE, exactly what each probe resolves to:

  * the sized BreadthPlan (class + every knob + its provenance),
  * the SCOPE DIRECTIVES block the qgen prompts would carry,
  * the ADDITIVE Serper / S2 / OpenAlex scoped-lane params.

This is the OFFLINE, no-network form of the Design 7 §3 lock-down loop — it proves the RESOLVER +
BUILDER contract deterministically. The LIVE search-only form (issuing real Serper / S2 / OpenAlex
and reading the request logs for union proof) is the VM hamster (see the small/full test commands
in the section handoff). Dates + language are parsed by the REAL deterministic
``extract_constraints_regex`` (regex, no network); geo / source-type / named-author scope is
supplied as the protocol.json ``scope_constraints`` dict shape the scope gate writes.

Usage:
    python scripts/dr_benchmark/breadth_scope_probe_harness.py
    python scripts/dr_benchmark/breadth_scope_probe_harness.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.retrieval import breadth_resolver as br  # noqa: E402
from src.polaris_graph.retrieval import scope_directives as sd  # noqa: E402
from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: E402
    extract_constraints_regex,
)


class _RunConfig:
    """Duck-typed RunConfig stand-in (WAVE-0 run_config.py not built yet): ``.get(knob_id)`` returns
    the probe's requested breadth_class so the resolver exercises the RunConfig precedence path."""

    def __init__(self, breadth_class: str | None):
        self._breadth_class = breadth_class

    def get(self, knob_id: str):
        if knob_id == "breadth_class" and self._breadth_class:
            return self._breadth_class
        return None


def _facet(facet_id: str, dimension: str, op: str = "prefer") -> dict:
    return {"facet_id": facet_id, "dimension": dimension, "op": op,
            "strictness": "weight", "trigger_span": "", "source": "regex"}


# 6-question probe slate. `scope_facets` / `named_include` are the protocol.json scope_constraints
# dict shape; dates + language are parsed live from the question by extract_constraints_regex.
_PROBES: list[dict] = [
    {"id": "narrow_single_drug", "class": "NARROW",
     "q": "What is the recommended maintenance dose of tirzepatide for type 2 diabetes?",
     "scope_facets": [], "named_include": []},
    {"id": "narrow_quick_overview", "class": "NARROW",
     "q": "Give a brief overview of metformin's mechanism of action.",
     "scope_facets": [], "named_include": []},
    {"id": "standard_dated", "class": "STANDARD",
     "q": "Summarize randomized trials of SGLT2 inhibitors in heart failure, sources from 2019 "
          "published before June 2023.",
     "scope_facets": [], "named_include": []},
    {"id": "standard_geo", "class": "STANDARD",
     "q": "What do United States peer-reviewed journals report on semaglutide cardiovascular "
          "outcomes?",
     "scope_facets": [_facet("jurisdiction:US", "geography", op="include"),
                      _facet("peer_reviewed_journal", "source_type", op="prefer")],
     "named_include": []},
    {"id": "wide_exhaustive", "class": "WIDE",
     "q": "Provide a comprehensive, exhaustive global review of all available evidence on GLP-1 "
          "receptor agonists across every indication.",
     "scope_facets": [], "named_include": []},
    {"id": "wide_non_english", "class": "WIDE",
     "q": "Comprehensive French-language review of all available evidence on DPP-4 inhibitor "
          "efficacy.",
     "scope_facets": [], "named_include": []},
]


def _resolve_probe(probe: dict) -> dict:
    uc = extract_constraints_regex(probe["q"]).to_dict()
    sc = {"facets": probe["scope_facets"], "named_include": probe["named_include"],
          "named_exclude": [], "source": "regex"}
    protocol = {"user_constraints": uc, "scope_constraints": sc}
    plan = br.resolve_breadth(probe["q"], protocol=protocol, facets=None,
                              run_config=_RunConfig(probe["class"]))
    return {
        "id": probe["id"],
        "requested_class": probe["class"],
        "question": probe["q"],
        "breadth_plan": plan.to_dict(),
        "scope_block": sd.scope_directives_block(uc, sc),
        "serper_scope_params": sd.serper_scope_params(uc, sc),
        "s2_scope_params": sd.s2_scope_params(uc, sc),
        "openalex_scope_params": sd.openalex_scope_params(uc, sc),
    }


def _print_human(rows: list[dict]) -> None:
    for r in rows:
        plan = r["breadth_plan"]
        print("=" * 88)
        print(f"PROBE {r['id']}  (requested class: {r['requested_class']})")
        print(f"  Q: {r['question']}")
        print(f"  BREADTH class={plan['breadth_class']} (source={plan['class_source']})")
        print(f"    query_budget={plan['query_budget']} serper_k={plan['serper_k']} "
              f"s2_k={plan['s2_k']} fetch_cap={plan['fetch_cap']} "
              f"serper_total={plan['serper_total']}")
        print(f"    rationale: {plan['rationale']}")
        block = r["scope_block"] or "(none — no scope directives)"
        print("  SCOPE DIRECTIVES block:")
        for line in block.splitlines():
            print(f"    | {line}")
        print(f"  SERPER scope params : {r['serper_scope_params'] or '(none)'}")
        print(f"  S2 scope params     : {r['s2_scope_params'] or '(none)'}")
        print(f"  OPENALEX scope params: {r['openalex_scope_params'] or '(none)'}")
    print("=" * 88)
    print(f"Resolved {len(rows)} probes (offline; live union-firing is the VM hamster).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    rows = [_resolve_probe(p) for p in _PROBES]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        _print_human(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
