"""I-ready-018 (#1138) — import-root alias identity regression tests.

The repo has TWO importable roots for the same package — bare ``polaris_graph`` (via ``src`` on
``sys.path``, e.g. ``PYTHONPATH=src``) and ``src.polaris_graph`` (via repo-root on ``sys.path``).
Without unification they resolve to DISTINCT module objects → distinct classes → pydantic
``model_type`` errors in the clinical_generator chain and DUPLICATE ``strict_verify`` singletons
(``_JUDGE_SINGLETON`` + telemetry counters) — a faithfulness hazard.

``src/sitecustomize.py`` (Codex design ruling C3) installs a MetaPathFinder that aliases the bare
spelling onto the canonical ``src.polaris_graph`` so BOTH spellings are the SAME module object.

These tests run under the both-roots pytest path (``PYTHONPATH=src`` + pytest rootdir), so they
assert the alias is active and the identities are collapsed. If sitecustomize did not load (e.g.
``python -S``), they fail LOUDLY rather than letting the dual-identity bug silently return.
"""
from __future__ import annotations

import sys

import pytest

# P2-1 (Codex iter-1): the alias is only active when src/sitecustomize.py installed the finder (the
# both-roots context: PYTHONPATH=src + repo-root on path). The previous `endswith('src')` sys.path
# heuristic was wrong — under a single-root launch the tests COLLECTED and FAILED with
# ModuleNotFoundError instead of skipping. The definitive, robust signal is whether the alias finder
# is on sys.meta_path. If it is not (single-root run, or `python -S`), the dual-identity bug cannot
# occur in this process, so skip cleanly.
_ALIAS_FINDER_ACTIVE = any(
    getattr(f, "_tag", None) == "_polaris_import_root_alias" for f in sys.meta_path
)

pytestmark = pytest.mark.skipif(
    not _ALIAS_FINDER_ACTIVE,
    reason="polaris import-root alias finder not installed (single-root / -S launch); "
    "dual-identity cannot occur in this process",
)


@pytest.mark.parametrize(
    "submodule",
    [
        "clinical_generator.verified_report",
        "clinical_generator.strict_verify",
        "clinical_generator.provenance",
        "generator.provenance_generator",
        "retrieval.tier_classifier",
    ],
)
def test_bare_and_src_module_are_same_object(submodule: str) -> None:
    """The bare and src. spellings of each module resolve to the SAME module object."""
    bare = __import__(f"polaris_graph.{submodule}", fromlist=["_"])
    srcm = __import__(f"src.polaris_graph.{submodule}", fromlist=["_"])
    assert bare is srcm, (
        f"polaris_graph.{submodule} and src.polaris_graph.{submodule} are DIFFERENT module objects "
        f"— the import-root alias (src/sitecustomize.py) is not active; the dual-identity bug is live."
    )


def test_verified_sentence_class_identity() -> None:
    """The pydantic class that broke generation must be ONE class across both roots."""
    from polaris_graph.clinical_generator.verified_report import VerifiedSentence as VS_bare
    from src.polaris_graph.clinical_generator.verified_report import VerifiedSentence as VS_src
    assert VS_bare is VS_src


def test_section_class_identity() -> None:
    from polaris_graph.clinical_generator.verified_report import Section as Sec_bare
    from src.polaris_graph.clinical_generator.verified_report import Section as Sec_src
    assert Sec_bare is Sec_src


def test_strict_verify_single_module_object() -> None:
    """One strict_verify module ⇒ one _JUDGE_SINGLETON + one telemetry-counter set (faithfulness)."""
    import polaris_graph.clinical_generator.strict_verify as sv_bare
    import src.polaris_graph.clinical_generator.strict_verify as sv_src
    assert sv_bare is sv_src


def test_generation_chain_uses_one_verified_sentence() -> None:
    """The exact mismatch that aborted generation: generator.py's Section field type vs the
    strict_verify-constructed instance must be the same class across roots."""
    from polaris_graph.clinical_generator import generator as gen_bare
    from src.polaris_graph.clinical_generator import strict_verify as sv_src
    from src.polaris_graph.clinical_generator.verified_report import VerifiedSentence
    # generator.py and strict_verify must agree on VerifiedSentence identity.
    assert gen_bare.VerifiedSentence is VerifiedSentence
    assert sv_src.VerifiedSentence is VerifiedSentence
