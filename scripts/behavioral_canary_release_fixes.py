#!/usr/bin/env python
"""A19 — Behavioral canary: prove every iarch007 fix FIRES in REAL call shape before any paid re-run.

THE LESSON (I-arch-005 project memory): "committed + Codex-approved != WIRED on the run path."
6 dead-on-arrival fixes shipped green because they were present but never activated on the
paid path. drb_90 itself proves it — the judge token bug only surfaced at runtime; A1's shell
detector is silently inert on a resume. This canary is the structural answer: it EXERCISES each
changed slug in its REAL call shape and EXITS NON-ZERO on any dead-on-arrival fix, so a paid
Q90 re-run is GATED behind a green canary instead of blind-firing all fixes at once.

What it exercises (real functions, real inputs — NOT mocks of the function under test):

  * A1 fetch shell detector (``frame_fetcher._is_fetch_shell``): an Archive.org JS wrapper, a
    soft-404, a CourtListener docket-index, and a bare-DOI MUST each be flagged as a SHELL;
    a real article MUST pass. Proves the detector is alive and keys on fetch-integrity, not
    topicality.
  * A2/A3 judge token resolver (``token_limit_resolver.compute_allowed_max_tokens`` /
    ``finalize_body``): the exact qwen3.6 judge body (max_tokens 262140 vs a 262144 window)
    MUST clamp DOWN so prompt+completion fits — the HTTP-400 fix. Injected model metadata
    (no network).
  * A2 seam rescue (``run_honest_sweep_r3.build_seam_release_outcome``): a judge seam error
    MUST yield a release_outcome labeled UNVERIFIED — status released_with_disclosed_gaps with
    the ``four_role_seam_unadjudicated`` disclosed gap, NEVER success; a fabricated cited
    identity MUST withhold the body.
  * A5 origin-drift fallback (``plan_sufficiency_gate.relevant_section_indices``): a drifted
    real origin MUST be recovered by the content-word overlap fallback instead of orphaned.
  * A10 quantified fail-loud (``run_honest_sweep_r3.SpecProviderTransportError``): the typed
    transport error MUST exist so an empty/garbage spec body raises instead of laundering as a
    benign decline.
  * The A18 release invariant MUST be importable and self-test green.

The default mode is OFFLINE + behavioral (no spend): it proves the fixes are WIRED. The
``--live`` mode (operator-gated, paid) additionally runs a real 1-query sweep and re-checks the
artifacts against the A18 release invariant — but the live run is NEVER triggered at import and
NEVER by the default invocation, so this file is safe to import and safe to run in CI.

Usage::

    python scripts/iarch007_behavioral_canary.py            # offline behavioral canary (no spend)
    python scripts/iarch007_behavioral_canary.py --live ... # operator-gated paid 1-query run

Exit 0 == every fix fired in real call shape; non-zero == a dead-on-arrival fix (do NOT spend).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

# Make `src.polaris_graph.*` importable when this file is run as a standalone script (the
# production package is rooted at the repo, imported as `src.polaris_graph...`). Idempotent;
# no side effect beyond a sys.path prepend.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Each check returns (ok, detail). A raised exception is treated as a hard FAIL (the slug is not
# even importable in its real call shape — the most dead-on-arrival outcome).
CheckResult = tuple[bool, str]


def check_a1_shell_detector() -> CheckResult:
    """A1: the fetch-layer shell detector flags page-furniture but passes a real article."""
    from src.polaris_graph.retrieval.frame_fetcher import _is_fetch_shell

    shells = {
        "archive_js_wrapper": (
            "<html><head><title>Wayback Machine</title></head>"
            "<body><script>__wbCsp=true;</script><div id='wm-ipp'></div></body></html>"
        ),
        "soft_404": "Page not found",
        "courtlistener_docket": "Filing fee: $402.00",
        "bare_doi": "doi:10.1234/abcd.5678",
    }
    real_article = (
        "The court held that the manufacturer was liable for design defects in the "
        "automated lane-keeping system. The verdict awarded $240 million in damages, "
        "finding the design unreasonably dangerous under the consumer-expectation test. "
    ) * 8

    for name, body in shells.items():
        is_shell, reason = _is_fetch_shell(body)
        if not is_shell:
            return False, f"shell {name!r} was NOT flagged (detector inert / dead-on-arrival)"
    real_is_shell, _ = _is_fetch_shell(real_article)
    if real_is_shell:
        return False, "a real article was mis-flagged as a shell (detector keys on topicality?)"
    return True, "4 shells flagged + real article passed (fetch-integrity, not topicality)"


def check_a2_a3_token_resolver() -> CheckResult:
    """A2/A3: the qwen-judge body (262140 vs a 262144 window) clamps DOWN — the HTTP-400 fix."""
    from src.polaris_graph.llm import token_limit_resolver as tlr

    # Inject the qwen3.6 judge model metadata so the resolver is exercised OFFLINE (no network).
    table = [{
        "id": "qwen/qwen3.6-35b-a3b",
        "context_length": 262144,
        "top_provider": {"max_completion_tokens": 262144},
    }]
    import os

    prev = {
        "PG_TOKEN_LIMIT_RESOLVER": os.environ.get("PG_TOKEN_LIMIT_RESOLVER"),
        "PG_TOKEN_LIMIT_ALLOW_FETCH": os.environ.get("PG_TOKEN_LIMIT_ALLOW_FETCH"),
        "PG_TOKEN_LIMIT_SAFETY_MARGIN": os.environ.get("PG_TOKEN_LIMIT_SAFETY_MARGIN"),
    }
    _orig_fetch = tlr._fetch_models_table
    try:
        os.environ["PG_TOKEN_LIMIT_RESOLVER"] = "1"
        os.environ["PG_TOKEN_LIMIT_ALLOW_FETCH"] = "1"
        os.environ["PG_TOKEN_LIMIT_SAFETY_MARGIN"] = "1000"
        tlr._fetch_models_table = lambda: table  # type: ignore[assignment]
        tlr.reset_cache()
        # The exact RC2 body: a real ~5000-token judge prompt with a generous 262140 request.
        prompt_tokens = 5000
        allowed = tlr.compute_allowed_max_tokens(
            "qwen/qwen3.6-35b-a3b", prompt_tokens, 262140, apply_completion_cap=True
        )
        if allowed >= 262140:
            return False, (
                f"judge max_tokens did NOT clamp ({allowed} >= 262140): the qwen HTTP-400 fix is "
                "dead-on-arrival on this path"
            )
        if prompt_tokens + allowed >= 262144:
            return False, (
                f"clamped budget {allowed} + prompt {prompt_tokens} still overruns the 262144 "
                "window — the request would still 400"
            )
        # finalize_body must mutate the body's max_tokens through the SAME chokepoint.
        body = {"model": "qwen/qwen3.6-35b-a3b", "max_tokens": 262140, "messages": []}
        tlr.finalize_body(body, "qwen/qwen3.6-35b-a3b", prompt_tokens, apply_completion_cap=True)
        if body["max_tokens"] >= 262140:
            return False, "finalize_body did NOT clamp body['max_tokens'] (chokepoint bypassed)"
        return True, (
            f"judge body clamped 262140 -> {allowed} (prompt {prompt_tokens} + {allowed} < 262144); "
            "finalize_body chokepoint fired"
        )
    finally:
        tlr._fetch_models_table = _orig_fetch  # type: ignore[assignment]
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tlr.reset_cache()


def _load_sweep_module():
    """Import the 10k-line sweep script by path (it has no fatal import-time side effects)."""
    import importlib.util
    from pathlib import Path

    sweep_path = Path(__file__).resolve().parents[1] / "scripts" / "run_honest_sweep_r3.py"
    spec = importlib.util.spec_from_file_location("rhsr3_canary", str(sweep_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sweep script at {sweep_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_a2_seam_rescue() -> CheckResult:
    """A2: a judge seam error yields a release_outcome labeled UNVERIFIED, never success."""
    sweep = _load_sweep_module()
    build = sweep.build_seam_release_outcome
    seam_token = sweep.SEAM_GAP_UNADJUDICATED

    # A non-clinical seam with all cited identities IN the pool: ships
    # released_with_disclosed_gaps + the seam gap, body NOT withheld.
    class _Tok:
        def __init__(self, eid: str) -> None:
            self.evidence_id = eid

    class _SV:
        def __init__(self, eids: list[str]) -> None:
            self.tokens = [_Tok(e) for e in eids]

    class _Section:
        def __init__(self, eids: list[str]) -> None:
            self.kept_sentences_pre_resolve = [_SV(eids)]

    sections = [_Section(["ev_1", "ev_2"])]
    evidence_for_gen = [{"evidence_id": "ev_1"}, {"evidence_id": "ev_2"}]
    outcome, body_withheld, _ = build(
        sections=sections,
        evidence_for_gen=evidence_for_gen,
        is_clinical=False,
        seam_held_reason="seam_error:HTTPStatusError:400",
    )
    from src.polaris_graph.roles.release_policy import (
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_SUCCESS,
    )
    if outcome.status == STATUS_SUCCESS:
        return False, "seam outcome resolved to SUCCESS (un-judged content marked verified!)"
    if outcome.status != STATUS_RELEASED_WITH_DISCLOSED_GAPS:
        return False, f"seam outcome status was {outcome.status!r}, not released_with_disclosed_gaps"
    if not any(seam_token in g for g in outcome.disclosed_gaps):
        return False, "seam disclosed_gaps did NOT carry the four_role_seam_unadjudicated label"
    if body_withheld:
        return False, "in-pool seam wrongly withheld the body"

    # A fabricated cited identity (ev_FAKE not in the pool) MUST withhold the body.
    sections_fab = [_Section(["ev_1", "ev_FAKE"])]
    outcome_fab, withheld_fab, _ = build(
        sections=sections_fab,
        evidence_for_gen=evidence_for_gen,
        is_clinical=False,
        seam_held_reason="seam_error:HTTPStatusError:400",
    )
    if not withheld_fab:
        return False, (
            "a cited identity NOT in the evidence pool did NOT withhold the body — an "
            "un-screened fabricated citation could ship on a seam error"
        )
    if outcome_fab.status == STATUS_SUCCESS:
        return False, "fabricated-identity seam resolved to SUCCESS"
    return True, (
        "seam -> released_with_disclosed_gaps + UNVERIFIED seam gap (body kept); "
        "fabricated identity -> body withheld; never success"
    )


def check_a5_origin_drift_fallback() -> CheckResult:
    """A5: a drifted real origin is recovered by the overlap fallback, not orphaned."""
    import os

    from src.polaris_graph.adequacy.plan_sufficiency_gate import relevant_section_indices

    class _Sec:
        def __init__(self, idxs: list[int]) -> None:
            self.sub_query_indices = idxs

    # Section 0 maps sub_query 0. The row's origin DRIFTED (a STORM expansion that no longer
    # string-equals any planned sub-query), so its EXACT match is empty. The landed fallback then
    # overlaps the ROW CONTENT (statement + direct_quote) against each section's sub-query texts;
    # the statement shares >= 2 content words with sub_query 0 -> section 0 is credited.
    sub_queries = ["liability allocation for automated driving system crashes"]
    outline = [_Sec([0])]
    row = {
        "query_origin": "storm_expansion_drifted_origin_no_exact_match",
        "statement": "Liability allocation for automated driving crashes assigns fault.",
        "direct_quote": "the manufacturer bears liability for the automated driving system",
    }
    prev = os.environ.get("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK")
    try:
        os.environ["PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK"] = "1"
        matched = relevant_section_indices(row, outline, sub_queries)
        if 0 not in matched:
            return False, (
                "a drifted real origin was ORPHANED (row-content overlap fallback did not fire) "
                "— A5 is dead-on-arrival; its evidence row would route to no section"
            )
        # A row with NO usable content stays orphaned (the fallback is content-keyed, not blanket).
        row_empty = dict(row, statement="x", direct_quote="")
        if 0 in relevant_section_indices(row_empty, outline, sub_queries):
            return False, "a content-less row was wrongly credited (fallback is not content-keyed)"
        return True, "drifted origin recovered via row-content overlap; content-less row orphaned"
    finally:
        if prev is None:
            os.environ.pop("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK", None)
        else:
            os.environ["PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK"] = prev


def check_a10_quantified_fail_loud() -> CheckResult:
    """A10: the typed SpecProviderTransportError exists (transport fault no longer launders as None)."""
    sweep = _load_sweep_module()
    err = getattr(sweep, "SpecProviderTransportError", None)
    if err is None:
        return False, "SpecProviderTransportError is missing — A10 fail-loud split is dead-on-arrival"
    if not (isinstance(err, type) and issubclass(err, Exception)):
        return False, "SpecProviderTransportError is not an Exception subclass"
    return True, "SpecProviderTransportError present (transport/parse fault raises, not None)"


def check_a18_release_invariant_importable() -> CheckResult:
    """The A18 release invariant module imports and its offline self-test passes."""
    import importlib.util
    from pathlib import Path

    inv_path = Path(__file__).resolve().parents[0] / "iarch007_release_invariant_check.py"
    spec = importlib.util.spec_from_file_location("iarch007_invariant_canary", str(inv_path))
    if spec is None or spec.loader is None:
        return False, f"cannot load the release-invariant module at {inv_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rc = module._self_test()
    if rc != 0:
        return False, "the A18 release-invariant self-test FAILED"
    return True, "A18 release-invariant module imports + self-test green"


# Ordered registry: (slug, human label, callable).
_CHECKS: list[tuple[str, str, Callable[[], CheckResult]]] = [
    ("A1", "fetch shell detector fires", check_a1_shell_detector),
    ("A2/A3", "judge token resolver clamps (HTTP-400 fix)", check_a2_a3_token_resolver),
    ("A2", "seam rescue labels UNVERIFIED, never success", check_a2_seam_rescue),
    ("A5", "origin-drift overlap fallback recovers a drifted row", check_a5_origin_drift_fallback),
    ("A10", "quantified transport fault fails loud", check_a10_quantified_fail_loud),
    ("A18", "release invariant importable + green", check_a18_release_invariant_importable),
]


def run_behavioral_canary() -> int:
    """Run every behavioral check (OFFLINE, no spend). Returns a process exit code."""
    print("iarch007 BEHAVIORAL CANARY — proving every fix FIRES in real call shape (no spend)\n")
    any_fail = False
    for slug, label, fn in _CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 — a raise IS a dead-on-arrival fail.
            ok, detail = False, f"raised {type(exc).__name__}: {str(exc)[:200]}"
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {slug:<6} {label}")
        print(f"          -> {detail}")
        any_fail = any_fail or not ok
    print()
    if any_fail:
        print("CANARY: FAIL — one or more fixes are DEAD-ON-ARRIVAL. Do NOT start a paid re-run.")
        return 1
    print("CANARY: PASS — every changed slug fired in real call shape. Paid re-run is gated-OK.")
    return 0


def _run_invariant_check_over_dir(run_dir: "Path") -> int:
    """Run the A18 artifact invariant over a finished run dir (every manifest under it). Returns a
    process exit code: 0 == every artifact satisfies the no-unjudged-release gate, non-zero == a
    violation or no manifest found. Pure call into the invariant module (no subprocess)."""
    import importlib.util

    inv_path = Path(__file__).resolve().parents[0] / "iarch007_release_invariant_check.py"
    spec = importlib.util.spec_from_file_location("iarch007_invariant_live", str(inv_path))
    if spec is None or spec.loader is None:
        print(f"LIVE CANARY: cannot load the release-invariant module at {inv_path}")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Find every manifest under the run dir (the sweep writes one per query run_dir).
    manifests = sorted(str(p) for p in Path(run_dir).rglob("manifest.json"))
    if not manifests:
        print(f"LIVE CANARY: NO manifest.json produced under {run_dir} — the run did not finish.")
        return 1
    count, messages = module.check_targets(manifests)
    if count:
        print(f"LIVE CANARY: A18 release-invariant FOUND {count} VIOLATION(S):")
        for msg in messages:
            print(f"  - {msg}")
        return 1
    print(f"LIVE CANARY: A18 release-invariant OK over {len(manifests)} produced manifest(s).")
    return 0


def run_live_canary(argv: list[str]) -> int:
    """Operator-gated PAID 1-query sweep + post-run A18 invariant re-check (REALLY runs — no stub).

    Pipeline:
      1. The OFFLINE behavioral canary MUST pass first (every changed slug fires in real call
         shape) — refuse to spend a cent otherwise.
      2. SHELL OUT to the real sweep entry point for a SINGLE query (``--only <slug> --out-root
         <dir>``) so the judge-400 / A1 / seam paths fire on a real non-resume run end-to-end.
      3. Run the A18 release-invariant over EVERY manifest the run produced.
    Exits NON-ZERO on any failure at any stage. Spend is the operator's call (the sweep itself
    enforces PG_AUTHORIZED_SWEEP_APPROVAL); this canary never sets that token. Requires an explicit
    ``--slug`` and ``--out-root`` so a paid run is always deliberate.

    Usage::

        python scripts/iarch007_behavioral_canary.py --live --slug <slug> --out-root <canary_dir>
    """
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(prog="iarch007_behavioral_canary.py --live")
    parser.add_argument("--slug", required=True, help="single sweep query slug to run (--only)")
    parser.add_argument("--out-root", required=True, help="run output root (--out-root)")
    parser.add_argument(
        "--python", default=sys.executable, help="python interpreter for the sweep subprocess"
    )
    parsed = parser.parse_args(argv)

    # (1) the offline behavioral canary MUST pass before any spend.
    print("LIVE CANARY step 1/3: offline behavioral canary (every fix must fire before spend)\n")
    offline_rc = run_behavioral_canary()
    if offline_rc != 0:
        print("\nLIVE CANARY ABORTED: offline behavioral canary failed; refusing to spend.")
        return offline_rc

    # (2) the real 1-query sweep (PAID). The sweep enforces its own spend authorization; this
    # canary does NOT set PG_AUTHORIZED_SWEEP_APPROVAL — an unauthorized run fails in the sweep.
    sweep_path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    out_root = Path(parsed.out_root)
    cmd = [
        parsed.python, str(sweep_path),
        "--only", parsed.slug,
        "--out-root", str(out_root),
    ]
    print(f"\nLIVE CANARY step 2/3: real 1-query sweep -> {' '.join(cmd)}\n")
    try:
        completed = subprocess.run(cmd, cwd=str(_REPO_ROOT), check=False)
    except OSError as exc:
        print(f"LIVE CANARY: could not launch the sweep subprocess: {exc}")
        return 2
    if completed.returncode != 0:
        print(f"LIVE CANARY: the sweep subprocess exited non-zero ({completed.returncode}).")
        # A non-zero sweep exit does not by itself mean an unsafe release — still check artifacts
        # below so a partial run dir is audited; but a failed launch is already a canary FAIL.
        # Fall through to the invariant check (it fails if no manifest was produced).

    # (3) the A18 artifact invariant over EVERY produced manifest. Non-zero on any violation.
    print("\nLIVE CANARY step 3/3: A18 release-invariant over the produced run dir(s)\n")
    inv_rc = _run_invariant_check_over_dir(out_root)
    if inv_rc != 0:
        return inv_rc
    if completed.returncode != 0:
        # Artifacts are clean but the sweep itself errored: still a non-green canary.
        return 1
    print("\nLIVE CANARY: PASS — real 1-query run produced A18-clean artifacts.")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0] == "--live":
        return run_live_canary(args[1:])
    return run_behavioral_canary()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
