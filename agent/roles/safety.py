# -*- coding: utf-8 -*-
"""⑦ SafetyAgent 安全审查：规则引擎 + 大模型双重校验，拥有流程驳回权（驳回即阻断并触发主治修订）。"""
import os

from agent.roles.base import RoleAgent
from agent.runtime import safety_rules

SAFETY_RULES_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'safety_rules.md')


class SafetyAgent(RoleAgent):
    name = 'safety'
    prompt_file = 'SafetyAgent.md'
    required_keys = ('approved', 'risk_level', 'rejection_reasons', 'required_revision',
                     'patient_facing_warning')

    def run(self, case_id, state, revision_no=0):
        self._case_id = case_id
        d = state.data
        attending = d['attending']
        treatment_text = '；'.join(attending.get('treatment_plan', []))
        allergies = d['allergies']

        # --- 规则引擎（确定性，可复现）---
        reasons, revisions = [], []
        for rule_id, reason, revision in safety_rules.check_treatment(
                allergies, d['medications'], treatment_text, d['pde5_exclusion']):
            reasons.append(f'[{rule_id}] {reason}')
            revisions.append(revision)
        avoid_lists = []
        for c in d['differential'].get('differential_diagnoses', []):
            s = self.kb.find_skill(c.get('disease'))
            if s:
                avoid_lists.append(s['exam_strategy']['avoid'])
        for rule_id, reason, revision in safety_rules.check_exams(d['exam_plan'], self.kb, avoid_lists):
            reasons.append(f'[{rule_id}] {reason}')
            revisions.append(revision)

        # --- 大模型审查 ---
        user = (f"病例：{d['chief_complaint']}（{d['sex']}，{d['age']} 岁）\n"
                f"过敏史：{allergies}；用药史：{d['medications']}\n"
                f"红旗征象：{', '.join(d['triage'].get('red_flags', [])) or '无'}\n"
                f"拟诊：{', '.join(attending.get('diagnosis_candidates', []))}\n"
                f"治疗方案：{treatment_text}\n"
                f"检查计划：{', '.join(p['exam'] for p in d['exam_plan'])}\n"
                f"安全前置条件：{'; '.join(d['safety_preconditions']) or '无'}\n"
                f"第 {revision_no + 1} 轮审查。")
        try:
            rules_md = open(SAFETY_RULES_MD, encoding='utf-8').read()[:3000] if os.path.exists(SAFETY_RULES_MD) else ''
            llm_review = self.ask_json(case_id, rules_md, user)
        except Exception:
            llm_review = {}
        for r in llm_review.get('rejection_reasons', []) or []:
            if isinstance(r, str) and r not in reasons:
                reasons.append(f'[llm] {r}')

        approved = not reasons and llm_review.get('approved', True) is not False
        review = {'round': revision_no + 1, 'approved': approved,
                  'risk_level': llm_review.get('risk_level', 'high' if reasons else 'low'),
                  'rejection_reasons': reasons,
                  'required_revision': '；'.join(revisions) if revisions else llm_review.get('required_revision', ''),
                  'patient_facing_warning': llm_review.get('patient_facing_warning', '')}
        state.apply('safety', {'safety': {'reviews': [review]}})
        if not approved:
            self.handoff(case_id, 'attending', '安全驳回，退回主治强制修订',
                         _result(review), reasons)
        return _result(review)


def _result(review):
    from agent.core.messages import AgentResult
    return AgentResult('safety', 'ok' if review['approved'] else 'rejected', review,
                       review['risk_level'], review['rejection_reasons'])
