"""I-deepfix-001 beat-both Wave B WS-3 — behavioral wiring test for the breadth surface
+ no-provenance-token repair.

Two WS-3 functions were built + committed (WIP 9f690609) but NOT wired and had no test:
  * ``verified_compose.repair_untokened_sentence`` — rebinds an untokened abstractive sentence
    to the nearest supporting basket's OWN verified clause BEFORE strict_verify drops it (the
    drb_72 ``no_provenance_token=34`` leak).
  * ``weighted_enrichment.build_evidence_base_section`` — surfaces the FULL uncapped unbound-
    SUPPORTS ev_id surface as ONE numbered "Evidence base" section so every span-verified source
    gets a ``[N]``.

This test is OFFLINE, fixture-driven, no model / GPU / network. It asserts:
  1. REPAIR: a fixture untokened sentence whose claim is supported by a basket span is REPAIRED
     (bound to that span, carries a real ``[#ev]`` token, survives the UNCHANGED strict_verify);
     a sentence with NO supporting basket span is STILL dropped (never fabricated).
  2. BREADTH: ``build_evidence_base_section`` over a fixture surface of 8 DISTINCT works yields a
     numbered list covering ALL 8 (one entry per work), FAIL LOUD if it regresses to a subset.
  3. KILL-SWITCHES OFF => byte-identical legacy behaviour (untokened dropped, no Evidence base
     section).
  4. WIRING: the caller in ``multi_section_generator`` actually invokes BOTH — the repair pass
     calls ``repair_untokened_sentence`` before dropping, and the assembly calls
     ``_append_evidence_base_section`` (which appends the section) — so a future un-wiring FAILS.

Entailment is forced OFF (``PG_STRICT_VERIFY_ENTAILMENT=off``) so ``strict_verify`` runs its
deterministic mechanical checks only — a verbatim K-span self-quote passes them by construction,
with zero model spend.
"""

from __future__ import annotations

import inspect
import re

import pytest

from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator import verified_compose as vc
from src.polaris_graph.generator import weighted_enrichment as we
from src.polaris_graph.generator.provenance_generator import (
    strict_verify,
    verify_sentence_provenance,
)

_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")


# ─────────────────────────────────────────────────────────────────────────────
# Lightweight offline fixtures (no ClaimBasket / BasketMember imports — the
# production functions read via getattr, so duck-typed shims are faithful).
# ─────────────────────────────────────────────────────────────────────────────
class _Member:
    def __init__(
        self,
        evidence_id: str,
        direct_quote: str,
        *,
        span_verdict: str = "SUPPORTS",
        credibility_weight: float = 0.5,
        origin_cluster_id: str | None = None,
        source_url: str = "",
        source_tier: str = "",
    ) -> None:
        self.evidence_id = evidence_id
        self.direct_quote = direct_quote
        self.span_verdict = span_verdict
        self.credibility_weight = credibility_weight
        self.origin_cluster_id = origin_cluster_id or evidence_id
        self.source_url = source_url
        self.source_tier = source_tier


class _Basket:
    def __init__(
        self,
        claim_text: str,
        members: list,
        *,
        subject: str = "",
        predicate: str = "",
        claim_cluster_id: str = "cluster_x",
    ) -> None:
        self.claim_text = claim_text
        self.subject = subject
        self.predicate = predicate
        self.supporting_members = members
        self.claim_cluster_id = claim_cluster_id


# The supported-claim quote (a clean, sentence-form verbatim span).
_SUPPORTED_QUOTE = (
    "Insulin resistance markedly increased fasting glucose in the treatment cohort "
    "during the study period."
)


def _supported_basket_and_pool():
    member = _Member("evA", _SUPPORTED_QUOTE, source_url="https://a.example", source_tier="T2")
    basket = _Basket(
        "Insulin resistance raises fasting glucose",
        [member],
        subject="insulin resistance",
        predicate="raises fasting glucose",
    )
    pool = {
        "evA": {
            "direct_quote": _SUPPORTED_QUOTE,
            "source_url": "https://a.example",
            "source_tier": "T2",
        }
    }
    return basket, pool


def _empty_writer(_basket, _pool) -> str:
    """A writer that produces NOTHING, forcing the deterministic verbatim K-span fallback —
    so the repair is proven WITHOUT any model call."""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 1. REPAIR — untokened + supported => repaired & survives strict_verify;
#             untokened + unsupported => still dropped (None), never fabricated.
# ─────────────────────────────────────────────────────────────────────────────
def test_repair_binds_supported_untokened_sentence_and_survives_strict_verify(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    basket, pool = _supported_basket_and_pool()

    untokened = "Insulin resistance raised fasting glucose across the study cohort overall."
    assert not _EV_TOKEN_RE.search(untokened)  # the leak precondition

    repaired = vc.repair_untokened_sentence(
        untokened, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert repaired is not None, "supported untokened sentence must be REPAIRED, not dropped"
    assert _EV_TOKEN_RE.search(repaired), "repaired clause must carry a real [#ev] provenance token"
    assert "evA" in repaired

    # The repaired clause must SURVIVE the UNCHANGED strict_verify (mechanical mode).
    report = strict_verify(repaired, pool)
    assert report.kept_sentences, "repaired verbatim K-span clause must survive strict_verify"
    kept_text = " ".join(str(getattr(s, "sentence", s)) for s in report.kept_sentences)
    assert _EV_TOKEN_RE.search(kept_text)


def test_repair_returns_tokened_sentence_unchanged():
    basket, pool = _supported_basket_and_pool()
    already = "Fasting glucose rose in the cohort [#ev:evA:0-40]."
    out = vc.repair_untokened_sentence(
        already, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert out == already, "a sentence that already cites a span must be returned unchanged"


def test_repair_drops_unsupported_untokened_sentence(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    basket, pool = _supported_basket_and_pool()
    # Zero content-word overlap with the basket -> no binding -> still dropped (never fabricated).
    unsupported = "Quantum chromodynamics governs subatomic gluon interactions entirely."
    out = vc.repair_untokened_sentence(
        unsupported, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert out is None, "an unsupported untokened sentence must STAY dropped (no fabricated binding)"


def test_repair_killswitch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "0")
    basket, pool = _supported_basket_and_pool()
    untokened = "Insulin resistance raised fasting glucose across the study cohort overall."
    out = vc.repair_untokened_sentence(
        untokened, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert out is None, "flag OFF => the legacy silent drop (returns None) => byte-identical"


# ─────────────────────────────────────────────────────────────────────────────
# 2. BREADTH — 8 distinct works => numbered list covering ALL 8 (one per work).
# ─────────────────────────────────────────────────────────────────────────────
def _eight_distinct_works():
    """8 evidence rows that are 8 DISTINCT works (no DOI, no title => _work_identity falls
    through to the distinct evidence_id, so none consolidate together)."""
    pool = {}
    ev_ids = []
    for i in range(1, 9):
        eid = f"ev{i:02d}"
        ev_ids.append(eid)
        pool[eid] = {
            "direct_quote": (
                f"Finding number {i}: the measured outcome improved substantially in "
                f"cohort {i} across the observed follow-up window."
            ),
            "source_url": f"https://source{i:02d}.example/paper",
            "source_tier": "T3",
        }
    return ev_ids, pool


def test_evidence_base_section_covers_all_eight_distinct_works(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    ev_ids, pool = _eight_distinct_works()

    block = we.build_evidence_base_section(ev_ids, pool)
    assert block, "8 distinct span-verified works must yield a non-empty Evidence base section"
    assert block.startswith("## Evidence base")

    # Exactly 8 numbered entries (one per distinct work) — FAIL LOUD on any regression to a subset.
    numbered = re.findall(r"(?m)^(\d+)\.\s", block)
    assert numbered == [str(n) for n in range(1, 9)], (
        f"expected numbered entries 1..8 (one per distinct work); got {numbered!r}"
    )
    # Every work's own [ev_id] marker is present (no work silently dropped from the surface).
    for eid in ev_ids:
        assert f"[{eid}]" in block, f"work {eid} missing from the Evidence base surface (breadth regression)"


def test_evidence_base_section_consolidates_same_work(monkeypatch):
    """Two ev_ids that are the SAME work (shared DOI) consolidate to ONE numbered entry."""
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    quote = (
        "The randomized trial reported a statistically significant reduction in the "
        "primary endpoint among treated participants."
    )
    pool = {
        "evX": {"direct_quote": quote, "doi": "10.1000/same", "source_url": "https://x.example"},
        "evY": {"direct_quote": quote, "doi": "10.1000/same", "source_url": "https://y.example"},
    }
    block = we.build_evidence_base_section(["evX", "evY"], pool)
    numbered = re.findall(r"(?m)^(\d+)\.\s", block)
    assert numbered == ["1"], f"same-work members must consolidate to ONE entry; got {numbered!r}"


def test_evidence_base_section_killswitch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "0")
    ev_ids, pool = _eight_distinct_works()
    block = we.build_evidence_base_section(ev_ids, pool)
    assert block == "", "flag OFF => no Evidence base section => byte-identical legacy output"


# ─────────────────────────────────────────────────────────────────────────────
# 3. WIRING — the multi_section_generator callers invoke BOTH functions.
# ─────────────────────────────────────────────────────────────────────────────
def test_repair_draft_wiring_invokes_repair_before_dropping(monkeypatch):
    """`_repair_untokened_draft` (called by `_run_section`) must invoke `repair_untokened_sentence`
    for EACH sentence before strict_verify, replace an untokened+supported sentence, and leave a
    tokened sentence unchanged."""
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    basket, pool = _supported_basket_and_pool()

    seen: list[str] = []
    real = msg.repair_untokened_sentence

    def _spy(sentence, baskets, evidence_pool, **kw):
        seen.append(sentence)
        return real(sentence, baskets, evidence_pool, **kw)

    monkeypatch.setattr(msg, "repair_untokened_sentence", _spy)

    tokened = "Fasting glucose rose in the cohort [#ev:evA:0-40]."
    untokened = "Insulin resistance raised fasting glucose across the study cohort overall."
    raw = f"{tokened}\n{untokened}"

    out = msg._repair_untokened_draft(
        raw, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )

    assert len(seen) == 2, "repair must be attempted on BOTH sentences (before any drop)"
    assert tokened in out, "the already-tokened sentence must survive unchanged"
    assert untokened not in out, "the untokened sentence must be REPLACED by its repaired clause"
    assert _EV_TOKEN_RE.search(out.replace(tokened, "")), "the repaired portion must carry a [#ev] token"


def test_repair_draft_wiring_byte_identical_when_off(monkeypatch):
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "0")
    basket, pool = _supported_basket_and_pool()
    raw = "Insulin resistance raised fasting glucose across the study cohort overall."
    out = msg._repair_untokened_draft(
        raw, [basket], pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    assert out == raw, "flag OFF => raw returned unchanged (untokened sentence still present, later dropped)"


def test_evidence_base_wiring_appends_section_and_extends_biblio(monkeypatch):
    """`_append_evidence_base_section` (called by `generate_multi_section_report`) must invoke
    `build_evidence_base_section`, append ONE SectionResult, and resolve every [ev_id] to a global
    [N] (extending the bibliography for newly-surfaced works)."""
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    ev_ids, pool = _eight_distinct_works()

    called: list = []
    real = we.build_evidence_base_section

    def _spy(passed_ev_ids, passed_pool, **kw):
        called.append((list(passed_ev_ids), passed_pool))
        return real(passed_ev_ids, passed_pool, **kw)

    monkeypatch.setattr(we, "build_evidence_base_section", _spy)

    section_results: list = []
    global_biblio: list = []
    appended = msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)

    assert appended is True
    assert called, "the caller must invoke build_evidence_base_section"
    assert called[0][0] == ev_ids, "the caller must pass the uncapped SUPPORTS ev_id surface"
    assert len(section_results) == 1, "exactly ONE Evidence base section must be appended"
    sect = section_results[0]
    assert sect.title == "Evidence base"
    assert not sect.dropped_due_to_failure and sect.verified_text
    # P1 FIX (Codex iter-1 REQUEST_CHANGES): the Evidence base MUST NOT ship lines outside
    # strict_verify/D8. It is routed through the frozen strict_verify, so every rendered entry is a
    # real SentenceVerification carried in kept_sentences_pre_resolve — which native_gate_b_inputs
    # promotes to a 4-role D8 claim. A revert to the pre-fix bypass (empty kept_sentences_pre_resolve)
    # FAILS here.
    assert sect.kept_sentences_pre_resolve, (
        "Evidence base must carry strict_verify SentenceVerification objects in "
        "kept_sentences_pre_resolve, else it bypasses strict_verify/D8 (the Codex iter-1 P1)"
    )
    assert all(getattr(v, "is_verified", False) for v in sect.kept_sentences_pre_resolve), (
        "every Evidence base entry Gate-B/D8 sees must be a strict_verify-VERIFIED sentence"
    )
    # No raw [ev_id] markers survive; every work resolved to a global [N].
    assert not re.search(r"\[ev\d", sect.verified_text), "every [ev_id] must resolve to a [N]"
    nums = {b["evidence_id"]: b["num"] for b in global_biblio}
    assert set(nums) == set(ev_ids), "global bibliography must be extended for all 8 surfaced works"
    assert len(set(nums.values())) == 8, "each surfaced work gets a distinct global [N]"
    for n in nums.values():
        assert f"[{n}]" in sect.verified_text


def test_evidence_base_wiring_reuses_existing_biblio_number(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    ev_ids, pool = _eight_distinct_works()
    # ev03 already cited elsewhere as [5] — its number must be REUSED, not renumbered.
    global_biblio = [{"num": 5, "evidence_id": "ev03", "url": "", "tier": "", "statement": ""}]
    section_results: list = []
    assert msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)
    nums = {b["evidence_id"]: b["num"] for b in global_biblio}
    assert nums["ev03"] == 5, "an already-numbered source must keep its existing global [N]"
    assert f"[5]" in section_results[0].verified_text


def test_evidence_base_wiring_noop_when_off(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "0")
    ev_ids, pool = _eight_distinct_works()
    section_results: list = []
    global_biblio: list = []
    appended = msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)
    assert appended is False
    assert section_results == [], "flag OFF => no section appended => byte-identical"
    assert global_biblio == [], "flag OFF => bibliography untouched"


def test_pipeline_source_invokes_both_helpers():
    """Source-level guard so a future UN-WIRING (removing either helper call from the pipeline)
    FAILS this test — the behavioral helper tests above prove the helpers work; this proves the
    real render path calls them."""
    run_section_src = inspect.getsource(msg._run_section)
    assert "_repair_untokened_draft(" in run_section_src, (
        "_run_section must call _repair_untokened_draft (no-token repair un-wired)"
    )
    gen_src = inspect.getsource(msg.generate_multi_section_report)
    assert "_append_evidence_base_section(" in gen_src, (
        "generate_multi_section_report must call _append_evidence_base_section (breadth surface un-wired)"
    )
