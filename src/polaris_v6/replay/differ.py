"""Compute PinDiff between an original RunPin and a replay RunPin."""

from __future__ import annotations

from polaris_v6.replay.schema import PinDiff, PinDiffField, RunPin

_REGRESSION_STATUSES = {
    "abort_scope_rejected",
    "abort_corpus_inadequate",
    "abort_corpus_approval_denied",
    "abort_no_verified_sections",
    "failed",
}


def compute_pin_diff(original: RunPin, replay: RunPin) -> PinDiff:
    """Field-by-field diff between two pins.

    Treats verifier-model swap as `warn` (deliberate roll), generator-model
    swap as `warn`, pipeline-status going from success to abort as
    `regression`, sentence-count drop > 10% as `regression`.
    """
    if original.run_id == replay.run_id and original.pin_id == replay.pin_id:
        raise ValueError("compute_pin_diff requires distinct pins")

    fields: list[PinDiffField] = []

    if original.generator_model != replay.generator_model:
        fields.append(
            PinDiffField(
                field="generator_model",
                original=original.generator_model,
                replay=replay.generator_model,
                severity="warn",
            )
        )
    if original.verifier_model != replay.verifier_model:
        fields.append(
            PinDiffField(
                field="verifier_model",
                original=original.verifier_model,
                replay=replay.verifier_model,
                severity="warn",
            )
        )
    if original.template != replay.template:
        fields.append(
            PinDiffField(
                field="template",
                original=original.template,
                replay=replay.template,
                severity="regression",
            )
        )
    if original.question != replay.question:
        fields.append(
            PinDiffField(
                field="question",
                original=original.question,
                replay=replay.question,
                severity="regression",
            )
        )

    pipeline_status_changed = (
        original.sealed_pipeline_status != replay.sealed_pipeline_status
    )
    if pipeline_status_changed:
        sev = (
            "regression"
            if (
                original.sealed_pipeline_status == "success"
                and replay.sealed_pipeline_status in _REGRESSION_STATUSES
            )
            else "warn"
        )
        fields.append(
            PinDiffField(
                field="pipeline_status",
                original=original.sealed_pipeline_status,
                replay=replay.sealed_pipeline_status,
                severity=sev,
            )
        )

    delta = (
        replay.sealed_verified_sentence_count
        - original.sealed_verified_sentence_count
    )
    if original.sealed_verified_sentence_count > 0:
        ratio = delta / original.sealed_verified_sentence_count
        if ratio <= -0.10:
            fields.append(
                PinDiffField(
                    field="verified_sentence_count",
                    original=str(original.sealed_verified_sentence_count),
                    replay=str(replay.sealed_verified_sentence_count),
                    severity="regression",
                )
            )

    original_pool = set(original.sealed_evidence_pool_ids)
    replay_pool = set(replay.sealed_evidence_pool_ids)
    added = sorted(replay_pool - original_pool)
    dropped = sorted(original_pool - replay_pool)

    is_regression = any(f.severity == "regression" for f in fields)

    return PinDiff(
        original_pin_id=original.pin_id,
        replay_pin_id=replay.pin_id,
        fields_changed=fields,
        evidence_pool_added=added,
        evidence_pool_dropped=dropped,
        verified_sentence_count_delta=delta,
        pipeline_status_changed=pipeline_status_changed,
        is_regression=is_regression,
    )
