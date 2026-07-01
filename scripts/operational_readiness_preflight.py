#!/usr/bin/env python3
"""Operational-readiness preflight (the "will it die from a stupid mistake" check).

WHY THIS EXISTS (the I-arch-005 lesson)
---------------------------------------
``scripts/pipeline_diced_preflight.py`` checks the pipeline-STAGE §-1.3 invariants (weight-not-
filter / consolidate-not-drop / basket-faithfulness) against a banked corpus_snapshot. This harness
checks the OTHER failure class — the boring run-CONFIG settings that SILENTLY KILL a paid run before a
single useful token is produced:

  * committed + Codex-approved != WIRED on the run path (I-arch-005): a fix that is real in the tree
    but DEAD because the flag that activates it is default-off and only the Gate-B slate turns it on.
    A direct ``run_honest_sweep_r3.py`` WITHOUT ``--pathB-gate`` never applies the slate -> the breadth
    enrichment is OFF -> a narrow report.
  * a token budget starved below need -> the generator/judge truncates mid-write -> empty/collapsed.
  * a timeout ordered wrong -> a healthy section is guillotined mid-write, or the 4-role seam tears.
  * a §-1.3-BANNED cap pinned ON -> the funnel silently re-asserts and breadth collapses.
  * a silent degrade (credibility tiering / relevance-gate demote) NOT disclosed to the manifest.

THE RUN CONFIG SOURCE OF TRUTH (read, never re-declared) + THE CANONICAL LAUNCH PATH
------------------------------------------------------------------------------------
The paid run's ONLY slate-applying entrypoint is ``scripts/dr_benchmark/run_gate_b.py`` (launched
DIRECTLY: ``python scripts/dr_benchmark/run_gate_b.py --only <slug> [--resume]``). Its ``main()`` and
``run_gate_b_query`` call ``apply_full_capability_benchmark_slate`` (force/floor) + ``enable_four_role_mode``.
DO NOT launch the paid run via ``scripts/run_honest_sweep_r3.py --pathB-gate``: that wrapper
(``pathB_runner.gate_around_question``) is a capture/preflight gate ONLY — it does NOT apply the slate,
so ``PG_BREADTH_ENRICHMENT_ENABLED`` (and the rest of the slate) stays default-OFF -> a NARROW report.
The D-1 launch-path check verifies the slate IS applied by run_gate_b.py and discloses this loudly.

This preflight IMPORTS run_gate_b's real constants (``_FULL_CAPABILITY_BENCHMARK_SLATE``, the
force-on / force-exact / required flag sets, ``benchmark_verifier_lineup``, ``load_lock``,
``assert_four_role_families_distinct``) and re-derives the EFFECTIVE config the SAME way the run will —
a faithful READ-ONLY replica of ``apply_full_capability_benchmark_slate``'s FORCE / FLOOR / setdefault
semantics. It NEVER re-hardcodes a value (that would be exactly the drift the preflight exists to catch).
It reads the .env-merged env WHILE resolving (fidelity) but SNAPSHOTS + RESTORES ``os.environ`` around
the run_gate_b import so the process env is left BYTE-IDENTICAL — that import transitively runs
``load_dotenv`` AND ``src/_polaris_native_thread_safety.apply_native_thread_safety_clamp`` (os.environ
.setdefault of the native thread-pool knobs), both of which would otherwise mutate the env. It loads NO
model and makes NO paid LLM call.

BUILD-ONLY / NO SPEND
---------------------
The ONLY network this harness performs is a FREE, UNAUTHENTICATED ``GET`` to the OpenRouter catalog
(``/api/v1/models`` + ``/api/v1/models/{slug}/endpoints``) to confirm each role's slug is served and the
Judge has enough providers (anti-429). That GET bills nothing. It is OPT-OUT (``--no-ping``) and degrades
to ``LIVE-PENDING`` (never RED, never a harness error) on any network failure. NOTHING here launches a
heavy run, loads a model, or makes a completion call.

STATIC vs LIVE-PING (honest labelling)
--------------------------------------
Each check is labelled ``STATIC`` (provable from config alone, deterministic) or ``LIVE-PING`` (only a
live probe can confirm it — the ``/models`` reachability + provider count, and the 4-role seam under
load). The overall GO/NO-GO is driven by the RED set; a ``LIVE-PENDING`` (could-not-confirm-live) never
forces NO-GO unless ``--require-live-ping`` is passed.

LAW VI: every threshold + expected value is an env var (``PG_OPREADY_*``) or a CLI arg. No magic numbers.

Usage
-----
    python scripts/operational_readiness_preflight.py                 # static + free /models ping + diced shell
    python scripts/operational_readiness_preflight.py --no-ping       # static only (no network)
    python scripts/operational_readiness_preflight.py --no-diced      # skip the diced-preflight shell-out
    python scripts/operational_readiness_preflight.py --json out.json  # machine-readable sidecar
    python scripts/operational_readiness_preflight.py --require-live-ping  # an unreachable /models ping => NO-GO

Exit code: 0 == GO (no RED), 1 == NO-GO (>=1 RED), 2 == harness error.
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Mapping, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Put the repo root on sys.path so `import scripts.dr_benchmark.run_gate_b` + `import src.polaris_graph...`
# resolve when this harness is run directly as `python scripts/operational_readiness_preflight.py` from a
# plain shell (where only the script's own dir is on the path, not the repo root). Without this the
# harness dies with ModuleNotFoundError — ironic for a "will it die" check.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_DICED_PREFLIGHT = _REPO_ROOT / "scripts" / "pipeline_diced_preflight.py"
# The honest_sweep --pathB-gate wrapper (read READ-ONLY via AST; never imported) — the launch-path
# check confirms it does NOT apply the slate, so the paid run must launch via run_gate_b.py instead.
_PATHB_RUNNER = _REPO_ROOT / "src" / "polaris_graph" / "benchmark" / "pathB_runner.py"

GREEN = "GREEN"
RED = "RED"
PENDING = "LIVE-PENDING"
INFO = "INFO"            # an input surfaced for the operator; never gates the GO/NO-GO verdict

STATIC = "STATIC"
LIVE = "LIVE-PING"

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("", "0", "false", "no", "off")


# --------------------------------------------------------------------------------------------
# env helpers (LAW VI)
# --------------------------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUTHY


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in _TRUTHY if value is not None else False


def _to_int(value: object) -> Optional[int]:
    """Best-effort int (the run reads these knobs as ints); None when un-parseable."""
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


@contextlib.contextmanager
def _process_env_byte_identical() -> Iterator[None]:
    """Leave ``os.environ`` BYTE-IDENTICAL across the wrapped block (the harness's READ-ONLY
    contract). Importing ``scripts.dr_benchmark.run_gate_b`` transitively runs
    ``load_dotenv(override=False)`` (merges ``.env``) AND
    ``src/_polaris_native_thread_safety.apply_native_thread_safety_clamp()`` (``os.environ.setdefault``
    of TOKENIZERS_PARALLELISM / OMP_NUM_THREADS / MKL_NUM_THREADS / OPENBLAS_NUM_THREADS /
    NUMEXPR_NUM_THREADS) — both MUTATE the process env. We snapshot on entry and restore on exit so a
    faithful replica may READ the .env-merged env WHILE inside, then leaves the process env exactly as
    found. Minimal-diff restore (drop import-added keys, re-set changed/removed ones) so there is never
    a transient empty-env window."""
    snapshot = dict(os.environ)
    try:
        yield
    finally:
        for key in [k for k in os.environ if k not in snapshot]:
            del os.environ[key]
        for key, value in snapshot.items():
            if os.environ.get(key) != value:
                os.environ[key] = value


def _source_calls(source: str, func_name: Optional[str], target_name: str) -> bool:
    """True iff ``source`` contains a REAL AST ``Call`` to a function named ``target_name`` — NOT a
    mere substring inside a comment/docstring/string literal (the P2 fix: a substring check
    false-passes on a commented-out call). When ``func_name`` is given, search ONLY inside that
    function's body; otherwise search the whole snippet. Used to verify wiring structurally
    (``enable_four_role_mode`` / ``apply_full_capability_benchmark_slate``)."""
    import ast  # noqa: PLC0415
    import textwrap  # noqa: PLC0415

    try:
        tree = ast.parse(textwrap.dedent(source))
    except (SyntaxError, ValueError):
        return False
    scope: Optional[ast.AST] = tree
    if func_name is not None:
        scope = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                scope = node
                break
        if scope is None:
            return False
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name == target_name:
                return True
    return False


# --------------------------------------------------------------------------------------------
# Documented CODE defaults for the per-role token knobs the SLATE does NOT pin (so a regression
# that lowers one is caught). Each is the value the run reads via os.getenv(<knob>, <default>) —
# sourced READ-ONLY here so the floor check resolves the SAME effective value the run would.
#   PG_D8_VERDICT_MAX_TOKENS                openrouter_role_transport.py:1393  (Judge verdict)
#   PG_MIRROR_MAX_TOKENS                    openrouter_role_transport.py:1364  (Mirror)
#   PG_SENTINEL_DECOMPOSITION_MAX_TOKENS    openrouter_role_transport.py:1332  (Sentinel decomposition)
#   PG_ENTAILMENT_MAX_TOKENS                entailment_judge.py:183/184        (NLI side-judge)
# --------------------------------------------------------------------------------------------
_CODE_DEFAULT_TOKENS: dict[str, int] = {
    "PG_D8_VERDICT_MAX_TOKENS": 16384,
    "PG_MIRROR_MAX_TOKENS": 131072,
    "PG_SENTINEL_DECOMPOSITION_MAX_TOKENS": 131072,
    "PG_ENTAILMENT_MAX_TOKENS": 131072,
}


# --------------------------------------------------------------------------------------------
# Env-tunable thresholds + expected values (LAW VI). Defaults match the operator-locked slate /
# §9.1.8 token governance / the I-judge-kimi anti-429 provider floor.
# --------------------------------------------------------------------------------------------

@dataclass
class Thresholds:
    # D-2 expected slugs (operator lock + benchmark lineup)
    expect_generator: str = field(default_factory=lambda: _env_str("PG_OPREADY_EXPECT_GENERATOR", "z-ai/glm-5.2"))
    expect_mirror: str = field(default_factory=lambda: _env_str("PG_OPREADY_EXPECT_MIRROR", "z-ai/glm-5.2"))
    expect_sentinel: str = field(default_factory=lambda: _env_str("PG_OPREADY_EXPECT_SENTINEL", "minimax/minimax-m2"))
    expect_judge: str = field(default_factory=lambda: _env_str("PG_OPREADY_EXPECT_JUDGE", "moonshotai/kimi-k2.6"))
    judge_min_providers: int = field(default_factory=lambda: _env_int("PG_OPREADY_JUDGE_MIN_PROVIDERS", 15))
    # D-3 token floors (§9.1.8: never starve)
    generator_token_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_GENERATOR_TOKEN_FLOOR", 64000))
    judge_token_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_JUDGE_TOKEN_FLOOR", 16384))
    mirror_token_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_MIRROR_TOKEN_FLOOR", 131072))
    sentinel_token_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_SENTINEL_TOKEN_FLOOR", 131072))
    sidejudge_token_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_SIDEJUDGE_TOKEN_FLOOR", 131072))
    # D-4 seam floor (raised for the big/slow kimi judge)
    seam_floor_seconds: int = field(default_factory=lambda: _env_int("PG_OPREADY_SEAM_FLOOR_SECONDS", 1800))
    # D-5 caps
    fetch_cap_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_FETCH_CAP_FLOOR", 200))
    gen_pool_floor: int = field(default_factory=lambda: _env_int("PG_OPREADY_GEN_POOL_FLOOR", 1500))
    # ping
    ping_base_url: str = field(default_factory=lambda: _env_str("PG_OPREADY_OPENROUTER_BASE", "https://openrouter.ai/api/v1"))
    ping_timeout_seconds: int = field(default_factory=lambda: _env_int("PG_OPREADY_PING_TIMEOUT", 12))
    diced_timeout_seconds: int = field(default_factory=lambda: _env_int("PG_OPREADY_DICED_TIMEOUT", 180))


@dataclass
class CheckResult:
    check_id: str          # D-1 .. D-6 (with a sub-suffix per assertion)
    what: str
    status: str            # GREEN | RED | LIVE-PENDING
    static_or_live: str    # STATIC | LIVE-PING
    detail: str

    @property
    def is_red(self) -> bool:
        return self.status == RED

    @property
    def is_pending(self) -> bool:
        return self.status == PENDING

    @property
    def is_info(self) -> bool:
        return self.status == INFO


def _ok(check_id: str, what: str, ok: bool, static_or_live: str, detail: str) -> CheckResult:
    return CheckResult(check_id, what, GREEN if ok else RED, static_or_live, detail)


# --------------------------------------------------------------------------------------------
# Run-config source of truth — imported from run_gate_b (NEVER re-declared here).
# --------------------------------------------------------------------------------------------

@dataclass
class SlateMeta:
    slate: dict
    force_on: frozenset
    force_exact: frozenset
    required: tuple
    required_off: tuple


def load_slate_meta() -> SlateMeta:
    """Import the Gate-B run-config constants (the SAME objects the run uses). Lightweight import —
    measured ~0.5s, loads ZERO heavy/model modules (verified) — and makes NO network call."""
    import scripts.dr_benchmark.run_gate_b as rg  # noqa: PLC0415

    return SlateMeta(
        slate=dict(rg._FULL_CAPABILITY_BENCHMARK_SLATE),
        force_on=frozenset(rg._BENCHMARK_FORCE_ON_FLAGS),
        force_exact=frozenset(rg._BENCHMARK_FORCE_EXACT_FLAGS),
        required=tuple(rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS),
        required_off=tuple(rg._BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS),
    )


def resolve_effective_config(env: Mapping[str, str], meta: SlateMeta) -> dict[str, str]:
    """READ-ONLY replica of ``apply_full_capability_benchmark_slate``'s env mutation (run_gate_b.py
    :2333-2341). For each slate key: force-on / force-exact -> the exact slate value; otherwise a
    numeric FLOOR -> ``max(env-or-slate, slate)``. Non-slate keys carry through from ``env`` unchanged.
    This is the EFFECTIVE config the --pathB-gate run will have AFTER the slate runs. Pure function —
    never writes ``os.environ`` (the source apply() does; this one must not, it is a preflight)."""
    eff: dict[str, str] = dict(env)
    for name, value in meta.slate.items():
        if name in meta.force_on or name in meta.force_exact:
            eff[name] = value                              # force exact value (run_gate_b.py:2335)
            continue
        try:
            current = float(env.get(name, value))
            eff[name] = str(int(max(current, float(value))))   # FLOOR: raise-to-slate, keep-if-higher
        except (TypeError, ValueError):
            # P1 resolver-fidelity: mirror apply()'s except branch (run_gate_b.py:2337-2341). On a
            # MALFORMED numeric env, production sets ``current = float(value)`` then writes
            # ``str(int(max(current, float(value))))`` == the FLOORED SLATE value — NOT the raw env
            # string. Replicate that so the preflight cannot false-RED a run that production would
            # floor-correct. A genuinely non-numeric SLATE value (which production's float(value)
            # would itself crash on, but a preflight must never crash) carries through unchanged.
            try:
                eff[name] = str(int(float(value)))
            except (TypeError, ValueError):
                eff[name] = env.get(name, value)
    return eff


def resolve_generator_slug(env: Mapping[str, str], lock: dict) -> str:
    """The generator runs upstream on OpenRouter via openrouter_client (PG_GENERATOR_MODEL >
    OPENROUTER_DEFAULT_MODEL > lock default) — mirrors pathB_runner + the family-guard precedence."""
    return (
        env.get("PG_GENERATOR_MODEL")
        or env.get("OPENROUTER_DEFAULT_MODEL")
        or str(lock["required_roles"]["generator"]["model_slug"])
    )


# --------------------------------------------------------------------------------------------
# D-1 — FLAGS ON / WIRED
# --------------------------------------------------------------------------------------------

def check_d1_flags(
    cfg: Mapping[str, str],
    raw_env: Mapping[str, str],
    meta: SlateMeta,
    four_role_mode_wired: bool,
) -> list[CheckResult]:
    out: list[CheckResult] = []
    # The breadth/quality flags the slate force-pins ON. GREEN requires BOTH effective-truthy AND a
    # force-pin (force-on / force-exact / required / numeric-floor) so a stray operator =0 cannot win.
    pinned = {
        "PG_BREADTH_ENRICHMENT_ENABLED": "breadth weighted-enrichment surface (the 485->~13 funnel fix)",
        "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS": "FIX-K: render the surfaced basket's VERIFIED spans verbatim",
        "PG_RETRIEVAL_RELEVANCE_GATE": "B4 relevance gate (weight-not-filter demote-not-drop)",
        # I-deepfix-001 (#1344) WS-2: the two remaining winner flags the paid run must NOT launch with OFF.
        # This turns the D-1 launch-path INFO disclosure (a paid run that skips the slate leaves these
        # default-OFF -> zero consolidation / zero analysis) into a HARD RED assert on the paid path. The
        # real Gate-B slate force-pins + preflight-requires both, so a slate-applied run is GREEN; a
        # slate-OFF (or --pathB-gate) launch RED-gates -> NO-GO.
        "PG_CONSOLIDATION_NLI": "W10 consolidate=NLI (same-claim paraphrase baskets -> multi-source corroboration)",
        "PG_CROSS_SOURCE_SYNTHESIS": "M6 cross-source analytical layer (the Comparative-Assessment analysis yield)",
        "PG_FOUR_ROLE_MODE": "the native 4-role D8 verification seam",
    }
    for flag, why in pinned.items():
        if flag == "PG_FOUR_ROLE_MODE":
            # NOT a slate key — wired by enable_four_role_mode() on the --pathB-gate entry (it force-
            # sets os.environ['PG_FOUR_ROLE_MODE']='1' unconditionally, run_gate_b.py:241-247).
            ok = four_role_mode_wired
            detail = (
                f"set by enable_four_role_mode() on the --pathB-gate entry (code-wired, force-set '1', "
                f"NOT a slate key) -> {'WIRED' if ok else 'NOT wired on the run path'}; "
                f"a direct run_honest_sweep_r3.py without --pathB-gate would NOT enable it"
            )
            out.append(CheckResult("D-1." + flag, why, GREEN if ok else RED, STATIC, detail))
            continue
        eff = cfg.get(flag)
        force_on = flag in meta.force_on
        force_exact = flag in meta.force_exact
        required = flag in meta.required
        in_slate = flag in meta.slate
        # I-deepfix-001 (#1344) WS-2: only RED-gate a pinned winner flag that THIS slate-meta actually
        # governs (in the slate or a force/required set). A meta with no knowledge of the flag (a synthetic
        # unit-test meta, or a pre-M6 slate) must not spuriously RED it — the real Gate-B slate governs all
        # of these, so the paid readiness run still hard-REDs a genuine slate-OFF launch.
        if not (in_slate or force_on or force_exact or required):
            continue
        # the numeric FLOOR guarantees a truthy "1" even on a stray =0 (max(0,1)=1) for slate keys.
        floor_guards = in_slate and not (force_on or force_exact)
        guaranteed = force_on or force_exact or required or floor_guards
        ok = _truthy(eff) and guaranteed
        detail = (
            f"effective={eff!r} (force_on={force_on} force_exact={force_exact} required={required} "
            f"slate_floor_guards={floor_guards}) -> "
            f"{'ON + force-pinned (a stray operator =0 cannot disable it)' if ok else 'NOT guaranteed-ON'}; "
            f"{why}. WITHOUT the --pathB-gate slate this defaults OFF (narrow report)."
        )
        out.append(CheckResult("D-1." + flag, why, GREEN if ok else RED, STATIC, detail))

    # PG_SCOPE_TOPIC_GATE_HARD_DROP must NOT be set truthy — it re-arms the §-1.3-banned scope
    # hard-filter. It is NOT a slate key, so it survives from the operator env if set.
    topic = raw_env.get("PG_SCOPE_TOPIC_GATE_HARD_DROP")
    topic_ok = not _truthy(topic)
    out.append(CheckResult(
        "D-1.PG_SCOPE_TOPIC_GATE_HARD_DROP",
        "the §-1.3-banned scope topic-gate hard-drop escape hatch is UNSET",
        GREEN if topic_ok else RED, STATIC,
        f"PG_SCOPE_TOPIC_GATE_HARD_DROP={topic!r} -> "
        f"{'unset/falsey (weight-not-filter holds)' if topic_ok else 'TRUTHY: re-arms the banned hard-filter'}",
    ))
    return out


def check_d1_launch_path(rg) -> list[CheckResult]:
    """D-1 LAUNCH PATH — the slate (incl. PG_BREADTH_ENRICHMENT_ENABLED) is applied ONLY by
    ``run_gate_b.py``'s ``main()`` + ``run_gate_b_query`` (``apply_full_capability_benchmark_slate``).
    ``run_honest_sweep_r3.py --pathB-gate`` wraps ``run_one_query`` in ``pathB_runner.gate_around_question``
    — a capture/preflight gate that does NOT apply the slate — so launching the paid run that way leaves
    every slate flag default-OFF (breadth OFF) -> a NARROW report. This RED-gates the regression where
    the canonical entrypoint stops applying the slate, and DISCLOSES (INFO) the correct launch command."""
    out: list[CheckResult] = []

    # (1) GATING: the canonical paid entrypoint applies the slate (AST call-node check, not a substring).
    try:
        main_applies = _source_calls(inspect.getsource(rg.main), None, "apply_full_capability_benchmark_slate")
        query_applies = _source_calls(
            inspect.getsource(rg.run_gate_b_query), None, "apply_full_capability_benchmark_slate"
        )
    except (OSError, TypeError):
        main_applies = query_applies = False
    slate_applied = main_applies and query_applies
    out.append(CheckResult(
        "D-1.launch_path.slate_applied",
        "the FULL slate is applied by the canonical entrypoint run_gate_b.py (main + run_gate_b_query)",
        GREEN if slate_applied else RED, STATIC,
        f"run_gate_b.main calls apply_full_capability_benchmark_slate={main_applies}; "
        f"run_gate_b_query calls it={query_applies} -> "
        + ("LAUNCH VIA run_gate_b.py --only <slug> [--resume] (applies the slate incl "
           "PG_BREADTH_ENRICHMENT_ENABLED); run_honest_sweep_r3.py --pathB-gate does NOT apply the "
           "slate -> breadth OFF" if slate_applied
           else "REGRESSION: the canonical paid entrypoint no longer applies the slate -> breadth OFF"),
    ))

    # (2) DISCLOSURE (INFO, never gates): --pathB-gate skips the slate. Read pathB_runner.py READ-ONLY
    # via AST (never imported -> no heavy deps, no env mutation).
    applies = enables = False
    if _PATHB_RUNNER.is_file():
        try:
            src = _PATHB_RUNNER.read_text(encoding="utf-8")
            applies = _source_calls(src, "gate_around_question", "apply_full_capability_benchmark_slate")
            enables = _source_calls(src, "gate_around_question", "enable_four_role_mode")
            src_note = f"gate_around_question applies_slate={applies} enables_four_role={enables}"
        except OSError as exc:
            src_note = f"could not read {_PATHB_RUNNER.name}: {exc}"
    else:
        src_note = f"{_PATHB_RUNNER.name} not found (cannot confirm the --pathB-gate path statically)"
    out.append(CheckResult(
        "D-1.launch_path.pathB_gate_skips_slate",
        "DISCLOSURE: run_honest_sweep_r3.py --pathB-gate does NOT apply the slate (breadth OFF)",
        INFO, STATIC,
        f"{src_note} -> LAUNCH VIA run_gate_b.py (applies the slate); "
        f"run_honest_sweep_r3.py --pathB-gate wraps run_one_query in gate_around_question which does "
        f"NOT apply_full_capability_benchmark_slate / enable_four_role_mode -> "
        f"PG_BREADTH_ENRICHMENT_ENABLED stays default-OFF -> NARROW report. Do NOT launch the paid run "
        f"via --pathB-gate.",
    ))
    return out


# --------------------------------------------------------------------------------------------
# D-2 — MODELS RIGHT + REACHABLE
# --------------------------------------------------------------------------------------------

def check_d2_models_static(
    lineup: Mapping[str, str],
    generator_slug: str,
    lock: dict,
    families: Optional[dict],
    families_error: Optional[str],
    th: Thresholds,
) -> list[CheckResult]:
    out: list[CheckResult] = []
    expected = {
        "generator": th.expect_generator,
        "mirror": th.expect_mirror,
        "sentinel": th.expect_sentinel,
        "judge": th.expect_judge,
    }
    active = {
        "generator": generator_slug,
        "mirror": lineup.get("mirror"),
        "sentinel": lineup.get("sentinel"),
        "judge": lineup.get("judge"),
    }
    for role in ("generator", "mirror", "sentinel", "judge"):
        ok = active[role] == expected[role]
        out.append(_ok(
            f"D-2.model.{role}", f"{role} slug == operator-expected", ok, STATIC,
            f"active={active[role]!r} expected={expected[role]!r} -> {'MATCH' if ok else 'MISMATCH'}",
        ))

    # Cross-check the GENERATOR against the runtime lock (verify_lock asserts code default == lock).
    lock_gen = str(lock["required_roles"]["generator"]["model_slug"])
    gen_lock_ok = lock_gen == th.expect_generator == generator_slug
    out.append(_ok(
        "D-2.lock.generator", "generator pinned by the runtime lock", gen_lock_ok, STATIC,
        f"lock.required_roles.generator.model_slug={lock_gen!r}; active={generator_slug!r}; "
        f"expected={th.expect_generator!r} -> {'LOCK-PINNED' if gen_lock_ok else 'DRIFT vs lock'}",
    ))
    # The benchmark verifier lineup INTENTIONALLY diverges from the lock's sovereign self-host slugs
    # for mirror/sentinel/judge (documented benchmark-vs-lock divergence). Surface it, do not RED it.
    lock_judge = str(lock["required_roles"]["judge"]["model_slug"])
    out.append(CheckResult(
        "D-2.lock.divergence",
        "benchmark-vs-lock judge divergence is the documented/intentional one",
        GREEN, STATIC,
        f"lock judge.model_slug={lock_judge!r} (sovereign, pending operator-signed reconciliation) vs "
        f"benchmark judge={active['judge']!r} (I-judge-kimi anti-429) — INTENTIONAL, not drift",
    ))

    # 4-distinct-family invariant (CLAUDE.md §9.1) over the ACTIVE transport, honoring allowed_collisions.
    if families_error is not None:
        out.append(CheckResult(
            "D-2.families", "4-role family lineages distinct (no self-verify collision)",
            RED, STATIC, f"assert_four_role_families_distinct() RAISED: {families_error}",
        ))
    else:
        out.append(_ok(
            "D-2.families", "4-role family lineages distinct (no self-verify collision)",
            True, STATIC,
            f"families={families} (allowed_collisions honored: gen+mirror share the glm lane by "
            f"operator-approved relaxation; sentinel + judge independent)",
        ))
    return out


def ping_openrouter_catalog(slugs: Mapping[str, str], judge_slug: str, th: Thresholds) -> dict:
    """FREE unauthenticated GET against the OpenRouter catalog — NO spend, NO completion. Returns a
    structured result; ANY network/parse failure -> {'reachable': False, ...} (degrades, never raises)."""
    result: dict = {"reachable": False, "served": {}, "judge_providers": None, "error": None}
    try:
        import httpx  # noqa: PLC0415

        base = th.ping_base_url.rstrip("/")
        with httpx.Client(timeout=th.ping_timeout_seconds) as client:
            resp = client.get(f"{base}/models")
            resp.raise_for_status()
            data = resp.json().get("data")
            if not isinstance(data, list):
                raise ValueError("/models body has no `data` list")
            catalog: set[str] = set()
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                for key in ("id", "canonical_slug"):
                    val = entry.get(key)
                    if val:
                        catalog.add(val)
            result["served"] = {role: (slug in catalog) for role, slug in slugs.items()}
            # provider count for the Judge (anti-429) = len of /models/{slug}/endpoints.
            ep = client.get(f"{base}/models/{judge_slug}/endpoints")
            ep.raise_for_status()
            ep_data = ep.json().get("data")
            endpoints = ep_data.get("endpoints") if isinstance(ep_data, dict) else None
            if isinstance(endpoints, list):
                result["judge_providers"] = len(endpoints)
            result["reachable"] = True
    except Exception as exc:  # noqa: BLE001 — any failure degrades to LIVE-PENDING, never RED/harness-error
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def check_d2_models_live(
    ping: dict, slugs: Mapping[str, str], judge_slug: str, th: Thresholds, require_live: bool,
) -> list[CheckResult]:
    out: list[CheckResult] = []
    if not ping.get("reachable"):
        status = RED if require_live else PENDING
        note = "" if require_live else " (does not force NO-GO unless --require-live-ping)"
        out.append(CheckResult(
            "D-2.ping", "OpenRouter /models reachability + per-role presence", status, LIVE,
            f"catalog GET unreachable: {ping.get('error')}{note}; re-run on the run host to confirm "
            f"each slug is served + judge providers >= {th.judge_min_providers}",
        ))
        return out
    served = ping.get("served", {})
    for role, slug in slugs.items():
        present = bool(served.get(role))
        out.append(_ok(
            f"D-2.ping.served.{role}", f"{role} slug served by OpenRouter", present, LIVE,
            f"slug={slug!r} served={present}",
        ))
    judge_providers = ping.get("judge_providers")
    if judge_providers is None:
        out.append(CheckResult(
            "D-2.ping.judge_providers", "Judge provider count (anti-429)", PENDING, LIVE,
            f"could not read /models/{judge_slug}/endpoints count; re-probe on the run host",
        ))
    else:
        ok = judge_providers >= th.judge_min_providers
        out.append(_ok(
            "D-2.ping.judge_providers",
            f"Judge served by >= {th.judge_min_providers} providers (anti-429 seam-tear guard)",
            ok, LIVE,
            f"judge={judge_slug!r} providers={judge_providers} (min {th.judge_min_providers}) -> "
            f"{'enough to spread the per-claim burst' if ok else 'TOO FEW -> 429 storm tears the D8 seam'}",
        ))
    return out


# --------------------------------------------------------------------------------------------
# D-3 — TOKENS NOT STARVED (§9.1.8)
# --------------------------------------------------------------------------------------------

def _effective_token(cfg: Mapping[str, str], knob: str) -> Optional[int]:
    """The effective token budget the run reads: the resolved cfg value if present (env override or
    slate floor), else the documented code default."""
    if knob in cfg:
        return _to_int(cfg.get(knob))
    return _CODE_DEFAULT_TOKENS.get(knob)


def check_d3_tokens(cfg: Mapping[str, str], th: Thresholds) -> list[CheckResult]:
    specs = [
        ("generator", "PG_SECTION_MAX_TOKENS", th.generator_token_floor),
        ("judge (D8 verdict)", "PG_D8_VERDICT_MAX_TOKENS", th.judge_token_floor),
        ("mirror", "PG_MIRROR_MAX_TOKENS", th.mirror_token_floor),
        ("sentinel (decomposition)", "PG_SENTINEL_DECOMPOSITION_MAX_TOKENS", th.sentinel_token_floor),
        ("side-judge (NLI entailment)", "PG_ENTAILMENT_MAX_TOKENS", th.sidejudge_token_floor),
    ]
    out: list[CheckResult] = []
    for role, knob, floor in specs:
        eff = _effective_token(cfg, knob)
        if eff is None:
            out.append(CheckResult(
                f"D-3.{knob}", f"{role} max_tokens >= {floor}", RED, STATIC,
                f"{knob}={cfg.get(knob)!r} is not a parseable int (un-resolvable token budget)",
            ))
            continue
        ok = eff >= floor
        out.append(_ok(
            f"D-3.{knob}", f"{role} max_tokens >= {floor}", ok, STATIC,
            f"{knob} effective={eff} (floor {floor}) -> "
            f"{'generous (never starves reasoning->verdict)' if ok else 'STARVED: truncates mid-write -> empty/collapse'}",
        ))
    return out


# --------------------------------------------------------------------------------------------
# D-4 — TIMEOUTS ORDERED
# --------------------------------------------------------------------------------------------

def check_d4_timeouts(cfg: Mapping[str, str], th: Thresholds) -> list[CheckResult]:
    gen = _to_int(cfg.get("PG_GENERATOR_LLM_TIMEOUT_SECONDS"))
    section = _to_int(cfg.get("PG_SECTION_WALLCLOCK_SECONDS"))
    run_wall = _to_int(cfg.get("PG_RUN_WALL_CLOCK_SEC"))
    seam = _to_int(cfg.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"))
    out: list[CheckResult] = []

    if None in (gen, section, run_wall):
        out.append(CheckResult(
            "D-4.ordering", "gen-call-wall < per-section budget < run wall", RED, STATIC,
            f"un-resolvable timeout(s): gen={gen} section={section} run_wall={run_wall}",
        ))
    else:
        ordering_ok = gen < section < run_wall
        out.append(_ok(
            "D-4.ordering", "gen-call-wall < per-section budget < run wall", ordering_ok, STATIC,
            f"gen={gen} < section={section} < run_wall={run_wall} -> "
            f"{'ordered (no healthy section guillotined mid-write)' if ordering_ok else 'INVERTED -> mid-write truncation'}",
        ))

    if seam is None or run_wall is None:
        out.append(CheckResult(
            "D-4.seam", "4-role seam wall raised for the big/slow kimi judge", RED, STATIC,
            f"un-resolvable: seam={seam} run_wall={run_wall}",
        ))
    else:
        # Binding lower bound = max(the §9.1.8 sane floor for the slow kimi judge, a single gen call) so
        # the seam is never tinier than a generation call AND is generous for the per-claim 4-role burst;
        # binding upper bound = the run wall (the seam must terminate inside it). seam-vs-section is
        # advisory: the locked full slate legitimately runs seam(7200) < section(9000) because the
        # section wall sizes ONE 64000-token section's generation while the seam covers whole-report D8.
        lower = max(th.seam_floor_seconds, gen or 0)
        seam_ok = (seam >= lower) and (seam <= run_wall)
        out.append(_ok(
            "D-4.seam", "4-role seam wall sane (>= floor & gen call, <= run wall)", seam_ok, STATIC,
            f"seam={seam} (floor {th.seam_floor_seconds}, gen-call {gen}, lower-bound {lower}) "
            f"vs run_wall={run_wall}; section={section} (advisory) -> "
            f"{'sane: generous for kimi, terminates inside the wall' if seam_ok else 'BAD: too short -> seam tears, or exceeds the run wall'}",
        ))
    return out


# --------------------------------------------------------------------------------------------
# D-5 — CAPS RIGHT
# --------------------------------------------------------------------------------------------

def check_d5_caps(cfg: Mapping[str, str], raw_env: Mapping[str, str], th: Thresholds) -> list[CheckResult]:
    out: list[CheckResult] = []

    fetch = _to_int(cfg.get("PG_SWEEP_FETCH_CAP"))
    fetch_ok = fetch is not None and fetch >= th.fetch_cap_floor
    out.append(_ok(
        "D-5.fetch_cap", f"PG_SWEEP_FETCH_CAP >= {th.fetch_cap_floor} (breadth floor)", fetch_ok, STATIC,
        f"PG_SWEEP_FETCH_CAP effective={fetch} (floor {th.fetch_cap_floor}) -> "
        f"{'breadth retained' if fetch_ok else 'STARVED main fetch lane'}",
    ))

    # The §-1.3-BANNED per-source citation cap was DELETED from fact_dedup.py — it must be ABSENT.
    span_cap = raw_env.get("PG_SPAN_PER_SOURCE_CITE_CAP")
    span_ok = span_cap is None or span_cap.strip() == ""
    out.append(CheckResult(
        "D-5.span_cite_cap", "§-1.3-banned PG_SPAN_PER_SOURCE_CITE_CAP is ABSENT",
        GREEN if span_ok else RED, STATIC,
        f"PG_SPAN_PER_SOURCE_CITE_CAP={span_cap!r} -> "
        f"{'absent (the deleted bolt-on stays gone)' if span_ok else 'PRESENT: a banned per-source cite cap is pinned'}",
    ))

    # PG_CAPPED_FINDING_DEDUP must be 0 on the production path (force-exact '0' in the slate).
    capped = cfg.get("PG_CAPPED_FINDING_DEDUP")
    capped_ok = not _truthy(capped)
    out.append(CheckResult(
        "D-5.capped_finding_dedup", "PG_CAPPED_FINDING_DEDUP == 0 (no re-cap-to-max_ev)",
        GREEN if capped_ok else RED, STATIC,
        f"PG_CAPPED_FINDING_DEDUP effective={capped!r} -> "
        f"{'0 (consolidate keep-all; no funnel re-cap)' if capped_ok else 'TRUTHY: the §-1.3-banned re-cap is re-armed'}",
    ))

    # The historical hidden [:N] choke = the generator-facing pool cap PG_LIVE_MAX_EV_TO_GEN
    # (was 20 -> 98% of the corpus silently dropped before per-section selection).
    pool = _to_int(cfg.get("PG_LIVE_MAX_EV_TO_GEN"))
    pool_ok = pool is not None and pool >= th.gen_pool_floor
    out.append(_ok(
        "D-5.gen_pool", f"PG_LIVE_MAX_EV_TO_GEN >= {th.gen_pool_floor} (no hidden pool [:N] choke)",
        pool_ok, STATIC,
        f"PG_LIVE_MAX_EV_TO_GEN effective={pool} (floor {th.gen_pool_floor}) -> "
        f"{'full pool reaches per-section selection' if pool_ok else 'CHOKED: rows silently dropped pre-selection'}",
    ))
    return out


# --------------------------------------------------------------------------------------------
# D-6 — FAIL-LOUD / NO SILENT DEGRADE
# --------------------------------------------------------------------------------------------

def check_d6_fail_loud(cfg: Mapping[str, str], th: Thresholds) -> list[CheckResult]:
    out: list[CheckResult] = []
    # The disclosure-PRODUCING flags must be effectively ON so a degrade is written to the manifest
    # (disclosed) rather than silently swallowed.
    disclosures = {
        "PG_SWEEP_CREDIBILITY_REDESIGN": "credibility tiering_status / corpus_credibility_disclosure to the manifest",
        "PG_CREDIBILITY_LLM_TIERING": "the LLM tiering winner that stamps tiering_status",
        "PG_RETRIEVAL_RELEVANCE_GATE": "relevance_gate demote-not-drop disclosure (demoted_fetched_to_fill)",
        "PG_REDACT_HELD_UNSUPPORTED": "held-unsupported quarantine disclosure (not a silent drop)",
        "PG_ALWAYS_RELEASE": "always-release + disclosed_gaps (a gap is disclosed, never silently withheld)",
    }
    for flag, why in disclosures.items():
        eff = cfg.get(flag)
        ok = _truthy(eff)
        out.append(_ok(
            f"D-6.{flag}", f"{flag} ON (degrade disclosed, not silent)", ok, STATIC,
            f"effective={eff!r} -> {'wired (disclosure reaches the manifest)' if ok else 'OFF: a degrade would be SILENT'}; {why}",
        ))
    return out


def shell_diced_preflight(th: Thresholds) -> CheckResult:
    """Shell ``pipeline_diced_preflight.py --json`` READ-ONLY and report its GO/NO-GO as an INPUT.

    INFORMATIONAL ONLY — never gates THIS config preflight's verdict. The diced harness gates a
    DIFFERENT concern (pipeline-STAGE §-1.3 invariants) and is deliberately CALIBRATED to go RED on the
    pre-fix banked drb_72 fixture (its own docstring) plus carries a KNOWN-RED-by-design dice, so its
    NO-GO is expected and orthogonal to run-config readiness. Surfaced so the operator sees both lanes;
    a missing fixture (exit 2) is reported, not failed. NEVER RED (status INFO)."""
    label = "diced pipeline-stage preflight (INFORMATIONAL input — never gates this verdict)"
    if not _DICED_PREFLIGHT.is_file():
        return CheckResult("D-6.diced", label, INFO, LIVE, f"{_DICED_PREFLIGHT} not found — cannot shell it")
    tmp = None
    try:
        import tempfile  # noqa: PLC0415

        fd, tmp = tempfile.mkstemp(prefix="opready_diced_", suffix=".json")
        os.close(fd)
        proc = subprocess.run(
            [sys.executable, str(_DICED_PREFLIGHT), "--json", tmp],
            capture_output=True, text=True, timeout=th.diced_timeout_seconds,
            cwd=str(_REPO_ROOT),
        )
        rc = proc.returncode
        verdict = {0: "GO", 1: "NO-GO", 2: "HARNESS-ERROR(no fixture?)"}.get(rc, f"rc={rc}")
        red_stages: list[str] = []
        by_design: list[str] = []
        if tmp and Path(tmp).is_file():
            try:
                payload = json.loads(Path(tmp).read_text(encoding="utf-8"))
                red_stages = payload.get("red_eruption_stages") or []
                by_design = payload.get("red_by_design_stages") or []
            except (OSError, ValueError):
                pass
        if rc == 2:
            return CheckResult(
                "D-6.diced", label, INFO, LIVE,
                "diced exit=2 (harness error — likely the banked drb_72 fixture is absent on this host); "
                "run it where the fixture exists. Informational only.",
            )
        return CheckResult(
            "D-6.diced", label, INFO, LIVE,
            f"diced verdict={verdict}; eruption-RED={red_stages or 'none'}; "
            f"known-RED-by-design={by_design or 'none'} "
            f"(NO-GO here is expected on the pre-fix banked fixture; see the diced table — does NOT gate config readiness)",
        )
    except subprocess.TimeoutExpired:
        return CheckResult("D-6.diced", label, INFO, LIVE,
                           f"diced exceeded {th.diced_timeout_seconds}s — skipped (informational)")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("D-6.diced", label, INFO, LIVE,
                           f"could not shell the diced preflight: {type(exc).__name__}: {exc}")
    finally:
        if tmp and Path(tmp).is_file():
            try:
                Path(tmp).unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------

def run_static_checks(env: Mapping[str, str], th: Thresholds) -> tuple[list[CheckResult], dict]:
    """Run every STATIC check. Returns (results, context) where context carries the resolved lineup /
    slugs the LIVE ping needs.

    The ``run_gate_b`` import + every downstream call run INSIDE ``_process_env_byte_identical`` so the
    process env is left byte-identical (P0 fix). When ``env`` is the live ``os.environ`` (the real-run
    path), the resolver still sees the .env-merged env WHILE inside the guard (fidelity preserved);
    when ``env`` is an injected dict (tests), resolution is unaffected and the guard merely undoes the
    import's mutation. Imports run_gate_b (lightweight, no model, no network)."""
    with _process_env_byte_identical():
        import scripts.dr_benchmark.run_gate_b as rg  # noqa: PLC0415
        from src.polaris_graph.roles.openrouter_role_transport import benchmark_verifier_lineup  # noqa: PLC0415

        meta = load_slate_meta()
        cfg = resolve_effective_config(env, meta)
        lock = rg.load_lock()
        generator_slug = resolve_generator_slug(env, lock)
        lineup = benchmark_verifier_lineup()

        # four-role-mode is wired by enable_four_role_mode() on the Gate-B entry — verify the entry
        # CALLS it (P2: AST call-node check, not a substring that false-passes on a comment/docstring).
        four_role_mode_wired = _source_calls(
            inspect.getsource(rg.run_gate_b_query), None, "enable_four_role_mode"
        )

        families: Optional[dict] = None
        families_error: Optional[str] = None
        try:
            families = rg.assert_four_role_families_distinct()
        except Exception as exc:  # noqa: BLE001 — a config-only collision check; capture, never crash
            families_error = f"{type(exc).__name__}: {exc}"

        results: list[CheckResult] = []
        results += check_d1_flags(cfg, env, meta, four_role_mode_wired)
        results += check_d1_launch_path(rg)
        results += check_d2_models_static(lineup, generator_slug, lock, families, families_error, th)
        results += check_d3_tokens(cfg, th)
        results += check_d4_timeouts(cfg, th)
        results += check_d5_caps(cfg, env, th)
        results += check_d6_fail_loud(cfg, th)

        slugs = {
            "generator": generator_slug,
            "mirror": lineup.get("mirror"),
            "sentinel": lineup.get("sentinel"),
            "judge": lineup.get("judge"),
        }
        return results, {"slugs": slugs, "judge_slug": lineup.get("judge")}


def aggregate(results: list[CheckResult]) -> str:
    return "NO-GO" if any(r.is_red for r in results) else "GO"


def print_table(results: list[CheckResult], verdict: str) -> None:
    id_w = max([len(r.check_id) for r in results] + [12])
    print("\n" + "=" * (id_w + 70))
    print("  OPERATIONAL-READINESS PREFLIGHT — will-it-die-from-a-stupid-mistake check")
    print("=" * (id_w + 70))
    print(f"  {'STATUS':<12} {'KIND':<10} {'CHECK':<{id_w}}  WHAT / DETAIL")
    print("-" * (id_w + 70))
    for r in results:
        print(f"  {r.status:<12} {r.static_or_live:<10} {r.check_id:<{id_w}}  {r.what}")
        print(f"  {'':<12} {'':<10} {'':<{id_w}}    -> {r.detail}")
    print("-" * (id_w + 70))
    greens = sum(r.status == GREEN for r in results)
    reds = sum(r.is_red for r in results)
    pendings = sum(r.is_pending for r in results)
    infos = sum(r.is_info for r in results)
    print(f"  {greens} GREEN, {reds} RED, {pendings} LIVE-PENDING, {infos} INFO  ->  {verdict}")
    if reds:
        print("  RED (these would kill / cripple the run):")
        for r in results:
            if r.is_red:
                print(f"    - {r.check_id}: {r.detail}")
    if pendings:
        print("  LIVE-PENDING (could not confirm without a live probe; does not force NO-GO):")
        for r in results:
            if r.is_pending:
                print(f"    - {r.check_id}: {r.detail}")
    if infos:
        print("  INFO (surfaced input; does NOT gate the verdict):")
        for r in results:
            if r.is_info:
                print(f"    - {r.check_id}: {r.detail}")
    print("=" * (id_w + 70))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Operational-readiness preflight for the Gate-B paid run.")
    ap.add_argument("--json", default=None, help="write a machine-readable result sidecar here.")
    ap.add_argument("--no-ping", action="store_true",
                    help="skip the free OpenRouter /models reachability GET (static checks only).")
    ap.add_argument("--no-diced", action="store_true",
                    help="skip shelling pipeline_diced_preflight.py (informational input).")
    ap.add_argument("--require-live-ping", action="store_true",
                    help="treat an unreachable /models ping as NO-GO (default: LIVE-PENDING).")
    args = ap.parse_args(argv)

    # Render the §/non-ASCII detail correctly regardless of the Windows console codepage (the operator
    # reads by ear; mojibake is noise). Best-effort — never fatal.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    th = Thresholds()
    try:
        results, ctx = run_static_checks(os.environ, th)
    except Exception as exc:  # noqa: BLE001 — any setup/import failure is a HARNESS error (exit 2)
        print(f"[opready] HARNESS ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    if not args.no_ping:
        ping = ping_openrouter_catalog(ctx["slugs"], ctx["judge_slug"], th)
        results += check_d2_models_live(ping, ctx["slugs"], ctx["judge_slug"], th, args.require_live_ping)
    else:
        results.append(CheckResult(
            "D-2.ping", "OpenRouter /models reachability (skipped)", PENDING, LIVE,
            "--no-ping: skipped the free catalog GET; confirm slug presence + judge providers on the run host",
        ))

    if not args.no_diced:
        results.append(shell_diced_preflight(th))
    else:
        results.append(CheckResult(
            "D-6.diced", "diced pipeline-stage preflight (skipped)", INFO, LIVE,
            "--no-diced: did not shell pipeline_diced_preflight.py",
        ))

    verdict = aggregate(results)
    print_table(results, verdict)

    if args.json:
        payload = {
            "verdict": verdict,
            "thresholds": th.__dict__,
            "checks": [r.__dict__ for r in results],
            "red": [r.check_id for r in results if r.is_red],
            "pending": [r.check_id for r in results if r.is_pending],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[opready] wrote sidecar -> {args.json}")

    return 1 if verdict == "NO-GO" else 0


if __name__ == "__main__":
    sys.exit(main())
