# -*- coding: utf-8 -*-
"""(6) AttendingAgent: summarise agreements and conflicts, output the final diagnosis and first-line plan (names aligned to the catalog)."""
from agent.roles.base import RoleAgent

FALLBACK_DIAGNOSIS = 'Refer for specialist evaluation'


class AttendingAgent(RoleAgent):
    name = 'attending'
    prompt_file = 'AttendingAgent.md'
    required_keys = ('consensus', 'conflicts', 'final_assessment', 'diagnosis_candidates',
                     'treatment_plan', 'evidence_level')

    def run(self, case_id, state, rejection=None, revision_no=0):
        self._case_id = case_id
        from agent.roles.differential import _case_text
        d = state.data
        cands = d['differential'].get('differential_diagnoses', [])
        skills = [self.kb.find_skill(c.get('disease')) for c in cands]
        skills = [s for s in skills if s]
        knowledge = self.kb.format_skills(skills[:4])
        opinions = []
        for lane, op in d['specialists'].items():
            opinions.append(f"[Lane {lane} · {op.get('department')}] Main judgement: {op.get('primary_opinion')}; "
                            f"leading diseases: {', '.join(op.get('likely_diseases', []))}; "
                            f"recommendations: {', '.join(op.get('recommendations', []))}")
        names = sorted({c.get('disease', '') for c in cands} |
                       {n for op in d['specialists'].values() for n in op.get('likely_diseases', [])
                        if self.kb.canonical_disease(n)})
        user = (_case_text(d) + '\n\nDual-specialist opinions:\n' + '\n'.join(opinions) +
                f"\n\nStandard disease names available for diagnosis_candidates (copy exactly): {'; '.join(names)}")
        if rejection:
            user += (f"\n\n[Safety review round {revision_no} REJECTED the plan. Address every point below.]\n" +
                     '\n'.join(f'- {r}' for r in rejection.get('rejection_reasons', [])) +
                     f"\nRequired revision: {rejection.get('required_revision', '')}"
                     "\nReflect each revision in treatment_plan, or record the confirmed precondition in safety_preconditions.")
        data = self.ask_json(case_id, knowledge, user)
        fixed = []
        for name in data.get('diagnosis_candidates', []):
            canon = self.kb.canonical_disease(name)
            fixed.append(canon or FALLBACK_DIAGNOSIS)
        data['diagnosis_candidates'] = list(dict.fromkeys(fixed))[:3]
        data['revision_no'] = revision_no
        if rejection:
            data['revised_from_rejection'] = rejection
        state.apply('attending', {'attending': data, 'attending_history': list(d['attending_history']) + [data]})
        self.handoff(case_id, 'safety',
                     f'attending plan{" (revision %d)" % revision_no if revision_no else ""} submitted for safety review',
                     _result(data), data.get('diagnosis_candidates', []))
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('attending', 'ok', data, 'medium', data.get('diagnosis_candidates', []))
