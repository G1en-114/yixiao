# -*- coding: utf-8 -*-
"""④ ExaminationAgent 检查规划：必要/鉴别/避免三清单选择检查，抑制过度医疗。

检查结果由用户录入，系统不编造（诚实边界）。
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
        user = (_case_text(d) +
                f"\n候选疾病：{', '.join(c.get('disease', '') for c in cands)}\n"
                f"可选检查举例（必须使用检查目录中的标准名称）：{', '.join(list(self.kb.exams_by_name)[:40])} ...\n"
                f"以下检查为 avoid 清单，绝对不得推荐：{'；'.join(avoid_all[:8])}")
        data = self.ask_json(case_id, knowledge, user)
        plan, avoid_used = [], []
        for e in data.get('recommended_exams', []):
            name = e.get('exam', '') if isinstance(e, dict) else str(e)
            if name in avoid_all:
                avoid_used.append(name)          # 规则引擎硬过滤：avoid 不得进入计划
                continue
            if not self.kb.is_valid_exam(name):
                self._emit(case_id, 'exam_filtered', f'目录外检查已过滤：{name}')
                continue
            plan.append({'exam': name, 'priority': e.get('priority', 'essential') if isinstance(e, dict) else 'essential',
                         'reason': e.get('reason', '') if isinstance(e, dict) else ''})
        if avoid_used:
            self._emit(case_id, 'avoid_filtered', f'已过滤 avoid 检查：{", ".join(avoid_used)}')
        plan = plan[:6]
        data['recommended_exams'] = plan
        data['avoid_exams'] = avoid_all
        state.apply('examination', {'exam_plan': plan})
        self.handoff(case_id, 'specialist', '检查规划完成，等待用户录入结果后进入双专科会诊', _result(plan))
        return _result(plan)


def _case_text(d):
    from agent.roles.differential import _case_text
    return _case_text(d)


def _result(plan):
    from agent.core.messages import AgentResult
    return AgentResult('examination', 'ok', {'plan': plan}, 'low', [p['exam'] for p in plan])
