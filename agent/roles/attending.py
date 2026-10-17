# -*- coding: utf-8 -*-
"""⑥ AttendingAgent 主治：归纳一致项与冲突项，输出最终诊断和一线治疗方案（诊断名 100% 对齐名录）。"""
from agent.roles.base import RoleAgent


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
            opinions.append(f"[通道 {lane} · {op.get('department')}] 主判断：{op.get('primary_opinion')}；"
                            f"倾向疾病：{', '.join(op.get('likely_diseases', []))}；"
                            f"建议：{', '.join(op.get('recommendations', []))}")
        user = _case_text(d) + '\n\n双专科会诊意见：\n' + '\n'.join(opinions)
        if rejection:
            user += (f"\n\n【安全审查第 {revision_no} 轮驳回意见，必须逐条落实修订】\n" +
                     '\n'.join(f'- {r}' for r in rejection.get('rejection_reasons', [])) +
                     f"\n修订要求：{rejection.get('required_revision', '')}"
                     "\n请在 treatment_plan 中逐条体现修订，或在 safety_preconditions 中记录已确认的前置条件。")
        data = self.ask_json(case_id, knowledge, user)
        fixed = []
        for name in data.get('diagnosis_candidates', []):
            if self.kb.is_standard_disease(name):
                fixed.append(name)
            else:                            # 诊断名对齐标准名录（取含关键词的名录项）
                match = [n for n in self.kb.disease_names if name and (name in n or n.split('（')[0] in name)]
                fixed.append(match[0] if match else '建议专科进一步评估')
        data['diagnosis_candidates'] = fixed[:3]
        data['revision_no'] = revision_no
        if rejection:
            data['revised_from_rejection'] = rejection
        state.apply('attending', {'attending': data})
        self.handoff(case_id, 'safety', f'主治方案{"（第 %d 次修订）" % revision_no if revision_no else ""}提交安全审查',
                     _result(data), data.get('diagnosis_candidates', []))
        return _result(data)


def _result(data):
    from agent.core.messages import AgentResult
    return AgentResult('attending', 'ok', data, 'medium', data.get('diagnosis_candidates', []))
