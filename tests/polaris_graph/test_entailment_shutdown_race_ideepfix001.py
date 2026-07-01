"""I-deepfix-001 (#1344): entailment-judge shutdown-race guard.

At the very end of a run, a straggler judge retry can call ThreadPoolExecutor.submit AFTER the
interpreter began shutting down -> RuntimeError('cannot schedule new futures after interpreter
shutdown'). Before the fix that UNHANDLED RuntimeError reached the run driver as
status=error_unexpected (losing the final scores manifest). The fix maps it to the existing
fail-closed concurrent.futures.TimeoutError path (sentinel DROPped -> faithfulness-safe).
"""
import concurrent.futures
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.llm import entailment_judge as ej  # noqa: E402


class _ShutdownExecutor:
    """A ThreadPoolExecutor stand-in whose submit() raises the interpreter-shutdown RuntimeError."""

    def __init__(self, *a, **k):
        pass

    def submit(self, *a, **k):
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    def shutdown(self, wait=True):
        pass


class _Client:
    def post(self, *a, **k):  # never reached during shutdown
        raise AssertionError("client.post must not run once submit raised the shutdown RuntimeError")

    def close(self):
        pass


def test_submit_shutdown_maps_to_timeouterror(monkeypatch):
    # Force the module's ThreadPoolExecutor to the shutdown-raising stand-in.
    monkeypatch.setattr(ej.concurrent.futures, "ThreadPoolExecutor", _ShutdownExecutor)
    raised = None
    try:
        ej._post_with_total_deadline(_Client(), "http://x", {}, {}, total_s=1.0)
    except concurrent.futures.TimeoutError as exc:
        raised = exc
    except RuntimeError as exc:  # the pre-fix behavior we must NOT see
        raised = exc
    assert isinstance(raised, concurrent.futures.TimeoutError), (
        f"shutdown RuntimeError must be mapped to TimeoutError (fail-closed path), got {type(raised)}"
    )
    assert "interpreter_shutdown" in str(raised)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
