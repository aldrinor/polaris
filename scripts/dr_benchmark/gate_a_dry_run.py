"""Gate-A no-spend dry-run harness (I-meta-002 sub-PR-6).

This is the operator's NO-SPEND green gate: it proves the 4-role substrate is internally
consistent and exercisable OFFLINE, with NO real network and NO money, BEFORE the operator
authorizes any paid (Gate-B) run. It emits a machine-readable PASS/FAIL report plus a
human-readable summary for the dual §-1.1 line-by-line review.

The four PASS checks (ALL must be green; ALL no-spend):

  (a) pytest tests/roles tests/architecture tests/dr_benchmark — run SERIALIZED (one process
      at a time per CLAUDE.md §8.4 resource discipline), each rc captured.
  (b) ``verify_lock --consistency`` exit-code 0 — the architecture lock is internally
      consistent (families registered, all-distinct policy holds, code defaults match, the
      canonical pin includes the lock) REGARDLESS of the pending ``status`` field.
  (c) FROZEN-LOCK COVERAGE (Codex P2 option (b)): build the FOUR role pins from the
      lock-sourced ``pathB_runner._role_pins()`` and run ``validate_role_families`` on the
      effective map — assert generator/mirror/sentinel/judge are present AND their families are
      all distinct. This DELIBERATELY does NOT call ``_assert_architecture_coverage`` (which
      RAISES while the lock is pending): there is no bypass mode a paid smoke could reuse.
  (d) Per-role contract fixtures via the MOCK transport: Sentinel ``yes`` => UNGROUNDED
      (lethal-polarity), Judge 5-enum (off-enum raises), Mirror two-pass binding holds.

The 3 cheap real probes (Serper / Semantic Scholar / DeepSeek) are GATED behind a default-OFF
``--with-live-probes`` flag and are NEVER part of the PASS criteria — the dry run is pure
zero-spend unless the operator explicitly opts in. Even with the flag set, the probes are
ADVISORY telemetry only.

Import-safety: importing this module performs NO I/O and starts NO subprocess. argparse,
subprocess, and pytest invocation all live under ``if __name__ == "__main__"`` / the
``main()`` entry only; the check functions are pure enough to be unit-tested offline (the
coverage + contract checks take no network).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Repo root: <root>/scripts/dr_benchmark/gate_a_dry_run.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]

# The four locked roles the coverage check must observe (canonical pipeline order).
_EXPECTED_ROLES = ("generator", "mirror", "sentinel", "judge")

# The pytest suites the dry run runs serialized (no-spend, offline).
_PYTEST_SUITES = ("tests/roles", "tests/architecture", "tests/dr_benchmark")

# Default report path under the repo's outputs tree.
_DEFAULT_REPORT_PATH = _REPO_ROOT / "outputs" / "gate_a" / "dry_run_report.json"

# Mock-transport canned outputs for the per-role contract fixtures (check (d)).
_SENTINEL_YES = "<score>yes</score>"  # yes = risk present = UNGROUNDED (lethal-polarity guard)
_JUDGE_OFF_ENUM = "definitely-true"   # off-enum token -> JudgeEnumError (no silent default)


@dataclass
class CheckResult:
    """One Gate-A check outcome."""

    name: str
    passed: bool
    detail: str


@dataclass
class GateAReport:
    """The full Gate-A dry-run report."""

    overall_pass: bool
    checks: list[CheckResult] = field(default_factory=list)
    live_probes_ran: bool = False
    live_probe_results: list[CheckResult] = field(default_factory=list)

    def to_json_dict(self) -> dict:
        return {
            "overall_pass": self.overall_pass,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
            "live_probes_ran": self.live_probes_ran,
            "live_probe_results": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in self.live_probe_results
            ],
            "no_spend": True,
            "note": (
                "Gate-A is no-spend/offline. PASS does NOT authorize a paid run; lock "
                "promotion to status: locked is the operator's separate spend gate (Gate-B)."
            ),
        }


# --- check (a): pytest suites, serialized -------------------------------------------------
def check_pytest_suites(suites: tuple[str, ...] = _PYTEST_SUITES) -> CheckResult:
    """Run each pytest suite SERIALIZED (one subprocess at a time), capture rc.

    PASS iff every suite exits 0. Serialized per CLAUDE.md §8.4 (no parallel pytest runs).
    """
    failures: list[str] = []
    for suite in suites:
        suite_path = _REPO_ROOT / suite
        if not suite_path.exists():
            failures.append(f"{suite}: MISSING")
            continue
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stdout or "").strip().splitlines()[-3:]
            failures.append(f"{suite}: rc={proc.returncode} {' | '.join(tail)}")
    if failures:
        return CheckResult("pytest_suites", False, "; ".join(failures))
    return CheckResult(
        "pytest_suites", True, f"all {len(suites)} suites passed (serialized)"
    )


# --- check (b): verify_lock --consistency rc==0 -------------------------------------------
def check_lock_consistency() -> CheckResult:
    """Run ``verify_lock --consistency`` and require exit-code 0 (status-independent)."""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.architecture.verify_lock", "--consistency"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    detail = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail_text = detail[-1] if detail else f"rc={proc.returncode}"
    return CheckResult("lock_consistency", proc.returncode == 0, detail_text)


# --- check (c): FROZEN-LOCK COVERAGE via P2 option (b) ------------------------------------
def check_frozen_lock_coverage() -> CheckResult:
    """Build the 4 role pins from the lock + run validate_role_families on the effective map.

    Codex P2 option (b): call ``pathB_runner._role_pins()`` (lock-sourced) and
    ``openrouter_client.validate_role_families`` DIRECTLY. Assert the four roles
    generator/mirror/sentinel/judge are present AND their families are all distinct. This does
    NOT invoke ``_assert_architecture_coverage`` (which raises on a pending lock) and creates no
    bypass a paid smoke could reuse. No network: imports + pure pin-build + family registry.
    """
    # Imported lazily so the module stays import-safe at boot (no side effects on import).
    from src.polaris_graph.benchmark.benchmark_gate_runner import _role_pins
    from src.polaris_graph.llm.openrouter_client import validate_role_families

    pins = _role_pins()
    pinned_roles = {pin.role for pin in pins}
    # Assert EXACTLY the 4 locked roles — fail on a missing role OR an extra/stray pin (Codex
    # sub-PR-6 diff P2): the architecture-coverage invariant is set-equality, not just presence.
    expected = set(_EXPECTED_ROLES)
    if pinned_roles != expected:
        missing = sorted(expected - pinned_roles)
        extra = sorted(pinned_roles - expected)
        return CheckResult(
            "frozen_lock_coverage",
            False,
            f"role pins must be EXACTLY {sorted(expected)}; missing={missing} extra={extra} "
            f"observed={sorted(pinned_roles)}",
        )

    effective_map = {pin.role: pin.model_slug for pin in pins}
    # Raises RuntimeError on an unknown family OR an all-distinct collision (fail loud).
    role_families = validate_role_families(effective_map)
    distinct_families = set(role_families.values())
    if len(distinct_families) != len(role_families):
        return CheckResult(
            "frozen_lock_coverage",
            False,
            f"family segregation violated: {role_families}",
        )
    return CheckResult(
        "frozen_lock_coverage",
        True,
        f"4 roles pinned + all-distinct families {role_families}",
    )


# --- check (d): per-role contract fixtures via the MOCK transport -------------------------
class _GateAMockTransport:
    """Mock RoleTransport for the offline per-role contract fixtures (no network, no spend).

    Returns canned outputs keyed on role: Mirror two-pass grounded; Sentinel ``yes`` =>
    UNGROUNDED; Judge an off-enum token (so the 5-enum guard raises). Configurable per fixture.
    """

    def __init__(self, *, judge_raw: str, sentinel_raw: str):
        self._judge_raw = judge_raw
        self._sentinel_raw = sentinel_raw

    def complete(self, request):
        from src.polaris_graph.roles.mirror_contract import CitationSpan
        from src.polaris_graph.roles.role_transport import RoleResponse

        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(
                    raw_text=json.dumps(payload), served_model=request.model_slug
                )
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=("doc1",))],
            )
        if request.role == "sentinel":
            return RoleResponse(raw_text=self._sentinel_raw, served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(raw_text=self._judge_raw, served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


def check_role_contracts() -> CheckResult:
    """Exercise the three role contracts THROUGH the mock RoleTransport + adapters (Codex P2).

    Routes each fixture through the real adapter -> injected `_GateAMockTransport` -> contract
    path (NOT direct parser calls), so check (d) is the fixture-through-transport check the
    brief required. Asserts:
    - Sentinel ``<score>yes</score>`` => UNGROUNDED (lethal-polarity: yes=risk=ungrounded).
    - Judge off-enum token => JudgeEnumError (no silent default for the terminal arbiter).
    - Mirror two-pass grounded round trip returns a bound MirrorPass2 (binding held).
    No network, no spend: the transport is the in-process mock.
    """
    from src.polaris_graph.roles.judge_adapter import run_judge
    from src.polaris_graph.roles.judge_contract import JudgeEnumError
    from src.polaris_graph.roles.mirror_adapter import run_mirror
    from src.polaris_graph.roles.role_transport import EvidenceDocument
    from src.polaris_graph.roles.sentinel_adapter import run_sentinel
    from src.polaris_graph.roles.sentinel_contract import SentinelVerdict

    transport = _GateAMockTransport(judge_raw=_JUDGE_OFF_ENUM, sentinel_raw=_SENTINEL_YES)
    # The mock Mirror pass-1 cites doc_ids=("doc1",); supply that as a real evidence document so
    # the grounding-integrity binding accepts it.
    evidence = [EvidenceDocument(doc_id="doc1", text="grounded answer source span")]
    claim = "The grounded answer."
    problems: list[str] = []

    # Sentinel GUARDIAN polarity through the adapter+transport: yes => UNGROUNDED, parsed_ok True.
    # mode="guardian" is pinned so this lethal-polarity fixture is mode-deterministic regardless of
    # the global default (I-run11-004: the default is now the MiniMax-M2 decomposition mode).
    sentinel_result, _ = run_sentinel(
        transport, claim, evidence,
        model_slug="ibm-granite/granite-guardian-4.1-8b", mode="guardian",
    )
    if sentinel_result.verdict is not SentinelVerdict.UNGROUNDED or not sentinel_result.parsed_ok:
        problems.append(
            f"Sentinel polarity wrong via transport: {sentinel_result} (expected UNGROUNDED)"
        )

    # Sentinel DECOMPOSITION contract (I-run11-004): the CERTIFIED MiniMax-M2 JSON verdict
    # "unsupported" => UNGROUNDED, "supported" => GROUNDED (mode pinned for determinism).
    decomp_unsupported = _GateAMockTransport(
        judge_raw=_JUDGE_OFF_ENUM,
        sentinel_raw='{"verdict": "unsupported", "unsupported_atoms": 1, "atoms": []}',
    )
    decomp_result, _ = run_sentinel(
        decomp_unsupported, claim, evidence,
        model_slug="minimax/minimax-m2", mode="decomposition",
    )
    if decomp_result.verdict is not SentinelVerdict.UNGROUNDED or not decomp_result.parsed_ok:
        problems.append(
            f"Sentinel decomposition unsupported wrong via transport: {decomp_result} "
            "(expected UNGROUNDED)"
        )
    decomp_supported = _GateAMockTransport(
        judge_raw=_JUDGE_OFF_ENUM,
        # Full decomposition contract (I-run11-004 brief-gate P1): a "supported" verdict needs a
        # non-empty atoms list + unsupported_atoms, else the parser fails closed (a bare/non-atomized
        # "supported" did no per-atom work and must not release).
        sentinel_raw='{"verdict": "supported", "unsupported_atoms": 0, "atoms": [{"atom": "x", "type": "mechanism", "status": "supported"}]}',
    )
    decomp_grounded, _ = run_sentinel(
        decomp_supported, claim, evidence,
        model_slug="minimax/minimax-m2", mode="decomposition",
    )
    if decomp_grounded.verdict is not SentinelVerdict.GROUNDED or not decomp_grounded.parsed_ok:
        problems.append(
            f"Sentinel decomposition supported wrong via transport: {decomp_grounded} "
            "(expected GROUNDED)"
        )

    # Judge through the adapter+transport: an off-enum token must RAISE (no silent default).
    # I-judge-kimi (2026-06-29): the benchmark Judge is now moonshotai/kimi-k2.6 (was qwen); the
    # off-enum rejection under test is model-agnostic, so this just reflects the current Judge slug.
    try:
        run_judge(
            transport,
            claim,
            evidence,
            "supported",
            "ungrounded",
            model_slug="moonshotai/kimi-k2.6",
        )
        problems.append(
            f"Judge accepted off-enum token {_JUDGE_OFF_ENUM!r} via transport "
            "(should raise JudgeEnumError)"
        )
    except JudgeEnumError:
        pass

    # Mirror through the adapter+transport: the two-pass grounded round trip binds and returns.
    try:
        mirror_pass2, mirror_records = run_mirror(
            transport, claim, evidence, model_slug="z-ai/glm-5.1"
        )
        if mirror_pass2 is None or len(mirror_records) != 2:
            problems.append(
                f"Mirror two-pass via transport did not return a bound pass-2 + 2 records "
                f"(got pass2={mirror_pass2!r}, records={len(mirror_records)})"
            )
    except Exception as exc:  # noqa: BLE001 - surface any fail-closed raise as a contract problem
        problems.append(f"Mirror two-pass via transport raised unexpectedly: {exc!r}")

    if problems:
        return CheckResult("role_contracts", False, "; ".join(problems))
    return CheckResult(
        "role_contracts",
        True,
        "via transport: Sentinel guardian yes=UNGROUNDED + decomposition "
        "supported=GROUNDED/unsupported=UNGROUNDED, Judge off-enum raises, Mirror two-pass binds",
    )


# --- cheap live probes (default OFF; ADVISORY ONLY; never part of PASS) --------------------
def run_live_probes() -> list[CheckResult]:
    """Run the 3 cheap real probes (Serper / Semantic Scholar / DeepSeek) — ADVISORY ONLY.

    Gated behind ``--with-live-probes``; NEVER part of the PASS criteria (the dry run is
    no-spend by default). Each probe is best-effort: a failure is reported as advisory, not a
    gate failure. Implemented as a documented stub here — the live probe wiring is intentionally
    minimal so the dry-run default path stays zero-network.
    """
    return [
        CheckResult(
            "live_probe_serper",
            False,
            "advisory stub: live Serper probe not wired in the no-spend harness",
        ),
        CheckResult(
            "live_probe_semantic_scholar",
            False,
            "advisory stub: live Semantic Scholar probe not wired in the no-spend harness",
        ),
        CheckResult(
            "live_probe_deepseek",
            False,
            "advisory stub: live DeepSeek probe not wired in the no-spend harness",
        ),
    ]


def run_gate_a(*, with_live_probes: bool = False) -> GateAReport:
    """Run all four no-spend Gate-A checks. PASS iff (a) AND (b) AND (c) AND (d) are green.

    The cheap live probes are run ONLY when ``with_live_probes`` is True and are ADVISORY —
    they never affect ``overall_pass``.
    """
    checks = [
        check_pytest_suites(),
        check_lock_consistency(),
        check_frozen_lock_coverage(),
        check_role_contracts(),
    ]
    overall = all(c.passed for c in checks)
    report = GateAReport(overall_pass=overall, checks=checks)
    if with_live_probes:
        report.live_probes_ran = True
        report.live_probe_results = run_live_probes()
    return report


def _render_human_summary(report: GateAReport) -> str:
    lines = [
        "POLARIS Gate-A no-spend dry run",
        f"  OVERALL: {'PASS' if report.overall_pass else 'FAIL'} (no-spend, offline)",
        "",
    ]
    for check in report.checks:
        lines.append(f"  [{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    if report.live_probes_ran:
        lines.append("")
        lines.append("  Live probes (ADVISORY ONLY — not part of PASS):")
        for probe in report.live_probe_results:
            lines.append(
                f"    [{'ok' if probe.passed else 'advisory'}] {probe.name}: {probe.detail}"
            )
    lines.append("")
    lines.append(
        "  Gate-A PASS does NOT authorize spend. Lock promotion to status: locked is the "
        "operator's separate spend gate."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run Gate-A, write the JSON report + a human summary, return 0 iff PASS."""
    import argparse

    parser = argparse.ArgumentParser(description="POLARIS Gate-A no-spend dry run.")
    parser.add_argument(
        "--with-live-probes",
        action="store_true",
        help=(
            "Run the 3 cheap real probes (Serper/S2/DeepSeek). ADVISORY ONLY — default OFF so "
            "the dry run is pure zero-spend. Never affects PASS/FAIL."
        ),
    )
    parser.add_argument(
        "--report-path",
        default=str(_DEFAULT_REPORT_PATH),
        help="Where to write the machine-readable JSON report.",
    )
    args = parser.parse_args(argv)

    report = run_gate_a(with_live_probes=args.with_live_probes)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = _render_human_summary(report)
    print(summary)
    print(f"\nJSON report: {report_path}")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
