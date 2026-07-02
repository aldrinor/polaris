"""I-wire-014 (#1334) FIX-A — CWF corroboration header renders a real claim sentence /
clean source title, never a clm_<hash> or a broken 2-word stub.

Pins the header-selection chain in scripts/run_honest_sweep_r3.py against small fixtures
mirroring the real bibliography.json shapes that produced the 154/155 hash-dump defect.
"""
import pytest

from scripts.run_honest_sweep_r3 import (
    _complete_sentence_prefix,
    _best_corroboration_header,
    _basket_corroboration_block,
    _title_candidate_is_renderable,
)


# ── _complete_sentence_prefix ────────────────────────────────────────────────

def test_complete_sentence_prefix_strips_doc_label_and_returns_first_sentence():
    raw = "Abstract We study the staggered introduction of a generative AI assistant. Access to AI assis"
    out = _complete_sentence_prefix(raw)
    assert out.startswith("We study the staggered introduction")
    assert out.endswith("AI assistant.")
    assert "Access to AI assis" not in out  # the truncated tail is dropped


def test_complete_sentence_prefix_empty_when_no_complete_sentence():
    # END-truncated single clause, no sentence-final punctuation
    raw = "We present a framework for understanding the effects of automation and use it to interpret changes in "
    assert _complete_sentence_prefix(raw) == ""


def test_complete_sentence_prefix_midword_start_yields_nothing():
    assert _complete_sentence_prefix("usand workers reduces the ratio by 0.2 percentage points") != \
        "usand workers reduces the ratio by 0.2 percentage points"  # a complete sentence here is fine
    # a genuinely fragmentary start with no sentence end:
    assert _complete_sentence_prefix("hodology to estimate the probability of computerisation for jobs") == ""


def test_complete_sentence_prefix_does_not_treat_ellipsis_as_sentence_end():
    # #1334 Codex P1: a clause terminated by a truncation marker must NOT yield a header.
    assert _complete_sentence_prefix("This representative span is incomplete and cut ...") == ""
    assert _complete_sentence_prefix("A clause cut mid thought …") == ""
    # an internal ellipsis glued before a real sentence must not produce a marker-bearing header
    out = _complete_sentence_prefix("fragment ... Then a full clean sentence appears here clearly.")
    assert "..." not in out


def test_complete_sentence_prefix_does_not_split_on_abbreviation():
    raw = "Adoption reached 35.9% of U.S. workers by 2025 and rose further the next year. Tail tail tail"
    out = _complete_sentence_prefix(raw)
    # must NOT cut at "U.S." — the first real sentence ends at "next year."
    assert "U.S. workers" in out
    assert out.endswith("the next year.")


# ── _title_candidate_is_renderable ───────────────────────────────────────────

def test_title_renderable_accepts_noun_phrase_title():
    assert _title_candidate_is_renderable("Robots and Jobs: Evidence from US Labor Markets") is True


def test_title_renderable_rejects_lowercase_slug():
    assert _title_candidate_is_renderable("fourth_industrial_revolution_framing") is False


# ── _best_corroboration_header (the full chain) ──────────────────────────────

def _basket(claim_text="", members=None, subject="", predicate="", ccid="clm_deadbeef"):
    return {
        "claim_cluster_id": ccid,
        "claim_text": claim_text,
        "subject": subject,
        "predicate": predicate,
        "supporting_members": members or [],
    }


def test_header_prefers_complete_sentence_from_claim_text():
    bk = _basket(
        claim_text="We study the staggered introduction of a generative AI assistant. Access to AI assis",
    )
    h = _best_corroboration_header(bk, statement="Some Source Title")
    assert h.startswith("We study the staggered introduction")
    assert "clm_" not in h


def test_header_falls_back_to_member_quote_sentence():
    bk = _basket(
        claim_text="usand workers reduces the ratio by ",  # midword start, no sentence
        members=[{"member_tier": "ENTAILMENT_VERIFIED",
                  "direct_quote": "One more robot per thousand workers reduces the employment ratio by 0.2 points."}],
    )
    h = _best_corroboration_header(bk, statement="")
    assert h.startswith("One more robot per thousand workers")


def test_header_falls_back_to_source_title_with_trailing_ellipsis_stripped():
    bk = _basket(claim_text="hodology to estimate the probability of ")  # no sentence
    h = _best_corroboration_header(
        bk, statement="A systematic review of Artificial Intelligence and Automation ..."
    )
    assert h == "A systematic review of Artificial Intelligence and Automation"
    assert "clm_" not in h and "..." not in h


def test_header_never_returns_hash_when_a_title_exists():
    bk = _basket(claim_text="", ccid="clm_abc123")
    h = _best_corroboration_header(bk, statement="The Future of Employment")
    assert "clm_abc123" not in h
    assert h == "The Future of Employment"


def test_header_returns_empty_only_when_truly_titleless():
    bk = _basket(claim_text="atch out mid word", members=[], subject="", predicate="")
    h = _best_corroboration_header(bk, statement="")
    assert h == ""  # caller applies the subject+predicate/ccid last resort


# ── U18: byte-identical corroboration blocks are collapsed (repeated-URL symptom) ────────────
#
# The drb_78 07-01 autopsy report rendered the "Source corroboration" section with 39 redundant
# duplicate blocks: distinct claim clusters that resolved to the SAME header + SAME single source
# + SAME count printed many times (identical "FDA carbidopa-levodopa …" block 8×, the same
# managing-patients URL 6×). _basket_corroboration_block must collapse a byte-identical block to
# one, while KEEPING two DISTINCT claims that happen to share a source (§-1.3 corroboration).

def _verified_member(url, eid="ev_a", tier="T1", weight=0.5, oc="oc1"):
    return {
        "member_tier": "ENTAILMENT_VERIFIED",
        "source_url": url,
        "evidence_id": eid,
        "origin_cluster_id": oc,
        "source_tier": tier,
        "credibility_weight": weight,
    }


def _corr_basket(ccid, claim_text, url):
    return {
        "claim_cluster_id": ccid,
        "claim_text": claim_text,
        "subject": "",
        "predicate": "",
        "verified_support_origin_count": 1,
        "basket_verdict": "supported",
        "supporting_members": [_verified_member(url)],
    }


_SENT_A = "Deep brain stimulation reduces motor complications in Parkinson disease patients."
_SENT_B = "Levodopa remains the most effective symptomatic treatment for Parkinson disease."
_URL = "https://example.org/parkinsons-study"


def _biblio(baskets, url=_URL, eid="ev_a"):
    # a single bibliography row whose url/eid set marks the members biblio-present
    return [{"num": "1", "evidence_id": eid, "url": url, "statement": "A Source Title",
             "baskets": baskets}]


def test_corroboration_block_collapses_byte_identical_duplicate():
    # two DISTINCT clusters render an identical block (same claim + same single source) -> once.
    biblio = _biblio([
        _corr_basket("clm_1", _SENT_A, _URL),
        _corr_basket("clm_2", _SENT_A, _URL),
    ])
    out = _basket_corroboration_block(biblio)
    assert out.count(f"SUPPORT: {_URL}") == 1
    assert out.count(_SENT_A) == 1


def test_corroboration_block_keeps_distinct_claims_sharing_a_source():
    # §-1.3: same URL corroborating TWO different claims must render BOTH (not dropped).
    biblio = _biblio([
        _corr_basket("clm_1", _SENT_A, _URL),
        _corr_basket("clm_3", _SENT_B, _URL),
    ])
    out = _basket_corroboration_block(biblio)
    assert _SENT_A in out
    assert _SENT_B in out
    assert out.count(f"SUPPORT: {_URL}") == 2  # each distinct claim keeps its corroboration


def test_corroboration_block_dedup_off_is_legacy(monkeypatch):
    # kill-switch OFF => byte-identical legacy render (duplicates preserved).
    monkeypatch.setenv("PG_CORROBORATION_BLOCK_DEDUP", "0")
    biblio = _biblio([
        _corr_basket("clm_1", _SENT_A, _URL),
        _corr_basket("clm_2", _SENT_A, _URL),
    ])
    out = _basket_corroboration_block(biblio)
    assert out.count(f"SUPPORT: {_URL}") == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
