# -*- coding: utf-8 -*-
"""SDK 入口：train 资产校验 / test 端到端报告 / BasicAgent 委托。"""
import os

from agent.runtime.retriever import KnowledgeBase
from tests.conftest import CHEST_PAIN, ROOT


def test_train_returns_asset_stats():
    from my_doctor_agent import MyDoctorAgent
    agent = MyDoctorAgent.__new__(MyDoctorAgent)   # 只测 train 的资产校验逻辑
    agent.kb = KnowledgeBase(os.path.join(ROOT, 'data', 'skills'))
    result = agent.train()
    assert result['status'] == 'ok'
    assert result['knowledge_base'] == {'departments': 19, 'skills': 584,
                                        'diseases': 584, 'exams': 837}


def test_test_entry_returns_final_report():
    from my_doctor_agent import MyDoctorAgent
    agent = MyDoctorAgent(fake=True)
    result = agent.test(dict(CHEST_PAIN))
    assert result['final'] and result['final']['safety']['approved'] is True
    # 报告统计在交付事件落账前生成，事件总数 >= 报告内统计
    assert result['events'] >= result['final']['stats']['events'] >= 40


def test_basic_agent_delegates(tmp_path, monkeypatch):
    import basic_agent
    import my_doctor_agent
    monkeypatch.setattr(my_doctor_agent, 'DATA_DIR', str(tmp_path / 'demo'))
    agent = basic_agent.BasicAgent(fake=True)
    assert agent.train()['status'] == 'ok'
    out = agent.test(dict(CHEST_PAIN))
    assert out['final']['title'].startswith('医晓')
