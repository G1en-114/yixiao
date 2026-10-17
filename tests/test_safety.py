# -*- coding: utf-8 -*-
"""安全规则引擎：过敏 / PDE-5×硝酸酯前置 / avoid 检查 / 目录外检查 / 红旗急诊。"""
from agent.runtime import safety_rules


def test_allergy_rejects_penicillin():
    v = safety_rules.check_treatment('青霉素过敏', '', '阿莫西林胶囊 抗感染', '')
    assert v and v[0][0] == 'allergy_conflict'


def test_pde5_nitrate_reject_then_pass_after_revision():
    v1 = safety_rules.check_treatment('', '', '硝酸甘油舌下含服', '')
    assert v1 and 'PDE-5' in v1[0][1]
    v2 = safety_rules.check_treatment('', '', '硝酸酯类：排除 PDE-5 抑制剂使用史后使用',
                                      '已登记前置条件：使用前排除 PDE-5（西地那非）')
    assert v2 == []


def test_avoid_exam_rejected(kb):
    v = safety_rules.check_exams(['不存在的检查'], kb, avoid_lists=[['不存在的检查']])
    kinds = [x[0] for x in v]
    assert 'exam_not_in_catalog' in kinds and 'avoid_exam' in kinds


def test_duplicate_exam_rejected(kb):
    v = safety_rules.check_exams(['心电图（ECG）', '心电图（ECG）'], kb)
    assert any(x[0] == 'duplicate_exam' for x in v)


def test_red_flag_requires_er_advice():
    v = safety_rules.check_red_flag_advice({'red_flags': ['胸痛'], 'urgency': 'high'}, '建议休息观察')
    assert v and v[0][0] == 'red_flag_er_missing'
    assert safety_rules.check_red_flag_advice({'red_flags': ['胸痛'], 'urgency': 'high'},
                                              '请立即线下急诊') == []
