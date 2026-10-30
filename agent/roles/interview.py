# -*- coding: utf-8 -*-
"""(2) InterviewAgent: information-gap analysis -> only 2-3 key questions per round, stop once the picture is complete."""
from agent.roles.base import RoleAgent


class InterviewAgent(RoleAgent):
    name = 'interview'
    prompt_file = 'InterviewAgent.md'
    required_keys = ('questions', 'missing_information', 'stop_interview')

    def run(self, case_id, state, round_no=1):
        self._case_id = case_id
        d = state.data
        skills = self.kb.retrieve(d['chief_complaint'] + ' ' + ' '.join(d['symptoms']),
                                  d['triage'].get('candidate_departments'))
        knowledge = self.kb.format_skills(skills)
        history = []
        for r in d['interview_rounds']:
            for q in r['questions']:
                history.append(f"Q: {q['question']}\nA: {r['answers'].get(q['id'], '(no answer)')}")
        asked = [q['question'] for r in d['interview_rounds'] for q in r['questions']]
        user = (f"Chief complaint: {d['chief_complaint']}\nAge: {d['age']}  Sex: {d['sex']}  Duration: {d['duration']}\n"
                f"Past history: {d['past_history']}  Allergies: {d['allergies']}  Medications: {d['medications']}\n"
                f"Candidate departments: {', '.join(d['triage'].get('candidate_departments', []))}\n"
                f"This is interview round {round_no} (at most 3 rounds; ask only the 2-3 most important questions, "
                f"never repeat a question already asked).\nCompleted Q&A:\n" + ('\n'.join(history) if history else '(none)') +
                f"\nQuestions already asked: {'; '.join(asked) if asked else '(none)'}")
        data = self.ask_json(case_id, knowledge, user)
        qs = [q for q in data.get('questions', []) if q.get('question')][:3]
        for i, q in enumerate(qs, 1):
            q['id'] = q.get('id') or f'r{round_no}q{i}'
            q.setdefault('why', '')
        data['questions'] = qs
        state.apply('interview', {'interview_rounds': [{
            'round': round_no, 'questions': qs, 'answers': {}, 'asked_before': asked,
            'missing_information': data.get('missing_information', []),
            'stop_interview': bool(data.get('stop_interview'))}]})
        return _result(data, qs)


def _result(data, qs):
    from agent.core.messages import AgentResult
    return AgentResult('interview', 'ok', data, 'low', [q.get('why', '') for q in qs])
