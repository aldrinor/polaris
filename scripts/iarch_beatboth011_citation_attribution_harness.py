#!/usr/bin/env python3
"""I-beatboth-011 (#1289) — citation mis-attribution replay harness (defect #6).

FAIL-LOUD behavioral harness for the basket-corroborator -> inline ``[N]`` filter added to
``provenance_generator.corroborator_span_grounds_sentence`` and wired into the corroborator
loop of ``resolve_provenance_to_citations_with_count``.

DEFECT (#6): the basket -> ``[N]`` expansion attached EVERY SUPPORTS member of a cluster as an
inline corroborator of a sentence, even members whose span does NOT carry THAT sentence's
specific claim (cluster membership != per-sentence grounding). Real ``drb_72_ai_labor``
examples: [85] (a Mapping-AI page-header span) glued to a BLS sentence only [84] grounds;
[17]/[19] (World-Bank / EPI spans lacking the displacement claim) glued to a displacement
sentence only [18] grounds.

FIX (faithfulness-TIGHTENING): before attaching a corroborator's ``[N]``, require its span to
carry the sentence's claim (>= ``MIN_CONTENT_WORD_OVERLAP`` distinctive content words — the SAME
predicate strict_verify already uses for own tokens, READ not re-implemented). True grounders
(strong overlap) survive; a member whose span does not carry the claim is withheld from inline
support. Own tokens are NEVER filtered; the sentence is never stranded uncited; genuine
multi-citation (multiple members each carrying the claim) is preserved.

This harness proves, on BOTH synthetic cases AND a REAL corpus pair (so a green run is not a
construction artifact — this project's #1 recurring miss):
  (a) a sentence grounded only by member A's span gets ONLY [A] attached, not [B]/[C] from the
      same basket whose spans lack the claim;
  (b) a sentence genuinely grounded by A AND B keeps BOTH [A][B];
  (c) the true grounding member is NEVER dropped.

Exit 0 iff every assertion holds; exit 1 (loud) on any regression. Offline, zero model spend.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make the strict-verify floor explicit + deterministic for the harness (matches production
# default 2). Set BEFORE importing the module so MIN_CONTENT_WORD_OVERLAP binds to it.
os.environ.setdefault("PG_PROVENANCE_MIN_CONTENT_OVERLAP", "2")

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    MIN_CONTENT_WORD_OVERLAP,
    ProvenanceToken,
    SentenceVerification,
    _basket_for_biblio,
    build_basket_supports_by_cluster,
    corroborator_grounds_sentence_via_basket,
    corroborator_span_grounds_sentence,
    resolve_provenance_to_citations_with_count,
)
from src.polaris_graph.generator.contract_section_runner import (  # noqa: E402
    contract_sentence_citation_nums,
)

_FAILURES: list[str] = []


def _check(cond: bool, msg: str) -> None:
    if not cond:
        _FAILURES.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok:   {msg}")


# ---------------------------------------------------------------------------
# Part 1 — unit: the grounding predicate itself (synthetic, fully controlled).
# ---------------------------------------------------------------------------
def test_predicate_unit() -> None:
    print("[1] predicate unit (synthetic)")
    # Claim about a SPECIFIC quantitative displacement finding.
    claim = "AI exposure raises measured occupational displacement risk for clerical workers."
    span_grounds = (
        "Our index finds elevated occupational displacement risk concentrated among "
        "clerical workers exposed to AI automation."
    )
    span_off_claim = (
        "Federal legislation proposals establish an oversight board and reporting "
        "requirements for deployed systems."  # different claim, no overlap of distinctive words
    )
    _check(
        corroborator_span_grounds_sentence(claim, span_grounds),
        "span carrying the claim's content words GROUNDS (kept)",
    )
    _check(
        not corroborator_span_grounds_sentence(claim, span_off_claim),
        "span NOT carrying the claim is rejected (dropped)",
    )
    # Empty / missing span can never be affirmed as support.
    _check(
        not corroborator_span_grounds_sentence(claim, ""),
        "empty span is rejected (never attached as support)",
    )
    _check(
        not corroborator_span_grounds_sentence("", span_grounds),
        "empty claim is rejected (cannot affirm grounding)",
    )
    # NUMERIC-corroboration path (regression lock for the iter-2 fix): an independent
    # corroborator that reports the SAME decimal figure but PARAPHRASES the prose shares < 2
    # content words yet legitimately corroborates. It must be KEPT via the numeric path —
    # a content-word-only predicate would WRONGLY drop it (the regression that broke the
    # B6/B8 whole-basket tests). Guard: a bare-number coincidence with ZERO shared words is
    # still rejected.
    numeric_claim = "Reported value was 14.9% here."
    numeric_corro = "Confirmed value was 14.9% too."  # shares only 'value' (<2) + the figure
    _check(
        corroborator_span_grounds_sentence(numeric_claim, numeric_corro),
        "NUMERIC corroborator (same 14.9%, <2 words) is KEPT via the numeric path",
    )
    bare_number_only = "The quarterly revenue figure stood at 14.9% in the latest filing."
    _check(
        not corroborator_span_grounds_sentence("Unemployment rose 14.9% among teens.", bare_number_only),
        "bare-number coincidence (14.9%, no shared distinctive word) is still rejected",
    )


# ---------------------------------------------------------------------------
# Part 2 — behavioral: the resolver loop attaches ONLY grounding corroborators.
# Drives resolve_provenance_to_citations_with_count end-to-end with a hand-built
# basket so the FULL render path (own-token + corroborator expansion + filter) runs.
# ---------------------------------------------------------------------------
class _Basket:
    """Minimal stand-in for credibility_pass.ClaimBasket consumed by _basket_for_biblio."""

    def __init__(self, claim_cluster_id, supporting_members):
        self.claim_cluster_id = claim_cluster_id
        self.supporting_members = supporting_members
        self.refuter_cluster_ids = []
        self.both_sides = None


class _Member:
    def __init__(self, evidence_id, span_verdict, direct_quote):
        self.evidence_id = evidence_id
        self.span_verdict = span_verdict
        self.direct_quote = direct_quote
        self.member_tier = "T1"
        self.authority_score = 1.0
        self.source_url = f"https://example.test/{evidence_id}"


def _sv(sentence: str, own_eid: str, start: int, end: int) -> SentenceVerification:
    return SentenceVerification(
        sentence=sentence,
        is_verified=True,
        tokens=[ProvenanceToken(evidence_id=own_eid, start=start, end=end, raw="")],
    )


def _render(sv, evidence_pool, baskets, cluster_id_by_evidence):
    text, biblio, _ = resolve_provenance_to_citations_with_count(
        [sv],
        evidence_pool,
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
    )
    eid_for_num = {row["num"]: row["evidence_id"] for row in biblio}
    # collect the [N] markers that ended up on the sentence, mapped back to evidence_ids
    import re as _re

    cited_eids = {
        eid_for_num[int(n)]
        for n in _re.findall(r"\[(\d+)\]", text)
        if int(n) in eid_for_num
    }
    return text, cited_eids


def test_resolver_behavioral() -> None:
    print("[2] resolver behavioral (single basket, own-token + corroborators)")
    # Sentence cites ONE own token (A). A, B, C are SUPPORTS members of the SAME cluster.
    # A & B spans carry the claim; C's span is an off-claim page-header that does NOT.
    claim_text = (
        "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60]."
    )
    span_a = (
        "AI exposure raises occupational displacement risk for clerical workers in our index."
    )
    span_b = (
        "We confirm elevated occupational displacement risk among clerical workers exposed to AI."
    )
    span_c = (
        "Download files. Version 2. Submitted March 2026. Copyright retained by the authors."
    )
    evidence_pool = {
        "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
        "eid_b": {"direct_quote": span_b, "statement": span_b, "source_url": "u/b", "tier": "T1"},
        "eid_c": {"direct_quote": span_c, "statement": span_c, "source_url": "u/c", "tier": "T6"},
    }
    members = [
        _Member("eid_a", "SUPPORTS", span_a),
        _Member("eid_b", "SUPPORTS", span_b),
        _Member("eid_c", "SUPPORTS", span_c),
    ]
    baskets = [_Basket("cl_1", members)]
    cluster_id_by_evidence = {"eid_a": ["cl_1"], "eid_b": ["cl_1"], "eid_c": ["cl_1"]}

    sv = _sv(claim_text, "eid_a", 0, 60)
    text, cited = _render(sv, evidence_pool, baskets, cluster_id_by_evidence)
    print(f"      rendered: {text!r}")
    print(f"      cited eids: {sorted(cited)}")

    # (c) the true grounding own member A is NEVER dropped.
    _check("eid_a" in cited, "(c) true grounding own-token A is retained")
    # (b) a genuine corroborator B (span carries the claim) is KEPT — multi-citation preserved.
    _check("eid_b" in cited, "(b) genuine corroborator B (carries claim) kept [A][B]")
    # (a) a non-grounding corroborator C (off-claim span) is NOT attached.
    _check(
        "eid_c" not in cited,
        "(a) off-claim corroborator C is NOT attached (mis-attribution removed)",
    )


def test_only_own_token_when_all_corro_off_claim() -> None:
    print("[3] resolver behavioral — only [A] when every corroborator is off-claim")
    claim_text = "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60]."
    span_a = "AI exposure raises occupational displacement risk for clerical workers in our index."
    span_b = "Quarterly earnings call transcript. Revenue grew. Guidance reaffirmed for fiscal year."
    span_c = "Download files. Version 2. Submitted March 2026. Copyright retained by the authors."
    evidence_pool = {
        "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
        "eid_b": {"direct_quote": span_b, "statement": span_b, "source_url": "u/b", "tier": "T5"},
        "eid_c": {"direct_quote": span_c, "statement": span_c, "source_url": "u/c", "tier": "T6"},
    }
    members = [
        _Member("eid_a", "SUPPORTS", span_a),
        _Member("eid_b", "SUPPORTS", span_b),
        _Member("eid_c", "SUPPORTS", span_c),
    ]
    baskets = [_Basket("cl_1", members)]
    cluster_id_by_evidence = {"eid_a": ["cl_1"], "eid_b": ["cl_1"], "eid_c": ["cl_1"]}
    sv = _sv(claim_text, "eid_a", 0, 60)
    text, cited = _render(sv, evidence_pool, baskets, cluster_id_by_evidence)
    print(f"      cited eids: {sorted(cited)}")
    _check("eid_a" in cited, "(a) sentence keeps ONLY its true grounder A")
    _check(
        cited == {"eid_a"},
        "(a) neither off-claim corroborator B nor C attached -> exactly {A}",
    )


# ---------------------------------------------------------------------------
# Part 3 — REAL corpus anchor (drb_72_ai_labor). Proves the filter discriminates a
# genuine corroborator mis-attribution on REAL spans, not just synthetic ones.
#   claim  = the IMF (ev_464) "complement or a substitute for labor" sentence.
#   keep   = ev_464 (the true grounding span, 17-word overlap).
#   drop   = ev_428 (EPI federal-AI-legislation span — a DIFFERENT claim, overlap=1 'labor').
# Skips (does NOT fail) if the banked corpus is absent.
# ---------------------------------------------------------------------------
_REAL_CORPUS = (
    _REPO_ROOT / "outputs" / "p6_postfix_resume" / "workforce"
    / "drb_72_ai_labor"
)


def test_real_corpus_anchor() -> None:
    print("[4] REAL corpus anchor (drb_72_ai_labor)")
    pv_path = _REAL_CORPUS / "postverify_checkpoint.json"
    ep_path = _REAL_CORPUS / "evidence_pool.json"
    if not pv_path.exists() or not ep_path.exists():
        # LOUD skip (I-beatboth-011 P2): this anchor is ABSENT off the canonical machine, so it
        # must NOT be read as a silent PASS. The synthetic multi-cluster checks below ALWAYS run
        # and are what gate this harness on any machine; the real-corpus pair is an extra anchor.
        print(
            "      SKIPPED (NOT PASSED): banked corpus absent "
            f"({_REAL_CORPUS}) — real-corpus anchor not exercised on this machine; "
            "synthetic multi-cluster checks still run and gate the harness"
        )
        return
    from src.polaris_graph.generator.provenance_generator import _verifier_cleaned_text

    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    pool = {r.get("evidence_id"): r for r in ep} if isinstance(ep, list) else ep
    pv = json.loads(pv_path.read_text(encoding="utf-8"))
    claim = None
    for sec in pv["verification_details"]["sections"]:
        for ks in sec.get("kept", []):
            eids = {t.get("evidence_id") for t in (ks.get("tokens") or [])}
            if "ev_464" in eids and "complement or a substitute" in ks["sentence"]:
                claim = _verifier_cleaned_text(ks["sentence"])
                break
    if claim is None:
        print(
            "      SKIPPED (NOT PASSED): anchor sentence not found in banked corpus "
            "— synthetic multi-cluster checks still run and gate the harness"
        )
        return
    span_keep = pool.get("ev_464", {}).get("direct_quote") or ""
    span_drop = pool.get("ev_428", {}).get("direct_quote") or ""
    _check(
        corroborator_span_grounds_sentence(claim, span_keep),
        "(c) REAL true grounder ev_464 is KEPT (never dropped)",
    )
    _check(
        not corroborator_span_grounds_sentence(claim, span_drop),
        "(a) REAL off-claim corroborator ev_428 (overlap=1) is DROPPED",
    )


# ---------------------------------------------------------------------------
# Part 4 — the 4 Codex P1 regression locks (#1289 diff review).
# ---------------------------------------------------------------------------
def _basket_map(members) -> dict:
    """Build the per-cluster PROJECTED basket map (the same _basket_for_biblio projection both
    render paths feed into corroborator_grounds_sentence_via_basket)."""
    return {"cl_1": _basket_for_biblio(_Basket("cl_1", members))}


def test_p1_2_reads_claim_local_member_span_not_pool_row() -> None:
    print("[5] P1#2 — grounds against the basket member's CLAIM-LOCAL span, not the pool row")
    # The basket member's stored span (direct_quote) is OFF-claim (a page header); the broad
    # evidence_pool row text IS on-claim. Pre-fix the resolver read the pool row -> it would
    # WRONGLY keep the mis-attributed corroborator. Post-fix it reads the member span -> dropped.
    claim_text = (
        "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60]."
    )
    span_a = "AI exposure raises occupational displacement risk for clerical workers in our index."
    member_b_span = "Download files. Version 2. Submitted March 2026. Copyright retained."  # off-claim
    pool_b_rowtext = (
        "AI exposure raises occupational displacement risk for clerical workers across sectors."
    )  # broad row text that WOULD ground if (wrongly) read
    evidence_pool = {
        "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
        # eid_b's POOL row carries the claim, but its BASKET MEMBER span does not:
        "eid_b": {"direct_quote": pool_b_rowtext, "statement": pool_b_rowtext, "source_url": "u/b", "tier": "T1"},
    }
    members = [
        _Member("eid_a", "SUPPORTS", span_a),
        _Member("eid_b", "SUPPORTS", member_b_span),  # claim-local span = off-claim
    ]
    baskets = [_Basket("cl_1", members)]
    cluster_id_by_evidence = {"eid_a": ["cl_1"], "eid_b": ["cl_1"]}
    sv = _sv(claim_text, "eid_a", 0, 60)
    _text, cited = _render(sv, evidence_pool, baskets, cluster_id_by_evidence)
    print(f"      cited eids: {sorted(cited)}")
    _check("eid_a" in cited, "P1#2 true grounder A retained")
    _check(
        "eid_b" not in cited,
        "P1#2 corroborator B dropped on its OFF-claim member span (pool row NOT consulted)",
    )


def test_p1_3_relevance_guard_never_strands_with_ungrounded_corro() -> None:
    print("[6] P1#3 — relevance guard uses FILTERED corroborators -> never strands a sentence")
    # The bug #3 scenario needs a corroborator that SURVIVES the relevance judge (SUPPORTED) but
    # FAILS grounding — that is the ONLY path where the UNFILTERED surviving-corro set fools the
    # guard. A judge that demotes everything would NOT exercise the fix (the corro lands in
    # _demote_eids and is excluded by the pre-existing clause). So the judge here is SELECTIVE,
    # keying off the SPAN text (the only signal the injected fn receives):
    #   - the OWN token's span CARRIES the claim          -> INSUFFICIENT (demoted)
    #   - the corroborator's span is OFF-claim (ungrounded)-> SUPPORTED   (survives the judge)
    # Pre-fix: _surviving_corro (unfiltered) still holds the SUPPORTED-but-ungrounded corro, so
    # the guard thinks "support remains", demotes the own token, then the append loop drops the
    # ungrounded corro -> ZERO markers (stranded). Post-fix: _surviving_corro is FILTERED to
    # grounded members only -> empty -> guard fires -> own token un-demoted/kept -> >=1 marker.
    os.environ["PG_RELEVANCE_GATE"] = "1"
    try:
        from src.polaris_graph.generator import provenance_generator as _pg
        _pg.reset_relevance_telemetry()

        span_a = "AI exposure raises occupational displacement risk for clerical workers in our index."
        member_b_span = "Quarterly earnings call transcript. Revenue grew. Guidance reaffirmed."  # off-claim

        def _selective_judge(_claim, span):
            # Demote the ON-claim own-token span; keep the OFF-claim corroborator span SUPPORTED
            # so it would survive the judge and (pre-fix) fool the unfiltered retention guard.
            if "displacement risk" in span:
                return ("INSUFFICIENT", "harness: demote the own-token to test the guard")
            return ("SUPPORTED", "harness: keep the off-claim corroborator past the judge")

        claim_text = (
            "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60]."
        )
        evidence_pool = {
            "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
            "eid_b": {"direct_quote": member_b_span, "statement": member_b_span, "source_url": "u/b", "tier": "T5"},
        }
        members = [
            _Member("eid_a", "SUPPORTS", span_a),
            _Member("eid_b", "SUPPORTS", member_b_span),
        ]
        baskets = [_Basket("cl_1", members)]
        cluster_id_by_evidence = {"eid_a": ["cl_1"], "eid_b": ["cl_1"]}
        sv = _sv(claim_text, "eid_a", 0, 60)
        text, _b, _ = resolve_provenance_to_citations_with_count(
            [sv], evidence_pool,
            baskets=baskets, cluster_id_by_evidence=cluster_id_by_evidence,
            relevance_judge_fn=_selective_judge,
        )
        import re as _re
        n_markers = len(_re.findall(r"\[(\d+)\]", text))
        print(f"      rendered: {text!r}  (markers={n_markers})")
        _check(
            n_markers >= 1,
            "P1#3 sentence NEVER stranded uncited (>=1 marker) when a SUPPORTED corro is ungrounded",
        )
    finally:
        os.environ.pop("PG_RELEVANCE_GATE", None)


def test_p1_4_integer_percent_corroborator_kept() -> None:
    print("[7] P1#4 — integer-percentage / integer-only corroborator is KEPT (not over-dropped)")
    # An independent corroborator reporting the SAME integer-% figure but paraphrasing (sharing
    # < 2 lexical content words). Pre-fix only _decimals_in was checked, so an integer-% claim
    # ("50%"/"19%") fell straight to the content-word floor and was WRONGLY dropped. Post-fix the
    # integer-% / _numbers_in path (the SAME one strict_verify uses) keeps it.
    # Shares exactly ONE distinctive content word ("adoption") + the same 50% figure — below the
    # 2-word lexical floor, so it survives ONLY via the integer-% numeric path (the P1#4 fix).
    _check(
        corroborator_span_grounds_sentence(
            "Adoption reached 50% across surveyed firms.",
            "Independent telemetry put adoption at 50% there.",
        ),
        "P1#4 integer-% corroborator (same 50%, 1 shared word) is KEPT via the integer path",
    )
    # Decimal-free integer claim with no '%' on either side would NOT exercise the integer-%
    # path; use a percentage claim so the fix's _INTEGER_PERCENT_RE branch is what saves it.
    _check(
        corroborator_span_grounds_sentence(
            "Clerical roles fell 19% over the decade.",
            "A separate panel reports clerical employment down 19% nationally.",
        ),
        "P1#4 second integer-% corroborator (same 19%, 1 shared word 'clerical') is KEPT",
    )
    # Guard still holds: a bare integer-% coincidence with ZERO shared distinctive words is rejected.
    _check(
        not corroborator_span_grounds_sentence(
            "Teen unemployment rose 19% last quarter.",
            "Highway funding increased 19% under the appropriations bill.",
        ),
        "P1#4 bare integer-% coincidence (no shared distinctive word) is still rejected",
    )


def test_p1_plain_integer_only_corroborator_kept() -> None:
    print("[7b] P1 — PLAIN integer-only corroborator is KEPT (not over-dropped)")
    # THE plain-integer-only gap (#1289 P1): a true grounding corroborator for an integer-only
    # claim (NO decimal, NO '%') was wrongly DETACHED when lexical overlap fell below the 2-word
    # floor, even though ALL the asserted integers ARE present in its span. The prior numeric path
    # checked only _decimals_in + %-expressed integers, so "5,172 agents were tested" / "47
    # occupations" fell straight to the content-word floor and were dropped. The fix READS the
    # SAME _numbers_in predicate strict_verify uses for own tokens (no engine change): all the
    # claim's integers in the span -> grounded, independent of lexical overlap, with the >=1
    # coincidence guard retained.
    # Case A: a count claim "5,172 agents" grounded by a paraphrase sharing exactly ONE word
    # ("agents") — below the 2-word floor, so it survives ONLY via the integer path.
    _check(
        corroborator_span_grounds_sentence(
            "5,172 agents were evaluated.",
            "An independent benchmark covered 5,172 distinct agents.",
        ),
        "P1 plain-integer corroborator (same 5,172, 1 shared word 'agents', LOW overlap) is KEPT",
    )
    # Case A2: "47 occupations" grounded by an off-vocabulary paraphrase that still carries 47.
    _check(
        corroborator_span_grounds_sentence(
            "47 occupations face elevated automation exposure.",
            "Our index flags 47 occupations as highly exposed.",
        ),
        "P1 plain-integer corroborator (same 47, low overlap) is KEPT via the integer path",
    )
    # Guard still holds for the plain-integer path: a bare integer coincidence with ZERO shared
    # distinctive words is rejected (not every span that merely contains 5,172 grounds the claim).
    _check(
        not corroborator_span_grounds_sentence(
            "5,172 agents were evaluated.",
            "Highway segment 5,172 was repaved last fiscal year.",
        ),
        "P1 plain-integer bare-number coincidence (no shared distinctive word) is still rejected",
    )
    # Guard still holds: a span MISSING one of the claim's integers does NOT ground it (mirrors
    # strict_verify's "EVERY standalone integer must appear in a cited span").
    _check(
        not corroborator_span_grounds_sentence(
            "5,172 agents across 47 occupations were evaluated.",
            "An independent benchmark covered 5,172 distinct agents.",  # has 5,172 + 1 word, NOT 47
        ),
        "P1 plain-integer claim is NOT grounded when the span misses an asserted integer (47)",
    )


def test_p1_1_contract_path_no_section_wide_reattachment() -> None:
    print("[8] P1#1 — contract (benchmark) render path: a corro numbered via S2 is NOT glued to S1")
    # THE finding-#1 scenario, driven through the EXTRACTED contract slot-regroup decision
    # (contract_sentence_citation_nums — the exact per-sentence attachment the benchmark path
    # runs). Two sentences in ONE cluster:
    #   S1 cites own-token eid_a (a DISPLACEMENT claim).
    #   S2 cites own-token eid_b (a WAGE claim).
    #   corroborator eid_c grounds S2's wage claim but NOT S1's displacement claim.
    # ev_to_num is SECTION-WIDE: eid_c earns a number via S2. Pre-fix, the bare
    # verified_corroborators_for_tokens re-added eid_c to S1 too (cluster membership, no span
    # check) -> mis-attribution. Post-fix the claim-local-span filter rejects eid_c on S1.
    span_a = "AI exposure raises occupational displacement risk for clerical workers in our index."
    span_b = "Average hourly wage compression of two percent followed automation adoption in retail."
    span_c = "We corroborate the same hourly wage compression after automation adoption in retail."
    evidence_pool = {
        "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
        "eid_b": {"direct_quote": span_b, "statement": span_b, "source_url": "u/b", "tier": "T1"},
        "eid_c": {"direct_quote": span_c, "statement": span_c, "source_url": "u/c", "tier": "T1"},
    }
    members = [
        _Member("eid_a", "SUPPORTS", span_a),
        _Member("eid_b", "SUPPORTS", span_b),
        _Member("eid_c", "SUPPORTS", span_c),
    ]
    basket_by_cluster = _basket_map(members)
    cluster_id_by_evidence = {"eid_a": ["cl_1"], "eid_b": ["cl_1"], "eid_c": ["cl_1"]}
    basket_supports_by_cluster = build_basket_supports_by_cluster(basket_by_cluster)

    # Section-wide bibliography numbering, as the contract regroup builds it (one section).
    ev_to_num = {"eid_a": 1, "eid_b": 2, "eid_c": 3}

    sv_s1 = _sv(
        "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60].",
        "eid_a", 0, 60,
    )
    sv_s2 = _sv(
        "Average hourly wage compression of two percent followed automation adoption [#ev:eid_b:0-60].",
        "eid_b", 0, 60,
    )

    def _nums(sv, own_eid):
        return contract_sentence_citation_nums(
            sv, [ProvenanceToken(evidence_id=own_eid, start=0, end=60, raw="")], ev_to_num,
            basket_supports_by_cluster=basket_supports_by_cluster,
            cluster_id_by_evidence=cluster_id_by_evidence,
            evidence_pool=evidence_pool,
            basket_by_cluster=basket_by_cluster,
        )

    s2_nums = _nums(sv_s2, "eid_b")   # S2: eid_c grounds S2's wage claim -> 3 SHOULD appear here
    s1_nums = _nums(sv_s1, "eid_a")   # S1: eid_c does NOT ground S1's displacement claim
    print(f"      S1 nums={s1_nums}  S2 nums={s2_nums}  (eid_c -> num 3)")
    _check(1 in s1_nums, "P1#1 S1 keeps its own true grounder eid_a (num 1)")
    _check(
        3 not in s1_nums,
        "P1#1 contract path does NOT glue eid_c (num 3, earned via S2) onto S1 (no re-attachment)",
    )
    _check(
        3 in s2_nums,
        "P1#1 the corroborator IS attached where it genuinely grounds (S2) — not over-dropped",
    )


def test_p1_multi_cluster_same_eid_uses_selected_cluster_span() -> None:
    print("[9] P1 multi-cluster — same eid in 2 clusters w/ DIFFERENT spans: SELECTED cluster wins")
    # THE multi-cluster span defect (#1289 P1). One corroborator eid_c is a SUPPORTS member of
    # BOTH clusters, but with DIFFERENT claim-local direct_quote spans:
    #   - in cl_disp (displacement) its stored span is OFF the displacement claim (a page header),
    #   - in cl_wage (wage)         its stored span is ON the wage claim.
    # Sentence S1 cites own-token eid_a (single-cluster cl_disp) -> eid_c is selected THROUGH
    #   cl_disp -> its cl_disp span is off-claim -> eid_c must be DROPPED from S1.
    # Sentence S2 cites own-token eid_b (single-cluster cl_wage) -> eid_c is selected THROUGH
    #   cl_wage -> its cl_wage span is on-claim -> eid_c must be KEPT on S2.
    # A GLOBAL first-match span lookup (the pre-fix bug) would read ONE of the two spans for BOTH
    # sentences, so it could NOT satisfy both directions at once. Passing both proves the filter
    # reads the SELECTED cluster's span. Driven end-to-end through the resolver (the cluster is
    # actually selected there), not a bare unit call.
    span_a = "AI exposure raises occupational displacement risk for clerical workers in our index."
    span_b = "Average hourly wage compression of two percent followed automation adoption in retail."
    # eid_c's TWO claim-local spans, one per cluster it belongs to:
    span_c_in_disp = "Download files. Version 2. Submitted March 2026. Copyright retained."  # OFF displacement
    span_c_in_wage = "We corroborate the same hourly wage compression after automation adoption in retail."  # ON wage
    # The evidence_pool row for eid_c is irrelevant to grounding (the member span is consulted),
    # but must exist so the member resolves. Use a neutral row.
    evidence_pool = {
        "eid_a": {"direct_quote": span_a, "statement": span_a, "source_url": "u/a", "tier": "T1"},
        "eid_b": {"direct_quote": span_b, "statement": span_b, "source_url": "u/b", "tier": "T1"},
        "eid_c": {"direct_quote": span_c_in_wage, "statement": span_c_in_wage, "source_url": "u/c", "tier": "T1"},
    }
    # Two baskets, eid_c a SUPPORTS member of BOTH with DIFFERENT direct_quote spans.
    basket_disp = _Basket(
        "cl_disp",
        [_Member("eid_a", "SUPPORTS", span_a), _Member("eid_c", "SUPPORTS", span_c_in_disp)],
    )
    basket_wage = _Basket(
        "cl_wage",
        [_Member("eid_b", "SUPPORTS", span_b), _Member("eid_c", "SUPPORTS", span_c_in_wage)],
    )
    baskets = [basket_disp, basket_wage]
    # Own tokens are single-cluster; eid_c maps to BOTH clusters (multi-cluster source).
    cluster_id_by_evidence = {
        "eid_a": ["cl_disp"],
        "eid_b": ["cl_wage"],
        "eid_c": ["cl_disp", "cl_wage"],
    }

    sv_s1 = _sv(
        "AI exposure raises occupational displacement risk for clerical workers [#ev:eid_a:0-60].",
        "eid_a", 0, 60,
    )
    sv_s2 = _sv(
        "Average hourly wage compression of two percent followed automation adoption [#ev:eid_b:0-60].",
        "eid_b", 0, 60,
    )
    _t1, cited_s1 = _render(sv_s1, evidence_pool, baskets, cluster_id_by_evidence)
    _t2, cited_s2 = _render(sv_s2, evidence_pool, baskets, cluster_id_by_evidence)
    print(f"      S1 cited={sorted(cited_s1)}  S2 cited={sorted(cited_s2)}")
    # S1: own grounder kept; eid_c DROPPED on its OFF-claim cl_disp span (selected cluster).
    _check("eid_a" in cited_s1, "P1 multi-cluster S1 keeps own grounder eid_a")
    _check(
        "eid_c" not in cited_s1,
        "P1 multi-cluster eid_c DROPPED from S1 (cl_disp span off-claim — selected cluster's span used)",
    )
    # S2: own grounder kept; eid_c KEPT on its ON-claim cl_wage span (selected cluster).
    _check("eid_b" in cited_s2, "P1 multi-cluster S2 keeps own grounder eid_b")
    _check(
        "eid_c" in cited_s2,
        "P1 multi-cluster eid_c KEPT on S2 (cl_wage span on-claim — selected cluster's span used)",
    )


def main() -> int:
    print(f"MIN_CONTENT_WORD_OVERLAP = {MIN_CONTENT_WORD_OVERLAP}")
    test_predicate_unit()
    test_resolver_behavioral()
    test_only_own_token_when_all_corro_off_claim()
    test_real_corpus_anchor()
    test_p1_2_reads_claim_local_member_span_not_pool_row()
    test_p1_3_relevance_guard_never_strands_with_ungrounded_corro()
    test_p1_4_integer_percent_corroborator_kept()
    test_p1_plain_integer_only_corroborator_kept()
    test_p1_1_contract_path_no_section_wide_reattachment()
    test_p1_multi_cluster_same_eid_uses_selected_cluster_span()
    print()
    if _FAILURES:
        print(f"HARNESS FAILED — {len(_FAILURES)} assertion(s) regressed:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("HARNESS PASSED — citation mis-attribution filter behaves correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
