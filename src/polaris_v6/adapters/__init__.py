"""Adapter layer between v6 and existing pipeline-A substrate.

Per CLAUDE.md LAW VII (CLI Isolation), v6 services do NOT import code
from pipeline-A directly; they communicate via JSON contracts. The
adapters in this module construct those contracts.
"""
