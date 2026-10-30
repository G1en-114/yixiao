# -*- coding: utf-8 -*-
"""Knowledge assets: 19 departments / 584 disease Skills / 584 standard diseases / 837 exams."""


def test_19_departments(kb):
    assert len(kb.departments) == 19
    assert 'Cardiology' in kb.departments and 'Respiratory Medicine' in kb.departments


def test_584_skills(kb):
    assert len(kb.all_skills) == 584


def test_584_standard_diseases(kb):
    assert len(kb.diseases) == 584
    assert len(kb.disease_names) == 584


def test_837_exams(kb):
    assert len(kb.exams_by_name) == 837
    assert kb.is_valid_exam('Electrocardiography (ECG)')
    assert not kb.is_valid_exam('Nonexistent exam')


def test_cad_skill_supports_demo_path(kb):
    """Knowledge integrity for the chest-pain demo path: the CAD Skill exists with essential exams and treatment."""
    s = kb.find_skill('Coronary atherosclerotic heart disease (coronary artery disease, CAD)')
    assert s and s['department'] == 'Cardiology'
    assert s['exam_strategy']['essential']
    assert s['treatment']['first_line']


def test_retrieve_chest_pain_hits_cardio(kb):
    skills = kb.retrieve('Crushing chest pain with shortness of breath, history of hypertension', ['Cardiology', 'Respiratory Medicine'])
    assert skills
    assert any(s['department'] == 'Cardiology' for s in skills)
