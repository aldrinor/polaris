"""Offline unit battery for the S2 line-level three-way select/drop reader
(``src/polaris_graph/retrieval/line_screen.py``). Stub LLM, NO OpenRouter key.

Covers Design 1 §6.4 lock-bar shapes: line splitting + short-line merge, deterministic
junk pre-pass, per-line KEEP/OFF_TOPIC/OUT_OF_SCOPE/JUNK verdicts, mixed-source partial
keep, fail-open (malformed verdict / LLM exception / count mismatch), whole-drop two-key +
marquee protection, sub-query anchor precedence + label rejection, explicit-scope activation
(armed vs inert, undated fail-open), and crash-resume checkpoint identity (LLM calls only for
the unscreened remainder).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.polaris_graph.retrieval import line_screen as ls

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "line_screen_corpus.json"
_QUESTION = "impact of Artificial Intelligence on the labor market and various industries"


def _load_fixture() -> tuple[str, list[dict]]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["question"], [dict(r) for r in data["evidence_for_gen"]]


def _row(rows: list[dict], eid: str) -> dict:
    return next(r for r in rows if r["evidence_id"] == eid)


# ── stub LLM factories (parse the numbered LINES block, verdict per rule) ──────
def _prompt_lines(prompt: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    src = prompt.splitlines()
    try:
        start = next(i for i, ln in enumerate(src) if ln.strip() == "LINES:") + 1
    except StopIteration:
        return out
    for ln in src[start:]:
        s = ln.strip()
        if not s or ":" not in s:
            continue
        idx_part, _, text = s.partition(":")
        if idx_part.strip().isdigit():
            out.append((int(idx_part.strip()), text.strip()))
    return out


def _stub_by_rule(rule):
    def _llm(prompt: str) -> str:
        return "\n".join(f"{i}: {rule(text)}" for i, text in _prompt_lines(prompt))
    return _llm


_CHROME = ("cookie", "consent", "subscribe", "sign in", "skip to", "share", "newsletter",
           "watch later", "accept all")


def _chrome_junk_rule(text: str) -> str:
    return ls.JUNK if any(h in text.lower() for h in _CHROME) else ls.KEEP


# ─────────────────────────────────────────────────────────────────────────────
# Flags / byte-identical-OFF
# ─────────────────────────────────────────────────────────────────────────────
def test_kill_switch_default_off(monkeypatch):
    monkeypatch.delenv(ls._ENV_ENABLED, raising=False)
    assert ls.line_screen_enabled() is False
    monkeypatch.setenv(ls._ENV_ENABLED, "1")
    assert ls.line_screen_enabled() is True


def test_scope_leg_default_off(monkeypatch):
    monkeypatch.delenv(ls._ENV_SCOPE, raising=False)
    assert ls.scope_leg_enabled() is False


# ─────────────────────────────────────────────────────────────────────────────
# Line splitting (V1)
# ─────────────────────────────────────────────────────────────────────────────
def test_split_empty_body():
    assert ls.split_line_units("") == []
    assert ls.split_line_units("   \n  \n") == []


def test_split_short_line_merges_into_neighbor(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "20")
    body = "This is a long enough first content line about AI and labor.\nshort\nAnother sufficiently long content line follows here."
    units = ls.split_line_units(body)
    # the 'short' line must have merged, not survive as its own unit
    assert not any(u.strip() == "short" for u in units)
    assert any("short" in u for u in units)


def test_split_leading_short_line_merges_forward(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "20")
    body = "hi\nThis is a sufficiently long content line about the labor market."
    units = ls.split_line_units(body)
    assert len(units) == 1
    assert units[0].startswith("hi ")


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic junk pre-pass (V2)
# ─────────────────────────────────────────────────────────────────────────────
def test_deterministic_junk_cookie_line():
    # a full SHELL_COOCCURRENCE class within one line ("we use cookies" + "accept all")
    assert ls._line_is_deterministic_junk("We use cookies. Accept all cookies to continue.") is True


def test_deterministic_junk_real_prose_kept():
    assert ls._line_is_deterministic_junk(
        "Automation displaces labor from tasks it previously performed."
    ) is False


# ─────────────────────────────────────────────────────────────────────────────
# Sub-query anchor (D2 precedence)
# ─────────────────────────────────────────────────────────────────────────────
def test_subquery_anchor_precedence():
    row = {"retrieval_subquery": "AI automation and wages", "query_origin": "domain_backend"}
    assert ls._row_subquery_anchor(row) == "AI automation and wages"
    assert ls._row_subquery_anchor({"query_origin": "labor market restructuring"}) == "labor market restructuring"
    assert ls._row_subquery_anchor({}) == ""


def test_usable_anchor_rejects_labels_and_short(monkeypatch):
    monkeypatch.setenv(ls._ENV_SUBQ_MIN_TOKENS, "3")
    assert ls._usable_subquery_anchor("domain_backend") is False
    assert ls._usable_subquery_anchor("need_type_backend") is False
    assert ls._usable_subquery_anchor("required_entity_retrieval anchor") is False
    assert ls._usable_subquery_anchor("two words") is False  # < 3 tokens
    assert ls._usable_subquery_anchor("impact of AI on jobs") is True


# ─────────────────────────────────────────────────────────────────────────────
# Parser fail-open + scope-token gating
# ─────────────────────────────────────────────────────────────────────────────
def test_parser_count_mismatch_fails_open():
    assert ls.parse_line_verdicts("0: KEEP", [0, 1], scope_offered=False) is None


def test_parser_out_of_scope_ignored_when_not_offered():
    # OUT_OF_SCOPE must map to KEEP when no scope block was offered (never fire w/o armed scope)
    parsed = ls.parse_line_verdicts("0: OUT_OF_SCOPE", [0], scope_offered=False)
    assert parsed == {0: ls.KEEP}
    parsed2 = ls.parse_line_verdicts("0: OUT_OF_SCOPE", [0], scope_offered=True)
    assert parsed2 == {0: ls.OUT_OF_SCOPE}


def test_parser_bare_drop_maps_offtopic():
    assert ls.parse_line_verdicts("0: DROP", [0], scope_offered=False) == {0: ls.OFF_TOPIC}


# ─────────────────────────────────────────────────────────────────────────────
# Per-source screen (V1-V5)
# ─────────────────────────────────────────────────────────────────────────────
def test_mixed_source_partial_keep(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    _, rows = _load_fixture()
    row = _row(rows, "mixed_wef_page")
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(_chrome_junk_rule))
    assert res.n_lines > 0
    assert 0 < res.n_kept < res.n_lines          # partial keep (lock bar c)
    assert len(res.dropped) >= 1
    assert res.whole_dropped is False
    # every dropped line is quoted
    assert all(d.get("quote") for d in res.dropped)
    # a real AI-labor prose line survives
    assert any("Fourth Industrial Revolution" in u or "complements high-skill" in u
               for u in res.kept_lines)


def test_clean_source_kept_fully(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    _, rows = _load_fixture()
    row = _row(rows, "clean_journal_paper")
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(lambda t: ls.KEEP))
    assert res.n_kept == res.n_lines
    assert res.dropped == []
    assert res.whole_dropped is False


def test_llm_exception_fails_open():
    _, rows = _load_fixture()
    row = _row(rows, "clean_journal_paper")

    def _raises(_prompt: str) -> str:
        raise RuntimeError("boom")

    res = ls.screen_source(row, _QUESTION, _raises)
    assert res.n_kept == res.n_lines  # kept unscreened (fail-open)
    assert res.dropped == []


def test_malformed_verdict_fails_open():
    _, rows = _load_fixture()
    row = _row(rows, "clean_journal_paper")
    res = ls.screen_source(row, _QUESTION, lambda _p: "garbage with no verdict lines")
    assert res.n_kept == res.n_lines
    assert res.dropped == []


# ─────────────────────────────────────────────────────────────────────────────
# Whole-drop two-key (V5) + marquee protection
# ─────────────────────────────────────────────────────────────────────────────
def test_whole_drop_offtopic_with_concurring_stamp():
    _, rows = _load_fixture()
    row = _row(rows, "offsubject_stamped")  # carries topic_off_subject=True
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(lambda t: ls.OFF_TOPIC))
    assert res.n_kept == 0
    assert res.whole_dropped is True
    assert res.whole_drop_reason.startswith("off_topic")


def test_no_whole_drop_without_concurring_stamp_disagreement_restores():
    _, rows = _load_fixture()
    row = _row(rows, "clean_journal_paper")  # NO topic_off_subject stamp
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(lambda t: ls.OFF_TOPIC))
    # 100% off_topic lines but no concurring whole-source key ⇒ fail-open keep-all
    assert res.whole_dropped is False
    assert res.disagreement is True
    assert res.n_kept == res.n_lines


def test_marquee_never_whole_dropped():
    _, rows = _load_fixture()
    row = _row(rows, "marquee_anchor_chrome")
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(lambda t: ls.JUNK))
    assert res.whole_dropped is False          # marquee protected (lock bar b)
    assert res.disagreement is True
    assert res.n_kept == res.n_lines


# ─────────────────────────────────────────────────────────────────────────────
# Explicit scope (V3) — armed vs inert, undated fail-open (lock bar d)
# ─────────────────────────────────────────────────────────────────────────────
def test_scope_inert_by_default_zero_out_of_scope(monkeypatch):
    monkeypatch.delenv(ls._ENV_SCOPE, raising=False)
    _, rows = _load_fixture()
    row = _row(rows, "dated_2019_paper")
    scope = ls.build_scope_from_dict({"date_start": "2023-01"})  # armed spec...
    # ...but scope leg kill-switch OFF ⇒ inert ⇒ no source scope drop
    assert scope.is_active() is False
    assert ls._source_out_of_scope_reason(row, scope) == ""


def test_scope_armed_drops_out_of_window(monkeypatch):
    monkeypatch.setenv(ls._ENV_SCOPE, "1")
    _, rows = _load_fixture()
    scope = ls.build_scope_from_dict({"date_start": "2023-01"})
    assert scope.armed is True and scope.is_active() is True
    # 2019 paper is out of the since-2023 window ⇒ source-level out_of_scope
    r2019 = _row(rows, "dated_2019_paper")
    assert ls._source_out_of_scope_reason(r2019, scope) == "date_window"
    res = ls.screen_source(r2019, _QUESTION, _stub_by_rule(lambda t: ls.KEEP), scope=scope)
    assert res.whole_dropped is True
    assert res.whole_drop_reason == "out_of_scope:date_window"
    # undated paper is KEPT (fail-open)
    rund = _row(rows, "undated_paper")
    assert ls._source_out_of_scope_reason(rund, scope) == ""
    res2 = ls.screen_source(rund, _QUESTION, _stub_by_rule(lambda t: ls.KEEP), scope=scope)
    assert res2.whole_dropped is False


def test_scope_from_question_journal_and_language():
    q = "Write a review. Ensure the review only cites high-quality, English-language journal articles."
    scope = ls.build_scope_from_question(q)
    assert scope.armed is True
    assert scope.journal_only is True


# ─────────────────────────────────────────────────────────────────────────────
# Corpus screen + crash-resume checkpoint (V6/V7)
# ─────────────────────────────────────────────────────────────────────────────
def test_corpus_screen_and_resume_identity(tmp_path, monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    q, rows = _load_fixture()
    ckpt = tmp_path / "line_screen_verdicts.jsonl"

    calls = {"n": 0}

    def _counting(prompt: str) -> str:
        calls["n"] += 1
        return _stub_by_rule(_chrome_junk_rule)(prompt)

    first = ls.screen_corpus(rows, q, _counting, parallel=1, checkpoint_path=ckpt)
    assert first.n_sources == len(rows)
    assert first.n_screened_llm == len(rows)
    assert first.n_replayed == 0
    calls_after_first = calls["n"]
    assert calls_after_first > 0
    assert ckpt.is_file()

    # resume: same checkpoint ⇒ every source replayed, ZERO new LLM calls
    second = ls.screen_corpus(rows, q, _counting, parallel=1, checkpoint_path=ckpt)
    assert second.n_replayed == len(rows)
    assert second.n_screened_llm == 0
    assert calls["n"] == calls_after_first  # no additional LLM calls on resume

    # identical verdict map (kept counts per source)
    m1 = {r.evidence_id: r.n_kept for r in first.results}
    m2 = {r.evidence_id: r.n_kept for r in second.results}
    assert m1 == m2


def test_checkpoint_header_mismatch_rescreens(tmp_path, monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    q, rows = _load_fixture()
    ckpt = tmp_path / "v.jsonl"
    ls.screen_corpus(rows, q, _stub_by_rule(_chrome_junk_rule), parallel=1, checkpoint_path=ckpt)
    # a DIFFERENT question ⇒ header mismatch ⇒ ignore file ⇒ re-screen fresh
    second = ls.screen_corpus(
        rows, "a completely different research question about oncology",
        _stub_by_rule(_chrome_junk_rule), parallel=1, checkpoint_path=ckpt)
    assert second.n_replayed == 0
    assert second.n_screened_llm == len(rows)


def test_parallel_determinism(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    q, rows = _load_fixture()
    a = ls.screen_corpus(rows, q, _stub_by_rule(_chrome_junk_rule), parallel=1)
    b = ls.screen_corpus(rows, q, _stub_by_rule(_chrome_junk_rule), parallel=8)
    ma = {r.evidence_id: (r.n_kept, len(r.dropped), r.whole_dropped) for r in a.results}
    mb = {r.evidence_id: (r.n_kept, len(r.dropped), r.whole_dropped) for r in b.results}
    assert ma == mb


def test_apply_result_rewrites_body(monkeypatch):
    monkeypatch.setenv(ls._ENV_MIN_LINE_CHARS, "10")
    _, rows = _load_fixture()
    row = _row(rows, "mixed_wef_page")
    res = ls.screen_source(row, _QUESTION, _stub_by_rule(_chrome_junk_rule))
    new_row = ls.apply_result_to_row(row, res)
    assert new_row is not row                      # pure — never mutates input
    assert "line_screen" in new_row
    assert new_row["line_screen"]["n_dropped"] == len(res.dropped)
    # dropped chrome no longer in the rewritten body
    assert "Accept all cookies" not in new_row.get("direct_quote", "")
