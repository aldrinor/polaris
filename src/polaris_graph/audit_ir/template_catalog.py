"""Curated template catalog (M-10 — Phase B foundation).

Per FINAL_PLAN.md, the curated template router is the Phase B
mitigation for Risk #13 (query-to-template misrouting / unsupported-
query overclaim). Phase B ships with a SINGLE working template
(v30_clinical) plus the routing infrastructure; new templates are
added to this catalog as data, no router-code change required.

The catalog also doubles as the data source for the "supported scope"
page (FINAL_PLAN scope-page reinforcement mitigation): UI surfaces
each entry's display_name, description, and scope_summary so users
understand the bounds before submitting a query.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedTemplate:
    """A supported audit template with metadata for routing + scope display.

    Codex M-10 review fix: signals are split into TWO classes to close
    the false-positive bypass identified in v1:

      drug_keywords   → STRONG signals (specific drug names + drug
                        classes). Required for the ROUTED verdict —
                        no drug-keyword hit means the verdict cannot
                        rise above OPERATOR_REVIEW regardless of
                        exemplar similarity. This is the Risk #13
                        guardrail: a query about supplements,
                        psychotherapy, or non-pharmaceutical
                        interventions cannot accidentally route to
                        v30_clinical just because it shares the
                        question scaffold of an exemplar.

      medical_keywords → BROAD signals (regulatory bodies, trial
                        methodology terms, conditions, generic
                        outcomes, broad medical-domain words).
                        Indicates the query is plausibly medical
                        and merits OPERATOR_REVIEW, but never alone
                        sufficient for ROUTED.

    `scope_keywords` is a property returning the union — kept for
    backwards compat with code that just wants the full bag.

    Attributes:
        template_id: Stable identifier matching a registered JobRunner.
        display_name: Human-readable name shown on the scope page.
        description: One- to two-sentence description.
        scope_summary: Longer scope description; documents IN-scope
                       AND OUT-of-scope per FINAL_PLAN scope-page
                       reinforcement mitigation.
        drug_keywords: Tuple of specific drugs / drug classes. Multi-
                       word entries match as token sets.
        medical_keywords: Tuple of broad medical/clinical-trial/
                          regulatory/condition terms.
        scope_examples: Concrete real-shape positive query exemplars.
    """

    template_id: str
    display_name: str
    description: str
    scope_summary: str
    drug_keywords: tuple[str, ...]
    medical_keywords: tuple[str, ...]
    scope_examples: tuple[str, ...]

    @property
    def scope_keywords(self) -> tuple[str, ...]:
        """Backward-compat: union of drug + medical keywords."""
        return tuple(self.drug_keywords) + tuple(self.medical_keywords)


# ---------------------------------------------------------------------------
# Phase B initial catalog
# ---------------------------------------------------------------------------

_V30_CLINICAL = CuratedTemplate(
    template_id="v30_clinical",
    display_name="Clinical drug audit",
    description=(
        "Audits a drug-condition pair for efficacy, safety, regulatory "
        "status, and contradictions across published evidence."
    ),
    scope_summary=(
        "IN SCOPE: questions about a specific regulated drug (by name "
        "or by drug class) for a specific clinical condition where "
        "regulatory filings, randomized trial data, and meta-analyses "
        "exist. Examples: efficacy of tirzepatide for type 2 diabetes; "
        "safety profile of semaglutide; cardiovascular outcomes of "
        "GLP-1 receptor agonists.\n\n"
        "OUT OF SCOPE: questions about supplements, vitamins, "
        "homeopathy, or other non-regulated interventions; "
        "psychotherapy or other non-pharmaceutical treatments; "
        "clinical practice guideline questions; patient-specific advice; "
        "non-clinical wellness; veterinary; off-label speculation "
        "without published evidence; comparative-effectiveness between "
        "drug classes when both lack head-to-head trials. The router "
        "will surface medical-but-non-drug queries to operator review; "
        "v30_clinical is not the right template for them."
    ),
    # Codex M-10 v2 review fix: drug_keywords are the STRONG gate;
    # ONLY entries here can cross the ROUTED threshold. v1 left
    # umbrella class terms (biologic, biosimilar, monoclonal
    # antibody, receptor agonist) in this list, which let
    # exemplar-shape queries auto-route without a specific named
    # drug — e.g. "Phase 3 trial of biologic for psoriasis" routed
    # at 0.72. v2 demotes those umbrellas to medical_keywords;
    # only specific drug names + sufficiently narrow class
    # abbreviations (GLP-1, SGLT2, DPP-4 — each identifies a small
    # set of known drugs) remain in the STRONG gate.
    drug_keywords=(
        # Specific drug names (small Phase B set; expanded as the
        # template library grows in Phase C).
        "tirzepatide", "semaglutide", "liraglutide", "dulaglutide",
        "exenatide",
        "metformin", "empagliflozin", "dapagliflozin", "canagliflozin",
        "sitagliptin", "saxagliptin",
        "atorvastatin", "rosuvastatin", "simvastatin",
        # Narrow class abbreviations (each identifies a small known
        # set of marketed drugs; a query naming the class is
        # specific enough to audit). The canonical hyphenated form
        # is used; the v7 tokenizer normalizes hyphen-less query
        # forms (GLP1 → "glp 1") so both orthographies match.
        "glp-1", "sglt-2", "dpp-4",
    ),
    # Codex M-10 review fix: medical_keywords cover the broad medical
    # domain — clinical-trial terminology, regulatory framing,
    # conditions, generic outcomes, AND the umbrella drug-class
    # terms that are too generic for the STRONG gate. A
    # medical_keyword hit is NEVER sufficient on its own for ROUTED;
    # it can only push the verdict up to OPERATOR_REVIEW.
    #
    # Codex M-10 v3 review fix: vocabulary expanded substantially
    # to support the alien-token gate (in classifier). Common
    # singular/plural variants and standard clinical query
    # vocabulary are explicitly listed so legitimate variations
    # don't trip the gate. Phase B is conservative: words missing
    # here cause queries to fall to OPERATOR_REVIEW, which is the
    # safe failure mode.
    medical_keywords=(
        # Umbrella drug-class terms (Codex M-10 v2 demote — too
        # generic to anchor ROUTED on their own).
        "biologic", "biologics", "biosimilar", "biosimilars",
        "monoclonal antibody", "monoclonal antibodies",
        "receptor agonist", "receptor antagonist",
        # Pharmacological vocabulary (Codex M-10 v3 — standalone
        # forms so plurals/singulars in a query are recognized).
        "receptor", "receptors",
        "agonist", "agonists", "antagonist", "antagonists",
        "inhibitor", "inhibitors",
        "modulator", "modulators",
        "statin", "statins",
        "ace inhibitor", "ace inhibitors",
        "ssri", "ssris",
        # Trial methodology
        "randomized", "double-blind", "placebo", "placebo-controlled",
        "phase 1", "phase 2", "phase 3", "phase 4",
        "primary endpoint", "secondary endpoint",
        "meta-analysis", "systematic review", "review", "reviews",
        "analysis", "analyses",
        # Regulatory framing
        "fda", "ema", "mhra", "pmda", "regulatory", "approval",
        "indication", "label", "labeling", "post-marketing",
        "clinical trial", "trial", "trials", "clinical",
        # Outcomes / safety / pharmacology
        "efficacy", "effectiveness", "safety", "tolerability",
        "adverse", "adverse event", "adverse events",
        "side effect", "side effects",
        "outcome", "outcomes", "endpoint", "endpoints",
        "composite", "composites", "individual", "individuals",
        "result", "results", "rate", "rates", "ratio", "ratios",
        "response", "responses", "responder", "responders",
        "remission", "relapse", "recurrence",
        "profile", "profiles",
        "mortality", "morbidity",
        "hospitalization", "hospitalizations",
        # Lab / biomarker vocabulary (Codex M-10 v4 additions).
        "hba1c", "ldl", "hdl", "blood pressure",
        "triglyceride", "triglycerides", "cholesterol",
        "apolipoprotein", "apolipoprotein b", "apob",
        "egfr", "albuminuria", "creatinine",
        "weight loss", "weight", "loss", "gain",
        "pharmacology", "pharmacokinetic", "pharmacokinetics",
        "pharmacodynamic", "pharmacodynamics",
        "dose", "doses", "dosage", "dosing", "dose-response",
        # Conditions / clinical contexts
        "diabetes", "diabetic",
        "type 2 diabetes", "type 1 diabetes",
        "diabetes mellitus", "prediabetes", "t2dm", "t1dm",
        "obesity", "obese", "overweight",
        "hypertension", "hypertensive",
        "cardiovascular", "atherosclerosis",
        "heart failure", "hfpef", "hfref",
        "heart attack", "myocardial infarction",
        "atrial fibrillation", "stroke", "arrhythmia",
        "oncology", "cancer", "tumor", "tumors", "malignancy",
        "depression", "anxiety", "ptsd",
        "hypercholesterolemia", "dyslipidemia",
        "chronic kidney disease", "ckd", "esrd",
        "kidney disease", "renal",
        "polycystic ovary syndrome", "pcos",
        "copd", "asthma",
        "rheumatoid arthritis", "arthritis", "osteoarthritis",
        "psoriasis", "eczema", "dermatitis", "lupus",
        # Patient-population vocabulary
        "patient", "patients", "subject", "subjects",
        "participant", "participants", "cohort", "cohorts",
        "population", "populations",
        "adult", "adults", "child", "children",
        "infant", "infants", "neonate", "neonates",
        "adolescent", "adolescents",
        "elderly", "geriatric", "pediatric",
        # Broader medical-domain words
        "drug", "drugs", "treatment", "treatments",
        "therapy", "therapies", "medication", "medications",
        "disease", "diseases", "syndrome", "syndromes",
        "condition", "conditions",
        "study", "studies", "studied",
        "effect", "effects",
        "management", "prevention", "prophylaxis",
        "screening", "monitoring",
        "diagnosis", "diagnostic", "prognosis", "prognostic",
        "assessment", "evaluation",
        "comparison", "comparative", "compared",
        "combined", "combination",
        "maintenance", "induction",
        "chronic", "acute", "mild", "moderate", "severe",
        "primary", "secondary",
        "onset", "duration",
        "guideline", "guidelines", "evidence",
        "long-term", "short-term",
    ),
    # Codex M-10 v2 review fix: every exemplar names a specific drug
    # from drug_keywords. Removed "Phase 3 trial of monoclonal
    # antibody for hypertension" — it had no specific drug and
    # doubled as a routing hazard via the demoted umbrella terms.
    scope_examples=(
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
        "Cardiovascular safety of GLP-1 receptor agonists",
        "Adverse event rates of liraglutide in obesity trials",
        "Empagliflozin cardiovascular outcomes meta-analysis in heart failure",
        "Atorvastatin efficacy for hypercholesterolemia in adults",
        "Dulaglutide phase 3 trial outcomes for type 2 diabetes",
        # Codex M-10 v4 review additions: cover renal-outcomes
        # queries (common Phase B request shape) so they don't fall
        # to operator_review purely because no exemplar has them.
        "Empagliflozin renal outcomes in chronic kidney disease patients",
        "GLP-1 receptor agonists management of obesity in adults",
    ),
)

_V30_CLINICAL_ONCOLOGY = CuratedTemplate(
    template_id="v30_clinical_oncology",
    display_name="Clinical oncology drug audit",
    description=(
        "Audits an oncology drug for indication, mechanism, "
        "efficacy, and safety across regulatory approvals."
    ),
    scope_summary=(
        "IN SCOPE: questions about a specific oncology drug or "
        "regimen for a specific cancer type with published trial "
        "data. Examples: pembrolizumab for non-small cell lung "
        "cancer; CAR-T efficacy in DLBCL; trastuzumab safety in "
        "HER2+ breast cancer.\n\n"
        "OUT OF SCOPE: non-oncology drugs; precision-medicine "
        "questions about specific patient cases; investigational "
        "compounds without published Phase 2+ data."
    ),
    drug_keywords=(
        # Specific oncology drugs.
        "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab",
        "ipilimumab",
        "trastuzumab", "pertuzumab",
        "rituximab", "obinutuzumab",
        "bevacizumab", "ramucirumab",
        "cetuximab", "panitumumab",
        "imatinib", "dasatinib", "nilotinib",
        "erlotinib", "gefitinib", "osimertinib",
        "sorafenib", "sunitinib",
        "olaparib", "rucaparib",
        "venetoclax",
        # Drug classes (narrow oncology). Codex M-20 review fix:
        # plural surface forms must be present so queries like
        # "PD-1 inhibitors efficacy in melanoma" match the singular
        # exemplars; otherwise the singular keyword "pd-1 inhibitor"
        # tokenizes differently from the plural "pd-1 inhibitors"
        # and the contiguous-subseq match misses.
        "checkpoint inhibitor", "checkpoint inhibitors",
        "pd-1 inhibitor", "pd-1 inhibitors",
        "pd-l1 inhibitor", "pd-l1 inhibitors",
        "car-t", "car-ts", "car t cell", "car t cells",
        "tyrosine kinase inhibitor", "tyrosine kinase inhibitors",
        "tki", "tkis",
        "parp inhibitor", "parp inhibitors",
        "antibody-drug conjugate", "antibody-drug conjugates",
        "adc", "adcs",
    ),
    medical_keywords=(
        # Trial methodology
        "randomized", "double-blind", "placebo-controlled",
        "phase 1", "phase 2", "phase 3", "phase 4",
        "primary endpoint", "secondary endpoint",
        "meta-analysis", "systematic review", "trial", "trials",
        # Regulatory
        "fda", "ema", "mhra", "regulatory", "approval",
        # Outcomes
        "efficacy", "safety", "overall survival",
        "progression-free survival", "response rate",
        "adverse event", "adverse events",
        "objective response", "complete response",
        "partial response",
        "grade 3", "grade 4",
        # Cancer types
        "non-small cell lung cancer", "nsclc", "small cell lung cancer",
        "sclc", "lung cancer",
        "breast cancer", "her2+", "her2-positive",
        "triple-negative", "metastatic",
        "colorectal cancer", "crc",
        "melanoma", "lymphoma", "dlbcl", "follicular lymphoma",
        "leukemia", "aml", "cll", "cml", "all",
        "myeloid", "lymphoid", "lymphoblastic", "myelogenous",
        "chronic myeloid", "chronic lymphocytic",
        "acute myeloid", "acute lymphoblastic",
        "multiple myeloma",
        "ovarian cancer", "prostate cancer", "pancreatic cancer",
        "renal cell carcinoma", "rcc",
        "hepatocellular carcinoma", "hcc",
        # Codex M-20 self-route gap fix: words appearing in
        # exemplars that need to be recognized.
        "relapsed", "refractory", "advanced",
        "front-line", "front", "line",
        "long-term", "high-risk", "low-risk",
        "brca", "brca-mutated", "mutation", "mutations",
        "wild-type", "subgroup", "subgroups",
        "rate", "rates", "remission", "recurrence",
        "survival",
        # General response/outcome vocabulary (shared with the
        # generic clinical template; oncology exemplars use
        # "overall response", "response rate", etc.).
        "overall", "response", "responses",
        "responder", "responders",
        "outcome", "outcomes", "result", "results",
        "endpoint", "endpoints",
        "ratio", "ratios",
        "profile", "profiles",
        # Population
        "patient", "patients", "subject", "subjects",
        "participant", "participants",
        "adult", "adults",
        # Domain
        "tumor", "tumors", "malignancy", "metastasis",
        "chemotherapy", "immunotherapy",
        "targeted therapy", "combination therapy",
        "first-line", "second-line", "maintenance",
        "neoadjuvant", "adjuvant",
        # General medical
        "drug", "drugs", "treatment", "treatments",
        "therapy", "therapies", "regimen", "regimens",
        "study", "studies", "studied",
    ),
    scope_examples=(
        "Pembrolizumab efficacy in metastatic non-small cell lung cancer",
        "Trastuzumab safety in HER2-positive breast cancer",
        "CAR-T overall response rate in relapsed DLBCL",
        "Olaparib in BRCA-mutated ovarian cancer first-line maintenance",
        "Imatinib long-term outcomes in chronic myeloid leukemia",
        "Nivolumab adverse event rates in advanced melanoma",
        "Bevacizumab progression-free survival in metastatic colorectal cancer",
        "Rituximab efficacy in follicular lymphoma front-line therapy",
    ),
)


_V30_CLINICAL_CARDIO = CuratedTemplate(
    template_id="v30_clinical_cardio",
    display_name="Clinical cardiovascular drug audit",
    description=(
        "Audits a cardiovascular drug for indication, mechanism, "
        "efficacy, and safety across approvals and major outcome "
        "trials."
    ),
    scope_summary=(
        "IN SCOPE: questions about a specific cardiovascular drug "
        "(antihypertensive, anticoagulant, lipid-lowering, "
        "antiarrhythmic, heart-failure) with published outcome "
        "trial data. Examples: apixaban for atrial fibrillation; "
        "atorvastatin for ASCVD prevention; sacubitril/valsartan "
        "in HFrEF.\n\n"
        "OUT OF SCOPE: non-cardiovascular drugs; surgical or "
        "device interventions; lifestyle-modification questions."
    ),
    drug_keywords=(
        # Anticoagulants.
        "warfarin", "apixaban", "rivaroxaban", "dabigatran",
        "edoxaban", "heparin",
        # Antiplatelets.
        "aspirin", "clopidogrel", "ticagrelor", "prasugrel",
        # Antihypertensives.
        "lisinopril", "enalapril", "ramipril",
        "losartan", "valsartan", "olmesartan",
        "amlodipine", "nifedipine",
        "metoprolol", "carvedilol", "bisoprolol",
        "furosemide", "spironolactone",
        # Lipid-lowering.
        "atorvastatin", "rosuvastatin", "simvastatin",
        "ezetimibe",
        "alirocumab", "evolocumab",
        # Heart-failure.
        "sacubitril", "sacubitril/valsartan", "ivabradine",
        # Antiarrhythmic.
        "amiodarone", "flecainide", "sotalol",
        # Drug classes. Codex M-20 review fix: plural surface forms
        # must be present; "DOACs" and "calcium channel blockers"
        # otherwise drop to operator_review even though "doac" /
        # "calcium channel blocker" route correctly.
        "ace inhibitor", "ace inhibitors",
        "arb", "arbs",
        "angiotensin receptor blocker", "angiotensin receptor blockers",
        "beta blocker", "beta blockers",
        "calcium channel blocker", "calcium channel blockers",
        "statin", "statins",
        "doac", "doacs", "noac", "noacs",
        "direct oral anticoagulant", "direct oral anticoagulants",
        "p2y12 inhibitor", "p2y12 inhibitors",
        "pcsk9 inhibitor", "pcsk9 inhibitors",
        "arni", "arnis",
    ),
    medical_keywords=(
        # Methodology
        "randomized", "double-blind", "placebo-controlled",
        "phase 1", "phase 2", "phase 3", "phase 4",
        "outcome trial", "outcome trials",
        "primary endpoint", "secondary endpoint", "meta-analysis",
        "trial", "trials", "study", "studies",
        # Regulatory
        "fda", "ema", "mhra", "regulatory", "approval",
        # Conditions
        "atrial fibrillation", "afib",
        "heart failure", "hfpef", "hfref",
        "hypertension", "hypertensive",
        "myocardial infarction", "heart attack",
        "stroke", "ischemic stroke",
        "ascvd", "atherosclerosis",
        "cardiovascular disease", "cvd",
        "ischemic heart disease", "coronary artery disease",
        "cad", "stable angina", "unstable angina",
        "acute coronary syndrome", "acs",
        "venous thromboembolism", "vte",
        "deep vein thrombosis", "dvt",
        "pulmonary embolism", "pe",
        "hyperlipidemia", "hypercholesterolemia",
        "dyslipidemia",
        # Outcomes
        "ldl", "hdl", "blood pressure", "ejection fraction",
        "lvef", "nyha class",
        "stroke prevention", "bleeding", "major bleeding",
        "all-cause mortality", "cardiovascular mortality",
        "mace", "major adverse cardiovascular events",
        "hospitalization",
        # Codex M-20 self-route gap fix: words appearing in
        # cardio exemplars that need to be recognized.
        "major", "adverse", "events", "reduction",
        "outcome", "outcomes", "result", "results",
        "rate", "rates", "ratio", "ratios", "risk",
        "long-term", "short-term",
        "after", "post", "primary", "secondary",
        "chronic", "acute",
        "response", "responses",
        "endpoint", "endpoints",
        "profile", "profiles",
        "in adults", "advanced",
        "stable", "unstable",
        "reduced", "preserved", "mildly reduced",
        "cardiovascular", "cardiac", "vascular",
        # Population
        "patient", "patients", "subject", "subjects",
        "adult", "adults", "elderly",
        # General medical
        "drug", "drugs", "treatment", "treatments",
        "therapy", "therapies",
        "primary prevention", "secondary prevention",
        "efficacy", "safety", "tolerability",
        "adverse event", "adverse events",
    ),
    scope_examples=(
        "Apixaban efficacy for stroke prevention in atrial fibrillation",
        "Atorvastatin major-adverse-cardiovascular-events reduction in ASCVD",
        "Sacubitril/valsartan all-cause mortality in heart failure with reduced ejection fraction",
        "Rivaroxaban bleeding risk in venous thromboembolism",
        "Ticagrelor outcomes after acute coronary syndrome",
        "Evolocumab LDL reduction and cardiovascular outcomes",
        "Spironolactone in chronic heart failure HFpEF outcomes",
        "Amiodarone safety profile in chronic atrial fibrillation",
    ),
)


TEMPLATE_CATALOG: tuple[CuratedTemplate, ...] = (
    _V30_CLINICAL,
    _V30_CLINICAL_ONCOLOGY,
    _V30_CLINICAL_CARDIO,
)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def list_catalog() -> tuple[CuratedTemplate, ...]:
    """Return the full curated catalog.

    The order of entries is meaningful: classifier picks the
    highest-scoring template, ties broken by catalog order.
    """
    return TEMPLATE_CATALOG


def get_template(template_id: str) -> CuratedTemplate | None:
    """Lookup a template by id. Returns None if not in the catalog."""
    for tmpl in TEMPLATE_CATALOG:
        if tmpl.template_id == template_id:
            return tmpl
    return None
