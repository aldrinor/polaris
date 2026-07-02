"""I-deepfix-001 (#1344) provenance_repair — offline RED->GREEN tests.

Wires the no-provenance-token leak repair into the LLM ``_call_section`` else-branch via the new
``_repair_llm_draft_untokened`` helper, called in ``_run_section`` AFTER ``_rewrite_draft_with_spans``
and BEFORE ``strict_verify``, guarded by ``if not _draft_directly_tokened``.

Offline: no GPU, no network, no paid LLM. The inner production repair (``repair_untokened_sentence``)
is monkeypatched with a deterministic stub mimicking its contract (tokened sentence returned unchanged;
untokened sentence rebound to a verified basket clause). The FROZEN faithfulness engine
(strict_verify / NLI / provenance / span-grounding) is neither imported for edit nor modified.
"""
from __future__ import annotations

import inspect

import src.polaris_graph.generator.multi_section_generator as msg


def _stub_repair(sentence, baskets, evidence_pool, *, writer_fn, verify_fn):
    """Mimic repair_untokened_sentence: a tokened sentence is returned unchanged; an untokened
    sentence is rebound to a basket's verified [#ev]-carrying clause."""
    if "[#ev:" in sentence:
        return sentence
    return "Rebound verified clause. [#ev:e1:0-24]"


def test_untokened_sentence_rebound_to_verified_basket_clause(monkeypatch):
    """An untokened LLM sentence is REPLACED by the basket's verified clause (RED pre-fix:
    the helper did not exist so the else-branch never repaired -> strict_verify dropped it)."""
    monkeypatch.setattr(msg, "no_token_sentence_repair_enabled", lambda: True)
    monkeypatch.setattr(msg, "_section_baskets_for_compose", lambda *a, **k: ["basket"])
    monkeypatch.setattr(msg, "repair_untokened_sentence", _stub_repair)
    out = msg._repair_llm_draft_untokened(
        "An untokened model sentence about clinical outcomes in the cohort.",
        section=object(),
        credibility_analysis=object(),
        evidence_pool={},
    )
    assert "[#ev:e1:0-24]" in out
    assert "untokened model sentence" not in out


def test_already_tokened_sentence_left_untouched(monkeypatch):
    """A sentence that ALREADY carries a [#ev] token is returned unchanged (no rewording of
    already-verified prose)."""
    monkeypatch.setattr(msg, "no_token_sentence_repair_enabled", lambda: True)
    monkeypatch.setattr(msg, "_section_baskets_for_compose", lambda *a, **k: ["basket"])
    monkeypatch.setattr(msg, "repair_untokened_sentence", _stub_repair)
    tokened = "A grounded sentence with a real token. [#ev:e2:5-40]"
    out = msg._repair_llm_draft_untokened(
        tokened, section=object(), credibility_analysis=object(), evidence_pool={},
    )
    assert out == tokened


def test_noop_when_credibility_analysis_none(monkeypatch):
    """No baskets available (credibility_analysis None) => byte-identical no-op."""
    monkeypatch.setattr(msg, "no_token_sentence_repair_enabled", lambda: True)
    txt = "An untokened sentence that would otherwise be repaired here."
    out = msg._repair_llm_draft_untokened(
        txt, section=object(), credibility_analysis=None, evidence_pool={},
    )
    assert out == txt


def test_noop_when_no_baskets(monkeypatch):
    """A section with no consolidated baskets => byte-identical no-op."""
    monkeypatch.setattr(msg, "no_token_sentence_repair_enabled", lambda: True)
    monkeypatch.setattr(msg, "_section_baskets_for_compose", lambda *a, **k: [])
    txt = "An untokened sentence with no supporting basket to bind."
    out = msg._repair_llm_draft_untokened(
        txt, section=object(), credibility_analysis=object(), evidence_pool={},
    )
    assert out == txt


def test_noop_when_kill_switch_off(monkeypatch):
    """PG_NO_TOKEN_SENTENCE_REPAIR OFF => byte-identical no-op (LAW VI kill-switch)."""
    monkeypatch.setattr(msg, "no_token_sentence_repair_enabled", lambda: False)
    monkeypatch.setattr(msg, "_section_baskets_for_compose", lambda *a, **k: ["basket"])
    monkeypatch.setattr(msg, "repair_untokened_sentence", _stub_repair)
    txt = "An untokened sentence that stays as-is when the flag is off."
    out = msg._repair_llm_draft_untokened(
        txt, section=object(), credibility_analysis=object(), evidence_pool={},
    )
    assert out == txt


def test_run_section_wires_repair_before_strict_verify_guarded():
    """WIRING GUARD: _run_section calls _repair_llm_draft_untokened, guarded by
    `if not _draft_directly_tokened`, BEFORE strict_verify (RED pre-fix: call absent)."""
    src = inspect.getsource(msg._run_section)
    assert "_repair_llm_draft_untokened(" in src
    assert "if not _draft_directly_tokened:" in src
    call_idx = src.index("_repair_llm_draft_untokened(")
    sv_idx = src.index("strict_verify, rewritten, evidence_pool")
    assert call_idx < sv_idx, "repair must be wired BEFORE strict_verify"


def test_run_section_wires_repair_in_retry_path_before_strict_verify():
    """RETRY-PATH WIRING GUARD (P1#2): when the first pass falls below min_kept_fraction and the
    tighter retry WINS, the retry draft (``rewritten2``) must ALSO be run through
    ``_repair_llm_draft_untokened`` — guarded by the SAME ``if not _draft_directly_tokened:`` flag
    as the primary path — AFTER ``_rewrite_draft_with_spans`` and BEFORE the retry ``strict_verify``.

    RED pre-fix: the retry path went ``_rewrite_draft_with_spans(raw2) -> strict_verify`` directly
    with NO repair in between, so a winning retry could still drop untokened-but-groundable LLM
    prose as ``no_provenance_token`` (the drb_72 leak on the retry branch). There was exactly ONE
    repair call site (the primary path); the fix adds the second on the retry path."""
    src = inspect.getsource(msg._run_section)
    # BOTH the primary AND the retry draft must be repaired -> two call sites.
    assert src.count("_repair_llm_draft_untokened(") >= 2, (
        "retry path must ALSO call _repair_llm_draft_untokened (primary + retry = 2 sites)"
    )
    rewrite2_idx = src.index("rewritten2, _c2, _u2 = _rewrite_draft_with_spans")
    sv2_idx = src.index("strict_verify, rewritten2, evidence_pool")
    repair2_idx = src.index("_repair_llm_draft_untokened(", rewrite2_idx)
    assert rewrite2_idx < repair2_idx < sv2_idx, (
        "retry repair must be AFTER the retry rewrite and BEFORE the retry strict_verify"
    )
    # the retry repair must operate on the retry draft variable, not the primary one.
    assert "rewritten2" in src[repair2_idx:sv2_idx]


def test_retry_repair_is_unconditional_not_guarded_by_stale_flag():
    """P1#3: the RETRY repair must be UNCONDITIONAL — NOT re-guarded by the stale first-pass
    ``_draft_directly_tokened`` flag.

    A verified-compose PRIMARY pass sets ``_draft_directly_tokened`` True, but the tighter retry
    ALWAYS produces fresh LLM prose (it calls ``_call_section`` unconditionally). Guarding the retry
    repair on the first-pass flag therefore lets a verified-compose-primary -> LLM-retry draft SKIP
    ``_repair_llm_draft_untokened`` and fall straight into strict_verify, which drops an
    untokened-but-groundable retry sentence as ``no_provenance_token`` (the drb_72 leak on the retry
    branch). The repair is a no-op on already-tokened sentences, so unconditional is safe.

    RED pre-fix: ``if not _draft_directly_tokened:`` wrapped the retry repair call.
    GREEN: the guard is removed so every retry draft is repaired before its strict_verify."""
    src = inspect.getsource(msg._run_section)
    rewrite2_idx = src.index("rewritten2, _c2, _u2 = _rewrite_draft_with_spans")
    sv2_idx = src.index("strict_verify, rewritten2, evidence_pool")
    retry_block = src[rewrite2_idx:sv2_idx]
    assert "_repair_llm_draft_untokened(" in retry_block, (
        "retry path must still call _repair_llm_draft_untokened"
    )
    assert "if not _draft_directly_tokened:" not in retry_block, (
        "retry repair must be UNCONDITIONAL (P1#3): the stale first-pass "
        "`_draft_directly_tokened` guard must not gate the retry repair"
    )
