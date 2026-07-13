#!/usr/bin/env python3
"""THE SYNTHESIS CONTRACT — the "deep thinking" half, without selling the faithfulness moat.

THE PROBLEM, PRECISELY
----------------------
POLARIS's entailment gate (entailment_judge.py:588) kills any sentence that introduces
"a fact, entity, MECHANISM ... NOT present in the SPAN". A cross-source inference IS, by definition,
a mechanism present in neither span. So our own gate deletes exactly the sentence type that earns
INSIGHT — 0.32 weight, the heaviest dimension, and our worst score (0.4238 vs bodhi's 0.5457).

We are not bad at analysis. We built a machine that cannot do it.

THE INSIGHT THAT MAKES THIS SOLVABLE
------------------------------------
Look at what the winning systems' synthesis prose actually asserts. cellcog, verbatim:

    "The three frameworks are complementary rather than competitive. SBTC remains the clearest model
     for relative skill demand. The task-based framework subsumes the phenomena both describe within
     a more general model of endogenous task allocation."

NO new fact. NO number. NO new entity. It RANKS and RELATES claims already on the page.
That is ADJUDICATION, and it is fully compatible with a no-fabrication guarantee.

So we do not relax the gate. We add a SECOND lane with a DIFFERENT PROOF OBLIGATION:

    EVIDENCE sentence  -> must be span-grounded in ONE source (the existing gate, UNCHANGED)
    SYNTHESIS sentence -> must be a TYPED RELATION over premises that are THEMSELVES already admitted

A synthesis sentence may not introduce a fact; it may only assert a relationship between facts that
are already proven. Its proof obligation is structural, not evidential.

THE HARD RULE THAT KEEPS US HONEST
----------------------------------
    An explanatory MECHANISM may appear ONLY if a premise span states that mechanism.
    Otherwise POLARIS may identify a contrast but MAY NOT explain its cause.

So this is legal:
    "Firm-level expansion and worker-level displacement are not contradictory: the two estimates
     observe different units of analysis."          [CONTRAST_LEVEL over two admitted premises]
And this is NOT, unless 'adoption lag' is stated in a premise:
    "The difference probably reflects slower regional adoption."   [imports an unproven mechanism]

Run the adversarial suite:  python scripts/synthesis_contract.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- the typed operations

OPERATIONS = {
    'CONVERGES':            'two or more premises agree on direction/finding',
    'CONTRASTS_DIRECTION':  'premises disagree on the direction of an effect',
    'CONTRASTS_LEVEL':      'premises differ because they observe different units (task/worker/firm/region/economy)',
    'CONTRASTS_HORIZON':    'premises differ because they observe different time horizons',
    'CONTRASTS_METHOD':     'premises differ because they use different identification strategies',
    'BOUNDARY_CONDITION':   'a premise holds only within a stated scope',
    'RANK_EVIDENCE':        'one premise rests on a stronger design than another (declared fields only)',
    'ESTABLISHES':          'the admitted evidence supports a claim AT A STATED LEVEL',
    'DOES_NOT_ESTABLISH':   'the admitted evidence does NOT support a claim at a stated level',
    'REMAINS_UNRESOLVED':   'the admitted evidence cannot distinguish between the competing accounts',
    'COVERAGE_GAP':         'a cell of the evidence matrix is empty — a real, derivable research gap',
}

# The rubric rewards ADJUDICATION, not hedging. This is the verdict vocabulary.
VERDICT_VOCAB = (
    'establishes', 'does not establish', 'supports', 'is limited to', 'cannot distinguish',
    'remains unresolved', 'are not contradictory', 'is consistent with', 'rests on',
    'observe different', 'holds only', 'no evidence', 'the evidence cannot', 'differ because',
    'complementary rather than', 'subsumes', 'rather than',
)

# A synthesis sentence may NEVER assert a causal mechanism of its own.
CAUSAL_IMPORT = re.compile(
    r'\b(because of|due to|caused by|driven by|reflects|reflecting|owing to|as a result of|'
    r'attributable to|explains why|the reason is|stems from|arises from|leads to|results in)\b', re.I)

# Forecasts / predictions are always fabrication in a literature review.
FORECAST = re.compile(r'\b(will|shall|is going to|by 20[3-9]\d|in the coming|future will|predict|forecast)\b', re.I)

# Universal quantifiers = overclaim.
UNIVERSAL = re.compile(r'\b(all|every|always|never|none|no one|invariably|universally|certainly|proves)\b', re.I)

NUMERIC = re.compile(r'\d')
SPELLED_QTY = re.compile(
    r'\b(doubl|tripl|quadrupl|halv|tenfold|twofold|threefold|a third|a quarter|a half|two[- ]thirds|'
    r'percent|percentage|majority|most of|vast majority)\w*\b', re.I)
CAP_TOKEN = re.compile(r"\b([A-Z][A-Za-z&.\-']{1,})\b")

# Discourse vocabulary that may be capitalised without being a new entity.
SAFE_CAPS = {
    'The', 'This', 'These', 'Those', 'Taken', 'Together', 'Both', 'Neither', 'Either', 'While',
    'Whereas', 'Although', 'Because', 'When', 'Where', 'If', 'In', 'At', 'By', 'For', 'A', 'An',
    'It', 'They', 'Their', 'Its', 'However', 'Yet', 'Still', 'Across', 'Within', 'One', 'Two',
    'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'AI', 'Artificial',
    'Intelligence', 'Fourth', 'Industrial', 'Revolution', 'Evidence', 'Studies', 'Research',
    'Together', 'Read', 'Seen', 'Firm', 'Worker', 'Task', 'Aggregate', 'Nor', 'That', 'What',
    # ANALYTIC META-VOCABULARY: words that describe the EVIDENCE, not entities in the world.
    # These are the declared-field names ('level', 'horizon', 'method') and the language of
    # adjudication. Admitting them cannot fabricate anything — a fabricated NAME would still be
    # caught, because it would not appear in any premise.
    'level', 'Level', 'unit', 'Unit', 'analysis', 'Analysis', 'scope', 'Scope', 'design', 'Design',
    'horizon', 'Horizon', 'method', 'Method', 'estimate', 'Estimate', 'estimates', 'Estimates',
    'outcome', 'Outcome', 'outcomes', 'Outcomes', 'finding', 'Finding', 'findings', 'Findings',
    'economy', 'Economy', 'result', 'Result', 'results', 'Results', 'literature', 'Literature',
    # THE EPISTEMIC TAXONOMY. cellcog is the ONLY system on the board that labels its own insight and
    # the judge scored it 9.8/10 for exactly that, naming all eight tagged syntheses. The gate was
    # rejecting '[Unresolved]' as a FABRICATED ENTITY. These are discourse markers about the STATUS OF
    # A CLAIM — they assert nothing about the world and cannot fabricate anything.
    'Established', 'Contested', 'Unresolved', 'Emerging', 'Conceptual', 'Analytical', 'Hypothesis',
    'Pattern', 'Synthesis', 'Our', 'We', 'Proposed', 'Argument',
}


@dataclass
class Premise:
    """An ALREADY-ADMITTED evidence sentence — it passed the existing span-grounding gate."""
    id: str
    text: str
    source: str                      # attribution string, e.g. "Autor et al. (2003), QJE"
    level: str = ''                  # task | worker | firm | occupation | region | economy
    horizon: str = ''                # short-run | long-run
    method: str = ''                 # experiment | quasi-experimental | observational | survey
    mechanisms: list[str] = field(default_factory=list)   # mechanisms STATED IN THE SPAN


@dataclass
class Synthesis:
    operation: str
    premise_ids: list[str]
    text: str


def _stem(w: str) -> str:
    """Crude stemmer. Needed because 'task level' must anchor to a premise that says 'tasks',
    and 'effect' to one that says 'effects'. Anchoring is a RELEVANCE check, not a safety check —
    loosening it cannot admit a fabrication (the entity/number/mechanism gates do that work)."""
    for suf in ('ies', 'es', 's'):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _content_lemmas(s: str) -> set[str]:
    return {_stem(w) for w in re.findall(r'[a-z]{4,}', s.lower())}


def validate(syn: Synthesis, premises: dict[str, Premise]) -> tuple[bool, str]:
    """Deterministic. No LLM. Returns (ok, reason_if_rejected)."""
    s = syn.text.strip()
    if not s:
        return False, 'empty'

    # 1. the operation must be one we defined
    if syn.operation not in OPERATIONS:
        return False, f'unknown_operation:{syn.operation}'

    # 2. premises must exist and be ADMITTED evidence
    prem = [premises[p] for p in syn.premise_ids if p in premises]
    if len(prem) != len(syn.premise_ids):
        missing = [p for p in syn.premise_ids if p not in premises]
        return False, f'premise_not_admitted:{missing}'

    # 3. relational operations need >= 2 premises from >= 2 DISTINCT sources
    relational = syn.operation not in ('COVERAGE_GAP',)
    if relational:
        if len(prem) < 2:
            return False, 'relational_operation_needs_2+_premises'
        if len({p.source for p in prem}) < 2:
            return False, 'premises_share_a_single_source'

    # 4. NO NEW NUMBER. Ever. (A number belongs to an EVIDENCE sentence, not a synthesis.)
    if NUMERIC.search(s):
        return False, 'synthesis_carries_a_digit'
    if SPELLED_QTY.search(s):
        return False, f'synthesis_carries_a_spelled_quantity:{SPELLED_QTY.search(s).group(0)}'

    # 5. NO NEW ENTITY. Every capitalised token must already appear in a premise or be discourse.
    #    Hyphenated compounds are checked COMPONENT-WISE ("Firm-level" -> "Firm", "level"), because a
    #    compound built from known words introduces no new entity. Each component still has to clear
    #    the same bar, so this cannot let a fabricated name through.
    blob = ' '.join(p.text + ' ' + p.source for p in prem)
    blob_lower = blob.lower()
    prem_caps = set(CAP_TOKEN.findall(blob))
    prem_stems = _content_lemmas(blob)
    # A PROPER NOUN is a capitalised token appearing MID-SENTENCE. A capital at the start of a sentence
    # (or after a full stop) is ORTHOGRAPHY, not an entity. Turn 2 rejected "Whether", "Reconciliation",
    # "AI's" and "driven" (from "AI-driven") as FABRICATED ENTITIES — every one a false positive, and
    # together they deleted 74 legitimate sentences. The gate's job is to catch INVENTED NAMES, not
    # capital letters.
    sentence_initial = set()
    for m in re.finditer(r'(?:^|[.!?]\s+)([A-Z][A-Za-z&.\-\']*)', s):
        sentence_initial.add(m.group(1))
    for tok in CAP_TOKEN.findall(s):
        if tok in sentence_initial:
            continue                      # orthography, not an entity
        tok = re.sub(r"'s$", '', tok)     # strip the possessive: "AI's" -> "AI"
        for part in re.split(r'[-–]', tok):
            if not part:
                continue
            if part in SAFE_CAPS or part in prem_caps:
                continue
            pl = part.lower()
            # a capitalised form of a word the premises already use (incl. plural/singular)
            if pl in blob_lower or _stem(pl) in prem_stems:
                continue
            return False, f'new_entity:{part}'

    # 6. NO IMPORTED MECHANISM, AND NO FABRICATED BINDING.
    #    A fabrication can be assembled ENTIRELY FROM TRUE PARTICULARS: bind a REAL mechanism to a REAL
    #    paper that never states it. Found live on disk: "task displacement" (Autor-Levy-Murnane's term)
    #    attributed to Bresnahan et al. (2002), whose span never says it. No "new entity" rule catches
    #    that -- both the mechanism and the paper are real. THE LIE IS IN THE BINDING.
    #    So we check TWO things: (a) is a causal mechanism asserted at all, and (b) if the sentence NAMES
    #    a source, does THAT source's own span state the mechanism it is being credited with?
    m = CAUSAL_IMPORT.search(s)
    if m:
        stated = {mm.lower() for p in prem for mm in p.mechanisms}
        if not stated:
            return False, f'causal_language_with_no_stated_mechanism:"{m.group(0)}"'
        if not any(mech in s.lower() for mech in stated):
            return False, f'causal_language_names_a_mechanism_no_premise_states:"{m.group(0)}"'
    # (b) THE BINDING CHECK -- runs whether or not causal vocabulary is present.
    #     If the sentence names an author from a premise AND asserts a mechanism, that mechanism must be
    #     stated by THAT author's premise -- not by some other paper in the room.
    for p in prem:
        surname = p.source.split()[0].rstrip(',')
        if len(surname) < 4 or surname.lower() not in s.lower():
            continue                      # this source is not named in the sentence
        for other in prem:
            if other is p:
                continue
            for mech in other.mechanisms:
                if mech.lower() in s.lower() and mech.lower() not in {x.lower() for x in p.mechanisms}:
                    return False, (f'FABRICATED_BINDING: "{mech}" is stated by {other.source.split()[0]}, '
                                   f'not by {surname} — the sentence credits the wrong paper')

    # 7. NO FORECAST, NO UNIVERSAL
    if FORECAST.search(s):
        return False, f'forecast_or_prediction:"{FORECAST.search(s).group(0)}"'
    if UNIVERSAL.search(s):
        return False, f'universal_overclaim:"{UNIVERSAL.search(s).group(0)}"'

    # 8. (REMOVED AS A HARD GATE.) This demanded "verdict vocabulary" of every uncited sentence and
    #    DELETED 163 sentences in wheel turn 1 — gutting the report to 4,021 words, below the length
    #    floor. It is a STYLE RULE WEARING A SAFETY RULE'S CLOTHES: a sentence that reads as a "vibe"
    #    is weak prose, not a fabrication. Adjudication is what the RUBRIC pays for; the CONTRACT's job
    #    is only to make lying impossible. Conflating the two is why our gate rejects 97% of the prose
    #    that the judge scores 9.8/10. Style belongs in the writer's PROMPT, not in the safety gate.

    # 9. operation-specific structural obligations, checked against DECLARED fields only
    if syn.operation == 'CONTRASTS_LEVEL':
        if len({p.level for p in prem if p.level}) < 2:
            return False, 'CONTRASTS_LEVEL but the premises do not declare 2 distinct levels'
    if syn.operation == 'CONTRASTS_HORIZON':
        if len({p.horizon for p in prem if p.horizon}) < 2:
            return False, 'CONTRASTS_HORIZON but the premises do not declare 2 distinct horizons'
    if syn.operation == 'CONTRASTS_METHOD' or syn.operation == 'RANK_EVIDENCE':
        if len({p.method for p in prem if p.method}) < 2:
            return False, f'{syn.operation} but the premises do not declare 2 distinct methods'

    # 10. must be anchored in the premises it claims to relate
    if len(_content_lemmas(s) & _content_lemmas(blob)) < 2:
        return False, 'not_anchored_in_its_premises'

    return True, ''


# ---------------------------------------------------------------- adversarial suite

P = {
    'p1': Premise('p1', 'Generative AI raised the productivity of professional writing tasks by 40 percent.',
                  'Noy and Zhang (2023), Science', level='task', horizon='short-run', method='experiment'),
    'p2': Premise('p2', 'Aggregate employment effects in AI-exposed occupations were too small to detect over the period studied.',
                  'Acemoglu et al. (2022), Journal of Labor Economics', level='economy', horizon='long-run',
                  method='observational'),
    'p3': Premise('p3', 'Firms adopting AI expanded employment relative to non-adopting competitors.',
                  'Babina et al. (2024), Journal of Financial Economics', level='firm', horizon='long-run',
                  method='observational'),
    'p4': Premise('p4', 'Routine task-intensive middle-wage occupations declined as computerisation spread, '
                        'a process the authors attribute to task displacement.',
                  'Autor et al. (2003), Quarterly Journal of Economics', level='occupation', horizon='long-run',
                  method='observational', mechanisms=['task displacement']),
}

ATTACKS = [
    # (should_admit, operation, premises, sentence, label)
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'The difference probably reflects slower regional adoption of the technology.',
     'imports a mechanism (adoption lag) no premise states'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Task-level gains of 40 percent do not establish economy-wide employment growth.',
     'carries a digit — that belongs to an EVIDENCE sentence'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Goldman Sachs analysts establish that these effects operate at different levels.',
     'fabricated attribution / new entity'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Task-level productivity gains doubled while aggregate effects remain unproven.',
     'spelled-out quantity ("doubled")'),
    (False, 'ESTABLISHES', ['p1', 'p2'],
     'AI will establish permanent job losses across the economy by 2035.',
     'forecast'),
    (False, 'CONVERGES', ['p1', 'p2'],
     'All studies establish that AI displaces workers.',
     'universal overclaim'),
    (False, 'CONTRASTS_LEVEL', ['p1'],
     'These findings observe different units of analysis.',
     'relational operation with only ONE premise'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'The literature on artificial intelligence and work is complex and multifaceted.',
     'no verdict vocabulary — a vibe, not an adjudication'),
    (False, 'CONTRASTS_HORIZON', ['p2', 'p3'],
     'These results are not contradictory: they observe different time horizons.',
     'CONTRASTS_HORIZON but both premises declare the SAME horizon (long-run)'),
    # --- these MUST be admitted: real adjudication, no new facts ---
    (True, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'These findings are not contradictory: the evidence establishes gains at the task level but '
     'does not establish an effect at the level of the economy.',
     'LEGAL: adjudicates two admitted premises across declared levels, no new fact'),
    (True, 'CONTRASTS_LEVEL', ['p2', 'p3'],
     'Firm-level expansion and undetectable aggregate effects are not contradictory, because the two '
     'estimates observe different units of analysis; the evidence is limited to relative outcomes '
     'among firms and cannot distinguish reallocation from net creation.',
     'LEGAL: reconciles firm vs economy, states what the evidence cannot do'),
    (True, 'RANK_EVIDENCE', ['p1', 'p2'],
     'The task-level result rests on an experimental design, whereas the aggregate result rests on '
     'observational data; the evidence therefore establishes the former more securely than the latter.',
     'LEGAL: ranks by DECLARED method fields only'),
    (True, 'REMAINS_UNRESOLVED', ['p2', 'p3'],
     'Taken together, the evidence cannot distinguish whether firm-level gains represent net job '
     'creation or reallocation from competitors; this remains unresolved.',
     'LEGAL: names exactly what the literature cannot settle'),
    (True, 'CONTRASTS_LEVEL', ['p2', 'p4'],
     'The occupational decline is attributable to task displacement, whereas the aggregate series '
     'does not establish a comparable effect at the level of the economy.',
     'LEGAL: causal language permitted — "task displacement" IS stated in premise p4'),
]


def self_test() -> int:
    print('=== SYNTHESIS CONTRACT — adversarial suite ===')
    print('   (deterministic; no LLM; a FALSE ADMISSION is a breach of the moat)\n')
    false_admits = false_rejects = 0
    for should_admit, op, pids, text, label in ATTACKS:
        ok, why = validate(Synthesis(op, pids, text), P)
        good = (ok == should_admit)
        if not good and ok:
            false_admits += 1
        if not good and not ok:
            false_rejects += 1
        mark = 'PASS' if good else ('**FALSE ADMIT**' if ok else '**FALSE REJECT**')
        verdict = 'ADMIT ' if ok else 'REJECT'
        print(f'  [{mark:>15}] {verdict} :: {label}')
        if not ok and should_admit:
            print(f'                     rejected because: {why}')
        if ok and not should_admit:
            print(f'                     !! ADMITTED: "{text[:70]}"')
    n_valid = sum(1 for a in ATTACKS if a[0])
    n_invalid = len(ATTACKS) - n_valid
    print(f'\n  invalid examples: {n_invalid}  | FALSE ADMISSIONS: {false_admits}  (release requires ZERO)')
    print(f'  valid examples  : {n_valid}  | false rejections: {false_rejects}')
    if false_admits:
        print('\n  ** RELEASE BLOCKED: the contract admitted a fabrication. **')
        return 1
    if false_rejects:
        print('\n  ** contract is SAFE but too strict — it rejects legitimate adjudication. **')
        return 1
    print('\n  ** CONTRACT GREEN: zero false admissions, zero false rejections. **')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    print(json.dumps({'operations': OPERATIONS}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
