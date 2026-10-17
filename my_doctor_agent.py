# -*- coding: utf-8 -*-
"""MyDoctorAgent：比赛 SDK 单一入口（train / test），内部由 Orchestrator 调度八个独立临床 Agent。

用法：
    python my_doctor_agent.py train                     # 加载并校验知识库（584 Skill / 837 检查）
    python my_doctor_agent.py test --complaint "胸口疼并伴有呼吸困难，持续半小时" --age 56 --sex 男
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
    """结构：BasicAgent / MyDoctorAgent → Orchestrator → 8 角色实例 → SDK submission。"""

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
        """知识库装配与校验（检索索引构建 + 口径核对），返回资产统计。"""
        stats = self.kb.stats()
        assert stats['skills'] == 584, f'疾病 Skill 应为 584 条，实际 {stats["skills"]}'
        assert stats['exams'] == 837, f'检查目录应为 837 项，实际 {stats["exams"]}'
        assert stats['departments'] == 19, f'科室应为 19 个，实际 {stats["departments"]}'
        return {'status': 'ok', 'knowledge_base': stats,
                'message': '知识库装配完成：19 科室 / 584 疾病 Skill / 837 检查目录'}

    def test(self, case_input):
        """单病例端到端：主诉输入 → 结构化诊疗报告（同步执行，自动应答追问与检查录入）。"""
        case_id = self.pipeline.create_case(case_input, auto=True)
        import time
        for _ in range(600):             # 最多等 5 分钟（真实模型约 1-2 分钟）
            view = self.pipeline.view(case_id)
            if isinstance(view, dict) and (view.get('stage') == 'final' or view.get('error')):
                break
            time.sleep(0.5)
        final = (self.store.get_case(case_id) or {}).get('final')
        events = self.store.events_for(case_id)
        result = {'case_id': case_id, 'events': len(events),
                  'stats': self.orch.stats_for(case_id), 'final': final}
        if final is None:                # 如实带回错误，不伪造成功
            view = self.pipeline.view(case_id)
            result['error'] = (view or {}).get('error') or '流程未在时限内完成'
        return result


def _parse_args():
    p = argparse.ArgumentParser(description='医晓 Hospital Agent SDK 入口')
    p.add_argument('mode', choices=['train', 'test'])
    p.add_argument('--complaint', default='胸口疼并伴有呼吸困难，持续半小时')
    p.add_argument('--age', type=int, default=56)
    p.add_argument('--sex', default='男')
    p.add_argument('--duration', default='半小时')
    p.add_argument('--symptoms', default='胸痛,呼吸困难')
    p.add_argument('--history', default='高血压')
    p.add_argument('--allergies', default='')
    p.add_argument('--medications', default='')
    p.add_argument('--fake', action='store_true', help='使用 FakeLLM（仅自动化测试/开发）')
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
