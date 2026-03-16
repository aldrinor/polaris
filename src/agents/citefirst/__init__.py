"""
POLARIS Cite-First Synthesizer Package (FIX-223)

Decomposes the monolithic citefirst_synthesizer.py into focused modules
while maintaining backward compatibility.
"""
from src.agents.citefirst.synthesizer import CitefirstSynthesizer

__all__ = ["CitefirstSynthesizer"]
