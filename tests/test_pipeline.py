# -*- coding: utf-8 -*-
"""端到端管线：胸痛病例全流程 / 问诊轮数上限 / 双专科并行 / 名录对齐 / Safety 两轮 / 事件持久化。"""
import time

from tests.conftest import CHEST_PAIN, run_case


def test_full_flow_final_stage(pipeline):
    cid, view = run_case(pipeline)
    assert view['final']['title'].startswith('医晓')


def test_interview_max_three_rounds(pipeline):
    cid, view = run_case(pipeline)
    assert 1 <= view['final']['interview_rounds'] <= 3


def test_dual_specialist_parallel(pipeline):
    cid, view = run_case(pipeline)
    lanes = view['final']['consultation']
    assert set(lanes.keys()) == {'A', 'B'}
    assert lanes['A']['department'] != lanes['B']['department']


def test_diagnosis_aligned_to_catalog(pipeline, kb):
    cid, view = run_case(pipeline)
    for name in view['final']['attending']['diagnosis_candidates']:
        assert kb.is_standard_disease(name), f'诊断名不在标准名录: {name}'


def test_safety_two_rounds_nitrate_rejection(pipeline):
    """标志性演示：硝酸酯方案因 PDE-5 前置条件未明被驳回，修订后第二轮通过。"""
    cid, view = run_case(pipeline)
    f = view['final']
    reviews = f['safety']['reviews']
    assert len(reviews) == 2 and f['safety']['approved'] is True
    assert not reviews[0]['approved']
    assert any('PDE-5' in r for r in reviews[0]['rejection_reasons'])
    assert any('排除' in p for p in f['safety']['preconditions'])


def test_events_persisted_in_sqlite(pipeline, store):
    cid, view = run_case(pipeline)
    events = store.events_for(cid)
    # 报告统计生成于"报告交付"事件之前，总账最多多 1 条
    assert len(events) - view['final']['stats']['events'] <= 1
    assert view['final']['stats']['events'] >= 40
    types = {e['type'] for e in events}
    assert {'case_created', 'handoff', 'agent_done', 'case_final'} <= types
