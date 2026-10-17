# -*- coding: utf-8 -*-
"""① TriageAgent 分诊：主诉理解 → 科室假设 + 风险分级（科室目录约束输出范围）。"""
from agent.roles.base import RoleAgent


class TriageAgent(RoleAgent):
    name = 'triage'
    prompt_file = 'TriageAgent.md'
    required_keys = ('urgency', 'candidate_departments', 'red_flags', 'triage_reasoning', 'next_step')

    def run(self, case_id, state):
        self._case_id = case_id
        d = state.data
        user = (f"主诉：{d['chief_complaint']}\n年龄：{d['age']}\n性别：{d['sex']}\n"
                f"持续时间：{d['duration']}\n症状：{', '.join(d['symptoms'])}\n"
                f"既往史：{d['past_history']}\n过敏史：{d['allergies']}\n当前用药：{d['medications']}\n"
                f"可选科室（只能从中选择）：{'、'.join(sorted(self.kb.departments))}")
        data = self.ask_json(case_id, '', user)
        # 确定性后验：红旗征象强制升级 + 急诊建议
        reds = data.get('red_flags') or []
        complaint = d['chief_complaint'] + ' ' + ' '.join(d['symptoms'])
        auto_flags = [k for k in ('胸痛', '呼吸困难', '意识障碍', '休克') if k in complaint]
        for flag in auto_flags:
            if flag not in reds:
                reds.append(flag)
        if auto_flags and data.get('urgency') not in ('high', 'emergency'):
            data['urgency'] = 'high'
            data['triage_reasoning'] += '（规则引擎：存在急症红旗征象，紧急程度上调）'
        if auto_flags and '急诊' not in data.get('next_step', ''):
            data['next_step'] += '；请患者立即线下急诊就医'
        data['red_flags'] = reds
        data['candidate_departments'] = [x for x in data.get('candidate_departments', [])
                                         if x in self.kb.departments] or ['心内科', '呼吸内科']
        state.apply('triage', {'triage': data})
        self.handoff(case_id, 'interview', '分诊完成，进入问诊',
                     _result(data), data.get('candidate_departments'))
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    risk = {'low': 'low', 'medium': 'medium', 'high': 'high', 'emergency': 'high'}.get(data.get('urgency'), 'medium')
    return AgentResult('triage', 'ok', data, risk, data.get('candidate_departments', []))
