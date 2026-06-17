"""Generation-level resume checkpoint: persist the generated section DRAFTS so a
``--resume`` can SKIP the expensive multi-section generation and re-enter at the
post-generation faithfulness gates.

WHY (SPEED, FAITHFULNESS-NEUTRAL):
    Today the latest resume checkpoint is ``corpus_snapshot.json`` (POST-SELECTION),
    so every ``--resume`` re-runs the ~30-40min multi-section generation before it can
    re-reach the verification/4-role stages. After a VERIFICATION bug-fix the operator
    pays that full generation cost again just to exercise the changed gate. This module
    persists the generator's per-section RAW DRAFTS (plus the accepted outline) at the
    single post-generation seam, so a resume reloads the drafts, skips the section-draft
    LLM calls, and re-enters the SAME strict_verify / NLI-repair / 4-role / D8 path.

WHAT THE SNAPSHOT PERSISTS (DATA ONLY):
    * the accepted OUTLINE: a flat list of ``SectionPlan`` dataclasses (title / focus /
      ev_ids / archetype) — ``asdict`` / ``SectionPlan(**d)`` round-trip, no live object.
      The outline is itself an LLM call (``_call_outline``) on a fresh run, so it MUST be
      persisted or the reloaded draft keys would not line up with a re-derived structure.
    * the per-section RAW DRAFT prose, keyed by section title. ``raw_draft`` is the
      generator's draft text BEFORE provenance-token rewrite + strict_verify (the candidate
      sentences the gate inspects). It is the ONLY input that lets strict_verify re-run
      MEANINGFULLY on resume — ``verified_text`` is already post-drop, so re-verifying it
      could never catch a strict_verify bug (the wrongly kept/dropped sentences are baked in).
    * ITEM 5a (I-arch-007 #1264 — LOSSLESS verification re-entry): the verdict-FREE
      per-section ``SectionPlan`` view (section id / title / atom-id list) AND the per-section
      atom/claim CATALOG (atom_id -> evidence-id / span bindings). The post-generation
      verification stage consumes per-section ``SectionPlan`` metadata + the per-section
      atom/claim catalog (which atoms/claims belong to each section + their evidence bindings),
      NOT just the raw section text. ``raw_drafts`` ALONE cannot deterministically re-enter
      strict_verify/NLI/D8 the way a fresh run does, so this metadata is persisted as DATA so a
      resume re-enters LOSSLESSLY. The SWEEP owner (ITEM 5 in run_honest_sweep_r3.py) consumes
      these. Every atom binding is PRE-verdict DATA (atom_id/evidence_id/span_start/span_end/
      literal_text) — NO ``is_verified``, NO ``release_outcome``; it remains subject to the
      ``_FORBIDDEN_VERDICT_KEYS`` guard, validated RECURSIVELY over the nested structure.
    * a ``generation_flags`` slate: the env flags that change WHAT the generator produces
      (distill / atom-refusal mode / outline mode). A cached raw draft is a faithful
      strict_verify input ONLY under the same flag config that produced it; on resume the
      loader FAILS LOUD if the active flags differ.

HARD INVARIANT (CLAUDE.md §-1.3, ABSOLUTE — mirrors corpus_snapshot.py):
    A checkpoint stores DATA, NEVER A VERDICT.
    The snapshot stores ONLY the outline (plan DATA) + raw draft PROSE + the verdict-free
    section/atom metadata (ITEM 5a) + the flag slate. It stores NO strict_verify result, NO
    NLI/4-role/D8 decision, NO "verified" flag, NO release outcome — at ANY nesting depth. On
    ``--resume`` the caller reloads this DATA and the generator RE-RUNS strict_verify / the
    NLI-driven sentence-repair loop on every reloaded draft, then the downstream 4-role / D8
    seam RE-RUNS from scratch — exactly as a fresh run does. Only the section-draft LLM call is
    skipped; every faithfulness gate still fully executes. This module makes a relaxation
    structurally impossible: it never serializes a verdict, and ``load_generation_snapshot``
    fail-loud-rejects a payload that smuggled one at ANY depth (the RECURSIVE guard,
    Codex P2-3).

PRECISE "SKIP GENERATION" CONTRACT:
    "skip generation" means "skip the initial section-draft LLM calls". strict_verify can
    still trigger a per-section REGENERATION (an LLM call) when the reloaded draft fails the
    kept-fraction floor — that regen runs exactly as on a fresh run. A resume is therefore
    cheap, not necessarily zero-LLM-cost.

The snapshot is a plain JSON document (schema_version pinned) so it is human-auditable.
No pickle, no code execution on load.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

# Bump on any incompatible schema change. A reload that sees a different version FAILS LOUD
# (refuses to resume) rather than silently feeding a stale-shaped draft set to the verifier.
# v2 (ITEM 5a, I-arch-007 #1264): added the verdict-free per-section ``section_plans`` view +
# per-section ``section_atom_catalogs`` for LOSSLESS verification re-entry. A v1 payload (no
# section metadata) is REFUSED — a resume from it could not re-enter strict_verify/NLI/D8
# losslessly, so failing loud is correct (re-run fresh).
GENERATION_SNAPSHOT_SCHEMA_VERSION = 2

# The canonical snapshot filename inside a per-query run_dir.
GENERATION_SNAPSHOT_FILENAME = "generation_snapshot.json"

# Stage pointer. Only ``post_generation`` is persisted today (the seam right after the
# generator produces section drafts, before the post-generation verification/4-role gates).
STAGE_POST_GENERATION = "post_generation"

# The master env flag gating the generation-snapshot feature (LAW VI: no hard-coded behavior).
# Default ON: a fresh run WRITES the snapshot; a ``--resume`` PREFERS it over corpus_snapshot
# when present. Set to a falsey value to disable both the write and the resume-load.
GENERATION_SNAPSHOT_ENV = "PG_GENERATION_SNAPSHOT"

# The env flag whose mode, when not "off", makes a cached-draft resume DIVERGE from a fresh run:
# the post-hoc atom-refusal validator consumes the per-section ``atom_catalog`` that ONLY the live
# ``_call_section`` produces. A reloaded-draft section has no live catalog (the cached path sets it
# empty), so under ``log_only``/``strict`` the validator would mark every reloaded section
# "skipped_empty_catalog" / degraded — a fresh run with a real catalog certifies them. That is a
# resume != fresh DIVERGENCE (a spurious extra-strictness, not a relaxation), so a generation-stage
# resume is REFUSED outright whenever this mode is active (``assert_atom_refusal_mode_resumable``).
ATOM_REFUSAL_MODE_ENV = "PG_ATOM_REFUSAL_MODE"
ATOM_REFUSAL_MODE_OFF = "off"

# Generation-affecting env flags whose values are captured into the snapshot slate. A cached
# raw draft is a faithful strict_verify input ONLY under the same values; on resume the loader
# FAILS LOUD on any mismatch (see ``assert_generation_flags_match``). These are the flags that
# change WHAT the generator emits as a draft (NOT verification-only flags, which are SUPPOSED to
# differ on a verification-fix resume — that is the entire point of the feature).
GENERATION_AFFECTING_ENV_FLAGS: tuple[str, ...] = (
    # PG_SECTION_DISTILL changes the section-writing path (REDUCE over a distilled ledger vs
    # legacy quote-blocks) => a draft produced under one is not a faithful input to the other.
    "PG_SECTION_DISTILL",
    # PG_ATOM_REFUSAL_MODE: in non-"off" modes the post-hoc atom validator consumes the
    # per-section atom_catalog that ONLY the live _call_section produces. A reloaded-draft
    # section has no live catalog, so a non-"off" mode cannot be faithfully replayed and the
    # loader refuses the resume rather than silently shipping a degraded section.
    "PG_ATOM_REFUSAL_MODE",
    # PG_GENERATOR_MODEL pins the writer; a draft produced by a different writer is a different
    # candidate set (recorded for audit + mismatch fail-loud).
    "PG_GENERATOR_MODEL",
    # PG_SWEEP_CREDIBILITY_REDESIGN gates the credibility pass that annotates the drafted
    # sentences' disclosure; recorded so a resume under a different setting is rejected.
    "PG_SWEEP_CREDIBILITY_REDESIGN",
)

# Verdict tokens a DATA-ONLY checkpoint may NEVER contain (mirrors the A12 forbidden set in
# run_honest_sweep_r3.py). If any appears ANYWHERE in a payload (top-level OR nested in the
# section/atom metadata), a verdict leaked in and the loader/saver FAILS LOUD — a silent load
# would relax the only hard gate (§-1.3 ABSOLUTE). Validated RECURSIVELY (Codex P2-3).
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


class GenerationSnapshotError(RuntimeError):
    """Raised when a --resume reload cannot trust the on-disk generation snapshot.

    FAIL LOUD (LAW II): a missing/corrupt/version-mismatched/verdict-leaked/flag-mismatched
    snapshot must NOT silently fall back to a fresh generation under --resume (the operator
    asked to skip generation; a silent re-bill would mask the interruption and defeat the
    feature). The caller surfaces this as a clean fail-loud — never a silent fresh run.
    """


def _assert_no_verdict_keys_recursive(obj: Any, *, path: str = "<root>") -> None:
    """RECURSIVELY fail-loud if a forbidden verdict key appears at ANY nesting depth.

    Codex P2-3 (I-arch-007 #1264): the ITEM-5a section/atom metadata is NESTED
    (section -> atom_catalog -> atom dict), so a top-level-only guard would let a verdict
    key leak through a nested structure. This walks every dict key + every list element so
    NO ``is_verified`` / ``release_outcome`` / ``verified_text`` (etc.) can survive at any
    depth — on BOTH the save path (refuse to PERSIST a leaked verdict) and the load path
    (refuse to LOAD one). The walk is data-only (dict/list/scalars); a JSON payload has no
    other container types, so this is total over a parsed snapshot.
    """
    if isinstance(obj, dict):
        leaked = sorted(_FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
        if leaked:
            raise GenerationSnapshotError(
                f"generation snapshot at {path} contains FORBIDDEN verdict key(s) {leaked} — "
                "a checkpoint stores DATA ONLY (§-1.3); a resume re-runs every gate and can NEVER "
                "replay a stored decision. Refusing (recursive verdict-key guard, Codex P2-3)."
            )
        for key, value in obj.items():
            _assert_no_verdict_keys_recursive(value, path=f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            _assert_no_verdict_keys_recursive(value, path=f"{path}[{index}]")


def generation_snapshot_path(run_dir: Path) -> Path:
    """Deterministic generation-snapshot location for a per-query run_dir."""
    return Path(run_dir) / GENERATION_SNAPSHOT_FILENAME


def generation_snapshot_enabled() -> bool:
    """Read the master feature flag at CALL TIME (LAW VI). Default ON (unset == enabled)."""
    raw = os.getenv(GENERATION_SNAPSHOT_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


def _capture_generation_flags() -> dict[str, str]:
    """Snapshot the current values of the generation-affecting env flags (DATA, no verdict).

    An unset flag is recorded as the empty string so a resume that sets it (or vice versa) is
    detected as a mismatch by ``assert_generation_flags_match`` rather than silently accepted.
    """
    return {name: os.environ.get(name, "") for name in GENERATION_AFFECTING_ENV_FLAGS}


def _outline_payload(outline: list[Any]) -> list[dict[str, Any]]:
    """Serialize the accepted outline (list of SectionPlan dataclasses) to flat dicts.

    Each ``SectionPlan`` is a flat dataclass (title / focus / ev_ids / archetype) so ``asdict``
    is a safe DATA-only round-trip. A non-dataclass entry is a programming error and fails loud
    (no silent drop) so the persisted outline can never diverge from the live one.
    """
    rows: list[dict[str, Any]] = []
    for plan in outline or []:
        if not is_dataclass(plan):
            raise GenerationSnapshotError(
                f"generation snapshot: outline entry {plan!r} is not a SectionPlan dataclass; "
                "refusing to persist a non-DATA outline element"
            )
        rows.append(asdict(plan))
    return rows


def _section_plans_payload(section_plans: dict[str, Any] | None) -> dict[str, Any]:
    """ITEM 5a: serialize the verdict-FREE per-section SectionPlan view.

    Maps section_id -> {title, atom_ids}. This is the minimal plan-DATA the verification
    re-entry needs to line each reloaded draft up with its atoms (NOT a verdict). ``atom_ids``
    is the ordered list of atom-id strings the section drew from; ``title`` is the section
    heading. DATA-only: no verified flag, no release outcome (the recursive guard enforces it).
    A None/empty input serializes to ``{}`` (a fresh run that produced no atom-bearing sections,
    e.g. OFF mode — the loader treats empty as "no metadata to re-enter with").
    """
    out: dict[str, Any] = {}
    for section_id, view in (section_plans or {}).items():
        if not isinstance(view, dict):
            raise GenerationSnapshotError(
                f"generation snapshot: section_plans[{section_id!r}] is {view!r}, not a dict; "
                "refusing to persist a non-DATA section-plan view"
            )
        atom_ids = view.get("atom_ids", [])
        out[str(section_id)] = {
            "title": str(view.get("title", "")),
            "atom_ids": [str(a) for a in (atom_ids or [])],
        }
    return out


# The DATA-only fields of a ClaimAtom that bind an atom to its evidence span. The atom/claim
# catalog persists EXACTLY these (atom_id -> evidence-id / span bindings) — never a verdict.
# Mirrors src.polaris_graph.generator.claim_atom_extractor.ClaimAtom identity+provenance fields.
_ATOM_BINDING_FIELDS: tuple[str, ...] = (
    "atom_id",
    "evidence_id",
    "span_start",
    "span_end",
    "literal_text",
)


def _atom_binding(atom: Any, *, section_id: str) -> dict[str, Any]:
    """Extract the DATA-only atom->evidence-id/span binding from one catalog entry.

    Accepts either a ClaimAtom dataclass (the live ``atom_catalog`` value type) or a plain
    dict (already-serialized). Persists ONLY the identity+provenance binding fields — never a
    verdict. A missing required binding field fails loud (no silent partial binding).
    """
    if is_dataclass(atom):
        source = asdict(atom)
    elif isinstance(atom, dict):
        source = atom
    else:
        raise GenerationSnapshotError(
            f"generation snapshot: section_atom_catalogs[{section_id!r}] entry {atom!r} is "
            "neither a ClaimAtom dataclass nor a dict; refusing to persist a non-DATA atom"
        )
    binding: dict[str, Any] = {}
    for field_name in _ATOM_BINDING_FIELDS:
        if field_name not in source:
            raise GenerationSnapshotError(
                f"generation snapshot: section_atom_catalogs[{section_id!r}] atom is missing the "
                f"required binding field {field_name!r}; refusing to persist an incomplete atom "
                "binding (a resume would mis-bind the claim to its evidence span)"
            )
        binding[field_name] = source[field_name]
    return binding


def _dict_atoms_only(section_atom_catalogs: dict[str, Any] | None) -> dict[str, Any]:
    """Return a view of the catalogs with frozen-ClaimAtom values EXCLUDED, for the input guard.

    A frozen ``ClaimAtom`` dataclass is verdict-free DATA by construction (its fields are the
    fixed identity/provenance/semantic set — no verdict field exists), and the recursive guard
    walks dict/list/scalars (not arbitrary dataclasses). So the raw-input verdict-key guard only
    needs to inspect DICT/LIST caller-supplied atom entries — those are the only ones that could
    smuggle a verdict key. This drops dataclass atoms from the walked view (their bindings are
    still extracted verbatim by ``_atom_binding``); dict atoms are kept so the guard sees them.
    """
    out: dict[str, Any] = {}
    for section_id, catalog in (section_atom_catalogs or {}).items():
        if isinstance(catalog, dict):
            entries = list(catalog.values())
        elif isinstance(catalog, (list, tuple)):
            entries = list(catalog)
        else:
            # A malformed catalog type — keep it so _section_atom_catalogs_payload fails loud on it.
            out[str(section_id)] = catalog
            continue
        out[str(section_id)] = [a for a in entries if not is_dataclass(a)]
    return out


def _section_atom_catalogs_payload(
    section_atom_catalogs: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    """ITEM 5a: serialize the per-section atom/claim catalog as DATA-only span bindings.

    Maps section_id -> [ {atom_id, evidence_id, span_start, span_end, literal_text}, ... ].
    The live ``atom_catalog`` is a ``dict[atom_id, ClaimAtom]``; we persist its values as the
    ordered list of evidence-span bindings the verification re-entry needs. Verdict-FREE; the
    recursive guard re-asserts it. A None/empty input serializes to ``{}``.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for section_id, catalog in (section_atom_catalogs or {}).items():
        sid = str(section_id)
        bindings: list[dict[str, Any]] = []
        if isinstance(catalog, dict):
            atoms = catalog.values()
        elif isinstance(catalog, (list, tuple)):
            atoms = catalog
        else:
            raise GenerationSnapshotError(
                f"generation snapshot: section_atom_catalogs[{sid!r}] is {catalog!r}, neither a "
                "dict[atom_id, ClaimAtom] nor a list; refusing to persist a non-DATA catalog"
            )
        for atom in atoms:
            bindings.append(_atom_binding(atom, section_id=sid))
        out[sid] = bindings
    return out


def save_generation_snapshot(
    run_dir: Path,
    *,
    run_id: str,
    question: str,
    slug: str,
    domain: str,
    outline: list[Any],
    section_raw_drafts: dict[str, str],
    had_contract_sections: bool,
    section_plans: dict[str, Any] | None = None,
    section_atom_catalogs: dict[str, Any] | None = None,
    stage: str = STAGE_POST_GENERATION,
) -> Path:
    """Persist the post-generation snapshot. Returns the written path.

    Atomic write (temp + os.replace) so a kill DURING the snapshot write never leaves a
    truncated/half-parsed file that a later --resume would choke on.

    ``outline`` is the ACCEPTED SectionPlan list (post outline-call / research_plan / contract
    injection). ``section_raw_drafts`` maps section title -> the generator's RAW DRAFT prose
    (pre strict_verify). ``had_contract_sections`` records whether the run used V30 contract
    plans: a reloaded plain-SectionPlan outline cannot reconstruct a ContractSectionPlanExt, so
    a resume of such a run must FAIL LOUD rather than silently route contract sections through
    the legacy path (a behavior divergence vs the fresh run).

    ITEM 5a (I-arch-007 #1264): ``section_plans`` is the verdict-FREE per-section view
    (section_id -> {title, atom_ids}); ``section_atom_catalogs`` is the per-section atom/claim
    catalog (section_id -> dict[atom_id, ClaimAtom] | list[ClaimAtom]). Both are persisted as
    DATA-only span bindings so a resume re-enters the verification stage LOSSLESSLY. The whole
    payload is validated RECURSIVELY for leaked verdict keys BEFORE the write (Codex P2-3) — a
    leaked ``is_verified`` / ``release_outcome`` at ANY depth fails loud rather than persisting.

    The payload carries DATA ONLY — outline + draft prose + verdict-free section/atom metadata +
    the flag slate. It carries NO verdict; a resume re-runs every faithfulness gate on the
    reloaded drafts.
    """
    run_dir = Path(run_dir)
    # Codex P2-3: fail loud on a leaked verdict key in the RAW caller-supplied section/atom
    # metadata BEFORE the binding-field whitelist (_atom_binding / _section_plans_payload) could
    # silently STRIP it. Whitelisting alone would drop a smuggled ``is_verified`` instead of
    # refusing — that is a silent strip, not the fail-loud §-1.3 demands. Guarding the raw input
    # (dataclass values are excluded — a frozen ClaimAtom is by construction verdict-free DATA;
    # only dict/list caller input can smuggle a key) makes a leaked decision impossible to persist.
    _assert_no_verdict_keys_recursive(
        {"section_plans": section_plans or {}}, path="<input>.section_plans"
    )
    _assert_no_verdict_keys_recursive(
        _dict_atoms_only(section_atom_catalogs), path="<input>.section_atom_catalogs"
    )
    payload: dict[str, Any] = {
        "schema_version": GENERATION_SNAPSHOT_SCHEMA_VERSION,
        "stage": stage,
        "run_id": run_id,
        "question": question,
        "slug": slug,
        "domain": domain,
        # DATA: the accepted outline (plan structure the drafts are keyed against).
        "outline": _outline_payload(outline),
        # DRAFT PROSE ONLY (re-verified on resume) — never a verified flag.
        "section_raw_drafts": {str(k): str(v or "") for k, v in (section_raw_drafts or {}).items()},
        # ITEM 5a: verdict-FREE per-section SectionPlan view (id -> title + atom-id list).
        "section_plans": _section_plans_payload(section_plans),
        # ITEM 5a: per-section atom/claim catalog (atom -> evidence-id/span bindings, DATA-only).
        "section_atom_catalogs": _section_atom_catalogs_payload(section_atom_catalogs),
        # The generation-affecting flag slate: a cached draft is faithful ONLY under these values.
        "generation_flags": _capture_generation_flags(),
        # Whether the run used V30 contract sections (resume of such a run fails loud).
        "had_contract_sections": bool(had_contract_sections),
        # EXPLICIT invariant marker so a §-1.1 auditor sees the contract on the artifact itself.
        "faithfulness_invariant": (
            "DATA ONLY; outline + raw section drafts + verdict-free section/atom metadata + flag "
            "slate; NO verdict/verified_text stored at any depth. A resume re-runs strict_verify + "
            "NLI-repair + 4-role + D8 on every reloaded draft; only the section-draft LLM call is "
            "skipped."
        ),
    }
    # Codex P2-3: refuse to PERSIST a payload that smuggled a verdict key at ANY nesting depth
    # (the ITEM-5a section/atom metadata is nested). Fail loud BEFORE the write so a leaked
    # decision can never reach disk.
    _assert_no_verdict_keys_recursive(payload)
    path = generation_snapshot_path(run_dir)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def load_generation_snapshot(run_dir: Path) -> dict[str, Any]:
    """Reload + validate the generation snapshot for --resume. Returns the parsed payload.

    Raises ``GenerationSnapshotError`` on absent / malformed / version-mismatched / verdict-
    leaked / empty-draft snapshots so the caller fails loud instead of resuming on bad data.
    Returns DATA ONLY — the caller MUST re-run every faithfulness gate on the reloaded drafts.
    Flag-slate compatibility is a SEPARATE check (``assert_generation_flags_match``) so the
    caller can surface a precise "active flags differ from the snapshot" message.
    """
    path = generation_snapshot_path(run_dir)
    if not path.exists():
        raise GenerationSnapshotError(
            f"--resume: no generation snapshot at {path} (nothing to resume at the generation "
            f"stage; the earlier corpus_snapshot path handles a pre-generation resume)"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationSnapshotError(
            f"--resume: generation snapshot at {path} is unreadable/corrupt: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise GenerationSnapshotError(
            f"--resume: generation snapshot at {path} is not a JSON object"
        )
    version = payload.get("schema_version")
    if version != GENERATION_SNAPSHOT_SCHEMA_VERSION:
        raise GenerationSnapshotError(
            f"--resume: generation snapshot schema_version {version!r} != expected "
            f"{GENERATION_SNAPSHOT_SCHEMA_VERSION} at {path}; refusing to resume on a stale-shaped "
            f"draft set (re-run fresh)"
        )
    # Codex P2-3: RECURSIVE verdict-key guard over the WHOLE payload (the ITEM-5a section/atom
    # metadata is nested) — a leaked verdict at any depth fails loud rather than loading.
    try:
        _assert_no_verdict_keys_recursive(payload, path=str(path))
    except GenerationSnapshotError as exc:
        raise GenerationSnapshotError(
            f"--resume: {exc}. Refusing to load (a resume re-runs every gate; it can NEVER "
            "replay a stored decision, §-1.3 ABSOLUTE)."
        ) from exc
    drafts = payload.get("section_raw_drafts")
    if not isinstance(drafts, dict) or not drafts:
        raise GenerationSnapshotError(
            f"--resume: generation snapshot at {path} has no section_raw_drafts; refusing to resume "
            f"a generation with no reloadable drafts"
        )
    # ITEM 5a: the section/atom re-entry metadata MUST be present (a v2 payload always carries
    # both keys, possibly empty for an OFF-mode run with no atom-bearing sections). A MISSING key
    # (not merely empty) means a malformed/hand-edited payload — fail loud rather than re-enter
    # verification with an incomplete structure.
    for _meta_key in ("section_plans", "section_atom_catalogs"):
        if not isinstance(payload.get(_meta_key), dict):
            raise GenerationSnapshotError(
                f"--resume: generation snapshot at {path} is missing the ITEM-5a {_meta_key!r} "
                "section-metadata map; a resume could not re-enter the verification stage "
                "losslessly. Refusing to resume (re-run fresh)."
            )
    if payload.get("had_contract_sections"):
        raise GenerationSnapshotError(
            f"--resume: generation snapshot at {path} was written for a run that used V30 contract "
            "sections; a reloaded plain-SectionPlan outline cannot reconstruct a "
            "ContractSectionPlanExt, so a generation-stage resume of this run would diverge from a "
            "fresh run. Refusing to resume at the generation stage (re-run fresh, or resume from the "
            "corpus_snapshot)."
        )
    # The cached-draft path produces an EMPTY per-section atom_catalog (only the live _call_section
    # builds one). Under PG_ATOM_REFUSAL_MODE != off the post-hoc validator would mark every reloaded
    # section degraded ("skipped_empty_catalog") while a fresh run certifies them — a resume != fresh
    # DIVERGENCE. Refuse the generation-stage resume outright while that mode is active.
    assert_atom_refusal_mode_resumable()
    return payload


def assert_atom_refusal_mode_resumable() -> None:
    """FAIL LOUD if PG_ATOM_REFUSAL_MODE is active (not "off") at resume time.

    A generation-stage resume injects cached drafts with NO live atom_catalog. The post-hoc atom-
    refusal validator (log_only / strict) consumes that catalog; with it empty, every reloaded
    section is flagged "skipped_empty_catalog" / degraded — diverging from a fresh run that has a
    real catalog. This refuses the resume rather than silently shipping a spuriously-degraded run
    (the divergence the generation snapshot exists to prevent). Mode "off" (the default) never
    consults the catalog, so the empty catalog is a true no-op and the resume proceeds.
    """
    mode = os.environ.get(ATOM_REFUSAL_MODE_ENV, ATOM_REFUSAL_MODE_OFF).strip().lower()
    if mode != ATOM_REFUSAL_MODE_OFF:
        raise GenerationSnapshotError(
            f"--resume: {ATOM_REFUSAL_MODE_ENV}={mode!r} is active, but a generation-stage resume "
            "injects cached drafts with NO live atom_catalog — the post-hoc atom-refusal validator "
            "would mark every reloaded section degraded ('skipped_empty_catalog'), diverging from a "
            f"fresh run. Refusing to resume at the generation stage (re-run fresh, or set "
            f"{ATOM_REFUSAL_MODE_ENV}=off)."
        )


def assert_generation_flags_match(payload: dict[str, Any]) -> None:
    """FAIL LOUD if the active generation-affecting flags differ from the snapshot slate.

    A cached raw draft is a faithful strict_verify input ONLY under the same flag config that
    produced it (§-1.3 no-silent-divergence). The verification-only flags are DELIBERATELY NOT in
    ``GENERATION_AFFECTING_ENV_FLAGS`` — changing them on a resume is the entire point of the
    feature and must be allowed. A mismatch on a generation-affecting flag, however, means the
    reloaded draft no longer matches what a fresh run would have produced, so we refuse rather
    than ship a divergent run.
    """
    snapshot_flags = payload.get("generation_flags")
    if not isinstance(snapshot_flags, dict):
        raise GenerationSnapshotError(
            "--resume: generation snapshot is missing its generation_flags slate; refusing to "
            "resume without the flag config that produced the cached drafts"
        )
    active = _capture_generation_flags()
    mismatches = {
        name: {"snapshot": snapshot_flags.get(name, ""), "active": active.get(name, "")}
        for name in GENERATION_AFFECTING_ENV_FLAGS
        if str(snapshot_flags.get(name, "")) != str(active.get(name, ""))
    }
    if mismatches:
        raise GenerationSnapshotError(
            "--resume: generation-affecting flags differ from the snapshot slate "
            f"{mismatches}; a cached raw draft is only a faithful strict_verify input under the "
            "flag config that produced it. Refusing to resume at the generation stage (re-run fresh)."
        )


def reconstruct_outline(payload: dict[str, Any]) -> list[Any]:
    """Rebuild the list of ``SectionPlan`` dataclasses from a reloaded snapshot payload.

    The rehydrated plans are plain ``SectionPlan`` (title / focus / ev_ids / archetype) — never
    a ContractSectionPlanExt (the loader already refuses a contract run), so every reloaded
    section routes through the LEGACY ``_run_section`` path on resume, exactly matching how a
    fresh non-contract run runs. Carries NO verdict — gates re-run on the drafts.
    """
    # Lazy import keeps this module import-light and avoids a cycle through the generator package.
    from src.polaris_graph.generator.multi_section_generator import SectionPlan

    rows = payload.get("outline") or []
    plans: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            raise GenerationSnapshotError(
                f"--resume: generation snapshot outline entry {row!r} is not a JSON object"
            )
        plans.append(
            SectionPlan(
                **{k: v for k, v in row.items() if k in SectionPlan.__dataclass_fields__}
            )
        )
    return plans
