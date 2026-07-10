"""S2/S3 re-pass iter-2 fix coverage (Fable full-list): P0-1 topic category-consistency +
on-topic anchors, P0-2 qualitative NLI-confirm, P0-3a line content-integrity junk, P0-3b
measurement gate, P1-4 unicode/LaTeX normalize, P1-5 metadata-less same-work fallback (+ render
parity). All pure/offline (NLI injected). General + question-agnostic (no basket ids / entity
lists / corpus-tuned numbers)."""
import types

from src.polaris_graph.synthesis import finding_dedup as fd
from src.polaris_graph.retrieval import line_screen as ls
from src.polaris_graph.retrieval import topic_relevance_gate as trg
from src.polaris_graph.generator import weighted_enrichment as we
import src.polaris_graph.generator.fact_dedup as fdd


def _claim(value=0.0, unit=""):
    c = types.SimpleNamespace()
    c.value = value; c.unit = unit; c.subject = "x"; c.predicate = "p"
    c.dose = ""; c.arm = ""; c.endpoint_phrase = ""
    return c


# ── P1-4 unicode / LaTeX normalize ───────────────────────────────────────────
def test_p1_4_ligature_folds():
    assert "significant" in fd._normalize_unicode_text("this is signiﬁcant")


def test_p1_4_latex_percent_and_math_wrap():
    assert "1.5%" in fd._normalize_unicode_text("$1.5\\%$")


# ── P0-3b measurement gate ───────────────────────────────────────────────────
def test_p0_3b_percent_kept_as_measurement():
    assert not fd._is_nonmeasurement_numeral(_claim(15.0, "%"), "wages rose 15%")


def test_p0_3b_ssrn_id_demoted():
    assert fd._is_nonmeasurement_numeral(
        _claim(4637198.0), "SSRN Electronic Journal https://ssrn.com/abstract=4637198")


def test_p0_3b_phone_demoted():
    assert fd._is_nonmeasurement_numeral(_claim(7721.0), "call 212-555-7721 for details")


def test_p0_3b_page_range_demoted():
    assert fd._is_nonmeasurement_numeral(_claim(145.0), "Journal of Labor, pp. 123-145")


def test_p0_3b_citation_year_demoted():
    assert fd._is_nonmeasurement_numeral(_claim(2024.0), "Autor, D. (2024). Journal of Labor Economics.")


def test_p0_3b_real_stat_with_url_kept_failopen():
    assert not fd._is_nonmeasurement_numeral(
        _claim(26.0), "output rose 26% see https://x.org/abstract=99")


def test_p0_3b_bare_number_no_signal_kept():
    assert not fd._is_nonmeasurement_numeral(_claim(26.08), "developer productivity index reached 26.08")


# ── P1-5 metadata-less same-work fallback + render parity ─────────────────────
_LONG = "Experimental Evidence on the Productivity Effects of Generative Artificial Intelligence"


def test_p1_5_long_title_alone_merges_mirrors():
    r1 = {"source_title": _LONG, "source_url": "https://a.org/x.pdf"}
    r2 = {"source_title": _LONG, "source_url": "https://b.org/y.pdf"}
    k1 = fd._same_work_key(r1)
    assert k1.startswith("titlealone:") and k1 == fd._same_work_key(r2)


def test_p1_5_render_parity():
    r1 = {"source_title": _LONG, "source_url": "https://a.org/x.pdf"}
    assert we._work_identity("e1", r1) == fd._same_work_key(r1)


def test_p1_5_filename_artifact_strip():
    base = {"source_title": _LONG, "source_url": "https://a.org/x"}
    fn = {"source_title": _LONG + "_1_0.pdf", "source_url": "https://c.org/z"}
    assert fd._same_work_key(fn) == fd._same_work_key(base)


def test_p1_5_short_title_not_merged():
    a = {"source_title": "AI and jobs", "source_url": "https://d.org/1"}
    b = {"source_title": "AI and jobs", "source_url": "https://d.org/2"}
    assert fd._same_work_key(a) != fd._same_work_key(b)


def test_p1_5_body_arxiv_id():
    rb = {"source_title": "z", "source_url": "https://mirror.org/paper",
          "direct_quote": "arXiv:2303.10130 GPTs are GPTs. We find..."}
    assert fd._same_work_key(rb) == "id:arxiv:2303.10130"


# ── P0-2 qualitative greedy NLI-confirm ──────────────────────────────────────
def _rows_scaffold():
    return [
        {"evidence_id": "a", "direct_quote": "Smith 2024 reports a finding in a journal reference line."},
        {"evidence_id": "b", "direct_quote": "Jones 2023 reports a different finding in a reference line."},
        {"evidence_id": "c", "direct_quote": "Lee 2022 reports yet another citation reference line entry."},
    ]


def test_p0_2_unconfirmed_cluster_splits_to_singletons():
    rows = _rows_scaffold()
    cl = [[fdd._prose_shingles(rows[0]["direct_quote"]),
           fdd._polarity_signature(rows[0]["direct_quote"]), [0, 1, 2]]]
    out = fd._confirm_greedy_clusters_via_nli(rows, cl, entail_fn=lambda a, b: False)
    assert sorted(len(c[2]) for c in out) == [1, 1, 1]


def test_p0_2_confirmed_pair_stays_merged():
    rows = _rows_scaffold()[:2]
    cl = [[fdd._prose_shingles(rows[0]["direct_quote"]),
           fdd._polarity_signature(rows[0]["direct_quote"]), [0, 1]]]
    out = fd._confirm_greedy_clusters_via_nli(rows, cl, entail_fn=lambda a, b: True)
    assert any(len(c[2]) == 2 for c in out)


# ── P0-2 chrome-dominant body guard (real-run fix: exclude nav/URL/binary from clustering) ──
def test_p0_2_chrome_nav_body_excluded():
    assert fd._body_is_chrome_dominant(
        "* [Summary](https://www.bls.gov/ooh/x.htm#tab-1) * [What They Do](https://www.bls.gov/ooh/y) "
        "* [Pay](https://www.bls.gov/ooh/pay.htm)")


def test_p0_2_bare_url_list_excluded():
    assert fd._body_is_chrome_dominant(
        "(https://siepr.stanford.edu/a )(https://siepr.stanford.edu/b )(https://x.org/c )")


def test_p0_2_pdf_xref_excluded():
    assert fd._body_is_chrome_dominant("%PDF-1.3 % 1 0 obj >]/Pages 3 0 R/Type/Catalog endobj stream")


def test_p0_2_javascript_void_excluded():
    assert fd._body_is_chrome_dominant(
        "Link opens in a new tab (javascript:void(0)) [ ](https://deloitte.com) * [Who we are]")


def test_p0_2_lone_link_fragment_excluded():
    assert fd._body_is_chrome_dominant(
        "[ ](https://blog.hospitalmedicine.org/) [](https://shmblog.example.com/x)")


def test_p0_2_short_cited_claim_kept():
    # a short real claim with no link is NOT chrome (the guard only fires on link/URL/binary)
    assert not fd._body_is_chrome_dominant(
        "The paper reports a 26 percent increase in developer output using an AI coding assistant.")


def test_p0_2_real_claim_body_not_chrome():
    assert not fd._body_is_chrome_dominant(
        "Generative AI raised worker productivity by 14% in a large customer-support field "
        "experiment, with the largest gains among less-experienced workers.")


# ── P0-3a line content-integrity junk ────────────────────────────────────────
def test_p0_3a_pdf_xref():
    assert ls._line_is_content_integrity_junk("stream x /Type /Page endobj FlateDecode")


def test_p0_3a_hex_run():
    assert ls._line_is_content_integrity_junk("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0")


def test_p0_3a_nav_link_list():
    assert ls._line_is_content_integrity_junk("Home | About | Contact | Privacy | Terms")


def test_p0_3a_license_footer():
    assert ls._line_is_content_integrity_junk("© 2024 Elsevier B.V. All rights reserved.")


def test_p0_3a_toc_leader():
    assert ls._line_is_content_integrity_junk("Introduction .......... 5")


def test_p0_3a_javascript_fragment():
    assert ls._line_is_content_integrity_junk("javascript:void(0)")


def test_p0_3a_real_prose_kept():
    assert not ls._line_is_content_integrity_junk(
        "The unemployment rate rose to 5.2% in 2024 across all major sectors of the economy.")


# ── P0-1b topic category-consistency ─────────────────────────────────────────
def test_p0_1b_oes_family_shares_signature():
    a = trg._category_signature({"source_url": "https://www.bls.gov/oes/current/oes232011.htm"})
    b = trg._category_signature({"source_url": "https://www.bls.gov/oes/current/oes436014.htm"})
    assert a == b and a != ""


def test_p0_1b_wiki_article_inert():
    assert trg._category_signature(
        {"source_url": "https://en.wikipedia.org/wiki/Cost-benefit_analysis"}) == ""


def test_p0_1b_credible_on_topic_sibling_not_deleted():
    def stub_llm(_prompt):
        return "0: ON\n1: OFF_SUBJECT\n2: OFF_SUBJECT\n"
    def oes(code):
        return {"statement": "Paralegals wage data occupational outlook",
                "snippet": "median annual wage",
                "source_url": f"https://www.bls.gov/oes/current/oes{code}.htm"}
    srcs = [oes("232011"), oes("436014"), oes("111011")]
    res = trg.classify_topic_relevance(srcs, "AI exposure of paralegals and office occupations", stub_llm)
    assert all(not r.get("topic_off_subject") for r in res.kept_rows)
    assert res.n_kept == 3
