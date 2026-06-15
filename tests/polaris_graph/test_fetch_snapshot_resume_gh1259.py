"""GH #1259 (FIX B) — POST-FETCH checkpoint + resume-from-nearest.

The pipeline had ONE checkpoint (F04 corpus_snapshot.json, written POST-SELECTION, right
before generation). Runs that died DURING fetch / embedding-rerank landed BEFORE it, so a
72-minute fetch was lost. This adds an EARLIER post-fetch checkpoint (fetch_snapshot.json,
written after fetch+merge but before the slow embedding-rerank/selection) and makes
--resume RESUME-FROM-NEAREST across the two staged checkpoints.

These tests prove, all offline (pure JSON + a stubbed retrieval/scope/generator — no
network, no model, no embedding):

  (a) the post-fetch snapshot WRITES at the seam (after fetch+merge, before selection),
      carrying DATA ONLY (no verdict, no selected pool);
  (b) --resume from a fetch_snapshot reconstructs the corpus, SKIPS the main
      run_live_retrieval (no re-fetch), RE-RUNS select_evidence_for_generation
      (embedding-rerank), and hands the generator the re-selected rows;
  (c) --resume from a corpus_snapshot still works UNCHANGED (no regression): selection is
      SKIPPED and the generator receives the snapshot's billed pool verbatim;
  (d) resume-from-nearest picks the LATER (corpus_snapshot) checkpoint when BOTH files
      exist.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest


# ───────────────────────── shared offline fixtures ─────────────────────────

class _FakeRetrieval:
    """Minimal stand-in for LiveRetrievalResult carrying the fields the snapshot persists."""

    def __init__(self, sources, rows):
        self.classified_sources = sources
        self.evidence_rows = rows
        self.notes = ["fetch note"]
        self.total_candidates_pre_filter = 120
        self.candidates_fetched = 55
        self.candidates_failed_fetch = 5
        self.candidates_total = 90
        self.candidates_processed = 90
        self.extraction_finding_rows = len(rows)
        self.corpus_truncated = False
        self.api_calls = {"serper": 4}


def _corpus_source(url, tier):
    from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
    return CorpusSource(url=url, tier=tier, title="t", domain="d")


def _seed_fetch_corpus(n=12):
    """A T1-T3 corpus generous enough to clear any corpus-adequacy floor on resume."""
    rows, sources = [], []
    for i in range(n):
        tier = "T1" if i < 5 else ("T2" if i < 9 else "T3")
        url = f"https://example.org/fetch{i}"
        rows.append({
            "evidence_id": f"ev_{i:03d}", "direct_quote": f"fetched claim {i}",
            "source_url": url, "tier": tier,
        })
        sources.append(_corpus_source(url, tier))
    return rows, sources


# ───────────────── (a) post-fetch snapshot module: write + DATA-only + fail-loud ─────────────────

def test_fetch_snapshot_saves_data_not_a_verdict(tmp_path):
    """HARD INVARIANT §-1.3: the post-fetch snapshot serializes EVIDENCE DATA only — never a
    faithfulness verdict / strict_verify result / 'verified' flag. Also asserts it carries NO
    selected pool key (selection has not run at the post-fetch seam)."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    rows, sources = _seed_fetch_corpus(3)
    retr = _FakeRetrieval(sources, rows)
    path = fs.save_fetch_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d", retrieval=retr,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["stage"] == fs.STAGE_POST_FETCH
    assert path.name == fs.FETCH_SNAPSHOT_FILENAME
    flat = json.dumps(payload).lower()
    for banned in ("verdict", "verified", "strict_verify", "entailed", "release_allowed",
                   "faithful", "nli_label"):
        assert banned not in flat, f"fetch snapshot must carry NO verdict; found {banned!r}"
    # A post-fetch snapshot stores NO selected/billed pool — selection has not run.
    assert "evidence_for_gen" not in payload


def test_fetch_snapshot_round_trips_via_shared_reconstruct(tmp_path):
    """The reloaded post-fetch snapshot rebuilds the SAME retrieval corpus via the shared
    corpus_snapshot.reconstruct_retrieval (identical retrieval payload shape)."""
    from src.polaris_graph.generator import fetch_snapshot as fs
    from src.polaris_graph.generator.corpus_snapshot import reconstruct_retrieval

    rows, sources = _seed_fetch_corpus(2)
    retr = _FakeRetrieval(sources, rows)
    fs.save_fetch_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d", retrieval=retr,
    )
    payload = fs.load_fetch_snapshot(tmp_path)
    recon = reconstruct_retrieval(payload)
    assert recon.evidence_rows == rows
    assert [s.url for s in recon.classified_sources] == [r["source_url"] for r in rows]
    assert recon.candidates_fetched == 55
    assert recon.extraction_finding_rows == 2


def test_fetch_snapshot_atomic_write_leaves_no_tmp(tmp_path):
    """The save is atomic (temp + replace); after a successful write no .tmp residue remains."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    rows, sources = _seed_fetch_corpus(2)
    fs.save_fetch_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d",
        retrieval=_FakeRetrieval(sources, rows),
    )
    assert not list(tmp_path.glob("*.tmp"))
    assert fs.fetch_snapshot_path(tmp_path).exists()


def test_fetch_snapshot_load_fails_loud_on_missing(tmp_path):
    """A --resume reload with no fetch snapshot raises (fail loud)."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    with pytest.raises(fs.FetchSnapshotError):
        fs.load_fetch_snapshot(tmp_path)


def test_fetch_snapshot_load_fails_loud_on_version_mismatch(tmp_path):
    """A schema_version mismatch raises (refuse to resume a stale-shaped corpus)."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    fs.fetch_snapshot_path(tmp_path).write_text(
        json.dumps({"schema_version": 999, "retrieval": {"evidence_rows": [{"x": 1}]}}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(fs.FetchSnapshotError):
        fs.load_fetch_snapshot(tmp_path)


def test_fetch_snapshot_load_fails_loud_on_empty_corpus(tmp_path):
    """An empty retrieval.evidence_rows raises (nothing to resume from)."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    fs.fetch_snapshot_path(tmp_path).write_text(
        json.dumps({
            "schema_version": fs.FETCH_SNAPSHOT_SCHEMA_VERSION,
            "stage": fs.STAGE_POST_FETCH,
            "retrieval": {"evidence_rows": [], "classified_sources": [{"url": "u"}]},
        }) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(fs.FetchSnapshotError):
        fs.load_fetch_snapshot(tmp_path)


# ───────────────── (P2-2) load fails loud on a malformed snapshot (stage + classified_sources) ─────────────────

def test_fetch_snapshot_load_fails_loud_on_wrong_stage(tmp_path):
    """Codex diff-gate P2-2: a snapshot whose stage != 'post_fetch' (e.g. a corpus_snapshot
    handed to the post-fetch loader) FAILS LOUD at LOAD, not later as a generic no-source
    error deep in the resume path."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    rows, _ = _seed_fetch_corpus(2)
    fs.fetch_snapshot_path(tmp_path).write_text(
        json.dumps({
            "schema_version": fs.FETCH_SNAPSHOT_SCHEMA_VERSION,
            "stage": "pre_generation",  # WRONG: this is corpus_snapshot's stage, not ours
            "retrieval": {"evidence_rows": rows, "classified_sources": [{"url": "u"}]},
        }) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(fs.FetchSnapshotError, match="stage"):
        fs.load_fetch_snapshot(tmp_path)


def test_fetch_snapshot_load_fails_loud_on_empty_or_malformed_sources(tmp_path):
    """Codex diff-gate P2-2: a snapshot with non-empty evidence_rows but an empty OR
    malformed classified_sources FAILS LOUD at LOAD (reconstruct_retrieval rehydrates
    CorpusSource(**row) from these — a non-dict entry would crash deep in resume)."""
    from src.polaris_graph.generator import fetch_snapshot as fs

    rows, _ = _seed_fetch_corpus(2)
    # (a) empty classified_sources
    fs.fetch_snapshot_path(tmp_path).write_text(
        json.dumps({
            "schema_version": fs.FETCH_SNAPSHOT_SCHEMA_VERSION,
            "stage": fs.STAGE_POST_FETCH,
            "retrieval": {"evidence_rows": rows, "classified_sources": []},
        }) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(fs.FetchSnapshotError, match="classified_sources"):
        fs.load_fetch_snapshot(tmp_path)
    # (b) malformed (non-dict) classified_sources entry
    fs.fetch_snapshot_path(tmp_path).write_text(
        json.dumps({
            "schema_version": fs.FETCH_SNAPSHOT_SCHEMA_VERSION,
            "stage": fs.STAGE_POST_FETCH,
            "retrieval": {"evidence_rows": rows, "classified_sources": ["not-a-dict"]},
        }) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(fs.FetchSnapshotError, match="classified_sources"):
        fs.load_fetch_snapshot(tmp_path)


# ───────────────── (P1) JOURNAL_ONLY fetch-resume round-trips (no no_journal_metadata abort) ─────────────────

def _citeable_journal_sidecar(rows):
    """A merged sidecar (keyed by canonical URL) where EVERY entry satisfies the full
    is_citeable_journal predicate: peer-reviewed journal article, real DOI, non-nav URL."""
    from src.polaris_graph.nodes import journal_only_filter as jof
    sidecar = {}
    for i, r in enumerate(rows):
        sidecar[jof.canonicalize_url(r["source_url"])] = jof.journal_metadata_entry(
            openalex_pub_type="article",
            openalex_source_type="journal",
            is_peer_reviewed=True,
            is_retracted=False,
            doi=f"10.1000/journal.{i:03d}",
            venue=f"Journal {i}",
        )
    return sidecar


def test_journal_only_fetch_resume_round_trips_not_dropped(tmp_path):
    """FIX (Codex P1): a JOURNAL_ONLY fetch-resume must NOT drop the reconstructed corpus
    with `no_journal_metadata`. We save a fetch_snapshot WITH the merged journal sidecar
    (as the runner now does), reload it, reconstruct the retrieval, restore the sidecar
    onto it EXACTLY as the runner's `_resume_from_fetch` branch does, then run the REAL
    journal_only filter merge (`merge_sidecars([retrieval.sidecar, None, None, None])`) +
    `filter_to_citeable`. Assert the rows SURVIVE (citeable, NOT excluded) — proving the
    journal_only abort is gone. WITHOUT the persisted sidecar this drops every row."""
    from src.polaris_graph.generator import fetch_snapshot as fs
    from src.polaris_graph.generator.corpus_snapshot import reconstruct_retrieval
    from src.polaris_graph.nodes import journal_only_filter as jof

    # T1/T2 rows only (T3 fails tier_not_journal even with a sidecar).
    rows, sources = [], []
    for i in range(6):
        tier = "T1" if i < 3 else "T2"
        url = f"https://journals.example.org/article/{i}"
        rows.append({"evidence_id": f"ev_{i:03d}", "direct_quote": f"claim {i}",
                     "source_url": url, "tier": tier})
        sources.append(_corpus_source(url, tier))
    merged_sidecar = _citeable_journal_sidecar(rows)

    # The runner persists the MERGED sidecar in the fetch_snapshot (the P1 fix).
    fs.save_fetch_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d",
        retrieval=_FakeRetrieval(sources, rows),
        journal_metadata_sidecar=merged_sidecar,
    )

    # --- BASELINE (proves the bug WAS real): reconstruct WITHOUT restoring the sidecar →
    # the journal_only filter sees an empty sidecar and drops every row as no_journal_metadata.
    payload = fs.load_fetch_snapshot(tmp_path)
    recon_no_sidecar = reconstruct_retrieval(payload)
    assert getattr(recon_no_sidecar, "journal_metadata_sidecar", None) in (None, {}), (
        "reconstruct_retrieval must NOT carry the sidecar by itself (it is journal_only-specific)"
    )
    empty_merge = jof.merge_sidecars([
        getattr(recon_no_sidecar, "journal_metadata_sidecar", None), None, None, None
    ])
    dropped = jof.filter_to_citeable(recon_no_sidecar.evidence_rows, empty_merge)
    assert dropped.citeable == [] and len(dropped.excluded) == len(rows), (
        "baseline: without the persisted sidecar EVERY row must drop (this is the bug we fix)"
    )
    assert all(e["reason"] == "no_journal_metadata" for e in dropped.excluded), (
        f"baseline drop reason must be no_journal_metadata; got {dropped.excluded!r}"
    )

    # --- FIX: restore the persisted sidecar onto the reconstructed retrieval EXACTLY as the
    # runner's `if _resume_from_fetch:` branch does, then run the SAME unchanged filter merge.
    recon = reconstruct_retrieval(payload)
    recon.journal_metadata_sidecar = dict(payload.get("journal_metadata_sidecar") or {})
    fixed_merge = jof.merge_sidecars([
        recon.journal_metadata_sidecar, None, None, None  # exp/deep/agentic are None on resume
    ])
    assert fixed_merge == merged_sidecar, "restored sidecar must round-trip the persisted dict"
    kept = jof.filter_to_citeable(recon.evidence_rows, fixed_merge)
    kept_srcs = jof.filter_to_citeable(recon.classified_sources, fixed_merge)
    # The corpus SURVIVES — no no_journal_metadata abort.
    assert [r["evidence_id"] for r in kept.citeable] == [r["evidence_id"] for r in rows], (
        f"journal_only fetch-resume must KEEP every reconstructed row; got {kept.citeable!r}"
    )
    assert kept.excluded == [], f"no row should be excluded on a faithful resume; {kept.excluded!r}"
    assert len(kept_srcs.citeable) == len(sources) and kept_srcs.excluded == []


# ───────────────── integration scaffolding (mirrors the F04 resume integration test) ─────────────────

class _RetrievalSentinel(RuntimeError):
    """Raised if the MAIN run_live_retrieval is invoked on a resume run (it must NOT be)."""


class _ReachedGeneration(RuntimeError):
    """Raised by the generator stub AFTER it captures the evidence it received, so the test
    asserts the resume path threaded through to the generation rejoin without driving the
    entire post-generation block."""


def _install_offline_stubs(monkeypatch, sweep):
    """Block the network: main retrieval must not run; scope gate is deterministic."""
    monkeypatch.setenv("PG_CAPTURE_PIN", "0")
    monkeypatch.delenv("PG_V30_PHASE2_ENABLED", raising=False)
    monkeypatch.delenv("PG_BENCHMARK_STRICT_GATES", raising=False)
    monkeypatch.setenv("PG_USE_RESEARCH_PLANNER", "0")  # legacy outline path (no planner LLM)

    def _retrieval_must_not_run(**kwargs):
        raise _RetrievalSentinel("main run_live_retrieval was called on a --resume run")

    monkeypatch.setattr(sweep, "run_live_retrieval", _retrieval_must_not_run)

    def _fake_scope(*args, **kwargs):
        protocol = SimpleNamespace(
            scope_decision="accepted", scope_rejected=False, scope_rejection_code=None,
            scope_reasons=[], needs_user_review=False,
            to_json_dict=lambda: {"decision": "accepted"},
        )
        return SimpleNamespace(protocol=protocol, protocol_sha256="0" * 64)

    monkeypatch.setattr(sweep, "run_scope_gate", _fake_scope)
    monkeypatch.setattr(sweep, "_classify_scope_with_llm", lambda **k: None)


def _install_generation_capture(monkeypatch, sweep, captured):
    async def _capture_generator(*args, **kwargs):
        captured["evidence"] = kwargs.get("evidence")
        raise _ReachedGeneration("reached generation rejoin")

    monkeypatch.setattr(sweep, "generate_multi_section_report", _capture_generator)


# ───────────────── (b) --resume from a fetch_snapshot: reconstruct, skip fetch, RE-RUN selection ─────────────────

def test_resume_from_fetch_snapshot_reruns_selection_and_skips_refetch(tmp_path, monkeypatch):
    """FIX B ACCEPT (integration): a --resume run that finds ONLY a fetch_snapshot must
      (1) NOT call the main run_live_retrieval (no re-fetch),
      (2) RE-RUN select_evidence_for_generation (the embedding-rerank seam) on the
          reconstructed corpus — proving the post-fetch resume path re-enters BEFORE
          selection, not at generation, and
      (3) hand the generator the RE-SELECTED rows.
    The discriminator vs corpus-resume is that selection RAN (a spy proves it)."""
    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import fetch_snapshot as fs

    _install_offline_stubs(monkeypatch, sweep)

    q = {"domain": "tech", "slug": "fetch_resume_smoke", "question": "Fetch resume question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    rows, sources = _seed_fetch_corpus(12)
    fs.save_fetch_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        retrieval=_FakeRetrieval(sources, rows),
    )
    # No corpus_snapshot.json present -> resume-from-nearest falls back to the fetch snapshot.

    # Spy on selection: it MUST run on fetch-resume (this is the whole point — re-run the
    # embedding-rerank). Return a deterministic re-selected pool we can assert on.
    selection_calls = {"n": 0}
    reselected = [
        {"evidence_id": "sel_0", "direct_quote": "reselected a", "source_url": "u1", "tier": "T1"},
        {"evidence_id": "sel_1", "direct_quote": "reselected b", "source_url": "u2", "tier": "T2"},
    ]

    def _spy_select(**kwargs):
        selection_calls["n"] += 1
        # The reconstructed corpus must be what selection sees (proves no re-fetch).
        seen_ids = [r.get("evidence_id") for r in (kwargs.get("evidence_rows") or [])]
        assert seen_ids == [f"ev_{i:03d}" for i in range(12)], (
            f"selection did not receive the reconstructed fetch corpus; got {seen_ids!r}"
        )
        from src.polaris_graph.retrieval.evidence_selector import EvidenceSelection
        return EvidenceSelection(
            selected_rows=list(reselected), full_counts={}, selected_counts={},
            dropped_count=0, selection_strategy="spy", notes=[],
        )

    # The sweep imports select_evidence_for_generation LOCALLY from evidence_selector at the
    # call site, so patch the SOURCE module (patching `sweep` would miss the fresh local bind).
    monkeypatch.setattr(
        "src.polaris_graph.retrieval.evidence_selector.select_evidence_for_generation",
        _spy_select,
    )

    captured: dict = {}
    _install_generation_capture(monkeypatch, sweep, captured)

    # run_one_query traps exceptions into an error manifest; we assert on the captured
    # evidence + the selection spy + the retrieval sentinel (no raise propagates out).
    asyncio.run(sweep.run_one_query(q, tmp_path, resume=True))

    assert selection_calls["n"] == 1, "fetch-resume must RE-RUN selection (embedding-rerank)"
    assert "evidence" in captured, "fetch-resume never reached the generation rejoin"
    got_ids = [r.get("evidence_id") for r in (captured["evidence"] or [])]
    assert got_ids == ["sel_0", "sel_1"], (
        f"generator did not receive the RE-SELECTED rows on fetch-resume; got {got_ids!r}"
    )


# ───────────────── (c) --resume from a corpus_snapshot: UNCHANGED (no regression) ─────────────────

def test_resume_from_corpus_snapshot_still_skips_selection_no_regression(tmp_path, monkeypatch):
    """REGRESSION GUARD: a --resume run that finds a corpus_snapshot (post-selection) must
    behave EXACTLY as before FIX B — selection is SKIPPED and the generator receives the
    snapshot's billed pool verbatim. If selection ran here, the two-flag split leaked."""
    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import corpus_snapshot as cs

    _install_offline_stubs(monkeypatch, sweep)

    q = {"domain": "tech", "slug": "corpus_resume_smoke", "question": "Corpus resume question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    rows, sources = _seed_fetch_corpus(12)
    cs.save_corpus_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        evidence_for_gen=rows, retrieval=_FakeRetrieval(sources, rows),
    )

    # Selection must NOT run on corpus-resume (the snapshot already holds the billed pool).
    def _selection_must_not_run(**kwargs):
        raise AssertionError("select_evidence_for_generation ran on a corpus_snapshot resume")

    monkeypatch.setattr(
        "src.polaris_graph.retrieval.evidence_selector.select_evidence_for_generation",
        _selection_must_not_run,
    )

    captured: dict = {}
    _install_generation_capture(monkeypatch, sweep, captured)

    asyncio.run(sweep.run_one_query(q, tmp_path, resume=True))

    assert "evidence" in captured, "corpus-resume never reached the generation rejoin"
    got_ids = [r.get("evidence_id") for r in (captured["evidence"] or [])]
    assert got_ids == [f"ev_{i:03d}" for i in range(12)], (
        f"corpus-resume generator did not receive the snapshot pool verbatim; got {got_ids!r}"
    )


# ───────────────── (d) resume-from-nearest: LATER (corpus_snapshot) wins when both exist ─────────────────

def test_resume_from_nearest_prefers_corpus_snapshot_when_both_exist(tmp_path, monkeypatch):
    """RESUME-FROM-NEAREST: when BOTH a fetch_snapshot AND a corpus_snapshot are present, the
    LATER (post-selection) corpus_snapshot wins — it skips strictly more work. Proven by:
    selection is SKIPPED (corpus path) and the generator receives the CORPUS snapshot's pool,
    which we make DISTINGUISHABLE from the fetch snapshot's corpus."""
    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import corpus_snapshot as cs
    from src.polaris_graph.generator import fetch_snapshot as fs

    _install_offline_stubs(monkeypatch, sweep)

    q = {"domain": "tech", "slug": "both_snapshots", "question": "Both snapshots question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    # Fetch snapshot carries the EARLIER (pre-selection) corpus: ev_000..ev_011.
    fetch_rows, fetch_sources = _seed_fetch_corpus(12)
    fs.save_fetch_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        retrieval=_FakeRetrieval(fetch_sources, fetch_rows),
    )
    # Corpus snapshot carries a DISTINCT post-selection billed pool: corpus_000..corpus_005.
    corpus_rows = [
        {"evidence_id": f"corpus_{i:03d}", "direct_quote": f"selected {i}",
         "source_url": f"https://example.org/sel{i}", "tier": "T1"}
        for i in range(6)
    ]
    cs.save_corpus_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        evidence_for_gen=corpus_rows, retrieval=_FakeRetrieval(fetch_sources, fetch_rows),
    )

    # If the corpus (nearest) path is taken, selection is SKIPPED.
    def _selection_must_not_run(**kwargs):
        raise AssertionError("selection ran: resume-from-nearest wrongly chose the fetch snapshot")

    monkeypatch.setattr(
        "src.polaris_graph.retrieval.evidence_selector.select_evidence_for_generation",
        _selection_must_not_run,
    )

    captured: dict = {}
    _install_generation_capture(monkeypatch, sweep, captured)

    asyncio.run(sweep.run_one_query(q, tmp_path, resume=True))

    assert "evidence" in captured, "resume-from-nearest never reached the generation rejoin"
    got_ids = [r.get("evidence_id") for r in (captured["evidence"] or [])]
    assert got_ids == [f"corpus_{i:03d}" for i in range(6)], (
        f"resume-from-nearest did not pick the LATER corpus_snapshot pool; got {got_ids!r}"
    )


# ───────────────── (P2 seam) FRESH path writes fetch_snapshot.json AFTER fetch/merge, BEFORE selection ─────────────────

def test_fresh_path_writes_fetch_snapshot_at_seam_before_selection(tmp_path, monkeypatch):
    """Codex diff-gate P2 (seam): a FRESH (non-resume) run must write fetch_snapshot.json at
    the POST-FETCH seam — AFTER run_live_retrieval returns + merges, BEFORE
    select_evidence_for_generation. Heavy stages are mocked: run_live_retrieval RETURNS a
    corpus (and asserts the snapshot does NOT yet exist), selection asserts the snapshot
    DOES exist at call time then short-circuits. Proves the checkpoint lands between fetch
    and selection."""
    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import fetch_snapshot as fs

    _install_offline_stubs(monkeypatch, sweep)  # base offline (scope gate etc.)
    # Keep every pre-selection network lane inert so the seam is deterministic (no I/O).
    monkeypatch.setenv("PG_R6_ENABLE_EXPANSION", "0")
    for _flag in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS",
        "PG_SOURCE_RESTRICTION_JOURNAL_ONLY",
    ):
        monkeypatch.delenv(_flag, raising=False)

    q = {"domain": "tech", "slug": "fresh_seam_smoke", "question": "Fresh seam question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    rows, sources = _seed_fetch_corpus(12)

    seam_path = fs.fetch_snapshot_path(run_dir)

    # FRESH run: run_live_retrieval RETURNS the corpus (it is the network stage). Assert the
    # snapshot is NOT yet on disk here (it is written AFTER this returns -> "written after fetch").
    def _fresh_retrieval(**kwargs):
        assert not seam_path.exists(), "fetch_snapshot written BEFORE run_live_retrieval returned"
        return _FakeRetrieval(sources, rows)

    monkeypatch.setattr(sweep, "run_live_retrieval", _fresh_retrieval)

    class _SelectionReached(RuntimeError):
        pass

    select_state = {"snapshot_present_at_selection": None}

    def _spy_select_seam(**kwargs):
        # The whole point: by the time selection is entered, the checkpoint must already be on disk.
        select_state["snapshot_present_at_selection"] = seam_path.exists()
        raise _SelectionReached("reached selection seam")

    monkeypatch.setattr(
        "src.polaris_graph.retrieval.evidence_selector.select_evidence_for_generation",
        _spy_select_seam,
    )

    # run_one_query traps the sentinel into an error manifest; we assert on disk + the spy state.
    asyncio.run(sweep.run_one_query(q, tmp_path, resume=False))

    assert select_state["snapshot_present_at_selection"] is True, (
        "fresh path did not write fetch_snapshot.json BEFORE select_evidence_for_generation"
    )
    assert seam_path.exists(), "fresh path left no fetch_snapshot.json after the run"
    # The persisted snapshot is the post-fetch corpus, DATA-only (no verdict).
    payload = json.loads(seam_path.read_text(encoding="utf-8"))
    assert payload["stage"] == fs.STAGE_POST_FETCH
    assert [r["evidence_id"] for r in payload["retrieval"]["evidence_rows"]] == [
        f"ev_{i:03d}" for i in range(12)
    ]
    # journal_only OFF here -> the persisted merged sidecar is empty (no-op), present as a dict.
    assert payload["journal_metadata_sidecar"] == {}


# ───────────────── (P1, INTEGRATION) JOURNAL_ONLY fetch-resume drives run_one_query → corpus SURVIVES ─────────────────

def test_journal_only_fetch_resume_via_run_one_query_does_not_abort(tmp_path, monkeypatch):
    """FIX (Codex P1) — the END-TO-END proof: drive the REAL ``run_one_query(resume=True)`` with
    journal_only ACTIVE and a fetch_snapshot carrying the persisted merged sidecar. The runner's
    OWN ``if _resume_from_fetch:`` injection must restore the sidecar onto the reconstructed
    corpus so the journal_only filter (:5142) sees the SAME metadata a fresh run had. We do NOT
    set ``retrieval.journal_metadata_sidecar`` ourselves — the runner must.

    Probe: the ``journal_only_excluded.json`` the filter writes at :5156 (BEFORE the row
    reassignment + any downstream adequacy abort, so it survives the run stopping later). The
    corpus SURVIVES iff every row is citeable and NO row is excluded as ``no_journal_metadata``.
    Without the runner's persist+restore, the merged sidecar is EMPTY and every row drops
    ``no_journal_metadata`` -> this asserts the named abort is gone."""
    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import fetch_snapshot as fs

    _install_offline_stubs(monkeypatch, sweep)
    # Force journal_only ACTIVE: the sweep calls `_jof.journal_only_active(_jo_cfg)` on the
    # module object, so patch the SOURCE attr (an empty scope template otherwise reports False).
    monkeypatch.setattr(
        "src.polaris_graph.nodes.journal_only_filter.journal_only_active", lambda *_a, **_k: True
    )

    q = {"domain": "tech", "slug": "journal_resume_smoke", "question": "Journal resume question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    # T1/T2 journal rows + a citeable sidecar; persisted in the fetch_snapshot as the runner does.
    rows, sources = [], []
    for i in range(6):
        tier = "T1" if i < 3 else "T2"
        url = f"https://journals.example.org/article/{i}"
        rows.append({"evidence_id": f"ev_{i:03d}", "direct_quote": f"claim {i}",
                     "source_url": url, "tier": tier})
        sources.append(_corpus_source(url, tier))
    merged_sidecar = _citeable_journal_sidecar(rows)
    fs.save_fetch_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        retrieval=_FakeRetrieval(sources, rows), journal_metadata_sidecar=merged_sidecar,
    )

    # Selection may or may not be reached (a thin-corpus adequacy abort can stop the run first);
    # the proof lives in journal_only_excluded.json, written BEFORE any such abort. Stub selection
    # so that IF it is reached it does not explode on the offline corpus.
    def _benign_select(**kwargs):
        from src.polaris_graph.retrieval.evidence_selector import EvidenceSelection
        return EvidenceSelection(
            selected_rows=list(kwargs.get("evidence_rows") or []), full_counts={},
            selected_counts={}, dropped_count=0, selection_strategy="benign", notes=[],
        )

    monkeypatch.setattr(
        "src.polaris_graph.retrieval.evidence_selector.select_evidence_for_generation",
        _benign_select,
    )
    captured: dict = {}
    _install_generation_capture(monkeypatch, sweep, captured)

    # run_one_query traps any downstream abort into an error manifest; assert on the artifact.
    asyncio.run(sweep.run_one_query(q, tmp_path, resume=True))

    excl_path = run_dir / "journal_only_excluded.json"
    assert excl_path.exists(), (
        "journal_only filter did not run on a journal_only fetch-resume (no excluded artifact)"
    )
    excl = json.loads(excl_path.read_text(encoding="utf-8"))
    # The runner's persist+restore made the merged sidecar non-empty on resume.
    assert excl["merged_sidecar_size"] == len(merged_sidecar), (
        f"runner did not restore the persisted sidecar on fetch-resume; "
        f"merged_sidecar_size={excl['merged_sidecar_size']} (expected {len(merged_sidecar)})"
    )
    # THE fix: NO row dropped as no_journal_metadata; the corpus survives the journal_only filter.
    no_meta_drops = [
        e for e in excl["evidence_rows_excluded"] if e.get("reason") == "no_journal_metadata"
    ]
    assert no_meta_drops == [], (
        f"journal_only fetch-resume DROPPED rows as no_journal_metadata (the P1 abort is back): "
        f"{no_meta_drops!r}"
    )
    assert excl["evidence_rows_excluded"] == [], (
        f"no journal row should be excluded on a faithful resume; got {excl['evidence_rows_excluded']!r}"
    )
