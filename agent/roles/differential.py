# -*- coding: utf-8 -*-
"""(3) DifferentialAgent: ranked differential with supporting / opposing evidence from disease Skills (bounded by the disease catalog)."""
from agent.roles.base import RoleAgent


class DifferentialAgent(RoleAgent):
    name = 'differential'
    prompt_file = 'DifferentialAgent.md'
    required_keys = ('differential_diagnoses', 'knowledge_used', 'next_step')

    def run(self, case_id, state):
        self._case_id = case_id
        d = state.data
        depts = d['triage'].get('candidate_departments', [])
        skills = self.kb.retrieve(_case_text(d), depts, top_k=6)
        knowledge = self.kb.format_skills(skills)
        user = (_case_text(d) +
                f"\nCandidate departments: {', '.join(depts)}\n"
                f"Standard disease catalog: final disease names must be copied exactly from the Skill names in the knowledge block above.")
        data = self.ask_json(case_id, knowledge, user)
        cands = []
        for c in data.get('differential_diagnoses', [])[:5]:
            name = self.kb.canonical_disease(c.get('disease', ''))
            if name:
                c['disease'] = name
                cands.append(c)
        if not cands:                    # no standard-name match: fall back to the retrieved Skills
            cands = [{'disease': s['disease'], 'department': s['department'],
                      'confidence': 'medium', 'supporting_evidence': ['Matched by knowledge-base retrieval'],
                      'against_evidence': ['Insufficient evidence; refer for specialist evaluation']} for s in skills[:3]]
        data['differential_diagnoses'] = cands
        data['knowledge_used'] = [c.get('disease') for c in cands]
        state.apply('differential', {'differential': data})
        self.handoff(case_id, 'examination', 'differential complete, moving to exam planning', _result(data), data['knowledge_used'])
        return _result(data)


def _case_text(d):
    lines = [f"Chief complaint: {d['chief_complaint']} (duration {d['duration']})",
             f"Patient: {d['sex']}, {d['age']} years", f"Symptoms: {', '.join(d['symptoms'])}",
             f"Past history: {d['past_history']}; allergies: {d['allergies']}; medications: {d['medications']}",
             f"Triage: urgency {d['triage'].get('urgency')}, candidate departments {', '.join(d['triage'].get('candidate_departments', []))}"]
    for r in d['interview_rounds']:
        for q in r['questions']:
            lines.append(f"Q: {q['question']} A: {r['answers'].get(q['id'], '(no answer)')}")
    if d['exam_inputs']:
        lines.append('Known exam results: ' + '; '.join(f'{k}: {v}' for k, v in d['exam_inputs'].items()))
    return '\n'.join(lines)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('differential', 'ok', data, 'medium', data.get('knowledge_used', []))
