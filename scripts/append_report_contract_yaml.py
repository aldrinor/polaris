"""One-shot utility to append the V30 Report Contract YAML block to
clinical.yaml. Idempotent: if the contract header is already present,
does nothing. Delete after M-54 lands.
"""
from __future__ import annotations

from pathlib import Path

YAML_PATH = Path("config/scope_templates/clinical.yaml")
CONTRACT_HEADER_MARKER = "per_query_report_contract:"

CONTRACT_YAML = """

# -------------------------------------------------------------------
# M-54 (2026-04-23): V30 Report Contract Architecture.
# Codex V30 plan pass-1 CONDITIONAL-no-blockers.
#
# per_query_report_contract defines the MANDATORY CONTENT MODEL for
# each research-question slug. Every required entity has an explicit
# rendering slot, every slot has required fields, and the pipeline
# commits to either FILL the slot with field-level structured data OR
# emit explicit "field not extractable" language (M-60). No silent
# omission.
#
# Entity types supported at M-54 schema level:
#   pivotal_trial     - named clinical trial with primary publication
#   mechanism_primary - pharmacology primary (clamp/PK/receptor study)
#   regulatory        - jurisdiction-specific label / guidance / monograph
#   (extensible; compiler must not hard-code these - see M-62)
# -------------------------------------------------------------------
per_query_report_contract:
  clinical_tirzepatide_t2dm:
    schema_version: "v30.1"

    required_entities:
      - id: surpass_1_primary
        type: pivotal_trial
        anchor: SURPASS-1
        doi: 10.1016/S0140-6736(21)01324-6
        pmid: 34186022
        journal: Lancet
        year: 2021
        population_scope: direct
        required_fields:
          - N
          - population
          - comparator
          - baseline_hba1c
          - primary_endpoint
          - timepoint
          - etd_with_uncertainty
          - safety_signal
          - study_design
          - sponsor
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_1

      - id: surpass_2_primary
        type: pivotal_trial
        anchor: SURPASS-2
        doi: 10.1056/NEJMoa2107519
        pmid: 34010531
        journal: NEJM
        year: 2021
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, primary_endpoint, timepoint, etd_with_uncertainty, safety_signal, study_design, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_2

      - id: surpass_3_primary
        type: pivotal_trial
        anchor: SURPASS-3
        doi: 10.1016/S0140-6736(21)01443-4
        pmid: 34370970
        journal: Lancet
        year: 2021
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, primary_endpoint, timepoint, etd_with_uncertainty, safety_signal, study_design, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_3

      - id: surpass_4_primary
        type: pivotal_trial
        anchor: SURPASS-4
        doi: 10.1016/S0140-6736(21)01997-1
        pmid: 34600604
        journal: Lancet
        year: 2021
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, primary_endpoint, timepoint, etd_with_uncertainty, durability_104wk, safety_signal, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_4

      - id: surpass_5_primary
        type: pivotal_trial
        anchor: SURPASS-5
        doi: 10.1001/jama.2022.0078
        pmid: 35103765
        journal: JAMA
        year: 2022
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, primary_endpoint, timepoint, etd_with_uncertainty, safety_signal, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_5

      - id: surpass_6_primary
        type: pivotal_trial
        anchor: SURPASS-6
        doi: 10.1001/jama.2023.0023
        pmid: 36744281
        journal: JAMA
        year: 2023
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, primary_endpoint, timepoint, etd_with_uncertainty, safety_signal, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surpass_6

      - id: surpass_cvot_primary
        type: pivotal_trial
        anchor: SURPASS-CVOT
        doi: 10.1056/NEJMoa2509079
        pmid: null
        journal: NEJM
        year: 2025
        population_scope: direct
        required_fields: [N, population, comparator, primary_endpoint, timepoint, hr_with_uncertainty, noninferiority_p, superiority_p, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_cvot

      - id: surmount_2_primary
        type: pivotal_trial
        anchor: SURMOUNT-2
        doi: 10.1016/S0140-6736(23)01200-X
        pmid: 37385275
        journal: Lancet
        year: 2023
        population_scope: direct
        required_fields: [N, population, comparator, baseline_hba1c, baseline_weight, primary_endpoint, timepoint, etd_with_uncertainty, safety_signal, sponsor]
        min_fields_for_completion: 5
        rendering_slot: efficacy_surmount_2

      - id: thomas_clamp_2022
        type: mechanism_primary
        anchor: Thomas-clamp
        doi: 10.1016/S2213-8587(22)00041-1
        pmid: 35364022
        journal: Lancet Diabetes Endocrinol
        year: 2022
        required_fields: [m_value_pct_increase, first_phase_insulin_secretion, second_phase_insulin_secretion, half_life_days, participant_n, clamp_duration_weeks, glucagon_suppression_pct]
        min_fields_for_completion: 3
        rendering_slot: mechanism_clamp

      - id: fda_mounjaro_label
        type: regulatory
        jurisdiction: FDA
        label_name: Mounjaro
        url_pattern: accessdata.fda.gov
        required_fields: [indications, boxed_warning, contraindications, warnings_and_precautions, dosing]
        min_fields_for_completion: 3
        rendering_slot: regulatory_fda_t2d

      - id: fda_zepbound_label
        type: regulatory
        jurisdiction: FDA
        label_name: Zepbound
        url_pattern: accessdata.fda.gov
        required_fields: [indications, bmi_thresholds, boxed_warning, contraindications, dosing]
        min_fields_for_completion: 3
        rendering_slot: regulatory_fda_obesity

      - id: ema_mounjaro_epar
        type: regulatory
        jurisdiction: EMA
        label_name: Mounjaro
        url_pattern: ema.europa.eu
        required_fields: [indications, pediatric_indication, contraindications, additional_monitoring, osa_extension]
        min_fields_for_completion: 3
        rendering_slot: regulatory_ema

      - id: nice_ta924_t2d
        type: regulatory
        jurisdiction: NICE
        label_name: TA924
        url_pattern: nice.org.uk/guidance/ta924
        required_fields: [triple_therapy_criteria, bmi_threshold, ethnic_adjusted_thresholds, occupational_implications, commercial_arrangement]
        min_fields_for_completion: 3
        rendering_slot: regulatory_nice_t2d

      - id: nice_ta1026_obesity
        type: regulatory
        jurisdiction: NICE
        label_name: TA1026
        url_pattern: nice.org.uk/guidance/ta1026
        required_fields: [indication, managed_access_agreement, specialist_services_requirement]
        min_fields_for_completion: 2
        rendering_slot: regulatory_nice_obesity

      - id: hc_mounjaro_monograph
        type: regulatory
        jurisdiction: HC
        label_name: Mounjaro Canadian Product Monograph
        url_pattern: pdf.hres.ca
        required_fields: [indications, serious_warnings_box, contraindications, dosing]
        min_fields_for_completion: 3
        rendering_slot: regulatory_hc

    rendering_slots:
      efficacy_surpass_1:
        section: Efficacy
        subsection_title: "SURPASS-1 (Rosenstock et al., Lancet 2021)"
        ordering: 1
        required: true
      efficacy_surpass_2:
        section: Efficacy
        subsection_title: "SURPASS-2 (Frias et al., NEJM 2021)"
        ordering: 2
        required: true
      efficacy_surpass_3:
        section: Efficacy
        subsection_title: "SURPASS-3 (Ludvik et al., Lancet 2021)"
        ordering: 3
        required: true
      efficacy_surpass_4:
        section: Efficacy
        subsection_title: "SURPASS-4 (Del Prato et al., Lancet 2021)"
        ordering: 4
        required: true
      efficacy_surpass_5:
        section: Efficacy
        subsection_title: "SURPASS-5 (Dahl et al., JAMA 2022)"
        ordering: 5
        required: true
      efficacy_surpass_6:
        section: Efficacy
        subsection_title: "SURPASS-6 (Rosenstock et al., JAMA 2023)"
        ordering: 6
        required: true
      efficacy_cvot:
        section: Efficacy
        subsection_title: "SURPASS-CVOT (Nicholls et al., NEJM 2025)"
        ordering: 7
        required: true
      efficacy_surmount_2:
        section: Efficacy
        subsection_title: "SURMOUNT-2 T2D+Obesity (Garvey et al., Lancet 2023)"
        ordering: 8
        required: true
      mechanism_clamp:
        section: Mechanism
        subsection_title: "Human hyperinsulinemic-euglycemic clamp (Thomas et al., Lancet D&E 2022)"
        ordering: 1
        required: true
      regulatory_fda_t2d:
        section: Regulatory
        subsection_title: "US FDA (Mounjaro for T2D)"
        ordering: 1
        required: true
      regulatory_fda_obesity:
        section: Regulatory
        subsection_title: "US FDA (Zepbound for chronic weight management)"
        ordering: 2
        required: true
      regulatory_ema:
        section: Regulatory
        subsection_title: "EU EMA (Mounjaro including pediatric >=10 yrs)"
        ordering: 3
        required: true
      regulatory_nice_t2d:
        section: Regulatory
        subsection_title: "UK NICE TA924 (tirzepatide for T2D access criteria)"
        ordering: 4
        required: true
      regulatory_nice_obesity:
        section: Regulatory
        subsection_title: "UK NICE TA1026 (managed access for obesity)"
        ordering: 5
        required: true
      regulatory_hc:
        section: Regulatory
        subsection_title: "Health Canada Product Monograph"
        ordering: 6
        required: true
"""


def main() -> int:
    text = YAML_PATH.read_text(encoding="utf-8")
    if CONTRACT_HEADER_MARKER in text:
        print(f"[skip] {CONTRACT_HEADER_MARKER} already present")
        return 0
    YAML_PATH.write_text(text + CONTRACT_YAML, encoding="utf-8")
    print(f"[ok] Contract appended to {YAML_PATH}")
    # Verify
    import yaml
    with YAML_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    ctr = data.get("per_query_report_contract", {}).get(
        "clinical_tirzepatide_t2dm", {}
    )
    print(f"    schema_version: {ctr.get('schema_version')}")
    print(f"    entities: {len(ctr.get('required_entities', []))}")
    print(f"    slots: {len(ctr.get('rendering_slots', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
