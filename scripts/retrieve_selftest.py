#!/usr/bin/env python3
"""S1.b RETRIEVE offline self-test harness (Design 7 D1-D3, master §4 S1.b bar).

PURE LOGIC — no network, no GPU, no LLM, no live_retriever fetch. It drives the breadth resolver
and the scope-to-qgen / scope-to-backend seams from RunConfig + scope FIXTURES and asserts the
CONSTRUCTED query objects + backend request params, proving the five S1.b conditions:

  (a) the breadth resolver sizes query_budget / serper_k / s2_k / fetch_cap FROM RunConfig — a
      35+ query_count is HONORED, never capped to the legacy hardcode of 35;
  (b) scope => a SCOPE DIRECTIVES block is woven into the generated qgen prompts;
  (c) scope => Serper request params carry date / geo / language (tbs / gl / hl);
  (d) scope => S2 (year / publicationTypes) + OpenAlex (language / author) request params carry scope;
  (e) the FS-Researcher query METHOD is intact (TOC -> per-todo -> retrieve) AND no scope stated =>
      ZERO scope filters and ZERO directive block (fail-open).

Run:  python scripts/retrieve_selftest.py [--out <summary.json path>]
Exit 0 iff all five conditions pass. Prints summary.json (each condition: bool + evidence string).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "retrieve"

# The retrieval-budget env knobs the resolver treats as EXPLICIT overrides — cleared so the offline
# run reads the class rows deterministically (a stray slate value in the shell must not skew the test).
_BUDGET_ENV = [
    "PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "PG_SWEEP_MAX_SERPER", "PG_SWEEP_MAX_S2",
    "PG_SERPER_TOTAL_PER_QUERY", "PG_SWEEP_FETCH_CAP",
]
_SCOPE_ENV = [
    "PG_SCOPE_TO_QGEN", "PG_SERPER_SCOPE_FILTER", "PG_S2_SCOPE_FILTER", "PG_OPENALEX_SCOPE_FILTER",
    "PG_BREADTH_RESOLVER", "PG_EXPERT_FACET_PLANNER",
]


def _load_fixture(name: str) -> dict[str, Any]:
    with open(_FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _clean_env() -> None:
    for var in _BUDGET_ENV:
        os.environ.pop(var, None)


# ── (a) breadth resolver sizes from RunConfig, 35+ honored ────────────────────
def check_breadth_resolver() -> tuple[bool, str]:
    _clean_env()
    from src.polaris_graph.retrieval.breadth_resolver import resolve_breadth

    rc_explicit = _load_fixture("run_config_explicit_query_budget.json")
    rc_wide = _load_fixture("run_config_wide_class.json")

    plan60 = resolve_breadth("a broad market question", protocol={}, facets=None, run_config=rc_explicit)
    planw = resolve_breadth("give me a comprehensive review", protocol={}, facets=None, run_config=rc_wide)

    ok_explicit = (
        plan60.query_budget == 60           # honored verbatim from RunConfig
        and plan60.query_budget > 35        # NOT capped to the legacy hardcode
        and plan60.sources["query_budget"] == "runconfig"
        and plan60.serper_k == 12 and plan60.s2_k == 12 and plan60.fetch_cap == 300  # STANDARD class row
    )
    ok_wide = (
        planw.breadth_class == "WIDE"
        and planw.query_budget == 80 and planw.serper_k == 20 and planw.s2_k == 20
        and planw.serper_total == 100 and planw.fetch_cap == 740
        and planw.sources["query_budget"] == "runconfig_class"
    )
    ok = ok_explicit and ok_wide
    ev = (
        f"explicit RunConfig query_budget=60 -> resolved {plan60.query_budget} "
        f"(source={plan60.sources['query_budget']}, >35 honored={plan60.query_budget > 35}); "
        f"serper_k/s2_k/fetch_cap={plan60.serper_k}/{plan60.s2_k}/{plan60.fetch_cap} from STANDARD class. "
        f"WIDE class -> query_budget={planw.query_budget} serper_k={planw.serper_k} s2_k={planw.s2_k} "
        f"serper_total={planw.serper_total} fetch_cap={planw.fetch_cap} (source={planw.sources['query_budget']})."
    )
    return ok, ev


# ── shared stub llm / retrieve for the FS-method drive ────────────────────────
class _StubResult:
    def __init__(self) -> None:
        self.evidence_rows: list[Any] = []


def _make_capturing_llm(captured: list[str]):
    def _llm(prompt: str) -> str:
        captured.append(prompt)
        if "table of contents" in prompt:
            return "adoption trends\nregulatory landscape\nmarket impact"
        if "Self-review the knowledge base" in prompt:
            return "NONE"
        # per-todo query derivation
        return "example search query about the sub-topic"
    return _llm


def _stub_retrieve(*, research_question: str, **_kw: Any) -> _StubResult:
    return _StubResult()


# ── (b) SCOPE DIRECTIVES woven into the qgen prompts ──────────────────────────
def check_scope_in_qgen() -> tuple[bool, str]:
    _clean_env()
    os.environ["PG_SCOPE_TO_QGEN"] = "1"
    os.environ.pop("PG_EXPERT_FACET_PLANNER", None)  # legacy TOC path (capturable prompts)
    from src.polaris_graph.retrieval.fs_researcher_query_gen import plan_fs_researcher_queries
    from src.polaris_graph.retrieval.scope_directives import SCOPE_DIRECTIVES_HEADER

    scope = _load_fixture("scope_dated_geo_lang.json")
    captured: list[str] = []
    queries, _results = plan_fs_researcher_queries(
        "impact of AI on the labor market", _make_capturing_llm(captured), _stub_retrieve,
        max_queries=4, scope=scope,
    )
    with_block = [p for p in captured if SCOPE_DIRECTIVES_HEADER in p]
    # The block must reach the TOC prompt AND at least one per-todo derivation prompt.
    toc_has = any("table of contents" in p and SCOPE_DIRECTIVES_HEADER in p for p in captured)
    todo_has = any("Write ONE" in p and SCOPE_DIRECTIVES_HEADER in p for p in captured)
    # And it must actually carry the parsed scope terms.
    carries_terms = any(("2023-06" in p and "de" in p.lower()) for p in with_block)
    ok = bool(queries) and toc_has and todo_has and carries_terms
    ev = (
        f"{len(with_block)}/{len(captured)} qgen prompts carry '{SCOPE_DIRECTIVES_HEADER[:24]}...'; "
        f"TOC_has_block={toc_has} per_todo_has_block={todo_has} carries_window+lang={carries_terms}; "
        f"issued {len(queries)} queries."
    )
    os.environ.pop("PG_SCOPE_TO_QGEN", None)
    return ok, ev


# ── (c) Serper params carry date/geo/lang (tbs/gl/hl) ─────────────────────────
def check_serper_scope() -> tuple[bool, str]:
    _clean_env()
    os.environ["PG_SERPER_SCOPE_FILTER"] = "1"
    from src.polaris_graph.retrieval.scope_search_lanes import build_serper_scope_params

    scope = _load_fixture("scope_dated_geo_lang.json")
    params = build_serper_scope_params(scope)
    ok = (
        isinstance(params.get("tbs"), str) and params["tbs"].startswith("cdr:1")
        and "cd_min:" in params["tbs"] and "cd_max:" in params["tbs"]
        and params.get("gl") == "eu" and params.get("hl") == "de"
    )
    ev = f"Serper scoped params = {json.dumps(params, sort_keys=True)}"
    os.environ.pop("PG_SERPER_SCOPE_FILTER", None)
    return ok, ev


# ── (d) S2 (year/publicationTypes) + OpenAlex (language/author) carry scope ───
def check_s2_openalex_scope() -> tuple[bool, str]:
    _clean_env()
    os.environ["PG_S2_SCOPE_FILTER"] = "1"
    os.environ["PG_OPENALEX_SCOPE_FILTER"] = "1"
    from src.polaris_graph.retrieval.scope_search_lanes import (
        build_s2_scope_params, build_openalex_scope_params,
    )

    scope = _load_fixture("scope_dated_geo_lang.json")
    s2 = build_s2_scope_params(scope)
    oa = build_openalex_scope_params(scope)
    ok_s2 = s2.get("year") == "2019-2023" and s2.get("publicationTypes") == "JournalArticle"
    ok_oa = oa.get("language") == "de" and oa.get("authors") == ["Jane Doe"]
    ok = ok_s2 and ok_oa
    ev = (
        f"S2 scoped params = {json.dumps(s2, sort_keys=True)}; "
        f"OpenAlex scoped params = {json.dumps(oa, sort_keys=True)}"
    )
    os.environ.pop("PG_S2_SCOPE_FILTER", None)
    os.environ.pop("PG_OPENALEX_SCOPE_FILTER", None)
    return ok, ev


# ── (e) FS-Researcher method intact AND no-scope => zero scope filters ────────
def check_fs_method_and_failopen() -> tuple[bool, str]:
    _clean_env()
    os.environ.pop("PG_EXPERT_FACET_PLANNER", None)
    from src.polaris_graph.retrieval.fs_researcher_query_gen import plan_fs_researcher_queries
    from src.polaris_graph.retrieval.scope_directives import (
        SCOPE_DIRECTIVES_HEADER, append_scope_directives,
    )
    from src.polaris_graph.retrieval.scope_search_lanes import (
        build_serper_scope_params, build_s2_scope_params, build_openalex_scope_params,
    )

    # FS METHOD INTACT: with NO scope threaded, the loop still deconstructs (TOC) -> per-todo ->
    # retrieve, issuing queries and calling the injected retriever. This is byte-identical to today.
    retrieve_calls: list[str] = []

    def _counting_retrieve(*, research_question: str, **_kw: Any) -> _StubResult:
        retrieve_calls.append(research_question)
        return _StubResult()

    captured: list[str] = []
    queries, _results = plan_fs_researcher_queries(
        "impact of AI on the labor market", _make_capturing_llm(captured), _counting_retrieve,
        max_queries=4, scope=None,
    )
    method_intact = (
        len(queries) >= 1                                   # queries issued
        and len(retrieve_calls) == len(queries)             # each query retrieved (method fired)
        and any("table of contents" in p for p in captured)  # TOC deconstruction ran
        and not any(SCOPE_DIRECTIVES_HEADER in p for p in captured)  # no scope => no block leaked
    )

    # FAIL-OPEN: empty scope + EVERY scope flag ON => still zero scoped params + zero directive block.
    os.environ["PG_SCOPE_TO_QGEN"] = "1"
    os.environ["PG_SERPER_SCOPE_FILTER"] = "1"
    os.environ["PG_S2_SCOPE_FILTER"] = "1"
    os.environ["PG_OPENALEX_SCOPE_FILTER"] = "1"
    empty_scope = _load_fixture("scope_empty.json")
    serper = build_serper_scope_params(empty_scope)
    s2 = build_s2_scope_params(empty_scope)
    oa = build_openalex_scope_params(empty_scope)
    prompt = "Deconstruct this research topic. One sub-topic per line.\n\nsome question"
    appended = append_scope_directives(prompt, empty_scope)
    failopen = (
        serper == {} and s2 == {} and oa == {}
        and appended == prompt and SCOPE_DIRECTIVES_HEADER not in appended
    )
    for var in ("PG_SCOPE_TO_QGEN", "PG_SERPER_SCOPE_FILTER", "PG_S2_SCOPE_FILTER", "PG_OPENALEX_SCOPE_FILTER"):
        os.environ.pop(var, None)

    ok = method_intact and failopen
    ev = (
        f"FS method: issued {len(queries)} queries, {len(retrieve_calls)} retrieve calls, TOC ran, "
        f"no scope block leaked (intact={method_intact}). Fail-open (empty scope, all flags ON): "
        f"serper={serper} s2={s2} openalex={oa} directive_block_appended={appended != prompt} "
        f"(zero_filters={failopen})."
    )
    return ok, ev


def main() -> int:
    ap = argparse.ArgumentParser(description="S1.b RETRIEVE offline self-test")
    ap.add_argument("--out", default=str(_REPO_ROOT / "outputs" / "retrieve_selftest" / "summary.json"))
    args = ap.parse_args()

    checks = [
        ("a_breadth_resolver_sizes_from_runconfig", check_breadth_resolver),
        ("b_scope_directives_in_qgen_prompts", check_scope_in_qgen),
        ("c_serper_params_date_geo_lang", check_serper_scope),
        ("d_s2_openalex_params_carry_scope", check_s2_openalex_scope),
        ("e_fs_method_intact_and_failopen", check_fs_method_and_failopen),
    ]

    results: dict[str, Any] = {}
    all_pass = True
    for key, fn in checks:
        try:
            ok, ev = fn()
        except Exception as exc:  # noqa: BLE001 — a raised check is a FAIL (fail-loud, LAW II)
            ok, ev = False, f"EXCEPTION: {type(exc).__name__}: {exc}"
        results[key] = {"pass": bool(ok), "evidence": ev}
        all_pass = all_pass and bool(ok)

    summary = {"all_pass": all_pass, "conditions": results}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\n[retrieve_selftest] summary.json -> {out_path}")
    print(f"[retrieve_selftest] ALL_PASS={all_pass}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
