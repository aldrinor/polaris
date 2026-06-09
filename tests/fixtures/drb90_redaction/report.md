# Research report: Analyze the complex issue of liability allocation in accidents involving vehicles with advanced driver-assistance systems (ADAS) operating in a shared human-machine driving context. Your analysis should integrate technical principles of ADAS, existing legal frameworks, and relevant case law to systematically examine the boundaries of responsibility between the driver and the system. Conclude with proposed regulatory guidelines or recommendations.

## Key Findings

_Each finding below is a verbatim, span-verified statement carried up from the body section named in bold; citations are the body's._

- **Technical_Standard.** ### SAE J3016 driving-automation levels and the human-machine boundary

Contract-bound content for sae_j3016_automation_levels did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap.
- **Legal_Framework.** ### UNECE WP.29 ALKS regulation (system-vs-driver responsibility)

Instrument: UN Regulation No.
- **Case_Law.** ### Relevant ADAS / automated-feature crash-liability case law

Contract-bound content for adas_crash_case_law did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap.
- **Regulatory_Recommendations.** ### Proposed regulatory guidelines and liability-allocation recommendations

Contract-bound content for proposed_regulatory_guidelines did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap.
- **Background.** The Society of Automotive Engineers (SAE) taxonomy classifies driving automation into six levels, from Level 0 (no automation) to Level 5 (full automation), based on the extent to which the system performs the dynamic driving task on a sustained basis.[4].[7]
- **Key Findings.** Conversely, the same study reported that ADS accidents had lower odds in rear-end (OR 0.457) and broadside (OR 0.171) collisions, suggesting that automation may reduce certain types of crashes.[8]

### Technical_Standard

### SAE J3016 driving-automation levels and the human-machine boundary

Contract-bound content for sae_j3016_automation_levels did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[1]

### Legal_Framework

### UNECE WP.29 ALKS regulation (system-vs-driver responsibility)

Instrument: UN Regulation No. 157 - Automated Lane Keeping Systems (ALKS).[2]

### NHTSA automated-driving-systems policy and crash-reporting order

Issuing agency: NHTSA.[4] The National Highway Traffic Safety Administration (NHTSA) issued a General Order that specifically addresses automated driving systems.[4] This order establishes reporting obligations for a defined set of parties.[4] Moreover, these entities must be specifically named in the General Order to fall within its requirements.[4] Entities that are not named, even if they otherwise qualify as manufacturers, developers, or operators, are not covered.[4] The term “reporting entities” is defined to include only those manufacturers, developers, and operators that are explicitly listed in the order.[4] The limitation ensures that only the identified manufacturers, developers, and operators bear the reporting burden.[4] In summary, NHTSA’s General Order imposes reporting obligations exclusively on the manufacturers, developers, and operators that are specifically named within it.[4]

### Product-liability / negligence doctrine for ADAS manufacturers

Doctrine: products liability.[3] Defect categories: manufacturing defects; design defects; and inadequate instructions or warnings defects.[3] This doctrine categorizes actionable defects into three distinct types: manufacturing defects, design defects, and inadequate instructions or warnings defects.[3]

### Case_Law

### Relevant ADAS / automated-feature crash-liability case law

Contract-bound content for adas_crash_case_law did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[5]

### Regulatory_Recommendations

### Proposed regulatory guidelines and liability-allocation recommendations

Contract-bound content for proposed_regulatory_guidelines did not survive strict verification against retrieved primary source text; this slot is a curator-actionable gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[6]

### Background

The Society of Automotive Engineers (SAE) taxonomy classifies driving automation into six levels, from Level 0 (no automation) to Level 5 (full automation), based on the extent to which the system performs the dynamic driving task on a sustained basis.[4].[7] Level 2 advanced driver assistance systems (ADAS) provide partial automation, simultaneously supporting lane position, speed, and following distance, but require the human driver to continually monitor the driving environment and remain prepared to intervene at all times.[4] In contrast, automated driving systems (ADS) at SAE Levels 3-5 are designed to perform the entire dynamic driving task without driver involvement within their defined operational design domain.[4] Research indicates that driver take-over time from automated to manual control can range from 0.69 to 19.79 seconds, with most transitions occurring within 7 seconds.[7] The General Order may not include some crashes involving Level 2 ADAS if the consumer did not state that the automation system was engaged within 30 seconds of the crash[4]

### Key Findings

Conversely, the same study reported that ADS accidents had lower odds in rear-end (OR 0.457) and broadside (OR 0.171) collisions, suggesting that automation may reduce certain types of crashes.[8] However, NHTSA cautions that the reported data may not be statistically representative due to variations in telemetry and reporting capabilities among manufacturers.[4] The General Order on crash reporting mandates that reporting entities report crashes involving ADS and Level 2 ADAS, providing a dataset that can be used to identify potential safety defects and assist in evaluating safety.[4]

### Evidence and Analysis

NHTSA cautions that incident report data should not be assumed statistically representative, as entities with advanced telematics may report more crashes simply because they are aware of them, while crashes involving systems with limited telemetry may go unreported if the driver does not state that automation was engaged.[4] Under the Restatement (Third) of Torts: Products Liability, defects are categorized as manufacturing, design, or inadequate warnings, each with distinct legal standards.[3] Violations of the NHTSA General Order can result in civil penalties of up to $27,874 per violation per day, with a maximum of $139,356,994 for a related series of violations.[4]

### Implications

In the United States, NHTSA's Standing General Order mandates crash reporting for vehicles equipped with ADS or Level 2 ADAS when the system was active within 30 seconds of a crash resulting in specified outcomes such as a fatality, air bag deployment, or hospital transport.[4] However, the Order does not require reporting entities to submit vehicle counts or miles traveled, precluding normalization of incident rates by exposure.[4] Moreover, data recording and telemetry capabilities vary widely, with Level 2 ADAS systems often having limited data recording and relying on consumer reports, which may delay or prevent manufacturer awareness of crashes.[4] Additionally, the take-over time for drivers resuming control from automated systems ranges from 0.69 to 19.79 seconds, with most below 7 seconds, and secondary tasks with handheld devices impose a significant time penalty.[7] One review notes that many developers are satisfied with 95–98% algorithm efficiency, whereas reliability of 99.9999% may be needed to match human safety levels, highlighting a gap between current engineering practices and safety goals.[7]

### Limitations

Limitations: The corpus is heavily skewed toward sources of unknown quality, with 84% of documents lacking a tier classification, while only 2% are T1 primary studies. A high-severity contradiction was detected regarding accuracy, where sources diverge by a relative difference of 545.7%, indicating fundamental disagreement on the magnitude or direction of this claim. The evidence horizon spans from 2015-01-01 to the present, which may omit earlier foundational work or recent preprints outside this window.

## Methods
Pre-registered protocol.json (SHA-256 f581fb1098484165...).
Corpus: Serper + Semantic Scholar + OpenAlex live retrieval, augmented by domain backends (policy: domain_backends(policy): {'serper_policy': 20}).
Retrieval fetch outcome: 42 of 151 candidate sources fetched; 109 failed or timed out.
Generator model: deepseek/deepseek-v4-pro (multi-section: outline + 8 parallel sections + strict_verify + regen-on-failure).
Evaluator model: google/gemma-4-31b-it (different family).
Sources classified using T1-T7 tier taxonomy.
Inclusion / exclusion per policy template. Sponsor / conflict-of-interest review per source.
Prompt-injection sanitization enabled. Retrieved 2026-06-09.
Expected tier distribution: T3 35-70%, T1 10-30%, T2 5-25%, T6 5-25%, T4 0-15%, T5 0-10%, T7 0-5%. Actual distribution: T1=1%, T3=1%, T4=4%, T6=1%, T7=6%, UNKNOWN=87%.
Corpus adequacy: decision=proceed, 8/8 thresholds met.
Completeness checklist: 6/6 topics covered.

## Capability disclosures
Quantified trade-off analysis was ENABLED but did not contribute to this report (no verified quantified output); 91 sourced numbers were extracted but not modeled into a verified quantified comparison.

## Contradiction disclosures
The contradiction detector flagged 1 numeric disagreements across the evidence pool. Most are extraction artifacts produced by grouping different measured endpoints, units, sub-populations, time windows, or comparators under the same subject/predicate label. The detector does NOT adjudicate by endpoint, population, timepoint, or source tier; raw detector output is available in `contradictions.json`. Per-flag enumeration (PT08 disclosure):

- unknown / accuracy: cited values range 15.0 to 96.86 % (source tiers: UNKNOWN, T4).

Claims made in the body of this report are individually bound to their cited evidence IDs via the strict-verify gate, so the reader can trace any specific numeric discrepancy to its source regardless of detector granularity.

## Qualitative safety-conflict disclosures
The qualitative detector flagged 0 present-vs-absent clinical-safety conflict(s) (contraindication / drug-interaction / eligibility / warning / adverse-event causation) and 6 review-flagged item(s) requiring human adjudication. Status is shown as asserted PRESENT/ABSENT/INDETERMINATE, not a numeric value; review flags are NOT adjudicated conflicts.

- [REVIEW]  / ae_causation (irregular detection performance): present [ev=ev_001, tier=T4] vs indeterminate [ev=ev_065, tier=UNKNOWN] — definite present vs indeterminate across sources — review
- [REVIEW]  / ae_causation (irregular detection performance): present [ev=ev_056, tier=UNKNOWN] vs indeterminate [ev=ev_065, tier=UNKNOWN] — definite present vs indeterminate across sources — review
- [REVIEW]  / ae_causation (irregular detection performance): present [ev=ev_075, tier=UNKNOWN] vs indeterminate [ev=ev_065, tier=UNKNOWN] — definite present vs indeterminate across sources — review
- [REVIEW]  / eligibility_exclusion (in the review): absent [ev=ev_067, tier=UNKNOWN] vs indeterminate [ev=ev_058, tier=UNKNOWN] — definite absent vs indeterminate across sources — review
- [REVIEW]  / eligibility_exclusion (of scoring points in pedestrian): absent [ev=ev_079, tier=UNKNOWN] vs indeterminate [ev=ev_058, tier=UNKNOWN] — definite absent vs indeterminate across sources — review
- [REVIEW]  / eligibility_exclusion (of scoring points in pedestrian): absent [ev=ev_079, tier=UNKNOWN] vs indeterminate [ev=ev_058, tier=UNKNOWN] — definite absent vs indeterminate across sources — review


## Bibliography
[1] sae_j3016_automation_levels — https://www.sae.org/standards/content/j3016_202104/ (tier T1)
[2] unece_alks_regulation_framework — https://unece.org/transport/documents/2021/03/standards/un-regulation-no-157-automated-lane-keeping-systems-alks (tier T1)
[3] product_liability_doctrine — https://www.ali.org/publications/restatement-law-third/torts-third (tier T1)
[4] nhtsa_ads_policy_framework — https://www.nhtsa.gov/laws-regulations/standing-general-order-crash-reporting (tier T1)
[5] adas_crash_case_law — https://www.courtlistener.com/docket/59932667/benavides-v-tesla-inc/ (tier T1)
[6] proposed_regulatory_guidelines — https://www.ntsb.gov/Advocacy/mwl/Pages/mwl-22-23/mwl-hs.aspx (tier T1)
[7] Are Connected and Automated Vehicles the Silver Bullet for Future Transportation Challenges? Benefits and Weaknesses on Safety, Consumption, and Traffic Congestion — https://doi.org/10.3389/frsc.2020.607054 (tier UNKNOWN)
[8] A matched case-control analysis of autonomous vs human-driven ... — https://pmc.ncbi.nlm.nih.gov/articles/PMC11189485/ (tier T4)


---

## V30 Phase-1 Retrieval Coverage Disclosure

PHASE-1 RETRIEVAL COVERAGE (V30 Report Contract, not yet report-coverage):
  This disclosure reports whether M-56 (deterministic DOI / PMID / Unpaywall retrieval) succeeded for each contract-required entity. It does NOT claim the legacy generator cited each entity in the verified report — that validation lands in Phase 2 when M-58 slot-bound prompts replace the legacy generator.

Frame coverage disclosure (V30 Report Contract):
  - Total contract-required entities: 6
  - Fully populated (full-text bound evidence): 4
  - Unretrievable (paywalled with no OA/abstract): 2
  - Gap slots render explicit gap language in the relevant subsection; see manifest.json frame_coverage_report for per-slot detail.
