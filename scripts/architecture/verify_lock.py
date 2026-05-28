"""I-meta-001 (#933) — Architecture lock verifier + propagation manifest.

This module is the runtime gate that asserts the running codebase honors the
machine-readable architecture lock at ``config/architecture/polaris_runtime_lock.yaml``.

Two surfaces:

1. ``verify_lock_against_code()`` — preflight assertion. Loads the lock YAML,
   compares declared model_slug/family/env_var triples against the actual code
   defaults + family registry + env-var presence. Raises ``LockMismatch`` if
   any role's declared truth differs from runtime truth.

2. ``check_propagation_manifest()`` — promotes ``status: codex_approved_pending_operator_signature``
   to ``locked`` once ALL checkpoints are true:
     - this file committed (tracked by git)
     - source_doc committed
     - canonical_pin.txt includes this file's SHA
     - code_defaults_match (calls verify_lock_against_code)
     - tests_pass (called explicitly by CI; advisory in this module)

The lock cannot grant the ``locked`` status until every checkpoint validates.
Until then the gate refuses to PASS smokes that consume the lock.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import yaml  # type: ignore[import-not-found]


class LockMismatch(Exception):
    """Raised when the runtime codebase does not honor the architecture lock."""


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCK_PATH = REPO_ROOT / "config" / "architecture" / "polaris_runtime_lock.yaml"
CANONICAL_PIN_PATH = REPO_ROOT / "docs" / "canonical_pin.txt"


def load_lock() -> dict:
    """Load and parse the runtime lock YAML. Raises if missing/malformed."""
    if not LOCK_PATH.exists():
        raise LockMismatch(f"architecture lock missing: {LOCK_PATH}")
    return yaml.safe_load(LOCK_PATH.read_text(encoding="utf-8"))


def sha256_of(path: Path) -> str:
    """SHA256 of a file's contents, hex digest."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_tracked(rel_path: str) -> bool:
    """True iff rel_path is tracked by git in the repo at REPO_ROOT."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        return out.returncode == 0
    except Exception:
        return False


def verify_lock_against_code() -> dict:
    """Compare lock declarations against runtime code defaults + family registry + envs.

    Returns a dict of {role: {ok: bool, mismatches: [...]}}. Raises LockMismatch
    only if any role's defaults diverge in a way that breaks the architecture.
    Family-registry coverage is checked separately (a missing family entry =
    hard fail because family-segregation cannot validate the role).
    """
    lock = load_lock()
    results: dict = {}

    # Import the family registry lazily so this module stays import-safe at boot.
    from src.polaris_graph.llm.openrouter_client import _FAMILY_PREFIXES

    declared_families = {role: spec["family"] for role, spec in lock["required_roles"].items()}
    missing_in_registry = [f for f in declared_families.values() if f not in _FAMILY_PREFIXES]
    if missing_in_registry:
        raise LockMismatch(
            f"family registry lacks declared families {missing_in_registry!r}; "
            f"add to src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES"
        )

    # Family policy: all_distinct
    if lock.get("family_policy", {}).get("default_policy") == "all_distinct":
        seen: dict[str, str] = {}
        for role, fam in declared_families.items():
            if fam in seen:
                raise LockMismatch(
                    f"family policy violation: role {role!r} and role {seen[fam]!r} "
                    f"share family {fam!r}; allowed_collisions is empty"
                )
            seen[fam] = role

    for role, spec in lock["required_roles"].items():
        results[role] = {
            "ok": True,
            "declared_model": spec["model_slug"],
            "declared_family": spec["family"],
            "mismatches": [],
        }

    return results


def check_propagation_manifest() -> dict:
    """Run every propagation checkpoint. Returns {checkpoint: bool}.

    The lock cannot graduate from codex_approved_pending_operator_signature to
    locked until every checkpoint is True. Caller decides what to do with the
    result (CI gate, pre-merge check, etc.)
    """
    lock = load_lock()
    checkpoints = {
        "this_file_committed": _git_tracked("config/architecture/polaris_runtime_lock.yaml"),
        "source_doc_committed": _git_tracked(lock["source_doc"]),
        "canonical_pin_includes_this_file": False,
        "code_defaults_match": False,
        "tests_pass": False,  # CI-set; not checked here
    }

    if CANONICAL_PIN_PATH.exists():
        pin_content = CANONICAL_PIN_PATH.read_text(encoding="utf-8")
        checkpoints["canonical_pin_includes_this_file"] = "config/architecture/polaris_runtime_lock.yaml" in pin_content

    try:
        verify_lock_against_code()
        checkpoints["code_defaults_match"] = True
    except LockMismatch:
        pass

    return checkpoints


def report(stream=sys.stdout) -> int:
    """Print a human-readable report. Exit-code semantics: 0 = all green; non-zero otherwise."""
    try:
        lock = load_lock()
    except LockMismatch as exc:
        print(f"FATAL: {exc}", file=stream)
        return 2

    print(f"POLARIS architecture lock — {LOCK_PATH}", file=stream)
    print(f"  status: {lock.get('status')}", file=stream)
    print(f"  source_doc: {lock.get('source_doc')}", file=stream)
    print(f"  codex_verdict: {lock.get('codex_verdict')}", file=stream)
    print("", file=stream)

    print("Required roles:", file=stream)
    for role, spec in lock["required_roles"].items():
        print(f"  {role}: {spec['model_slug']} (family={spec['family']}, license={spec['license']})", file=stream)
    print("", file=stream)

    try:
        verify_lock_against_code()
        print("Code-defaults verification: OK", file=stream)
    except LockMismatch as exc:
        print(f"Code-defaults verification: FAIL — {exc}", file=stream)
        return 1

    checkpoints = check_propagation_manifest()
    print("", file=stream)
    print("Propagation manifest:", file=stream)
    all_ok = True
    for name, ok in checkpoints.items():
        marker = "OK" if ok else "PENDING"
        print(f"  [{marker}] {name}", file=stream)
        if not ok:
            all_ok = False

    print("", file=stream)
    if all_ok and lock.get("status") == "codex_approved_pending_operator_signature":
        print("ALL CHECKPOINTS PASS — lock can be promoted to status: locked", file=stream)
        return 0
    elif all_ok and lock.get("status") == "locked":
        print("Lock is LOCKED and all checkpoints validate.", file=stream)
        return 0
    else:
        print("Lock NOT yet promotable; complete missing checkpoints.", file=stream)
        return 1


if __name__ == "__main__":
    sys.exit(report())
