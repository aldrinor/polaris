#!/usr/bin/env python
"""§-1.4 BEHAVIORAL fire-test for the CRAG adequacy CLASSIFIER + loop-back
(W7, I-wire-001 #1305).

FAIL-LOUD canary (NOT a stubbed unit test). Drives the REAL
`scripts/run_honest_sweep_r3.py --only <slug>` end-to-end on a deliberately
STARVED initial corpus, twice:

  * FLAG-OFF  (`PG_ADEQUACY_CRAG` unset): the legacy count-floor single-pass
    path runs. Assert NO `crag_adequacy_loop.json` artifact is written
    (byte-identical legacy: the classifier, the LLM call, the loop, and the
    artifact all live inside the flag-ON branch).

  * FLAG-ON   (`PG_ADEQUACY_CRAG=1`, `PG_ADEQUACY_CRAG_MAX_LOOPS=1`): the CRAG
    sufficiency CLASSIFIER (the bal-acc=1.0 winner mechanism, ported from the
    bake-off `crag_design`) is INVOKED, grades the corpus, and DRIVES the STOP
    decision (decision_source="crag_classifier"). On a not-sufficient verdict
    it fires EXACTLY ONE bounded corrective loop-back, the gap corpus is
    widened, and a NEWLY-INJECTED source (a URL NOT in the initial corpus) is
    actually CITED in the rendered output (`bibliography.json` / report.md).

THE DISCRIMINATING ASSERTIONS (the in-the-slate-not-in-the-output trap +
the Codex P1 — "the classifier is never invoked", §-1.4):

  (A) `crag_adequacy_loop.json` records `decision_source="crag_classifier"`
      and >= 1 classification with `invoked=True` and a real verdict
      (correct/ambiguous/incorrect) — proving the CLASSIFIER ran and was the
      decision source, NOT the count-floor. If the classifier never ran, the
      verdict list is empty / decision_source is wrong => non-zero exit.

  (B) An injected source must be CITED in the rendered output, not merely added
      to the corpus slate: the intersection of
      `crag_adequacy_loop.json.injected_urls` with the URLs actually CITED in
      `bibliography.json` is NON-EMPTY. Empty intersection => non-zero exit
      (the loop widened the corpus but nothing reached the page = the real bug,
      caught).

Run directly (needs OPENROUTER + SERPER keys + network — a LIVE run):

    python tests/polaris_graph/test_crag_adequacy_loop_fire.py

Exit 0 => both legs fired as asserted. Non-zero => the classifier did not drive
the decision, or the effect did NOT appear in the real output (fail-loud).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_honest_sweep_r3.py"

# The run-script and this canary emit UTF-8 (→, ≤, …). On Windows the parent's
# stdout defaults to cp1252, so printing the captured run output raises
# UnicodeEncodeError. Reconfigure THIS process's stdout/stderr to UTF-8 with
# errors="replace" so diagnostics never crash the canary on a stray glyph.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — older/odd streams; best-effort only
        pass

# Load .env so the LIVE keys are present in this process's guard AND inherited by
# the subprocess env (the run-script also calls load_dotenv, but the top-level
# key guard below runs in THIS process before any subprocess is spawned).
try:
    from dotenv import load_dotenv

    load_dotenv()  # walks up to the repo .env
except Exception:  # noqa: BLE001 — dotenv optional; keys may be in the ambient env
    pass

# A tech-domain query (lowest count-floor thresholds) so ONE loop-back can
# widen the corpus and a real source can be cited. The CLASSIFIER, not the
# count-floor, decides sufficiency on the ON leg.
QUERY_SLUG = os.getenv("PG_CRAG_FIRE_TEST_SLUG", "tech_rag_architectures_2024")

# STARVE the initial retrieval so the first-pass corpus is thin enough that the
# CRAG confidence grader returns AMBIGUOUS / INCORRECT (not sufficient).
_STARVE_ENV = {
    "PG_SWEEP_MAX_SERPER": "2",
    "PG_SWEEP_MAX_S2": "0",
    "PG_SWEEP_FETCH_CAP": "3",
    "PG_SIMPLE_FETCH_CAP": "3",
}
# Generous loop-back caps so the ONE corrective round closes the gap.
_CRAG_LOOP_ENV = {
    "PG_ADEQUACY_CRAG_MAX_SERPER": "12",
    "PG_ADEQUACY_CRAG_MAX_S2": "12",
    "PG_ADEQUACY_CRAG_FETCH_CAP": "24",
}


def _run(out_root: Path, *, flag_on: bool) -> Path:
    """Run the sweep once; return the per-query run directory."""
    env = dict(os.environ)
    env.update(_STARVE_ENV)
    # Force UTF-8 stdio in the subprocess so the run-script's own UTF-8 prints
    # (→, ≤, …) do not raise UnicodeEncodeError when its stdout is a pipe (the
    # subprocess exit 2147483651 = a cp1252 encode crash on a piped tty).
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # Structured operator authorization (spend authorized — speed over cost):
    # set on BOTH legs so the corpus-approval gate's material-deviation refusal
    # does not pre-empt the comparison. The ONLY difference between the two legs
    # remains the CRAG flag. This is an operator credential, NOT a faithfulness
    # relaxation — strict_verify / 4-role / provenance still gate every source.
    env["PG_AUTHORIZED_SWEEP_APPROVAL"] = "1"
    if flag_on:
        env["PG_ADEQUACY_CRAG"] = "1"
        env["PG_ADEQUACY_CRAG_MAX_LOOPS"] = "1"
        env.update(_CRAG_LOOP_ENV)
    else:
        # Ensure a clean OFF baseline even if the host env had it set.
        env.pop("PG_ADEQUACY_CRAG", None)
        env.pop("PG_ADEQUACY_CRAG_MAX_LOOPS", None)

    cmd = [
        sys.executable, str(SCRIPT),
        "--only", QUERY_SLUG,
        "--out-root", str(out_root),
    ]
    leg = "ON" if flag_on else "OFF"
    print(f"\n=== [{leg}] {' '.join(cmd)}", flush=True)
    # The run-script emits UTF-8 (→, ≤, …). On Windows the default cp1252 decode
    # raises UnicodeDecodeError mid-stream; force UTF-8 with errors="replace" so
    # capturing the run's own output never crashes the canary.
    proc = subprocess.run(
        cmd, env=env, cwd=str(ROOT),
        capture_output=True, text=True, timeout=2400,
        encoding="utf-8", errors="replace",
    )
    print(f"=== [{leg}] exit={proc.returncode}", flush=True)
    # Surface the tail so a failure is diagnosable (guard None on early failure).
    print((proc.stdout or "")[-3000:], flush=True)
    if proc.returncode != 0:
        print((proc.stderr or "")[-3000:], flush=True)

    run_dirs = sorted(out_root.rglob("manifest.json"))
    if not run_dirs:
        raise SystemExit(f"FAIL [{leg}]: no manifest.json produced under {out_root}")
    return run_dirs[0].parent


def _cited_urls(run_dir: Path) -> set[str]:
    bib = run_dir / "bibliography.json"
    if not bib.exists():
        return set()
    data = json.loads(bib.read_text(encoding="utf-8"))
    return {
        (e.get("url") or "").strip()
        for e in data
        if isinstance(e, dict) and (e.get("url") or "").strip()
    }


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY") or not os.getenv("SERPER_API_KEY"):
        raise SystemExit(
            "FAIL: OPENROUTER_API_KEY + SERPER_API_KEY required for the LIVE "
            "fire-test (this is a behavioral canary, not a stub)."
        )

    # PG_CRAG_FIRE_OUT_ROOT: when set, use a PERSISTENT out-root (not auto-
    # cleaned) so the real rendered output survives for a §-1.1 line-by-line
    # audit after the canary exits. Unset => ephemeral temp dirs (clean canary).
    _persist = os.getenv("PG_CRAG_FIRE_OUT_ROOT", "").strip()
    if _persist:
        off_root_p = Path(_persist) / "off"
        on_root_p = Path(_persist) / "on"
        off_root_p.mkdir(parents=True, exist_ok=True)
        on_root_p.mkdir(parents=True, exist_ok=True)
        _off_cm = _on_cm = None
        off_root, on_root = str(off_root_p), str(on_root_p)
    else:
        _off_cm = tempfile.TemporaryDirectory(prefix="crag_fire_off_")
        _on_cm = tempfile.TemporaryDirectory(prefix="crag_fire_on_")
        off_root, on_root = _off_cm.name, _on_cm.name

    try:
        # ── FLAG-OFF leg: byte-identical legacy (no loop-back artifact) ──
        off_dir = _run(Path(off_root), flag_on=False)
        off_trace = off_dir / "crag_adequacy_loop.json"
        if off_trace.exists():
            raise SystemExit(
                "FAIL [OFF]: crag_adequacy_loop.json was written with the flag "
                "OFF — flag-OFF is NOT byte-identical legacy."
            )
        off_manifest = json.loads((off_dir / "manifest.json").read_text("utf-8"))
        off_status = off_manifest.get("status", "")
        print(f"[OFF] status={off_status}  (no loop-back artifact: OK)")

        # ── FLAG-ON leg: classifier INVOKED + drove decision + injected cited ──
        on_dir = _run(Path(on_root), flag_on=True)
        on_trace_path = on_dir / "crag_adequacy_loop.json"
        if not on_trace_path.exists():
            raise SystemExit(
                "FAIL [ON]: crag_adequacy_loop.json missing — the CRAG block did "
                "not run with the flag ON."
            )
        trace = json.loads(on_trace_path.read_text("utf-8"))

        # ── DISCRIMINATING ASSERTION (A): the CLASSIFIER drove the decision ──
        decision_source = trace.get("decision_source")
        classifications = trace.get("classifications") or []
        if decision_source != "crag_classifier":
            raise SystemExit(
                f"FAIL [ON]: decision_source={decision_source!r}, expected "
                "'crag_classifier'. The count-floor still drives the STOP "
                "decision — the classifier is decorative (the Codex P1)."
            )
        if not classifications:
            raise SystemExit(
                "FAIL [ON]: no CRAG classifications recorded — the sufficiency "
                "CLASSIFIER was never invoked (the Codex P1)."
            )
        first = classifications[0]
        if not first.get("invoked"):
            raise SystemExit(
                "FAIL [ON]: first classification invoked=False — the classifier "
                "did not actually run."
            )
        if first.get("verdict") not in {"correct", "ambiguous", "incorrect"}:
            raise SystemExit(
                f"FAIL [ON]: classifier returned a non-grade verdict "
                f"{first.get('verdict')!r} ('error'/'unparseable') — the live "
                "GLM grade did not parse. Check the model/keys."
            )
        print(
            f"[ON] classifier INVOKED  decision_source={decision_source}  "
            f"initial_verdict={trace.get('initial_crag_verdict')}  "
            f"final_verdict={trace.get('final_crag_verdict')}  "
            f"classifications={len(classifications)}"
        )

        loops = int(trace.get("loops_fired", 0))
        injected = {u for u in trace.get("injected_urls", []) if u}
        max_loops = int(trace.get("max_loops", 0))
        print(f"[ON] loops_fired={loops}  max_loops={max_loops}  "
              f"injected={len(injected)}  final_sufficient={trace.get('final_sufficient')}")

        # If the classifier graded the STARVED corpus sufficient on the first
        # pass, the loop-back legitimately does not fire — but then this test
        # cannot discriminate the loop-back effect. Treat that as a tuning fail
        # (starve harder), not a silent pass.
        if bool(trace.get("initial_sufficient", classifications[0].get("sufficient"))):
            raise SystemExit(
                "FAIL [ON]: the CRAG classifier graded the STARVED corpus "
                "SUFFICIENT on the first pass (verdict=CORRECT), so the loop-back "
                "did not fire and the effect cannot be discriminated. Starve "
                "harder (lower _STARVE_ENV) so the grader returns AMBIGUOUS/"
                "INCORRECT."
            )
        if loops < 1:
            raise SystemExit(
                "FAIL [ON]: classifier graded the corpus not-sufficient but the "
                f"loop-back did NOT fire (loops_fired={loops}). The corrective "
                "action no-opped."
            )
        if loops > max_loops:
            raise SystemExit(
                f"FAIL [ON]: loops_fired={loops} exceeds the bound max_loops={max_loops}."
            )
        if not injected:
            raise SystemExit(
                "FAIL [ON]: the loop-back fired but injected ZERO new sources — "
                "the corrective retrieval found nothing the initial pass lacked."
            )

        # ── DISCRIMINATING ASSERTION (B): an injected source is CITED ──
        cited = _cited_urls(on_dir)
        cited_from_loopback = injected & cited
        print(f"[ON] cited_urls={len(cited)}  "
              f"cited_from_loopback={len(cited_from_loopback)}")
        if not cited_from_loopback:
            raise SystemExit(
                "FAIL [ON]: the loop-back widened the corpus (injected="
                f"{len(injected)}) but NONE of the injected sources reached the "
                "rendered bibliography (in-the-slate-not-in-the-output). The "
                "effect did NOT appear in report.md."
            )

        example = sorted(cited_from_loopback)[0]
        print(
            "\nPASS: CRAG sufficiency CLASSIFIER drove the STOP decision and the "
            "corrective loop-back effect APPEARS in the real output.\n"
            f"  flag-OFF: no loop-back artifact; status={off_status} (byte-identical legacy)\n"
            f"  flag-ON:  classifier INVOKED, decision_source=crag_classifier, "
            f"initial_verdict={trace.get('initial_crag_verdict')}\n"
            f"  flag-ON:  loops_fired={loops} (bounded <= {max_loops}); "
            f"{len(injected)} sources injected by the loop-back\n"
            f"  newly-cited-from-loopback source(s)={len(cited_from_loopback)}; "
            f"example={example}"
        )
        return 0
    finally:
        # Release ephemeral temp dirs (no-op when PG_CRAG_FIRE_OUT_ROOT is set).
        if _off_cm is not None:
            _off_cm.cleanup()
        if _on_cm is not None:
            _on_cm.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
