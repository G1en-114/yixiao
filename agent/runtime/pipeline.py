# -*- coding: utf-8 -*-
"""Clinical pipeline: an end-to-end state machine from one chief complaint to a replayable clinical report.

Pausable / resumable: the interview waits for patient answers, exams wait for user-entered results, failures retry per stage.
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

    # ---- create and advance ----
    def create_case(self, intake, auto=False):
        case_id = uuid.uuid4().hex[:12]
        state = CaseState(intake)
        entry = {'state': state, 'wait': threading.Event(), 'lock': threading.Lock(),
                 'phase': 'interview', 'pending_round': 0, 'auto': auto}
        with self._lock:
            self.cases[case_id] = entry
        self.store.create_case(case_id, intake)
        self.bus.emit(case_id, 'system', 'case_created',
                      f'Case created: {intake.get("chief_complaint", "")}', {'intake': intake})
        t = threading.Thread(target=self._run_intake, args=(case_id,), daemon=True)
        entry['thread'] = t
        t.start()
        return case_id

    def _auto_respond(self, case_id, kind, payload):
        """SDK / evaluation mode: auto-answer questions and auto-enter exam results (the web demo uses human input)."""
        entry = self.cases.get(case_id)
        if not entry or not entry.get('auto'):
            return
        intake = entry['state'].data

        def _go():
            if kind == 'answers':
                answers = {}
                for q in payload.get('questions', []):
                    custom = (intake.get('interview_answers') or {}).get(q['question'])
                    answers[q['id']] = custom or 'None of the above (auto-answer)'
                self.submit_answers(case_id, answers)
            else:
                results = {}
                for exam in payload.get('exams', []):
                    custom = (intake.get('exam_results') or {}).get(exam)
                    results[exam] = custom or 'Done, no significant abnormality (auto-entered)'
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
        if not questions or (stop and round_no >= MIN_INTERVIEW_ROUNDS):
            self._after_interview(case_id)
            return
        entry['phase'] = 'await_answers'
        entry['pending_round'] = round_no
        state.apply('system', {'stage': f'interview_r{round_no}'})
        self.bus.emit(case_id, 'system', 'await_user',
                      f'Waiting for the patient to answer round {round_no}', {'round': round_no, 'questions': questions})
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
                current['answers'][q['id']] = answers.get(q['id'], '(no answer)')
                self.store.add_message(case_id, current['round'], 'user_answer',
                                       f"{q['question']} → {answers.get(q['id'], '')}")
            entry['phase'] = 'running'
            round_no = current['round']
        self.bus.emit(case_id, 'system', 'answers_received', f'Round {round_no} answers submitted', {'answers': answers})
        threading.Thread(target=self._continue_interview, args=(case_id, round_no), daemon=True).start()
        return True

    def _continue_interview(self, case_id, round_no):
        entry = self.cases[case_id]
        try:
            if round_no >= MAX_INTERVIEW_ROUNDS:     # the last allowed round has been answered
                self._after_interview(case_id)
            else:
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
        self.bus.emit(case_id, 'system', 'await_user', 'Waiting for user-entered exam results (the system never invents exam data)',
                      {'exams': [p['exam'] for p in state.get('exam_plan')]})
        self._auto_respond(case_id, 'exams', {'exams': [p['exam'] for p in state.get('exam_plan')]})

    def submit_exam_results(self, case_id, results):
        entry = self.cases[case_id]
        with entry['lock']:
            if entry['phase'] != 'await_exams':
                return False
            entry['phase'] = 'running'
            entry['state'].apply('system', {'exam_inputs': results})
        self.bus.emit(case_id, 'system', 'exam_results_received', 'Exam results entered', {'results': results})
        threading.Thread(target=self._run_consultation, args=(case_id,), daemon=True).start()
        return True

    def _run_consultation(self, case_id):
        entry = self.cases[case_id]
        state = entry['state']
        try:
            # (5) dual-specialist consult in parallel
            cands = state.get('differential').get('differential_diagnoses', [])
            depts = []
            for c in cands:
                dept = c.get('department')
                if dept and dept in self.kb.departments and dept not in depts:
                    depts.append(dept)
            for dept in state.get('triage').get('candidate_departments', []):
                if dept not in depts:
                    depts.append(dept)
            depts = (depts + ['Cardiology', 'Respiratory Medicine'])[:2]
            state.apply('system', {'stage': 'specialist'})
            threads = []
            results = {}
            for i, dept in enumerate(depts[:2], 1):
                lane = 'AB'[i - 1]
                self.bus.emit(case_id, f'specialist_{lane}', 'agent_start',
                              f'Parallel specialist consult started: lane {lane} · {dept}', {'department': dept, 'lane': lane})

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

            # (6)(7) attending -> safety review (at most 2 rounds on rejection)
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
                # revision: the attending writes the rejection into preconditions and the system records the exclusion
                self._apply_revision(state, safety_result.payload)
                revision_no += 1
                self.bus.emit(case_id, 'system', 'revision',
                              f'Attending revises per the rejection (revision {revision_no})', {'revision_no': revision_no})

            # (8) audit -> final report
            self.orch.run(case_id, 'audit', state, stats=self.orch.stats_for(case_id))
            final = self._build_final(case_id, state, safety_result)
            state.apply('audit', {'final': final})
            state.apply('system', {'stage': 'final'})
            self.store.finish_case(case_id, 'final', final)
            self.bus.emit(case_id, 'system', 'case_final', 'Clinical report delivered (verifiable · replayable)', {'final': final})
        except Exception as exc:
            self._fail(case_id, exc)

    def _apply_revision(self, state, safety_payload):
        """Record the rejection as plan preconditions; a nitrate rejection also records the PDE-5 exclusion step."""
        reasons = safety_payload.get('rejection_reasons', [])
        preconds = list(state.get('safety_preconditions'))
        preconds += reasons
        patch = {'safety_preconditions': preconds}
        if any('PDE-5' in r or 'nitrate' in r.lower() for r in reasons) and not state.get('pde5_exclusion'):
            patch['pde5_exclusion'] = ('PDE-5 exclusion recorded as a precondition: before any nitrate, use of a PDE-5 inhibitor '
                                       '(sildenafil / vardenafil / tadalafil) within the last 24-48 h must be ruled out')
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
            warnings.append('The safety review did not fully pass after two revisions; the advice below is a low-risk conservative fallback. Please confirm with an in-person doctor.')
        if reds or d['triage'].get('urgency') in ('high', 'emergency'):
            warnings.append('Emergency red flags present: go to the emergency department now. Do not delay.')
        return {
            'title': 'YiXiao Structured Clinical Report (teaching demo)',
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
            'disclaimer': 'For teaching demos and clinical decision-support research only. Not a substitute for real diagnosis, prescriptions or emergency care.',
        }

    def _fail(self, case_id, exc):
        state = self.cases[case_id]['state']
        state.apply('system', {'error': str(exc)})
        self.bus.emit(case_id, 'system', 'error', f'Pipeline failed (reported as-is): {exc}', {'error': str(exc)})

    # ---- queries ----
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
