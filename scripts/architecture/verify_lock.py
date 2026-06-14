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

import ast
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
SRC_ROOT = REPO_ROOT / "src"

# B10 conformance gate (2026-06-14): the locked Mirror slug. Any inline
# PG_EVALUATOR_MODEL default in live src/ must equal this (the evaluator role
# maps to the Mirror per the lock's legacy_compat). Read from the lock at call
# time, not hardcoded, so it tracks the operator-signed truth.
_GEMMA_PREFIX = "google/gemma"

# Frozen pipeline-C (src/orchestration/**) is governed separately (CLAUDE.md §5);
# its config is not on the live faithfulness path. Scope the gate to live src/.
_GEMMA_GATE_EXCLUDE_DIRS = ("orchestration",)


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

    # Slug check: each role's lock model_slug must equal its code default.
    # Import lazily so this module stays import-safe at boot.
    from src.polaris_graph.llm.openrouter_client import (
        PG_GENERATOR_MODEL,
        PG_JUDGE_MODEL,
        PG_MIRROR_MODEL,
        PG_SENTINEL_MODEL,
    )

    role_to_code_default = {
        "generator": PG_GENERATOR_MODEL,
        "mirror": PG_MIRROR_MODEL,
        "sentinel": PG_SENTINEL_MODEL,
        "judge": PG_JUDGE_MODEL,
    }

    for role, spec in lock["required_roles"].items():
        code_default = role_to_code_default.get(role)
        if code_default is None:
            # No code-default constant for this role; skip the slug assertion.
            continue
        declared = spec["model_slug"]
        if declared != code_default:
            raise LockMismatch(
                f"role {role!r} lock model_slug {declared!r} does not match "
                f"code default {code_default!r}; reconcile "
                f"config/architecture/polaris_runtime_lock.yaml with "
                f"src/polaris_graph/llm/openrouter_client.py"
            )

    for role, spec in lock["required_roles"].items():
        results[role] = {
            "ok": True,
            "declared_model": spec["model_slug"],
            "declared_family": spec["family"],
            "mismatches": [],
        }

    return results


def _mirror_slug_from_lock() -> str:
    """Return the locked Mirror model_slug (the evaluator's legacy_compat target)."""
    lock = load_lock()
    return lock["required_roles"]["mirror"]["model_slug"]


def _getenv_default_literal(call: ast.Call) -> tuple[str | None, str | None]:
    """If ``call`` is os.getenv / os.environ.get with a string-literal default,
    return (env_var_name_or_None, default_literal_or_None); else (None, None).

    Recognizes both ``os.getenv("X", "default")`` and
    ``os.environ.get("X", "default")``. The default is the 2nd POSITIONAL arg.
    Dict literals (cost table, family registry) and comments are NOT ast.Call
    nodes of this shape, so they are structurally excluded — zero false positives.
    """
    func = call.func
    is_getenv = (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    )
    is_environ_get = (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )
    if not (is_getenv or is_environ_get):
        return None, None

    def _const_str(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    # The default may be the 2nd POSITIONAL arg OR a `default=` keyword
    # (os.getenv supports both; os.environ.get's mapping .get default is
    # positional, but a kwarg form is still parsed here defensively so the gate
    # cannot be bypassed by os.getenv("X", default="google/gemma-...")). Codex
    # B10 iter-1 P2.
    default_node: ast.AST | None = None
    if len(call.args) >= 2:
        default_node = call.args[1]
    else:
        for kw in call.keywords:
            if kw.arg == "default":
                default_node = kw.value
                break
    if default_node is None:
        return None, None  # no default supplied

    env_name = _const_str(call.args[0]) if call.args else None
    default_lit = _const_str(default_node)
    return env_name, default_lit


def scan_gemma_defaults() -> list[str]:
    """Scan live src/ for forbidden gemma model defaults + bad evaluator defaults.

    Returns a list of human-readable violation strings (empty = clean). Two checks
    via AST (so comments/docstrings/cost-table/family-registry never false-positive):

      1. NO live src/ os.getenv/os.environ.get may default a model env var to a
         ``google/gemma*`` slug. This is the structural close that stops the
         transparency.py / llm_provider.py class of bug from recurring.
      2. Any inline ``PG_EVALUATOR_MODEL`` default MUST equal the locked Mirror slug
         (the evaluator role maps to the Mirror per the lock's legacy_compat). A
         PG_EVALUATOR_MODEL with NO string default (e.g. ``os.getenv(...) or X``)
         passes — there is no literal default to be wrong.
    """
    violations: list[str] = []
    if not SRC_ROOT.exists():
        return violations
    try:
        mirror_slug = _mirror_slug_from_lock()
    except Exception as exc:  # noqa: BLE001
        return [f"could not load lock mirror slug: {exc}"]

    for py_path in sorted(SRC_ROOT.rglob("*.py")):
        rel = py_path.relative_to(REPO_ROOT).as_posix()
        if any(f"/{d}/" in f"/{rel}" for d in _GEMMA_GATE_EXCLUDE_DIRS):
            continue
        try:
            tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            env_name, default_lit = _getenv_default_literal(node)
            if default_lit is None:
                continue
            # Check 1: forbidden gemma default for any model env var.
            if default_lit.lower().startswith(_GEMMA_PREFIX):
                violations.append(
                    f"{rel}:{node.lineno}: forbidden gemma default "
                    f"{default_lit!r} for env {env_name!r} — repoint to the locked "
                    f"GLM mirror (no google/gemma* runtime default; CLAUDE.md §9.1.8)"
                )
            # Check 2: inline PG_EVALUATOR_MODEL default must equal the mirror.
            if env_name == "PG_EVALUATOR_MODEL" and default_lit != mirror_slug:
                violations.append(
                    f"{rel}:{node.lineno}: PG_EVALUATOR_MODEL inline default "
                    f"{default_lit!r} != locked mirror {mirror_slug!r} — the "
                    f"evaluator role maps to the Mirror (lock legacy_compat)"
                )
    return violations


def gemma_gate(stream=sys.stdout) -> int:
    """CI conformance gate: 0 iff no forbidden gemma/evaluator default in live src/."""
    violations = scan_gemma_defaults()
    if violations:
        print("Gemma conformance gate: FAIL", file=stream)
        for v in violations:
            print(f"  - {v}", file=stream)
        return 1
    print(
        "Gemma conformance gate: OK — no google/gemma* model default and no "
        "mis-pointed PG_EVALUATOR_MODEL default in live src/",
        file=stream,
    )
    return 0


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


def verify_consistency(stream=sys.stdout) -> int:
    """Status-independent consistency gate.

    Returns 0 when ALL of the following hold, REGARDLESS of the lock's
    ``status`` field or the propagation ``tests_pass`` checkpoint:
      - the lock YAML loads
      - every declared family is registered in _FAMILY_PREFIXES
      - family_policy (all_distinct) holds
      - code defaults match the lock model_slugs
      - canonical_pin.txt includes the lock file path

    The first four are covered by verify_lock_against_code(); the last is a
    substring presence check on canonical_pin.txt. This deliberately does NOT
    route through check_propagation_manifest() (which hardwires tests_pass=False
    and git-tracked checks). Returns 0 on full consistency, 1 on any mismatch.
    """
    try:
        verify_lock_against_code()
    except LockMismatch as exc:
        print(f"Consistency: FAIL — {exc}", file=stream)
        return 1

    if not CANONICAL_PIN_PATH.exists():
        print(
            f"Consistency: FAIL — canonical pin missing: {CANONICAL_PIN_PATH}",
            file=stream,
        )
        return 1

    pin_content = CANONICAL_PIN_PATH.read_text(encoding="utf-8")
    if "config/architecture/polaris_runtime_lock.yaml" not in pin_content:
        print(
            "Consistency: FAIL — canonical_pin.txt does not include the lock file",
            file=stream,
        )
        return 1

    # B10 (2026-06-14): the gemma conformance gate is part of consistency — no live
    # src/ path may default a model to a google/gemma* slug, and inline
    # PG_EVALUATOR_MODEL defaults must equal the mirror. Makes B10 self-enforcing:
    # the transparency.py / llm_provider.py class of drift fails CI on re-introduction.
    gemma_violations = scan_gemma_defaults()
    if gemma_violations:
        print("Consistency: FAIL — gemma conformance gate:", file=stream)
        for v in gemma_violations:
            print(f"  - {v}", file=stream)
        return 1

    print("Consistency: OK — families registered, family_policy holds, "
          "code defaults match lock, canonical_pin includes lock file, "
          "no gemma model default in live src/", file=stream)
    return 0


if __name__ == "__main__":
    if "--gemma-gate" in sys.argv:
        sys.exit(gemma_gate())
    if "--consistency" in sys.argv:
        sys.exit(verify_consistency())
    sys.exit(report())
