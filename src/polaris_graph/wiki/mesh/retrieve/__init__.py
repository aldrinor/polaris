"""Mesh retrieval package — lethal retrieval + gap classification."""

from .gap_classify import GapCategory, check_nearby_budget, classify_gap
from .lethal import RetrievalResult, lethal_retrieve

__all__ = [
    "GapCategory",
    "RetrievalResult",
    "check_nearby_budget",
    "classify_gap",
    "lethal_retrieve",
]
