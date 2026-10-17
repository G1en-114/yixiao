# -*- coding: utf-8 -*-
"""③ DifferentialAgent 鉴别：结合疾病 Skill 输出鉴别排序与支持/排除依据（疾病名录限定）。"""
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
                f"\n候选科室：{', '.join(depts)}\n"
                f"标准疾病名录（最终诊断名必须从中选择）：见上方知识区块中的疾病名。")
        data = self.ask_json(case_id, knowledge, user)
        cands = []
        for c in data.get('differential_diagnoses', [])[:5]:
            name = c.get('disease', '')
            if self.kb.is_standard_disease(name):
                cands.append(c)
        if not cands:                    # 无标准名匹配时回退：取检索 Skill 的疾病名
            cands = [{'disease': s['disease'], 'department': s['department'],
                      'confidence': 'medium', 'supporting_evidence': ['基于知识库检索匹配'],
                      'against_evidence': ['证据不足，建议专科进一步评估']} for s in skills[:3]]
        data['differential_diagnoses'] = cands
        data['knowledge_used'] = [c.get('disease') for c in cands]
        state.apply('differential', {'differential': data})
        self.handoff(case_id, 'examination', '鉴别完成，进入检查规划', _result(data), data['knowledge_used'])
        return _result(data)


def _case_text(d):
    lines = [f"主诉：{d['chief_complaint']}（持续 {d['duration']}）",
             f"患者：{d['sex']}，{d['age']} 岁", f"症状：{', '.join(d['symptoms'])}",
             f"既往史：{d['past_history']}；过敏史：{d['allergies']}；用药：{d['medications']}",
             f"分诊：紧急程度 {d['triage'].get('urgency')}，候选科室 {', '.join(d['triage'].get('candidate_departments', []))}"]
    for r in d['interview_rounds']:
        for q in r['questions']:
            lines.append(f"问：{q['question']} 答：{r['answers'].get(q['id'], '（未答）')}")
    if d['exam_inputs']:
        lines.append('已知检查结果：' + '；'.join(f'{k}：{v}' for k, v in d['exam_inputs'].items()))
    return '\n'.join(lines)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('differential', 'ok', data, 'medium', data.get('knowledge_used', []))
