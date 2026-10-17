# -*- coding: utf-8 -*-
"""确定性安全规则（规则引擎），与 SafetyAgent 大模型审查双重校验。

规则来源：安全规则知识库（过敏/禁忌/急症红旗/过度检查/相互作用前置条件）。
这些检查不依赖大模型，保证演示可复现：驳回瞬间一定发生。
"""

RED_FLAGS = ['胸痛伴大汗', '呼吸困难', '意识障碍', '休克', '卒中', '严重过敏']

# 药物类别关键词 → 需要排除的前置条件
DRUG_PRECONDITIONS = [
    {   # 硝酸酯 × PDE-5：原版演示中的标志性驳回
        'trigger_any': ['硝酸甘油', '硝酸酯', '单硝酸异山梨酯', '硝酸异山梨酯'],
        'condition_field': 'pde5_exclusion',
        'reason': '治疗方案含硝酸酯类药物，但未排除 PDE-5 抑制剂（西地那非/伐地那非/他达拉非）'
                  '使用史——两者联用可致严重低血压，属禁忌。',
        'revision': '请在方案中补充 PDE-5 抑制剂使用排除信息：明确询问近期（尤其 24-48 小时内）'
                    '是否使用西地那非/伐地那非/他达拉非；未排除前硝酸酯仅可作为备选并标注前提条件。',
        'satisfied_if_contains': '排除',
    },
]

ALLERGY_RULES = [
    {'allergy_any': ['青霉素', '盘尼西林', '青酶素'],
     'drug_any': ['青霉素', '阿莫西林', '氨苄西林', '哌拉西林', '苄星青霉素'],
     'reason': '患者过敏史记录青霉素类过敏，治疗方案含青霉素类药物，存在过敏风险。'},
    {'allergy_any': ['头孢'],
     'drug_any': ['头孢'],
     'reason': '患者过敏史记录头孢类过敏，治疗方案含头孢类药物。'},
    {'allergy_any': ['磺胺'],
     'drug_any': ['磺胺', '复方新诺明'],
     'reason': '患者过敏史记录磺胺类过敏，治疗方案含磺胺类药物。'},
]


def check_treatment(allergies, medications_history, treatment_text, pde5_exclusion):
    """返回 [(rule_id, reason, revision_required)]；空列表表示通过。"""
    violations = []
    treatment_text = treatment_text or ''
    history_text = f'{medications_history or ""} {pde5_exclusion or ""}'

    for rule in ALLERGY_RULES:
        if any(a in (allergies or '') for a in rule['allergy_any']) and \
           any(d in treatment_text for d in rule['drug_any']):
            violations.append(('allergy_conflict', rule['reason'],
                               '请更换为与过敏史无冲突的替代药物，并说明替代依据。'))

    for i, rule in enumerate(DRUG_PRECONDITIONS):
        if any(t in treatment_text for t in rule['trigger_any']):
            satisfied = rule['satisfied_if_contains'] in history_text
            if not satisfied:
                violations.append((f'precondition_{i}', rule['reason'], rule['revision']))

    return violations


def check_exams(exam_plan, kb, avoid_lists=None):
    """检查计划合规：目录内、非 avoid、非重复。返回违规列表。"""
    violations = []
    seen = set()
    avoid_all = set()
    for av in (avoid_lists or []):
        avoid_all.update(av)
    for exam in exam_plan:
        name = exam if isinstance(exam, str) else exam.get('exam', '')
        if not kb.is_valid_exam(name):
            violations.append(('exam_not_in_catalog', f'检查项「{name}」不在 837 项标准检查目录内', '目录外检查不得提交'))
        if name in avoid_all:
            violations.append(('avoid_exam', f'检查项「{name}」属于 Skill 标记的 avoid 清单', '不得推荐 avoid 检查'))
        if name in seen:
            violations.append(('duplicate_exam', f'检查项「{name}」重复提交', '已完成操作不得重复建议'))
        seen.add(name)
    return violations


def check_red_flag_advice(triage, final_report_text):
    """红旗征象必须建议线下急诊。"""
    reds = triage.get('red_flags') or []
    urgency = triage.get('urgency', '')
    if reds or urgency in ('high', 'emergency'):
        if '急诊' not in (final_report_text or ''):
            return [('red_flag_er_missing', '病例存在红旗征象/高紧急度，但结论未建议线下急诊',
                     '结论必须包含立即线下急诊建议')]
    return []
