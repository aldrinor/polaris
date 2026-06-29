"""I-deepfix-001 FIX-1 (keystone) — offline guards for the PG_EMBED_BATCH_SIZE knob.

The keystone GPU behaviour (W5 reranker fitting on cuda:0 once the embedder batch
peak is capped + the scoring is chunked) is validated UNDER REAL LOAD on the VM
(reranker_device=cuda:0, 126 scores, no OOM). These offline tests guard the OTHER
half of the contract: the env-knob parsing + the BYTE-IDENTICAL default (32) so a
run with PG_EMBED_BATCH_SIZE unset is behaviourally unchanged. No GPU, no model
load (the SentenceTransformer import lives inside EmbeddingService.__init__, not at
module import, so importing/reloading this module is offline-safe).
"""

import importlib

import src.utils.embedding_service as es


def test_default_batch_size_unset_is_32(monkeypatch):
    monkeypatch.delenv("PG_EMBED_BATCH_SIZE", raising=False)
    assert es._default_batch_size() == 32


def test_default_batch_size_honors_env(monkeypatch):
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "8")
    assert es._default_batch_size() == 8
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "16")
    assert es._default_batch_size() == 16


def test_default_batch_size_garbage_falls_back_to_32(monkeypatch):
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "not-an-int")
    assert es._default_batch_size() == 32
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "")
    assert es._default_batch_size() == 32


def test_default_batch_size_clamps_to_at_least_one(monkeypatch):
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "0")
    assert es._default_batch_size() == 1
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "-7")
    assert es._default_batch_size() == 1


def test_module_default_batch_size_reflects_env_on_import(monkeypatch):
    # embed_batch's default param `batch_size=DEFAULT_BATCH_SIZE` binds the module
    # constant at import, so the knob must flow through a fresh import.
    monkeypatch.setenv("PG_EMBED_BATCH_SIZE", "8")
    try:
        importlib.reload(es)
        assert es.DEFAULT_BATCH_SIZE == 8
    finally:
        monkeypatch.delenv("PG_EMBED_BATCH_SIZE", raising=False)
        importlib.reload(es)
    assert es.DEFAULT_BATCH_SIZE == 32  # byte-identical default restored
