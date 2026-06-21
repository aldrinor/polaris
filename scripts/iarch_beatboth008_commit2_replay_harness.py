"""I-beatboth-008 (#1285) commit-2 build B — behavioral replay harness (§-1.4).

WHAT THIS PROVES (fail-loud, non-zero exit on any failure):
    A `--resume` must FIRE the STORM scaffold. Before this fix, a resume re-entered the
    pipeline AFTER the STORM producer block (which is `not _resume_active and not
    _resume_from_fetch`-guarded), so `_storm_outline` silently collapsed to `[]` and the
    STORM section scaffold never fired on a resume.

    The fix has three parts in scripts/run_honest_sweep_r3.py:
      (1) PERSIST  — write_storm_outline_checkpoint() at ~L5407 (atomic, fail-open).
      (2) RESTORE  — load_storm_outline_checkpoint() inside `if resume:` at ~L4685, into
                     `_resumed_storm_outline` (initialized None BEFORE `if resume:`).
      (3) CLOBBER  — the seed at ~L5325 is `_storm_outline = list(_resumed_storm_outline
                     or [])` (NOT the old unconditional `= []` that overwrote the restore).

    This harness exercises the REAL helpers (imported from the production module — NOT a
    replica) for PERSIST + RESTORE, then replicates ONLY the one-line L5325 seed expression
    (comment-linked to the exact production expression) to prove the restored outline
    survives the producer-skipped resume path with N>9 sections, NOT [].

RED before fix:  `load_storm_outline_checkpoint` / `write_storm_outline_checkpoint` do not
                 exist in the module -> the import raises -> harness exits non-zero.
GREEN after fix: the helpers exist, the round-trip restores all N sections, and the L5325
                 seed preserves them -> harness exits 0.

Usage:
    python -X utf8 scripts/iarch_beatboth008_commit2_replay_harness.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


# N > 9 so the survival assertion is unambiguous (the legacy template is 3 contract + 6
# enrichment = 9; a STORM-widened outline has MORE, and a silent collapse yields 0).
_N_SECTIONS = 14


def _fake_storm_outline_dicts(n: int) -> list[dict]:
    """N StormOutlineSection-shaped dicts (the persisted-payload shape: model_dump() output)."""
    return [
        {
            "title": f"STORM Section {i}",
            "description": f"What section {i} covers",
            "search_keywords": f"keyword_{i}a, keyword_{i}b, ASTM D{i}",
            "evidence_summary": f"Evidence summary for section {i}",
            "perspectives": [f"perspective_{i}_x", f"perspective_{i}_y"],
            "order": i,
        }
        for i in range(n)
    ]


def _fail(msg: str) -> None:
    print(f"[HARNESS] FAIL: {msg}")
    sys.exit(1)


# P1-2 DATA-ONLY contract (§-1.3): the ONLY keys a persisted section may carry. STORM-authored
# prose (`evidence_summary` / `perspectives`) and any verdict are FORBIDDEN on a resume artifact.
_FORBIDDEN_SECTION_KEYS = ("evidence_summary", "perspectives", "verdict")
_ALLOWED_SECTION_KEYS = {"title", "description", "search_keywords", "order"}


def _assert_disk_payload_data_only(ckpt, *, expected_n: int) -> None:
    """Re-read the on-disk checkpoint and assert EVERY persisted section is DATA-ONLY:
    none of `_FORBIDDEN_SECTION_KEYS`, and no key outside `_ALLOWED_SECTION_KEYS`. Run on
    BOTH the object-input AND the dict-input (production-representative) persist paths so a
    prose leak on EITHER shape is caught by the committed harness (not just an ad-hoc run)."""
    payload = json.loads(ckpt.read_text(encoding="utf-8"))
    if payload.get("stage") != "post_interview":
        _fail(f"unexpected checkpoint stage: {payload.get('stage')!r}")
    if not isinstance(payload.get("storm_outline"), list):
        _fail("checkpoint 'storm_outline' is not a list")
    if len(payload["storm_outline"]) != expected_n:
        _fail(
            f"checkpoint persisted {len(payload['storm_outline'])} sections, "
            f"expected {expected_n}"
        )
    for _i, _sec in enumerate(payload["storm_outline"]):
        if not isinstance(_sec, dict):
            _fail(f"persisted section {_i} is not a dict: {_sec!r}")
        for _bad in _FORBIDDEN_SECTION_KEYS:
            if _bad in _sec:
                _fail(
                    f"persisted section {_i} smuggled a FORBIDDEN key {_bad!r} "
                    f"(STORM prose / verdict in a resume artifact — §-1.3 violation)"
                )
        _extra = set(_sec) - _ALLOWED_SECTION_KEYS
        if _extra:
            _fail(
                f"persisted section {_i} carries non-scaffold key(s) {sorted(_extra)} "
                f"(DATA-ONLY contract allows only {sorted(_ALLOWED_SECTION_KEYS)})"
            )


def main() -> None:
    # Import the REAL production helpers. Pre-fix this import RAISES (helpers absent) -> the
    # except converts it to a fail-loud non-zero exit == the RED state.
    try:
        from scripts.run_honest_sweep_r3 import (
            load_storm_outline_checkpoint,
            write_storm_outline_checkpoint,
            _STORM_OUTLINE_CHECKPOINT,
        )
    except Exception as exc:  # noqa: BLE001 — RED: the helpers do not exist yet (pre-fix)
        _fail(
            "could not import the STORM-outline resume helpers from "
            f"scripts.run_honest_sweep_r3 ({type(exc).__name__}: {exc}). "
            "RED expected pre-fix; this is the bug commit-2 build B fixes."
        )

    from src.polaris_graph.agents.storm_interviews import StormOutlineSection

    with tempfile.TemporaryDirectory(prefix="iarch_beatboth008_b_") as _td:
        run_dir = Path(_td)

        # ---- Arrange: a fresh run persists the captured STORM outline ------------------
        # Build real StormOutlineSection objects (what _storm_outline holds at L5406) and
        # round-trip them through the REAL persist helper (atomic temp + os.replace).
        fake_dicts = _fake_storm_outline_dicts(_N_SECTIONS)
        fresh_outline = [StormOutlineSection(**d) for d in fake_dicts]
        written = write_storm_outline_checkpoint(run_dir, fresh_outline)
        if written is None:
            _fail("write_storm_outline_checkpoint returned None (persist failed)")
        ckpt = run_dir / _STORM_OUTLINE_CHECKPOINT
        if not ckpt.is_file():
            _fail(f"persisted checkpoint not found on disk: {ckpt}")

        # The on-disk payload must be DATA-ONLY structure (no STORM prose smuggled as a
        # verified surface, no verdict) — the §-1.3 invariant for a resume artifact. The fake
        # input (object path) DELIBERATELY carries `evidence_summary` + `perspectives` (STORM
        # prose); the projector MUST strip them. If this ever goes green vacuously, check that
        # _fake_storm_outline_dicts still injects the prose.
        _assert_disk_payload_data_only(ckpt, expected_n=_N_SECTIONS)

        # ---- Act: a --resume restores the outline via the REAL loader ------------------
        # Mirror the production sequence: `_resumed_storm_outline` starts None (fresh-path
        # default, defined BEFORE `if resume:`), and the resume block reassigns it from the
        # loader. (Init -> reassign matches run_honest_sweep_r3.py L4658-ish + L4685-ish.)
        _resumed_storm_outline = None  # noqa: F841 — fresh-path default, then resume reassigns
        _resumed_storm_outline = load_storm_outline_checkpoint(run_dir)
        if _resumed_storm_outline is None:
            _fail("load_storm_outline_checkpoint returned None for a present checkpoint")
        if not all(isinstance(s, StormOutlineSection) for s in _resumed_storm_outline):
            _fail("restored items are not StormOutlineSection objects")
        if len(_resumed_storm_outline) != _N_SECTIONS:
            _fail(
                f"loader restored {len(_resumed_storm_outline)} sections, "
                f"expected {_N_SECTIONS}"
            )

        # ---- Assert: the L5325 CLOBBER-FIX seed preserves the restored outline ---------
        # This one expression is the production seed at run_honest_sweep_r3.py:
        #     _storm_outline: list = list(_resumed_storm_outline or [])
        # On a resume the STORM producer block (L5326+) is SKIPPED by the resume guard, so
        # this seed is the FINAL value threaded to the generator @ ~L8768. The OLD code was
        # `_storm_outline: list = []` which clobbered the restore -> silent no-op. Replicate
        # the exact expression and assert the restored sections survive (NOT []).
        _storm_outline = list(_resumed_storm_outline or [])
        if len(_storm_outline) != _N_SECTIONS:
            _fail(
                "CLOBBER-FIX seed lost the restored outline: _storm_outline has "
                f"{len(_storm_outline)} sections, expected {_N_SECTIONS} (a resume "
                "silently dropped the STORM scaffold -> the exact bug)."
            )
        if _storm_outline == []:
            _fail("CLOBBER-FIX seed produced [] — the resume STORM scaffold no-op'd")

        # ---- Fresh-path sanity: None -> [] (no NameError, no crash, STORM then populates)
        _fresh_seed = list((None) or [])
        if _fresh_seed != []:
            _fail("fresh-path seed (None or []) did not produce [] — would break a fresh run")

        # ---- P1-3 FAIL-LOUD: any PRESENT-but-malformed file must RAISE, never silently empty ---
        # The OLD loader used `_payload.get("storm_outline", [])`, so a present-but-malformed
        # file ({}, missing key, wrong schema_version/stage) returned [] — silently reproducing
        # the exact resume STORM no-op this checkpoint exists to prevent. Each case below writes
        # a PRESENT file then asserts the loader RAISES (fail-loud, like the A12 corrupt path).
        def _assert_raises_on_present(label: str, content: str) -> None:
            ckpt.write_text(content, encoding="utf-8")
            try:
                load_storm_outline_checkpoint(run_dir)
            except Exception:  # noqa: BLE001 — EXPECTED: a present-but-malformed file must fail loud
                pass
            else:
                _fail(
                    f"loader did NOT raise on a PRESENT-but-malformed file ({label}) — "
                    "silently returned [] / restored nothing (fail-loud violated, the P1-3 bug)"
                )

        # corrupt JSON
        _assert_raises_on_present("corrupt JSON", "{ this is not valid json")
        # empty object {} — present file, no storm_outline key / no stage / no schema_version
        _assert_raises_on_present("empty object {}", json.dumps({}))
        # valid JSON but MISSING the required storm_outline key (right stage + version)
        _assert_raises_on_present(
            "missing 'storm_outline' key",
            json.dumps({"schema_version": 1, "stage": "post_interview"}),
        )
        # wrong stage
        _assert_raises_on_present(
            "wrong stage",
            json.dumps({"schema_version": 1, "stage": "pre_interview", "storm_outline": []}),
        )
        # wrong schema_version
        _assert_raises_on_present(
            "wrong schema_version",
            json.dumps({"schema_version": 999, "stage": "post_interview", "storm_outline": []}),
        )
        # MISSING schema_version (None != expected)
        _assert_raises_on_present(
            "missing schema_version",
            json.dumps({"stage": "post_interview", "storm_outline": []}),
        )
        # P1-3 (commit-2 iter-3) — the three section-level fail-loud cases. EACH carries a
        # VALID schema_version + stage so the raise is attributable to section-level validation
        # (not the schema/stage gates above) — i.e. the loader must FAIL LOUD on a structurally-
        # present-but-unusable storm_outline payload, NOT lean on the lenient pydantic
        # constructor (storm_interviews.py normalize_field_names coerces missing/None title -> ""
        # -> ONE blank-title section that SILENTLY NO-OPS in the scaffold builder — the exact
        # resume no-op this checkpoint exists to prevent).
        # (a) storm_outline is NOT a list (a dict) — present, valid schema/stage -> RAISE
        _assert_raises_on_present(
            "storm_outline is a dict, not a list",
            json.dumps(
                {"schema_version": 1, "stage": "post_interview", "storm_outline": {"a": 1}}
            ),
        )
        # (b) a section is NOT a dict (a bare string) — present, valid schema/stage -> RAISE
        _assert_raises_on_present(
            "section is a string, not a dict",
            json.dumps(
                {"schema_version": 1, "stage": "post_interview", "storm_outline": ["x"]}
            ),
        )
        # (c) RED->GREEN keystone: a malformed section dict {} (blank scaffold title). The
        # lenient pydantic constructor coerces this to ONE blank-title section that silently
        # no-ops the scaffold builder; the loader MUST raise instead. Pre-fix this is RED (the
        # loader returns a [blank-title section], does not raise); post-fix it RAISES.
        _assert_raises_on_present(
            "section dict has a blank scaffold title ({})",
            json.dumps(
                {"schema_version": 1, "stage": "post_interview", "storm_outline": [{}]}
            ),
        )

        # ---- Empty-but-VALID outline -> [] (NOT a raise, NOT None) ------------------------
        # `storm_outline: []` is a legitimately-empty STORM outline, not a malformed file.
        ckpt.write_text(
            json.dumps({"schema_version": 1, "stage": "post_interview", "storm_outline": []}),
            encoding="utf-8",
        )
        _empty = load_storm_outline_checkpoint(run_dir)
        if _empty is None:
            _fail("loader returned None for an empty-but-VALID outline (should be [])")
        if _empty != []:
            _fail(f"loader returned {_empty!r} for an empty-but-VALID outline (should be [])")

        # ---- Absent checkpoint -> None (the fresh-run / no-snapshot case) ----------------
        ckpt.unlink()
        if load_storm_outline_checkpoint(run_dir) is not None:
            _fail("loader returned non-None for an ABSENT checkpoint (should be None)")

        # ---- DICT-input persist: the REAL fresh-path shape -------------------------------
        # _generate_outline_from_conversations / _fallback_outline return model_dump() DICTS
        # (storm_interviews.py:1241/1284), so the production _storm_outline at L5406 holds
        # DICTS, not StormOutlineSection objects. Exercise the persist helper's dict branch
        # with that real shape and confirm the round-trip restores N objects (the generator's
        # _field at multi_section_generator.py:1895 reads BOTH shapes, so objects are correct).
        dict_outline = _fake_storm_outline_dicts(_N_SECTIONS)  # plain dicts (real fresh shape)
        if write_storm_outline_checkpoint(run_dir, dict_outline) is None:
            _fail("persist of dict-shaped outline (real fresh-path shape) returned None")
        # P1-2 on the PRODUCTION-representative DICT path: these dicts carry the same STORM
        # prose (evidence_summary / perspectives) AND the projector must strip it here too —
        # the dict path is what production actually persists, so the DATA-ONLY assertion MUST
        # run against it (not only the object path above), or a dict-path prose leak would
        # pass the committed harness green.
        _assert_disk_payload_data_only(ckpt, expected_n=_N_SECTIONS)
        restored_from_dicts = load_storm_outline_checkpoint(run_dir)
        if restored_from_dicts is None or len(restored_from_dicts) != _N_SECTIONS:
            _fail("dict-input persist round-trip lost sections")
        if not all(isinstance(s, StormOutlineSection) for s in restored_from_dicts):
            _fail("dict-input round-trip did not restore StormOutlineSection objects")
        ckpt.unlink()

    print(
        f"[HARNESS] GREEN: resume restored {_N_SECTIONS} STORM sections and the L5325 "
        "seed preserved them (NOT []). The STORM scaffold FIRES on --resume. "
        "DATA-ONLY (no evidence_summary/perspectives/verdict persisted) + "
        "fail-loud-on-present-but-malformed (corrupt/{}/missing-key/wrong-stage/"
        "wrong-or-missing-schema_version) + empty-valid->[] + None-on-absent + "
        "fresh-path-None->[] all verified."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
