# FX-10 (#1115) grounding — completeness NOT_APPLICABLE 3VL state

INDEP. Base = current HEAD bot/I-ready-017-faithfulness (FX-09 verified, 61856dfd).

## Targets (verified against running code)
- `completeness_checker.py` (find: src/.../completeness_checker.py): the report dataclass has fields
  total_applicable/total_covered/total_uncovered/notes + a `covered_fraction` PROPERTY (lines ~61-65):
  `if self.total_applicable == 0: return 1.0` else total_covered/total_applicable. KEEP numeric (do
  NOT return None — evaluator_gate.py:186 does `None < 0.5` -> TypeError).
- FIX leg 1: add a `completeness_state` property → 'not_applicable' if total_applicable==0 else 'measured'.
- FIX leg 2: surface completeness_state + notes in completeness.json + manifest.completeness
  (serialization sites in run_honest_sweep_r3.py — grep for completeness.json write + manifest['completeness']).
- FIX leg 3: evaluator_gate.py:186 — treat not_applicable as advisory/skip (NOT pass); keep numeric compare safe.
- FIX leg 4: ON-mode path run_honest_sweep_r3.py:2548 — set notes=['no_checklist_loaded'].
- run_honest_sweep_r3.py:4999 already guards total_applicable>0 (verify, likely no change).

## Tests (test_completeness_r6_gap3.py)
- no-checklist domain -> state=='not_applicable', notes present, numeric stays 1.0 WITH state.
- 2/4 covered -> state=='measured', covered_fraction==0.5.
- consumer-safety: not_applicable report through evaluator_gate -> NO TypeError, advisory/skip not pass.

## §-1.1 (fresh ON-mode run OR replay): manifest.completeness does NOT present bare covered_fraction=1.0
as complete; carries completeness_state + notes; report.md '0/0 topics covered' consistent; neither
consumer changed its gate decision.

## Resume: add completeness_state property + serialization + evaluator_gate guard + ON-mode notes; test; §-1.1; ONE gate.
