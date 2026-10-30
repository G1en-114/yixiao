# -*- coding: utf-8 -*-
"""SDK entries: train asset check / test end-to-end report / BasicAgent delegation."""
import os

from agent.runtime.retriever import KnowledgeBase
from tests.conftest import CHEST_PAIN, ROOT


def test_train_returns_asset_stats():
    from my_doctor_agent import MyDoctorAgent
    agent = MyDoctorAgent.__new__(MyDoctorAgent)   # only test the asset check in train
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
    # report stats are produced before the delivery event, so total events >= report stats
    assert result['events'] >= result['final']['stats']['events'] >= 40


def test_basic_agent_delegates(tmp_path, monkeypatch):
    import basic_agent
    import my_doctor_agent
    monkeypatch.setattr(my_doctor_agent, 'DATA_DIR', str(tmp_path / 'demo'))
    agent = basic_agent.BasicAgent(fake=True)
    assert agent.train()['status'] == 'ok'
    out = agent.test(dict(CHEST_PAIN))
    assert out['final']['title'].startswith('YiXiao')
