"""S3 CONSOLIDATE checkpoint — ``cp3_basket_snapshot.json`` (Master Execution Plan v2 §4 S3).

The consolidation stage (``synthesis/credibility_pass.py`` — per-claim ``ClaimBasket`` assembly +
``synthesis/finding_dedup.py`` grouping + the contradiction detectors) is the semantic map-reduce of
the pipeline: it groups every source carrying the SAME claim into a **basket** (corroboration, never
a drop) and records the contradiction edges between claims. That work is expensive (the NLI
cross-encoder claim clustering + the isolated per-member verify loop). Today it is re-run from zero
on every ``--resume``. This module persists the CONSOLIDATION DATA at the post-consolidation seam so
a resume can land at cp3 and re-run only the downstream S4-S7 stages.

Scope (per the plan, "checkpoint only; dedup loop already landed"): this module adds NO consolidation
logic — ``finding_dedup`` / ``credibility_pass`` / the detectors stand exactly as deployed. It only
SERIALIZES their output as a DATA-only checkpoint and reloads it fail-loud.

HARD INVARIANT (CLAUDE.md §-1.3, ABSOLUTE — identical to ``corpus_snapshot.py`` /
``generation_snapshot.py``):
    A checkpoint carries DATA, NEVER A VERDICT.
    The snapshot stores the consolidation GROUPING — which sources cluster into which basket, their
    credibility WEIGHTS, the corroboration COUNTS, and the contradiction PAIRS. It stores NO
    faithfulness verdict: the per-member ``span_verdict`` (isolated SUPPORTS/UNSUPPORTED) and the
    ``basket_verdict`` LABEL (full/partial/contested) are DERIVED gate/label outputs and are
    DELIBERATELY EXCLUDED — a resume re-runs the per-member verify + re-derives them from scratch,
    exactly as generation_snapshot's atom_catalog stores PRE-verdict bindings only (evidence_id +
    span offsets + text, never ``is_verified``). No ``release_outcome`` / ``d8_decision`` /
    ``four_role_evaluation`` can ever appear; the RECURSIVE forbidden-verdict-key guard enforces it
    on BOTH the save path (refuse to persist a leaked verdict) and the load path (refuse to load a
    poisoned checkpoint) at ANY nesting depth.

CONSOLIDATE-DON'T-DROP (§-1.3 principle 2): every ``supporting_member`` of every basket is kept —
the checkpoint never thins a basket to hit a number. ``keep_all_members`` is a structural property
the unit harness asserts.

The snapshot is a plain JSON document (schema_version pinned), sorted-keys + deterministic bytes so
the same consolidation produces the same sha256 on any of the 128 cores (cross-core determinism /
byte-identical round-trip). No pickle, no code execution on load.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# Bump on any incompatible schema change. A reload that sees a different version FAILS LOUD (refuses
# to resume) rather than feeding a stale-shaped basket set downstream — LAW II no-silent-downgrade.
CP3_SCHEMA_VERSION = 1

# The canonical snapshot filename inside a per-query run_dir (Master Plan §2: the S3 boundary).
CP3_SNAPSHOT_FILENAME = "cp3_basket_snapshot.json"

# The section id this checkpoint captures (one of the 8 section ids, Master Plan §2).
CP3_STAGE = "s3_consolidate"

# LAW VI kill-switch. Default ON — cp3 is best-effort durability like its siblings
# (corpus_snapshot / postgen_checkpoint), and a checkpoint WRITE changes no report byte (it only
# adds a file to run_dir), so writing it is byte-neutral to the deliverable. OFF => no cp3 is written.
CP3_SNAPSHOT_ENV = "PG_CP3_BASKET_SNAPSHOT"

# The consolidation-affecting env flags stamped into ``flag_slate`` (DATA). A resume that finds a
# different slate refuses to trust the checkpoint (mirrors generation_snapshot.assert_*_flags_match).
# These are the flags that change which baskets/weights/tiers the consolidation produces.
CONSOLIDATION_AFFECTING_ENV_FLAGS = (
    "PG_SWEEP_CREDIBILITY_REDESIGN",
    "PG_BASKET_CONSUME_FINDING_DEDUP",
    "PG_INSTITUTIONAL_AUTHORITY_TIER",
    "PG_CREDIBILITY_TIER_AUTHORITY_JOIN",
)

# The verdict tokens a DATA-ONLY checkpoint may NEVER contain, at ANY nesting depth. This MIRRORS the
# canonical set in ``generator/generation_snapshot.py`` (superset of the ``run_honest_sweep_r3`` A12
# set) so all checkpoints share one definition of "verdict"; kept local to avoid importing a scripts
# module into src (LAW VII isolation). If a forbidden key appears the loader/saver FAILS LOUD — a
# silent load would relax the only hard gate (§-1.3 ABSOLUTE). NOTE: ``span_verdict`` /
# ``basket_verdict`` are consolidation LABELS, not release verdicts, and are EXCLUDED FROM THE PAYLOAD
# by the whitelist projection below (never serialized), so they can never reach this guard.
_FORBIDDEN_VERDICT_KEYS = frozenset(
    {
        "release_outcome",
        "release_allowed",
        "released",
        "verified",
        "is_verified",
        "verified_text",
        "final_verdicts",
        "d8_decision",
        "four_role_evaluation",
        "strict_verify_result",
    }
)


class Cp3SnapshotError(RuntimeError):
    """Raised when cp3 cannot be trusted (absent / corrupt / version-mismatched / verdict-leaked /
    question-mismatched). FAIL LOUD (LAW II): a resume must never silently fall back to a fresh
    consolidation or load a poisoned checkpoint. The caller surfaces this as a clean abort."""


def cp3_snapshot_path(run_dir: Path) -> Path:
    """Deterministic cp3 location for a per-query run_dir."""
    return Path(run_dir) / CP3_SNAPSHOT_FILENAME


def cp3_snapshot_enabled() -> bool:
    """Read the kill-switch at CALL TIME (LAW VI). Default ON (unset == enabled). OFF values:
    ``0`` / ``false`` / ``no`` / ``off`` / empty-after-set."""
    raw = os.getenv(CP3_SNAPSHOT_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


def _assert_no_verdict_keys_recursive(obj: Any, *, path: str = "<root>") -> None:
    """RECURSIVELY fail-loud if a forbidden verdict key appears at ANY nesting depth (Design 6 §3:
    "forbidden-verdict-key guard runs RECURSIVELY on load for every checkpoint"). The basket payload
    is nested (payload -> baskets -> members), so a top-level-only guard would let a verdict key leak
    through a member dict. Walks every dict key + every list/tuple element; a JSON payload has no
    other container types, so the walk is total. Runs on BOTH save (refuse to PERSIST a leak) and
    load (refuse to LOAD a poisoned cp3 — the verdict-smuggling RED test)."""
    if isinstance(obj, dict):
        leaked = sorted(_FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
        if leaked:
            raise Cp3SnapshotError(
                f"cp3 basket snapshot at {path} contains FORBIDDEN verdict key(s) {leaked} — a "
                "checkpoint stores DATA ONLY (§-1.3); a resume re-runs every gate and can NEVER "
                "replay a stored decision. Refusing (recursive verdict-key guard)."
            )
        for key, value in obj.items():
            _assert_no_verdict_keys_recursive(value, path=f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _assert_no_verdict_keys_recursive(value, path=f"{path}[{index}]")


def question_sha256(question: str) -> str:
    """GATE0 identity hash of the research question (hex sha256 of the utf-8 bytes)."""
    return hashlib.sha256((question or "").encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """Hex sha256 of a file's bytes, or "" if absent/unreadable (best-effort hash-chain link)."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (OSError, ValueError):
        return ""


def _capture_consolidation_flags() -> dict[str, str]:
    """Snapshot the consolidation-affecting env flags (DATA, no verdict). An unset flag records the
    empty string so a resume that sets it (or clears it) is DETECTED as a slate mismatch rather than
    silently accepted."""
    return {name: os.environ.get(name, "") for name in CONSOLIDATION_AFFECTING_ENV_FLAGS}


def _member_payload(member: Any) -> dict[str, Any]:
    """DATA-only projection of ONE ``BasketMember`` (credibility_pass.py:713).

    WHITELIST projection (never ``asdict`` minus keys — an allow-list can't leak a future field or a
    verdict; mirrors ``_project_storm_outline_scaffold``). Carries the member's IDENTITY + WEIGHTS +
    the PRE-verdict span binding (offsets + the span text). DELIBERATELY OMITS ``span_verdict`` — the
    isolated per-member SUPPORTS/UNSUPPORTED gate output — which a resume re-derives from scratch.
    """
    span = getattr(member, "span", None)
    span_list = list(span) if isinstance(span, (list, tuple)) else []
    weight = getattr(member, "credibility_weight", None)
    return {
        "evidence_id": str(getattr(member, "evidence_id", "") or ""),
        "source_url": str(getattr(member, "source_url", "") or ""),
        "source_tier": str(getattr(member, "source_tier", "") or ""),
        "origin_cluster_id": str(getattr(member, "origin_cluster_id", "") or ""),
        # WEIGHTS (§-1.3 principle 1) — the credibility weight the basket carries per source.
        "credibility_weight": None if weight is None else float(weight),
        "authority_score": float(getattr(member, "authority_score", 0.0) or 0.0),
        # PRE-verdict span binding (offsets + the exact bytes) — the DATA a resume re-verifies.
        "span": span_list,
        "direct_quote": str(getattr(member, "direct_quote", "") or ""),
        # The additive 3-value entailment TIER label + the durable chrome / judge-outage signals are
        # consolidation DATA (never a release verdict, not in the forbidden set); kept so the resume
        # + forensic monitor see the same member classification without re-scoring page furniture.
        "member_tier": str(getattr(member, "member_tier", "") or ""),
        "span_is_chrome": bool(getattr(member, "span_is_chrome", False)),
        "entailment_judge_unavailable": bool(
            getattr(member, "entailment_judge_unavailable", False)
        ),
    }


def _basket_payload(basket: Any) -> dict[str, Any]:
    """DATA-only projection of ONE ``ClaimBasket`` (credibility_pass.py:759).

    Keeps ALL ``supporting_members`` (§-1.3 CONSOLIDATE-DON'T-DROP — never thinned). Carries the
    consolidation grouping identity + the corroboration COUNTS + the WEIGHT mass + the contradiction
    REFERENCES (``refuter_cluster_ids``). OMITS ``basket_verdict`` — a derived LABEL a resume
    re-derives. ``corroboration_count`` == ``verified_support_origin_count`` (§-1.3 principle 3: the
    corroboration a verdict carries is a COUNT, advisory here — a resume re-derives it, never replays
    it as a gate).
    """
    members = getattr(basket, "supporting_members", None) or []
    refuters = getattr(basket, "refuter_cluster_ids", None) or ()
    return {
        "claim_cluster_id": str(getattr(basket, "claim_cluster_id", "") or ""),
        "claim_text": str(getattr(basket, "claim_text", "") or ""),
        "subject": str(getattr(basket, "subject", "") or ""),
        "predicate": str(getattr(basket, "predicate", "") or ""),
        # WEIGHT (authority-only, copy-uninflatable from weight_mass.py).
        "weight_mass": float(getattr(basket, "weight_mass", 0.0) or 0.0),
        # COUNTS — advisory corroboration strength (§-1.3 principle 3). total_clustered is ADVISORY
        # ONLY; corroboration_count is the isolated-verified distinct-origin count (re-derived on
        # resume). Kept for the forensic monitor's per-tick basket count.
        "total_clustered_origin_count": int(
            getattr(basket, "total_clustered_origin_count", 0) or 0
        ),
        "corroboration_count": int(getattr(basket, "verified_support_origin_count", 0) or 0),
        # CONTRADICTION references — the clusters this basket is contested by (REFERENCE, not dup).
        "refuter_cluster_ids": [str(r) for r in refuters],
        # ALL sources, never dropped (§-1.3 principle 2).
        "members": [_member_payload(m) for m in members],
    }


def _contradiction_payload(edges: Any) -> list[dict[str, Any]]:
    """DATA-only projection of the contradiction edges (``ContradictionEdge``, claim_graph.py:190) —
    the "contradiction pairs" of the plan. Each edge names the producing detector, the claim
    subject/predicate, the endpoint evidence_ids, the endpoint claim_cluster_ids, and the detector's
    own severity label. Pure DATA (a contradiction is disclosed corroboration-conflict, never a
    faithfulness verdict)."""
    out: list[dict[str, Any]] = []
    for edge in edges or []:
        out.append(
            {
                "source": str(getattr(edge, "source", "") or ""),
                "subject": str(getattr(edge, "subject", "") or ""),
                "predicate": str(getattr(edge, "predicate", "") or ""),
                "evidence_ids": [str(e) for e in (getattr(edge, "evidence_ids", None) or ())],
                "claim_cluster_ids": [
                    str(c) for c in (getattr(edge, "claim_cluster_ids", None) or ())
                ],
                "severity": str(getattr(edge, "severity", "") or ""),
            }
        )
    return out


def build_cp3_payload(
    *,
    run_id: str,
    question: str,
    slug: str,
    domain: str,
    credibility_analysis: Any,
    upstream_name: str = "corpus_snapshot.json",
    upstream_sha256: str = "",
    flag_slate: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the cp3 envelope + DATA payload from a ``CredibilityAnalysis`` (credibility_pass.py:785).

    The payload is validated by the RECURSIVE verdict guard BEFORE it is returned (refuse to build a
    leaked-verdict payload). Deterministic content only — no timestamps in the payload body so the
    same consolidation yields the same sha256 (the ``created_utc`` envelope field is filled by the
    writer, kept OUT of the byte-determinism contract by the round-trip harness comparing payload
    bodies).
    """
    baskets = getattr(credibility_analysis, "baskets", None) or []
    edges = getattr(credibility_analysis, "edges", None) or []
    payload: dict[str, Any] = {
        "schema_version": CP3_SCHEMA_VERSION,
        "stage": CP3_STAGE,
        "run_id": str(run_id or ""),
        "slug": str(slug or ""),
        "domain": str(domain or ""),
        "question": str(question or ""),
        "question_sha": question_sha256(question),
        # hash-chain: cp3 pins its input checkpoint (cp2 corpus_snapshot) — Design 6 §3.
        "upstream": {"name": str(upstream_name or ""), "sha256": str(upstream_sha256 or "")},
        # the consolidation-affecting flag slate active when written (resume refuses on drift).
        "flag_slate": dict(flag_slate if flag_slate is not None else _capture_consolidation_flags()),
        # adjustments folded in upstream (empty on a fresh run) — Design 6 §3 envelope.
        "adjustments_applied": [],
        "payload": {
            "baskets": [_basket_payload(b) for b in baskets],
            "contradiction_pairs": _contradiction_payload(edges),
            "basket_count": len(baskets),
            "contradiction_pair_count": len(edges),
        },
        "faithfulness_invariant": (
            "DATA ONLY; no span_verdict/basket_verdict/release verdict stored; a resume re-runs "
            "the per-member verify + every gate and can NEVER replay a stored decision."
        ),
    }
    # Defensive save-path guard: my projection is a whitelist and cannot leak, but re-assert so a
    # future field-add that accidentally names a verdict key fails LOUD in tests, not in production.
    _assert_no_verdict_keys_recursive(payload, path="<cp3-build>")
    return payload


def serialize_cp3_payload(payload: dict[str, Any]) -> str:
    """The ONE canonical serialization (sorted-keys, deterministic bytes) — shared by the writer and
    the round-trip harness so a re-serialize of a reloaded payload is byte-identical to the original.
    Excludes ``created_utc`` from the determinism contract by the caller passing a payload without it
    (the harness compares the DATA body)."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"


def save_cp3_basket_snapshot(
    run_dir: Path,
    *,
    run_id: str,
    question: str,
    slug: str,
    domain: str,
    credibility_analysis: Any,
    upstream_name: str = "corpus_snapshot.json",
    upstream_sha256: str = "",
    flag_slate: dict[str, str] | None = None,
    created_utc: str | None = None,
) -> Path | None:
    """Persist ``cp3_basket_snapshot.json`` (DATA ONLY). Returns the written path, or None when cp3 is
    disabled (kill-switch OFF) or ``credibility_analysis`` is absent (master flag off => nothing to
    consolidate — byte-neutral, no artifact).

    Atomic write (temp + ``os.replace``) so a kill DURING the write never leaves a half-parsed file a
    later ``--resume`` would choke on. Raises ``Cp3SnapshotError`` only if the (whitelist) payload
    somehow carries a verdict key — the production seam wraps this best-effort so a durability hiccup
    never aborts a paid run, while a real leak still surfaces in tests.
    """
    if not cp3_snapshot_enabled():
        return None
    if credibility_analysis is None:
        return None
    payload = build_cp3_payload(
        run_id=run_id,
        question=question,
        slug=slug,
        domain=domain,
        credibility_analysis=credibility_analysis,
        upstream_name=upstream_name,
        upstream_sha256=upstream_sha256,
        flag_slate=flag_slate,
    )
    # created_utc is envelope metadata, kept OUT of the byte-determinism body (the harness compares
    # the DATA payload). Default to a fixed empty marker when the caller does not supply a clock.
    payload["created_utc"] = str(created_utc or "")
    run_dir = Path(run_dir)
    path = cp3_snapshot_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialize_cp3_payload(payload), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_cp3_basket_snapshot(
    run_dir: Path,
    *,
    expected_question_sha: str | None = None,
) -> dict[str, Any]:
    """Reload + validate cp3 for a resume. Returns the parsed payload (DATA ONLY — the caller MUST
    re-run every faithfulness gate on it).

    FAIL LOUD (``Cp3SnapshotError``) on: absent / unreadable / non-object / version-mismatched /
    verdict-smuggled (recursive guard — the RED test) / question-mismatched (GATE0 identity) cp3.
    Never a silent fresh-consolidation fallback.
    """
    path = cp3_snapshot_path(run_dir)
    if not path.exists():
        raise Cp3SnapshotError(
            f"--resume: no cp3 basket snapshot at {path} (nothing to resume at S3; run without "
            f"--resume-from cp3 for a fresh consolidation)"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Cp3SnapshotError(
            f"--resume: cp3 basket snapshot at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise Cp3SnapshotError(f"--resume: cp3 basket snapshot at {path} is not a JSON object")
    version = payload.get("schema_version")
    if version != CP3_SCHEMA_VERSION:
        raise Cp3SnapshotError(
            f"--resume: cp3 basket snapshot schema_version {version!r} != expected "
            f"{CP3_SCHEMA_VERSION} at {path}; refusing to resume on a stale-shaped basket set "
            f"(re-run fresh)"
        )
    # Recursive verdict-key guard — the poisoned-cp3 RED test. A checkpoint with any forbidden
    # verdict key at ANY depth is REFUSED (a resume re-runs every gate; it can never replay one).
    _assert_no_verdict_keys_recursive(payload, path=str(path))
    if expected_question_sha is not None and payload.get("question_sha") != expected_question_sha:
        raise Cp3SnapshotError(
            f"--resume: cp3 basket snapshot at {path} is for a DIFFERENT question "
            f"(question_sha {payload.get('question_sha')!r} != expected {expected_question_sha!r}); "
            f"GATE0 identity mismatch — refusing to resume (a question change is a new run)"
        )
    return payload
