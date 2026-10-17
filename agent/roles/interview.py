# -*- coding: utf-8 -*-
"""② InterviewAgent 问诊：信息差分析 → 每轮仅追问 2-3 个关键问题，达停止条件即止。"""
from agent.roles.base import RoleAgent


class InterviewAgent(RoleAgent):
    name = 'interview'
    prompt_file = 'InterviewAgent.md'
    required_keys = ('questions', 'missing_information', 'stop_interview')

    def run(self, case_id, state, round_no=1):
        self._case_id = case_id
        d = state.data
        skills = self.kb.retrieve(d['chief_complaint'], d['triage'].get('candidate_departments'))
        knowledge = self.kb.format_skills(skills)
        history = []
        for r in d['interview_rounds']:
            for q in r['questions']:
                history.append(f"问：{q['question']}\n答：{r['answers'].get(q['id'], '（未答）')}")
        asked = [q['question'] for r in d['interview_rounds'] for q in r['questions']]
        user = (f"主诉：{d['chief_complaint']}\n年龄：{d['age']} 性别：{d['sex']} 持续时间：{d['duration']}\n"
                f"既往史：{d['past_history']} 过敏史：{d['allergies']} 用药：{d['medications']}\n"
                f"候选科室：{', '.join(d['triage'].get('candidate_departments', []))}\n"
                f"当前是第 {round_no} 轮问诊（最多 3 轮，每轮只问 2-3 个最关键问题，"
                f"不得重复已问过的问题）。\n已完成问答：\n" + ('\n'.join(history) if history else '（无）') +
                f"\n已问过的问题：{'；'.join(asked) if asked else '（无）'}")
        data = self.ask_json(case_id, knowledge, user)
        qs = [q for q in data.get('questions', []) if q.get('question')][:3]
        for i, q in enumerate(qs, 1):
            q.setdefault('id', f'r{round_no}q{i}')
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
