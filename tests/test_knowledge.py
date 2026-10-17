# -*- coding: utf-8 -*-
"""知识资产：19 科室 / 584 疾病 Skill / 584 标准疾病 / 837 检查目录。"""


def test_19_departments(kb):
    assert len(kb.departments) == 19
    assert '心内科' in kb.departments and '呼吸内科' in kb.departments


def test_584_skills(kb):
    assert len(kb.all_skills) == 584


def test_584_standard_diseases(kb):
    assert len(kb.diseases) == 584
    assert len(kb.disease_names) == 584


def test_837_exams(kb):
    assert len(kb.exams_by_name) == 837
    assert kb.is_valid_exam('心电图（ECG）')
    assert not kb.is_valid_exam('不存在的检查')


def test_cad_skill_supports_demo_path(kb):
    """胸痛演示路径的知识完整性：CAD Skill 存在、含必要检查与治疗。"""
    s = kb.find_skill('冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）')
    assert s and s['department'] == '心内科'
    assert s['exam_strategy']['essential']
    assert s['treatment']['first_line']


def test_retrieve_chest_pain_hits_cardio(kb):
    skills = kb.retrieve('胸口压榨样疼痛伴呼吸困难，高血压史', ['心内科', '呼吸内科'])
    assert skills
    assert any('心' in s['department'] for s in skills)
