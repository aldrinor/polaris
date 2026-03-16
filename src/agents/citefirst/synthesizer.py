"""
POLARIS Cite-First Synthesizer - Main Module (FIX-223)

Currently re-exports from the monolithic citefirst_synthesizer.py.
Future iterations will extract methods into focused mixins:
- evidence_clustering.py: _cluster_evidence, _recover_perspectives
- prose_generation.py: _write_section_prose, _fallback_section_prose
- claim_processing.py: _parse_claims, _refine_claims, _deduplicate
- report_composition.py: _compose_clustered_report, _enforce_balance
- revision_loop.py: process_revision, _write_grounded_sentence
"""
# FIX-223: Import from existing monolithic module for backward compatibility
# Actual extraction will be done incrementally with per-module test verification
from src.agents.citefirst_synthesizer import CitefirstSynthesizer

__all__ = ["CitefirstSynthesizer"]
