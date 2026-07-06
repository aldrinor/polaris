"""I-deepfix-001 Wave-1a (#1344) — SYNTH_PRIMARY: group-writer contract + bounded repair + labeled block.

RED/GREEN offline proof for the compose-then-verify Wave-1a build. Pure unit test — NO real LLM, NO
GPU, NO network: the writer is a STUB callable, the verifier is a STUB returning real
``SentenceVerification`` dataclasses (so the stricter ``make_writer_verify_fn`` wrapper's
``dataclasses.replace`` works unchanged), and every path is exercised with in-memory baskets.

The five required proofs (wave1a_brief.md "Required tests"):
  1. OFF byte-identical — with ``PG_SYNTH_PRIMARY`` unset ``_compose_one_basket`` is byte-identical on
     (a) an all-pass draft, (b) a first-sentence-fails draft (legacy K-span glue), (c) a no-verified-span
     basket (disclosure). Also: SYNTH ON but no ``redraft_fn`` threaded still takes the legacy path (the
     AND guard).
  2. ON group contract — ``group_mode=True`` prompt carries the connected-paragraph lead + ALL spans and
     tokens; ``_WRITER_SYSTEM_GROUP`` is a distinct group contract (selected by ``_call_writer``).
  3. ON bounded repair — a stub writer failing sentence 2 on attempt 1 and passing on attempt 2 yields a
     body with BOTH sentences; the attempt count is respected; ``PG_WRITER_REPAIR_MAX=0`` => no repair.
  4. ON labeled fallback — after the repair budget exhausts, the body is the verified authored
     sentence(s) and the uncovered-fact K-span renders as a SEPARATE ``\\n\\n`` labeled disclosure
     paragraph (ARM-B routed), NEVER the mid-line ``" ".join(kept + [fallback])`` glue; the failed
     AUTHORED sentence is absent.
  5. Faithfulness wrapper — the stricter ``make_writer_verify_fn`` wrapper is applied UNCHANGED on the ON
     path (a transport ``judge_error`` is forced fail-closed), a token-less sentence never survives the
     region gate, and the labeled K-span carries a real ``[#ev]`` token (region-safe by construction).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import src.polaris_graph.generator.abstractive_writer as abstractive_writer_mod
from src.polaris_graph.generator.abstractive_writer import (
    _WRITER_SYSTEM,
    _WRITER_SYSTEM_GROUP,
    _build_writer_prompt,
    abstractive_pre_pass,
    make_writer_verify_fn,
)
from src.polaris_graph.generator.provenance_generator import SentenceVerification
from src.polaris_graph.generator.verified_compose import (
    _UNCOVERED_FACT_DISCLOSURE_PREFIX,
    _compose_one_basket,
    build_verified_span_draft_multi,
    partition_composed_disclosures,
    render_degraded_disclosures,
)

_FAIL_MARKER = "FAILMEPLEASE"


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────
def _member(eid: str, quote: str, weight: float = 1.0):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict="SUPPORTS",
        credibility_weight=weight,
        supporting_members=None,
    )


def _basket(members, subject="AI and labor market outcomes", cluster_id="clust_1"):
    return SimpleNamespace(
        supporting_members=members,
        subject=subject,
        claim_text=subject,
        claim_cluster_id=cluster_id,
    )


def _pool(*members):
    return {m.evidence_id: {"direct_quote": m.direct_quote} for m in members}


def _tok(eid: str, quote: str) -> str:
    """The member's canonical WHOLE-span token: its global span in the pool is (0, len(quote))."""
    return f"[#ev:{eid}:0-{len(quote)}]"


def _line(text: str, eid: str, quote: str) -> str:
    """A draft sentence: paraphrase text + the member's exact whole-span token (within its region)."""
    return f"{text} {_tok(eid, quote)}."


def _sv(sentence: str, *, is_verified: bool, reasons=None, judge_error: bool = False):
    return SentenceVerification(
        sentence=sentence,
        tokens=[],
        is_verified=is_verified,
        failure_reasons=list(reasons or []),
        judge_error=judge_error,
    )


def _stub_verify(sentence, _scoped_pool, *args, **kwargs):
    """PASS every sentence that does NOT carry the fail marker (the region gate — real, not stubbed —
    then gates the token). A sentence carrying the marker is a strict_verify FAIL."""
    if _FAIL_MARKER in sentence:
        return _sv(sentence, is_verified=False, reasons=["stub_entailment_fail"])
    return _sv(sentence, is_verified=True)


# ── 1. OFF byte-identical ───────────────────────────────────────────────────────────────────────
def test_off_all_pass_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_SYNTH_PRIMARY", raising=False)
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)
    sentence = _line("Automation cut factory employment by two percentage points", "eva", quote)

    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: sentence, verify_fn=_stub_verify,
    )
    assert out == sentence  # kept + not fell_back => " ".join(kept) == the single verified sentence


def test_off_first_fails_falls_back_to_kspan(monkeypatch):
    monkeypatch.delenv("PG_SYNTH_PRIMARY", raising=False)
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)
    bad = _line(f"{_FAIL_MARKER} this sentence fails", "eva", quote)

    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: bad, verify_fn=_stub_verify,
    )
    # Legacy: first-failure break, kept empty => the basket's own verbatim K-span (the multi fallback,
    # sub-topic decomposition default-ON). Byte-identical to calling the K-span builder directly.
    assert out == build_verified_span_draft_multi(basket, pool)
    assert _FAIL_MARKER not in out
    assert "[#ev:eva:" in out


def test_off_no_verified_span_is_disclosure(monkeypatch):
    monkeypatch.delenv("PG_SYNTH_PRIMARY", raising=False)
    m = _member("evmissing", "Some fact that never resolves in the pool.")
    basket = _basket([m])
    # Empty pool => no member resolves => K-span None => the honest gap disclosure.
    out = _compose_one_basket(
        basket, {}, writer_fn=lambda _b, _p: "", verify_fn=_stub_verify,
    )
    assert out.startswith("[insufficient verified evidence")


def test_synth_on_but_no_redraft_still_legacy(monkeypatch):
    """The ON path requires BOTH the flag AND a threaded redraft_fn — flag alone keeps the legacy
    body byte-identical (redraft_fn defaults None)."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)
    sentence = _line("Automation cut factory employment by two percentage points", "eva", quote)
    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: sentence, verify_fn=_stub_verify,
    )
    assert out == sentence  # no redraft_fn => legacy path even with the flag ON


# ── 2. ON group contract ──────────────────────────────────────────────────────────────────────────
def test_group_prompt_contract_and_system():
    q1 = "Automation displaced routine manufacturing tasks over the decade."
    q2 = "Reinstatement effects created new labor tasks in services."
    m1, m2 = _member("eva", q1), _member("evb", q2)
    pool = _pool(m1, m2)
    members = [m1, m2]

    group = _build_writer_prompt(members, pool, group_mode=True)
    single = _build_writer_prompt(members, pool, group_mode=False)

    # group lead is the connected-paragraph instruction; single lead is byte-identical to legacy.
    assert group.startswith("Write ONE connected paragraph covering ALL the verified spans below")
    assert single.startswith("Rewrite each verified evidence span below into ONE clean")
    assert "connected paragraph" not in single

    # spans + tokens block is UNCHANGED across modes (both carry every member's SPAN i / TOKEN i).
    for i, m in enumerate(members, start=1):
        span_line = f"SPAN {i}: {m.direct_quote}"
        token_line = f"TOKEN {i} (append verbatim to sentence {i}): {_tok(m.evidence_id, m.direct_quote)}"
        assert span_line in group and span_line in single
        assert token_line in group and token_line in single

    # _WRITER_SYSTEM_GROUP is a DISTINCT group contract selected by _call_writer on group_mode=True.
    assert _WRITER_SYSTEM_GROUP != _WRITER_SYSTEM
    assert "one coherent, connected multi-sentence narrative" in _WRITER_SYSTEM_GROUP.lower()
    assert "never merge two spans' numbers into a new aggregate" in _WRITER_SYSTEM_GROUP
    # the shared faithfulness rules are preserved verbatim in the group contract.
    assert "You NEVER add a fact that is not in a provided span." in _WRITER_SYSTEM_GROUP
    assert "copy every number" in _WRITER_SYSTEM_GROUP.lower()


# ── 3. ON bounded repair ──────────────────────────────────────────────────────────────────────────
def _two_member_basket():
    q1 = "Automation displaced routine manufacturing tasks over the decade."
    q2 = "Reinstatement effects created new labor tasks in the services sector."
    m1, m2 = _member("eva", q1), _member("evb", q2)
    return _basket([m1, m2]), _pool(m1, m2), q1, q2


def test_on_bounded_repair_recovers_second_sentence(monkeypatch):
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")  # isolate repair from the chrome screen
    basket, pool, q1, q2 = _two_member_basket()

    s1 = _line("Automation displaced routine manufacturing tasks", "eva", q1)
    s2_bad = _line(f"{_FAIL_MARKER} reinstatement created new tasks", "evb", q2)
    s2_good = _line("Reinstatement effects created new services tasks", "evb", q2)

    calls = {"n": 0}

    def _writer(_b, _p):
        return f"{s1} {s2_bad}"

    def _redraft(_b, _p, *, revise_reasons=None):
        calls["n"] += 1
        assert revise_reasons and "stub_entailment_fail" in revise_reasons  # RARR reasons fed back
        return f"{s1} {s2_good}"

    out = _compose_one_basket(
        basket, pool, writer_fn=_writer, verify_fn=_stub_verify, redraft_fn=_redraft,
    )
    assert calls["n"] == 1  # one repair attempt was enough
    assert s1 in out and s2_good in out
    assert _FAIL_MARKER not in out  # the failed authored sentence was discarded
    assert "\n\n" not in out  # all covered => a single body paragraph, no labeled block


def test_on_repair_max_zero_disables_repair(monkeypatch):
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool, q1, q2 = _two_member_basket()

    s1 = _line("Automation displaced routine manufacturing tasks", "eva", q1)
    s2_bad = _line(f"{_FAIL_MARKER} reinstatement created new tasks", "evb", q2)

    calls = {"n": 0}

    def _redraft(_b, _p, *, revise_reasons=None):
        calls["n"] += 1
        return f"{s1} {s2_bad}"

    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: f"{s1} {s2_bad}",
        verify_fn=_stub_verify, redraft_fn=_redraft,
    )
    assert calls["n"] == 0  # MAX=0 => a single draft, no repair
    # body (s1) survives; the uncovered fact renders as a SEPARATE labeled block; the failure is gone.
    assert s1 in out
    assert _FAIL_MARKER not in out
    assert f"\n\n{_UNCOVERED_FACT_DISCLOSURE_PREFIX}" in out


# ── 4. ON labeled fallback (separate paragraph, never mid-line glue) ───────────────────────────────
def test_on_exhaustion_labeled_block_is_separate_paragraph(monkeypatch):
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "2")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool, q1, q2 = _two_member_basket()

    s1 = _line("Automation displaced routine manufacturing tasks", "eva", q1)
    s2_bad = _line(f"{_FAIL_MARKER} reinstatement created new tasks", "evb", q2)

    calls = {"n": 0}

    def _redraft(_b, _p, *, revise_reasons=None):
        calls["n"] += 1
        return f"{s1} {s2_bad}"  # never recovers => budget exhausts

    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: f"{s1} {s2_bad}",
        verify_fn=_stub_verify, redraft_fn=_redraft,
    )
    assert calls["n"] == 2  # exactly PG_WRITER_REPAIR_MAX attempts, then stop (finite cap)

    # the unit is body-paragraph THEN a SEPARATE \n\n labeled K-span paragraph (never mid-line glue).
    assert "\n\n" in out
    paragraphs = out.split("\n\n")
    assert paragraphs[0] == s1  # body is exactly the verified authored sentence, nothing glued in
    assert paragraphs[1].startswith(_UNCOVERED_FACT_DISCLOSURE_PREFIX)
    assert _FAIL_MARKER not in out  # the failed AUTHORED sentence never ships

    # ARM-B routing: partition holds the labeled K-span aside; render re-appends it as its own paragraph.
    real, disclosures = partition_composed_disclosures([out])
    assert real == [s1]
    assert len(disclosures) == 1 and disclosures[0].startswith(_UNCOVERED_FACT_DISCLOSURE_PREFIX)
    rendered = render_degraded_disclosures("VERIFIED BODY PROSE", disclosures)
    assert rendered == "VERIFIED BODY PROSE\n\n" + disclosures[0]
    # Fable P1 (raw-[#ev]-leak fix): the appended LABELED BLOCK is MARKER-LESS like every sibling ARM-B
    # disclosure — the raw provenance token is stripped so no unresolvable [#ev:...] ships in report.md
    # (it is appended AFTER the [N] resolver ran). The verbatim source span text survives, marker-less.
    # (The BODY paragraph legitimately KEEPS its token — it flows through strict_verify -> [N] resolution.)
    assert "[#ev:" not in disclosures[0]
    assert "[#ev:" not in paragraphs[1]
    assert q1.rstrip(".") in disclosures[0]  # the verbatim uncovered-fact span text is preserved


def test_partition_is_byte_identical_without_paragraph_break():
    """A plain composed unit (no \\n\\n) routes exactly as before — the fast path is byte-identical."""
    units = ["Real prose sentence one [#ev:eva:0-5].", "[verification incomplete: judge outage]"]
    real, disclosures = partition_composed_disclosures(units)
    assert real == ["Real prose sentence one [#ev:eva:0-5]."]
    assert disclosures == ["[verification incomplete: judge outage]"]


# ── 5. Faithfulness wrapper applied unchanged on the ON path ───────────────────────────────────────
def test_writer_wrapper_forces_judge_error_fail_closed():
    """The stricter make_writer_verify_fn wrapper (P1-1) is byte-untouched: a transport judge_error is
    forced is_verified=False even though the base verifier advisory-kept it True."""
    def _base(sentence, _pool, *a, **k):
        # advisory-keep True but mark the durable transport judge_error (the I-arch-010 default).
        return _sv(sentence, is_verified=True, judge_error=True)

    wrapped = make_writer_verify_fn(_base)
    res = wrapped("Some paraphrase [#ev:eva:0-10].", {})
    assert res.is_verified is False
    assert "writer_judge_error_fail_closed" in res.failure_reasons


def test_on_path_applies_wrapper_and_rejects_unfaithful(monkeypatch):
    """On the SYNTH_PRIMARY ON path the wrapped verify_fn rejects a judge_error sentence, so it is NOT
    kept; the body is empty and the basket's verbatim K-span renders as the MARKER-LESS labeled block
    (Fable P1: the raw [#ev] token is stripped so nothing unresolvable ships). A token-less sentence
    also never survives the own-region gate."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "1")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)

    paraphrase = _line("Automation slashed factory employment sharply", "eva", quote)

    def _base(sentence, _pool, *a, **k):
        return _sv(sentence, is_verified=True, judge_error=True)  # transport judge_error

    verify_fn = make_writer_verify_fn(_base)

    out = _compose_one_basket(
        basket, pool,
        writer_fn=lambda _b, _p: paraphrase,
        verify_fn=verify_fn,
        redraft_fn=lambda _b, _p, *, revise_reasons=None: paraphrase,  # never recovers
    )
    # the judge_error paraphrase was rejected by the wrapper => never in the body; body empty => the
    # labeled K-span IS the unit (pure disclosure), MARKER-LESS (Fable P1: no raw [#ev] token ships).
    assert out.startswith(_UNCOVERED_FACT_DISCLOSURE_PREFIX)
    assert "Automation slashed factory employment sharply" not in out
    assert "[#ev:" not in out
    assert quote.rstrip(".") in out  # the verbatim source span survives, marker-less


def test_tokenless_sentence_never_survives_region_gate(monkeypatch):
    """The real own-region gate rejects a sentence with NO provenance token (fail-closed) even when the
    stub verifier says is_verified=True — so ungrounded prose never ships on the ON path."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "0")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)

    tokenless = "Automation slashed factory employment with no citation."
    out = _compose_one_basket(
        basket, pool,
        writer_fn=lambda _b, _p: tokenless,
        verify_fn=_stub_verify,  # says verified, but the region gate has the final say
        redraft_fn=lambda _b, _p, *, revise_reasons=None: tokenless,
    )
    assert tokenless not in out  # rejected by the own-region gate (no token)
    assert out.startswith(_UNCOVERED_FACT_DISCLOSURE_PREFIX)


# ── dual-gate iter-1 fix regressions ──────────────────────────────────────────────────────────────
def test_empty_redraft_preserves_verified_sentences(monkeypatch):
    """Codex P0 / Fable P1: an EMPTY re-draft (a 429 storm / a wedged writer abandoned by the async
    bridge) must NOT overwrite the prior attempt's verified sentences with nothing. The verified
    authored body survives to the exhaustion path (body + labeled K-span), never collapsing to a bare
    disclosure-only unit."""
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "1")
    monkeypatch.setenv("PG_WRITER_REPAIR_MAX", "2")
    monkeypatch.setenv("PG_RENDER_CHROME_PROSE_SCREEN", "0")
    basket, pool, q1, q2 = _two_member_basket()

    s1 = _line("Automation displaced routine manufacturing tasks", "eva", q1)
    s2_bad = _line(f"{_FAIL_MARKER} reinstatement created new tasks", "evb", q2)

    calls = {"n": 0}

    def _redraft(_b, _p, *, revise_reasons=None):
        calls["n"] += 1
        return ""  # empty re-draft (simulated 429 / abandoned worker)

    out = _compose_one_basket(
        basket, pool, writer_fn=lambda _b, _p: f"{s1} {s2_bad}",
        verify_fn=_stub_verify, redraft_fn=_redraft,
    )
    assert calls["n"] == 1  # broke on the first empty re-draft (did not burn all attempts)
    assert s1 in out  # the prior attempt's verified sentence SURVIVED (not collapsed to nothing)
    assert _FAIL_MARKER not in out
    assert f"\n\n{_UNCOVERED_FACT_DISCLOSURE_PREFIX}" in out  # uncovered fact still disclosed, separate


def test_keystone_group_writer_fires_on_attempt_zero(monkeypatch):
    """Codex P1 / Fable P1 KEYSTONE: under PG_SYNTH_PRIMARY the pre-pass attempt-0 draft uses the GROUP
    contract (group_mode=True threaded through abstractive_pre_pass -> _pre_pass_one_basket ->
    _call_writer), so the coherent-narrative writer actually fires on the first draft. OFF => group_mode
    is False (single-sentence-per-span, byte-identical). Offline: _call_writer is stubbed (no LLM)."""
    quote = "Robots reduced factory employment by two percentage points."
    m = _member("eva", quote)
    basket, pool = _basket([m]), _pool(m)
    seen = {}

    async def _stub_call_writer(members, evidence_pool, *, model, max_tokens,
                                reasoning_max_tokens, temperature,
                                revise_reasons=None, group_mode=False):
        seen["group_mode"] = group_mode
        first = members[0]
        return _line("Automation cut factory employment sharply",
                     first.evidence_id, first.direct_quote)

    monkeypatch.setattr(abstractive_writer_mod, "_call_writer", _stub_call_writer)

    # ON: attempt-0 must use the GROUP contract.
    out_on = asyncio.run(abstractive_pre_pass(
        [basket], pool, writer_verify_fn=_stub_verify, group_mode=True,
    ))
    assert seen["group_mode"] is True
    assert out_on.get("clust_1")  # the group draft was precomputed for this basket

    # OFF: attempt-0 stays single-sentence-per-span (byte-identical default).
    seen.clear()
    asyncio.run(abstractive_pre_pass([basket], pool, writer_verify_fn=_stub_verify))
    assert seen["group_mode"] is False
