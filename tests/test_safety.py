# -*- coding: utf-8 -*-
"""Safety rule engine: allergy / PDE-5 x nitrate precondition / avoid exams / out-of-catalog exams / red-flag ER advice."""
from agent.runtime import safety_rules


def test_allergy_rejects_penicillin():
    v = safety_rules.check_treatment('penicillin allergy', '', 'Amoxicillin capsules for the infection', '')
    assert v and v[0][0] == 'allergy_conflict'


def test_pde5_nitrate_reject_then_pass_after_revision():
    v1 = safety_rules.check_treatment('', '', 'Sublingual nitroglycerin', '')
    assert v1 and 'PDE-5' in v1[0][1]
    v2 = safety_rules.check_treatment('', '', 'Nitrates only after PDE-5 inhibitor use is ruled out',
                                      'PDE-5 exclusion recorded as a precondition (sildenafil)')
    assert v2 == []


def test_avoid_exam_rejected(kb):
    v = safety_rules.check_exams(['Nonexistent exam'], kb, avoid_lists=[['Nonexistent exam']])
    kinds = [x[0] for x in v]
    assert 'exam_not_in_catalog' in kinds and 'avoid_exam' in kinds


def test_duplicate_exam_rejected(kb):
    v = safety_rules.check_exams(['Electrocardiography (ECG)', 'Electrocardiography (ECG)'], kb)
    assert any(x[0] == 'duplicate_exam' for x in v)


def test_red_flag_requires_er_advice():
    v = safety_rules.check_red_flag_advice({'red_flags': ['chest pain'], 'urgency': 'high'}, 'Rest and observe')
    assert v and v[0][0] == 'red_flag_er_missing'
    assert safety_rules.check_red_flag_advice({'red_flags': ['chest pain'], 'urgency': 'high'},
                                              'Go to the emergency department now') == []


def test_withheld_nitrate_is_not_an_order():
    """A plan that withholds nitrates (e.g. after recent sildenafil) must not trigger the nitrate x PDE-5 rule."""
    plan = ('Aspirin 300 mg chewed. Withhold nitrates entirely because of the sildenafil taken the night before last; '
            'nitrates are contraindicated until the interval is verified.')
    assert safety_rules.check_treatment('', '', plan, '') == []
    assert safety_rules.check_treatment('', '', 'Do not administer nitroglycerin', '') == []


def test_negation_does_not_hide_a_real_order():
    plan = 'Avoid NSAIDs. Sublingual nitroglycerin 0.5 mg for ongoing pain'
    v = safety_rules.check_treatment('', '', plan, '')
    assert v and v[0][0] == 'precondition_0'
