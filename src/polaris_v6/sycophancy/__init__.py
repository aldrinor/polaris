"""Sycophancy + refusal CI suite — Phase 1 Task 1.7.

Per docs/carney_delivery_plan_FINAL.md and the ELEPHANT/SycEval
methodology, sycophancy means a model drifts its factual answer based
on the framing of the prompt: "Surely X is great" yields a different
answer than "Surely X is awful" or the neutral "What about X?".

This module provides paired-prompt fixtures + a drift scorer that the
CI suite runs against any candidate generator before it's allowed in
the production code path.
"""
