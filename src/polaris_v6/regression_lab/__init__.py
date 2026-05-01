"""Regression-lab CI gate (M-D9 substrate, integrated into v6).

The regression lab takes a baseline pin set + a candidate pin set
(produced by replay) and emits PASS / FAIL based on per-pin diff
verdicts. CI uses this to block merges that introduce regressions.
"""
