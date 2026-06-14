"""LANE-CI (B23) — status-schema parity gate (I-arch-005 Phase-2/3, umbrella #1257).

PURPOSE
-------
Every terminal status that ``scripts/run_honest_sweep_r3.py`` can write into
``manifest.status`` MUST be a known value in the shared *downstream* registries
that consume that field. A runner status that is unknown downstream is a real
production bug:

  * ``PipelineStatus`` (``src/polaris_v6/schemas/run_status.py``) — the v6 actor
    loads ``manifest.status`` into ``RunStatusResponse.pipeline_status``. A value
    outside the ``Literal`` 500s Pydantic validation on a *real* run, so the UI
    cannot render that terminal at all. The in-code comments call this the
    contract ("must mirror UNIFIED_STATUS_VALUES or RunStatusResponse 500s").
  * ``KNOWN_STATUS_VALUES`` (``src/polaris_graph/audit_ir/regression_lab.py``) —
    the regression lab's named status registry (``frozenset(_STATUS_TIERS)``); an
    unknown status is silently mis-bucketed.

This gate is a **read-only STATIC scan**. It AST-parses ALL THREE source files
(the runner producer set + both downstream registries) and imports NOTHING from
``src/`` or ``scripts/``. Consequences:
  * no pipeline runs, no LLM/network, no heavy retrieval import chain executes;
  * the gate cannot ImportError under a minimal CI dependency set — it needs only
    the stdlib (``ast``) + pytest. This is deliberate: importing
    ``regression_lab`` / the runner would pull the production import chain, the
    exact fragility a CI parity gate must not have.

PRODUCER SET (what can reach ``manifest.status``)
-------------------------------------------------
The producer set is recovered TWO complementary ways, both static:

  1. The *declared* taxonomy: ``UNIFIED_STATUS_VALUES`` ∪
     ``set(_SUMMARY_TO_UNIFIED.values())``. The runner either writes a unified
     value directly (``UNIFIED_STATUS_VALUES``) or routes a legacy
     ``summary["status"]`` label through ``to_unified_status`` (whose codomain is
     exactly the ``_SUMMARY_TO_UNIFIED`` values, defaulting to
     ``error_unexpected`` which is itself in the set). The legacy *keys* are not
     producers — only the mapped *values* land in the manifest — so the declared
     set scans the dict *values*.

  2. The *actual emission sites*: a STATIC AST scan of EVERY literal status the
     runner emits into status-space. Three syntactic forms produce a
     ``manifest.status``, and ALL THREE are scanned (missing any one lets a new
     literal escape both the declared-set parity check and this gate):

       a. plain-Name ``summary_status = "..."`` (the DOMINANT cluster:
          L7918-7972, 882, 8235, 9115, ...) and ``summary["status"] = "..."``;
       b. direct ``<x>manifest["status"] = "..."`` subscript assignment;
       c. DICT-LITERAL construction — ``{"status": "...", ...}`` — however it is
          consumed: a Name-bound manifest dict (``budget_manifest =
          {"status": "abort_budget_exceeded", ...}`` → ``manifest.json``),
          ``manifest.update({"status": "..."})`` / ``abort_manifest.update(...)``,
          or an inline ``write_text(json.dumps({"status": "..."}))``. Caught by an
          ``ast.Dict``-with-``"status"``-key walk so the consumption form is
          irrelevant — the reference ``test_manifest_contract_abort_statuses_are
          _authoritative`` uses the same source-scan-minus-telemetry strategy.

     Every such literal MUST be *registered* (see REGISTRATION below). This is
     what catches a NEW literal status written into the runner WITHOUT being added
     to the declared taxonomy — that literal would otherwise escape the
     declared-set parity check entirely (P1.2: a post-extraction set-union test
     would not bite on real source drift).

  Sweep-level / event telemetry ``"status":`` literals that are NOT manifest
  producers are excluded by a TIGHTLY-SCOPED, documented carve-out (mirrors the
  reference test's exclusion list — NOT a broad allowlist). Each is provably never
  a run ``manifest.status``:
    * ``abort_quota_exceeded`` — written to ``sweep_quota_refusal.json`` (a
      SWEEP-level refusal artifact), never a per-run manifest;
    * ``not_applicable_planner_lane`` — FX-14 custody-lane honesty marker, written
      ONLY to ``custody_lane_status.json``;
    * ``started`` — the in-memory ``summary["status"]`` sentinel / run-start event
      payload, overwritten before every return, never persisted to a manifest.
  A NEW unrecognised dict-literal status is NOT on this list → it bites.

REGISTRATION INVARIANT (what makes a literal "registered")
----------------------------------------------------------
``manifest.status`` is written either directly (a unified value) or via
``to_unified_status(summary_status)``. So:

  * a ``summary`` / ``summary_status`` literal is registered iff it is a KEY of
    ``_SUMMARY_TO_UNIFIED`` (it gets mapped) OR already a member of
    ``UNIFIED_STATUS_VALUES`` (it is written into summary-space as a final unified
    value — e.g. ``summary["status"] = "cancelled"``, which is NOT a map key but
    IS a unified value);
  * a direct ``*manifest["status"]`` literal AND a dict-literal manifest
    ``"status"`` value are registered iff they are members of
    ``UNIFIED_STATUS_VALUES`` (they land in the manifest verbatim).

An UNREGISTERED literal = a status the runner can write that the declared
taxonomy does not know = it would reach ``manifest.status`` (directly, or as the
``error_unexpected`` default of an unmapped ``summary_status``) and could escape
the downstream-parity check. The gate FAILS on it.

ASSUMPTION: the three registries are defined as literal collections
(``frozenset({...})`` / ``{...}`` dict / ``Literal[...]`` / ``frozenset(dict)``).
If a future refactor builds one via a runtime union (e.g. ``frozenset({...}) |
{...}``) the literal extractor would under-read; the ``"success" in extracted``
sanity assert on each set guards the total-failure case, and the gate runs on
every change to these files so a shape change is caught at review time.
"""

from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RUNNER_PATH = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
_RUN_STATUS_PATH = _REPO_ROOT / "src" / "polaris_v6" / "schemas" / "run_status.py"
_REGRESSION_LAB_PATH = _REPO_ROOT / "src" / "polaris_graph" / "audit_ir" / "regression_lab.py"


# ─────────────────────────────────────────────────────────────────────────
# Pure parity logic — (runner_set, downstream_set) -> missing.
# Kept pure (no IO, no import side effects) so the injection tests can prove the
# gate bites WITHOUT touching the real runner file.
# ─────────────────────────────────────────────────────────────────────────
def find_missing_statuses(
    runner_statuses: typing.Iterable[str],
    downstream_statuses: typing.Iterable[str],
) -> set[str]:
    """Return the runner statuses that are NOT present downstream.

    An empty result means parity holds. A non-empty result is real drift = CI
    FAIL. There is NO whitelist/baseline: the registries are reconciled so parity
    is GENUINE, and any new drift surfaces immediately.
    """
    return set(runner_statuses) - set(downstream_statuses)


# ─────────────────────────────────────────────────────────────────────────
# Static (AST) extraction helpers — no module import, pure source read.
# ─────────────────────────────────────────────────────────────────────────
def _str_constants(node: ast.AST | None) -> set[str]:
    """All str-constant elements of a Set / List / Tuple literal node."""
    out: set[str] = set()
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.add(elt.value)
    return out


def _iter_named_assignments(tree: ast.AST):
    """Yield (target_name, value_node) for top-level/`AnnAssign`/`Assign` bindings
    to a single ``Name`` target."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id, node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            yield node.targets[0].id, node.value


def _is_status_subscript(target: ast.AST) -> bool:
    """True for ``<name>["status"]`` where the base name is ``summary`` or ends in
    ``manifest`` (covers ``manifest``, ``_pm_manifest``, ``_ja_manifest``)."""
    if not isinstance(target, ast.Subscript) or not isinstance(target.value, ast.Name):
        return False
    base = target.value.id
    if not (base == "summary" or base == "manifest" or base.endswith("manifest")):
        return False
    sl = target.slice  # py3.9+: index node directly
    return isinstance(sl, ast.Constant) and sl.value == "status"


# Telemetry ``"status":`` dict-literals that are PROVABLY NOT a run manifest.status
# (mirrors the carve-out in tests/.../test_manifest_contract.py — tightly scoped,
# NOT a broad allowlist). A NEW unrecognised dict-literal status is not here → bites.
_TELEMETRY_STATUS_LITERALS: frozenset[str] = frozenset({
    "abort_quota_exceeded",          # sweep_quota_refusal.json — sweep-level, never a run manifest
    "not_applicable_planner_lane",   # custody_lane_status.json — FX-14 custody marker, never a manifest
    "started",                       # in-memory summary sentinel / run-start event — never persisted
})


def _scanned_status_emissions(runner_source: str) -> dict[str, set[str]]:
    """STATIC scan of the runner for the LITERAL statuses it emits into status-
    space, split by destination so the registration invariant can be applied:

      * ``"summary"`` — literals written to ``summary["status"]`` or to a plain
        ``summary_status`` Name (the dominant cluster: L7918-7972, 882, 8235, ...).
        These are mapped through ``to_unified_status`` (or already unified), so the
        registration check allows ``_SUMMARY_TO_UNIFIED`` keys ∪ UNIFIED.
      * ``"manifest"`` — literals that land in the manifest VERBATIM, via either
        (a) a direct ``<x>manifest["status"]`` subscript assignment, OR
        (b) a DICT-LITERAL ``{"status": "...", ...}`` (a Name-bound manifest dict,
            ``manifest.update({...})`` / ``abort_manifest.update({...})``, or an
            inline ``write_text(json.dumps({...}))``). These must be UNIFIED members.

    The dict-literal form is recovered by an ``ast.Dict``-with-``"status"``-key walk
    so the consumption form (assignment / ``.update()`` / ``json.dumps`` arg) does
    not matter. Provable telemetry literals (``_TELEMETRY_STATUS_LITERALS``) are
    excluded — they are written only to sweep/custody/event artifacts, never to a
    run ``manifest.json``.
    """
    tree = ast.parse(runner_source)
    summary_literals: set[str] = set()
    manifest_literals: set[str] = set()

    for node in ast.walk(tree):
        # Form (a)/(summary): str-Constant assigned to a status-space target.
        if isinstance(node, ast.Assign):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literal = value.value
                for target in node.targets:
                    # Plain Name: ``summary_status = "..."`` (dominant cluster).
                    if isinstance(target, ast.Name) and target.id == "summary_status":
                        summary_literals.add(literal)
                    # Subscript: ``summary["status"] = "..."`` / ``*manifest["status"] = "..."``.
                    elif _is_status_subscript(target):
                        base = target.value.id  # type: ignore[union-attr]
                        if base == "summary":
                            summary_literals.add(literal)
                        else:
                            manifest_literals.add(literal)

        # Form (b): a dict literal carrying a ``"status": "<literal>"`` key — a
        # manifest dict construction, regardless of how it is consumed. The
        # telemetry carve-out keeps sweep/custody/event dicts out.
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "status"
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                    and v.value not in _TELEMETRY_STATUS_LITERALS
                ):
                    manifest_literals.add(v.value)

    return {"summary": summary_literals, "manifest": manifest_literals}


def _extract_runner_declared_taxonomy(runner_source: str) -> dict[str, set[str]]:
    """Parse the runner's DECLARED status registries:

      * ``UNIFIED_STATUS_VALUES`` (a ``frozenset({...})`` annotated assign),
      * ``_SUMMARY_TO_UNIFIED`` (a dict) — both its KEYS (legacy labels accepted by
        ``to_unified_status``) and VALUES (what those map to).

    Returns ``{"unified", "summary_keys", "summary_values"}``.
    """
    tree = ast.parse(runner_source)
    unified: set[str] = set()
    summary_keys: set[str] = set()
    summary_values: set[str] = set()

    for name, value in _iter_named_assignments(tree):
        if value is None:
            continue
        if name == "UNIFIED_STATUS_VALUES" and isinstance(value, ast.Call):
            # frozenset({ "a", "b", ... }) — the set literal is the sole arg.
            if value.args:
                unified |= _str_constants(value.args[0])
        if name == "_SUMMARY_TO_UNIFIED" and isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    summary_keys.add(k.value)
            for v in value.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    summary_values.add(v.value)

    return {"unified": unified, "summary_keys": summary_keys, "summary_values": summary_values}


def _extract_runner_status_producers(runner_source: str) -> set[str]:
    """The set of strings that can land in ``manifest.status`` (the DECLARED
    producer set): ``UNIFIED_STATUS_VALUES`` ∪ ``_SUMMARY_TO_UNIFIED`` values."""
    declared = _extract_runner_declared_taxonomy(runner_source)
    return declared["unified"] | declared["summary_values"]


def _find_unregistered_emissions(runner_source: str) -> set[str]:
    """STATIC drift detector: every literal status the runner EMITS into status-
    space must be REGISTERED in the declared taxonomy. Returns the unregistered
    literals (empty == every emission is registered).

    Registration (per the docstring invariant):
      * a ``summary`` literal ∈ (_SUMMARY_TO_UNIFIED keys ∪ UNIFIED_STATUS_VALUES);
      * a direct ``manifest`` literal ∈ UNIFIED_STATUS_VALUES.
    """
    declared = _extract_runner_declared_taxonomy(runner_source)
    unified = declared["unified"]
    summary_registered = declared["summary_keys"] | unified

    emissions = _scanned_status_emissions(runner_source)
    bad: set[str] = set()
    bad |= {s for s in emissions["summary"] if s not in summary_registered}
    bad |= {s for s in emissions["manifest"] if s not in unified}
    return bad


def _extract_pipeline_status_literal(run_status_source: str) -> set[str]:
    """Parse the ``PipelineStatus = Literal["a", "b", ...]`` assignment — a
    ``Subscript`` whose slice is a Tuple of str Constants."""
    tree = ast.parse(run_status_source)
    for name, value in _iter_named_assignments(tree):
        if name != "PipelineStatus" or not isinstance(value, ast.Subscript):
            continue
        sl = value.slice  # py3.9+: the index node directly
        if isinstance(sl, (ast.Tuple, ast.List, ast.Set)):
            return _str_constants(sl)
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return {sl.value}  # single-element Literal
    return set()


def _extract_known_status_values(regression_lab_source: str) -> set[str]:
    """Parse ``KNOWN_STATUS_VALUES = frozenset(_STATUS_TIERS)`` by reading the KEYS
    of the ``_STATUS_TIERS`` dict literal it is derived from."""
    tree = ast.parse(regression_lab_source)
    status_tiers_keys: set[str] = set()
    for name, value in _iter_named_assignments(tree):
        if name == "_STATUS_TIERS" and isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    status_tiers_keys.add(k.value)
    return status_tiers_keys


# ─────────────────────────────────────────────────────────────────────────
# Loaders (read the real files; sanity-assert extraction actually worked).
# ─────────────────────────────────────────────────────────────────────────
def _runner_source() -> str:
    return _RUNNER_PATH.read_text(encoding="utf-8")


def _runner_producer_statuses() -> set[str]:
    producers = _extract_runner_status_producers(_runner_source())
    assert "success" in producers, (
        "AST extraction failed to find runner status producers "
        f"(found {len(producers)}); the runner's UNIFIED_STATUS_VALUES / "
        "_SUMMARY_TO_UNIFIED shape may have changed — update the extractor."
    )
    return producers


def _pipeline_status_values() -> set[str]:
    vals = _extract_pipeline_status_literal(_RUN_STATUS_PATH.read_text(encoding="utf-8"))
    assert "success" in vals, (
        "AST extraction failed to find PipelineStatus Literal members "
        f"(found {len(vals)}); the PipelineStatus = Literal[...] shape in "
        "src/polaris_v6/schemas/run_status.py may have changed — update the extractor."
    )
    return vals


def _known_status_values() -> set[str]:
    vals = _extract_known_status_values(_REGRESSION_LAB_PATH.read_text(encoding="utf-8"))
    assert "success" in vals, (
        "AST extraction failed to find KNOWN_STATUS_VALUES members "
        f"(found {len(vals)}); the _STATUS_TIERS dict shape in "
        "src/polaris_graph/audit_ir/regression_lab.py may have changed — update the extractor."
    )
    return vals


# ─────────────────────────────────────────────────────────────────────────
# Gate tests (the ones CI runs)
# ─────────────────────────────────────────────────────────────────────────
def test_runner_statuses_parity_with_pipeline_status_schema():
    """Every runner-emittable status is known to the v6 ``PipelineStatus`` schema.
    A runner status missing here 500s ``RunStatusResponse`` on a real run — CI
    FAIL. GENUINE parity: no whitelist absorbs the gap."""
    missing = find_missing_statuses(
        _runner_producer_statuses(),
        _pipeline_status_values(),
    )
    assert not missing, (
        "Runner status(es) missing from PipelineStatus "
        f"(src/polaris_v6/schemas/run_status.py): {sorted(missing)}. A manifest.status "
        "outside the PipelineStatus Literal 500s RunStatusResponse on a real run. Add "
        "each value to the PipelineStatus Literal so parity is genuine."
    )


def test_runner_statuses_parity_with_regression_lab_registry():
    """Every runner-emittable status is known to the regression-lab
    ``KNOWN_STATUS_VALUES`` registry. GENUINE parity: no whitelist."""
    missing = find_missing_statuses(
        _runner_producer_statuses(),
        _known_status_values(),
    )
    assert not missing, (
        "Runner status(es) missing from KNOWN_STATUS_VALUES "
        f"(src/polaris_graph/audit_ir/regression_lab.py): {sorted(missing)}. Add each "
        "value to _STATUS_TIERS so parity is genuine."
    )


def test_every_runner_status_emission_site_is_registered():
    """P1.2: STATIC scan of the runner's ACTUAL literal emission sites
    (``summary["status"]`` / ``summary_status`` / ``*manifest["status"]``). Every
    emitted literal MUST be registered in the declared taxonomy — otherwise a new
    literal status written into the runner WITHOUT being added to
    UNIFIED_STATUS_VALUES / _SUMMARY_TO_UNIFIED would escape the parity gate (it
    would reach manifest.status directly or via the error_unexpected default)."""
    unregistered = _find_unregistered_emissions(_runner_source())
    assert not unregistered, (
        "Runner emits literal status(es) NOT registered in the declared taxonomy: "
        f"{sorted(unregistered)}. Add each summary literal as a _SUMMARY_TO_UNIFIED "
        "key (or a UNIFIED_STATUS_VALUES member if written as a final unified value), "
        "and each direct manifest literal to UNIFIED_STATUS_VALUES — otherwise it "
        "escapes the downstream status-schema parity gate."
    )


# ─────────────────────────────────────────────────────────────────────────
# Proof the gate BITES — on the DOWNSTREAM parity check AND on real SOURCE drift.
# (acceptance: "fail if a fake unmapped status is injected")
# ─────────────────────────────────────────────────────────────────────────
def test_gate_bites_on_injected_fake_downstream_drift():
    """Inject a fake status into the runner producer set and assert the parity
    function flags it against BOTH downstream registries. Proves the downstream
    parity check is not a tautology and that real parity holds today (the fake is
    the ONLY thing flagged — every real producer is genuinely present
    downstream, with no whitelist absorbing anything)."""
    fake = "abort_totally_fake_unmapped_status_b23"
    runner = _runner_producer_statuses() | {fake}

    missing_ps = find_missing_statuses(runner, _pipeline_status_values())
    assert missing_ps == {fake}, (
        f"expected ONLY the injected fake missing vs PipelineStatus, got {sorted(missing_ps)} "
        "— a non-empty residual means real (un-whitelisted) drift still exists."
    )

    missing_kn = find_missing_statuses(runner, _known_status_values())
    assert missing_kn == {fake}, (
        f"expected ONLY the injected fake missing vs KNOWN_STATUS_VALUES, got "
        f"{sorted(missing_kn)} — real drift still exists."
    )


def test_emission_scan_bites_on_injected_literal_in_source_text():
    """P1.2 core: the emission scan must catch an UNREGISTERED literal status added
    to the runner SOURCE. We mutate a COPY of the real scanned source text (inject a
    ``summary["status"] = "<fake>"`` line that is in NEITHER _SUMMARY_TO_UNIFIED nor
    UNIFIED_STATUS_VALUES) and re-run the extractor on the mutated text — proving the
    gate bites on REAL source drift, not merely on a post-extraction set union."""
    fake = "abort_brand_new_literal_unregistered_b23"
    real_source = _runner_source()

    # Sanity: the real source is clean (no unregistered emissions) before mutation.
    assert _find_unregistered_emissions(real_source) == set(), (
        "precondition failed: the real runner already emits an unregistered literal "
        f"(found {sorted(_find_unregistered_emissions(real_source))}) — fix that first."
    )

    # Mutate a COPY of the scanned source: append a real emission line with an
    # unregistered literal. (Module level keeps it a top-level ast.Assign.)
    injected_source = real_source + f'\nsummary["status"] = "{fake}"\n'
    unregistered = _find_unregistered_emissions(injected_source)
    assert fake in unregistered, (
        "emission scan did NOT catch an unregistered literal injected into the runner "
        f"source text: {sorted(unregistered)}. The gate would not bite on real source drift."
    )

    # And a direct manifest literal must also be caught.
    injected_manifest = real_source + f'\nmanifest["status"] = "{fake}"\n'
    assert fake in _find_unregistered_emissions(injected_manifest), (
        "emission scan did NOT catch an unregistered direct manifest literal."
    )

    # And the dominant plain-Name form must be caught too.
    injected_name = real_source + f'\nsummary_status = "{fake}"\n'
    assert fake in _find_unregistered_emissions(injected_name), (
        "emission scan did NOT catch an unregistered summary_status Name literal."
    )


def test_emission_scan_bites_on_injected_dict_literal_manifest_status():
    """P1.2 (dict-literal form): a manifest is frequently built as a dict literal
    (``budget_manifest = {"status": "...", ...}``), via ``manifest.update({...})``,
    or inline ``write_text(json.dumps({...}))``. A NEW status added that way must
    NOT escape the scan just because the value is inside a dict literal rather than
    a Constant-valued assignment. Mutate a COPY of the source with each form and
    assert the scan bites."""
    fake = "abort_dict_literal_unregistered_b23"
    real_source = _runner_source()
    assert _find_unregistered_emissions(real_source) == set(), "precondition: source clean"

    # (a) Name-bound manifest dict literal written to manifest.json.
    inj_assign = real_source + (
        f'\nbudget_manifest = {{"status": "{fake}", "cost_usd": 0.0}}\n'
        '(run_dir / "manifest.json").write_text(json.dumps(budget_manifest))\n'
    )
    assert fake in _find_unregistered_emissions(inj_assign), (
        "emission scan did NOT catch an unregistered Name-bound manifest dict-literal status."
    )

    # (b) manifest.update({...}) call form.
    inj_update = real_source + f'\nmanifest.update({{"status": "{fake}"}})\n'
    assert fake in _find_unregistered_emissions(inj_update), (
        "emission scan did NOT catch an unregistered manifest.update({...}) status."
    )

    # (c) inline write_text(json.dumps({...})) form.
    inj_inline = real_source + (
        f'\n(run_dir / "manifest.json").write_text(json.dumps({{"status": "{fake}"}}))\n'
    )
    assert fake in _find_unregistered_emissions(inj_inline), (
        "emission scan did NOT catch an unregistered inline json.dumps manifest status."
    )


def test_emission_scan_allows_unified_value_written_to_summary_space():
    """Registration must NOT false-fail on a UNIFIED value written directly into
    summary-space (``summary["status"] = "cancelled"`` — NOT a _SUMMARY_TO_UNIFIED
    key, but a valid unified terminal). This is the real case (runner L2791) that
    separates a correct invariant from one that passes synthetics but breaks on
    real source."""
    real_source = _runner_source()
    emissions = _scanned_status_emissions(real_source)
    assert "cancelled" in emissions["summary"], (
        "expected the real runner's summary[\"status\"] = \"cancelled\" emission to be "
        "scanned — if not, the scan missed a real emission site."
    )
    # It is a unified value (not a map key), and the real source must stay clean.
    assert _find_unregistered_emissions(real_source) == set()


def test_emission_scan_excludes_sweep_telemetry_status_literals():
    """Sweep-level telemetry ``"status":`` dict-literals (``abort_quota_exceeded``
    in the sweep refusal summary, ``not_applicable_planner_lane`` custody-marker
    return, ``started`` event payload) are NOT treated as manifest producers — they
    are written only to sweep/custody/event artifacts, never to a run manifest.
    Confirms the tightly-scoped carve-out keeps false-positives out."""
    emissions = _scanned_status_emissions(_runner_source())
    scanned = emissions["summary"] | emissions["manifest"]
    for telemetry in ("abort_quota_exceeded", "not_applicable_planner_lane", "started"):
        assert telemetry not in scanned, (
            f"{telemetry!r} is sweep/event telemetry, not a manifest.status producer, "
            "but the emission scan picked it up — extend _TELEMETRY_STATUS_LITERALS."
        )


def test_emission_scan_captures_real_dict_literal_manifest_aborts():
    """The dict-literal abort manifest writes that exist in the runner TODAY
    (``manifest.update({"status": "abort_corpus_inadequate"})`` etc., and the
    Name-bound ``budget_manifest = {"status": "abort_budget_exceeded", ...}``) MUST
    be scanned as manifest producers — proving the dict-literal form is actually
    covered, not just exercised by synthetic injections. All are registered (in
    UNIFIED), so the source stays clean."""
    emissions = _scanned_status_emissions(_runner_source())
    for real_abort in (
        "abort_corpus_inadequate",
        "abort_corpus_approval_denied",
        "abort_budget_exceeded",
        "abort_conflict_judge_unavailable",
    ):
        assert real_abort in emissions["manifest"], (
            f"{real_abort!r} is written as a dict-literal manifest status in the runner "
            "but the emission scan missed it — the dict-literal form is not covered."
        )
    # And every one of them is registered, so the real source has zero unregistered.
    assert _find_unregistered_emissions(_runner_source()) == set()


def test_find_missing_statuses_pure_semantics():
    """Unit-cover the pure parity function: present-downstream passes, genuinely-
    missing surfaces, no whitelist."""
    assert find_missing_statuses({"a", "b"}, {"a"}) == {"b"}
    assert find_missing_statuses({"a"}, {"a", "z"}) == set()
    assert find_missing_statuses({"x", "y"}, set()) == {"x", "y"}


def test_static_scan_imports_nothing_from_src_or_scripts():
    """The gate must stay a pure static scan: this module imports nothing from
    ``src`` or ``scripts`` (so it cannot ImportError under minimal CI deps and runs
    no pipeline). Asserted against this file's own import statements."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.split(".")[0] in {"src", "scripts"}]
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in {"src", "scripts"}:
                bad.append(node.module or "")
    assert not bad, f"gate must not import from src/scripts (static-scan invariant): {bad}"


if __name__ == "__main__":  # pragma: no cover - manual invocation aid
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
