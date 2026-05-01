"""F11 report-scoped auditable follow-up agent (Phase 3 Task 3.1).

Once a research run produces an EvidenceContract, the user can ask
follow-up questions that are scoped to that run's evidence pool only.
This prevents the follow-up agent from silently broadening sources.

Each follow-up answer is itself a verifiable claim with provenance
tokens pointing into the same pool.
"""
