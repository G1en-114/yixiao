# -*- coding: utf-8 -*-
"""(4) ExaminationAgent: choose exams from the required / differential / avoid lists and curb over-testing.

Exam results are entered by the user; the system never invents them (honest boundary).
"""
from agent.roles.base import RoleAgent


class ExaminationAgent(RoleAgent):
    name = 'examination'
    prompt_file = 'ExaminationAgent.md'
    required_keys = ('recommended_exams', 'avoid_exams', 'missing_results_warning')

    def run(self, case_id, state):
        self._case_id = case_id
        d = state.data
        cands = d['differential'].get('differential_diagnoses', [])
        skills = [self.kb.find_skill(c.get('disease')) for c in cands]
        skills = [s for s in skills if s] or \
            self.kb.retrieve(_case_text(d), d['triage'].get('candidate_departments'))
        knowledge = self.kb.format_skills(skills[:4])
        avoid_all = sorted({x for s in skills for x in s['exam_strategy']['avoid']})
        catalog = self.kb.related_exams(skills[:4])
        user = (_case_text(d) +
                f"\nCandidate diseases: {', '.join(c.get('disease', '') for c in cands)}\n"
                f"Catalog exams you may choose from (copy the exact name): {'; '.join(catalog)}\n"
                f"These exams are on the avoid list and must never be recommended: {'; '.join(avoid_all[:8])}")
        data = self.ask_json(case_id, knowledge, user)
        plan, avoid_used = [], []
        for e in data.get('recommended_exams', []):
            raw = e.get('exam', '') if isinstance(e, dict) else str(e)
            if raw in avoid_all:
                avoid_used.append(raw)           # rule-engine hard filter: avoid items never enter the plan
                continue
            name = self.kb.canonical_exam(raw)
            if not name:
                self._emit(case_id, 'exam_filtered', f'Filtered exam outside the catalog: {raw}')
                continue
            if any(p['exam'] == name for p in plan):
                continue
            plan.append({'exam': name, 'priority': e.get('priority', 'essential') if isinstance(e, dict) else 'essential',
                         'reason': e.get('reason', '') if isinstance(e, dict) else ''})
        if avoid_used:
            self._emit(case_id, 'avoid_filtered', f'Filtered avoid-list exams: {", ".join(avoid_used)}')
        # rule engine: the leading candidate's Skill essentials always come first
        added, skill_order = [], []
        if skills:
            for line in skills[0]['exam_strategy']['essential']:
                hit = self.kb.match_exam_line(line, top=1)
                if not hit or hit[0] in avoid_all:
                    continue
                # an exam already in the plan that is the same test or a more specific form of it covers this line
                cover = next((p['exam'] for p in plan if self.kb.exam_covers(p['exam'], hit[0])), None)
                if cover:
                    skill_order.append(cover)
                    continue
                plan.append({'exam': hit[0], 'priority': 'essential',
                             'reason': f"Essential exam in the {skills[0]['disease']} Skill (rule engine)"})
                added.append(hit[0]); skill_order.append(hit[0])
        if added:
            self._emit(case_id, 'essential_added', f'Rule engine added Skill essentials: {", ".join(added)}')
        for p in plan:                       # covering exams count as essential
            if p['exam'] in skill_order:
                p['priority'] = 'essential'
        order = {n: i for i, n in enumerate(skill_order)}
        essential = sorted((p for p in plan if p['priority'] == 'essential'), key=lambda p: order.get(p['exam'], len(order)))
        conditional = [p for p in plan if p['priority'] != 'essential'][:2]
        plan = (essential + conditional)[:6]
        data['recommended_exams'] = plan
        data['avoid_exams'] = avoid_all
        state.apply('examination', {'exam_plan': plan})
        self.handoff(case_id, 'specialist', 'exam plan ready; waiting for user-entered results before the specialist consult',
                     _result(plan))
        return _result(plan)


def _case_text(d):
    from agent.roles.differential import _case_text
    return _case_text(d)


def _result(plan):
    from agent.core.messages import AgentResult
    return AgentResult('examination', 'ok', {'plan': plan}, 'low', [p['exam'] for p in plan])
