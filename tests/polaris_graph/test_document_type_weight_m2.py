"""I-deepfix-001 M2 — isolated OFFLINE test (no paid API, no GPU, no network).

Covers the per-citation document-type WEIGHT-and-DISCLOSE path against the REAL banked
drb_72 artifacts:
  1. ``classify_document_type`` truth-table on the real drb_72 wrong-genre offenders.
  2. ``build_corpus_credibility_disclosure`` replay over the real 64-row ``per_source``:
     len/url-set conserved (KEEP-not-DROP), raw ``credibility_weight``/``weight_basis``
     BYTE-IDENTICAL to the banked file (M2 does not touch the credibility axis), the 4 new
     genre fields appear ON, the adjusted mean is a SEPARATE second mean, and OFF is
     byte-identical (no M2 keys serialized).
  3. Corroboration re-rank over the real ``bibliography.json``: the predatory ``ewadirect``
     venue no longer sorts first under the document-type-adjusted weight AND is still present.
  4. ``resolve_document_type_weight`` honors lower-case YAML overrides; garbage env is ignored.

Run directly:  python tests/polaris_graph/test_document_type_weight_m2.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.nodes.weighted_corpus_gate import (  # noqa: E402
    build_corpus_credibility_disclosure,
    disclosure_to_dict,
    _tier_prior,
)
from src.polaris_graph.retrieval.document_type_classifier import (  # noqa: E402
    DocumentType,
    classify_document_type,
    document_type_weighting_active,
    is_peer_reviewed_journal_article,
    resolve_document_type_weight,
)

_BANKED = Path(
    "C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/outputs/"
    "deepfix_safety_smoke/workforce/drb_72_ai_labor"
)

_PROTOCOL = {  # synthetic journal-only protocol mirroring config/scope_templates/workforce.yaml
    "document_type_preference": "journal_article",
    "document_type_weights": {
        "journal_article": 1.0, "review_article": 1.0, "preprint": 0.7,
        "report": 0.5, "book": 0.5, "blog_commentary": 0.3,
        "predatory_oa_journal": 0.25, "unknown": 0.5,
    },
}


def _load(name: str):
    return json.loads((_BANKED / name).read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. classify_document_type truth table on the real drb_72 offenders.
# ─────────────────────────────────────────────────────────────────────────────
def test_classify_truth_table() -> list[str]:
    fails: list[str] = []
    cases = [
        # (kwargs, expected DocumentType, expected is_journal_article)
        (dict(url="https://arxiv.org/pdf/2011.03044"), DocumentType.PREPRINT, False),
        (dict(url="https://www.amazon.com/Artificial-Intelligence-Fourth-Industrial-Revolution/dp/X"),
         DocumentType.BOOK, False),
        (dict(url="https://www.weforum.org/stories/2026/01/ai-has-already-added-jobs"),
         DocumentType.REPORT, False),
        (dict(url="https://its.uri.edu/2025/08/07/a-new-industrial-revolution-ai"),
         DocumentType.BLOG_COMMENTARY, False),
        (dict(url="https://etm.wsu.edu/2023/08/30/the-fourth-industrial-revolution/"),
         DocumentType.BLOG_COMMENTARY, False),
        (dict(url="https://labourdiscovery.ilo.org/discovery/fulldisplay?docid=alma123"),
         DocumentType.REPORT, False),
        (dict(url="https://www.researchgate.net/publication/385880711_Theorizing_Labor"),
         DocumentType.PREPRINT, False),
        # predatory OA proceedings venue that LED the corroborated findings
        (dict(url="https://www.ewadirect.com/proceedings/ace/article/view/16842/pdf",
              openalex_publication_type="article", predatory_oa=True),
         DocumentType.PREDATORY_OA_JOURNAL, False),
        # genuine peer-reviewed journal articles (source_type==journal AND peer-reviewed)
        (dict(url="https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3",
              openalex_publication_type="article", openalex_source_type="journal",
              openalex_is_peer_reviewed=True),
         DocumentType.JOURNAL_ARTICLE, True),
        (dict(url="https://onlinelibrary.wiley.com/doi/10.1155/hbe2/3424335",
              openalex_publication_type="article", openalex_source_type="journal",
              openalex_is_peer_reviewed=True),
         DocumentType.JOURNAL_ARTICLE, True),
        # peer-reviewed REVIEW article
        (dict(openalex_publication_type="review", openalex_source_type="journal",
              openalex_is_peer_reviewed=True, url="https://example.org/x"),
         DocumentType.REVIEW_ARTICLE, True),
        # OpenAlex over-marks "article" but NO journal/peer-review => must NOT be journal-positive
        (dict(openalex_publication_type="article", url="https://some-unknown-host.example/x"),
         DocumentType.UNKNOWN, False),
    ]
    for kwargs, exp_dt, exp_journal in cases:
        dt, basis = classify_document_type(**kwargs)
        if dt is not exp_dt:
            fails.append(f"classify {kwargs.get('url','')[:48]!r} -> {dt} (basis={basis}); expected {exp_dt}")
        if is_peer_reviewed_journal_article(dt) is not exp_journal:
            fails.append(f"is_journal_article {kwargs.get('url','')[:48]!r} -> "
                         f"{is_peer_reviewed_journal_article(dt)}; expected {exp_journal}")
    return fails


# ─────────────────────────────────────────────────────────────────────────────
# Stub CorpusSource reconstructed from a banked per_source row (deterministically
# reproduces the banked credibility_weight/weight_basis: seed authority_score for the
# authority_score-basis rows; leave None for tier_prior rows so the builder recomputes
# the same per-tier prior — verified 0/64 mismatch).
# ─────────────────────────────────────────────────────────────────────────────
class _StubSource:
    def __init__(self, row: dict, document_type: str | None = None):
        self.url = row["url"]
        self.tier = row["tier"]
        self.domain = row.get("domain", "")
        self.title = ""
        self.authority_score = (
            row["credibility_weight"] if row["weight_basis"] == "authority_score" else None
        )
        if document_type is not None:
            self.document_type = document_type


def _build(srcs, banked, *, protocol=None):
    return build_corpus_credibility_disclosure(
        classified_sources=srcs,
        tier_counts=banked["tier_counts"],
        tier_fractions=banked["tier_fractions"],
        total_sources=banked["total_sources"],
        had_material_deviation=banked["had_material_deviation"],
        domain=banked["domain"],
        research_question=banked["research_question"],
        protocol=protocol,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. build_corpus_credibility_disclosure replay over the real 64-row per_source.
# ─────────────────────────────────────────────────────────────────────────────
def test_disclosure_replay() -> list[str]:
    fails: list[str] = []
    banked = _load("corpus_credibility_disclosure.json")
    ps = banked["per_source"]
    # tag ONE row's carried-through document_type to exercise the journal 1.0 + carry-through leg
    journal_idx = next((i for i, r in enumerate(ps) if "sagepub" in r["url"]), 0)
    srcs = [
        _StubSource(r, document_type="JOURNAL_ARTICLE" if i == journal_idx else None)
        for i, r in enumerate(ps)
    ]

    # --- OFF (no flag): byte-identical to HEAD ---
    os.environ.pop("PG_DOCUMENT_TYPE_WEIGHT", None)
    off = disclosure_to_dict(_build(srcs, banked, protocol=_PROTOCOL))  # flag unset => inactive
    if len(off["per_source"]) != 64:
        fails.append(f"OFF len(per_source)={len(off['per_source'])} != 64")
    off_keys = sorted(off["per_source"][0].keys())
    if off_keys != ["credibility_weight", "domain", "tier", "url", "weight_basis"]:
        fails.append(f"OFF per_source row leaked M2 keys: {off_keys}")
    for k in ("document_type_adjusted_mean", "document_type_preference_active"):
        if k in off:
            fails.append(f"OFF disclosure leaked top-level M2 key {k!r}")
    # OFF credibility_weight/weight_basis byte-identical to the banked file
    for orig, new in zip(ps, off["per_source"]):
        if abs(orig["credibility_weight"] - new["credibility_weight"]) > 1e-9:
            fails.append(f"OFF credibility_weight drift {orig['url'][:40]}")
        if orig["weight_basis"] != new["weight_basis"]:
            fails.append(f"OFF weight_basis drift {orig['url'][:40]}")

    # --- ON (flag + active protocol) ---
    os.environ["PG_DOCUMENT_TYPE_WEIGHT"] = "1"
    try:
        if not document_type_weighting_active(_PROTOCOL):
            fails.append("document_type_weighting_active should be True under flag+protocol")
        on = disclosure_to_dict(_build(srcs, banked, protocol=_PROTOCOL))
    finally:
        os.environ.pop("PG_DOCUMENT_TYPE_WEIGHT", None)

    # (a) KEEP-not-DROP: len + url set conserved
    if len(on["per_source"]) != 64:
        fails.append(f"ON len(per_source)={len(on['per_source'])} != 64 (DROP!)")
    if {r["url"] for r in on["per_source"]} != {r["url"] for r in ps}:
        fails.append("ON url set changed (a source vanished)")
    # (d) raw credibility axis BYTE-IDENTICAL to the banked file (M2 does not touch it)
    for orig, new in zip(ps, on["per_source"]):
        if abs(orig["credibility_weight"] - new["credibility_weight"]) > 1e-9:
            fails.append(f"ON credibility_weight drift {orig['url'][:40]}: "
                         f"{orig['credibility_weight']} -> {new['credibility_weight']}")
        if orig["weight_basis"] != new["weight_basis"]:
            fails.append(f"ON weight_basis drift {orig['url'][:40]}")
    if abs(on["weighted_credibility_mean"] - banked["weighted_credibility_mean"]) > 1e-9:
        fails.append("ON weighted_credibility_mean changed (M2 must NOT touch it)")
    # (b) every ON row gained the 4 new fields
    for r in on["per_source"]:
        for k in ("document_type", "is_journal_article",
                  "document_type_weight", "document_type_adjusted_weight"):
            if k not in r or r[k] is None:
                fails.append(f"ON row {r['url'][:40]} missing M2 field {k!r}")
                break
    by_url = {r["url"]: r for r in on["per_source"]}
    # (c) journal row keeps 1.0; report/blog/preprint/book/predatory carry reduced multiplier
    jr = on["per_source"][journal_idx]
    if jr["document_type"] != "JOURNAL_ARTICLE" or abs(jr["document_type_weight"] - 1.0) > 1e-9:
        fails.append(f"carried-through JOURNAL_ARTICLE row weight={jr.get('document_type_weight')} != 1.0")
    if jr["is_journal_article"] is not True:
        fails.append("carried-through journal row is_journal_article != True")
    expect_mult = {
        "https://arxiv.org/pdf/2011.03044": 0.7,  # PREPRINT
        "https://www.weforum.org/stories/2026/01/ai-has-already-added-1-3-million-new-j": None,
    }
    # check a few real offenders by prefix match
    def _row_for(prefix):
        return next((r for u, r in by_url.items() if u.startswith(prefix)), None)
    for prefix, dt_exp, mult_exp in [
        ("https://arxiv.org/pdf/2011.03044", "PREPRINT", 0.7),
        ("https://www.amazon.com/", "BOOK", 0.5),
        ("https://www.weforum.org/stories", "REPORT", 0.5),
        ("https://etm.wsu.edu/", "BLOG_COMMENTARY", 0.3),
        ("https://its.uri.edu/", "BLOG_COMMENTARY", 0.3),
    ]:
        r = _row_for(prefix)
        if r is None:
            fails.append(f"expected offender {prefix} not in disclosure")
            continue
        if r["document_type"] != dt_exp:
            fails.append(f"{prefix} document_type={r['document_type']} != {dt_exp}")
        if abs(r["document_type_weight"] - mult_exp) > 1e-9:
            fails.append(f"{prefix} document_type_weight={r['document_type_weight']} != {mult_exp}")
        if r["document_type_weight"] >= 1.0:
            fails.append(f"{prefix} non-journal carries full weight {r['document_type_weight']}")
    # ewadirect (the predatory venue that LED the corroborated findings) is KEPT in the corpus
    # disclosure (KEEP-not-DROP) and its document-type-adjusted weight falls BELOW the journal row.
    ewa = next((r for r in on["per_source"] if "ewadirect" in r["url"]), None)
    if ewa is None:
        fails.append("ewadirect dropped from the corpus disclosure (must be KEPT)")
    else:
        if abs(ewa["credibility_weight"] - 0.6) > 1e-9:
            fails.append(f"ewadirect raw credibility_weight changed: {ewa['credibility_weight']}")
        if not (ewa["document_type_adjusted_weight"] < jr["document_type_adjusted_weight"]):
            fails.append("ewadirect adjusted weight not below the journal row (re-rank would not demote it)")
    # (e) the adjusted mean is a SEPARATE, lower second mean
    if on.get("document_type_preference_active") is not True:
        fails.append("ON document_type_preference_active != True")
    adj = on.get("document_type_adjusted_mean")
    if not isinstance(adj, (int, float)):
        fails.append(f"ON document_type_adjusted_mean missing/non-numeric: {adj!r}")
    elif not (adj < on["weighted_credibility_mean"]):
        fails.append(f"adjusted_mean {adj} should be < weighted_mean {on['weighted_credibility_mean']}")
    return fails


# ─────────────────────────────────────────────────────────────────────────────
# 3. Corroboration re-rank over the real bibliography.json (mirrors _m2_bib_genre).
# ─────────────────────────────────────────────────────────────────────────────
def _adjusted(b: dict) -> float:
    dt, _ = classify_document_type(url=str(b.get("url") or ""),
                                   title=str(b.get("statement") or ""))
    return _tier_prior(str(b.get("tier") or "")) * resolve_document_type_weight(dt, _PROTOCOL)


def test_corroboration_rerank() -> list[str]:
    """The predatory ``ewadirect`` venue is a basket MEMBER, not a numbered bibliography row,
    so its demotion is asserted at the disclosure layer (test_disclosure_replay). Here we prove
    the bibliography re-rank itself: KEEP-not-DROP conservation + a real non-journal-below-journal
    ordering, mirroring scripts/run_honest_sweep_r3.py:_m2_bib_genre."""
    fails: list[str] = []
    biblio = _load("bibliography.json")
    ranked = sorted(biblio, key=lambda b: -_adjusted(b))
    # conservation: nothing dropped/added (routed display order, not a filter)
    if {str(b.get("num")) for b in ranked} != {str(b.get("num")) for b in biblio}:
        fails.append("re-rank changed the bibliography set (must be conserved)")
    if len(ranked) != len(biblio):
        fails.append("re-rank changed the bibliography length (must be conserved)")
    pos = {str(b.get("num")): i for i, b in enumerate(ranked)}
    # cognifit blog (#21, T6 BLOG_COMMENTARY) must sort BELOW the wiley journal-host T1 entry (#10)
    if "21" in pos and "10" in pos and not (pos["21"] > pos["10"]):
        fails.append("blog #21 did not sort below journal-host T1 #10 after re-rank")
    # monotonic non-increasing in the adjusted-weight key (sorted-by-construction sanity)
    adj_seq = [_adjusted(b) for b in ranked]
    if any(adj_seq[i] < adj_seq[i + 1] - 1e-12 for i in range(len(adj_seq) - 1)):
        fails.append("re-rank ordering is not monotonic in document-type-adjusted weight")
    return fails


# ─────────────────────────────────────────────────────────────────────────────
# 4. resolve_document_type_weight override handling.
# ─────────────────────────────────────────────────────────────────────────────
def test_resolve_weight() -> list[str]:
    fails: list[str] = []
    # lower-case YAML override keys must resolve against upper-case DocumentType.value
    proto = {"document_type_weights": {"preprint": 0.42, "journal_article": 0.9}}
    if abs(resolve_document_type_weight(DocumentType.PREPRINT, proto) - 0.42) > 1e-9:
        fails.append("lower-case YAML override 'preprint' not applied")
    if abs(resolve_document_type_weight(DocumentType.JOURNAL_ARTICLE, proto) - 0.9) > 1e-9:
        fails.append("lower-case YAML override 'journal_article' not applied")
    # absent override falls to the module default
    if abs(resolve_document_type_weight(DocumentType.BOOK, proto) - 0.5) > 1e-9:
        fails.append("default BOOK weight not 0.5")
    # garbage override value ignored -> module default
    if abs(resolve_document_type_weight(DocumentType.REPORT, {"document_type_weights": {"report": "x"}}) - 0.5) > 1e-9:
        fails.append("garbage override not ignored")
    # no protocol => default
    if abs(resolve_document_type_weight(DocumentType.UNKNOWN, None) - 0.5) > 1e-9:
        fails.append("None protocol default not 0.5")
    return fails


def main() -> int:
    all_fails: dict[str, list[str]] = {}
    for fn in (test_classify_truth_table, test_disclosure_replay,
               test_corroboration_rerank, test_resolve_weight):
        f = fn()
        all_fails[fn.__name__] = f
        status = "PASS" if not f else "FAIL"
        print(f"[{status}] {fn.__name__}  ({len(f)} failure(s))")
        for line in f:
            print(f"    - {line}")
    total = sum(len(v) for v in all_fails.values())
    print(f"\nTOTAL failures: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
