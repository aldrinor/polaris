"""I-carney-003 — public transparency endpoint.

Returns deploy provenance (region, signing key, sovereignty filter coverage,
evaluator models, egress allowlist) so reviewers and Carney's office can
audit that the deploy is sovereign + verifiable.

Three routes:
- GET /transparency         JSON deploy descriptor
- GET /transparency/pubkey.asc  text/plain armored GPG public key
- GET /transparency/policy  JSON full sovereignty + egress policy
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from polaris_v6 import __version__

router = APIRouter(prefix="/transparency", tags=["transparency"])

POLICY_VERSION = "v1.0"
DEFAULT_PUBKEY_PATH = "/app/gpg/polaris_demo_pubkey.asc"
# Codex diff iter-1 P1-004: /etc/polaris/* only exists on the EC2 host (cloud-
# init copies it there). The api container has /app/config/ baked in by
# Dockerfile.v6 via `COPY config/ config/`. Default to the in-container path
# so /transparency returns the real 17-domain allowlist without operator
# bind-mount; the host /etc/polaris path is used by egress_lockdown.sh only.
DEFAULT_EGRESS_ALLOWLIST = "/app/config/egress_allowlist.txt"


class SovereigntyPolicy(BaseModel):
    """Sovereignty filter description — cited tiers, cascade behavior."""

    cleared_tiers: list[str]
    cascade_rule: str
    tier_definitions: dict[str, str]


class TransparencyResponse(BaseModel):
    """Public deploy descriptor."""

    provider: str
    region: str
    git_commit: str
    polaris_version: str
    deploy_timestamp: str
    signing_key_id: str | None
    signing_key_fingerprint: str | None
    sovereignty_filter: SovereigntyPolicy
    evaluator_models: dict[str, str]
    egress_allowlist: list[str]
    build_time_hosts_pruned: bool
    dependencies: dict[str, list[str]]


def _load_egress_allowlist() -> list[str]:
    """Load the in-container egress allowlist or fall back to 'unrestricted'.

    Default path is /app/config/egress_allowlist.txt (baked into Dockerfile.v6
    via `COPY config/ config/`); operator override via POLARIS_EGRESS_ALLOWLIST.
    """
    path = Path(os.environ.get("POLARIS_EGRESS_ALLOWLIST", DEFAULT_EGRESS_ALLOWLIST))
    if not path.exists():
        return ["unrestricted (no lockdown applied)"]
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _load_dependencies() -> dict[str, list[str]]:
    """Best-effort dependency listing for transparency.

    Reads requirements-v6.txt if present (backend image bakes this in).
    web/package.json may or may not be present in the backend image —
    fail silently and emit empty list rather than 503 on absence.
    """
    deps: dict[str, list[str]] = {"python": [], "node": []}
    py_req = Path("/app/requirements-v6.txt")
    if py_req.exists():
        deps["python"] = [
            line.strip()
            for line in py_req.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("-")
        ][:50]  # cap to keep response small
    # web/package.json optional — backend image doesn't include it.
    return deps


def _git_commit() -> str:
    """Resolve git commit SHA in order:

    1. POLARIS_GIT_COMMIT env var — injected at image build time (Dockerfile.v6
       arg) or by cloud-init from the pinned commit it checked out. This is
       the production path; Codex diff iter-2 P1 noted that the container
       does NOT have .git because Dockerfile.v6 only COPYs src/scripts/config.
    2. .git/HEAD probe in /opt/polaris or cwd — local-dev path.
    3. "unknown" — fail-soft.
    """
    explicit = os.environ.get("POLARIS_GIT_COMMIT", "").strip()
    if explicit:
        return explicit[:12]
    for candidate in [Path("/opt/polaris"), Path.cwd()]:
        head_file = candidate / ".git" / "HEAD"
        if head_file.exists():
            head = head_file.read_text(encoding="utf-8").strip()
            if head.startswith("ref: "):
                ref_path = candidate / ".git" / head[5:]
                if ref_path.exists():
                    return ref_path.read_text(encoding="utf-8").strip()[:12]
            return head[:12]
    return "unknown"


def _signing_key_info() -> tuple[str | None, str | None]:
    """Read POLARIS_GPG_KEY_ID and look up the fingerprint via gpg if available."""
    key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip() or None
    if not key_id:
        return None, None
    # The env var IS the fingerprint per I-carney-005 convention.
    return key_id, key_id


def _sovereignty_policy() -> SovereigntyPolicy:
    """Encodes the artifact_to_slice_chain filter constants for reviewers."""
    return SovereigntyPolicy(
        cleared_tiers=["T1"],
        cascade_rule=(
            "Sentences citing non-T1 sources are redacted from the bundle. "
            "Sections with zero passing sentences are dropped. Reports "
            "with zero passing sections raise "
            "SovereigntyFilterEmptiedReportError (HTTP 422)."
        ),
        tier_definitions={
            "T1": "Regulatory + clinical guideline corpora (FDA, EMA, NICE, etc.) — legal-cleared by default",
            "T2": "Peer-reviewed primary literature — requires explicit operator clearance",
            "T3": "Unverified web content + raw uploads — defaults excluded; falls back to T3 on unknown tiers",
        },
    )


def _read_pubkey() -> str:
    """Read the armored GPG public key, falling back to gpg --export.

    Per Codex iter-2 P1-002: cloud-init writes the file alongside the GPG
    import, but local dev may not have the file. Fall back to shelling out
    to gpg if POLARIS_GPG_KEY_ID is set. Strict 503 if neither works.
    """
    path = Path(os.environ.get("POLARIS_GPG_PUBKEY_PATH", DEFAULT_PUBKEY_PATH))
    if path.exists():
        return path.read_text(encoding="utf-8")
    key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip()
    if key_id:
        try:
            result = subprocess.run(
                ["gpg", "--armor", "--export", key_id],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and "BEGIN PGP PUBLIC KEY BLOCK" in result.stdout:
                return result.stdout
        except Exception:
            pass
    raise HTTPException(
        status_code=503,
        detail={
            "error": "pubkey_unavailable",
            "message": (
                f"Public key not found at {path} and gpg --export fallback failed. "
                "Run scripts/bootstrap_gpg_demo_key.sh on the operator workstation "
                "and confirm cloud-init imported the key."
            ),
        },
    )


@router.get("", response_model=TransparencyResponse)
def transparency() -> TransparencyResponse:
    """Public deploy descriptor."""
    key_id, fpr = _signing_key_info()
    # I-carney-008 Codex iter-1 P1-2: treat empty-string env vars as missing
    # (otherwise an unfilled .env template surfaces provider="" / region="").
    provider = os.environ.get("POLARIS_PROVIDER", "").strip() or "unknown"
    region = (
        os.environ.get("POLARIS_REGION", "").strip()
        or os.environ.get("AWS_REGION", "").strip()
        or "unknown"
    )
    # I-carney-008 Codex iter-2 P2-2: surface whether the build-time block
    # (GitHub, Docker registry, Cloudflare CDN, pypi/npm/debian) was pruned
    # from the runtime allowlist by scripts/egress_runtime_tighten.sh.
    pruned_flag = Path(
        os.environ.get(
            "POLARIS_RUNTIME_PRUNED_FLAG", "/etc/polaris/runtime_pruned.flag"
        )
    )
    return TransparencyResponse(
        provider=provider,
        region=region,
        git_commit=_git_commit(),
        polaris_version=__version__,
        deploy_timestamp=datetime.now(timezone.utc).isoformat(),
        signing_key_id=key_id,
        signing_key_fingerprint=fpr,
        sovereignty_filter=_sovereignty_policy(),
        evaluator_models={
            "generator": os.environ.get("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro"),
            # B10 (2026-06-14): emit the RESOLVED live evaluator model, never a stale
            # default. The evaluator role resolves to PG_EVALUATOR_MODEL, else the
            # Mirror (PG_MIRROR_MODEL), else the locked GLM-5.1 — mirroring
            # openrouter_client.PG_EVALUATOR_MODEL = (PG_EVALUATOR_MODEL or PG_MIRROR_MODEL).
            # The old "google/gemma-4-31b-it" default made /transparency LIE about
            # which model actually ran (sovereignty/transparency violation): the live
            # path is GLM, the API reported gemma. "gemma" must NEVER appear here.
            "evaluator": (
                os.environ.get("PG_EVALUATOR_MODEL")
                or os.environ.get("PG_MIRROR_MODEL")
                or "z-ai/glm-5.1"
            ),
        },
        egress_allowlist=_load_egress_allowlist(),
        build_time_hosts_pruned=pruned_flag.exists(),
        dependencies=_load_dependencies(),
    )


@router.get("/pubkey.asc", response_class=PlainTextResponse)
def pubkey() -> PlainTextResponse:
    """Armored GPG public key for bundle signature verification."""
    body = _read_pubkey()
    return PlainTextResponse(content=body, media_type="text/plain; charset=us-ascii")


class PolicyResponse(BaseModel):
    """Full sovereignty + egress policy with version string."""

    version: str
    sovereignty_filter: SovereigntyPolicy
    egress_allowlist: list[str]
    enforcement_layer: list[str]


@router.get("/policy", response_model=PolicyResponse)
def policy() -> PolicyResponse:
    """Return the full sovereignty + egress policy descriptor.

    Bundles the policy version, sovereignty filter, current egress allowlist,
    and the host/Docker enforcement layers that enforce it.
    """
    return PolicyResponse(
        version=POLICY_VERSION,
        sovereignty_filter=_sovereignty_policy(),
        egress_allowlist=_load_egress_allowlist(),
        enforcement_layer=[
            "host iptables OUTPUT chain (scripts/egress_lockdown.sh)",
            "Docker DOCKER-USER chain (scripts/egress_lockdown.sh)",
        ],
    )
