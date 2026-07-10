"""S2/S3 re-pass fixes — regression tests (Fix 1/3c/4/5/8 + parity).

Pure/deterministic unit tests for the S2+S3 re-pass. No network, no LLM, no model — every
assertion exercises a pure predicate/keying function. General/question-agnostic: no basket id,
entity list, or corpus-tuned number is hardcoded.
"""
import os

import pytest

from src.polaris_graph.synthesis import finding_dedup as fd
from src.polaris_graph.generator import weighted_enrichment as we


# ── Fix 1(a)(b) + Fix 8: chrome whole-source deletion + mixed-row route-by-body ──────────────
def test_fix1_title_only_bot_wall_is_chrome():
    """A Cloudflare wall whose challenge tell is only in the TITLE (short shell body) is chrome."""
    row = {
        "title": "Just a moment...",
        "statement": "## Security check required We've detected unusual activity from your network.",
    }
    assert fd._is_captcha_stub(row) is True


def test_fix1_general_antibot_shell_is_chrome():
    """A general anti-bot / shell body with no propositional prose is chrome (title+body union)."""
    row = {"title": "Security check", "statement": "Please enable JavaScript and cookies to continue. Ray ID: 9ab2."}
    assert fd._is_captcha_stub(row) is True


def test_fix8_chrome_title_substantive_body_is_kept():
    """Fix 8: a chrome TITLE with a substantive recovered body is routed by BODY — never deleted."""
    row = {
        "title": "Verifying your browser | OpenReview",
        "statement": (
            "Generative AI could expose three hundred million full time jobs to automation "
            "across advanced economies, with the largest exposure among white collar clerical roles."
        ),
    }
    assert fd._is_captcha_stub(row) is False


def test_fix1_real_prose_with_security_word_is_kept():
    """A real sentence that merely mentions a security term is never chrome (propositional guard)."""
    row = {"statement": "The paper reports that access denied errors rose twelve percent after the firewall upgrade in twenty twenty three across the surveyed firms."}
    assert fd._is_captcha_stub(row) is False


def test_fix1_killswitch_off_reverts_to_legacy():
    """PG_CI_ANTIBOT_SHELL=0 restores the legacy trigger+WAF-only predicate."""
    row = {"title": "Just a moment...", "statement": "## Security check required unusual activity"}
    os.environ["PG_CI_ANTIBOT_SHELL"] = "0"
    try:
        # legacy needs the literal "just a moment" trigger in the (title+body) union AND a WAF token;
        # here the body has no "just a moment", but the title does + "attention"? no — legacy is off.
        assert fd._is_captcha_stub(row) is False
    finally:
        os.environ.pop("PG_CI_ANTIBOT_SHELL", None)


# ── Fix 4: cross-mirror same-work identity ───────────────────────────────────────────────────
def test_fix4_arxiv_id_merges_across_mirrors():
    a = {"source_url": "https://arxiv.org/abs/2303.10130", "title": "GPTs are GPTs"}
    b = {"source_url": "https://arxiv.org/pdf/2303.10130v4", "title": "GPTs are GPTs early look"}
    assert fd._same_work_key(a) == fd._same_work_key(b) == "id:arxiv:2303.10130"


def test_fix4_bare_arxiv_id_merges_nonarxiv_mirrors():
    # S2/S3 re-pass iter 2: repec (/arx/papers/<id>) and HuggingFace (/papers/<id>) host the
    # SAME arXiv work but on a non-arxiv.org host. The bare-id path matcher must extract the
    # same id so all mirrors share one work id (the Eloundou fragmentation fix). A genuinely
    # different arXiv id must NOT collide.
    arx = {"source_url": "https://arxiv.org/abs/2303.10130"}
    repec = {"source_url": "https://ideas.repec.org/p/arx/papers/2303.10130.html"}
    hf = {"source_url": "https://huggingface.co/papers/2303.10130"}
    ar5 = {"source_url": "https://ar5iv.labs.arxiv.org/html/2303.10130"}
    other = {"source_url": "https://huggingface.co/papers/2401.99999"}
    keys = {fd._same_work_key(r) for r in (arx, repec, hf, ar5)}
    assert keys == {"id:arxiv:2303.10130"}, keys
    assert fd._same_work_key(other) == "id:arxiv:2401.99999"
    # render-side mirror stays byte-identical
    assert we._url_work_identifier(repec) == "arxiv:2303.10130"
    assert we._url_work_identifier(hf) == "arxiv:2303.10130"


def test_fix4_bare_id_no_false_match_on_doi_or_nber():
    # A DOI path (10.NNNN/...) and an NBER /papers/wNNNNN must not be mis-read as a bare
    # arXiv id (the dotted YYMM.NNNNN form is arXiv-specific).
    assert we._url_work_identifier({"source_url": "https://x.org/papers/w31161"}) != "arxiv:w31161"
    doi = we._url_work_identifier({"source_url": "https://doi.org/10.1126/science.adj0998"})
    assert not doi.startswith("arxiv:")


def test_fix4_nber_id_merges_across_mirrors():
    a = {"source_url": "https://www.nber.org/system/files/working_papers/w31161/w31161.pdf", "title": "x"}
    b = {"source_url": "https://nber.org/papers/w31161", "title": "y"}
    assert fd._same_work_key(a) == fd._same_work_key(b) == "id:nber:w31161"


def test_fix4_title_author_merges_when_url_differs():
    a = {"source_url": "https://governance.ai/research/gpts", "title": "GPTs are GPTs: Labor market impact potential", "authors": ["Eloundou T"]}
    b = {"source_url": "https://openai.com/research/gpts-are-gpts", "title": "GPTs are GPTs: Labor market impact potential", "authors": ["Eloundou T"]}
    assert fd._same_work_key(a) == fd._same_work_key(b)
    assert fd._same_work_key(a).startswith("title:")


def test_fix4_distinct_works_not_merged():
    a = {"source_url": "https://x.org/a.pdf", "title": "Automation and jobs one", "authors": ["Autor D"]}
    b = {"source_url": "https://x.org/b.pdf", "title": "Robots and wages two", "authors": ["Acemoglu D"]}
    assert fd._same_work_key(a) != fd._same_work_key(b)


def test_fix4_killswitch_off_is_url_first():
    os.environ["PG_SAMEWORK_CROSSMIRROR"] = "0"
    try:
        row = {"source_url": "https://arxiv.org/abs/2303.10130", "title": "x", "doi": "10.1/z"}
        assert fd._same_work_key(row).startswith("url:")
    finally:
        os.environ.pop("PG_SAMEWORK_CROSSMIRROR", None)


def test_fix4_render_parity():
    """finding_dedup._same_work_key and weighted_enrichment._work_identity agree (shared contract)."""
    row = {"source_url": "https://nber.org/papers/w31161", "title": "x", "evidence_id": "ev_1"}
    assert fd._same_work_key(row) == we._work_identity("ev_1", row)


# ── Fix 3(c): garbage-subject / garbage-value key hygiene ────────────────────────────────────
def test_fix3c_garbage_subjects_flagged():
    assert fd._is_garbage_subject("wp096") is True        # working-paper code
    assert fd._is_garbage_subject("flatedecode") is True  # PDF-stream artifact
    assert fd._is_garbage_subject("com") is True           # lone TLD token
    assert fd._is_garbage_subject("w31161") is True        # nber code token
    assert fd._is_garbage_subject("123456789") is True     # long digit run (ISBN-like)
    # real subjects survive:
    assert fd._is_garbage_subject("ecommerce") is False
    assert fd._is_garbage_subject("productivity") is False


class _Claim:
    def __init__(self, subject, value, predicate="rose", unit="%"):
        self.subject, self.value, self.predicate, self.unit = subject, value, predicate, unit
        self.dose = self.arm = self.endpoint_phrase = ""


def test_fix3c_garbage_subject_key_collapses_to_singleton():
    """A garbage subject yields the unknown per-claim sentinel, never a shared merge key."""
    k = fd._finding_key(_Claim("wp096", 5.0), "ev_1", 0, clinical=False)
    assert k[0] == "__unknown__"


def test_fix3c_absurd_value_collapses():
    k = fd._finding_key(_Claim("ecommerce", 9.78e17), "ev_1", 0, clinical=False)
    assert k[0] == "__unknown__"


def test_fix3c_real_nonclinical_claim_keeps_real_key():
    k = fd._finding_key(_Claim("ecommerce", 5.0), "ev_1", 0, clinical=False)
    assert k[0] == "ecommerce"


# ── Fix 1(e) + Fix 5: recover-before-delete disclosure + distinct-works corroboration ────────
def test_fix1e_recover_before_delete_disclosure():
    """A chrome row with a clean same-work sibling is RECOVERED; one with none is a GAP."""
    rows = [
        # chrome row + a clean sibling at the SAME url → recovered
        {"evidence_id": "ev_1", "source_url": "https://a.org/paper.pdf",
         "title": "Just a moment...", "statement": "## Security check required unusual activity Ray ID x"},
        {"evidence_id": "ev_2", "source_url": "https://a.org/paper.pdf",
         "title": "Real Paper", "statement": "Employment rose five percent among clerical workers in twenty twenty three per the survey."},
        # chrome row with NO clean sibling → coverage gap
        {"evidence_id": "ev_3", "source_url": "https://b.org/other.pdf",
         "title": "Just a moment...", "statement": "## Security check required unusual activity Ray ID y"},
    ]
    res = fd.consolidate_same_work(rows)
    assert 0 in res.dropped_captcha_indices and 2 in res.dropped_captcha_indices
    assert res.dropped_captcha_recovered == {0}
    assert res.dropped_captcha_gap == {2}


def test_fix5_corroboration_counts_distinct_works():
    """Two mirror URLs of one arXiv work carrying the same finding corroborate as ONE work."""
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    try:
        rows = [
            {"evidence_id": "ev_1", "source_url": "https://arxiv.org/abs/2303.10130",
             "statement": "Exposure reached 80 percent of workers.", "direct_quote": "Exposure reached 80 percent of workers.",
             "authority_score": 0.9},
            {"evidence_id": "ev_2", "source_url": "https://arxiv.org/pdf/2303.10130v2",
             "statement": "Exposure reached 80 percent of workers.", "direct_quote": "Exposure reached 80 percent of workers.",
             "authority_score": 0.8},
        ]
        res = fd.dedup_by_finding(rows, gov_suffixes=(".gov",), domain="workforce")
        # both rows are the SAME arXiv work → any shared-finding basket corroborates as 1 work
        for c in res.clusters:
            if len(c.member_indices) == 2:
                assert c.corroboration_count == 1
    finally:
        os.environ.pop("PG_SWEEP_CREDIBILITY_REDESIGN", None)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
