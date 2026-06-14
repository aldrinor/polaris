"""I-arch-005 B13 (#1257) — conflict side-judge EMPTY-content guard + retry + conflict_unscored label.

The bug: ``json.loads(data["choices"][0]["message"]["content"])`` had no None/empty guard, so an empty
GLM response (the reasoning-model collapse) → ``json.loads(None)`` → broad except → under strict gates
a RAISE → the caller HELD the whole report. The B13 fix (operator-locked 2026-06-14 "nothing shall hold
the report"): guard empty/None content, RETRY via the B14 helper, and on PERSISTENT empty LABEL the pair
``conflict_unscored`` (a disclosed gap) — never raise to a hold, never fabricate a conflict, never drop a
real one (none was adjudicated).

Offline + deterministic: the httpx client is a mock; no network, no model.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import semantic_conflict_detector as scd

_ROW_A = {
    "evidence_id": "ev_a", "tier": "T1", "source_url": "u1",
    "direct_quote": "Adjuvant chemotherapy improved overall survival in stage II colon cancer.",
}
_ROW_B = {
    "evidence_id": "ev_b", "tier": "T1", "source_url": "u2",
    "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit in stage II colon cancer.",
}


class _SeqClient:
    """Mock httpx.Client returning a SEQUENCE of message contents (None/"" = empty collapse)."""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = 0

    def post(self, url, headers=None, json=None):
        idx = min(self.calls, len(self._contents) - 1)
        content = self._contents[idx]
        self.calls += 1

        class _Resp:
            def raise_for_status(self_inner):
                return None

            def json(self_inner):
                return {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0.0},
                }

        return _Resp()


def _make_judge(monkeypatch, contents, *, strict_fail_closed=False):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")  # glm != deepseek => family ok
    judge = scd._SemanticContradictionJudge(strict_fail_closed=strict_fail_closed)
    judge._client = _SeqClient(contents)
    return judge


# ── the production judge: empty content is RETRIED, not crashed ──────────────────

def test_judge_empty_then_verdict_retries_and_returns_label(monkeypatch):
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "2")
    judge = _make_judge(monkeypatch, [None, '{"verdict": "CONTRADICT", "confidence": 0.9}'])
    label, conf = judge.judge("a", "b")
    assert label == "contradict"
    assert conf == pytest.approx(0.9)
    assert judge._client.calls == 2          # one empty (retried) + one good


def test_judge_persistent_empty_returns_unscored_label_never_raises(monkeypatch):
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "2")
    judge = _make_judge(monkeypatch, [None])  # always empty
    label, conf = judge.judge("a", "b")
    assert label == scd.CONFLICT_UNSCORED_LABEL
    assert conf == 0.0
    assert judge._client.calls == 3          # 1 + 2 retries, then the sentinel


def test_judge_whitespace_content_treated_as_empty(monkeypatch):
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "1")
    judge = _make_judge(monkeypatch, ["   \n  "])  # whitespace-only == empty
    label, conf = judge.judge("a", "b")
    assert label == scd.CONFLICT_UNSCORED_LABEL
    assert conf == 0.0


def test_judge_empty_under_strict_gates_still_labels_never_raises(monkeypatch):
    # B13 contract: an EMPTY judge is ALWAYS a label, never a hold — even under strict_fail_closed.
    # (A real transport ERROR under strict gates still raises; that path is the legacy F07 behavior,
    # unchanged. Empty content is the specific class B13 converts to a label.)
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "1")
    judge = _make_judge(monkeypatch, [None], strict_fail_closed=True)
    label, conf = judge.judge("a", "b")       # must NOT raise
    assert label == scd.CONFLICT_UNSCORED_LABEL
    assert conf == 0.0


# ── the detector: the unscored label → a ConflictUnscoredRecord (disclosed gap) ──

def _unscored_judge(a, b):
    return scd.CONFLICT_UNSCORED_LABEL, 0.0


def test_detector_labels_unscored_pair_when_collector_passed():
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    unscored: list = []
    records = scd.detect_semantic_conflicts(pairs, _unscored_judge, unscored_out=unscored)
    # no fabricated contradiction; exactly one disclosed-gap label
    assert records == []
    assert len(unscored) == 1
    rec = unscored[0]
    assert isinstance(rec, scd.ConflictUnscoredRecord)
    assert rec.type == "conflict_unscored"
    assert rec.severity == "unscored"
    assert set(rec.evidence_ids) == {"ev_a", "ev_b"}
    assert rec.subject  # non-empty


def test_detector_unscored_without_collector_is_byte_identical_skip():
    # No collector → the unscored label is simply skipped (the pre-B13 "not contradict -> skip" path).
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    records = scd.detect_semantic_conflicts(pairs, _unscored_judge)
    assert records == []


def test_detector_unscored_label_never_raises_even_strict():
    # The unscored LABEL must not be confused with the F07 strict-raise path: a labeled pair under
    # strict_fail_closed must NOT raise ConflictJudgeUnavailableError (the judge already retried+labeled).
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    unscored: list = []
    records = scd.detect_semantic_conflicts(
        pairs, _unscored_judge, strict_fail_closed=True, unscored_out=unscored,
    )
    assert records == []
    assert len(unscored) == 1


# ── end-to-end with_unscored wrapper ────────────────────────────────────────────

def test_for_rows_with_unscored_returns_both_lists():
    records, unscored = scd.detect_semantic_conflicts_for_rows_with_unscored(
        [_ROW_A, _ROW_B], judge=_unscored_judge,
    )
    assert records == []
    assert len(unscored) == 1
    assert set(unscored[0].evidence_ids) == {"ev_a", "ev_b"}


def test_for_rows_with_unscored_mixes_contradict_and_unscored():
    rows = [_ROW_A, _ROW_B]

    def _judge(a, b):
        return "contradict", 0.95

    records, unscored = scd.detect_semantic_conflicts_for_rows_with_unscored(rows, judge=_judge)
    assert len(records) == 1
    assert unscored == []


# ── legacy entry point stays byte-identical (no collector) ──────────────────────

def test_legacy_for_rows_unchanged_on_contradict():
    def _judge(a, b):
        return "contradict", 0.95

    records = scd.detect_semantic_conflicts_for_rows([_ROW_A, _ROW_B], judge=_judge)
    assert len(records) == 1
    assert records[0].type == "semantic"
