"""POLARIS graph tools -- data analysis, chart generation, code execution, SQL, PDF."""

from src.polaris_graph.tools.analysis_toolkit import (
    build_comparison_table,
    compute_agreement_score,
    detect_outliers,
    generate_meta_analysis_summary,
    rank_evidence_by_impact,
    statistical_summary,
)
from src.polaris_graph.tools.code_executor import (
    execute_analysis_script,
    generate_and_execute_analysis,
    get_sandbox_paths,
    validate_script,
)
from src.polaris_graph.tools.evidence_database import (
    EvidenceDatabase,
)
from src.polaris_graph.tools.package_installer import (
    get_approved_packages,
    is_approved,
    safe_install,
)
from src.polaris_graph.tools.pdf_table_extractor import (
    extract_tables_from_pdf,
    tables_to_structured_data,
)

__all__ = [
    # Analysis toolkit
    "build_comparison_table",
    "compute_agreement_score",
    "detect_outliers",
    "generate_meta_analysis_summary",
    "rank_evidence_by_impact",
    "statistical_summary",
    # Code executor
    "execute_analysis_script",
    "generate_and_execute_analysis",
    "get_sandbox_paths",
    "validate_script",
    # Evidence database (SQLite)
    "EvidenceDatabase",
    # Package installer
    "get_approved_packages",
    "is_approved",
    "safe_install",
    # PDF table extractor
    "extract_tables_from_pdf",
    "tables_to_structured_data",
]
