# Codex static review — I-arch-011 794->9 breadth-collapse forensic plan

You are the ONLY review gate. STATIC review only.

EXPLORATION IS CAPPED — read FAST, emit the YAML as soon as you can answer:
- READ the plan: `.codex/iarch011_campaign/collapse_forensic_plan.json` (it is NOT inlined here).
- The 3 decisive code snippets are INLINED below — you do NOT need to open those files; assess the reasoning.
- DO NOT open `outputs/iarch011_drb78_run5/full_run.log` — the plan already cites its line numbers + content; your job is to judge the REASONING, not re-verify every log line.
- You MAY spot-open at most ONE file if a question truly hinges on it. Do not cat large files. Do NOT run pytest / any command.

## Context (one paragraph)
Run-5 (DRB #78) shipped breadth 794 distinct sources -> only 9 cited. `collapsed=0`, enrichment EMPTY. The plan claims this is a CONSOLIDATION+DECOUPLE chokepoint (NO in-scope source DROP), plus a separate 4-role D8 seam crash that left faithfulness unadjudicated. Pipeline DNA (CLAUDE.md §-1.3) is WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP; faithfulness is the only hard gate and is NEVER relaxed to widen breadth.

## INLINED decisive snippets (the questions hinge on these)

### Snippet 1 — `src/polaris_graph/synthesis/finding_dedup.py:80-114` (`_finding_key`)
```python
def _finding_key(claim, evidence_id, claim_index, *, exact_value=False) -> tuple:
    subject = getattr(claim, "subject", "") or ""
    if not subject or subject == _UNKNOWN_SUBJECT:
        return ("__unknown__", evidence_id, claim_index)   # <-- the manifest '__unknown__'[0] origin
    raw_value = float(getattr(claim, "value", 0.0) or 0.0)
    value_slot = raw_value if exact_value else round(raw_value, 3)
    return (subject, getattr(claim,"predicate","") or "", value_slot, getattr(claim,"unit","") or "",
            getattr(claim,"dose","") or "", getattr(claim,"arm","") or "", getattr(claim,"endpoint_phrase","") or "")
```
=> the `__unknown__` sentinel fires when `claim.subject` is empty / `_UNKNOWN_SUBJECT`. KEY QUESTION for (b): plan F1 says the fix locus is "the evidence distiller MAP step (`evidence_distiller.py` finding-row emission)". Is that the WRONG site? If `__unknown__` comes from an empty `claim.subject`, the real fix is wherever `claim.subject` is POPULATED upstream (claim extraction), not the distiller row emission. State the correct file:line.

### Snippet 2 — `src/polaris_graph/generator/multi_section_generator.py:147-148` (guard) + `weighted_enrichment.py:180-181`
```python
# multi_section_generator.py  _credibility_guard_decision:
    if judge is None or not gov_suffixes:
        return "degrade" if always_release else "raise"   # judge=None + always_release -> 'degrade' (skips pass body)
    return "run"
# weighted_enrichment.py:
    if credibility_analysis is None:
        return UnboundSupportsSelection([], _REASON_CREDIBILITY_NONE, 0,0,0,0,0)   # <-- run5 empty-enrichment exit
```
=> the keystone F2 (Form B) flips this guard to `"run"` on judge=None+always_release and builds the basket with a deterministic verify_fn so `credibility_analysis` is populated. Judge `run_credibility_analysis` already supports judge=None priors-only (plan cites credibility_pass.py:691,700).

### Snippet 3 — `src/polaris_graph/roles/openrouter_role_transport.py` getter L970-979, force-close ~L479, swallowed rebuild ~L1156-1157
```python
@property
def _http_client(self) -> httpx.Client:
    client = getattr(self._tls, "client", None)
    if client is None:                       # <-- F3: does NOT check is_closed; a force-closed client survives in TLS
        client = self._http_client_factory()
        self._tls.client = client
    return client
# ~L479 total-deadline timeout path:  client.close()  (force the hung socket closed)
# ~L1156-1157 rebuild after force-close:
    try:
        self._http_client = self._http_client_factory()
    except Exception:                        # <-- F3: swallowed; LAW II says log loudly
        pass
```
=> F3 = `if client is None or client.is_closed:` in the getter + stop swallowing the rebuild. On the unrecoverable path the EXISTING fail-closed `RoleTransportError` must still fire (D8 HOLDS, never a fabricated PASS).

## Answer ALL of these
(a) **Cause completeness.** Does `complete_cause_list` MISS any real reason for the 794->9 collapse within the in-scope hops (basket -> consolidation -> generator -> verify -> render)? Name any missed chokepoint with file:line. The plan asserts NO in-scope source-drop hop (collapsed=0, dropped_count=0) and the only real drop is the upstream pre-fetch fetch_cap=740 (out of scope) — confirm or refute that specifically.

(b) **Keystone soundness.** Is the keystone (decouple basket from the LLM judge — Form B: deterministic verify_fn + flip the guard to 'run' on judge=None) (i) sound, (ii) faithfulness-safe (every basket member still independently passes the unchanged strict_verify; binding gates unchanged), (iii) non-neck-choke (no NEW serial LLM hop re-armed on the basket path)? AND verify F1's fix locus per Snippet 1 — is the distiller the wrong site, with the true root being upstream empty `claim.subject`? Give the correct file:line.

(c) **4-role seam fix correctness.** Is F3 (`if client is None or client.is_closed:` + stop swallowing the rebuild) correct per Snippet 3? Confirm `httpx.Client.is_closed` exists and flips True on `.close()`. Confirm that on the unrecoverable path the EXISTING fail-closed `RoleTransportError` still fires so D8 HOLDS (never a fabricated PASS).

(d) **3-PRONG GUARD — reject any fix that:** (1) RELAXES faithfulness (binding gate -> pass / admits unverified content), (2) GRANDFATHERS (accepts stale/legacy behavior a frontier standard rejects), or (3) adds a CAP / FLOOR / THROTTLE / TARGET to force a breadth number. For EACH of F1..F16 give one word OK/FLAG. Scrutinize especially F13 (core_client year-mismatch relax — fetch-admission vs verify relaxation?), F6/F7 (claimed faithfulness TIGHTENINGS — confirm they tighten, not relax), F4 (`_regroup_graph_by_finding_dedup` — confirm group+edge-remap only, no member newly passes any gate).

Front-load every real finding now. A wrong fix or missed cause is a successful REQUEST_CHANGES.

## Output — emit EXACTLY this schema, final line is the machine-parsed verdict
```yaml
cause_completeness: <complete | missed:[chokepoint@file:line, ...]>
keystone_sound: <yes | no — reason>
f1_fix_locus_correct: <yes | no — correct file:line is ...>
four_role_seam_fix_correct: <yes | no — reason>
three_prong_per_fix: {F1: OK|FLAG, F2: ., F3: ., F4: ., F5: ., F6: ., F7: ., F8: ., F9: ., F10: ., F11: ., F12: ., F13: ., F14: ., F15: ., F16: .}
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
verdict: APPROVE | REQUEST_CHANGES
```
