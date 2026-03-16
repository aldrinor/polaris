"""
Export package for polaris graph research reports.

Provides exporters that convert pipeline output (ResearchState JSON)
into professional document formats for downstream consumption.
"""

from src.polaris_graph.export.docx_exporter import DocxExporter

__all__ = [
    "DocxExporter",
]
