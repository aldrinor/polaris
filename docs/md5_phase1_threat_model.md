# M-D5 phase 1 — confidence-gated template matching boundary

**Status:** v3 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/scope_classifier.py`
**Tests:** `tests/polaris_graph/test_md5_scope_classifier.py` (29 passing)
**Pairs with:** M-20 router (`template_classifier.classify_query`),
M-D1 validation set (43 cases)
**Substrate:** stdlib + `template_classifier` only — no LLM client coupling

---

## Scope

M-D5 sits **above** M-20. M-20 is a fast deterministic
keyword/Jaccard-driven curated-template router; M-D5 layers a
pluggable second-opinion classifier on top so that:

- A confident off-domain question can be **rejected** even when
  M-20 lexically matches a template
- A confident in-domain question is auto-enqueued only when M-20
  also routes lexically (defense-in-depth — both signals must
  agree to auto-route)
- Any disagreement between classifier and router flows to
  operator review with a useful rationale

Phase 1 ships the **gating logic + protocol contract** only.
Concrete classifier implementations are deferred to phase 2,
where they will pair with the M-D6 cross-domain templates and
M-D2 phase b's LLM-augmented infrastructure.

---

## Phase 1 v1 boundaries

### 1. Phase 1 = gating logic + protocol; classifier impl deferred

`scope_classifier.py` ships:
- `ScopeVerdict` enum (`in_scope` / `out_of_scope` / `uncertain`)
- `ScopeClassification` dataclass
- `ScopeEligibilityClassifier` Protocol
- `confidence_gated_match()` function
- `GatedAction` + `GatedMatchResult` dataclasses

Phase 1 does NOT ship a concrete classifier. Tests use stubs:
hand-built deterministic classifiers, plus an `_OracleClassifier`
built from the M-D1 validation set's `domain` and
`expected_action` fields.

**Mitigation**: phase 2 will ship a regex-anchor fallback +
LLM-augmented classifier (mirroring M-D2 phase b's keyword +
LLM split). Until then, callers must inject their own
classifier; until a concrete impl ships, M-D5 has no production
caller and is a substrate primitive.

### 2. Classifier confidence is uncalibrated

The threshold (`PG_SCOPE_GATE_CONFIDENCE_THRESHOLD`, default
0.70) compares classifier-emitted confidence values against a
fixed cutoff. Until a concrete classifier ships, the calibration
of that confidence value is undefined: a stub classifier emitting
0.95 means "the test author chose 0.95"; an LLM-augmented
classifier emitting 0.95 will mean something different.

The threshold default of 0.70 is chosen as a conservative-high
floor so that low-confidence verdicts are rejected by default,
but is **subject to recalibration in phase 2** once empirical
classifier-confidence histograms are available. This matches
the autoloop pattern from M-D2 phase b (where calibration
sweeps were run against the M-D1 set after the LLM-augmented
inductor shipped).

**Mitigation**: phase 2 will pin the threshold on real classifier
output. Operators can override via env until then.

### 3. `reject` is a soft reject — operator override path preserved

`GatedAction.REJECT` is the gate's signal that the classifier
was confident the question is out of scope. It is **NOT** a
hard block:

- The function returns the verdict; it does not enforce a
  database-level rejection
- Callers (the inspector router, M-23 review queue) can surface
  the rejection rationale and let the operator force-enqueue
  if they disagree with the classifier

Same fail-closed-with-escape pattern as M-20: M-20 returns
`UNSUPPORTED`, but the `/api/inspector/jobs` enqueue endpoint
still requires an explicit `template_id` and operators retain
the ability to bypass.

**Mitigation**: a future hard-block layer (e.g. quota-driven
rejection of N rejections per workspace per hour) is a phase 2
concern. Phase 1 reasons about scope, not policy enforcement.

### 4. The threshold gates the classifier, not the router

`PG_SCOPE_GATE_CONFIDENCE_THRESHOLD` checks
`classification.confidence`. M-20's score thresholds
(`PG_TEMPLATE_ROUTER_FLOOR_HIGH` etc.) are independent and
continue to gate the router as before.

This separation is deliberate: M-20 already has a gate. Adding
a second router-confidence check would either duplicate M-20's
work (no value) or silently raise M-20's effective floor (an
implicit policy change). The point of M-D5 is the second opinion.

**Mitigation**: callers needing tighter router gating should
override M-20's env vars directly, not M-D5's.

### 5. No telemetry table in phase 1

M-D5 phase 1 is a **stateless function** — no SQLite tables, no
audit log, no `gate_decisions` substrate. Each call returns a
`GatedMatchResult` and the caller decides whether to persist it
(typically into the M-23 review queue or the M-21 workspace
memory).

This was a deliberate cut after consultation with the user via
the advisor. M-D3 telemetry has not yet shipped; until M-D3
defines the production telemetry schema, baking a separate
`gate_decisions` table here would create dual-write risk.

**Mitigation**: phase 2 may add `gate_decisions` once M-D3
substrate is in place. Until then, callers audit via existing
M-23 / M-15 / M-21 substrates.

### 6. No LLM client imports

`scope_classifier.py` imports only stdlib + `template_classifier`.
The LLM clients used by phase 2's eventual concrete classifier
will pick up the env on their next call; M-D5 phase 1 itself
never touches their internals.

**Why**: M-D11 phase 1 / phase 2 / M-D7 / M-D10 all shipped
clean by avoiding LLM-internal coupling. Phase 1 preserves that
— the scope-gate is a substrate primitive, not a runtime
orchestrator.

### 7. Visually-empty queries short-circuit before classifier (v3)

**Codex round-1 LOW fix** (v2): the gate short-circuits empty /
whitespace-only queries to `OPERATOR_REVIEW` *before* invoking
`classifier.classify()`. The `ScopeEligibilityClassifier`
Protocol does NOT guarantee output for empty input — a phase 2
classifier may legitimately raise on empty / whitespace-only
strings (or hit edge cases in tokenizers).

**Codex round-2 PARTIAL fix** (v3): v2 used `str.strip()` to
detect empty input, but `strip()` only removes characters where
`str.isspace()` returns True (Zs/Zl/Zp + control whitespace).
It does NOT remove Cf (format) characters: U+200B (zero-width
space), U+200C (ZWNJ), U+200D (ZWJ), U+2060 (word joiner),
U+FEFF (BOM). These render as nothing but leave a non-empty
string after `strip()` — letting a query like `"​​​"`
bypass the v2 short-circuit and reach the classifier.

v3 adds `_is_visually_empty(text)` which iterates char-by-char
and treats a string as empty when every character is one of:
- whitespace (`isspace()` True)
- `Cf` (Format) — zero-width spaces, joiners, BOM, word joiner
- `Cc` (Control) — control codes
- `Cn` (Unassigned) — unassigned code points
- `Co` (Private Use) — private-use area

Visible Unicode (Japanese, accented Latin, Greek, em-dashes,
etc.) is NOT treated as empty (verified by
`test_visible_unicode_query_does_not_short_circuit` covering 5
visible-Unicode inputs).

The short-circuit emits a sentinel `ScopeClassification` with
`verdict=UNCERTAIN, confidence=0.0` so callers retain a uniform
result shape. The router's `RoutingVerdict.UNSUPPORTED` rationale
is preserved in the gate rationale.

This mirrors the M-20 router's existing empty-query handling
into the gate's contract, end-to-end. Tests pin both:
- `test_unicode_format_character_query_short_circuits` (7
  visually-empty Cf inputs all bypass classifier)
- `test_visible_unicode_query_does_not_short_circuit` (5 visible
  Unicode inputs all reach classifier)

**Mitigation**: phase 2 may revisit this if a real classifier
defines well-formed empty-input behavior. Phase 1 prefers the
fail-closed-with-empty-handler path so the protocol contract
holds without imposing classifier-side requirements.

---

## Empirical contract — validation-set abstain spec

The **spec** for what M-D5 has to deliver downstream is:

> Against the M-D1 validation set (43 cases) with a perfect-
> oracle classifier (built from YAML's `domain` /
> `expected_action` fields), zero `route` outcomes occur for
> any non-`in_scope` case.

`test_validation_set_abstain_contract` enforces this. The test
also pins three sub-contracts:

- `out_of_scope` rows → `REJECT` (with confidence 0.95 and
  threshold 0.70, all 14 oos cases reject)
- `ambiguous` rows → `OPERATOR_REVIEW` (all 15 ambiguous cases
  hit the uncertain branch)
- `in_scope` rows → `ROUTE` when M-20 also `ROUTED`, else
  `OPERATOR_REVIEW`

This is the empirical floor M-D5 must meet for any concrete
classifier to ship in phase 2: a classifier passing this spec
on the validation set is "phase-2 ready".

---

## Codex review trail

Round-1 brief incoming. v1's tight scope + threat-model-with-v1-
commit pattern (per M-D7/M-D10/M-D11 phase 2 precedent) targeted
at 2-3 round convergence.

---

## Lock note

Phase 1 v1 GREEN-lock is the target after Codex round 1-2. v2
work (concrete classifier impl, M-D6 domain-adapter pairing,
M-D3 telemetry hookup, calibration sweep) tracked separately
under M-D5 phase 2.
