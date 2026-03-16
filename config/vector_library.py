"""POLARIS Vector Library - 175-Vector Template-Based Configuration for C-POLAR Antimicrobial Coating Analysis"""

import re
from typing import Dict, List, Optional, Any

# Exact stage vector counts from specification.md (sum = 175)
STAGE_VECTOR_COUNTS = {
    1: 35, 2: 21, 3: 15, 4: 10, 5: 12, 6: 8, 7: 16,  # Stage 7 MUST be 16
    8: 10, 9: 10, 10: 8, 11: 10, 12: 10, 13: 10      # Total: 175 vectors
}

# Regional vs Global stages from specification.md
REGIONAL_STAGES = {1, 2, 3, 6, 8}
GLOBAL_STAGES = {4, 5, 7, 9, 10, 11, 12, 13}

# C-POLAR specific stage names matching specification
STAGE_NAMES = {
    1: "Contamination Problem Identification",
    2: "Cost of Pain Quantification",
    3: "Solution Landscape Analysis",
    4: "Technology Gap Identification",
    5: "C-POLAR Value Proposition",
    6: "Market Size Quantification",
    7: "Competitive Intelligence",
    8: "Regulatory Pathway Analysis",
    9: "Technical Feasibility Assessment",
    10: "Business Model Design",
    11: "Financial Modeling",
    12: "Risk Assessment",
    13: "Go-to-Market Strategy"
}

# Vector question templates with {application} and {region} placeholders
VECTOR_QUESTION_TEMPLATES = {
    1: [  # Contamination Problem Identification (35 templates)
        "What pathogen contamination rates exist in {application} for {region}?",
        "What bacterial biofilm formation patterns occur on {application} surfaces in {region}?",
        "What viral transmission pathways are documented for {application} environments in {region}?",
        "What fungal growth conditions persist in {application} systems in {region}?",
        "What multi-drug resistant organism prevalence exists in {application} settings in {region}?",
        "What seasonal contamination variations affect {application} performance in {region}?",
        "What surface contamination persistence times are observed in {application} systems in {region}?",
        "What cross-contamination vectors exist within {application} infrastructure in {region}?",
        "What contamination load thresholds trigger failures in {application} systems in {region}?",
        "What environmental factors accelerate contamination in {application} systems in {region}?",
        "What contamination hotspots are identified in {application} operations in {region}?",
        "What contamination transmission chains originate from {application} surfaces in {region}?",
        "What resistance patterns emerge in {application} environments in {region}?",
        "What contamination monitoring gaps exist in {application} systems in {region}?",
        "What contamination diversity profiles characterize {application} contamination in {region}?",
        "What contamination reservoirs persist despite current cleaning in {application} in {region}?",
        "What surface material properties influence contamination in {application} in {region}?",
        "What environmental conditions promote contamination growth in {application} in {region}?",
        "What environmental quality impacts result from {application} contamination in {region}?",
        "What system degradation occurs from {application} contamination buildup in {region}?",
        "What equipment failure modes result from contamination buildup in {application} in {region}?",
        "What regulatory contamination limits apply to {application} in {region}?",
        "What contamination detection methods are used for {application} in {region}?",
        "What contamination incident frequencies are reported for {application} in {region}?",
        "What contamination-related downtime affects {application} operations in {region}?",
        "What temperature-dependent biofilm formation rates occur in {application} in {region}?",
        "What humidity effects on microbial growth patterns exist in {application} in {region}?",
        "What surface material contamination susceptibility exists in {application} in {region}?",
        "What cross-contamination pathway identification is documented for {application} in {region}?",
        "What environmental factor contamination acceleration occurs in {application} in {region}?",
        "What antimicrobial resistance development timelines exist for {application} in {region}?",
        "What cleaning protocol failure mechanisms are documented for {application} in {region}?",
        "What disinfection resistance patterns are observed in {application} in {region}?",
        "What evolutionary adaptation to current treatments occurs in {application} in {region}?",
        "What pathogen survival rates on different surfaces exist in {application} in {region}?"
    ],
    2: [  # Cost of Pain Quantification (21 templates)
        "What treatment costs for contamination-related illnesses exist for {application} in {region}?",
        "What hospital readmission costs from healthcare-associated infections occur in {application} in {region}?",
        "What extended treatment costs for resistant organism infections exist for {application} in {region}?",
        "What emergency response costs for contamination outbreaks affect {application} in {region}?",
        "What diagnostic testing and monitoring costs apply to {application} in {region}?",
        "What sales loss costs from consumer rejection due to sensory quality degradation occur in {application} in {region}?",
        "What brand switching costs when contamination affects product acceptability exist for {application} in {region}?",
        "What market share losses from contamination-related reputation damage occur for {application} in {region}?",
        "What price discount costs required to sell quality-degraded products exist for {application} in {region}?",
        "What customer acquisition costs to replace lost consumers due to quality issues exist for {application} in {region}?",
        "What product disposal and waste costs from contamination-induced spoilage occur in {application} in {region}?",
        "What inventory devaluation costs from shortened shelf-life exist for {application} in {region}?",
        "What processing and manufacturing losses from contamination events occur in {application} in {region}?",
        "What raw material waste costs due to contamination spread exist for {application} in {region}?",
        "What recall and remediation costs for contamination-affected products occur in {application} in {region}?",
        "What property value depreciation from contamination occurs for {application} in {region}?",
        "What building repair and restoration costs from contamination damage exist for {application} in {region}?",
        "What equipment replacement costs due to contamination-induced degradation occur in {application} in {region}?",
        "What facility condemnation and demolition costs from severe contamination exist for {application} in {region}?",
        "What infrastructure modification costs to prevent contamination recurrence exist for {application} in {region}?",
        "What energy penalty and operational efficiency losses from contamination occur in {application} in {region}?"
    ],
    3: [  # Solution Landscape Analysis (15 templates)
        "What existing antimicrobial solutions are deployed for {application} in {region}?",
        "What current technology efficacy rates and duration exist for {application} in {region}?",
        "What application methods and coverage capabilities are used for {application} in {region}?",
        "What cost structures and pricing models exist for {application} solutions in {region}?",
        "What market penetration rates and adoption barriers exist for {application} in {region}?",
        "What customer satisfaction levels and pain points exist for {application} solutions in {region}?",
        "What documented failure modes of existing solutions occur in {application} in {region}?",
        "What duration limitations and reapplication requirements exist for {application} in {region}?",
        "What spectrum coverage gaps (bacteria, virus, fungi) exist in {application} solutions in {region}?",
        "What safety concerns and toxicity issues exist for {application} solutions in {region}?",
        "What environmental impact and sustainability issues exist for {application} solutions in {region}?",
        "What regulatory restrictions and approval challenges exist for {application} in {region}?",
        "What consumer tolerance thresholds for contamination exist in {application} systems in {region}?",
        "What behavioral adaptation patterns and learned helplessness toward contamination problems exist for {application} in {region}?",
        "What psychological barriers and triggers that drive contamination solution adoption vs. acceptance exist for {application} in {region}?"
    ],
    4: [  # Technology Gap Identification (10 templates) - GLOBAL
        "What duration gap analysis (current vs. required protection periods) exists for {application} globally?",
        "What efficacy gaps in pathogen spectrum coverage exist for {application} globally?",
        "What surface compatibility and adhesion limitations exist for {application} globally?",
        "What environmental durability shortcomings exist for {application} globally?",
        "What reapplication complexity and cost burden exists for {application} globally?",
        "What unserved market segments and applications exist for {application} globally?",
        "What price-performance optimization opportunities exist for {application} globally?",
        "What regulatory approval pathway simplification needs exist for {application} globally?",
        "What integration with existing systems and workflows is needed for {application} globally?",
        "What customization and application-specific requirements exist for {application} globally?"
    ],
    5: [  # C-POLAR Value Proposition (12 templates) - GLOBAL
        "What quantified reduction in treatment and infection costs through C-POLAR prevention exists for {application} globally?",
        "What healthcare-associated infection prevention value and readmission cost savings exist for {application} globally?",
        "What outbreak prevention value and emergency response cost avoidance exists for {application} globally?",
        "What sales preservation value by preventing sensory quality degradation exists for {application} globally?",
        "What brand protection value and market share retention benefits exist for {application} globally?",
        "What price premium maintenance by ensuring consistent product quality exists for {application} globally?",
        "What shelf-life extension value and inventory loss prevention exists for {application} globally?",
        "What manufacturing efficiency preservation and downtime reduction exists for {application} globally?",
        "What energy efficiency maintenance by preventing biofouling and flow restrictions exists for {application} globally?",
        "What property value preservation and structural damage prevention exists for {application} globally?",
        "What equipment longevity extension and replacement cost avoidance exists for {application} globally?",
        "What long-term durability advantage (5-year protection vs. 30-90 day alternatives) exists for {application} globally?"
    ],
    6: [  # Market Size Quantification (8 templates)
        "What total addressable market (TAM) exists for {application} in {region}?",
        "What serviceable addressable market (SAM) segmentation by customer type exists for {application} in {region}?",
        "What serviceable obtainable market (SOM) penetration modeling exists for {application} in {region}?",
        "What market growth rate projections and key drivers exist for {application} in {region}?",
        "What replacement cycle analysis and recurring revenue potential exists for {application} in {region}?",
        "What price elasticity and willingness-to-pay analysis exists for {application} in {region}?",
        "What market concentration and competitive intensity analysis exists for {application} in {region}?",
        "What regulatory and economic factors affecting market accessibility exist for {application} in {region}?"
    ],
    7: [  # Competitive Intelligence (16 templates) - GLOBAL
        "What direct antimicrobial competitor identification and classification exists for {application} globally?",
        "What indirect competitor and substitute technology analysis exists for {application} globally?",
        "What behavioral acceptance as competitive force (do nothing option analysis) exists for {application} globally?",
        "What competitor technology portfolio and R&D pipeline exists for {application} globally?",
        "What competitor customer base and market relationships exist for {application} globally?",
        "What competitor pricing strategies and business models exist for {application} globally?",
        "What competitor geographic presence and expansion plans exist for {application} globally?",
        "What competitor strengths, weaknesses, and vulnerabilities exist for {application} globally?",
        "What market share analysis and concentration metrics exist for {application} globally?",
        "What competitive response scenarios to C-POLAR entry exist for {application} globally?",
        "What patent landscape and intellectual property barriers exist for {application} globally?",
        "What supplier relationships and supply chain dependencies exist for {application} globally?",
        "What distribution channel control and partnerships exist for {application} globally?",
        "What brand positioning and marketing strategies exist for {application} globally?",
        "What merger, acquisition, and consolidation trends exist for {application} globally?",
        "What customer inertia and switching cost analysis exists for {application} globally?"
    ],
    8: [  # Regulatory Pathway Analysis (10 templates)
        "What primary regulatory framework for antimicrobial coatings exists for {application} in {region}?",
        "What specific approval pathway for {application} antimicrobial treatment exists in {region}?",
        "What testing and validation requirements for regulatory compliance exist for {application} in {region}?",
        "What timeline and cost estimates for regulatory approval exist for {application} in {region}?",
        "What documentation and submission requirements exist for {application} in {region}?",
        "What post-market surveillance and renewal requirements exist for {application} in {region}?",
        "What regulatory harmonization opportunities across regions exist for {application}?",
        "What fast-track or expedited approval pathways are available for {application} in {region}?",
        "What environmental and safety compliance requirements exist for {application} in {region}?",
        "What labeling, claims, and marketing restrictions exist for {application} in {region}?"
    ],
    9: [  # Technical Feasibility Assessment (10 templates) - GLOBAL
        "What identification of existing manufacturers for {application} suitable for C-POLAR integration exists globally?",
        "What partnership readiness assessment and technical compatibility evaluation exists for {application} globally?",
        "What coating integration points in existing manufacturing processes exist for {application} globally?",
        "What quality control integration with partner's existing QA systems exists for {application} globally?",
        "What cost-benefit analysis of partnership vs. direct manufacturing exists for {application} globally?",
        "What technical requirements for coating application at partner facilities exist for {application} globally?",
        "What training and certification needs for partner's production staff exist for {application} globally?",
        "What supply chain integration for C-POLAR chemical delivery to partners exists for {application} globally?",
        "What joint product certification and regulatory compliance pathways exist for {application} globally?",
        "What revenue sharing and intellectual property protection models exist for {application} globally?"
    ],
    10: [  # Business Model Design (8 templates) - GLOBAL
        "What revenue sharing models with manufacturing partners (royalty, markup, hybrid) exist for {application} globally?",
        "What pricing strategy for C-POLAR coating as value-add to partner products exists for {application} globally?",
        "What joint go-to-market strategies with manufacturing partners exist for {application} globally?",
        "What intellectual property licensing and protection frameworks exist for {application} globally?",
        "What partner selection criteria and evaluation framework exists for {application} globally?",
        "What technical support and training service models for partners exist for {application} globally?",
        "What quality assurance and brand protection strategies exist for {application} globally?",
        "What partnership scaling and multi-partner management systems exist for {application} globally?"
    ],
    11: [  # Financial Modeling (10 templates) - GLOBAL
        "What revenue forecasting from partner royalties and licensing fees exists for {application} globally?",
        "What partner adoption rate modeling and market penetration scenarios exist for {application} globally?",
        "What volume-based pricing tiers and revenue optimization exists for {application} globally?",
        "What recurring revenue from coating supply to partners exists for {application} globally?",
        "What revenue sensitivity to partner performance and market conditions exists for {application} globally?",
        "What C-POLAR chemical production and supply costs to partners exist for {application} globally?",
        "What partner support and training operational expenses exist for {application} globally?",
        "What minimal capital requirements (no manufacturing facilities needed) exist for {application} globally?",
        "What working capital optimization through partner inventory management exists for {application} globally?",
        "What break-even analysis and path to profitability with partnership model exists for {application} globally?"
    ],
    12: [  # Risk Assessment (10 templates) - GLOBAL
        "What partner performance and quality control risks exist for {application} globally?",
        "What partner dependency and concentration risks exist for {application} globally?",
        "What intellectual property protection and technology transfer risks exist for {application} globally?",
        "What partner competitive behavior and channel conflict risks exist for {application} globally?",
        "What joint regulatory compliance and liability sharing risks exist for {application} globally?",
        "What market adoption through indirect channels risks exist for {application} globally?",
        "What revenue sharing and payment collection risks exist for {application} globally?",
        "What partner financial stability and business continuity risks exist for {application} globally?",
        "What brand reputation risks from partner actions exist for {application} globally?",
        "What scaling limitations and partner capacity constraints exist for {application} globally?"
    ],
    13: [  # Go-to-Market Strategy (10 templates) - GLOBAL
        "What priority partner identification and recruitment sequencing exists for {application} globally?",
        "What joint value proposition development with partners exists for {application} globally?",
        "What co-marketing and co-branding strategies with partners exist for {application} globally?",
        "What partner enablement and sales support systems exist for {application} globally?",
        "What demonstration and pilot program strategies exist for {application} globally?",
        "What geographic expansion strategy and timing exists for {application} globally?",
        "What product line extension and diversification exists for {application} globally?",
        "What partnership and alliance development exists for {application} globally?",
        "What operational scaling and capability development exists for {application} globally?",
        "What success metrics and performance monitoring exists for {application} globally?"
    ]
}


class VectorLibrary:
    """Template-based vector library that dynamically creates questions based on application and region parameters."""

    def __init__(self):
        self.template_vectors = self._build_template_vectors()

    def _build_template_vectors(self):
        """Build template vectors with placeholders for dynamic replacement."""
        templates = []

        for stage in range(1, 14):
            count = STAGE_VECTOR_COUNTS[stage]
            is_regional = stage in REGIONAL_STAGES
            question_templates = VECTOR_QUESTION_TEMPLATES[stage]

            for i in range(1, count + 1):
                # Get question template (cycle through available templates)
                template_index = (i - 1) % len(question_templates)
                question_template = question_templates[template_index]

                # Create template vector
                template_vector = {
                    "stage": stage,
                    "stage_name": STAGE_NAMES[stage],
                    "vector_number": i,
                    "question_template": question_template,
                    "is_regional": is_regional
                }

                templates.append(template_vector)

        return templates

    def get_vector(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a vector by dynamically parsing the ID and filling templates.

        Expected format: S{stage}V{number}_{application}_{region}
        Example: S1V1_Household_Water_Filter_NORTH_AMERICA
        """
        # Parse vector ID
        parsed = self._parse_vector_id(vector_id)
        if not parsed:
            return None

        stage, vector_number, application, region = parsed

        # Find template vector
        template_vector = self._find_template_vector(stage, vector_number)
        if not template_vector:
            return None

        # Validate region for stage type
        if template_vector["is_regional"] and region == "GLOBAL":
            # For regional stages, use region as passed, but GLOBAL is not valid
            return None
        elif not template_vector["is_regional"] and region != "GLOBAL":
            # For global stages, force GLOBAL region
            region = "GLOBAL"

        # Create dynamic vector by filling templates
        question_template = template_vector["question_template"]

        # Format application name for display (replace underscores with spaces)
        application_display = application.replace("_", " ")

        # Format region name for display (replace underscores with spaces)
        region_display = region.replace("_", " ") if region != "GLOBAL" else "Global"

        # Fill template placeholders
        question = question_template.format(
            application=application_display,
            region=region_display
        )

        # Return complete vector
        return {
            "id": vector_id,
            "stage": stage,
            "stage_name": template_vector["stage_name"],
            "vector_number": vector_number,
            "question": question,
            "question_template": question_template,
            "application": application,
            "region": region,
            "is_regional": template_vector["is_regional"]
        }

    def _parse_vector_id(self, vector_id: str) -> Optional[tuple]:
        """Parse vector ID into components."""
        pattern = r'^S(\d+)V(\d+)_(.+)_(NORTH_AMERICA|EUROPE|ASIA_PACIFIC|GLOBAL)$'
        match = re.match(pattern, vector_id)

        if not match:
            return None

        stage = int(match.group(1))
        vector_number = int(match.group(2))
        application = match.group(3)
        region = match.group(4)

        # Validate stage
        if stage < 1 or stage > 13:
            return None

        # Validate vector number for stage
        if vector_number < 1 or vector_number > STAGE_VECTOR_COUNTS[stage]:
            return None

        return (stage, vector_number, application, region)

    def _find_template_vector(self, stage: int, vector_number: int) -> Optional[Dict[str, Any]]:
        """Find template vector for given stage and vector number."""
        for template in self.template_vectors:
            if template["stage"] == stage and template["vector_number"] == vector_number:
                return template
        return None

    @property
    def total_template_count(self) -> int:
        """Return total number of template vectors."""
        return len(self.template_vectors)

    def get_stage_info(self, stage: int) -> Optional[Dict[str, Any]]:
        """Get information about a specific stage."""
        if stage < 1 or stage > 13:
            return None

        return {
            "stage": stage,
            "stage_name": STAGE_NAMES[stage],
            "vector_count": STAGE_VECTOR_COUNTS[stage],
            "is_regional": stage in REGIONAL_STAGES
        }

    def verify_vector_counts(self) -> Dict[str, Any]:
        """Verify the vector library has exactly 175 template vectors with correct distribution."""
        total = self.total_template_count
        by_stage = {}

        for stage in range(1, 14):
            stage_templates = [t for t in self.template_vectors if t["stage"] == stage]
            by_stage[stage] = len(stage_templates)

        # Check total
        is_valid = total == 175

        # Check per-stage counts
        for stage, expected in STAGE_VECTOR_COUNTS.items():
            if by_stage.get(stage, 0) != expected:
                is_valid = False

        return {
            "total": total,
            "by_stage": by_stage,
            "expected_total": 175,
            "expected_by_stage": STAGE_VECTOR_COUNTS,
            "is_valid": is_valid,
            "stage_7_verification": by_stage.get(7, 0) == 16
        }

    def generate_all_vectors_for_application(self, application: str, region_override: str = None) -> List[Dict[str, Any]]:
        """
        Generate all 175 vectors for a specific application.

        Args:
            application: The application name (e.g., "Household_Water_Filter")
            region_override: Optional region to use for regional stages (default cycles through regions)

        Returns:
            List of 175 vector dictionaries for this application
        """
        vectors = []
        regions = ["NORTH_AMERICA", "EUROPE", "ASIA_PACIFIC"]

        for template in self.template_vectors:
            stage = template["stage"]
            vector_number = template["vector_number"]
            is_regional = template["is_regional"]

            if is_regional:
                # Use region_override if provided, otherwise cycle through regions
                if region_override:
                    region = region_override
                else:
                    # Distribute regional vectors across regions
                    region_idx = (vector_number - 1) % len(regions)
                    region = regions[region_idx]
            else:
                region = "GLOBAL"

            vector_id = f"S{stage}V{vector_number}_{application}_{region}"
            vector = self.get_vector(vector_id)
            if vector:
                vectors.append(vector)

        return vectors


# Global instance
VECTOR_LIBRARY = VectorLibrary()


def get_vector(vector_id: str) -> Optional[Dict[str, Any]]:
    """Get a vector by ID with dynamic template filling."""
    return VECTOR_LIBRARY.get_vector(vector_id)


def verify_vector_counts() -> Dict[str, Any]:
    """Verify that the total vector template count is exactly 175 with correct distribution."""
    result = VECTOR_LIBRARY.verify_vector_counts()
    if not result["is_valid"]:
        raise ValueError(f"Invalid vector configuration: {result}")
    return result


def get_vector_id_regex() -> str:
    """Regex pattern for vector IDs: S{stage}V{number}_{application}_{region}"""
    return r'^S([1-9]|1[0-3])V\d{1,2}_[A-Za-z_]+_(NORTH_AMERICA|EUROPE|ASIA_PACIFIC|GLOBAL)$'


def get_stage_info(stage: int) -> Optional[Dict[str, Any]]:
    """Get information about a specific stage."""
    return VECTOR_LIBRARY.get_stage_info(stage)


def generate_all_vectors_for_application(application: str, region_override: str = None) -> List[Dict[str, Any]]:
    """Generate all 175 vectors for a specific application."""
    return VECTOR_LIBRARY.generate_all_vectors_for_application(application, region_override)


if __name__ == "__main__":
    result = VECTOR_LIBRARY.verify_vector_counts()
    print(f"C-POLAR Vector Library Template Status:")
    print(f"  Total templates: {result['total']}")
    print(f"  Expected: {result['expected_total']}")
    print(f"  Valid: {result['is_valid']}")
    print(f"  Stage 7 has 16 templates: {result['stage_7_verification']}")
    print(f"\nTemplates by stage:")
    for stage in range(1, 14):
        actual = result['by_stage'].get(stage, 0)
        expected = result['expected_by_stage'][stage]
        status = "+" if actual == expected else "X"
        stage_type = "REGIONAL" if stage in REGIONAL_STAGES else "GLOBAL"
        print(f"  Stage {stage:2d} ({STAGE_NAMES[stage][:30]}...): {actual:3d}/{expected:3d} {status} [{stage_type}]")

    # Test dynamic vector creation
    print(f"\n" + "="*80)
    print("DYNAMIC VECTOR CREATION TEST")
    print("="*80)

    test_vectors = [
        "S1V1_Household_Water_Filter_NORTH_AMERICA",
        "S1V2_Household_Water_Filter_NORTH_AMERICA",
        "S1V3_Household_Water_Filter_NORTH_AMERICA",
        "S1V4_Household_Water_Filter_NORTH_AMERICA",
        "S1V5_Household_Water_Filter_NORTH_AMERICA",
        "S1V6_Household_Water_Filter_NORTH_AMERICA",
        "S1V1_Hospital_HVAC_System_EUROPE",
        "S4V1_Food_Processing_Equipment_GLOBAL",  # Global stage
        "S7V16_Manufacturing_System_GLOBAL"  # Stage 7, Vector 16
    ]

    for test_id in test_vectors:
        print(f"\nTesting: {test_id}")
        vector = VECTOR_LIBRARY.get_vector(test_id)
        if vector:
            print(f"  + Success - Stage {vector['stage']}: {vector['stage_name']}")
            print(f"    Question: {vector['question'][:100]}...")
            print(f"    Application: {vector['application']} | Region: {vector['region']}")
        else:
            print(f"  X Failed to create vector")

    print(f"\n" + "="*80)
    print(f"TEMPLATE-BASED VECTOR LIBRARY READY")
    print(f"Total Templates: {VECTOR_LIBRARY.total_template_count}")
    print(f"Applications are now DYNAMIC parameters, not hardcoded!")
    print("="*80)
