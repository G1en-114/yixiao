# -*- coding: utf-8 -*-
"""⑧ AuditAgent 审计回放：梳理每步决策所用知识与理由，生成可回放的复盘摘要。"""
from agent.roles.base import RoleAgent


class AuditAgent(RoleAgent):
    name = 'audit'
    prompt_file = 'AuditAgent.md'
    required_keys = ('audit_summary', 'agent_timeline', 'knowledge_hits', 'safety_decision', 'limitations')

    def run(self, case_id, state, stats=None):
        self._case_id = case_id
        d = state.data
        reviews = d['safety'].get('reviews', [])
        safety_decision = '通过' if reviews and reviews[-1]['approved'] else \
            ('驳回后保守回退' if reviews else '未审查')
        events = self.orchestrator.store.events_for(case_id) if self.orchestrator else []
        lanes = ', '.join('{lane}({dept})'.format(lane=k, dept=v.get('department'))
                          for k, v in d['specialists'].items())
        user = (f"病例：{d['chief_complaint']}（{d['sex']}，{d['age']} 岁）\n"
                f"拟诊：{', '.join(d['attending'].get('diagnosis_candidates', []))}\n"
                f"问诊轮数：{len(d['interview_rounds'])}\n"
                f"检查项：{', '.join(p['exam'] for p in d['exam_plan'])}\n"
                f"会诊通道：{lanes}\n"
                f"安全审查：{len(reviews)} 轮，结论 {safety_decision}\n"
                f"事件总数：{len(events)}；模型调用：{stats.get('model_calls', 0)}；"
                f"tokens：{stats.get('prompt_tokens', 0) + stats.get('completion_tokens', 0)}")
        data = self.ask_json(case_id, '', user)
        data['event_count'] = len(events)
        data['stats'] = stats or {}
        state.apply('audit', {'audit': data})
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('audit', 'ok', data, 'low', data.get('knowledge_hits', []))
