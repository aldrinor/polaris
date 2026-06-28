"""I-deepfix-001 P0-2a + P0-3 (2026-06-28) — offline proofs for the two fixes
owned by the prefetch/embedding-service file-owner agent.

Offline only: no GPU, no network, no real model load. SentenceTransformer and
EmbeddingService are mocked so we assert WIRING, not model behavior.

Proves:
  P0-2a  `prefetch_offtopic_filter._load_embedder` imports `EmbeddingService`
         from `src.utils.embedding_service` (the real definition), NOT from
         `src.polaris_graph.agents.nli_verifier` (which never defined it). The
         old wrong-module import raised ImportError every run, silently knocking
         out the EmbeddingService primary path.
  P0-3   Both loaders honor the new `PG_EMBED_DEVICE` launch-env knob: when set,
         `device=` is passed to SentenceTransformer; when an installed
         sentence-transformers rejects `device=` (raises TypeError), the loader
         falls back LOUDLY to the no-arg constructor (never a silent drop).
"""
from __future__ import annotations

import importlib
import sys
import types

import numpy as np


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _RecordingST:
    """Stand-in SentenceTransformer that records constructor kwargs."""

    last_args = None
    last_kwargs = None

    def __init__(self, *args, **kwargs):
        type(self).last_args = args
        type(self).last_kwargs = kwargs

    def encode(self, *a, **k):  # used by the embedding_service dim check
        return np.zeros(_EXPECTED_DIMS)


class _DeviceRejectingST:
    """SentenceTransformer build that does NOT accept device= (raises TypeError
    only when device= is passed)."""

    no_arg_called = False

    def __init__(self, model_name, device=None):
        if device is not None:
            raise TypeError(
                "__init__() got an unexpected keyword argument 'device'"
            )
        type(self).no_arg_called = True

    def encode(self, *a, **k):
        return np.zeros(_EXPECTED_DIMS)


_EXPECTED_DIMS = 384  # default MiniLM dim used in the dim-check path


def _install_fake_sentence_transformers(monkeypatch, cls) -> None:
    """Make `from sentence_transformers import SentenceTransformer` yield cls."""
    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = cls
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)


# ---------------------------------------------------------------------------
# P0-2a — the import targets the REAL EmbeddingService module.
# ---------------------------------------------------------------------------

def test_load_embedder_imports_real_embedding_service(monkeypatch) -> None:
    """`_load_embedder` must reach `src.utils.embedding_service.EmbeddingService`
    on the primary path. We inject a sentinel EmbeddingService into that module;
    the loader must return the sentinel, proving the import was repointed."""
    import src.utils.embedding_service as real_mod

    sentinel = object()

    class _FakeEmbeddingService:
        def __new__(cls):  # match no-arg construction
            return sentinel

    monkeypatch.setattr(real_mod, "EmbeddingService", _FakeEmbeddingService)

    from src.polaris_graph.retrieval import prefetch_offtopic_filter as pf
    result = pf._load_embedder()
    assert result is sentinel, (
        "expected EmbeddingService() from src.utils.embedding_service; the "
        "import was not repointed to the real module"
    )


def test_nli_verifier_has_no_embedding_service() -> None:
    """Regression guard: the OLD import target must NOT define EmbeddingService.
    If someone re-adds it there, the import ambiguity that caused the dark
    embedder could silently reappear."""
    nli = importlib.import_module("src.polaris_graph.agents.nli_verifier")
    assert not hasattr(nli, "EmbeddingService"), (
        "nli_verifier unexpectedly defines EmbeddingService — the wrong-module "
        "import bug could silently reappear"
    )


# ---------------------------------------------------------------------------
# P0-3 — PG_EMBED_DEVICE knob honored in prefetch_offtopic_filter.
# ---------------------------------------------------------------------------

def _force_primary_path_to_fail(monkeypatch) -> None:
    """Make EmbeddingService() raise so _load_embedder falls through to the
    SentenceTransformer branch that reads PG_EMBED_DEVICE."""
    import src.utils.embedding_service as real_mod

    class _Boom:
        def __new__(cls):
            raise RuntimeError("primary path unavailable for this test")

    monkeypatch.setattr(real_mod, "EmbeddingService", _Boom)


def test_prefetch_loader_passes_device_when_set(monkeypatch) -> None:
    from src.polaris_graph.retrieval import prefetch_offtopic_filter as pf

    _force_primary_path_to_fail(monkeypatch)
    _RecordingST.last_args = None
    _RecordingST.last_kwargs = None
    _install_fake_sentence_transformers(monkeypatch, _RecordingST)
    monkeypatch.setenv("PG_EMBED_DEVICE", "cuda:0")

    result = pf._load_embedder()
    assert isinstance(result, _RecordingST)
    assert _RecordingST.last_kwargs.get("device") == "cuda:0", (
        "PG_EMBED_DEVICE was not passed as device= to SentenceTransformer"
    )


def test_prefetch_loader_no_device_when_unset(monkeypatch) -> None:
    from src.polaris_graph.retrieval import prefetch_offtopic_filter as pf

    _force_primary_path_to_fail(monkeypatch)
    _RecordingST.last_args = None
    _RecordingST.last_kwargs = None
    _install_fake_sentence_transformers(monkeypatch, _RecordingST)
    monkeypatch.delenv("PG_EMBED_DEVICE", raising=False)

    result = pf._load_embedder()
    assert isinstance(result, _RecordingST)
    assert "device" not in (_RecordingST.last_kwargs or {}), (
        "device= must NOT be passed when PG_EMBED_DEVICE is unset (byte-identical "
        "to prior behavior)"
    )


def test_prefetch_loader_falls_back_loudly_on_device_reject(
    monkeypatch, caplog
) -> None:
    from src.polaris_graph.retrieval import prefetch_offtopic_filter as pf

    _force_primary_path_to_fail(monkeypatch)
    _DeviceRejectingST.no_arg_called = False
    _install_fake_sentence_transformers(monkeypatch, _DeviceRejectingST)
    monkeypatch.setenv("PG_EMBED_DEVICE", "cuda:1")

    with caplog.at_level("WARNING"):
        result = pf._load_embedder()
    assert isinstance(result, _DeviceRejectingST)
    assert _DeviceRejectingST.no_arg_called, (
        "loader did not fall back to the no-arg constructor when device= rejected"
    )
    assert any("rejected device" in r.getMessage() for r in caplog.records), (
        "no LOUD warning emitted on device= rejection (silent device drop)"
    )


# ---------------------------------------------------------------------------
# P0-3 — PG_EMBED_DEVICE knob honored in src.utils.embedding_service too.
# ---------------------------------------------------------------------------

def _fresh_embedding_module():
    """Reset the EmbeddingService singleton so each test exercises __init__."""
    import src.utils.embedding_service as es
    es.EmbeddingService._instance = None
    es._embedding_service = None
    return es


def _new_uninitialized_service(es):
    svc = es.EmbeddingService.__new__(es.EmbeddingService)
    svc._initialized = False
    return svc


def test_embedding_service_passes_device_when_set(monkeypatch) -> None:
    es = _fresh_embedding_module()
    global _EXPECTED_DIMS
    _EXPECTED_DIMS = es.EMBEDDING_DIMENSIONS
    _RecordingST.last_args = None
    _RecordingST.last_kwargs = None
    _install_fake_sentence_transformers(monkeypatch, _RecordingST)
    monkeypatch.setenv("PG_EMBED_DEVICE", "cuda:0")

    svc = _new_uninitialized_service(es)
    svc.__init__()
    assert _RecordingST.last_kwargs.get("device") == "cuda:0", (
        "PG_EMBED_DEVICE not passed as device= in src.utils.embedding_service"
    )


def test_embedding_service_no_device_when_unset(monkeypatch) -> None:
    es = _fresh_embedding_module()
    global _EXPECTED_DIMS
    _EXPECTED_DIMS = es.EMBEDDING_DIMENSIONS
    _RecordingST.last_args = None
    _RecordingST.last_kwargs = None
    _install_fake_sentence_transformers(monkeypatch, _RecordingST)
    monkeypatch.delenv("PG_EMBED_DEVICE", raising=False)

    svc = _new_uninitialized_service(es)
    svc.__init__()
    assert "device" not in (_RecordingST.last_kwargs or {}), (
        "device= must NOT be passed when PG_EMBED_DEVICE is unset"
    )


def test_embedding_service_falls_back_loudly_on_device_reject(
    monkeypatch, caplog
) -> None:
    es = _fresh_embedding_module()
    global _EXPECTED_DIMS
    _EXPECTED_DIMS = es.EMBEDDING_DIMENSIONS
    _DeviceRejectingST.no_arg_called = False
    _install_fake_sentence_transformers(monkeypatch, _DeviceRejectingST)
    monkeypatch.setenv("PG_EMBED_DEVICE", "cuda:1")

    svc = _new_uninitialized_service(es)
    with caplog.at_level("WARNING"):
        svc.__init__()
    assert _DeviceRejectingST.no_arg_called, (
        "embedding_service did not fall back to no-arg constructor on device= "
        "reject"
    )
    assert any("rejected device" in r.getMessage() for r in caplog.records), (
        "no LOUD warning on device= rejection in src.utils.embedding_service"
    )
