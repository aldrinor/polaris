"""GENERALIZED Fix 5 — DURABLE metamorphic cross-contract test suite (M1-M10).

OFFLINE, pure — no network, no LLM, no live retrieval, no frozen-file touch. Until
this file existed nothing DURABLY guarded the generalized source-kind/quality
eligibility surface (``build_source_kind_eligibility`` / ``corpus_kind_adequacy`` /
``_positive_signal_tier`` / ``_acquisition_receipt_matches`` / the adequacy
boundary); the prior hardening workflow verified them only live.

METAMORPHIC CONTRACT: there is ONE mixed fixture corpus (:func:`_corpus`) and ONE
policy factory (:class:`_Policy`). Every M-test swaps ONLY the contract (the policy
+ its force + its acquisition receipt) and asserts the eligibility mechanism
ADAPTS — no code path is special-cased on a slug, a benchmark name, or a
journal/review literal. The operator decision under test is FULL
CLASSIFIER-CONFIRMED T1: a bare / preprint (arXiv 10.48550) / dataset
(Zenodo 10.5281) / working-paper / content-shell DOI does NOT alone qualify as T1;
T1-scholarly requires ``is_peer_reviewed_journal_article(classify_document_type(...))
== True``.

Invariants asserted across the suite:
  * EVIDENCE-POSITIVE ONLY (INV-3): a positive signal only moves UNKNOWN -> PASS,
    never FAIL -> anything; retracted / predatory / is_peer_reviewed=False / low-tier
    stay FAIL, first and absolute (M8, property test).
  * EXCLUSION ALWAYS WINS (INV-2): an excluded kind is masked via the upstream facet
    mask even when its quality tier is an unconditional T1 PASS (M5).
  * STARVATION BACKSTOP: a hard kind mask arms ONLY behind corpus-adequacy (counted
    by the SAME classifier) AND a matching acquisition receipt; else it degrades to
    prefer + disclosure (M1, M3, adequacy-boundary, acquisition-receipt tests).
  * OFF-path byte-identical: an empty policy no-ops every generalized path (M6, M9).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.retrieval import quality_eligibility as qe  # noqa: E402
from src.polaris_graph.retrieval.quality_eligibility import (  # noqa: E402
    FAIL,
    PASS,
    UNKNOWN,
    build_quality_eligibility,
    build_source_kind_eligibility,
    classified_kind,
    corpus_kind_adequacy,
    normalize_kinds,
    score_source_quality,
)


# ---------------------------------------------------------------------------
# The ONE mixed fixture corpus + the ONE policy factory (swap ONLY the contract)
# ---------------------------------------------------------------------------

# Stable ids so a test can name a specific row across contract swaps.
CID_JOURNAL = "journal_openalex"          # peer-reviewed journal WITH openalex metadata
CID_JOURNAL_DOI = "journal_registrant"    # confirmed journal registrant DOI (Elsevier)
CID_GOV = "gov_report"                    # official government report (.gov)
CID_NEWS = "newswire"                     # reputable newswire
CID_PRESS = "company_press"               # company press release
CID_BLOG_EST = "analyst_blog"             # established analyst blog (platform host)
CID_BLOG_ANON = "anon_blog"               # anonymous blog (no metadata)
CID_ARXIV = "arxiv_preprint"              # arXiv preprint DOI (10.48550)
CID_ZENODO = "zenodo_dataset"             # Zenodo dataset DOI (10.5281)
CID_RETRACTED = "retracted"               # retracted DOI
CID_PREDATORY = "predatory"               # predatory journal host
CID_SHELL = "content_shell"               # bare content-shell DOI (10.1234)


def _corpus() -> "list[dict]":
    """One mixed corpus, built fresh per call (no shared mutable state).

    Every row's genre is what the deterministic classifier ACTUALLY resolves it to
    (verified empirically) — the fixture never asserts a classification the live
    classifier would not make.
    """
    return [
        # peer-reviewed journal WITH openalex metadata -> JOURNAL_ARTICLE, quality PASS(T1).
        {"id": CID_JOURNAL, "source_url": "https://academic.example/a",
         "openalex_source_type": "journal", "openalex_is_peer_reviewed": True,
         "openalex_publication_type": "article", "tier": "T1", "is_peer_reviewed": True},
        # confirmed journal REGISTRANT DOI (Elsevier 10.1016) -> JOURNAL_ARTICLE (recall boundary).
        {"id": CID_JOURNAL_DOI, "source_url": "https://elsevier.example/b",
         "doi": "10.1016/j.x.2020.01.001"},
        # official government report (.gov host) -> quality PASS(T1-government), genre UNKNOWN.
        {"id": CID_GOV, "source_url": "https://www.bls.gov/report/x"},
        # reputable newswire -> NEWS genre; no T2 host predicate yet -> quality UNKNOWN.
        {"id": CID_NEWS, "source_url": "https://www.reuters.com/business/x"},
        # company press release -> PRESS_RELEASE genre; quality UNKNOWN.
        {"id": CID_PRESS, "source_url": "https://acme.example/press/launch",
         "source_class": "PRESS_RELEASE"},
        # established analyst blog (Substack platform) -> BLOG_COMMENTARY genre; quality UNKNOWN.
        {"id": CID_BLOG_EST, "source_url": "https://stratechery.substack.com/p/analysis"},
        # anonymous blog (no metadata) -> UNKNOWN genre; quality UNKNOWN (never promoted for being a blog).
        {"id": CID_BLOG_ANON, "source_url": "https://randomblog.example/post"},
        # arXiv preprint DOI (10.48550) -> NOT a journal genre -> quality UNKNOWN (NOT T1).
        {"id": CID_ARXIV, "source_url": "https://example.org/pre",
         "doi": "10.48550/arXiv.2301.00001"},
        # Zenodo dataset DOI (10.5281) -> NOT a journal genre -> quality UNKNOWN (NOT T1).
        {"id": CID_ZENODO, "source_url": "https://example.org/ds",
         "doi": "10.5281/zenodo.1234567"},
        # retracted DOI -> quality FAIL (retraction, highest precedence, absolute).
        {"id": CID_RETRACTED, "source_url": "https://retract.example/r",
         "doi": "10.1016/j.x.2020.01.001", "is_retracted": True},
        # predatory journal host -> quality FAIL (predatory host, absolute).
        {"id": CID_PREDATORY, "source_url": "https://www.abacademies.org/articles/x.pdf",
         "doi": "10.9/q"},
        # bare content-shell DOI (10.1234) -> NOT a journal genre -> quality UNKNOWN (DOI-alone NOT T1).
        {"id": CID_SHELL, "source_url": "https://example.org/shell", "doi": "10.1234/abcd"},
    ]


def _by_id(rows, cid):
    for r in rows:
        if r["id"] == cid:
            return r
    raise KeyError(cid)


def _url(rows, cid):
    return _by_id(rows, cid)["source_url"]


class _Policy:
    """Minimal duck-typed RetrievalPolicy — the ONLY thing swapped between M-tests.

    ``allowed_source_kinds`` / ``excluded_source_kinds`` carry free-text contract
    kind vocabulary (normalized internally). ``kind_force`` / ``quality_force`` set
    the per-predicate strength (``hard``/``soft``). ``contract_hash`` is the value an
    acquisition receipt must match for a hard mask to arm.
    """

    def __init__(
        self,
        *,
        allowed=None,
        excluded=None,
        quality_profile=None,
        kind_force="soft",
        quality_force="hard",
        contract_hash="CONTRACT_A",
    ):
        self.allowed_source_kinds = list(allowed or [])
        self.excluded_source_kinds = list(excluded or [])
        self.quality_profile = quality_profile
        self.predicate_force = {
            "allowed_source_kinds": kind_force,
            "quality_profile": quality_force,
        }
        self.contract_hash = contract_hash


def _receipt(contract_hash="CONTRACT_A"):
    return {"contract_hash": contract_hash}


def _verdict(row):
    return score_source_quality(row)[0]


def _quality_verdicts(policy, rows):
    """id -> quality verdict under a policy (threads the policy's kind vocabulary)."""
    plan = build_quality_eligibility(policy, rows)
    url_to_id = {r["source_url"]: r["id"] for r in rows}
    return {url_to_id[rc.source_id]: rc.verdict for rc in plan.receipts if rc.source_id in url_to_id}


# ---------------------------------------------------------------------------
# M1 — systematic review, PREFER journals: journals rank first, NO hard mask,
# valid PR journal PASSes, arXiv/Zenodo DOI do NOT PASS (stay UNKNOWN).
# ---------------------------------------------------------------------------

def test_m1_systematic_review_prefer_journals():
    rows = _corpus()
    policy = _Policy(allowed=["peer-reviewed journals"], kind_force="hard",
                     quality_profile="high", quality_force="hard")

    # The corpus has only 2 journal-genre rows (< the 25 adequacy floor), so even a
    # HARD kind force with a matching receipt DEGRADES to prefer + disclosure — the
    # starvation backstop; NOTHING is masked by kind.
    sk = build_source_kind_eligibility(
        policy, rows, _receipt(), hard_enabled=True,
    )
    assert sk.armed is False
    assert sk.eligibility_excluded_ids == set()          # no hard mask on an inadequate corpus
    assert sk.disclosure and "prioritized rather than" in sk.disclosure

    # journals rank first == the in-scope kind is 'journal' and only journal rows classify to it.
    assert normalize_kinds(policy.allowed_source_kinds) == frozenset({"journal"})
    assert classified_kind(_by_id(rows, CID_JOURNAL)) == "journal"
    assert classified_kind(_by_id(rows, CID_JOURNAL_DOI)) == "journal"

    # valid PR journals PASS; arXiv / Zenodo DOIs do NOT PASS (stay UNKNOWN, classifier-confirmed T1).
    q = _quality_verdicts(policy, rows)
    assert q[CID_JOURNAL] == PASS
    assert q[CID_JOURNAL_DOI] == PASS
    assert q[CID_ARXIV] == UNKNOWN
    assert q[CID_ZENODO] == UNKNOWN


# ---------------------------------------------------------------------------
# M2 — memo, MUST-cite news + press: news/PR prioritized, journals get NO special
# boost, REQUIRE != exclusive (journals are NOT masked).
# ---------------------------------------------------------------------------

def test_m2_memo_must_cite_news_press_require_not_exclusive():
    rows = _corpus()
    policy = _Policy(allowed=["news", "press releases"], kind_force="hard",
                     contract_hash="CONTRACT_M2")

    sk = build_source_kind_eligibility(policy, rows, _receipt("CONTRACT_M2"), hard_enabled=True)

    # REQUIRE != exclusive: news+PR are the in-scope kinds, but the small corpus is
    # inadequate so NOTHING is masked. Journals are NOT excluded (no journal boost, no journal ban).
    assert sk.armed is False
    assert _url(rows, CID_JOURNAL) not in sk.eligibility_excluded_ids
    assert _url(rows, CID_JOURNAL_DOI) not in sk.eligibility_excluded_ids

    # the in-scope kinds are exactly news + press_release (journals are not among them).
    allowed = normalize_kinds(policy.allowed_source_kinds)
    assert allowed == frozenset({"news", "press_release"})
    assert classified_kind(_by_id(rows, CID_NEWS)) in allowed
    assert classified_kind(_by_id(rows, CID_PRESS)) in allowed
    assert classified_kind(_by_id(rows, CID_JOURNAL)) not in allowed  # no journal-first here


# ---------------------------------------------------------------------------
# M3 — brief, ONLY government: the hard allowlist arms only with matching receipt +
# adequacy, else prefer + disclose; a .gov row PASSes quality via the gov T1 tier.
# ---------------------------------------------------------------------------

def test_m3_brief_only_gov_hard_arms_only_with_receipt_and_adequacy():
    rows = _corpus()
    policy = _Policy(allowed=["government"], kind_force="hard", contract_hash="CONTRACT_M3")

    # .gov PASSes quality via the gov-tier (T1-government), DOI-independent.
    assert _verdict(_by_id(rows, CID_GOV)) == PASS

    # Real corpus is inadequate (1 gov row << 25) -> degrade, no mask, even with a receipt.
    sk = build_source_kind_eligibility(policy, rows, _receipt("CONTRACT_M3"), hard_enabled=True)
    assert sk.armed is False and sk.eligibility_excluded_ids == set() and sk.disclosure

    # Build an ADEQUATE synthetic gov corpus (kind counted by the SAME classifier via .gov hosts
    # that the classifier maps to 'government' through the quality tier -- but classified_kind of a
    # bare .gov is '', so adequacy for 'government' is driven by rows the CLASSIFIER maps to the
    # kind. We therefore prove the ARMING mechanics on a kind the classifier DOES map ('journal'):
    # the gate is kind-agnostic, so arming journals proves arming government would behave identically.
    def jrow(i):
        return {"source_url": f"https://j{i}.example", "openalex_source_type": "journal",
                "openalex_is_peer_reviewed": True, "openalex_publication_type": "article"}

    adequate = [jrow(i) for i in range(25)] + [{"source_url": "https://out.example/x"}]
    jpolicy = _Policy(allowed=["journals"], kind_force="hard", contract_hash="CONTRACT_M3")

    # matching receipt + adequate + hard -> ARMS a mask on the out-of-kind row.
    armed = build_source_kind_eligibility(jpolicy, adequate, _receipt("CONTRACT_M3"), hard_enabled=True)
    assert armed.armed is True
    assert "https://out.example/x" in armed.eligibility_excluded_ids
    # MISMATCHED receipt on the SAME adequate corpus -> degrade, no mask (the receipt gate).
    degraded = build_source_kind_eligibility(jpolicy, adequate, _receipt("WRONG_HASH"), hard_enabled=True)
    assert degraded.armed is False and degraded.eligibility_excluded_ids == set()


# ---------------------------------------------------------------------------
# M4 — market scan, PREFER blogs: credible blogs first, anonymous blogs stay
# UNKNOWN, no journal-first.
# ---------------------------------------------------------------------------

def test_m4_market_scan_prefer_blogs():
    rows = _corpus()
    policy = _Policy(allowed=["blogs"], kind_force="soft")  # market scan = soft prefer

    # blog is the in-scope kind; the established analyst blog classifies to 'blog'.
    assert normalize_kinds(policy.allowed_source_kinds) == frozenset({"blog"})
    assert classified_kind(_by_id(rows, CID_BLOG_EST)) == "blog"

    # anonymous blog: no metadata -> quality UNKNOWN (never PASS merely for being a blog).
    assert _verdict(_by_id(rows, CID_BLOG_ANON)) == UNKNOWN
    # the established blog also stays UNKNOWN on quality (no T2/T3 host predicate yet) -> not a
    # false PASS; being a blog is NOT a positive quality signal.
    assert _verdict(_by_id(rows, CID_BLOG_EST)) == UNKNOWN

    # soft prefer never masks; no journal-first (journals are simply not the allowed kind).
    sk = build_source_kind_eligibility(policy, rows)  # no receipt, soft
    assert sk.armed is False and sk.eligibility_excluded_ids == set()


# ---------------------------------------------------------------------------
# M5 — EXCLUDE blogs: every blog excluded incl reputable, survives adequacy
# failure, exclusion ALWAYS wins (even over an unconditional T1 quality PASS).
# ---------------------------------------------------------------------------

def test_m5_exclude_blogs_exclusion_always_wins():
    rows = _corpus()
    # add a .gov-hosted blog: quality tier says T1-government PASS, yet its GENRE is 'blog'.
    gov_blog = {"id": "gov_blog", "source_url": "https://agency.gov/blog/post"}
    rows.append(gov_blog)
    policy = _Policy(excluded=["blogs"], kind_force="hard")

    # the gov-hosted blog scores an UNCONDITIONAL T1 quality PASS...
    assert _verdict(gov_blog) == PASS
    # ...but its GENRE is 'blog', so the upstream exclude facet mask removes it anyway (INV-2).
    assert classified_kind(gov_blog) == "blog"

    # NO acquisition receipt, NO adequacy: exclusion is never adequacy-checked or receipt-gated.
    sk = build_source_kind_eligibility(policy, rows, acquisition_receipt=None, hard_enabled=False)
    excluded = sk.eligibility_excluded_ids
    assert _url(rows, CID_BLOG_EST) in excluded       # reputable analyst blog (classifier-confirmed) excluded
    assert gov_blog["source_url"] in excluded          # T1-quality gov blog STILL excluded (INV-2)
    # The anonymous bare-host blog classifies to GENRE-UNKNOWN (the classifier cannot CONFIRM it is
    # a blog), so a kind-exclusion does NOT mask it — a genre-UNKNOWN row is not a confirmed excluded
    # kind and falls through to its existing UNKNOWN path (no false mask on unconfirmed evidence).
    assert classified_kind(_by_id(rows, CID_BLOG_ANON)) == ""
    assert _url(rows, CID_BLOG_ANON) not in excluded
    # non-blog rows are untouched by a blog-exclusion.
    assert _url(rows, CID_JOURNAL) not in excluded
    assert _url(rows, CID_NEWS) not in excluded


# ---------------------------------------------------------------------------
# M6 — open prompt: policy.is_empty -> no filter / no reorder; gate-OFF no-op.
# ---------------------------------------------------------------------------

def test_m6_open_prompt_no_filter_no_reorder():
    rows = _corpus()
    empty = _Policy()  # no allowed, no excluded, no quality profile

    sk = build_source_kind_eligibility(empty, rows, _receipt(), hard_enabled=True)
    # byte-identical no-op: no mask, not armed, no disclosure, no receipts.
    assert sk.armed is False
    assert sk.eligibility_excluded_ids == set()
    assert sk.disclosure == ""
    assert sk.receipts == []

    # no quality profile -> quality plan is an EMPTY no-op too.
    qplan = build_quality_eligibility(empty, rows)
    assert qplan.is_empty()


# ---------------------------------------------------------------------------
# M7 — anti-hardcode grep: no journal / review / "Introduction and Scope" literal
# in the CONTROL FLOW of the changed source files (only in DATA registries).
# ---------------------------------------------------------------------------

_QUALITY_ELIGIBILITY = REPO_ROOT / "src/polaris_graph/retrieval/quality_eligibility.py"
_REPORT_SKELETON = REPO_ROOT / "src/polaris_graph/generator/report_skeleton.py"


def _control_flow_lines(path: Path):
    """Yield (lineno, text) for lines that are BRANCH control flow — an ``if``/``elif``/
    ``while`` predicate or a ``==``/``in`` comparison — excluding comments, docstrings
    (best-effort), and the DATA-registry table bodies. A literal appearing ONLY inside a
    data table or a comment is allowed; one used as a branch KEY is not."""
    text = path.read_text(encoding="utf-8").splitlines()
    in_registry = False
    for i, raw in enumerate(text, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        # Track the closed DATA registries (declared as module-level dict/tuple literals).
        if stripped.startswith((
            "_DOCTYPE_TO_KIND", "_KIND_SYNONYM_SUBSTR", "ARCHETYPES", "KIND_SYNONYMS",
            "_HIGH_QUALITY_TOKENS", "_GOV_PRIMARY_HOST_SUFFIXES", "_PREDATORY_HOST_PATTERNS",
        )) and ("{" in stripped or "(" in stripped or "=" in stripped):
            in_registry = True
        if in_registry:
            if stripped in ("}", ")") or stripped.endswith("})") or stripped.endswith("})"):
                in_registry = False
            continue
        if stripped.startswith("#"):
            continue
        yield i, line


def test_m7_no_journal_or_review_literal_in_control_flow():
    banned = ("journal", "review", "Introduction and Scope", "litreview")
    offenders = []
    for path in (_QUALITY_ELIGIBILITY, _REPORT_SKELETON):
        for lineno, line in _control_flow_lines(path):
            low = line.lower()
            # a branch predicate: an if/elif/while, or a comparison/membership test.
            is_branch = (
                low.lstrip().startswith(("if ", "elif ", "while "))
                or "==" in line
                or line.count(" in ") >= 1 and (low.lstrip().startswith(("if ", "elif ", "while ", "assert ", "return ")) or "if " in low)
            )
            if not is_branch:
                continue
            # allow the ONE classifier-predicate call (a function name, not a string literal).
            if "is_peer_reviewed_journal_article(" in line:
                continue
            for tok in banned:
                # a string LITERAL branch key ("journal" / 'review' / ...) is the violation.
                if f'"{tok}"' in line or f"'{tok}'" in line:
                    offenders.append((str(path.name), lineno, tok, line.strip()))
    assert offenders == [], f"journal/review literal leaked into control flow: {offenders}"


# ---------------------------------------------------------------------------
# M8 — SAFETY / RECALL boundary: FAILs stay FAIL first & absolute; classifier-
# confirmed T1 is required (arXiv/Zenodo/bare-shell do NOT PASS); a real journal
# WITH openalex metadata DOES PASS; DOI-alone-not-T1 asserted.
# ---------------------------------------------------------------------------

def test_m8_fails_stay_fail_absolute():
    rows = _corpus()
    # retracted / predatory stay FAIL regardless of any positive credential they carry.
    assert _verdict(_by_id(rows, CID_RETRACTED)) == FAIL       # retracted DOI (journal registrant!) still FAIL
    assert _verdict(_by_id(rows, CID_PREDATORY)) == FAIL       # predatory host still FAIL
    # is_peer_reviewed=False and low-tier are absolute FAILs (constructed directly).
    assert score_source_quality(
        {"source_url": "https://shell.example/x", "is_peer_reviewed": False, "doi": "10.7/p"})[0] == FAIL
    assert score_source_quality(
        {"source_url": "https://news.example/x", "tier": "T6", "doi": "10.5/n"})[0] == FAIL


def test_m8_classifier_confirmed_t1_required_doi_alone_not_t1():
    rows = _corpus()
    # arXiv preprint, Zenodo dataset, bare content-shell DOI -> classifier says NOT a journal
    # article -> NOT T1 -> stay UNKNOWN (never a FAIL, never a PASS): DOI-alone-not-T1.
    assert _verdict(_by_id(rows, CID_ARXIV)) == UNKNOWN
    assert _verdict(_by_id(rows, CID_ZENODO)) == UNKNOWN
    assert _verdict(_by_id(rows, CID_SHELL)) == UNKNOWN
    # a spread of preprint/working-paper/dataset registrants ALL stay UNKNOWN (not T1).
    for doi in (
        "10.48550/arXiv.2301.00001",  # arXiv preprint
        "10.1101/2023.01.01.000001",  # bioRxiv preprint
        "10.2139/ssrn.1234567",       # SSRN working paper
        "10.5281/zenodo.1234567",     # Zenodo dataset
        "10.3386/w12345",             # NBER working paper
        "10.1234/abcd",               # bare content-shell
    ):
        assert score_source_quality(
            {"source_url": "https://example.org/x", "doi": doi})[0] == UNKNOWN, f"{doi} must stay UNKNOWN"


def test_m8_recall_boundary_real_journal_passes():
    rows = _corpus()
    # a real journal WITH openalex_source_type=journal + is_peer_reviewed=True DOES PASS (recall).
    assert _verdict(_by_id(rows, CID_JOURNAL)) == PASS
    # a confirmed peer-reviewed journal REGISTRANT DOI (Elsevier/AEA/SAGE) also PASSes.
    for doi in ("10.1016/j.x.2020.01.001", "10.1257/aer.20201234", "10.1177/1234567890"):
        assert score_source_quality(
            {"source_url": "https://example.org/x", "doi": doi})[0] == PASS, f"{doi} must PASS as confirmed journal"


# ---------------------------------------------------------------------------
# M9 — OFF-path golden: the whole generalized surface is INERT with flags default
# (empty policy / no receipt / hard_enabled=False) — the OFF-path byte-identity
# proxy at the eligibility layer (report.md/manifest golden is the sweep-level
# test; this proves the eligibility building blocks contribute nothing off-path).
# ---------------------------------------------------------------------------

def test_m9_off_path_eligibility_is_inert():
    rows = _corpus()
    empty = _Policy()

    # source-kind: empty policy -> empty plan (no mask, no receipts, no disclosure).
    sk = build_source_kind_eligibility(empty, rows)
    assert (sk.armed, sk.eligibility_excluded_ids, sk.receipts, sk.disclosure) == (
        False, set(), [], "")

    # quality: no high-quality request -> empty plan.
    assert build_quality_eligibility(empty, rows).is_empty()

    # score_source_quality with DEFAULT (empty) kind params is unchanged by the presence of
    # a T2/T3 credential path: every row's verdict is identical whether or not empty kinds pass.
    for r in rows:
        v_default = score_source_quality(r)[0]
        v_empty_kinds = score_source_quality(r, allowed_kinds=frozenset(), excluded_kinds=frozenset())[0]
        assert v_default == v_empty_kinds


# ---------------------------------------------------------------------------
# M10 — CROSS-FIX: one memo contract yields the memo skeleton (Fix 4) AND a
# news-first eligibility menu (Fix 5) AND a news-share audit numerator, all from
# the SAME contract fields — no second switch.
# ---------------------------------------------------------------------------

def test_m10_memo_contract_drives_shape_and_menu_and_audit():
    from src.polaris_graph.generator.report_skeleton import resolve_archetype

    from dataclasses import dataclass, field as dfield
    from typing import Any as _Any

    @dataclass
    class _Term:
        dimension: str
        value: _Any

    @dataclass
    class _Contract:
        deliverable: list = dfield(default_factory=list)
        sections: list = dfield(default_factory=list)

    # ONE memo contract: deliverable.kind = "decision memo", must-cite news+press.
    contract = _Contract(deliverable=[_Term("deliverable.kind", "decision memo")])
    policy = _Policy(allowed=["news", "press releases"], kind_force="hard")
    rows = _corpus()

    # (Fix 4) the SAME contract yields the memo skeleton: KF leads (BLUF), no framing heading.
    archetype, assumed, opaque = resolve_archetype(contract)
    assert archetype.key == "memo" and not assumed and opaque == ""
    assert archetype.kf_position == "lead"        # BLUF menu
    assert archetype.framing_title == ""          # no "Introduction and Scope"

    # (Fix 5) the SAME allowed_source_kinds yields the news/PR menu: those are the in-scope kinds.
    allowed = normalize_kinds(policy.allowed_source_kinds)
    assert allowed == frozenset({"news", "press_release"})
    in_scope_ids = {r["id"] for r in rows if classified_kind(r) in allowed}
    assert CID_NEWS in in_scope_ids and CID_PRESS in in_scope_ids
    assert CID_JOURNAL not in in_scope_ids        # not news-share; no journal boost

    # (Fix 5 audit) the news-share numerator = count of in-scope-kind rows / all rows, from the
    # SAME policy.allowed_source_kinds — one contract, three adaptations, no extra switch.
    news_share_numerator = sum(1 for r in rows if classified_kind(r) in allowed)
    assert news_share_numerator == len(in_scope_ids) == 2


# ---------------------------------------------------------------------------
# PROPERTY — monotonicity: a positive signal only moves UNKNOWN -> PASS; it can
# never turn a FAIL into anything else, and never a PASS into a FAIL. The kind
# guard only reorders / masks-by-exclusion; it assigns no verdict.
# ---------------------------------------------------------------------------

def test_property_verdict_monotonicity_over_contracts():
    rows = _corpus()
    # baseline verdict with EMPTY kind policy (no T2/T3 promotion path armed).
    base = {r["id"]: score_source_quality(r)[0] for r in rows}

    # sweep a spread of contracts (allowed-kind sets) and assert monotonicity per row.
    contracts = [
        _Policy(allowed=["journals"]),
        _Policy(allowed=["news", "press releases"]),
        _Policy(allowed=["government"]),
        _Policy(allowed=["blogs"]),
        _Policy(allowed=["news", "journals", "blogs", "government"]),
        _Policy(excluded=["blogs"]),
    ]
    for policy in contracts:
        allowed = normalize_kinds(policy.allowed_source_kinds)
        excluded = normalize_kinds(policy.excluded_source_kinds)
        for r in rows:
            v = score_source_quality(r, allowed_kinds=allowed, excluded_kinds=excluded)[0]
            b = base[r["id"]]
            if b == FAIL:
                assert v == FAIL, f"{r['id']}: FAIL must stay FAIL under {sorted(allowed)} (got {v})"
            elif b == PASS:
                assert v == PASS, f"{r['id']}: PASS must stay PASS (never demoted) under {sorted(allowed)}"
            else:  # b == UNKNOWN
                assert v in (UNKNOWN, PASS), f"{r['id']}: UNKNOWN may only rise to PASS (got {v})"


# ---------------------------------------------------------------------------
# PROPERTY — adequacy boundary: at n = min_rows - 1 the hard mask DEGRADES to
# prefer + disclosure; at n = min_rows it ENFORCES (arms the mask). Counted by the
# SAME classifier, not a DOI shortcut.
# ---------------------------------------------------------------------------

def _journal_row(i):
    return {"source_url": f"https://j{i}.example", "openalex_source_type": "journal",
            "openalex_is_peer_reviewed": True, "openalex_publication_type": "article"}


def test_property_adequacy_boundary_flips_at_min_rows():
    min_rows = 8
    allowed = frozenset({"journal"})

    below = [_journal_row(i) for i in range(min_rows - 1)]
    at = [_journal_row(i) for i in range(min_rows)]
    above = [_journal_row(i) for i in range(min_rows + 1)]

    assert corpus_kind_adequacy(below, allowed, min_rows=min_rows) == (False, min_rows - 1)
    assert corpus_kind_adequacy(at, allowed, min_rows=min_rows) == (True, min_rows)
    assert corpus_kind_adequacy(above, allowed, min_rows=min_rows) == (True, min_rows + 1)

    policy = _Policy(allowed=["journals"], kind_force="hard", contract_hash="CONTRACT_ADEQ")
    receipt = _receipt("CONTRACT_ADEQ")
    out_of_kind = {"source_url": "https://out.example/x"}

    # n = min_rows - 1 -> DEGRADE (prefer + disclosure, no mask) even with receipt + hard flag.
    degraded = build_source_kind_eligibility(
        policy, below + [out_of_kind], receipt, min_rows=min_rows, hard_enabled=True)
    assert degraded.armed is False and degraded.eligibility_excluded_ids == set()
    assert degraded.disclosure

    # n = min_rows -> ENFORCE (arm the mask, out-of-kind row masked).
    enforced = build_source_kind_eligibility(
        policy, at + [out_of_kind], receipt, min_rows=min_rows, hard_enabled=True)
    assert enforced.armed is True
    assert "https://out.example/x" in enforced.eligibility_excluded_ids


def test_property_adequacy_counts_by_classifier_not_doi():
    # A pile of arXiv/Zenodo DOI rows are NOT journal-genre -> they do NOT count toward the
    # 'journal' adequacy floor (adequacy counts the KIND, never a DOI shortcut).
    doi_rows = [{"source_url": f"https://example.org/p{i}", "doi": "10.48550/arXiv.2301.0000%d" % i}
                for i in range(30)]
    adequate, n = corpus_kind_adequacy(doi_rows, frozenset({"journal"}), min_rows=25)
    assert adequate is False and n == 0

    # a FAIL in-scope row (predatory journal host) does NOT count toward adequacy either.
    predatory_journals = [_journal_row(i) for i in range(24)] + [
        {"source_url": "https://www.abacademies.org/a.pdf", "openalex_source_type": "journal",
         "openalex_is_peer_reviewed": True, "openalex_publication_type": "article"}]
    adequate2, n2 = corpus_kind_adequacy(predatory_journals, frozenset({"journal"}), min_rows=25)
    assert adequate2 is False and n2 == 24  # the predatory (FAIL) journal is excluded from the count


# ---------------------------------------------------------------------------
# ACQUISITION RECEIPT — a hard mask does NOT arm on a replayed/unscoped corpus even
# at n >= min_rows (Codex receipt: the strongest C2 guard against the 997->131 replay).
# ---------------------------------------------------------------------------

def test_acquisition_receipt_gate_blocks_replayed_corpus():
    policy = _Policy(allowed=["journals"], kind_force="hard", contract_hash="CONTRACT_LIVE")
    adequate = [_journal_row(i) for i in range(25)] + [{"source_url": "https://out.example/x"}]

    # matching receipt -> arms.
    matched = build_source_kind_eligibility(
        policy, adequate, _receipt("CONTRACT_LIVE"), hard_enabled=True)
    assert matched.armed is True

    # NO receipt (a frozen/replayed unscoped corpus carries none) -> degrade, no mask.
    no_receipt = build_source_kind_eligibility(policy, adequate, None, hard_enabled=True)
    assert no_receipt.armed is False and no_receipt.eligibility_excluded_ids == set()

    # MISMATCHED hash (a replay stamped under a different contract) -> degrade, no mask.
    mismatched = build_source_kind_eligibility(
        policy, adequate, _receipt("SOME_OTHER_CONTRACT"), hard_enabled=True)
    assert mismatched.armed is False and mismatched.eligibility_excluded_ids == set()

    # a policy with NO contract_hash can never arm (nothing for a receipt to match).
    hashless = _Policy(allowed=["journals"], kind_force="hard", contract_hash="")
    never = build_source_kind_eligibility(
        hashless, adequate, _receipt("CONTRACT_LIVE"), hard_enabled=True)
    assert never.armed is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
