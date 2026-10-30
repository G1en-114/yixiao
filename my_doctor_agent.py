# -*- coding: utf-8 -*-
"""MyDoctorAgent: the single competition SDK entry (train / test); the Orchestrator schedules eight independent clinical agents inside.

Usage:
    python my_doctor_agent.py train                     # load and validate the knowledge base (584 Skills / 837 exams)
    python my_doctor_agent.py test --complaint "Chest pain with shortness of breath for 30 minutes" --age 56 --sex male
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from agent.core.events import EventBus, Store          # noqa: E402
from agent.core.orchestrator import Orchestrator       # noqa: E402
from agent.runtime.llm import FakeLLM, LLMClient, load_config  # noqa: E402
from agent.runtime.pipeline import Pipeline            # noqa: E402
from agent.runtime.retriever import KnowledgeBase      # noqa: E402

DATA_DIR = os.path.join(ROOT, 'data', 'demo')
SKILLS_DIR = os.path.join(ROOT, 'data', 'skills')


class MyDoctorAgent:
    """Structure: BasicAgent / MyDoctorAgent -> Orchestrator -> 8 role instances -> SDK submission."""

    def __init__(self, fake=False, data_dir=None, store=None, bus=None):
        cfg = load_config(ROOT)
        if fake:
            from agent.runtime.fake_script import build_script
            self.llm = FakeLLM(build_script())
        else:
            self.llm = LLMClient(cfg)
        self.kb = KnowledgeBase(SKILLS_DIR)
        data_dir = data_dir or DATA_DIR
        os.makedirs(data_dir, exist_ok=True)
        self.store = store or Store(os.path.join(data_dir, 'hospital_demo.db'))
        self.bus = bus or EventBus(self.store, os.path.join(data_dir, 'events'))
        self.orch = Orchestrator(self.bus, self.store)
        self.pipeline = Pipeline(self.orch, self.bus, self.store, self.kb, self.llm)

    def train(self, skills_dir=None):
        """Assemble and validate the knowledge base (build the retrieval index + check counts); return asset stats."""
        stats = self.kb.stats()
        assert stats['skills'] == 584, f'expected 584 disease Skills, got {stats["skills"]}'
        assert stats['exams'] == 837, f'expected 837 exams, got {stats["exams"]}'
        assert stats['departments'] == 19, f'expected 19 departments, got {stats["departments"]}'
        return {'status': 'ok', 'knowledge_base': stats,
                'message': 'Knowledge base ready: 19 departments / 584 disease Skills / 837 exams'}

    def test(self, case_input):
        """Single case end to end: chief complaint -> structured clinical report (synchronous; auto-answers questions and exam entry)."""
        case_id = self.pipeline.create_case(case_input, auto=True)
        import time
        for _ in range(600):             # wait up to 5 minutes (a real model takes about 1-2 minutes)
            view = self.pipeline.view(case_id)
            if isinstance(view, dict) and (view.get('stage') == 'final' or view.get('error')):
                break
            time.sleep(0.5)
        final = (self.store.get_case(case_id) or {}).get('final')
        events = self.store.events_for(case_id)
        result = {'case_id': case_id, 'events': len(events),
                  'stats': self.orch.stats_for(case_id), 'final': final}
        if final is None:                # bring the error back as-is, never fake success
            view = self.pipeline.view(case_id)
            result['error'] = (view or {}).get('error') or 'The pipeline did not finish within the time limit'
        return result


def _parse_args():
    p = argparse.ArgumentParser(description='YiXiao Hospital Agent SDK entry')
    p.add_argument('mode', choices=['train', 'test'])
    p.add_argument('--complaint', default='Chest pain with shortness of breath for 30 minutes')
    p.add_argument('--age', type=int, default=56)
    p.add_argument('--sex', default='male')
    p.add_argument('--duration', default='30 minutes')
    p.add_argument('--symptoms', default='chest pain,shortness of breath')
    p.add_argument('--history', default='hypertension')
    p.add_argument('--allergies', default='')
    p.add_argument('--medications', default='')
    p.add_argument('--fake', action='store_true', help='use FakeLLM (automated tests / development only)')
    return p.parse_args()


def main():
    args = _parse_args()
    agent = MyDoctorAgent(fake=args.fake)
    if args.mode == 'train':
        print(json.dumps(agent.train(), ensure_ascii=False, indent=2))
        return
    result = agent.test({'chief_complaint': args.complaint, 'age': args.age, 'sex': args.sex,
                         'duration': args.duration, 'symptoms': [s for s in args.symptoms.split(',') if s],
                         'past_history': args.history, 'allergies': args.allergies,
                         'medications': args.medications,
                         'interview_answers': {}, 'exam_results': {}})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
