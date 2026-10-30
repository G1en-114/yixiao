# -*- coding: utf-8 -*-
"""(5) SpecialistAgent: loaded per department; two specialist views run independently in parallel."""
from agent.roles.base import RoleAgent


class SpecialistAgent(RoleAgent):
    name = 'specialist'
    prompt_file = 'SpecialistAgent.md'
    required_keys = ('department', 'primary_opinion', 'likely_diseases', 'key_evidence',
                     'uncertainties', 'recommendations')

    def run(self, case_id, state, department='Cardiology', lane='A'):
        self._case_id = case_id
        d = state.data
        skills = self.kb.retrieve(_case_text(d), [department], top_k=5)
        dept_skills = [s for s in skills if s['department'] == department][:3]
        knowledge = self.kb.format_skills((dept_skills + [s for s in skills if s not in dept_skills])[:5])
        user = (_case_text(d) +
                f"\n\nYou represent: {department} (consult lane {lane}). "
                f"Answer only from the {department} point of view, independently of the other consult lane.")
        data = self.ask_json(case_id, knowledge, user)
        data['department'] = department
        data['lane'] = lane
        self.handoff(case_id, 'attending', f'{department} (lane {lane}) opinion issued', _result(lane, data),
                     data.get('likely_diseases', []))
        return _result(lane, data)


def _case_text(d):
    from agent.roles.differential import _case_text
    return _case_text(d)


def _result(lane, data):
    from agent.core.messages import AgentResult
    return AgentResult(f'specialist_{lane}', 'ok', data, 'medium', data.get('likely_diseases', []))
