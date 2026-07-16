"""S4 compose OFF-path byte-identity + faithfulness-frozen guards (offline).

These lock the two guardrails that matter most for the compose seam:

  * the OFF path is byte-identical — with no ``compose_projection`` the resolved
    voice advisory is "" (an inert append), and the new generator kwargs all
    default to a value that changes nothing;
  * the frozen faithfulness engine is untouched — ``provenance_generator.py`` is
    unchanged vs HEAD, and the S4 modules never import strict_verify.

No network / no LLM: signature + source introspection only.
"""

from __future__ import annotations

import inspect
import subprocess

from src.polaris_graph.planning import compose_render_projection as crp


def test_off_path_voice_is_empty_append():
    # No projection => "" => the generator's advisory append is inert.
    assert crp.compose_voice_advisory(None) == ""
    # An empty contract => a projection with no voice => "".
    from src.polaris_graph.planning.planning_gate_schema import contract_from_dict
    empty = crp.from_contract(contract_from_dict({}))
    assert crp.compose_voice_advisory(empty) == ""


def test_generator_kwargs_default_to_inert():
    from src.polaris_graph.generator import multi_section_generator as msg
    sig = inspect.signature(msg.generate_multi_section_report)
    # the new compose kwarg exists and defaults to None (OFF => byte-identical).
    assert "compose_projection" in sig.parameters
    assert sig.parameters["compose_projection"].default is None
    # deliverable_spec / scope_spec (S4 ORCH-2) still default None.
    assert sig.parameters["deliverable_spec"].default is None
    assert sig.parameters["scope_spec"].default is None

    # _call_section carries the voice slot defaulting to "".
    sig2 = inspect.signature(msg._call_section)
    assert "voice_advisory_text" in sig2.parameters
    assert sig2.parameters["voice_advisory_text"].default == ""

    # _run_section forwards it, defaulting to "".
    sig3 = inspect.signature(msg._run_section)
    assert "voice_advisory_text" in sig3.parameters
    assert sig3.parameters["voice_advisory_text"].default == ""


def test_faithfulness_file_unchanged_vs_head():
    """The frozen provenance_generator.py must have a clean diff vs HEAD."""
    out = subprocess.run(
        ["git", "diff", "--stat", "HEAD", "--",
         "src/polaris_graph/generator/provenance_generator.py"],
        capture_output=True, text=True, cwd=_repo_root(),
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "", (
        "provenance_generator.py must be byte-identical to HEAD (faithfulness "
        f"frozen); got diff:\n{out.stdout}"
    )


def test_s4_modules_do_not_touch_strict_verify():
    """The S4 compose/render module must never IMPORT/CALL the faithfulness engine
    (a boundary docstring mention is fine — assert on imports/calls, not text)."""
    import ast
    for mod in (crp,):
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "provenance_generator" not in node.module
            elif isinstance(node, ast.Import):
                assert all("provenance_generator" not in a.name for a in node.names)
            elif isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", "") or getattr(fn, "attr", "")
                assert name != "strict_verify"


def _repo_root() -> str:
    import pathlib
    # tests/planning/<this> -> repo root is two parents up from tests/.
    return str(pathlib.Path(__file__).resolve().parents[2])
