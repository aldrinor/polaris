"""PROVE-FIRST probe: can we faithfully replay apply_d8_release_policy over the saved
beatboth8/drb_76 data and reproduce the saved held_reasons EXACTLY?

Reuses the production helpers (load_required_entities, validate_entity_severity,
load_d8_policy_config, apply_d8_release_policy) — NO re-implementation, so no drift.
If this reproduces ['d8_unsupported_residual_below_coverage',
'd8_s0_must_cover_missing:contraindications','d8_pending_rewrite'] and coverage 0.4,
the reconstruction is faithful and the I-perm-009 harness can be built around it.
"""

import json
from pathlib import Path

import yaml

from src.polaris_graph.roles.native_gate_b_inputs import (
    load_required_entities,
    validate_entity_severity,
    _KEY_ENTITY_ID,
)
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    apply_d8_release_policy,
    load_d8_policy_config,
)

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs" / "audits" / "beatboth8" / "drb_76"
SLUG = "drb_76_gut_microbiota_crc"
TEMPLATE_PATH = ROOT / "config" / "scope_templates" / "clinical.yaml"


def main() -> None:
    audit_map = json.loads((RUN / "four_role_claim_audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
    four_role = manifest["four_role_evaluation"]
    final_verdicts = four_role["final_verdicts"]
    saved_held = four_role["held_reasons"]
    saved_cov = four_role["coverage_fraction"]

    template = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    d8_config = load_d8_policy_config()

    entities = load_required_entities(template, SLUG)
    required_element_ids = [e[_KEY_ENTITY_ID] for e in entities]
    required_s0 = set()
    sev_by_entity = {}
    for e in entities:
        sev, s0 = validate_entity_severity(e, d8_config)
        sev_by_entity[e[_KEY_ENTITY_ID]] = (sev, s0)
        if s0 is not None:
            required_s0.add(s0)
    required_s0 = sorted(required_s0)

    # Reconstruct D8 rows from saved final_verdicts + audit_map (exact, saved ground truth).
    d8_rows = []
    for cid, verdict in final_verdicts.items():
        a = audit_map[cid]
        d8_rows.append(
            D8ClaimRow(
                claim_id=cid,
                severity=a["severity"],
                verdict=verdict,
                s0_categories=list(a.get("s0_categories", [])),
            )
        )

    # Covered = required elements satisfied by a VERIFIED claim (matches builder semantics:
    # only VERIFIED claims add to coverage).
    covered = set()
    for cid, verdict in final_verdicts.items():
        if verdict == "VERIFIED":
            covered.update(audit_map[cid].get("covered_element_ids", []))
    covered &= set(required_element_ids)
    ledger = CoverageLedger(required_element_ids=required_element_ids, covered_element_ids=covered)

    decision = apply_d8_release_policy(
        d8_rows,
        required_s0_categories=required_s0,
        coverage_ledger=ledger,
        coverage_threshold=d8_config.coverage_threshold,
        rewrite_already_attempted=False,
        prior_fabricated_latched=four_role.get("fabricated_occurrence_latched", False),
    )

    print(f"required_element_ids ({len(required_element_ids)}): {required_element_ids}")
    print(f"required_s0_categories: {required_s0}")
    print(f"covered ({len(covered)}): {sorted(covered)}")
    print(f"reconstructed coverage_fraction: {ledger.fraction():.3f}   saved: {saved_cov}")
    print(f"reconstructed held_reasons: {sorted(decision.held_reasons)}")
    print(f"saved        held_reasons: {sorted(saved_held)}")
    print(f"needs_rewrite reconstructed: {len(decision.needs_rewrite)}   saved: {len(four_role['needs_rewrite'])}")
    cov_ok = abs(ledger.fraction() - saved_cov) < 1e-9
    held_ok = sorted(decision.held_reasons) == sorted(saved_held)
    print(f"\nCOVERAGE MATCH: {cov_ok}")
    print(f"HELD_REASONS MATCH: {held_ok}")
    print(f"BASELINE-LOCK FAITHFUL: {cov_ok and held_ok}")


if __name__ == "__main__":
    main()
