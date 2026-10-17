# -*- coding: utf-8 -*-
"""临床管线：从一条主诉到一份可复盘诊疗报告的端到端状态机。

可暂停/可恢复：问诊等待患者回答，检查等待用户录入结果，失败可从阶段重试。
"""
import threading
import uuid

from agent.core.state import CaseState
from agent.runtime import safety_rules

STAGES = ['triage', 'interview', 'differential', 'examination', 'specialist',
          'attending', 'safety', 'audit', 'final']
MAX_INTERVIEW_ROUNDS = 3
MIN_INTERVIEW_ROUNDS = 2
MAX_SAFETY_ROUNDS = 2


class Pipeline:
    def __init__(self, orchestrator, bus, store, kb, llm):
        from agent.roles.attending import AttendingAgent
        from agent.roles.audit import AuditAgent
        from agent.roles.differential import DifferentialAgent
        from agent.roles.examination import ExaminationAgent
        from agent.roles.interview import InterviewAgent
        from agent.roles.safety import SafetyAgent
        from agent.roles.specialist import SpecialistAgent
        from agent.roles.triage import TriageAgent
        self.orch = orchestrator
        self.bus = bus
        self.store = store
        self.kb = kb
        for role in (TriageAgent(llm, kb), InterviewAgent(llm, kb), DifferentialAgent(llm, kb),
                     ExaminationAgent(llm, kb), SpecialistAgent(llm, kb), AttendingAgent(llm, kb),
                     SafetyAgent(llm, kb), AuditAgent(llm, kb)):
            orchestrator.register(role)
        self.cases = {}                  # case_id -> dict(state, thread, wait_event, lock)
        self._lock = threading.Lock()

    # ---- 创建与推进 ----
    def create_case(self, intake, auto=False):
        case_id = uuid.uuid4().hex[:12]
        state = CaseState(intake)
        entry = {'state': state, 'wait': threading.Event(), 'lock': threading.Lock(),
                 'phase': 'interview', 'pending_round': 0, 'auto': auto}
        with self._lock:
            self.cases[case_id] = entry
        self.store.create_case(case_id, intake)
        self.bus.emit(case_id, 'system', 'case_created',
                      f'病例创建：{intake.get("chief_complaint", "")}', {'intake': intake})
        t = threading.Thread(target=self._run_intake, args=(case_id,), daemon=True)
        entry['thread'] = t
        t.start()
        return case_id

    def _auto_respond(self, case_id, kind, payload):
        """SDK/评测模式：自动应答追问与自动录入检查结果（Web 演示为人工输入）。"""
        entry = self.cases.get(case_id)
        if not entry or not entry.get('auto'):
            return
        intake = entry['state'].data

        def _go():
            if kind == 'answers':
                answers = {}
                for q in payload.get('questions', []):
                    custom = (intake.get('interview_answers') or {}).get(q['question'])
                    answers[q['id']] = custom or '无上述情况（自动应答）'
                self.submit_answers(case_id, answers)
            else:
                results = {}
                for exam in payload.get('exams', []):
                    custom = (intake.get('exam_results') or {}).get(exam)
                    results[exam] = custom or '已完成，未见明显异常（自动录入）'
                self.submit_exam_results(case_id, results)
        threading.Timer(0.3, _go).start()

    def _run_intake(self, case_id):
        entry = self.cases[case_id]
        state = entry['state']
        try:
            self.orch.run(case_id, 'triage', state)
            state.apply('system', {'stage': 'interview'})
            self._interview_round(case_id, 1)
        except Exception as exc:
            self._fail(case_id, exc)

    def _interview_round(self, case_id, round_no):
        entry = self.cases[case_id]
        state = entry['state']
        result = self.orch.run(case_id, 'interview', state, round_no=round_no)
        questions = result.payload.get('questions', [])
        stop = bool(result.payload.get('stop_interview'))
        if not questions or (stop and round_no >= MIN_INTERVIEW_ROUNDS) or round_no >= MAX_INTERVIEW_ROUNDS:
            self._after_interview(case_id)
            return
        entry['phase'] = 'await_answers'
        entry['pending_round'] = round_no
        state.apply('system', {'stage': f'interview_r{round_no}'})
        self.bus.emit(case_id, 'system', 'await_user',
                      f'等待患者回答第 {round_no} 轮追问', {'round': round_no, 'questions': questions})
        self._auto_respond(case_id, 'answers', {'questions': questions})

    def submit_answers(self, case_id, answers):
        entry = self.cases[case_id]
        with entry['lock']:
            if entry['phase'] != 'await_answers':
                return False
            state = entry['state']
            rounds = state.get('interview_rounds')
            current = rounds[-1]
            for q in current['questions']:
                current['answers'][q['id']] = answers.get(q['id'], '（未答）')
                self.store.add_message(case_id, current['round'], 'user_answer',
                                       f"{q['question']} → {answers.get(q['id'], '')}")
            entry['phase'] = 'running'
            round_no = current['round']
        self.bus.emit(case_id, 'system', 'answers_received', f'第 {round_no} 轮回答已提交', {'answers': answers})
        threading.Thread(target=self._continue_interview, args=(case_id, round_no), daemon=True).start()
        return True

    def _continue_interview(self, case_id, round_no):
        entry = self.cases[case_id]
        try:
            self._interview_round(case_id, round_no + 1)
        except Exception as exc:
            self._fail(case_id, exc)

    def _after_interview(self, case_id):
        entry = self.cases[case_id]
        state = entry['state']
        self.orch.run(case_id, 'differential', state)
        self.orch.run(case_id, 'examination', state)
        state.apply('system', {'stage': 'await_exams'})
        entry['phase'] = 'await_exams'
        self.bus.emit(case_id, 'system', 'await_user', '等待用户录入检查结果（系统不伪造检查数据）',
                      {'exams': [p['exam'] for p in state.get('exam_plan')]})
        self._auto_respond(case_id, 'exams', {'exams': [p['exam'] for p in state.get('exam_plan')]})

    def submit_exam_results(self, case_id, results):
        entry = self.cases[case_id]
        with entry['lock']:
            if entry['phase'] != 'await_exams':
                return False
            entry['phase'] = 'running'
            entry['state'].apply('system', {'exam_inputs': results})
        self.bus.emit(case_id, 'system', 'exam_results_received', '检查结果已录入', {'results': results})
        threading.Thread(target=self._run_consultation, args=(case_id,), daemon=True).start()
        return True

    def _run_consultation(self, case_id):
        entry = self.cases[case_id]
        state = entry['state']
        try:
            # ⑤ 双专科并行会诊
            cands = state.get('differential').get('differential_diagnoses', [])
            depts = []
            for c in cands:
                dept = c.get('department')
                if dept and dept in self.kb.departments and dept not in depts:
                    depts.append(dept)
            for dept in state.get('triage').get('candidate_departments', []):
                if dept not in depts:
                    depts.append(dept)
            depts = (depts + ['心内科', '呼吸内科'])[:2]
            state.apply('system', {'stage': 'specialist'})
            threads = []
            results = {}
            for i, dept in enumerate(depts[:2], 1):
                lane = 'AB'[i - 1]
                self.bus.emit(case_id, f'specialist_{lane}', 'agent_start',
                              f'双专科并行会诊启动：通道{lane} · {dept}', {'department': dept, 'lane': lane})

                def _run_specialist(dept=dept, lane=lane):
                    try:
                        results[lane] = self.orch.run(case_id, 'specialist', state,
                                                      department=dept, lane=lane)
                    except Exception as exc:
                        self.bus.emit(case_id, f'specialist_{lane}', 'agent_error', str(exc), {})

                th = threading.Thread(target=_run_specialist, daemon=True)
                threads.append(th)
                th.start()
            for th in threads:
                th.join(120)
            state.apply('specialist', {'specialists': {
                lane: r.payload for lane, r in results.items()}})

            # ⑥⑦ 主治 → 安全审查（驳回重试最多 2 轮）
            state.apply('system', {'stage': 'attending'})
            revision_no = 0
            while True:
                self.orch.run(case_id, 'attending', state,
                              rejection=entry.get('last_rejection'), revision_no=revision_no)
                state.apply('system', {'stage': 'safety'})
                safety_result = self.orch.run(case_id, 'safety', state, revision_no=revision_no)
                if safety_result.status == 'ok' or revision_no >= MAX_SAFETY_ROUNDS - 1:
                    break
                entry['last_rejection'] = {
                    'rejection_reasons': safety_result.payload.get('rejection_reasons', []),
                    'required_revision': safety_result.payload.get('required_revision', '')}
                # 修订落实前置条件：主治把驳回要求写入 preconditions，系统登记排除信息
                self._apply_revision(state, safety_result.payload)
                revision_no += 1
                self.bus.emit(case_id, 'system', 'revision',
                              f'主治按驳回意见修订（第 {revision_no} 次）', {'revision_no': revision_no})

            # ⑧ 审计 → 最终报告
            self.orch.run(case_id, 'audit', state, stats=self.orch.stats_for(case_id))
            final = self._build_final(case_id, state, safety_result)
            state.apply('audit', {'final': final})
            state.apply('system', {'stage': 'final'})
            self.store.finish_case(case_id, 'final', final)
            self.bus.emit(case_id, 'system', 'case_final', '诊疗报告交付（可验收·可复盘）', {'final': final})
        except Exception as exc:
            self._fail(case_id, exc)

    def _apply_revision(self, state, safety_payload):
        """把驳回要求登记为方案前置条件；硝酸酯类驳回同步登记 PDE-5 排除动作。"""
        reasons = safety_payload.get('rejection_reasons', [])
        preconds = list(state.get('safety_preconditions'))
        preconds += reasons
        patch = {'safety_preconditions': preconds}
        if any('PDE-5' in r or '硝酸' in r for r in reasons) and not state.get('pde5_exclusion'):
            patch['pde5_exclusion'] = ('已登记前置条件：使用硝酸酯前必须排除 PDE-5 抑制剂'
                                       '（西地那非/伐地那非/他达拉非）使用史（24-48 小时内）')
        state.apply('attending', patch)

    def _build_final(self, case_id, state, safety_result):
        d = state.data
        att = d['attending']
        reviews = d['safety'].get('reviews', [])
        approved = bool(reviews and reviews[-1]['approved'])
        stats = self.orch.stats_for(case_id)
        events = self.store.events_for(case_id)
        reds = d['triage'].get('red_flags', [])
        warnings = []
        if not approved:
            warnings.append('安全审查两轮修订后仍未完全通过，以下为低风险保守建议，请线下就医确认。')
        if reds or d['triage'].get('urgency') in ('high', 'emergency'):
            warnings.append('存在急症红旗征象：请立即线下急诊，不要延误。')
        return {
            'title': '医晓结构化诊疗报告（教学演示）',
            'patient': {'age': d['age'], 'sex': d['sex']},
            'chief_complaint': d['chief_complaint'],
            'triage': d['triage'],
            'interview_rounds': len(d['interview_rounds']),
            'differential': d['differential'].get('differential_diagnoses', []),
            'exams': [{'exam': p['exam'], 'priority': p['priority'], 'result': d['exam_inputs'].get(p['exam'], '')}
                      for p in d['exam_plan']],
            'consultation': {lane: {'department': op.get('department'), 'opinion': op.get('primary_opinion'),
                                    'likely': op.get('likely_diseases', [])}
                             for lane, op in d['specialists'].items()},
            'attending': {'consensus': att.get('consensus', []), 'conflicts': att.get('conflicts', []),
                          'final_assessment': att.get('final_assessment', ''),
                          'diagnosis_candidates': att.get('diagnosis_candidates', []),
                          'treatment_plan': att.get('treatment_plan', []),
                          'evidence_level': att.get('evidence_level', '')},
            'safety': {'approved': approved, 'rounds': len(reviews),
                       'reviews': reviews,
                       'preconditions': d.get('safety_preconditions') or [],
                       'warning': warnings},
            'audit': d['audit'],
            'stats': {'events': len(events), **stats},
            'disclaimer': '本报告仅用于教学演示与临床决策辅助研究，不替代真实医疗诊断、处方或急救。',
        }

    def _fail(self, case_id, exc):
        state = self.cases[case_id]['state']
        state.apply('system', {'error': str(exc)})
        self.bus.emit(case_id, 'system', 'error', f'流程失败，如实上报：{exc}', {'error': str(exc)})

    # ---- 查询 ----
    def view(self, case_id):
        entry = self.cases.get(case_id)
        if not entry:
            stored = self.store.get_case(case_id)
            return stored
        snap = entry['state'].public_view()
        snap['id'] = case_id
        snap['phase'] = entry['phase']
        snap['pending_round'] = entry['pending_round']
        snap['stats'] = self.orch.stats_for(case_id)
        return snap
