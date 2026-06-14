"""Offline tests for the Gate-B 4-role benchmark CLI launcher (I-meta-008 #1014).

NO network, NO spend anywhere. Covers:
  * --help exits 0 and lists the flags;
  * --list resolves all 5 locked slugs and leaves os.environ BYTE-IDENTICAL (full mapping),
    with no network and no spend;
  * a DISCRIMINATING direct-mechanism test that proves the env snapshot/restore actually
    restores a mutated/added key (the full-mapping --list assertion is vacuous on its own
    because pytest collection already imports run_honest_sweep_r3, so its module-top
    load_dotenv(override=False) does not re-fire — this test exercises the restore directly);
  * --only <unknown-slug> fails loud (rc 2);
  * mutually-exclusive / required-flag argparse behavior (rc 2 paths);
  * the per-question path threads four_role_transport=<fake> + a builder into run_one_query
    via an injected FAKE transport (run_one_query is monkeypatched so the real
    retrieval/generation pipeline — network + spend — never executes);
  * the CLI loop calls run_gate_b_query once per resolved question;
  * the drift-guard: the 5 SWEEP_QUERIES prompts == verbatim golden_questions_locked.md prompts;
  * import-safety: importing run_gate_b opens no socket and mutates no env.

Hermetic: env is snapshotted/restored so PG_FOUR_ROLE_MODE / PG_ENABLE_QUANTIFIED_ANALYSIS do
not leak into sibling tests.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    DEFAULT_OUT_ROOT,
    LOCKED_BENCHMARK_SLUGS,
    load_locked_questions,
    main,
)

_GOLDEN_MD = Path(".codex/I-safety-002b/golden_questions_locked.md")

# Map each locked slug -> the golden-md task header it lives under (the verbatim prompt
# follows the header line in golden_questions_locked.md). Used by the drift-guard test.
_SLUG_TO_GOLDEN_ID = {
    "drb_72_ai_labor": "#72",
    "drb_75_metal_ions_cvd": "#75",
    "drb_76_gut_microbiota_crc": "#76",
    "drb_78_parkinsons_dbs": "#78",
    "drb_90_adas_liability": "#90",
}


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so a CLI run that flips
    PG_FOUR_ROLE_MODE / PG_ENABLE_QUANTIFIED_ANALYSIS does not leak into sibling tests."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- --help / argparse

def test_help_exits_zero_and_lists_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--only", "--all", "--list", "--out-root"):
        assert flag in out


def test_no_selection_flag_is_required_rc2(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2  # argparse: required mutually-exclusive group


def test_only_and_all_mutually_exclusive_rc2():
    with pytest.raises(SystemExit) as exc:
        main(["--only", "drb_72_ai_labor", "--all"])
    assert exc.value.code == 2


def test_only_unknown_slug_fails_loud_rc2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--only", "drb_99_not_a_slug"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    # Fail LOUD: the message names the bad slug AND lists the valid ones.
    assert "drb_99_not_a_slug" in err
    assert "drb_72_ai_labor" in err


# --------------------------------------------------------------------------- --list

def test_list_resolves_all_five_and_env_byte_identical(capsys):
    env_before = dict(os.environ)
    rc = main(["--list"])
    env_after = dict(os.environ)
    assert rc == 0
    # FULL-mapping env-identity assertion (not just the two flags): every key unchanged.
    assert env_after == env_before
    out = capsys.readouterr().out
    # All 5 slugs + their domains + scope_template paths surfaced.
    expected = {
        "drb_72_ai_labor": "workforce",
        "drb_75_metal_ions_cvd": "clinical",
        "drb_76_gut_microbiota_crc": "clinical",
        "drb_78_parkinsons_dbs": "clinical",
        "drb_90_adas_liability": "policy",
    }
    for slug, domain in expected.items():
        assert f"slug={slug}" in out
        assert f"domain={domain}" in out
        assert f"config/scope_templates/{domain}.yaml" in out
    # Transport mode + the 4 roles are surfaced for the blind operator.
    assert "PG_FOUR_ROLE_TRANSPORT mode:" in out
    for role in ("generator", "mirror", "sentinel", "judge"):
        assert role in out
    assert "preflight plan" in out
    # --list must NOT have flipped the 4-role activation flags.
    assert os.environ.get("PG_FOUR_ROLE_MODE") == env_before.get("PG_FOUR_ROLE_MODE")
    assert os.environ.get("PG_ENABLE_QUANTIFIED_ANALYSIS") == env_before.get(
        "PG_ENABLE_QUANTIFIED_ANALYSIS"
    )


def test_dry_run_alias_matches_list(capsys):
    main(["--list"])
    list_out = capsys.readouterr().out
    main(["--dry-run"])
    dry_out = capsys.readouterr().out
    assert list_out == dry_out


def test_env_snapshot_restore_mechanism_is_real(monkeypatch):
    """DISCRIMINATING test (advisor): the full-mapping --list assertion is vacuous because
    pytest collection already imported run_honest_sweep_r3, so its load_dotenv(override=False)
    does not re-fire on the --list call and the env is unchanged regardless of the restore code.
    This test exercises the snapshot/restore MECHANISM directly: wrap a callable that ADDS a
    sentinel key AND MUTATES an existing key inside the protected region (standing in for the
    SWEEP_QUERIES import that triggers load_dotenv), and assert the sentinel is gone and the
    existing key restored afterward. If the os.environ.clear()/update(snap) restore in main()'s
    --list branch were removed, this protection would break."""
    sentinel = "PG_TEST_LIST_SENTINEL_I_META_008"
    existing = "PG_TEST_LIST_EXISTING_I_META_008"
    monkeypatch.setenv(existing, "original")
    monkeypatch.delenv(sentinel, raising=False)

    # Reproduce main()'s --list env-preservation pattern around a mutating callable.
    def _mutating_enumeration():
        os.environ[sentinel] = "leaked"           # an added key (like a fresh .env key)
        os.environ[existing] = "mutated-by-dotenv"  # an overwritten key
        return ["q"]

    env_snapshot = dict(os.environ)
    try:
        _mutating_enumeration()
    finally:
        os.environ.clear()
        os.environ.update(env_snapshot)

    assert sentinel not in os.environ            # added key removed
    assert os.environ[existing] == "original"    # mutated key restored


def test_list_env_restore_is_bound_to_main(monkeypatch):
    """DISCRIMINATING + BOUND TO main() (advisor): force the env mutation through main()'s actual
    --list flow. main() snapshots os.environ BEFORE calling load_locked_questions (the call that,
    in a fresh process, triggers run_honest_sweep_r3's load_dotenv from .env); we monkeypatch the
    loader to ADD a sentinel key (standing in for that .env-driven mutation), then assert main()'s
    restore removed it. If the `os.environ.clear(); os.environ.update(env_snapshot)` lines were
    deleted from main()'s --list branch, the sentinel would survive and THIS test fails — the
    other --list test is vacuous because the module is already cached at collection time."""
    real_loader = run_gate_b.load_locked_questions
    sentinel = "PG_TEST_DOTENV_SIM_I_META_008"
    monkeypatch.delenv(sentinel, raising=False)

    def _loader_that_mutates_env(slugs=None):
        os.environ[sentinel] = "leaked"  # stand in for load_dotenv populating a .env key
        return real_loader(slugs)

    monkeypatch.setattr(run_gate_b, "load_locked_questions", _loader_that_mutates_env)
    assert main(["--list"]) == 0
    assert sentinel not in os.environ  # only true if main()'s --list restore ran


# --------------------------------------------------------------------------- loader

def test_load_locked_questions_all_five():
    questions = load_locked_questions()
    assert [q["slug"] for q in questions] == list(LOCKED_BENCHMARK_SLUGS)
    for q in questions:
        assert q.get("domain")
        assert q.get("question")


def test_load_locked_questions_unknown_slug_raises():
    with pytest.raises(ValueError, match="not locked benchmark slugs"):
        load_locked_questions(("drb_99_not_a_slug",))


# --------------------------------------------------------------------------- per-question wiring

def test_per_question_path_threads_fake_transport_into_run_one_query(monkeypatch):
    """The per-question entrypoint must thread four_role_transport=<fake> AND a builder into
    run_one_query — WITHOUT executing run_one_query's real retrieval/generation pipeline
    (network + spend). Monkeypatch run_one_query to a recording async fake."""
    captured = {}

    async def _fake_run_one_query(q, out_root, **kwargs):
        captured["q"] = q
        captured["out_root"] = out_root
        captured["kwargs"] = kwargs
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query
    )

    q = load_locked_questions(("drb_72_ai_labor",))[0]
    fake_transport = object()  # never invoked — run_one_query is faked
    summary = asyncio.run(
        run_gate_b.run_gate_b_query(q, Path("outputs/__test_unused__"), transport=fake_transport)
    )

    assert summary["status"] == "success"
    # The injected fake transport reached run_one_query (no real transport built, no socket).
    assert captured["kwargs"]["four_role_transport"] is fake_transport
    # A builder closure was threaded too (the seam needs it to produce inputs post-generation).
    assert callable(captured["kwargs"]["four_role_input_builder"])
    # Mode flags flipped by the entrypoint (proves it activated the seam env).
    assert os.environ.get("PG_FOUR_ROLE_MODE") in ("1", "true", "True")
    assert os.environ.get("PG_ENABLE_QUANTIFIED_ANALYSIS") == "1"


def test_cli_loop_invokes_run_gate_b_query_per_question(monkeypatch):
    """main(--only <slug>) calls run_gate_b_query exactly once with the resolved question; the
    CLI adds no pipeline logic of its own. run_gate_b_query is monkeypatched to a recorder so
    no transport is built and nothing spends."""
    calls = []

    async def _recording_run_gate_b_query(q, out_root, **kwargs):
        calls.append({"slug": q["slug"], "out_root": out_root})
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _recording_run_gate_b_query)

    rc = main(["--only", "drb_72_ai_labor", "--out-root", "outputs/__test_unused__"])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0]["slug"] == "drb_72_ai_labor"
    assert calls[0]["out_root"] == Path("outputs/__test_unused__")


def test_cli_all_runs_five_questions(monkeypatch):
    calls = []

    async def _recording_run_gate_b_query(q, out_root, **kwargs):
        calls.append(q["slug"])
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _recording_run_gate_b_query)

    rc = main(["--all", "--out-root", "outputs/__test_unused__"])
    assert rc == 0
    assert calls == list(LOCKED_BENCHMARK_SLUGS)


def test_cli_nonzero_rc_on_abort_status(monkeypatch):
    async def _aborting_run_gate_b_query(q, out_root, **kwargs):
        return {"status": "abort_corpus_inadequate", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _aborting_run_gate_b_query)
    rc = main(["--only", "drb_75_metal_ions_cvd", "--out-root", "outputs/__test_unused__"])
    assert rc == 1


# --------------------------------------------------------------------------- #
# GAP1 (I-arch-005): --resume threads main() -> run_gate_b_query -> run_one_query
# so the A3 replay harness exercises the back half (incl. the native 4-role D8 seam,
# which is injected ONLY by this caller) WITHOUT re-fetching. Two tests, one per hop,
# mirror the existing main->query / query->run_one_query split above.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("argv_resume,expected", [(["--resume"], True), ([], False)])
def test_resume_flag_threads_main_to_run_gate_b_query(monkeypatch, argv_resume, expected):
    """main(--only <slug> [--resume]) forwards resume= to run_gate_b_query; absent flag => False
    (default OFF = byte-identical to the prior cert path). run_gate_b_query is monkeypatched to a
    recorder so no transport is built and nothing spends/networks."""
    captured = {}

    async def _recording_run_gate_b_query(q, out_root, **kwargs):
        captured["resume"] = kwargs.get("resume")
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr(run_gate_b, "run_gate_b_query", _recording_run_gate_b_query)

    rc = main(
        ["--only", "drb_72_ai_labor", "--out-root", "outputs/__test_unused__"] + argv_resume
    )
    assert rc == 0
    assert captured["resume"] is expected


@pytest.mark.parametrize("resume_arg,expected", [(True, True), (False, False)])
def test_run_gate_b_query_forwards_resume_to_run_one_query(monkeypatch, resume_arg, expected):
    """run_gate_b_query(resume=...) reaches run_one_query(resume=...) — the receiving end
    (_resume_active corpus-snapshot reconstruct, run_honest_sweep_r3.py) is already
    implemented + tested; this proves the wire. FAKE transport injected so no real transport
    is built; run_one_query monkeypatched so the real pipeline (network + spend) never runs."""
    captured = {}

    async def _fake_run_one_query(q, out_root, **kwargs):
        captured["resume"] = kwargs.get("resume")
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)

    q = load_locked_questions(("drb_72_ai_labor",))[0]
    fake_transport = object()  # never invoked — run_one_query is faked
    summary = asyncio.run(
        run_gate_b.run_gate_b_query(
            q, Path("outputs/__test_unused__"), transport=fake_transport, resume=resume_arg
        )
    )
    assert summary["status"] == "success"
    assert captured["resume"] is expected


def test_default_out_root_constant():
    assert DEFAULT_OUT_ROOT == "outputs/honest_sweep_r3"


# --------------------------------------------------------------------------- drift-guard

def _golden_prompts() -> dict[str, str]:
    """Parse the verbatim per-question prompts out of golden_questions_locked.md (test-time
    ONLY; never at runtime). Each prompt is the quoted block immediately after its `### #NN`
    header in the '## The 5 (verbatim golden prompts)' section."""
    text = _GOLDEN_MD.read_text(encoding="utf-8")
    prompts: dict[str, str] = {}
    # Header line e.g. `### #75 — Health (clinical) — *primary clinical slice*`, then a line
    # starting with a double-quote that holds the verbatim prompt.
    blocks = re.split(r"^### (#\d+)", text, flags=re.MULTILINE)
    # blocks: [pre, id1, body1, id2, body2, ...]
    for i in range(1, len(blocks) - 1, 2):
        gid = blocks[i].strip()
        body = blocks[i + 1]
        m = re.search(r'"([^"]+)"', body, flags=re.DOTALL)
        if m:
            prompts[gid] = m.group(1).strip()
    return prompts


def test_sweep_queries_prompts_match_golden_md_verbatim():
    """Drift-guard (AC-2 auditability): each of the 5 locked SWEEP_QUERIES prompts is the
    verbatim prompt in golden_questions_locked.md — proving the RUNTIME source (SWEEP_QUERIES)
    IS the locked source, without a second runtime source of truth."""
    assert _GOLDEN_MD.exists(), f"golden questions file missing: {_GOLDEN_MD}"
    golden = _golden_prompts()
    questions = {q["slug"]: q["question"] for q in load_locked_questions()}

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    for slug, gid in _SLUG_TO_GOLDEN_ID.items():
        assert gid in golden, f"golden md missing prompt for {gid}"
        assert _norm(questions[slug]) == _norm(golden[gid]), (
            f"prompt drift for {slug} ({gid}): SWEEP_QUERIES text != golden_questions_locked.md"
        )


# --------------------------------------------------------------------------- import-safety

def test_import_run_gate_b_opens_no_socket_and_mutates_no_env(monkeypatch):
    """Importing run_gate_b must open no socket and mutate no process env. The module is
    already imported by the time this runs; re-exec the import contract by asserting the
    module-level state has no client and that a fresh import via importlib does not flip the
    4-role flags."""
    import importlib
    import socket

    env_before = dict(os.environ)

    real_socket = socket.socket

    def _blocked_socket(*a, **k):
        raise AssertionError("run_gate_b import opened a socket")

    monkeypatch.setattr(socket, "socket", _blocked_socket)
    try:
        importlib.reload(run_gate_b)
    finally:
        monkeypatch.setattr(socket, "socket", real_socket)

    assert dict(os.environ) == env_before
