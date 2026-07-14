"""P1 — runtime-contract generality.

The downstream runtime (composer frame, argument planner, synthesis contract) must carry NO task-72
subject as a production default. A clinical, a legal and a CS review, compiled and rendered through the
same code, must inherit none of the AI / labor-market / journal-only / 4IR wording that used to be baked
into `WRITE_PROMPT`, `OUTLINE`, the report title, `argument_planner.default_contract()`, and the
`SAFE_CAPS` / `LEVEL_CUES` authorities.

Positive-proof, generality: a capitalised entity is admissible only when it is EARNED (premise, or the
original question/compiled contract); it is never on a subject allow-list. Swapping the entity for an
unrelated one gives the same structural verdict; putting it into a premise makes it admissible with no
edit to any list.
"""
import re

import pytest

import cellcog_composer as C
import research_contract as RC
import argument_planner as AP
from synthesis_contract import Premise, Synthesis, validate


FORBIDDEN = ('artificial intelligence', 'labor market', 'labour market', 'labor-market',
             'fourth industrial', '4ir', 'peer-reviewed journal', 'peer reviewed journal',
             'journal articles only', 'restructuring impact')

CLINICAL = 'Summarize the clinical evidence on metformin for type 2 diabetes.'
LEGAL = 'Review the case law on the contract doctrine of promissory estoppel.'
CS = 'Review the literature on transformer architectures for code generation.'
ALL_PROMPTS = [CLINICAL, LEGAL, CS]


class _FakeBundle:
    """A minimal bundle: the frame renderers touch only admitted_ids()/resolve() for a spelled count."""
    def __init__(self, work_ids=()):
        self._ids = list(range(len(work_ids)))
        self._works = list(work_ids)

    def admitted_ids(self):
        return list(self._ids)

    def resolve(self, cid):
        class _M:
            work_id = self._works[cid] if cid < len(self._works) else 'w'
        return _M()


def _rendered_text(nodes):
    return ' '.join(getattr(n, 'text', '') or '' for n in nodes)


# ── the compiled contract carries the REAL subject and no benchmark wording ──────────────────────

@pytest.mark.parametrize('question', ALL_PROMPTS)
def test_rendered_frame_inherits_no_task_wording(question):
    contract = RC.compile_contract(question, use_llm=False)
    b = _FakeBundle(work_ids=('w1', 'w2'))
    text = _rendered_text(C.abstract_nodes(b, contract) + C.methods_nodes(b, contract))
    title = C.report_title(contract)
    low = (text + ' ' + title).lower()
    hits = [w for w in FORBIDDEN if w in low]
    assert not hits, f'inherited task wording {hits} for {question!r}: {low[:200]}'


@pytest.mark.parametrize('question', ALL_PROMPTS)
def test_source_prose_comes_from_compliance_prose(question):
    contract = RC.compile_contract(question, use_llm=False)
    b = _FakeBundle()
    text = _rendered_text(C.methods_nodes(b, contract))
    # When the question imposed no journal-only constraint, the methods prose must NOT assert one.
    assert 'only articles published in peer-reviewed journals' not in text.lower()


def test_journal_only_prompt_DOES_render_its_own_constraint():
    # Generality cuts both ways: a request that DID ask for journals must say so — the prose tracks the
    # compiled source policy, it is not blanket-suppressed.
    contract = RC.compile_contract('Using only peer-reviewed journal articles, review the evidence on X.',
                                   use_llm=False)
    text = _rendered_text(C.methods_nodes(_FakeBundle(), contract))
    assert 'peer-reviewed' in text.lower()


# ── the planner default is EMPTY and facet-agnostic, never AI ────────────────────────────────────

def test_default_contract_is_empty_and_facet_agnostic():
    dc = AP.default_contract()
    assert dc.span_facets == {}          # no technology/outcome/industry/geography vocabulary
    assert dc.polarity == {}
    blob = (dc.question + ' ' + repr(dc.span_facets) + ' ' + repr(dc.adjudicative_roles)).lower()
    assert 'artificial intelligence' not in blob
    assert 'labor' not in blob and 'labour' not in blob


def test_no_contract_render_names_no_domain():
    text = _rendered_text(C.abstract_nodes(_FakeBundle(), None))
    low = text.lower()
    assert not any(w in low for w in FORBIDDEN)


def test_contract_from_research_contract_carries_the_real_question_not_ai():
    contract = RC.compile_contract(CLINICAL, use_llm=False)
    rc = AP.contract_from_research_contract(contract)
    assert 'metformin' in rc.question.lower() or 'diabetes' in rc.question.lower()
    assert rc.span_facets == {}
    assert 'artificial intelligence' not in rc.question.lower()


# ── caps entity: earned, never allow-listed (positive proof + generality) ────────────────────────

def _neutral_premises(entity_in_premise=''):
    t1 = 'The compound reduced mortality in the treated cohort.'
    if entity_in_premise:
        t1 = f'The {entity_in_premise} compound reduced mortality in the treated cohort.'
    return {
        'p1': Premise('p1', t1, 'Ng and Okafor (2021), Trials', direction='negative', outcome='mortality'),
        'p2': Premise('p2', 'A separate cohort also showed reduced mortality under treatment.',
                      'Reyes and Silva (2022), Registry', direction='negative', outcome='mortality'),
    }


_BASE = 'The evidence establishes a consistent reduction in mortality across both cohorts.'


def test_base_synthesis_admits():
    ok, why = validate(Synthesis('CONVERGES', ['p1', 'p2'], _BASE), _neutral_premises())
    assert ok, why


@pytest.mark.parametrize('entity', ['Zorblax', 'Qwibbletron', 'Fnordax'])
def test_capitalised_entity_absent_from_premises_and_contract_is_rejected(entity):
    text = (f'The evidence establishes that {entity} drives a consistent reduction in mortality '
            f'across both cohorts.')
    ok, why = validate(Synthesis('CONVERGES', ['p1', 'p2'], text), _neutral_premises())
    assert ok is False
    assert why == f'new_entity:{entity}'


def test_entity_in_the_premise_is_admissible_without_any_allowlist():
    entity = 'Zorblax'
    text = (f'The evidence establishes that {entity} drives a consistent reduction in mortality '
            f'across both cohorts.')
    ok, why = validate(Synthesis('CONVERGES', ['p1', 'p2'], text),
                       _neutral_premises(entity_in_premise=entity))
    assert ok, why


def test_entity_in_the_question_context_is_admissible_without_any_allowlist():
    entity = 'Zorblax'
    text = (f'The evidence establishes that {entity} drives a consistent reduction in mortality '
            f'across both cohorts.')
    ok, why = validate(Synthesis('CONVERGES', ['p1', 'p2'], text), _neutral_premises(),
                       context=f'A clinical review of {entity} therapy and mortality outcomes.')
    assert ok, why


def test_swapping_the_entity_gives_the_same_structural_verdict():
    # Metamorphic: the verdict is determined by STRUCTURE (unearned capitalised token), not by identity.
    verdicts = set()
    for entity in ('Zorblax', 'Qwibbletron', 'Metropolis', 'Braxidil'):
        text = (f'The evidence establishes that {entity} drives a consistent reduction in mortality '
                f'across both cohorts.')
        ok, _ = validate(Synthesis('CONVERGES', ['p1', 'p2'], text), _neutral_premises())
        verdicts.add(ok)
    assert verdicts == {False}          # every unearned entity rejects, identically


def test_no_second_allowlist_in_owned_is_safe():
    # owned_is_safe must run the SAME structural predicate as validate — an unearned entity is rejected,
    # and one present in the premise blob is admitted. No SAFE_CAPS import decides it.
    blob = 'the compound reduced mortality in the treated cohort'
    ok_bad, why = AP.owned_is_safe('The evidence establishes that Zorblax reduces mortality.',
                                   set(), blob)
    assert ok_bad is False and 'Zorblax' in why
    ok_good, _ = AP.owned_is_safe('The evidence establishes that the compound reduces mortality.',
                                  set(), blob)
    assert ok_good is True
