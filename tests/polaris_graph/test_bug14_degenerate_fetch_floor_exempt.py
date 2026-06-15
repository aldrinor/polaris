"""BUG-14 (GH #1262, §-1.3 WEIGHT-not-FILTER): a FAILED / STUB / content-starved
fetch yields a DEGENERATE embedding (empty statement+quote → near-zero, often
IDENTICAL, cosine — the drb_72 smoking gun: two distinct journal URLs both logged
cosine 0.0431 from identical empty input). The relevance floor then HARD-DROPPED
those rows as if "off-topic", silently losing 24 of 166 canonical T1 sources
(Autor, Frey & Osborne).

§-1.3: empty content is UNKNOWN-relevance, NOT off-topic — you cannot conclude
off-topic from a fetch that never delivered content. So a degenerate / stub-fetch
row must be KEPT (floor-EXEMPT), down-weighted so it sorts LAST, and DISCLOSED for
re-fetch — never silently dropped. A genuinely off-topic row with REAL non-empty
content stays DROPPED (the floor still filters real off-topic noise — faithfulness
untouched).

These tests exercise the public selector entry (`select_evidence_for_generation`),
which builds the `scored` tuples and calls `_relevance_floor_selection` — the exact
keep-filter near lines 1937-1968 BUG-14 fixes. The default (`PG_SWEEP_CREDIBILITY_
REDESIGN` unset) routes through the legacy lexical floor where the over-drop lived.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.polaris_graph.retrieval.evidence_selector import (
    _fetch_degenerate,
    select_evidence_for_generation,
)


@dataclass
class _FakeSource:
    url: str
    tier: str


def _srcs(rows: list[dict]) -> list[_FakeSource]:
    return [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]


# A focused, SHORT question so an on-topic row clears the 0.30 lexical floor
# (a long question would dilute the denominator — irrelevant to BUG-14).
_QUESTION = "automation employment effect"


def _on_topic_t1() -> dict:
    """Real, on-topic T1 content — must clear the floor (sanity baseline)."""
    return {
        "evidence_id": "ev_ontopic",
        "source_url": "https://nber.org/papers/autor-real",
        "statement": "Automation employment effect on workers.",
        "direct_quote": "The automation employment effect reshaped employment.",
        "tier": "T1",
    }


def _degenerate_t1() -> dict:
    """A canonical T1 journal source whose fetch FAILED / returned a STUB: empty
    embeddable content => degenerate near-zero cosine => the BUG-14 over-drop.
    (Autor / Frey & Osborne were exactly this on drb_72.)"""
    return {
        "evidence_id": "ev_degenerate",
        "source_url": "https://www.journals.example/frey-osborne-stub",
        "statement": "",        # fetch failed → no body extracted
        "direct_quote": "",     # → degenerate (identical) embedding for any such row
        "tier": "T1",
    }


def _offtopic_t1_real() -> dict:
    """A genuinely OFF-TOPIC row with REAL, non-empty content — below floor but
    NOT degenerate. Must STILL be dropped (we never relax the off-topic filter)."""
    return {
        "evidence_id": "ev_offtopic",
        "source_url": "https://www.journals.example/quantum-nebula",
        "statement": "Quantum astronomy nebula spectroscopy of distant galaxies.",
        "direct_quote": "Spectral nebula emission lines mapped across the cosmos.",
        "tier": "T1",
    }


def _select(rows: list[dict]):
    return select_evidence_for_generation(
        research_question=_QUESTION,
        protocol=None,
        classified_sources=_srcs(rows),
        evidence_rows=rows,
        max_rows=1000,          # high — isolate the FLOOR, not the cap
        relevance_floor=0.30,   # not-None => the floor branch BUG-14 fixes
    )


def _ids(res) -> set[str]:
    return {r["evidence_id"] for r in res.selected_rows}


# ── helper unit coverage ─────────────────────────────────────────────────────

def test_fetch_degenerate_detects_empty_content_directly() -> None:
    """Backstop direct-content detection: empty embeddable text is degenerate."""
    assert _fetch_degenerate(_degenerate_t1()) is True
    assert _fetch_degenerate(_offtopic_t1_real()) is False
    assert _fetch_degenerate(_on_topic_t1()) is False


def test_fetch_degenerate_honors_upstream_markers() -> None:
    """Reliable upstream markers set by live_retriever's down-weight path are
    trusted even when (hypothetically) the content surface is non-empty."""
    assert _fetch_degenerate({"statement": "x" * 80, "content_starved": True})
    assert _fetch_degenerate({"statement": "x" * 80, "landing_page": True})
    assert _fetch_degenerate({"statement": "x" * 80, "down_weighted": True})
    assert _fetch_degenerate({"statement": "x" * 80, "full_text_capable": False})
    assert _fetch_degenerate({"statement": "x" * 80, "failure_mode": "fetch_failed"})


def test_min_chars_env_override(monkeypatch) -> None:
    """`PG_SELECT_DEGENERATE_MIN_CHARS` (LAW VI) tunes the direct-content floor; a
    malformed / non-positive value falls back to the default (fail-safe: never
    disables the unknown-relevance guard)."""
    row = {"statement": "short text here", "direct_quote": ""}  # ~15 chars
    monkeypatch.setenv("PG_SELECT_DEGENERATE_MIN_CHARS", "5")
    assert _fetch_degenerate(row) is False   # 15 >= 5 → not degenerate
    monkeypatch.setenv("PG_SELECT_DEGENERATE_MIN_CHARS", "200")
    assert _fetch_degenerate(row) is True    # 15 < 200 → degenerate
    monkeypatch.setenv("PG_SELECT_DEGENERATE_MIN_CHARS", "garbage")
    # default 24 → 15 < 24 → degenerate (malformed value does NOT disable the guard)
    assert _fetch_degenerate(row) is True


# ── end-to-end keep-filter behavior (the BUG-14 fix in situ) ─────────────────

def test_bug14_degenerate_t1_is_kept_default_on(monkeypatch) -> None:
    """(a) THE FIX: a T1 row with empty/stub content AND below-floor cosine is now
    KEPT (was hard-dropped). PG_SELECT_KEEP_DEGENERATE_FETCH defaults ON."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    monkeypatch.delenv("PG_SELECT_KEEP_DEGENERATE_FETCH", raising=False)  # default ON
    rows = [_on_topic_t1(), _degenerate_t1()]
    res = _select(rows)
    ids = _ids(res)
    assert "ev_ontopic" in ids, "the real on-topic T1 row must clear the floor"
    assert "ev_degenerate" in ids, (
        "BUG-14: the stub-fetch (UNKNOWN-relevance) T1 row must be KEPT, not dropped"
    )


def test_bug14_degenerate_row_sorts_last(monkeypatch) -> None:
    """The kept degenerate row must sort AFTER the real on-topic content (its
    near-zero cosine drives the existing relevance x authority x weight sort)."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    monkeypatch.delenv("PG_SELECT_KEEP_DEGENERATE_FETCH", raising=False)
    rows = [_degenerate_t1(), _on_topic_t1()]   # degenerate listed FIRST on input
    res = _select(rows)
    order = [r["evidence_id"] for r in res.selected_rows]
    assert order.index("ev_ontopic") < order.index("ev_degenerate"), (
        "real on-topic content must rank ahead of the down-weighted stub-fetch row"
    )


def test_bug14_genuine_offtopic_still_dropped(monkeypatch) -> None:
    """(b) FAITHFULNESS PRESERVED: a genuinely off-topic row with REAL non-empty
    content AND below-floor cosine is STILL dropped — we did not relax the
    off-topic filter, only the silent over-drop of unknown-relevance rows."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    monkeypatch.delenv("PG_SELECT_KEEP_DEGENERATE_FETCH", raising=False)
    rows = [_on_topic_t1(), _offtopic_t1_real(), _degenerate_t1()]
    res = _select(rows)
    ids = _ids(res)
    assert "ev_offtopic" not in ids, (
        "a real-content off-topic row must remain dropped (off-topic filter intact)"
    )
    assert "ev_degenerate" in ids, "the stub-fetch row is kept (unknown relevance)"
    assert "ev_ontopic" in ids


def test_bug14_telemetry_counts_the_exemption(monkeypatch) -> None:
    """(c) DISCLOSURE: the kept-for-refetch count is surfaced in the note
    (`fetch_degenerate_exempt=N`) — §-1.3 disclose, never a silent keep."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    monkeypatch.delenv("PG_SELECT_KEEP_DEGENERATE_FETCH", raising=False)
    rows = [_on_topic_t1(), _degenerate_t1(), _offtopic_t1_real()]
    res = _select(rows)
    note = " ".join(res.notes)
    assert "fetch_degenerate_exempt=1" in note, (
        f"the note must disclose the 1 kept stub-fetch row; got: {note!r}"
    )


def test_bug14_flag_off_restores_legacy_drop(monkeypatch) -> None:
    """PG_SELECT_KEEP_DEGENERATE_FETCH=0 reverts to the legacy hard-drop (the
    stub-fetch T1 row is dropped) AND the note does NOT widen — proving the fix is
    cleanly gated and the OFF path is byte-identical to the prior behavior."""
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
    monkeypatch.setenv("PG_SELECT_KEEP_DEGENERATE_FETCH", "0")
    rows = [_on_topic_t1(), _degenerate_t1()]
    res = _select(rows)
    ids = _ids(res)
    assert "ev_degenerate" not in ids, "flag OFF => legacy floor drops the stub row"
    assert "ev_ontopic" in ids
    note = " ".join(res.notes)
    assert "fetch_degenerate_exempt" not in note, "OFF path note must not widen"
