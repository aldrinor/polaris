"""I-cd-016a (under #626) — live-run journey harness.

OPERATOR-RUN ONLY. NOT for CI. Costs real OpenRouter spend per invocation.

Flow:
  1. GPG preflight via GET /transparency (stub check; real preflight at I-cd-016d).
  2. POST /auth/login (unless POLARIS_SMOKE_AUTH_DISABLED=1) → store JWT.
  3. POST /runs → get run_id.
  4. SSE /stream/{run_id} → wait for run_complete (capped at POLARIS_SMOKE_TIMEOUT_S).
  5. Poll GET /runs/{run_id} until lifecycle_status=='completed' AND pipeline_status=='success'.
  6. GET /runs/{run_id}/bundle.tar.gz → extract.
  7. check_bundle_conformance(extracted_dir) (I-cd-012 v1.0 schema).
  8. Parse verified_report.json → assert pipeline_verdict=='success' AND >=1 verifier_pass=true sentence.
  9. Print RESULT: PASS|FAIL with measured wallclock duration_ms.

KNOWN LIMITATIONS (do NOT remove without addressing the underlying issues):
  - Lock-verification assertions (generator_model=='deepseek/deepseek-v4-pro' etc.) are
    DEFERRED until I-cd-016c (#675) fixes the audit bridge model fallback bug.
  - GPG signer preflight is a STUB (GET /transparency just echoes the env);
    real preflight at I-cd-016d (#676). Operator confirms via scripts/v6_preflight.py manually.

EXIT CODES (11 structured codes: PASS + 10 domain failures + 1 uncaught):
  0   PASS
  10  MISSING_SIGNER     /transparency.signing_key_fingerprint empty
  11  AUTH_FAILED        /auth/login non-200 or no token (also missing creds env)
  12  RUN_START_FAILED   POST /runs non-200
  13  TIMEOUT            SSE wallclock cap reached / degraded status / SSE HTTPError; cancel attempted
  14  RUN_CANCELED       lifecycle_status=='cancelled' after wait
  15  POLL_TIMEOUT       lifecycle not 'completed'+pipeline not 'success' after 30x2s post run_complete
  16  BUNDLE_FETCH_FAILED  GET /bundle.tar.gz non-200 or unsafe path in tar
  17  CONFORMANCE_FAILED   check_bundle_conformance.valid==False or verified_report.json unparseable
  18  VERDICT_NOT_SUCCESS  verified_report.pipeline_verdict != 'success'
  19  NO_VERIFIED_SECTIONS no sections with >=1 verifier_pass=true sentence
  99  UNEXPECTED_ERROR    uncaught exception (KeyboardInterrupt etc.)

Per Codex brief iter-3 APPROVE 2026-05-20 (Codex caveats honored: PR scope tight;
GPG + OpenRouter spend operator-only; SSE via httpx; race-handling via lifecycle poll).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import httpx

# Add src/ to path so polaris_graph imports resolve.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from polaris_graph.audit_bundle.conformance import (  # noqa: E402
    check_bundle_conformance,
)


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None or val == "":
        # Codex diff iter-2 P2: missing smoke creds is auth-preflight, not
        # unexpected error. Use exit 11 (AUTH_FAILED) to match the structured
        # exit-code scheme documented in the module docstring.
        print(f"FAIL: env var {name} is required", file=sys.stderr)
        print("RESULT: FAIL")
        sys.exit(11)
    return val


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="POLARIS live-run smoke harness (I-cd-016a)")
    ap.add_argument("--question", required=True, help="Research question text")
    ap.add_argument("--template", required=True, help="Template ID (clinical/policy/tech/...)")
    args = ap.parse_args(argv)

    backend = os.environ.get("POLARIS_V6_BACKEND_URL", "http://localhost:8000").rstrip("/")
    auth_disabled = os.environ.get("POLARIS_SMOKE_AUTH_DISABLED", "") == "1"
    timeout_s = float(os.environ.get("POLARIS_SMOKE_TIMEOUT_S", "600"))

    wall_start = time.monotonic()
    client = httpx.Client(timeout=30.0)

    # --- 1. GPG signer preflight (STUB; real preflight at I-cd-016d #676) ---
    try:
        r = client.get(f"{backend}/transparency")
        r.raise_for_status()
        signing_fp = (r.json() or {}).get("signing_key_fingerprint", "")
    except (httpx.HTTPError, ValueError) as exc:
        print(f"FAIL: /transparency preflight error: {exc}", file=sys.stderr)
        print("RESULT: FAIL")
        return 10
    if not signing_fp:
        print("FAIL: /transparency.signing_key_fingerprint is empty; configure POLARIS_GPG_KEY_ID + signer at app startup", file=sys.stderr)
        print("RESULT: FAIL")
        return 10

    # --- 2. Auth: POST /auth/login → bearer token ---
    headers: dict[str, str] = {}
    if not auth_disabled:
        username = _env("POLARIS_SMOKE_USERNAME")
        password = _env("POLARIS_SMOKE_PASSWORD")
        try:
            r = client.post(
                f"{backend}/auth/login",
                json={"username": username, "password": password},
            )
            r.raise_for_status()
            token = (r.json() or {}).get("access_token", "")
        except (httpx.HTTPError, ValueError) as exc:
            print(f"FAIL: /auth/login error: {exc}", file=sys.stderr)
            print("RESULT: FAIL")
            return 11
        if not token:
            print("FAIL: /auth/login returned no access_token", file=sys.stderr)
            print("RESULT: FAIL")
            return 11
        headers["Authorization"] = f"Bearer {token}"

    # --- 3. POST /runs → run_id ---
    try:
        r = client.post(
            f"{backend}/runs",
            headers=headers,
            json={"question": args.question, "template": args.template, "document_ids": []},
        )
        r.raise_for_status()
        run_id = (r.json() or {}).get("run_id", "")
    except (httpx.HTTPError, ValueError) as exc:
        print(f"FAIL: POST /runs error: {exc}", file=sys.stderr)
        print("RESULT: FAIL")
        return 12
    if not run_id:
        print("FAIL: POST /runs returned no run_id", file=sys.stderr)
        print("RESULT: FAIL")
        return 12

    # --- 4. SSE /stream/{run_id} → wait for run_complete (wallclock-capped) ---
    # Codex diff iter-1 P1: SSE can emit DEGRADED terminal statuses
    # (`stream_unavailable`, `stream_lost`) per run_events.py:249,268.
    # Treat those as failure, NOT pass.
    DEGRADED_STATUSES = {"stream_unavailable", "stream_lost"}
    sse_deadline = time.monotonic() + timeout_s
    run_complete_seen = False
    run_complete_status = ""
    current_event_type = ""
    try:
        with client.stream("GET", f"{backend}/stream/{run_id}", headers=headers) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if time.monotonic() > sse_deadline:
                    break
                line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace")
                if not line:
                    current_event_type = ""
                    continue
                if line.startswith("event:"):
                    current_event_type = line.split(":", 1)[1].strip()
                    continue
                if line.startswith("data:"):
                    payload_str = line.split(":", 1)[1].strip()
                    try:
                        payload = json.loads(payload_str)
                    except (ValueError, json.JSONDecodeError):
                        payload = {}
                    is_terminal = (
                        current_event_type in ("run_complete", "run.completed")
                        or payload.get("event") == "run_complete"
                        or payload.get("event_type") == "run.completed"
                    )
                    if is_terminal:
                        run_complete_status = (payload.get("status") or "").strip()
                        run_complete_seen = True
                        break
    except httpx.HTTPError as exc:
        # Codex diff iter-1 P2: cancel before exit on SSE HTTP error too.
        try:
            client.post(f"{backend}/runs/{run_id}/cancel", headers=headers, timeout=10.0)
        except httpx.HTTPError:
            pass
        print(f"FAIL: SSE /stream error: {exc}; sent /runs/{run_id}/cancel", file=sys.stderr)
        print("RESULT: FAIL")
        return 13

    if not run_complete_seen:
        # Wallclock cap fired; cancel the in-flight run to prevent spend.
        try:
            client.post(f"{backend}/runs/{run_id}/cancel", headers=headers, timeout=10.0)
        except httpx.HTTPError:
            pass
        print(f"FAIL: SSE wallclock cap ({timeout_s:.0f}s) reached; sent /runs/{run_id}/cancel", file=sys.stderr)
        print("RESULT: FAIL")
        return 13

    # Codex diff iter-1 P1: degraded SSE terminal statuses are NOT pass.
    if run_complete_status in DEGRADED_STATUSES:
        try:
            client.post(f"{backend}/runs/{run_id}/cancel", headers=headers, timeout=10.0)
        except httpx.HTTPError:
            pass
        print(f"FAIL: SSE run_complete with degraded status={run_complete_status!r}; sent /runs/{run_id}/cancel", file=sys.stderr)
        print("RESULT: FAIL")
        return 13

    # --- 5. Poll /runs/{run_id} until lifecycle_status=='completed' AND pipeline_status=='success' ---
    # Per Codex iter-3 P2: SSE run_complete fires BEFORE the actor sqlite-UPDATE.
    poll_ok = False
    for _ in range(30):
        try:
            r = client.get(f"{backend}/runs/{run_id}", headers=headers)
            r.raise_for_status()
            body = r.json() or {}
        except (httpx.HTTPError, ValueError):
            time.sleep(2.0)
            continue
        lifecycle = body.get("lifecycle_status") or body.get("status", "")
        pipeline = body.get("pipeline_status", "")
        if lifecycle == "cancelled":
            print(f"FAIL: run {run_id} cancelled", file=sys.stderr)
            print("RESULT: FAIL")
            return 14
        if lifecycle == "completed" and pipeline == "success":
            poll_ok = True
            break
        time.sleep(2.0)
    if not poll_ok:
        print(f"FAIL: /runs/{run_id} did not reach lifecycle=completed + pipeline=success within 60s", file=sys.stderr)
        print("RESULT: FAIL")
        return 15

    # --- 6-7. GET /bundle.tar.gz → extract → check_bundle_conformance ---
    try:
        r = client.get(f"{backend}/runs/{run_id}/bundle.tar.gz", headers=headers, timeout=120.0)
        r.raise_for_status()
        tar_bytes = r.content
    except httpx.HTTPError as exc:
        print(f"FAIL: GET /bundle.tar.gz error: {exc}", file=sys.stderr)
        print("RESULT: FAIL")
        return 16

    with tempfile.TemporaryDirectory(prefix="polaris_smoke_") as tmpdir:
        extracted = Path(tmpdir) / "bundle"
        extracted.mkdir(parents=True, exist_ok=True)
        # Codex diff iter-1 P2: reject absolute / `..` / backslash paths
        # AFTER stripping exactly one top-level directory. Path-traversal
        # hardening; only regular files and directories accepted.
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not (member.isfile() or member.isdir()):
                    print(f"FAIL: bundle contains non-file/dir member {member.name!r}", file=sys.stderr)
                    print("RESULT: FAIL")
                    return 16
                # Codex diff iter-2 P2: detect absolute / UNC / drive-qualified
                # BEFORE lstrip (so we reject them outright rather than normalize).
                raw = member.name
                if (
                    raw.startswith("/")
                    or "\\" in raw
                    or (len(raw) >= 2 and raw[1] == ":")
                    or raw.startswith("//")
                ):
                    print(f"FAIL: bundle contains unsafe path {member.name!r}", file=sys.stderr)
                    print("RESULT: FAIL")
                    return 16
                rel = raw
                parts = rel.split("/", 1)
                if len(parts) == 2 and parts[1]:
                    rel = parts[1]
                else:
                    rel = parts[0]
                if not rel or rel.startswith("/") or ".." in rel.split("/"):
                    print(f"FAIL: bundle contains unsafe path after strip {rel!r}", file=sys.stderr)
                    print("RESULT: FAIL")
                    return 16
                member.name = rel
                tar.extract(member, path=extracted)

        result = check_bundle_conformance(extracted)
        if not result.valid:
            print(f"FAIL: bundle conformance ({len(result.errors)} errors):", file=sys.stderr)
            for e in result.errors[:5]:
                print(f"  {e.code}: {e.message[:120]}", file=sys.stderr)
            print("RESULT: FAIL")
            return 17

        # --- 8. Parse verified_report.json + assert success + verified content ---
        vr_path = extracted / "verified_report.json"
        try:
            vr = json.loads(vr_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"FAIL: parse verified_report.json: {exc}", file=sys.stderr)
            print("RESULT: FAIL")
            return 17

    verdict = vr.get("pipeline_verdict", "")
    if verdict != "success":
        print(f"FAIL: verified_report.pipeline_verdict={verdict!r} (expected 'success')", file=sys.stderr)
        print("RESULT: FAIL")
        return 18

    sections = vr.get("sections", [])
    verified_count = 0
    for section in sections:
        verified_count += sum(1 for s in section.get("verified_sentences", []) if s.get("verifier_pass"))
    if verified_count == 0:
        print(f"FAIL: no verified sentences across {len(sections)} sections", file=sys.stderr)
        print("RESULT: FAIL")
        return 19

    # --- 9. PASS summary ---
    duration_ms = int((time.monotonic() - wall_start) * 1000)
    cost_usd = vr.get("cost_usd", "?")
    print(
        f"PASS: run_id={run_id} sections={len(sections)} verified_sentences={verified_count} "
        f"cost_usd={cost_usd} duration_ms={duration_ms}",
    )
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(99)
    except Exception as exc:  # noqa: BLE001 — uncaught is structured exit 99
        print(f"FAIL: unexpected error: {exc}", file=sys.stderr)
        print("RESULT: FAIL")
        sys.exit(99)
