"""M-LIVE-1: V19 single-query end-to-end smoke.

Acceptance bar (per docs/full_online_plan.md M-LIVE-1):
  - One real query through the integrated pipeline
  - All Phase E substrates fire (verified by run-log + sinks)
  - Manifest + audit bundle + Inspector views all render
  - Codex review: artifact completeness, every substrate's
    invocation count > 0

Substrate sinks:
  - M-INT-0a (decision telemetry):   /api/inspector/templates/route POST →
                                     DecisionRecordStore SQLite row
  - M-INT-0b (pin capture):          run_dir / model_pin.json + stdout
                                     `[M-INT-0b]` marker
  - M-INT-1 (parallel fetch):        manifest.json
                                     `retrieval.api_calls.parallel_fetch_*`
  - M-INT-2 (cache warming):         stdout `[M-INT-2] cache_warming`
  - M-INT-3 (freshness detector):    stdout
                                     `[M-INT-3] sweep_freshness_summary`
  - M-INT-4 (scope LLM):             run_log.txt `[M-INT-4]   scope_llm:`
  - M-INT-5 (domain router):         run_log.txt `[M-INT-5]   domain_router:`
  - M-INT-6 (auto induction):        run_log.txt `[M-INT-6]   inductor:`
                                     + run_dir / operator_review_queue.jsonl
  - M-INT-7 (billing quota):         stdout `[M-INT-7] billing_quota:`
  - M-INT-8/9/10/11 (endpoints):     TestClient request returns 2xx
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


M_LIVE_1_ENV: dict[str, str] = {
    "PG_RECORD_DECISIONS":             "1",
    "PG_CAPTURE_PIN":                  "1",
    "PG_USE_PARALLEL_FETCH":           "1",
    "PG_USE_CACHE_WARMING":            "1",
    "PG_USE_FRESHNESS_DETECTOR":       "1",
    "PG_USE_LLM_SCOPE":                "1",
    "PG_USE_DOMAIN_ROUTER":            "1",
    "PG_USE_AUTO_INDUCTION":           "1",
    "PG_USE_BILLING_QUOTA":            "1",
    "PG_USE_SLIDE_DECK_ENDPOINT":      "1",
    "PG_USE_CONTRACT_DRAFT_ENDPOINT":  "1",
    "PG_USE_DRIVE_CONNECTOR_ENDPOINT": "1",
    "PG_USE_SUPPORT_TICKET_ENDPOINT":  "1",
    "PG_MAX_COST_PER_RUN":             "2.00",
    "PG_SWEEP_MAX_SERPER":             "10",
    "PG_SWEEP_MAX_S2":                 "10",
    "PG_SWEEP_FETCH_CAP":              "30",
    "PG_LIVE_MAX_EV_TO_GEN":           "30",
    "PG_V30_ENABLED":                  "1",
    "PG_V30_PHASE2_ENABLED":           "1",
    "PG_UNPAYWALL_ENABLED":            "1",
    "PG_CRAWL4AI_ENABLED":             "0",
    "PG_TRAFILATURA_ENABLED":          "1",
    "PG_SCIHUB_ENABLED":               "0",
    # v2 (post-empirical-R1):
    # endpoint smokes need the trusted-test-header gate (auth
    # middleware ignores X-Polaris-Caller without this)
    "PG_AUTH_TRUSTED_TEST_HEADER":     "1",
    # M-INT-7 billing quota needs an org_id to charge against
    "PG_BILLING_ORG_ID":               "org_default",
}


M_LIVE_1_INJECTED_CANONICAL_URLS: list[str] = [
    "https://www.nejm.org/doi/10.1056/NEJMoa2107519",
    "https://www.nejm.org/doi/10.1056/NEJMoa2206038",
    "https://www.thelancet.com/journals/lancet/article/"
    "PIIS0140-6736(23)01200-X/fulltext",
]


def _seed_billing_plan_for_smoke() -> None:
    """v3 fix: M-INT-7 fires correctly but consume() raises
    QuotaExceededError when org_default has no assigned plan.
    The sweep then exits rc=2 BEFORE the query loop runs, which
    blocks M-INT-0b/1/4/5/6 (per-query substrates) from firing.

    Seed org_default with a generous tier1 plan so consume()
    succeeds and the sweep proceeds. This is smoke-only setup;
    production billing is provisioned via M-NEW assign_plan API.
    """
    try:
        from src.polaris_graph.audit_ir.billing_quota_store import (
            BillingQuotaStore,
            PlanTier,
            QuotaEventKind,
        )
    except Exception as exc:
        print(f"[M-LIVE-1 patch] WARN: billing import failed: {exc}")
        return
    db_path = Path(os.environ.get(
        "PG_BILLING_QUOTA_DB_PATH",
        str(REPO_ROOT / "state" / "billing_quota.sqlite"),
    ))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        store = BillingQuotaStore(db_path)
        store.assign_plan(
            org_id="org_default",
            tier=PlanTier.PRODUCTION,
            quotas_override={
                QuotaEventKind.AUDIT_RUN_ENQUEUED: 100,
            },
        )
        print(
            "[M-LIVE-1 patch] seeded billing plan: org=org_default "
            "tier=production audit_run_quota=100"
        )
    except Exception as exc:
        print(f"[M-LIVE-1 patch] WARN: billing seed failed: {exc}")


def _patch_query_with_canonical_urls() -> None:
    """v2 fix: inject canonical_urls into the smoke query so
    M-INT-2 (cache_warming) and M-INT-3 (freshness) fire
    end-to-end. The substrates correctly gate on
    `if canonical_urls:` — without injection, the v1 smoke
    showed 0 invocations of either substrate (5/12 fired).

    This is a smoke-script-only patch; it does NOT modify the
    production query catalog. Done before sweep_main() is
    invoked so the patched value is what the sweep loop sees.
    """
    import scripts.run_honest_sweep_r3 as sweep_mod
    if not hasattr(sweep_mod, "SWEEP_QUERIES"):
        return
    for q in sweep_mod.SWEEP_QUERIES:
        if q.get("slug") == "clinical_tirzepatide_t2dm":
            q["canonical_urls"] = list(M_LIVE_1_INJECTED_CANONICAL_URLS)
            print(
                f"[M-LIVE-1 patch] injected "
                f"{len(M_LIVE_1_INJECTED_CANONICAL_URLS)} canonical_urls "
                f"into query 'clinical_tirzepatide_t2dm' for "
                f"M-INT-2/3 verification"
            )
            return


SWEEP_LOG_PATTERNS: dict[str, list[str]] = {
    "M-INT-0b": [r"\[M-INT-0b\]"],
    "M-INT-2":  [r"\[M-INT-2\] cache_warming"],
    "M-INT-3":  [r"\[M-INT-3\] sweep_freshness_summary"],
    "M-INT-4":  [r"\[M-INT-4\]\s+scope_llm:"],
    "M-INT-5":  [r"\[M-INT-5\]\s+domain_router:"],
    "M-INT-6":  [r"\[M-INT-6\]\s+inductor:"],
    "M-INT-7":  [r"\[M-INT-7\] billing_quota:"],
}


def _apply_env() -> None:
    for k, v in M_LIVE_1_ENV.items():
        cur = os.environ.get(k)
        if cur is None or cur == "":
            os.environ[k] = v
            print(f"[M-LIVE-1 env] {k} = {v}")
        else:
            print(f"[M-LIVE-1 env] {k} = {cur}  (already set)")


def _verify_log_substrates(out_root: Path, captured: str) -> dict:
    log_text = captured
    for lf in out_root.rglob("run_log.txt"):
        try:
            log_text += "\n" + lf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    out: dict = {}
    for substrate, patterns in SWEEP_LOG_PATTERNS.items():
        count = sum(len(re.findall(p, log_text)) for p in patterns)
        out[substrate] = {"fired": count > 0, "invocation_count": count}
    return out


def _verify_m_int_1(out_root: Path) -> dict:
    files: list[str] = []
    success_total = 0
    for mf in out_root.rglob("manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            api_calls = (data.get("retrieval") or {}).get("api_calls", {}) or {}
            if "parallel_fetch_success_count" in api_calls:
                files.append(str(mf))
                success_total += int(api_calls.get(
                    "parallel_fetch_success_count", 0,
                ))
        except Exception:
            pass
    return {
        "fired": bool(files),
        "invocation_count": success_total,
        "sink_files": files,
    }


def _verify_m_int_0b(out_root: Path, sweep_rc: int) -> dict:
    """v2 R1 P0 #2 fix: require sweep_rc == 0 AND model_pin.json
    file. v1 only checked file existence — would inherit a stale
    model_pin.json from a prior run if sweep aborted.

    Note: the production code path emits no success [M-INT-0b]
    stdout marker; only WARN markers on failure
    (run_honest_sweep_r3.py:1000). Acceptance is therefore
    'file written + sweep succeeded' rather than 'marker emitted'.
    """
    files = [str(p) for p in out_root.rglob("model_pin.json")]
    fired = sweep_rc == 0 and bool(files)
    return {
        "fired": fired,
        "invocation_count": len(files) if fired else 0,
        "sink_files": files,
        "sweep_rc": sweep_rc,
        "rationale": (
            "sweep_rc==0 + model_pin.json present"
            if fired
            else f"NOT FIRED: sweep_rc={sweep_rc}, files={len(files)}"
        ),
    }


def _verify_m_int_6(out_root: Path, captured_stdout: str) -> dict:
    """v2 R1 P0 #3 fix: queue file is conditional on abstain
    decision. Accept-decision runs do NOT write a queue row but
    DO emit the [M-INT-6] inductor: marker. v1 verifier passed
    via OR fallback; v2 requires the marker explicitly and
    treats the queue file as informational, not load-bearing.
    """
    queue_files: list[str] = []
    queue_rows = 0
    for q in out_root.rglob("operator_review_queue.jsonl"):
        queue_files.append(str(q))
        try:
            queue_rows += sum(1 for _ in q.read_text(
                encoding="utf-8", errors="replace",
            ).splitlines() if _.strip())
        except Exception:
            pass

    log_text = captured_stdout
    for lf in out_root.rglob("run_log.txt"):
        try:
            log_text += "\n" + lf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    marker_count = len(re.findall(r"\[M-INT-6\]\s+inductor:", log_text))
    accept_count = len(re.findall(
        r"\[M-INT-6\]\s+inductor:\s+decision=accept", log_text,
    ))
    abstain_count = len(re.findall(
        r"\[M-INT-6\]\s+inductor:\s+decision=abstain", log_text,
    ))

    fired = marker_count > 0
    return {
        "fired": fired,
        "invocation_count": marker_count,
        "marker_count": marker_count,
        "accept_count": accept_count,
        "abstain_count": abstain_count,
        "queue_files": queue_files,
        "queue_rows": queue_rows,
        "rationale": (
            f"marker fired {marker_count}x; queue rows={queue_rows} "
            f"(queue write only on abstain; accept={accept_count} "
            f"abstain={abstain_count})"
        ),
    }


def _smoke_endpoints() -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.polaris_graph.audit_ir.inspector_router import (
        _get_decision_store,
        router,
    )

    app = FastAPI()
    app.include_router(router)
    headers = {"X-Polaris-Caller": "org_default:usr_test:owner"}
    client = TestClient(app, headers=headers)

    results: dict = {}

    rows_before = 0
    try:
        store_before = _get_decision_store()
        rows_before = len(store_before.list_for_workspace(
            workspace_id="org_default",
        ) or [])
    except Exception as exc:
        results["_decision_store_pre_count_err"] = str(exc)

    r0a = client.post(
        "/api/inspector/templates/route",
        json={"question": (
            "M-LIVE-1 smoke: efficacy of tirzepatide for "
            "type 2 diabetes mellitus"
        )},
    )
    results["M-INT-0a"] = {
        "endpoint": "POST /api/inspector/templates/route",
        "status_code": r0a.status_code,
        "response_keys": (
            list(r0a.json().keys()) if r0a.status_code == 200 else []
        ),
    }
    rows_after = 0
    try:
        store_after = _get_decision_store()
        rows_after = len(store_after.list_for_workspace(
            workspace_id="org_default",
        ) or [])
    except Exception as exc:
        results["M-INT-0a"]["row_count_err"] = str(exc)
    results["M-INT-0a"]["decision_rows_before"] = rows_before
    results["M-INT-0a"]["decision_rows_after"] = rows_after
    results["M-INT-0a"]["fired"] = (
        r0a.status_code == 200 and rows_after > rows_before
    )
    results["M-INT-0a"]["invocation_count"] = max(
        0, rows_after - rows_before,
    )

    try:
        from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_SLUG
    except Exception:
        CANONICAL_DEMO_SLUG = "v30_phase2_clinical_tirzepatide_t2dm"

    # v3 R2 P0 #1+#2 fix: M-INT-8 (slide-deck endpoint) verifies
    # the FastAPI substrate is wired against the canonical demo
    # run from the static registry. By design, the slide-deck
    # endpoint reads from `find_run_by_slug()` allowlist
    # (outputs/full_scale_v30_phase2_run14/...), NOT from the
    # fresh smoke run's out_root — the substrate is endpoint +
    # auth + flag wiring, decoupled from sweep state.
    #
    # v2 accepted 200 OR 404; that allowed all_phase_e_fired=true
    # even when the slide-deck route is missing/disabled. v3
    # requires 200 strictly. The substrate's behavior on missing
    # slug is exercised by the test suite, not the smoke.
    #
    # Body sanity check: confirm the response body actually
    # references the canonical demo slug, ruling out stale
    # boilerplate.
    r8 = client.get(
        f"/api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck",
    )
    body8 = r8.json() if r8.status_code == 200 else {}
    r8_body_references_slug = (
        isinstance(body8, dict)
        and any(
            CANONICAL_DEMO_SLUG in str(v) for v in body8.values()
        )
    )
    results["M-INT-8"] = {
        "endpoint": (
            f"GET /api/inspector/runs/{CANONICAL_DEMO_SLUG}/slide-deck"
        ),
        "status_code": r8.status_code,
        "fired": r8.status_code == 200 and r8_body_references_slug,
        "invocation_count": 1,
        "body_references_canonical_slug": r8_body_references_slug,
        "note": (
            "Substrate is the FastAPI slide-deck endpoint, which "
            "reads from the static registry (find_run_by_slug). "
            "Verification is endpoint+auth+flag wiring against the "
            "canonical demo, not the fresh smoke run. Fresh-run "
            "coupling would require registry-bypass plumbing "
            "outside M-LIVE-1 scope."
        ),
    }

    r9 = client.post(
        "/api/inspector/contract-drafts",
        json={
            "audit_run_id": "RUN_M_LIVE_1_SMOKE",
            "kind": "dpa",
            "title": "M-LIVE-1 smoke DPA",
            "counterparty_name": "Smoke Counterparty Inc.",
        },
    )
    results["M-INT-9"] = {
        "endpoint": "POST /api/inspector/contract-drafts",
        "status_code": r9.status_code,
        "fired": r9.status_code == 201,
        "invocation_count": 1,
    }

    r10 = client.post(
        "/api/inspector/private-corpus-sources",
        json={
            "workspace_id": "ws_m_live_1_smoke",
            "name": "M-LIVE-1 smoke Drive folder",
            "external_uri": "1abcDriveFolderId123456_AAA",
            "credential_ref": "vault://secrets/m-live-1-smoke",
        },
    )
    results["M-INT-10"] = {
        "endpoint": "POST /api/inspector/private-corpus-sources",
        "status_code": r10.status_code,
        "fired": r10.status_code == 201,
        "invocation_count": 1,
    }

    r11 = client.post(
        "/api/inspector/support-tickets",
        json={
            "title": "M-LIVE-1 smoke ticket",
            "description": "Smoke test: end-to-end Phase E coverage.",
            "category": "audit",
            "priority": "low",
        },
    )
    results["M-INT-11"] = {
        "endpoint": "POST /api/inspector/support-tickets",
        "status_code": r11.status_code,
        "fired": r11.status_code == 201,
        "invocation_count": 1,
    }

    return results


def main() -> int:
    _apply_env()

    # v2 R1 P0 #1 fix: run-scoped artifact path. v1 used a
    # reusable `outputs/m_live_1_smoke/` tree, so a failed sweep
    # could inherit stale model_pin.json / queue files from a
    # prior run and still pass verification. v2 creates a
    # timestamped subdir per run; verifiers only scan that dir.
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_base = REPO_ROOT / "outputs" / "m_live_1_smoke"
    out_root = out_base / f"run_{timestamp}"
    out_root.mkdir(parents=True, exist_ok=True)

    if "--only" not in sys.argv:
        sys.argv.extend(["--only", "clinical_tirzepatide_t2dm"])
    if "--out-root" not in sys.argv:
        sys.argv.extend(["--out-root", str(out_root)])

    print("=" * 72)
    print("M-LIVE-1 single-query end-to-end smoke (v3 — LOCKED Codex R3 GREEN)")
    print("=" * 72)
    print(f"out_root: {out_root}")
    print()

    captured = io.StringIO()
    rc = 1
    sweep_dt = 0.0
    try:
        from scripts.run_honest_sweep_r3 import main as sweep_main
        _seed_billing_plan_for_smoke()
        _patch_query_with_canonical_urls()
        t0 = time.time()
        with redirect_stdout(_TeeStream(sys.stdout, captured)):
            rc = sweep_main()
        sweep_dt = time.time() - t0
    except SystemExit as se:
        rc = int(se.code) if se.code is not None else 0
        sweep_dt = time.time() - t0
    except Exception as exc:
        print(f"[M-LIVE-1] sweep raised: {exc!r}")

    captured_text = captured.getvalue()

    print()
    print("=" * 72)
    print(f"sweep done: rc={rc} elapsed={sweep_dt:.1f}s")
    print("=" * 72)

    log_subst = _verify_log_substrates(out_root, captured_text)
    log_subst["M-INT-0b"] = _verify_m_int_0b(out_root, sweep_rc=rc)
    log_subst["M-INT-6"] = _verify_m_int_6(out_root, captured_text)
    parallel = _verify_m_int_1(out_root)

    print()
    print("=" * 72)
    print("endpoint smoke (M-INT-0a / 8 / 9 / 10 / 11)")
    print("=" * 72)
    endpoint = _smoke_endpoints()

    all_subst = {**log_subst, "M-INT-1": parallel, **endpoint}
    fired = sorted(s for s, v in all_subst.items() if v.get("fired"))
    not_fired = sorted(s for s, v in all_subst.items() if not v.get("fired"))

    # Phase E has 13 distinct substrates (M-INT-0a + 0b + 1..11).
    # The "12 substrates" framing in FINAL_PLAN groups 0a+0b into
    # "M-INT-0" but the real count is 13. v2 brief is updated to
    # match.
    #
    # v2 R1 P0 #1 fix: GREEN requires sweep_rc == 0 AND
    # not_fired_substrates == []. v1 only checked the latter, so
    # an aborted sweep could still report GREEN if stale
    # artifacts inherited from a prior run.
    all_phase_e_fired = (rc == 0) and (len(not_fired) == 0)
    manifest = {
        "milestone": "M-LIVE-1",
        "version": "v3",
        "elapsed_sweep_seconds": round(sweep_dt, 1),
        "sweep_rc": rc,
        "out_root": str(out_root),
        "expected_substrates": 13,
        "fired_substrates": fired,
        "not_fired_substrates": not_fired,
        "fired_count": len(fired),
        "all_phase_e_fired": all_phase_e_fired,
        "details": all_subst,
    }
    smoke_manifest_path = out_root / "smoke_manifest.json"
    smoke_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print(
        f"M-LIVE-1 smoke result: {len(fired)}/13 substrates fired, "
        f"sweep_rc={rc} "
        f"({'GREEN' if all_phase_e_fired else 'INCOMPLETE'})"
    )
    print(f"  fired:     {fired}")
    print(f"  not_fired: {not_fired}")
    print(f"manifest:    {smoke_manifest_path}")
    print("=" * 72)

    return 0 if all_phase_e_fired else 1


class _TeeStream:
    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary
    def write(self, s):
        try:
            self._primary.write(s)
        except Exception:
            pass
        try:
            self._secondary.write(s)
        except Exception:
            pass
        return len(s) if isinstance(s, str) else 0
    def flush(self):
        for s in (self._primary, self._secondary):
            try:
                s.flush()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
