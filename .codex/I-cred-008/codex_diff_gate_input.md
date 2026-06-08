HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: P8 disclosure population (#1157) — DIFF gate iter 1. BRIEF Codex-APPROVE'd (.codex/I-cred-008/codex_brief_verdict.txt, all Q1-Q5 answered). PURE population only (render deferred to I-cred-008b). populate_disclosure(verifications, credibility_by_evidence, origin_by_evidence) -> NEW SentenceVerifications via dataclasses.replace (NO provenance_generator import, inputs untouched). Fields per the approved answers: span_verdict = SUPPORTS if is_verified else UNSUPPORTED (binary, Q2); independent_origin_count = distinct Phase-4 origins among cited evidence (unmapped -> own origin); credibility_weight = MIN Phase-2 weight over cited evidence (Q3), absent -> None; certainty_label deterministic env-overridable bucket, None credibility -> low (Q4 — unknown never inflates). ADVISORY only — NEVER changes is_verified / strict_verify; default-OFF PG_SWEEP_CREDIBILITY_DISCLOSURE (Q5); weight_by_origin dropped (P2 note). SMOKE: 12 passed (real SentenceVerification, incl. purity + None->low + env knob).
```diff
diff --git a/src/polaris_graph/synthesis/disclosure_population.py b/src/polaris_graph/synthesis/disclosure_population.py
new file mode 100644
index 00000000..dedbcb10
--- /dev/null
+++ b/src/polaris_graph/synthesis/disclosure_population.py
@@ -0,0 +1,115 @@
+"""I-cred-008 (Phase 8, L7) — per-claim disclosure POPULATION (pure module).
+
+Populate the four inert Phase-1 disclosure fields on each post-``strict_verify`` ``SentenceVerification``
+from the already-computed upstream signals — WITHOUT re-running or touching the verifier:
+  * ``span_verdict``            = "SUPPORTS" if the sentence is verified, else "UNSUPPORTED" (SUPPORTS,
+                                  not "EXISTS" — operator).
+  * ``independent_origin_count`` = number of DISTINCT Phase-4 origin clusters among the sentence's cited
+                                  evidence (unmapped evidence counts as its own origin).
+  * ``credibility_weight``      = MIN Phase-2 credibility weight over the cited evidence (a sentence is
+                                  only as credible as its weakest cited source); absent → None (unknown,
+                                  never fabricated).
+  * ``certainty_label``         = a deterministic, env-overridable bucket; UNKNOWN credibility → "low"
+                                  (unknown must never inflate certainty — Codex #1157).
+
+POSTURE (binding):
+  * ADVISORY ONLY. NEVER changes ``is_verified`` / ``failure_reasons`` / ``tokens`` / ``sentence`` or any
+    of ``strict_verify``'s six checks — they remain the only binding faithfulness gate. The four fields
+    are side-outputs (Phase-1 proved them inert).
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_CREDIBILITY_DISCLOSURE`` (no production caller; the RENDER that
+    surfaces these fields is the flag-gated follow-up I-cred-008b).
+  * PURE: inputs are NOT mutated — new verifications are produced with ``dataclasses.replace`` (so the
+    module never imports ``provenance_generator`` / couples to the faithfulness path). LAW VI; snake_case.
+"""
+from __future__ import annotations
+
+import dataclasses
+import os
+from typing import Any
+
+_FLAG = "PG_SWEEP_CREDIBILITY_DISCLOSURE"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+_ENV_HIGH_CRED = "PG_DISCLOSURE_HIGH_CRED"
+_ENV_LOW_CRED = "PG_DISCLOSURE_LOW_CRED"
+_ENV_HIGH_MIN_ORIGINS = "PG_DISCLOSURE_HIGH_MIN_ORIGINS"
+_DEFAULT_HIGH_CRED = 0.7
+_DEFAULT_LOW_CRED = 0.4
+_DEFAULT_HIGH_MIN_ORIGINS = 2
+
+
+def credibility_disclosure_enabled() -> bool:
+    """True unless ``PG_SWEEP_CREDIBILITY_DISCLOSURE`` is unset/falsey (default OFF => byte-identical)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _float_env(name: str, default: float) -> float:
+    try:
+        return float(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        return int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _cited_evidence_ids(sv: Any) -> list[str]:
+    out: list[str] = []
+    for token in (getattr(sv, "tokens", None) or []):
+        eid = str(getattr(token, "evidence_id", "") or "")
+        if eid:
+            out.append(eid)
+    return out
+
+
+def _certainty_label(is_verified: bool, origin_count: int, credibility: float | None) -> str:
+    """Deterministic, advisory certainty bucket. NEVER consulted by any verifier."""
+    if not is_verified:
+        return "low"
+    if credibility is None:
+        return "low"  # unknown credibility must NOT inflate certainty (Codex #1157)
+    high_cred = _float_env(_ENV_HIGH_CRED, _DEFAULT_HIGH_CRED)
+    low_cred = _float_env(_ENV_LOW_CRED, _DEFAULT_LOW_CRED)
+    high_min_origins = _int_env(_ENV_HIGH_MIN_ORIGINS, _DEFAULT_HIGH_MIN_ORIGINS)
+    if origin_count >= high_min_origins and credibility >= high_cred:
+        return "high"
+    if origin_count < 1 or credibility < low_cred:
+        return "low"
+    return "moderate"
+
+
+def populate_disclosure(
+    verifications: list,
+    credibility_by_evidence: dict,
+    origin_by_evidence: dict,
+) -> list:
+    """Return NEW ``SentenceVerification``s with the four disclosure fields populated — ADVISORY, pure.
+
+    ``credibility_by_evidence``: ``evidence_id -> Phase-2 credibility_weight``.
+    ``origin_by_evidence``: ``evidence_id -> Phase-4 origin_cluster_id``.
+    Inputs are NOT mutated; ``strict_verify`` is NOT re-run; ``is_verified`` is NEVER changed.
+    """
+    cred_map = {str(k): v for k, v in (credibility_by_evidence or {}).items()}
+    origin_map = {str(k): str(v) for k, v in (origin_by_evidence or {}).items()}
+
+    out: list = []
+    for sv in (verifications or []):
+        is_verified = bool(getattr(sv, "is_verified", False))
+        cited = _cited_evidence_ids(sv)
+        # Distinct origin clusters among cited evidence; an unmapped evidence is its own origin.
+        origin_count = len({origin_map.get(eid, f"singleton::{eid}") for eid in cited})
+        # MIN credibility over cited evidence (conservative — weakest cited source); absent -> None.
+        creds = [cred_map[eid] for eid in cited if eid in cred_map and cred_map[eid] is not None]
+        credibility = min(creds) if creds else None
+        out.append(dataclasses.replace(
+            sv,
+            span_verdict="SUPPORTS" if is_verified else "UNSUPPORTED",
+            credibility_weight=credibility,
+            independent_origin_count=origin_count,
+            certainty_label=_certainty_label(is_verified, origin_count, credibility),
+        ))
+    return out
diff --git a/tests/polaris_graph/synthesis/test_disclosure_population_phase8.py b/tests/polaris_graph/synthesis/test_disclosure_population_phase8.py
new file mode 100644
index 00000000..b7b30f67
--- /dev/null
+++ b/tests/polaris_graph/synthesis/test_disclosure_population_phase8.py
@@ -0,0 +1,96 @@
+"""I-cred-008 (Phase 8) — disclosure population. Offline, deterministic, no network.
+
+Uses the REAL SentenceVerification dataclass (the actual population target) with duck-typed tokens."""
+from __future__ import annotations
+
+from types import SimpleNamespace
+
+import pytest
+
+from src.polaris_graph.generator.provenance_generator import SentenceVerification
+from src.polaris_graph.synthesis.disclosure_population import (
+    credibility_disclosure_enabled,
+    populate_disclosure,
+)
+
+
+def _sv(sentence, eids, is_verified):
+    return SentenceVerification(
+        sentence=sentence,
+        tokens=[SimpleNamespace(evidence_id=e) for e in eids],
+        is_verified=is_verified,
+    )
+
+
+# ── AC-1 ──────────────────────────────────────────────────────────────────────
+def test_flag_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_DISCLOSURE", raising=False)
+    assert credibility_disclosure_enabled() is False
+
+
+@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on(monkeypatch, on):
+    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_DISCLOSURE", on)
+    assert credibility_disclosure_enabled() is True
+
+
+# ── AC-2: never changes verifier fields; pure (inputs untouched) ─────────────
+def test_population_never_changes_verifier_fields_and_is_pure():
+    sv = _sv("The rate was 5 percent.", ["e0"], True)
+    out = populate_disclosure([sv], {"e0": 0.8}, {"e0": "o1"})
+    assert out[0].span_verdict == "SUPPORTS"
+    # verifier-owned fields unchanged on the OUTPUT...
+    assert out[0].is_verified is True
+    assert out[0].sentence == sv.sentence and out[0].tokens == sv.tokens
+    # ...and the INPUT sv is NOT mutated (disclosure fields still at their inert defaults).
+    assert sv.span_verdict == "" and sv.credibility_weight is None
+    assert sv.independent_origin_count is None and sv.certainty_label == ""
+
+
+# ── AC-3: span_verdict SUPPORTS / UNSUPPORTED ────────────────────────────────
+def test_span_verdict_supports_vs_unsupported():
+    out = populate_disclosure([_sv("s", ["e0"], True), _sv("s", ["e0"], False)], {}, {})
+    assert out[0].span_verdict == "SUPPORTS"
+    assert out[1].span_verdict == "UNSUPPORTED"
+
+
+# ── AC-4: independent_origin_count = distinct origins among cited evidence ────
+def test_independent_origin_count():
+    one = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o1"})
+    assert one[0].independent_origin_count == 1
+    two = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o2"})
+    assert two[0].independent_origin_count == 2
+    unmapped = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1"})
+    assert unmapped[0].independent_origin_count == 2  # e1 unmapped -> its own origin
+
+
+# ── AC-5: credibility_weight = MIN over cited evidence; absent -> None ────────
+def test_credibility_weight_min_and_none():
+    out = populate_disclosure([_sv("s", ["e0", "e1"], True)], {"e0": 0.9, "e1": 0.3}, {})
+    assert abs(out[0].credibility_weight - 0.3) < 1e-9  # weakest cited source
+    out2 = populate_disclosure([_sv("s", ["e0"], True)], {}, {})
+    assert out2[0].credibility_weight is None
+
+
+# ── AC-6: certainty buckets; None -> low; env knob ───────────────────────────
+def test_certainty_label_buckets(monkeypatch):
+    hi = populate_disclosure([_sv("s", ["e0", "e1"], True)],
+                             {"e0": 0.9, "e1": 0.9}, {"e0": "o1", "e1": "o2"})
+    assert hi[0].certainty_label == "high"
+    unknown = populate_disclosure([_sv("s", ["e0", "e1"], True)], {}, {"e0": "o1", "e1": "o2"})
+    assert unknown[0].certainty_label == "low"  # unknown credibility must NOT inflate certainty
+    unverified = populate_disclosure([_sv("s", ["e0"], False)], {"e0": 0.9}, {"e0": "o1"})
+    assert unverified[0].certainty_label == "low"
+    monkeypatch.setenv("PG_DISCLOSURE_HIGH_CRED", "0.2")
+    monkeypatch.setenv("PG_DISCLOSURE_HIGH_MIN_ORIGINS", "1")
+    boosted = populate_disclosure([_sv("s", ["e0"], True)], {"e0": 0.3}, {"e0": "o1"})
+    assert boosted[0].certainty_label == "high"
+
+
+# ── AC-7: a sentence with no tokens -> safe defaults, no crash ────────────────
+def test_no_tokens_safe_defaults():
+    out = populate_disclosure([_sv("s", [], True)], {"e0": 0.9}, {"e0": "o1"})
+    assert out[0].span_verdict == "SUPPORTS"
+    assert out[0].independent_origin_count == 0
+    assert out[0].credibility_weight is None
+    assert out[0].certainty_label == "low"
```
