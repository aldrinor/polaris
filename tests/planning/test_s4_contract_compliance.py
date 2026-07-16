"""S4 contract-compliance audit tests — offline + deterministic, DISCLOSURE-ONLY.

Assert the S4 compliance acceptance (GATE_DESIGN_CONSOLIDATED §8 S4 / §6,
sol_gate_design §4 compliance row):

  * audit_contract on a saved report produces a TERM-LEVEL report
    (SATISFIED/FAILED/UNSATISFIABLE/UNKNOWN + owning stage);
  * required-section presence AND order are DETERMINISTIC;
  * counts / length / tables / citations are deterministic;
  * a hard retrieval-scope term on a prebuilt corpus is UNKNOWN (disclosed, never
    claimed satisfied) with retrieval_scope_status recorded;
  * semantic coverage is UNKNOWN without an injected judge, and uses the judge
    (never fabricating) when one is supplied;
  * the audit NEVER imports the frozen faithfulness engine and NEVER mutates the
    report (disclosure-only);
  * fail-open on a None / degraded contract.
"""

from __future__ import annotations

from src.polaris_graph.planning.planning_gate_schema import contract_from_dict
from src.polaris_graph.planning import contract_compliance as cc


PROMPT = (
    "Write a report on X with sections in order: Background, Findings, "
    "Recommendations. Cite English-language journal articles only. Include a "
    "comparison table. Provide the top ten items. Cover topic Alpha and topic Beta."
)


def _span(phrase: str) -> dict:
    i = PROMPT.find(phrase)
    assert i != -1, phrase
    return {"start": i, "end": i + len(phrase), "quote": phrase}


def _contract():
    return contract_from_dict({
        "scope": [
            {"term_id": "scope.lang", "dimension": "scope.source_languages",
             "value": "English", "origin": "explicit", "force": "hard",
             "spans": [_span("English-language")]},
            {"term_id": "scope.type", "dimension": "scope.source_types",
             "value": "journal", "origin": "explicit", "force": "hard",
             "spans": [_span("journal articles")]},
        ],
        "deliverable": [
            {"term_id": "deliverable.cite", "dimension": "deliverable.citation",
             "value": "required", "origin": "explicit", "force": "hard",
             "spans": [_span("Cite")]},
            {"term_id": "deliverable.tbl", "dimension": "deliverable.visual.table",
             "value": "comparison table", "origin": "explicit", "force": "hard",
             "spans": [_span("comparison table")]},
        ],
        "sections": [
            {"section_id": "s1", "order": 1,
             "title": {"term_id": "sec.bg", "dimension": "deliverable.section",
                       "value": "Background", "origin": "explicit", "force": "hard",
                       "spans": [_span("Background")]},
             "exact_title_lock": True},
            {"section_id": "s2", "order": 2,
             "title": {"term_id": "sec.fd", "dimension": "deliverable.section",
                       "value": "Findings", "origin": "explicit", "force": "hard",
                       "spans": [_span("Findings")]},
             "exact_title_lock": True},
            {"section_id": "s3", "order": 3,
             "title": {"term_id": "sec.rc", "dimension": "deliverable.section",
                       "value": "Recommendations", "origin": "explicit", "force": "hard",
                       "spans": [_span("Recommendations")]},
             "exact_title_lock": True},
        ],
        "coverage": [
            {"requirement_id": "cov.count", "kind": "topic", "required": True,
             "statement": {"term_id": "cov.count", "dimension": "content.count",
                           "value": "top ten items", "origin": "explicit",
                           "force": "hard", "spans": [_span("top ten")]}},
            {"requirement_id": "cov.alpha", "kind": "topic", "required": True,
             "statement": {"term_id": "cov.alpha", "dimension": "content.coverage",
                           "value": "topic Alpha", "origin": "explicit",
                           "force": "hard", "spans": [_span("topic Alpha")]}},
            {"requirement_id": "cov.beta", "kind": "topic", "required": True,
             "statement": {"term_id": "cov.beta", "dimension": "content.coverage",
                           "value": "topic Beta", "origin": "explicit",
                           "force": "hard", "spans": [_span("topic Beta")]}},
        ],
        "assumptions": [],
    })


GOOD_REPORT = """# Report on X

## Background

Some background prose about topic Alpha [1].

## Findings

Findings about topic Beta with a table.

| Item | Value |
|------|-------|
| a    | 1     |

1. first
2. second
3. third
4. fourth
5. fifth
6. sixth
7. seventh
8. eighth
9. ninth
10. tenth

## Recommendations

Recommendations prose [2].

## References
[1] Alpha source — http://a.example (tier T1)
[2] Beta source — http://b.example (tier T2)
"""


def _finding(audit, dim, term_id=None):
    for f in audit.findings:
        if f.dimension == dim and (term_id is None or f.term_id == term_id):
            return f
    return None


def test_term_level_report_shape():
    audit = cc.audit_contract(_contract(), GOOD_REPORT, contract_sha256="abc")
    d = audit.to_dict()
    assert d["retrieval_scope_status"] == "not_evaluated_prebuilt_corpus"
    assert d["contract_sha256"] == "abc"
    assert d["counts"], "counts must be populated"
    # every finding carries a status + owning stage + method.
    assert audit.findings
    for f in audit.findings:
        assert f.status in cc.STATUSES
        assert f.owning_stage in {"retrieval", "outline", "compose", "render", "audit"}
        assert f.method in {"deterministic", "judge", "not_evaluated"}


def test_required_sections_present_and_ordered_satisfied():
    audit = cc.audit_contract(_contract(), GOOD_REPORT)
    # each required section present.
    for tid in ("sec.bg", "sec.fd", "sec.rc"):
        f = _finding(audit, "deliverable.section", tid)
        assert f is not None and f.status == cc.SATISFIED, tid
    order = _finding(audit, "deliverable.section_order")
    assert order is not None and order.status == cc.SATISFIED
    assert order.owning_stage == "render" and order.method == "deterministic"


def test_section_order_violation_is_failed():
    # swap Findings and Background order in the produced report.
    scrambled = GOOD_REPORT.replace(
        "## Background", "## TMP").replace(
        "## Findings", "## Background").replace("## TMP", "## Findings")
    audit = cc.audit_contract(_contract(), scrambled)
    order = _finding(audit, "deliverable.section_order")
    assert order is not None and order.status == cc.FAILED


def test_missing_section_is_failed():
    dropped = GOOD_REPORT.replace("## Recommendations\n\nRecommendations prose [2].\n", "")
    audit = cc.audit_contract(_contract(), dropped)
    f = _finding(audit, "deliverable.section", "sec.rc")
    assert f is not None and f.status == cc.FAILED


def test_table_and_citation_deterministic():
    audit = cc.audit_contract(_contract(), GOOD_REPORT)
    tbl = _finding(audit, "deliverable.visual")
    assert tbl is not None and tbl.status == cc.SATISFIED
    cite = _finding(audit, "deliverable.citation")
    assert cite is not None and cite.status == cc.SATISFIED
    # no table present => FAILED.
    no_table = GOOD_REPORT.replace("| Item | Value |\n|------|-------|\n| a    | 1     |\n", "")
    a2 = cc.audit_contract(_contract(), no_table)
    assert _finding(a2, "deliverable.visual").status == cc.FAILED


def test_count_satisfied_when_enough_numbered_items():
    audit = cc.audit_contract(_contract(), GOOD_REPORT)
    f = _finding(audit, "content.count")
    assert f is not None and f.status == cc.SATISFIED
    assert f.owning_stage == "compose"


def test_retrieval_scope_hard_terms_unknown_on_prebuilt():
    audit = cc.audit_contract(_contract(), GOOD_REPORT)
    scope_findings = [f for f in audit.findings if f.owning_stage == "retrieval"]
    assert scope_findings, "hard scope terms must be disclosed"
    for f in scope_findings:
        assert f.status == cc.UNKNOWN
        assert f.method == "not_evaluated"
        assert "not_evaluated_prebuilt_corpus" in f.detail


def test_coverage_unknown_without_judge_but_judge_used_when_injected():
    # no judge => UNKNOWN (never fabricated as satisfied).
    audit = cc.audit_contract(_contract(), GOOD_REPORT)
    cov = [f for f in audit.findings if f.dimension == "content.coverage"]
    assert cov and all(f.status == cc.UNKNOWN for f in cov)

    # inject a judge that PASSES Alpha and FAILS Beta.
    def judge(topic, report):
        return "Alpha" in topic

    audit2 = cc.audit_contract(_contract(), GOOD_REPORT, coverage_judge=judge)
    by_id = {f.term_id: f for f in audit2.findings if f.dimension == "content.coverage"}
    assert by_id["cov.alpha"].status == cc.SATISFIED
    assert by_id["cov.alpha"].method == "judge"
    assert by_id["cov.beta"].status == cc.FAILED


def test_disclosure_only_never_mutates_report():
    report = GOOD_REPORT
    before = report
    cc.audit_contract(_contract(), report, coverage_judge=lambda t, r: True)
    assert report == before  # the string is unchanged (disclosure-only)


def test_failopen_none_contract():
    audit = cc.audit_contract(None, GOOD_REPORT)
    assert audit.findings == []
    assert audit.retrieval_scope_status == "not_evaluated_prebuilt_corpus"


def test_audit_module_does_not_import_faithfulness_engine():
    """The compliance audit must never IMPORT / CALL strict_verify or the
    provenance generator (mentioning them in a boundary docstring is fine)."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(cc))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", "") or getattr(fn, "attr", "")
            assert name != "strict_verify", "audit must not call strict_verify"
    assert not any("provenance_generator" in m for m in imported)
