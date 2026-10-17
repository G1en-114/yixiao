# -*- coding: utf-8 -*-
"""CaseState：中心病例状态，唯一事实源。各角色只返回结构化补丁，按写权限合并。"""

# 角色 → 允许写入的字段（写权限隔离，避免互相覆盖）
PERMISSIONS = {
    'triage': {'triage'},
    'interview': {'interview_rounds', 'collected'},
    'differential': {'differential'},
    'examination': {'exam_plan'},
    'specialist': {'specialists'},
    'attending': {'attending', 'diagnosis_final', 'safety_preconditions', 'pde5_exclusion'},
    'safety': {'safety'},
    'audit': {'audit', 'final'},
    'system': {'stage', 'exam_inputs', 'pde5_exclusion', 'error'},
}


class CaseState:
    def __init__(self, intake):
        self.data = {
            'chief_complaint': intake.get('chief_complaint', ''),
            'age': intake.get('age'),
            'sex': intake.get('sex', ''),
            'duration': intake.get('duration', ''),
            'symptoms': intake.get('symptoms', []),
            'past_history': intake.get('past_history', ''),
            'allergies': intake.get('allergies', ''),
            'medications': intake.get('medications', ''),
            'exam_inputs': {},           # 用户录入的检查结果 {检查名: 结果}
            'pde5_exclusion': '',        # PDE-5 抑制剂使用排除信息
            'triage': {},
            'interview_rounds': [],      # [{round, questions:[{id,question,why}], answers:{}}]
            'collected': [],
            'differential': {},
            'exam_plan': [],
            'specialists': {},           # {dept: opinion}
            'attending': {},
            'safety_preconditions': [],
            'safety': {'reviews': []},
            'audit': {},
            'final': {},
            'stage': 'created',
            'error': '',
        }
        self.patches = []                # 追加式补丁历史，不覆盖

    def apply(self, role, patch):
        allowed = PERMISSIONS.get(role)
        if allowed is None:
            raise ValueError(f'未知角色: {role}')
        illegal = [k for k in patch if k not in allowed]
        if illegal:
            raise PermissionError(f'{role} 无权写入: {illegal}')
        for k, v in patch.items():
            if k in ('interview_rounds',):
                self.data[k].extend(v)
            elif k in ('specialists',):
                self.data[k].update(v)
            elif k == 'safety':
                reviews = v.pop('reviews', None)
                if reviews:
                    self.data['safety'].setdefault('reviews', []).extend(reviews)
                self.data['safety'].update(v)
            else:
                self.data[k] = v
        self.patches.append({'role': role, 'patch': patch})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def snapshot(self):
        return json_copy(self.data)

    def public_view(self):
        """给前端的脱敏视图。"""
        d = self.data
        return {
            'chief_complaint': d['chief_complaint'], 'age': d['age'], 'sex': d['sex'],
            'duration': d['duration'], 'symptoms': d['symptoms'],
            'past_history': d['past_history'], 'allergies': d['allergies'],
            'medications': d['medications'], 'stage': d['stage'], 'error': d['error'],
            'triage': d['triage'], 'interview_rounds': d['interview_rounds'],
            'differential': d['differential'], 'exam_plan': d['exam_plan'],
            'exam_inputs': d['exam_inputs'], 'specialists': d['specialists'],
            'attending': d['attending'], 'safety': d['safety'],
            'safety_preconditions': d['safety_preconditions'],
            'audit': d['audit'], 'final': d['final'],
        }


def json_copy(obj):
    import json
    return json.loads(json.dumps(obj, ensure_ascii=False))
