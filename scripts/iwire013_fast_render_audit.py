#!/usr/bin/env python3
"""I-wire-013 (#1327): FAST render-replay VALIDATOR (the short test).

Validates the I-wire-011/012/013 render fixes — chrome-as-claim screening, mid-word
TRUNCATION suppression, the possible_metric_mismatch contradiction render-gate, and the
analytical-DEPTH layer — in MINUTES, by REPLAYING composition + render + screens from a banked
post-verification checkpoint and STOPPING before the 4-role/D8 judge. It skips the ~40min
generation (reuses the banked verified sentences) and the ~40min D8 (never invoked).

WHY a standalone validator and NOT a `--render-only` flag inside run_one_query (advisor, this
session): run_one_query's render block (run_honest_sweep_r3.py L11455-11722) reads dozens of
fields off a FULLY-POPULATED ``multi`` MultiSectionResult (per-section SectionResult objects,
``credibility_analysis.baskets``, ``bibliography``, ``reliability_header``,
``dropped_sentences_final`` ...). NO banked artifact carries ``multi``: the post-verification
checkpoint (``postverify_checkpoint.json``) is DATA-ONLY (per-sentence kept/dropped accounting,
§-1.3), and the existing ``--resume`` infra either re-runs generation (from
``corpus_snapshot.json``) or re-runs D8 — neither is the fast render-only path. So a faithful
fast validator must RECONSTRUCT the minimal section state from ``verification_details`` and drive
the REAL leaf render/screen/composition functions directly.

FAITHFULNESS — calls the REAL pipeline functions, never a reimplementation (the constraint). The
fixes live in these leaves and this validator imports + calls them, in the SAME order
run_one_query assembles report.md (L11668-11707):
  - composition: ``key_findings.build_key_findings`` / ``key_findings.build_depth_layer``
                 ``abstract_conclusion.build_abstract`` / ``.build_conclusion``
                 ``depth_synthesis.synthesize_cross_source_findings`` (bounded; --skip-depth off)
  - render+assembly: ``run_honest_sweep_r3.assemble_report_md`` / ``.dedup_identical_paragraphs``
  - SCREENS: ``run_honest_sweep_r3._screen_key_findings_chrome`` /
             ``._screen_offtopic_chrome_sections`` / ``._strip_dangling_gap_crossref`` /
             ``._correct_contradiction_magnitude_range`` / ``._screen_garbled_headers`` /
             ``._render_contradicts_block`` (the I-wire-013 possible_metric_mismatch render-gate)
  - chrome canary: ``weighted_enrichment.evaluate_render_chrome_canary`` (mode=enforce)
  - §-1.1 audit predicates: ``weighted_enrichment.is_render_chrome_or_unrenderable`` /
             ``key_findings.is_truncated_fragment`` / ``contradiction_detector.POSSIBLE_METRIC_MISMATCH_MARKER``

DATA-AVAILABILITY HONESTY (§-1.1 false-green guard): the optional render inputs
(``contradictions.json`` for the contradiction-noise check, ``bibliography.json`` /
``evidence_pool.json`` / ``baskets.json`` for the depth-synthesis network pass) are loaded from
the SNAPSHOT DIR only — never cross-imported from a DIFFERENT run (split-brain). When an input is
ABSENT the check it gates is labeled ``SKIPPED (input absent)``, NOT silently passed as 0 — a
missing-sidecar -> ``contradiction_noise=0 -> PASS`` would be the exact false-green this validator
exists to catch.

LAW VI: every threshold + path + toggle is a CLI arg / PG_* env read.

Usage (LOCAL, instant deterministic check — no network):
    python scripts/iwire013_fast_render_audit.py \
        --snapshot-dir outputs/iwire013_validate_local --skip-depth

Usage (with the bounded depth-synthesis pass when baskets+evidence are banked):
    python scripts/iwire013_fast_render_audit.py --snapshot-dir <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Repo root on sys.path so ``scripts.*`` / ``src.*`` import exactly as production does.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The render fixes are default-ON in the cert slate; pin them here so the REAL functions actually
# DO their work on the replay (an OFF flag would make a screen a no-op and the validation
# meaningless). ``setdefault`` keeps any explicit operator override.
os.environ.setdefault("PG_RENDER_CHROME_CANARY", "enforce")   # canary verdict is COMPUTED + enforced
os.environ.setdefault("PG_RENDER_CHROME_SCREEN", "1")          # new chrome categories + truncation ON
os.environ.setdefault("PG_SWEEP_DEPTH_LAYER", "1")             # build_depth_layer emits the analytical layer
os.environ.setdefault("PG_SWEEP_KEY_FINDINGS", "1")            # key-findings block ON
os.environ.setdefault("PG_SYNTHESIS_ABSTRACT_CONCLUSION", "1") # abstract/conclusion composition ON
os.environ.setdefault("PG_SWEEP_CONTRADICTS_BLOCK", "1")       # contradicts both-sides block (the render-gate)

# Default thresholds (LAW VI — overridable by CLI). FAIL the run if any VALIDATED check breaches.
_DEFAULT_CHROME_MAX = 5
_DEFAULT_TRUNCATION_MAX = 3
_DEFAULT_CONTRADICTION_NOISE_MAX = 0
_DEFAULT_DEPTH_MIN = 1

_POSTVERIFY_CHECKPOINT = "postverify_checkpoint.json"
_VERIFICATION_DETAILS = "verification_details.json"


@dataclass
class _ReplaySection:
    """Minimal stand-in for a ``SectionResult``, reconstructed from ``verification_details``.

    Carries ONLY the attributes the real render leaves read via ``getattr``
    (``build_key_findings`` / ``build_depth_layer`` / ``build_abstract`` / ``build_conclusion``):
    ``title`` / ``verified_text`` / ``sentences_verified`` / ``dropped_due_to_failure`` /
    ``is_gap_stub``. ``verified_text`` is the section's banked KEPT (strict_verify-passed)
    sentences joined verbatim — the exact prose those leaves lift findings from."""

    title: str
    verified_text: str
    sentences_verified: int
    dropped_due_to_failure: bool = False
    is_gap_stub: bool = False


# ---------------------------------------------------------------------------
# Load + reconstruct
# ---------------------------------------------------------------------------
def load_verification_details(snapshot_dir: Path) -> dict[str, Any]:
    """Load the banked per-sentence verification accounting. Prefer the DATA-ONLY
    ``postverify_checkpoint.json`` (the canonical fast-replay checkpoint); fall back to the
    standalone ``verification_details.json`` sidecar. Fail loud on absence/corruption (LAW II —
    never a silent empty corpus)."""
    cp = snapshot_dir / _POSTVERIFY_CHECKPOINT
    if cp.is_file():
        payload = json.loads(cp.read_text(encoding="utf-8"))
        vd = payload.get("verification_details")
        if isinstance(vd, dict) and vd.get("sections"):
            return vd
    vdp = snapshot_dir / _VERIFICATION_DETAILS
    if vdp.is_file():
        vd = json.loads(vdp.read_text(encoding="utf-8"))
        if isinstance(vd, dict) and vd.get("sections"):
            return vd
    raise FileNotFoundError(
        f"no usable verification accounting in {snapshot_dir} "
        f"({_POSTVERIFY_CHECKPOINT} / {_VERIFICATION_DETAILS} absent or sectionless)"
    )


def reconstruct_sections(verif_details: dict[str, Any]) -> list[_ReplaySection]:
    """Rebuild the per-section render input from the banked verification accounting. Each kept
    sentence already passed strict_verify and carries its inline ``[#ev:...]`` / ``[N]`` token, so
    the joined ``verified_text`` is exactly what ``build_key_findings`` / ``build_depth_layer``
    lift from. A section with zero kept sentences gets ``sentences_verified=0`` so the leaves skip
    it (their gap-stub guard), matching production."""
    sections: list[_ReplaySection] = []
    for s in verif_details.get("sections", []):
        if not isinstance(s, dict):
            continue
        kept = [k.get("sentence", "") for k in (s.get("kept") or []) if isinstance(k, dict)]
        kept = [t for t in kept if t and t.strip()]
        sections.append(
            _ReplaySection(
                title=str(s.get("title") or ""),
                verified_text=" ".join(kept),
                sentences_verified=len(kept),
                dropped_due_to_failure=bool(s.get("dropped_due_to_failure", False)),
            )
        )
    return sections


def _section_body_md(sections: list[_ReplaySection]) -> str:
    """Reconstruct ``sections_concat`` — the body prose the section-level screens operate on:
    one ``### Title`` header + the verbatim verified prose per non-dropped, non-empty section."""
    blocks: list[str] = []
    for sr in sections:
        if sr.dropped_due_to_failure or sr.sentences_verified == 0 or not sr.verified_text.strip():
            continue
        title = sr.title or "Section"
        blocks.append(f"### {title}\n\n{sr.verified_text.strip()}\n")
    return "\n\n".join(blocks) + ("\n\n" if blocks else "")


# ---------------------------------------------------------------------------
# Optional render inputs (present -> validate; absent -> SKIP, never false-green)
# ---------------------------------------------------------------------------
@dataclass
class _OptionalInputs:
    contradictions_path: str | None = None
    bibliography: list[dict] = field(default_factory=list)
    evidence_pool: dict[str, dict] = field(default_factory=dict)
    baskets: list[Any] = field(default_factory=list)


def load_optional_inputs(snapshot_dir: Path) -> _OptionalInputs:
    """Load render inputs that are banked ONLY in a richer snapshot. Each is loaded from THIS
    snapshot dir alone (never another run). Absence is fine — it downgrades the gated check to
    SKIPPED, never a false pass."""
    opt = _OptionalInputs()
    cpath = snapshot_dir / "contradictions.json"
    if cpath.is_file():
        opt.contradictions_path = str(cpath)
    bpath = snapshot_dir / "bibliography.json"
    if bpath.is_file():
        try:
            opt.bibliography = json.loads(bpath.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001 — malformed optional input -> treat as absent
            opt.bibliography = []
    epath = snapshot_dir / "evidence_pool.json"
    if epath.is_file():
        try:
            rows = json.loads(epath.read_text(encoding="utf-8")) or []
            opt.evidence_pool = {
                r["evidence_id"]: r for r in rows if isinstance(r, dict) and r.get("evidence_id")
            }
        except Exception:  # noqa: BLE001
            opt.evidence_pool = {}
    kpath = snapshot_dir / "baskets.json"
    if kpath.is_file():
        try:
            opt.baskets = json.loads(kpath.read_text(encoding="utf-8")) or []
        except Exception:  # noqa: BLE001
            opt.baskets = []
    return opt


# ---------------------------------------------------------------------------
# Render (mirrors run_one_query L11668-11707 — REAL functions, SAME order)
# ---------------------------------------------------------------------------
def assemble_report(
    sections: list[_ReplaySection],
    opt: _OptionalInputs,
    snapshot_dir: Path,
    *,
    skip_depth: bool,
) -> tuple[str, int, int]:
    """Drive composition + render + ALL screens and return ``(report_md, n_key_findings_bullets,
    n_cross_source_synth)``. Calls the REAL leaves in run_one_query's order."""
    import scripts.run_honest_sweep_r3 as R
    from src.polaris_graph.generator.abstract_conclusion import build_abstract, build_conclusion
    from src.polaris_graph.generator.key_findings import build_depth_layer, build_key_findings

    question = "I-wire-013 fast render-replay validation"

    sections_concat = _section_body_md(sections)

    # 1) Key Findings (composition) — first verified sentence per section.
    key_findings = build_key_findings(sections)

    # 2) Depth: optional bounded cross-source synthesis pass + the per-section analytical layer.
    synth_findings = _run_depth_synthesis(sections, opt, skip_depth=skip_depth)
    depth_layer = build_depth_layer(sections, synthesized_findings=synth_findings)

    # 3) Chrome screen on the Key-Findings bullets (real fix).
    key_findings = R._screen_key_findings_chrome(key_findings)

    # 4) Off-topic / chrome section screen + dangling-crossref strip on the section body.
    placeholder_nums = R._placeholder_bib_nums(opt.bibliography or [])
    sections_concat = R._screen_offtopic_chrome_sections(sections_concat, placeholder_nums)
    sections_concat = R._strip_dangling_gap_crossref(sections_concat, str(snapshot_dir))

    # 5) Contradiction render-gate: the CONTRADICTS both-sides block (skips possible_metric_mismatch
    #    predicates, L2464) + the magnitude-range correction. Both read contradictions.json.
    methods = ""
    if opt.contradictions_path:
        methods += R._render_contradicts_block(opt.contradictions_path)
        sections_concat = R._correct_contradiction_magnitude_range(
            sections_concat, opt.contradictions_path
        )

    # 6) Abstract (front) + Conclusion (end) composition.
    abstract_md = build_abstract(sections)
    conclusion_md = build_conclusion(sections)

    # 7) Final assembly (body order verbatim from run_one_query L11692) + header-sanity screen.
    body = key_findings + sections_concat + depth_layer + methods
    final_report = R.assemble_report_md(
        f"# Research report: {question}\n\n",
        abstract_md,
        body,
        conclusion_md,
        dedup_enabled=True,
    )
    final_report = R._screen_garbled_headers(final_report)

    n_kf = sum(1 for ln in key_findings.split("\n") if ln.lstrip().startswith("- "))
    return final_report, n_kf, len(synth_findings)


def _run_depth_synthesis(
    sections: list[_ReplaySection], opt: _OptionalInputs, *, skip_depth: bool
) -> list[str]:
    """The bounded cross-source synthesis pass (depth_synthesis.synthesize_cross_source_findings).
    Runs ONLY when ``--skip-depth`` is off AND the inputs it needs (baskets + evidence_pool) are
    banked in the snapshot. Otherwise returns ``[]`` (the per-section depth layer still renders, so
    depth_grounded_findings stays >=1 from key_findings). Fail-open: a synthesis error never aborts
    the validator (it is additive)."""
    if skip_depth or not opt.baskets or not opt.evidence_pool:
        return []
    try:
        from src.polaris_graph.generator.depth_synthesis import (
            bib_num_by_evidence_id,
            depth_synthesis_pre_pass,
            make_depth_synthesizer,
            synthesize_cross_source_findings,
        )
        from src.polaris_graph.generator.provenance_generator import strict_verify

        async def _go() -> list[str]:
            precomputed = await depth_synthesis_pre_pass(opt.baskets, opt.evidence_pool)
            return synthesize_cross_source_findings(
                opt.baskets,
                opt.evidence_pool,
                synthesizer=make_depth_synthesizer(precomputed),
                verify_fn=strict_verify,
                bib_num_by_evidence_id=bib_num_by_evidence_id(opt.bibliography or []),
            )

        return list(asyncio.run(_go()) or [])
    except Exception as exc:  # noqa: BLE001 — additive synthesis; never abort the validator
        print(f"[depth-synthesis] skipped (fail-open): {exc}")
        return []


# ---------------------------------------------------------------------------
# §-1.1 audit (REAL predicates) on the EMITTED report.md
# ---------------------------------------------------------------------------
def audit_report(
    report_md: str,
    opt: _OptionalInputs,
    n_key_findings: int,
    n_cross_source: int,
    *,
    cross_source_exercised: bool,
) -> dict[str, Any]:
    """Compute the four §-1.1 render-integrity metrics with the SAME predicates the pipeline uses,
    plus a per-check VALIDATED/SKIPPED label."""
    from src.polaris_graph.generator.key_findings import is_truncated_fragment
    from src.polaris_graph.generator.weighted_enrichment import (
        _report_claim_bullets,
        evaluate_render_chrome_canary,
    )
    from src.polaris_graph.retrieval.contradiction_detector import (
        POSSIBLE_METRIC_MISMATCH_MARKER,
    )

    # (a) chrome-as-claim — the canary's own count (NOT a parallel reimplementation).
    canary = evaluate_render_chrome_canary(report_md)
    chrome_count = int(canary["chrome_claim_bullets"])

    # (b) truncation — claim bullets carrying an unambiguous mid-word / cut-span marker.
    bullets = _report_claim_bullets(report_md)
    truncation_count = sum(1 for b in bullets if is_truncated_fragment(b))

    # (c) contradiction NOISE — a possible_metric_mismatch rendered INSIDE the CONTRADICTS headline
    #     both-sides block (where it would assert an UNCONFIRMED mismatch as a settled contradiction,
    #     the lethal §-1.1 case the I-wire-013 render-gate at _render_contradicts_block:L2464 removes).
    #     SCOPED to ``- CONTRADICTS:`` lines deliberately: the SAME marker rendered in the numeric /
    #     qualitative DISCLOSURE block is a CORRECT §-1.3 disclosure (kept, never dropped) — counting
    #     whole-report markers would false-flag those legitimate disclosures. VALIDATED only when
    #     contradictions.json is present (else no CONTRADICTS block is rendered and a 0 proves nothing).
    contradiction_validated = bool(opt.contradictions_path)
    contradiction_noise = sum(
        line.count(POSSIBLE_METRIC_MISMATCH_MARKER)
        for line in report_md.split("\n")
        if line.lstrip().startswith("- CONTRADICTS:")
    )

    # (d) depth — grounded cross-source synthesis findings + key-findings bullets. The cross-source
    #     leg is EXERCISED only when the depth-synthesis pass actually ran (baskets + evidence banked
    #     AND --skip-depth off). Baskets are persisted to NO banked artifact in-tree, so on a standard
    #     checkpoint the cross-source fix is STRUCTURALLY unvalidatable by this short test — only the
    #     key-findings depth leg is. Surfaced explicitly so a depth PASS carried purely by key_findings
    #     is never mistaken for validation of the cross-source synthesis fix.
    depth_grounded = n_cross_source + n_key_findings

    return {
        "chrome": {
            "count": chrome_count,
            "total_claim_bullets": int(canary["total_claim_bullets"]),
            "rate": canary["chrome_as_claim_rate"],
            "canary_verdict": canary["verdict"],
            "validated": True,
        },
        "truncation": {"count": truncation_count, "validated": True},
        "contradiction": {"count": contradiction_noise, "validated": contradiction_validated},
        "depth": {
            "count": depth_grounded,
            "cross_source": n_cross_source,
            "key_findings": n_key_findings,
            "validated": True,
            "cross_source_exercised": cross_source_exercised,
        },
    }


def evaluate_thresholds(audit: dict[str, Any], args: argparse.Namespace) -> tuple[bool, list[str]]:
    """Apply the FAIL-LOUD thresholds. A check only forces FAIL when it was VALIDATED. SKIPPED
    checks are surfaced but never silently pass as a green — they make the overall verdict
    ``PASS (partial)``."""
    failures: list[str] = []
    if audit["chrome"]["count"] > args.chrome_max:
        failures.append(f"chrome_as_claim={audit['chrome']['count']} > {args.chrome_max}")
    if audit["truncation"]["count"] > args.truncation_max:
        failures.append(f"truncation={audit['truncation']['count']} > {args.truncation_max}")
    if audit["depth"]["count"] < args.depth_min:
        failures.append(f"depth_grounded_findings={audit['depth']['count']} < {args.depth_min}")
    if audit["contradiction"]["validated"] and (
        audit["contradiction"]["count"] > args.contradiction_noise_max
    ):
        failures.append(
            f"contradiction_noise={audit['contradiction']['count']} > {args.contradiction_noise_max}"
        )
    return (not failures), failures


def _print_table(
    audit: dict[str, Any], failures: list[str], skipped: list[str], args: argparse.Namespace
) -> None:
    def verdict(ok: bool, validated: bool) -> str:
        if not validated:
            return "SKIPPED (input absent)"
        return "PASS" if ok else "FAIL"

    print("\n=== I-wire-013 fast render-replay sec-1.1 audit ===")
    print(f"  (a) chrome-as-claim    : {audit['chrome']['count']:>4}  "
          f"({audit['chrome']['count']}/{audit['chrome']['total_claim_bullets']} bullets, "
          f"rate={audit['chrome']['rate']}, canary={audit['chrome']['canary_verdict']})  "
          f"-> {verdict(audit['chrome']['count'] <= args.chrome_max, True)}")
    print(f"  (b) truncation         : {audit['truncation']['count']:>4}  "
          f"-> {verdict(audit['truncation']['count'] <= args.truncation_max, True)}")
    cval = audit["contradiction"]["validated"]
    print(f"  (c) contradiction_noise: {audit['contradiction']['count']:>4}  "
          f"(possible_metric_mismatch in '- CONTRADICTS:' lines)  "
          f"-> {verdict(audit['contradiction']['count'] <= args.contradiction_noise_max, cval)}")
    xs = "exercised" if audit["depth"]["cross_source_exercised"] else "NOT exercised (baskets unbanked)"
    print(f"  (d) depth_grounded     : {audit['depth']['count']:>4}  "
          f"(cross_source={audit['depth']['cross_source']} [{xs}] + key_findings={audit['depth']['key_findings']})  "
          f"-> {verdict(audit['depth']['count'] >= args.depth_min, True)}")
    if skipped:
        print(f"  NOT EXERCISED on this snapshot: {'; '.join(skipped)}")
    if failures:
        print(f"  FAILURES: {'; '.join(failures)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I-wire-013 fast render-replay validator + audit")
    parser.add_argument("--snapshot-dir", type=Path, default=Path("outputs/iwire013_validate_local"),
                        help="dir holding postverify_checkpoint.json (+ optional sidecars)")
    parser.add_argument("--out", type=Path, default=None,
                        help="where to write the replayed report.md (default: <snapshot-dir>/iwire013_replay_report.md)")
    parser.add_argument("--skip-depth", action="store_true",
                        help="skip the bounded depth-synthesis network pass (pure-deterministic, instant)")
    parser.add_argument("--chrome-max", type=int, default=_DEFAULT_CHROME_MAX)
    parser.add_argument("--truncation-max", type=int, default=_DEFAULT_TRUNCATION_MAX)
    parser.add_argument("--contradiction-noise-max", type=int, default=_DEFAULT_CONTRADICTION_NOISE_MAX)
    parser.add_argument("--depth-min", type=int, default=_DEFAULT_DEPTH_MIN)
    args = parser.parse_args(argv)

    snapshot_dir = args.snapshot_dir.resolve()
    out_path = (args.out or (snapshot_dir / "iwire013_replay_report.md")).resolve()

    print(f"[validate] snapshot_dir={snapshot_dir}")
    verif_details = load_verification_details(snapshot_dir)
    sections = reconstruct_sections(verif_details)
    opt = load_optional_inputs(snapshot_dir)
    print(f"[validate] sections={len(sections)} "
          f"(verified={sum(1 for s in sections if s.sentences_verified)}); "
          f"contradictions.json={'yes' if opt.contradictions_path else 'NO'}; "
          f"bibliography={len(opt.bibliography)}; baskets={len(opt.baskets)}; skip_depth={args.skip_depth}")

    cross_source_exercised = bool(not args.skip_depth and opt.baskets and opt.evidence_pool)
    report_md, n_kf, n_synth = assemble_report(sections, opt, snapshot_dir, skip_depth=args.skip_depth)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"[validate] wrote {out_path} ({len(report_md)} bytes)")

    audit = audit_report(
        report_md, opt, n_kf, n_synth, cross_source_exercised=cross_source_exercised
    )
    # Loudly enumerate the headline I-wire-013 checks NOT exercised on this snapshot (inputs absent)
    # so a partial PASS is never over-trusted (operator reads by ear).
    not_exercised: list[str] = []
    if not audit["contradiction"]["validated"]:
        not_exercised.append("contradiction render-gate (no contradictions.json for this run_id)")
    if not audit["depth"]["cross_source_exercised"]:
        not_exercised.append("cross-source depth synthesis (baskets persisted to no artifact)")

    ok, failures = evaluate_thresholds(audit, args)
    _print_table(audit, failures, not_exercised, args)

    if not ok:
        print("\n[validate] OVERALL: FAIL")
        return 1
    if not_exercised:
        print(
            "\n[validate] OVERALL: PASS (PARTIAL) - validated chrome + truncation + key-findings depth "
            "ONLY. NOT exercised on this snapshot: " + "; ".join(not_exercised)
            + ". These require a richer checkpoint (contradictions.json + persisted baskets) or a full run."
        )
        return 0
    print("\n[validate] OVERALL: PASS (all four checks validated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
