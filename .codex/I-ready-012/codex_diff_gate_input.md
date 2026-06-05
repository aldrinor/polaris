# Codex DIFF review — I-ready-012 (#1079): semantic/NLI contradiction layer — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Return the YAML verdict block ONLY. Claude authored the diff (commits c70d4f2a + a1bb9d49 on bot/I-ready-012-semantic-conflict-nli).**

---

## 0. Your iter-1 verdict: APPROVE (0 P0/P1, size_acceptable=yes, 3 non-blocking P2)

Iter-1 was APPROVE. The change since iter-1 is ONE folded-in P2 fix + 2 deferred P2s:

- **P2 (folded in, commit a1bb9d49):** `detect_semantic_conflicts` now rejects non-finite / out-of-range confidence (`math.isfinite(conf) and 0.0<=conf<=1.0`) BEFORE the threshold — a NaN/inf from a malformed judge can no longer pass (NaN < x is False) and fabricate a phantom conflict that would falsely abort a run via PT08. +4 parametrized tests (nan/inf/-0.1/1.5 → no record). This is the only code change since iter-1.
- **P2-1 (judge ledger / Path-B capture) + P2-3 (typed contradiction IR vs the value=0.0 sentinel)** — deferred to follow-up issue #1092 (observability + data-model, non-correctness, non-safety; the hard budget cap already works and the loader is compatible). Per §8.3.1 "don't pick bone from egg" these are not fold-ins.

## 1. What to verify this iter

- The finite-confidence guard is correct + a NaN/inf/out-of-range confidence can never create a semantic record (fail-safe: never fabricate a conflict).
- No regression to the iter-1-APPROVE'd behavior (recall, precision, flag-OFF byte-identical, fail-open, PT08 routing, audit_ir.loader compat).
- Agreement that P2-1 + P2-3 are correctly deferred to #1092 (not P0/P1).

## 2. Verification done (offline, no spend, FAKE judge)

16 behavioral tests pass (the 4 new finite-confidence cases + the original 12). 39 contradiction/qualitative regression green; sweep imports clean.

## 3. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

## 4. The full committed diff (`git diff bot/I-ready-013-analyst-synthesis-verified..HEAD`)

```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 35218b9d..b4ada837 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -3117,10 +3117,33 @@ async def run_one_query(
         except Exception as exc:  # noqa: BLE001 — fail-open, log loudly, never abort the sweep
             _log(f"[qual-conflict] detector error (skipped, fail-open): {exc}")
             qualitative_records = []
+        # Semantic/NLI cross-document contradiction detection (I-ready-012 #1079). The THIRD
+        # detector: an LLM-NLI pass catching prose-only directional contradictions with NO shared
+        # number and NO NegEx cue that the numeric+qualitative rule layers miss (the lethal-miss
+        # class). Default OFF (PG_SWEEP_NLI_CONFLICT) -> byte-identical when off (no judge built, no
+        # network). Fail-open: a detector/judge/import error logs + skips, never aborts the sweep; a
+        # BudgetExceededError is absorbed inside the detector as keep-partial (the run's hard cap is
+        # still enforced by the downstream generation/evaluation budget guards). Merged into the SAME
+        # contradictions.json list with a `type:"semantic"` discriminator; routed to a dedicated
+        # report disclosure block + the PT08 evaluator gate below (the numeric renderer is untouched).
+        semantic_records = []
+        try:
+            from src.polaris_graph.retrieval.semantic_conflict_detector import (
+                detect_semantic_conflicts_for_rows,
+                semantic_conflict_enabled,
+            )
+            if semantic_conflict_enabled():
+                semantic_records = detect_semantic_conflicts_for_rows(
+                    retrieval.evidence_rows,
+                )
+        except Exception as exc:  # noqa: BLE001 — fail-open, log loudly, never abort the sweep
+            _log(f"[semantic-conflict] detector error (skipped, fail-open): {exc}")
+            semantic_records = []
         (run_dir / "contradictions.json").write_text(
             json.dumps(
                 [asdict(c) for c in contradictions]
-                + [asdict(qr) for qr in qualitative_records],
+                + [asdict(qr) for qr in qualitative_records]
+                + [asdict(sr) for sr in semantic_records],
                 indent=2, sort_keys=True, default=str,
             ) + "\n",
             encoding="utf-8",
@@ -4559,6 +4582,31 @@ async def run_one_query(
                 )
                 methods += f"- [{_label}] {r.subject} / {r.predicate}: {_statuses} — {r.conflict_reason}\n"
 
+        # Semantic/NLI cross-document contradiction disclosure (I-ready-012 #1079). Renders each
+        # NLI-detected prose-only conflict (subject + predicate + the two conflicting claims with
+        # evidence ids/tiers) into the report so the user sees it AND the PT08 gate (substring of
+        # subject+predicate in report text) finds it. Distinct from the numeric renderer (no value
+        # range) and the qualitative renderer (no assertion status); only present when the semantic
+        # detector ran (default OFF) and found a conflict.
+        if semantic_records:
+            methods += (
+                f"\n## Semantic contradiction disclosures (cross-document NLI)\n"
+                f"An NLI pass over same-subject evidence pairs flagged {len(semantic_records)} "
+                f"prose-only directional contradiction(s) that carry no shared number and no "
+                f"rule-cue (and so are not caught by the numeric or qualitative detectors). Each "
+                f"is shown with both conflicting source claims for human adjudication.\n\n"
+            )
+            for r in semantic_records:
+                _claims = " VS ".join(
+                    f"\"{(cl.get('text') or '').strip()}\" "
+                    f"[ev={cl.get('evidence_id', '')}, tier={cl.get('tier', '')}]"
+                    for cl in r.claims
+                )
+                methods += (
+                    f"- [SEMANTIC] {r.subject} / {r.predicate} "
+                    f"(NLI confidence {r.nli_confidence:.2f}): {_claims}\n"
+                )
+
         biblio_section = "\n\n## Bibliography\n"
         for b in multi.bibliography:
             biblio_section += (
@@ -4822,7 +4870,13 @@ async def run_one_query(
                 report_text=final_report,
                 protocol=protocol,
                 tier_distribution_report=asdict(dist),
-                contradictions=[asdict(c) for c in contradictions],
+                # I-ready-012 (#1079): PT08 also gates the NLI semantic contradictions — a detected
+                # semantic conflict whose subject+predicate is absent from the report aborts the run
+                # (abort_evaluator_critical), exactly like a numeric one. asdict carries subject +
+                # predicate; PT08 reads only those (substring presence), so the extra semantic fields
+                # are ignored. Numeric records are unchanged.
+                contradictions=[asdict(c) for c in contradictions]
+                + [asdict(sr) for sr in semantic_records],
                 evidence_pool=ev_pool,
                 enable_llm_judge=False,
             )
diff --git a/src/polaris_graph/retrieval/semantic_conflict_detector.py b/src/polaris_graph/retrieval/semantic_conflict_detector.py
new file mode 100644
index 00000000..28daae2a
--- /dev/null
+++ b/src/polaris_graph/retrieval/semantic_conflict_detector.py
@@ -0,0 +1,429 @@
+"""Semantic/NLI cross-document contradiction detector (I-ready-012 / #1079).
+
+The THIRD contradiction detector, complementing the numeric-regex detector
+(``contradiction_detector``) and the NegEx/ConText rule-cue qualitative detector
+(``qualitative_conflict_detector``). Those two cap detection recall at the rule
+layer: a genuine prose-only directional contradiction with NO shared number and
+NO lexicon cue — e.g. "adjuvant chemotherapy improved overall survival" vs
+"...provided no overall survival benefit" — passes both silently. In a clinical
+report that is the lethal-miss class (F12).
+
+This module adds an LLM-NLI pass that:
+  1. clusters evidence rows by shared SALIENT content words computed from the raw
+     row text (``cluster_candidate_rows``) — RECALL-oriented, independent of the
+     rule extractors (which are blind to the no-number/no-cue rows). The cheap
+     pre-filter bounds the O(n^2) judge cost; the judge provides precision.
+  2. emits same-cluster row pairs (``extract_pairs``), hard-capped, highest-tier
+     first.
+  3. judges each pair (claim A vs claim B -> contradict/entail/neutral) and keeps
+     ``contradict`` pairs above a confidence threshold (``detect_semantic_conflicts``).
+
+Design invariants:
+  * ADDITIVE + fail-open: a detector / judge / import / budget error logs and
+    skips; it NEVER aborts the sweep and NEVER weakens an existing gate. It can
+    only ADD disclosures and (via PT08) make the release gate stricter.
+  * Default OFF (``PG_SWEEP_NLI_CONFLICT``): flag-off is byte-identical — no judge
+    is constructed and no network call is made.
+  * The judge is INJECTED (a ``(claim_a, claim_b) -> (label, confidence)``
+    callable), so the detector is fully offline-testable with a fake. The
+    production judge (``get_default_judge``) reuses the family-segregated,
+    cost-ledgered OpenRouter substrate (``PG_ENTAILMENT_MODEL``, Gemma-4-31B by
+    default) — the same two-family evaluator the strict_verify entailment judge
+    uses — with a CONTRADICTION prompt. The strict_verify entailment path is NOT
+    modified.
+
+Records are shaped (``SemanticConflictRecord``) so the existing ``contradictions.json``
+merge consumes them, and they are routed by the caller into a dedicated report
+disclosure block + the PT08 evaluator input (the numeric renderer is untouched).
+"""
+
+from __future__ import annotations
+
+import json
+import logging
+import math
+import os
+import re
+import time
+from dataclasses import asdict, dataclass, field
+
+logger = logging.getLogger(__name__)
+
+# --- configuration (LAW VI: all knobs are env-overridable) -------------------
+_FLAG = "PG_SWEEP_NLI_CONFLICT"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+_ENV_MIN_OVERLAP = "PG_SWEEP_NLI_CONFLICT_MIN_OVERLAP"      # default 2 shared salient words
+_ENV_MAX_PAIRS = "PG_SWEEP_NLI_CONFLICT_MAX_PAIRS"          # default 60 judged pairs
+_ENV_MAX_ROWS = "PG_SWEEP_NLI_CONFLICT_MAX_ROWS"            # default 200 rows clustered
+_ENV_MIN_CONFIDENCE = "PG_SWEEP_NLI_CONFLICT_MIN_CONFIDENCE"  # default 0.7
+
+_DEFAULT_MIN_OVERLAP = 2
+_DEFAULT_MAX_PAIRS = 60
+_DEFAULT_MAX_ROWS = 200
+_DEFAULT_MIN_CONFIDENCE = 0.7
+
+_DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"
+_JUDGE_TIMEOUT_S = 30.0
+
+# Small, domain-aware stopword set. Salient-word overlap (NOT all words) keys the
+# clustering, so generic connectives never group unrelated rows.
+_STOPWORDS = frozenset({
+    "the", "and", "for", "with", "was", "were", "has", "have", "had", "are", "but",
+    "not", "from", "that", "this", "these", "those", "their", "its", "than", "then",
+    "into", "onto", "over", "under", "between", "within", "without", "during", "after",
+    "before", "while", "which", "when", "where", "what", "who", "whom", "how", "why",
+    "study", "trial", "patients", "patient", "group", "groups", "results", "result",
+    "showed", "shown", "found", "reported", "compared", "versus", "vs", "among",
+    "using", "based", "data", "analysis", "associated", "may", "can", "also", "both",
+    "more", "most", "less", "high", "low", "higher", "lower", "year", "years",
+})
+
+# Tier ordering: highest-evidence pairs judged first (so the pair cap keeps the
+# most decision-relevant conflicts). Unknown tiers sort last.
+_TIER_RANK = {"T1": 0, "gold": 0, "T2": 1, "T3": 2, "T4": 3, "T5": 4, "T6": 5, "T7": 6}
+
+
+@dataclass
+class SemanticConflictRecord:
+    """A cross-document semantic contradiction (type discriminator: ``semantic``).
+
+    Shaped for: (a) the merged ``contradictions.json`` dump; (b) the dedicated
+    report disclosure block (subject + predicate + the two conflicting claims);
+    (c) the PT08 evaluator gate (substring(subject) + substring(predicate) in
+    report text). ``claims`` always has length 2 — the two conflicting sources.
+    """
+
+    subject: str
+    predicate: str
+    claims: list = field(default_factory=list)  # [{evidence_id, text, tier, nli_label}, ...] (len 2)
+    type: str = "semantic"
+    severity: str = "review"
+    nli_confidence: float = 0.0
+
+
+def semantic_conflict_enabled() -> bool:
+    """True unless ``PG_SWEEP_NLI_CONFLICT`` is unset/falsey. Default OFF — flag-off
+    is byte-identical (no judge constructed, no network)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        return int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _float_env(name: str, default: float) -> float:
+    try:
+        return float(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+
+
+def _row_text(row: dict) -> str:
+    return str(row.get("direct_quote") or row.get("statement") or row.get("text") or "")
+
+
+def _content_words(text: str) -> set:
+    """Salient (>=3 char, non-stopword) lowercase tokens for overlap keying."""
+    return {
+        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
+        if len(t) >= 3 and t not in _STOPWORDS
+    }
+
+
+def _tier_rank(row: dict) -> int:
+    return _TIER_RANK.get(str(row.get("tier") or ""), 99)
+
+
+def cluster_candidate_rows(evidence_rows, *, min_overlap: int | None = None,
+                           max_rows: int | None = None) -> list:
+    """Group rows that share >= ``min_overlap`` salient content words (connected
+    components). RECALL-oriented pre-filter, independent of the rule extractors.
+
+    Bounded: only the top ``max_rows`` rows (highest tier first) are clustered, so
+    the O(n^2) comparison is capped at full scale. Returns a list of clusters
+    (each a list of the original row dicts); singletons are dropped.
+    """
+    min_overlap = _DEFAULT_MIN_OVERLAP if min_overlap is None else min_overlap
+    max_rows = _DEFAULT_MAX_ROWS if max_rows is None else max_rows
+
+    rows = [r for r in (evidence_rows or []) if _row_text(r).strip()]
+    rows = sorted(rows, key=_tier_rank)[:max_rows]
+    words = [_content_words(_row_text(r)) for r in rows]
+
+    n = len(rows)
+    parent = list(range(n))
+
+    def find(x: int) -> int:
+        while parent[x] != x:
+            parent[x] = parent[parent[x]]
+            x = parent[x]
+        return x
+
+    def union(a: int, b: int) -> None:
+        ra, rb = find(a), find(b)
+        if ra != rb:
+            parent[rb] = ra
+
+    for i in range(n):
+        if not words[i]:
+            continue
+        for j in range(i + 1, n):
+            if len(words[i] & words[j]) >= min_overlap:
+                union(i, j)
+
+    groups: dict = {}
+    for idx in range(n):
+        groups.setdefault(find(idx), []).append(rows[idx])
+    return [g for g in groups.values() if len(g) >= 2]
+
+
+def extract_pairs(clusters, *, max_pairs: int | None = None) -> list:
+    """Same-cluster row pairs, highest-tier first, hard-capped at ``max_pairs``."""
+    max_pairs = _DEFAULT_MAX_PAIRS if max_pairs is None else max_pairs
+    pairs: list = []
+    for cluster in clusters:
+        ordered = sorted(cluster, key=_tier_rank)
+        for i in range(len(ordered)):
+            for j in range(i + 1, len(ordered)):
+                pairs.append((ordered[i], ordered[j]))
+    # Rank pairs by best tier in the pair so the cap keeps the strongest evidence.
+    pairs.sort(key=lambda p: (_tier_rank(p[0]) + _tier_rank(p[1])))
+    return pairs[:max_pairs]
+
+
+def _shared_subject(row_a: dict, row_b: dict) -> str:
+    """Top shared salient words → a stable subject phrase (for PT08 + disclosure)."""
+    shared = _content_words(_row_text(row_a)) & _content_words(_row_text(row_b))
+    # Preserve appearance order in row A for readability.
+    ordered = [w for w in re.findall(r"[a-z0-9]+", _row_text(row_a).lower()) if w in shared]
+    seen: set = set()
+    uniq = [w for w in ordered if not (w in seen or seen.add(w))]
+    return " ".join(uniq[:4]) if uniq else "cross-document claim"
+
+
+def detect_semantic_conflicts(pairs, judge, *, min_confidence: float | None = None) -> list:
+    """Judge each pair; keep ``contradict`` pairs above ``min_confidence``.
+
+    ``judge`` is a ``(claim_a, claim_b) -> (label, confidence)`` callable, label in
+    {"contradict","entail","neutral"}. Fail-open:
+      * a per-pair judge error skips THAT pair (never fabricates a conflict);
+      * a ``BudgetExceededError`` stops judging, KEEPS records found so far, and
+        propagates as a clean stop signal (caught by the caller's fail-open block)
+        — it never aborts mid-record.
+    """
+    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
+
+    min_confidence = _DEFAULT_MIN_CONFIDENCE if min_confidence is None else min_confidence
+    records: list = []
+    for row_a, row_b in pairs:
+        text_a, text_b = _row_text(row_a), _row_text(row_b)
+        try:
+            label, confidence = judge(text_a, text_b)
+        except BudgetExceededError:
+            logger.warning(
+                "[semantic-conflict] budget exceeded after %d record(s); "
+                "stopping judge calls (fail-open, keep-partial).", len(records),
+            )
+            break
+        except Exception as exc:  # noqa: BLE001 — per-pair fail-open; never fabricate a conflict
+            logger.warning("[semantic-conflict] judge error on a pair (skipped): %s", exc)
+            continue
+        if str(label).strip().lower() != "contradict":
+            continue
+        try:
+            conf = float(confidence)
+        except (TypeError, ValueError):
+            conf = 0.0
+        # Codex diff-gate P2: reject non-finite / out-of-range confidence. A NaN/inf from a
+        # malformed judge response must NOT pass the threshold and fabricate a phantom conflict
+        # — a phantom contradiction would falsely abort a legitimate run via PT08. (NaN < x is
+        # False, so a bare `conf < min_confidence` would let NaN slip through; guard explicitly.)
+        if not math.isfinite(conf) or not (0.0 <= conf <= 1.0):
+            logger.warning("[semantic-conflict] dropping pair with non-finite/out-of-range "
+                           "confidence %r (fail-safe, never fabricate a conflict)", confidence)
+            continue
+        if conf < min_confidence:
+            continue
+        subject = _shared_subject(row_a, row_b)
+        predicate = "cross-document directional disagreement"
+        # Each claim carries evidence_id + predicate + a finite value (0.0) so a
+        # contradictions.json holding a semantic record stays loadable by
+        # audit_ir.loader._parse_contradiction_claim (which REQUIRES those three keys
+        # and does float(value)). Semantic conflicts are prose-only — there is no
+        # numeric value — so value is the finite sentinel 0.0; the `type:"semantic"`
+        # discriminator + `nli_label` distinguish them from numeric records downstream.
+        records.append(SemanticConflictRecord(
+            subject=subject,
+            predicate=predicate,
+            claims=[
+                {"evidence_id": str(row_a.get("evidence_id") or ""), "predicate": predicate,
+                 "value": 0.0, "text": text_a, "tier": str(row_a.get("tier") or ""),
+                 "nli_label": "contradict"},
+                {"evidence_id": str(row_b.get("evidence_id") or ""), "predicate": predicate,
+                 "value": 0.0, "text": text_b, "tier": str(row_b.get("tier") or ""),
+                 "nli_label": "contradict"},
+            ],
+            nli_confidence=conf,
+        ))
+    return records
+
+
+def detect_semantic_conflicts_for_rows(evidence_rows, judge=None) -> list:
+    """End-to-end convenience: cluster -> pairs -> judge. Used by the sweep block.
+
+    If ``judge`` is None the production default judge is lazily constructed
+    (``get_default_judge``). Returns ``list[SemanticConflictRecord]``.
+    """
+    clusters = cluster_candidate_rows(
+        evidence_rows,
+        min_overlap=_int_env(_ENV_MIN_OVERLAP, _DEFAULT_MIN_OVERLAP),
+        max_rows=_int_env(_ENV_MAX_ROWS, _DEFAULT_MAX_ROWS),
+    )
+    if not clusters:
+        return []
+    pairs = extract_pairs(clusters, max_pairs=_int_env(_ENV_MAX_PAIRS, _DEFAULT_MAX_PAIRS))
+    if not pairs:
+        return []
+    if judge is None:
+        judge = get_default_judge()
+    return detect_semantic_conflicts(
+        pairs, judge,
+        min_confidence=_float_env(_ENV_MIN_CONFIDENCE, _DEFAULT_MIN_CONFIDENCE),
+    )
+
+
+# --- production judge (isolated; reuses the openrouter cost/family substrate) ---
+
+_CONTRADICTION_PROMPT = """You are a strict cross-document contradiction judge. You are given two independent CLAIMS, each from a different source document, about a related subject. Decide their logical relation.
+
+Rules:
+- CONTRADICT: the two claims cannot both be true for the same population/endpoint — one asserts something the other explicitly denies or reverses (e.g. "improved overall survival" vs "no overall survival benefit"; "first-line therapy" vs "reserved for refractory cases").
+- ENTAIL: the claims agree, or one restates / refines the other.
+- NEUTRAL: the claims are about different things, or could both be true (different populations, endpoints, doses, or time points), or there is not enough overlap to judge a conflict.
+
+Be conservative: only answer CONTRADICT when the disagreement is direct and on the same subject. Return STRICT JSON only, no prose:
+{{"verdict": "CONTRADICT" | "ENTAIL" | "NEUTRAL", "confidence": <number 0.0-1.0>}}
+
+CLAIM A:
+{claim_a}
+
+CLAIM B:
+{claim_b}
+
+JSON:"""
+
+
+class _SemanticContradictionJudge:
+    """Synchronous httpx wrapper around a cross-document contradiction call.
+
+    Mirrors ``llm.entailment_judge._EntailmentJudge`` (same two-family evaluator
+    model, the same ``openrouter_client`` cost/budget helpers, family segregation
+    enforced at construction) but with a CONTRADICTION prompt and a (label,
+    confidence) return. Kept SEPARATE from ``_EntailmentJudge`` so the
+    faithfulness-critical strict_verify entailment path is never touched.
+    """
+
+    def __init__(self) -> None:
+        import httpx
+
+        from src.polaris_graph.llm.openrouter_client import check_family_segregation
+
+        api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
+        if not api_key:
+            raise RuntimeError("PG_SWEEP_NLI_CONFLICT requires OPENROUTER_API_KEY")
+        self._api_key = api_key
+        base_url = os.environ.get(
+            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
+        ).rstrip("/")
+        self._endpoint = f"{base_url}/chat/completions"
+        self._model = os.environ.get("PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL)
+        # Two-family invariant (§9.1.1): the conflict judge is an evaluator-family
+        # call and MUST differ from the generator family — raises at construction.
+        check_family_segregation(evaluator_model=self._model)
+        self._client = httpx.Client(timeout=_JUDGE_TIMEOUT_S)
+
+    def judge(self, claim_a: str, claim_b: str) -> tuple:
+        """Return ``(label, confidence)`` with label in {contradict,entail,neutral}.
+
+        Fail-open on API/parse error → ("neutral", 0.0) so a transient outage never
+        FABRICATES a conflict. ``BudgetExceededError`` is re-raised (the caller
+        stops + keeps partial) — never masked as a neutral result.
+        """
+        from src.polaris_graph.llm import openrouter_client as _orc
+
+        prompt = _CONTRADICTION_PROMPT.format(claim_a=claim_a, claim_b=claim_b)
+        json_body: dict = {
+            "model": self._model,
+            "messages": [{"role": "user", "content": prompt}],
+            "temperature": 0.0,
+            "max_tokens": 60,
+            "response_format": {"type": "json_object"},
+        }
+        try:
+            from src.polaris_graph.benchmark import pathB_capture as _pathb_for_routing
+            _gate_provider = _pathb_for_routing.get_role_provider("evaluator")
+        except Exception:
+            _gate_provider = None
+        if _gate_provider:
+            json_body["provider"] = {
+                "order": [_gate_provider],
+                "allow_fallbacks": False,
+                "require_parameters": True,
+            }
+        try:
+            response = self._client.post(
+                self._endpoint,
+                headers={
+                    "Authorization": f"Bearer {self._api_key}",
+                    "Content-Type": "application/json",
+                },
+                json=json_body,
+            )
+            response.raise_for_status()
+            data = response.json()
+            usage = data.get("usage", {}) or {}
+            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
+            output_tokens = int(usage.get("completion_tokens", 0) or 0)
+            api_cost = float(usage.get("cost", 0) or 0)
+            actual_cost = api_cost or _orc._impute_cost_from_tokens(
+                self._model, input_tokens, output_tokens, 0,
+            )
+            if actual_cost == 0 and not usage:
+                actual_cost = _orc._impute_cost_from_tokens(self._model, 400, 60, 0)
+            _orc._add_run_cost(actual_cost)
+            _orc.check_run_budget(0)  # raises BudgetExceededError if cap breached
+            content = data["choices"][0]["message"]["content"]
+            parsed = json.loads(content)
+            verdict = str(parsed.get("verdict", "")).strip().upper()
+            confidence = float(parsed.get("confidence", 0.0) or 0.0)
+            label = {"CONTRADICT": "contradict", "ENTAIL": "entail",
+                     "NEUTRAL": "neutral"}.get(verdict, "neutral")
+            return label, confidence
+        except Exception:
+            # BudgetExceededError is a subclass-free RuntimeError in openrouter_client;
+            # re-raise it explicitly so the caller's keep-partial path fires.
+            from src.polaris_graph.llm.openrouter_client import BudgetExceededError
+            import sys
+            exc = sys.exc_info()[1]
+            if isinstance(exc, BudgetExceededError):
+                raise
+            logger.warning("[semantic-conflict] judge call failed (fail-open neutral): %s", exc)
+            return "neutral", 0.0
+
+
+_JUDGE_SINGLETON = None
+
+
+def get_default_judge():
+    """Lazy singleton production judge callable ``(a, b) -> (label, confidence)``.
+
+    Constructed only when ``PG_SWEEP_NLI_CONFLICT`` is ON and first used — off-mode
+    never instantiates it (no network, no httpx client)."""
+    global _JUDGE_SINGLETON
+    if _JUDGE_SINGLETON is None:
+        _JUDGE_SINGLETON = _SemanticContradictionJudge()
+    return _JUDGE_SINGLETON.judge
diff --git a/tests/polaris_graph/test_semantic_conflict_detector_iready012.py b/tests/polaris_graph/test_semantic_conflict_detector_iready012.py
new file mode 100644
index 00000000..fe36a0b3
--- /dev/null
+++ b/tests/polaris_graph/test_semantic_conflict_detector_iready012.py
@@ -0,0 +1,223 @@
+"""I-ready-012 (#1079) — semantic/NLI cross-document contradiction detector.
+
+Closes the F12 recall hole: a prose-only directional contradiction with NO shared number and NO
+NegEx cue ("adjuvant chemotherapy improved overall survival" vs "...provided no overall survival
+benefit") passes both the numeric and qualitative rule detectors silently. This detector adds an
+LLM-NLI pass (default OFF, fail-open, additive) that catches it and routes the conflict into the
+existing report disclosure + PT08 release gate.
+
+All offline: the judge is INJECTED (a fake), so no network / no model. Verifies recall, precision,
+flag-OFF inertness, every fail-open path (per-pair error + BudgetExceededError keep-partial), the
+pair cap, the audit_ir.loader compatibility (Codex iter-1 P2), and the real PT08 routing (Codex
+iter-1 P1: semantic records must actually reach the PT08 evaluator gate).
+"""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from src.polaris_graph.llm.openrouter_client import BudgetExceededError
+from src.polaris_graph.retrieval import semantic_conflict_detector as scd
+
+# The reproduced recall-hole pair: prose-only, no shared number, no NegEx cue.
+_ROW_A = {
+    "evidence_id": "ev_a", "tier": "T1", "source_url": "u1",
+    "direct_quote": "Adjuvant chemotherapy improved overall survival in stage II colon cancer.",
+}
+_ROW_B = {
+    "evidence_id": "ev_b", "tier": "T1", "source_url": "u2",
+    "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit in stage II colon cancer.",
+}
+
+
+def _contradict_judge(a, b):
+    return "contradict", 0.95
+
+
+def _neutral_judge(a, b):
+    return "neutral", 0.9
+
+
+# ───────────────────────────── recall: the hole closes ──────────────────────────────
+
+def test_cluster_groups_the_reproduced_rows_before_any_judge():
+    """The recall-oriented clustering (independent of the rule extractors) must put the two
+    prose-only rows in ONE candidate cluster — BEFORE the judge is ever invoked."""
+    clusters = scd.cluster_candidate_rows([_ROW_A, _ROW_B])
+    assert len(clusters) == 1
+    assert {r["evidence_id"] for r in clusters[0]} == {"ev_a", "ev_b"}
+
+
+def test_detect_emits_one_semantic_record_on_contradict():
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    records = scd.detect_semantic_conflicts(pairs, _contradict_judge)
+    assert len(records) == 1
+    rec = records[0]
+    assert rec.type == "semantic"
+    assert rec.severity == "review"
+    assert rec.subject  # non-empty (PT08 substring source)
+    assert rec.predicate
+    assert {c["evidence_id"] for c in rec.claims} == {"ev_a", "ev_b"}
+    assert rec.nli_confidence == pytest.approx(0.95)
+
+
+def test_end_to_end_for_rows_with_injected_judge():
+    records = scd.detect_semantic_conflicts_for_rows([_ROW_A, _ROW_B], judge=_contradict_judge)
+    assert len(records) == 1
+    assert "survival" in records[0].subject
+
+
+# ───────────────────────────── precision ──────────────────────────────
+
+def test_neutral_or_entail_pair_yields_no_record():
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    assert scd.detect_semantic_conflicts(pairs, _neutral_judge) == []
+    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("entail", 0.99)) == []
+
+
+def test_low_confidence_contradict_is_filtered():
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    # below the 0.7 default threshold → dropped
+    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("contradict", 0.4)) == []
+
+
+@pytest.mark.parametrize("bad_conf", [float("nan"), float("inf"), -0.1, 1.5])
+def test_non_finite_or_out_of_range_confidence_never_fabricates(bad_conf):
+    """Codex diff-gate P2: a NaN/inf/out-of-range confidence from a malformed judge must NOT pass
+    the threshold and create a phantom contradiction (which would falsely abort a run via PT08)."""
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("contradict", bad_conf)) == []
+
+
+# ───────────────────────────── flag-OFF inertness ──────────────────────────────
+
+def test_enabled_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_NLI_CONFLICT", raising=False)
+    assert scd.semantic_conflict_enabled() is False
+    for off in ("0", "false", "off", "no", ""):
+        monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", off)
+        assert scd.semantic_conflict_enabled() is False
+    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
+    assert scd.semantic_conflict_enabled() is True
+
+
+def test_for_rows_never_constructs_a_judge_when_no_pairs(monkeypatch):
+    """Unrelated rows (no shared salient words) → no cluster → no pairs → the default judge
+    factory is NEVER called (no network even if somehow ON)."""
+    def _boom():
+        raise AssertionError("default judge must not be constructed when there are no pairs")
+    monkeypatch.setattr(scd, "get_default_judge", _boom)
+    rows = [
+        {"evidence_id": "x", "tier": "T1", "direct_quote": "Quantum entanglement decoheres rapidly."},
+        {"evidence_id": "y", "tier": "T1", "direct_quote": "Maple syrup grades reflect color."},
+    ]
+    assert scd.detect_semantic_conflicts_for_rows(rows) == []
+
+
+# ───────────────────────────── fail-open ──────────────────────────────
+
+def test_per_pair_judge_error_is_skipped_not_fatal():
+    rows = [_ROW_A, _ROW_B,
+            {"evidence_id": "ev_c", "tier": "T2",
+             "direct_quote": "Adjuvant chemotherapy overall survival benefit was confirmed in colon cancer."}]
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows(rows))
+    calls = {"n": 0}
+
+    def _flaky(a, b):
+        calls["n"] += 1
+        if calls["n"] == 1:
+            raise RuntimeError("transient judge error")
+        return "contradict", 0.9
+
+    records = scd.detect_semantic_conflicts(pairs, _flaky)
+    # first pair errored (skipped), remaining pairs still judged → at least one record
+    assert len(records) >= 1
+
+
+def test_budget_exceeded_keeps_partial_and_stops():
+    rows = [_ROW_A, _ROW_B,
+            {"evidence_id": "ev_c", "tier": "T2",
+             "direct_quote": "Adjuvant chemotherapy overall survival in stage II colon cancer was worse."}]
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows(rows))
+    assert len(pairs) >= 2
+    calls = {"n": 0}
+
+    def _budget_then_more(a, b):
+        calls["n"] += 1
+        if calls["n"] == 1:
+            return "contradict", 0.9
+        raise BudgetExceededError("run budget cap reached")
+
+    records = scd.detect_semantic_conflicts(pairs, _budget_then_more)
+    assert len(records) == 1            # pair-1 kept
+    assert calls["n"] == 2              # stopped at the breach (did not judge pair 3+)
+
+
+# ───────────────────────────── cost bound ──────────────────────────────
+
+def test_pair_cap_is_honored(monkeypatch):
+    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT_MAX_PAIRS", "3")
+    # 6 same-cluster rows → 15 raw pairs, capped to 3.
+    rows = [
+        {"evidence_id": f"e{i}", "tier": "T1",
+         "direct_quote": f"Adjuvant chemotherapy overall survival colon cancer finding number {i}."}
+        for i in range(6)
+    ]
+    clusters = scd.cluster_candidate_rows(rows)
+    pairs = scd.extract_pairs(clusters, max_pairs=3)
+    assert len(pairs) == 3
+
+
+# ───────────────────────────── routing (Codex iter-1 P1-2) ──────────────────────────────
+
+def test_pt08_gate_counts_a_semantic_record_real_evaluator():
+    """The REAL PT08 check must treat a semantic record like a numeric one: disclosed
+    (subject+predicate in report text) → pass; not disclosed → fail. Proves the record reaches
+    and is gated by the evaluator, not just written to contradictions.json."""
+    from src.polaris_graph.evaluator.external_evaluator import run_external_evaluation
+    from dataclasses import asdict
+
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    rec = scd.detect_semantic_conflicts(pairs, _contradict_judge)[0]
+    contra = [asdict(rec)]
+    protocol = {"research_question": "q", "date_range": {}}
+
+    disclosed = (
+        f"## Semantic contradiction disclosures\n- [SEMANTIC] {rec.subject} / {rec.predicate}: "
+        f"claim A VS claim B\n"
+    )
+    out_ok = run_external_evaluation(
+        report_text=disclosed, protocol=protocol, tier_distribution_report={},
+        contradictions=contra, evidence_pool={}, enable_llm_judge=False,
+    )
+    out_missing = run_external_evaluation(
+        report_text="A report with no contradiction disclosure at all.",
+        protocol=protocol, tier_distribution_report={},
+        contradictions=contra, evidence_pool={}, enable_llm_judge=False,
+    )
+    pt08_ok = next(r for r in out_ok.rule_checks if r.item_id == "PT08")
+    pt08_missing = next(r for r in out_missing.rule_checks if r.item_id == "PT08")
+    assert pt08_ok.passed is True
+    assert pt08_missing.passed is False
+
+
+# ───────────────────────────── audit_ir.loader compat (Codex iter-1 P2) ──────────────────────────────
+
+def test_semantic_record_is_audit_ir_loader_compatible():
+    """A contradictions.json holding a semantic record must parse — _parse_contradiction_claim
+    REQUIRES evidence_id + predicate + finite value on every claim."""
+    from dataclasses import asdict
+    from src.polaris_graph.audit_ir import loader
+
+    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
+    rec = scd.detect_semantic_conflicts(pairs, _contradict_judge)[0]
+    raw = json.loads(json.dumps([asdict(rec)]))  # round-trip exactly like the on-disk file
+    clusters = loader._parse_contradictions(raw)
+    assert len(clusters) == 1
+    assert len(clusters[0].claims) == 2
+    for c in clusters[0].claims:
+        assert c.evidence_id
+        assert c.predicate
+        assert c.value == pytest.approx(0.0)  # finite sentinel (prose has no numeric value)

```
