# -*- coding: utf-8 -*-
"""(8) AuditAgent: trace the knowledge and reasoning behind each step and produce a replayable review summary."""
from agent.roles.base import RoleAgent


class AuditAgent(RoleAgent):
    name = 'audit'
    prompt_file = 'AuditAgent.md'
    required_keys = ('audit_summary', 'agent_timeline', 'knowledge_hits', 'safety_decision', 'limitations')

    def run(self, case_id, state, stats=None):
        self._case_id = case_id
        stats = stats or {}
        d = state.data
        reviews = d['safety'].get('reviews', [])
        safety_decision = 'approved' if reviews and reviews[-1]['approved'] else \
            ('conservative fallback after rejection' if reviews else 'not reviewed')
        events = self.orchestrator.store.events_for(case_id) if self.orchestrator else []
        lanes = ', '.join('{lane} ({dept})'.format(lane=k, dept=v.get('department'))
                          for k, v in d['specialists'].items())
        user = (f"Case: {d['chief_complaint']} ({d['sex']}, {d['age']} years)\n"
                f"Working diagnosis: {', '.join(d['attending'].get('diagnosis_candidates', []))}\n"
                f"Interview rounds: {len(d['interview_rounds'])}\n"
                f"Exams: {', '.join(p['exam'] for p in d['exam_plan'])}\n"
                f"Consult lanes: {lanes}\n"
                f"Safety review: {len(reviews)} round(s), outcome {safety_decision}\n"
                f"Total events: {len(events)}; model calls: {stats.get('model_calls', 0)}; "
                f"tokens: {stats.get('prompt_tokens', 0) + stats.get('completion_tokens', 0)}")
        data = self.ask_json(case_id, '', user)
        data['event_count'] = len(events)
        data['stats'] = stats
        state.apply('audit', {'audit': data})
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('audit', 'ok', data, 'low', data.get('knowledge_hits', []))
