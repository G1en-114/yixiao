# -*- coding: utf-8 -*-
"""⑤ SpecialistAgent 专科会诊：按科室动态加载，两个专科视角并行独立分析。"""
from agent.roles.base import RoleAgent


class SpecialistAgent(RoleAgent):
    name = 'specialist'
    prompt_file = 'SpecialistAgent.md'
    required_keys = ('department', 'primary_opinion', 'likely_diseases', 'key_evidence',
                     'uncertainties', 'recommendations')

    def run(self, case_id, state, department='心内科', lane='A'):
        self._case_id = case_id
        d = state.data
        skills = self.kb.retrieve(_case_text(d), [department], top_k=5)
        dept_skills = [s for s in self.kb.departments.get(department, [])][:3]
        knowledge = self.kb.format_skills((dept_skills + [s for s in skills if s not in dept_skills])[:5])
        user = (_case_text(d) +
                f"\n\n你代表的科室：{department}（会诊通道 {lane}）。"
                f"只从 {department} 的专科角度输出，与其他会诊通道相互独立。")
        data = self.ask_json(case_id, knowledge, user)
        data['department'] = department
        data['lane'] = lane
        self.handoff(case_id, 'attending', f'{department}（通道{lane}）专科意见已出具', _result(lane, data),
                     data.get('likely_diseases', []))
        return _result(lane, data)


def _case_text(d):
    from agent.roles.differential import _case_text
    return _case_text(d)


def _result(lane, data):
    from agent.core.messages import AgentResult
    return AgentResult(f'specialist_{lane}', 'ok', data, 'medium', data.get('likely_diseases', []))
