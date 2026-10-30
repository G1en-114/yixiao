# -*- coding: utf-8 -*-
"""(1) TriageAgent: understand the complaint -> department hypotheses + risk level (department catalog bounds the output)."""
import re

from agent.roles.base import RoleAgent

DEFAULT_DEPTS = ['Cardiology', 'Respiratory Medicine']
# deterministic red-flag keywords -> label added to red_flags
RED_FLAG_RULES = [
    (r'chest (pain|tightness|pressure)', 'Chest pain'),
    (r'short(ness)? of breath|breathless|difficulty breathing|dyspn', 'Shortness of breath'),
    (r'unconscious|altered (mental|consciousness)|confus|faint|syncope', 'Altered consciousness'),
    (r'\bshock\b', 'Shock'),
]


class TriageAgent(RoleAgent):
    name = 'triage'
    prompt_file = 'TriageAgent.md'
    required_keys = ('urgency', 'candidate_departments', 'red_flags', 'triage_reasoning', 'next_step')

    def run(self, case_id, state):
        self._case_id = case_id
        d = state.data
        user = (f"Chief complaint: {d['chief_complaint']}\nAge: {d['age']}\nSex: {d['sex']}\n"
                f"Duration: {d['duration']}\nSymptoms: {', '.join(d['symptoms'])}\n"
                f"Past history: {d['past_history']}\nAllergies: {d['allergies']}\nCurrent medications: {d['medications']}\n"
                f"Allowed departments (choose only from these): {', '.join(sorted(self.kb.departments))}")
        data = self.ask_json(case_id, '', user)
        # deterministic post-check: red flags force escalation + emergency advice
        reds = data.get('red_flags') or []
        complaint = (d['chief_complaint'] + ' ' + ' '.join(d['symptoms'])).lower()
        auto_flags = [label for pat, label in RED_FLAG_RULES if re.search(pat, complaint)]
        for flag in auto_flags:
            if not any(flag.lower() in str(r).lower() for r in reds):
                reds.append(flag)
        if auto_flags and data.get('urgency') not in ('high', 'emergency'):
            data['urgency'] = 'high'
            data['triage_reasoning'] += ' (Rule engine: emergency red flags present, urgency raised.)'
        if auto_flags and 'emergency' not in data.get('next_step', '').lower():
            data['next_step'] += '; the patient should go to the emergency department now'
        data['red_flags'] = reds
        data['candidate_departments'] = [x for x in data.get('candidate_departments', [])
                                         if x in self.kb.departments] or list(DEFAULT_DEPTS)
        state.apply('triage', {'triage': data})
        self.handoff(case_id, 'interview', 'triage complete, moving to interview',
                     _result(data), data.get('candidate_departments'))
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    risk = {'low': 'low', 'medium': 'medium', 'high': 'high', 'emergency': 'high'}.get(data.get('urgency'), 'medium')
    return AgentResult('triage', 'ok', data, risk, data.get('candidate_departments', []))
