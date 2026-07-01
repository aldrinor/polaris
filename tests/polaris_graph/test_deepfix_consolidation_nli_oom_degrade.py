"""I-deepfix-001 fix-3 (#1344): W10 consolidation-NLI cross-encoder OOM-DEGRADE.

The consolidation cross-encoder (`consolidation_nli._load_model`) loaded on CUDA by
default with NO device control and NO OOM handling. On the crammed 2-GPU split (W6
embedder + W5 reranker + W10 NLI all co-resident on cuda:0) a CUDA OOM during load
(or during predict) RAISES — `score_pairs` -> `_apply_consolidation_nli` ->
`dedup_by_finding` propagate the OOM and the CONSOLIDATION step dies. Consolidation
is a §-1.3 WEIGHT (corroboration baskets), not a faithfulness gate; killing it on an
OOM throws away basket merges the run could still produce on CPU.

The fix DEGRADES instead of dying:
  * `PG_CONSOLIDATION_NLI_DEVICE` knob places the cross-encoder (default unset =>
    byte-identical: no device kwarg, library auto-placement);
  * on a CUDA OOM during the model LOAD, retry the load on CPU (degrade) — the
    winner still FIRES (it logs the load + scores), just on CPU, so the §-1.4
    firing canary is satisfied and NO basket is lost;
  * on a CUDA OOM during PREDICT, reload the model on CPU and re-score — the edge
    list is identical (CPU vs GPU give the same argmax entailment), so the merged
    baskets are unchanged.

§-1.3 / faithfulness: this keeps MORE baskets (consolidation runs to completion on
CPU instead of dying), never fewer; it merges literal clusters exactly as before;
it touches NO strict_verify / NLI-entailment-verifier / 4-role / span gate. Default
(no CUDA OOM, knob unset) is byte-identical.

Offline: NO torch, NO sentence-transformers, NO GPU. The cross-encoder is injected
via the `predict_fn` seam and the loader is monkeypatched with a fake CrossEncoder
that raises a synthetic CUDA-OOM RuntimeError on its first (GPU) construction.
"""
from __future__ import annotations

import pytest

import src.polaris_graph.synthesis.consolidation_nli as cnli


_OOM_MESSAGE = "CUDA out of memory. Tried to allocate 2.00 GiB"
# I-deepfix-001 (#1344): the REAL clinical crash signature. A cuBLAS handle-alloc failure
# when the card is full contains NO 'out of memory' substring, so the old _is_cuda_oom
# returned False, the CPU degrade never fired, and the run DIED at consolidation. Must now
# be detected as OOM-equivalent and routed to the same identical-result CPU degrade.
_CUBLAS_MESSAGE = "CUDA error: CUBLAS_STATUS_ALLOC_FAILED when calling `cublasCreate(handle)`"


def _reset_model() -> None:
    cnli._MODEL = None
    cnli._MODEL_DEVICE = None


def test_is_cuda_oom_detects_cublas_alloc_failed():
    """RED before I-deepfix-001 #1344 (the matcher only caught 'out of memory'), GREEN
    after. The clinical run crashed with CUBLAS_STATUS_ALLOC_FAILED, which the old
    _is_cuda_oom missed, so the CPU degrade never fired and the run died."""
    assert cnli._is_cuda_oom(RuntimeError(_CUBLAS_MESSAGE)) is True
    assert cnli._is_cuda_oom(RuntimeError("CUDA error: CUBLAS_STATUS_NOT_INITIALIZED")) is True
    # the plain CUDA-OOM path is still detected
    assert cnli._is_cuda_oom(RuntimeError(_OOM_MESSAGE)) is True
    # a genuinely-unrelated error must STILL fail loud (NOT be swallowed as an OOM degrade)
    assert cnli._is_cuda_oom(ValueError("bad tensor shape")) is False


def test_predict_chunk_env_bounds_forward_batch(monkeypatch):
    """I-deepfix-001 #1344: PG_CONSOLIDATION_NLI_PREDICT_CHUNK caps the per-forward batch
    (default 256; <=0 disables) — the guard against the unbounded chunk_size that OOM'd
    the card on the large clinical corpora."""
    monkeypatch.delenv(cnli.ENV_PREDICT_CHUNK, raising=False)
    assert cnli._predict_chunk() == 256
    monkeypatch.setenv(cnli.ENV_PREDICT_CHUNK, "64")
    assert cnli._predict_chunk() == 64
    monkeypatch.setenv(cnli.ENV_PREDICT_CHUNK, "0")
    assert cnli._predict_chunk() == 0


class _FakeCrossEncoder:
    """Records the device it was built with. Raises a synthetic CUDA-OOM on the
    FIRST construction (the GPU attempt) and succeeds on the CPU retry."""

    instances: list = []
    fail_first_on_device = None  # set per-test: the device value that should OOM

    def __init__(self, model_id, device=None, **kwargs):
        type(self).instances.append({"model_id": model_id, "device": device})
        if (
            type(self).fail_first_on_device is not None
            and device == type(self).fail_first_on_device
        ):
            raise RuntimeError(_OOM_MESSAGE)
        self.model_id = model_id
        self.device = device

    def predict(self, batch):  # pragma: no cover - not exercised by load tests
        # Deterministic: never-entail logits ([con, ent, neu] with ent lowest).
        return [[2.0, 0.0, 1.0] for _ in batch]


def _install_fake_cross_encoder(monkeypatch) -> None:
    """Make `from sentence_transformers import CrossEncoder` yield the fake."""
    import sys
    import types

    mod = types.ModuleType("sentence_transformers")
    mod.CrossEncoder = _FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


# ── 1. device knob: default unset => no device kwarg (byte-identical) ──────────
def test_device_knob_unset_passes_no_device(monkeypatch) -> None:
    _reset_model()
    _FakeCrossEncoder.instances = []
    _FakeCrossEncoder.fail_first_on_device = None
    _install_fake_cross_encoder(monkeypatch)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_DEVICE", raising=False)

    model = cnli._load_model()
    assert model.device is None, "unset knob must NOT pass a device kwarg"
    assert len(_FakeCrossEncoder.instances) == 1
    _reset_model()


def test_device_knob_set_places_on_device(monkeypatch) -> None:
    _reset_model()
    _FakeCrossEncoder.instances = []
    _FakeCrossEncoder.fail_first_on_device = None
    _install_fake_cross_encoder(monkeypatch)
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_DEVICE", "cuda:0")

    model = cnli._load_model()
    assert model.device == "cuda:0"
    _reset_model()


# ── 2. OOM degrade on LOAD: cuda OOM => retry on CPU, winner still FIRES ───────
def test_load_cuda_oom_degrades_to_cpu(monkeypatch) -> None:
    """A CUDA OOM on the GPU load must DEGRADE to a CPU load (never raise) so the
    consolidation winner still fires and no basket is lost."""
    _reset_model()
    _FakeCrossEncoder.instances = []
    _FakeCrossEncoder.fail_first_on_device = "cuda:0"
    _install_fake_cross_encoder(monkeypatch)
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_DEVICE", "cuda:0")

    model = cnli._load_model()  # must NOT raise
    # Two constructions: the failed cuda:0 attempt, then the CPU degrade.
    devices = [i["device"] for i in _FakeCrossEncoder.instances]
    assert devices == ["cuda:0", "cpu"], devices
    assert model.device == "cpu", "the degraded model must be the CPU one"
    _reset_model()


def test_non_oom_load_error_still_raises(monkeypatch) -> None:
    """A NON-OOM load error (e.g. a missing model id) must NOT be silently degraded
    to CPU — only a genuine CUDA OOM degrades; everything else fails loud (§-1.4)."""
    _reset_model()
    _FakeCrossEncoder.instances = []
    _install_fake_cross_encoder(monkeypatch)
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_DEVICE", "cuda:0")

    def _boom_non_oom(model_id, device=None, **kwargs):
        raise RuntimeError("checkpoint file not found: totally-unrelated-error")

    import sys
    sys.modules["sentence_transformers"].CrossEncoder = _boom_non_oom
    with pytest.raises(RuntimeError, match="checkpoint file not found"):
        cnli._load_model()
    _reset_model()


# ── 3. OOM degrade on PREDICT: cuda OOM mid-score => reload CPU + re-score ─────
def test_predict_cuda_oom_degrades_and_completes(monkeypatch) -> None:
    """A CUDA OOM during predict must reload the cross-encoder on CPU and re-score
    (no exception escapes; the consolidation completes). We drive `score_pairs` with
    a `predict_fn` that OOMs once, and assert the degrade path reloads + completes
    with the SAME deterministic edge list."""
    _reset_model()
    _FakeCrossEncoder.instances = []
    _FakeCrossEncoder.fail_first_on_device = None
    _install_fake_cross_encoder(monkeypatch)

    calls = {"n": 0}

    def _entail_then_oom_first(batch):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(_OOM_MESSAGE)
        # Second call (the CPU degrade): every pair bidirectionally entails.
        return [[0.0, 5.0, 0.0] for _ in batch]

    edges = cnli.score_pairs(
        ["claim a", "claim a paraphrase"],
        workers=1,
        predict_fn=_entail_then_oom_first,
    )
    # The degrade re-ran the score and produced the merge edge (0, 1).
    assert edges == [(0, 1)], edges
    assert calls["n"] >= 2, "the predict OOM must be retried (degraded), not raised"
    _reset_model()


def test_predict_non_oom_error_still_raises(monkeypatch) -> None:
    """A NON-OOM predict error is NOT degraded — only a CUDA OOM triggers the CPU
    re-score; other errors fail loud."""
    _reset_model()
    _install_fake_cross_encoder(monkeypatch)

    def _boom(batch):
        raise ValueError("tokenizer mismatch — not an OOM")

    with pytest.raises(ValueError, match="tokenizer mismatch"):
        cnli.score_pairs(["a", "b"], workers=1, predict_fn=_boom)
    _reset_model()
