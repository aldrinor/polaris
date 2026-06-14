"""B9 domain-generalization package.

Houses the deterministic ``is_clinical`` backbone (``domain_signal``) that the
B1-B10 redesign threads into every domain-sensitive consumer so POLARIS is
GENERAL by default and clinical rigor is a DETECTED specialization.
"""

from src.polaris_graph.domain.domain_signal import (
    CLINICAL_DOMAIN,
    GENERAL_DOMAIN,
    is_clinical_domain,
    normalize_domain,
)
from src.polaris_graph.domain.domain_pack import (
    available_packs,
    load_domain_pack,
    pack_is_clinical,
)

__all__ = [
    "CLINICAL_DOMAIN",
    "GENERAL_DOMAIN",
    "is_clinical_domain",
    "normalize_domain",
    "available_packs",
    "load_domain_pack",
    "pack_is_clinical",
]
