# -*- coding: utf-8 -*-
"""End-to-end pipeline: chest-pain full flow / interview round cap / parallel specialists / catalog alignment / two safety rounds / event persistence."""
import time

from tests.conftest import CHEST_PAIN, run_case


def test_full_flow_final_stage(pipeline):
    cid, view = run_case(pipeline)
    assert view['final']['title'].startswith('YiXiao')


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
        assert kb.is_standard_disease(name), f'diagnosis not in the standard catalog: {name}'


def test_safety_two_rounds_nitrate_rejection(pipeline):
    """Signature demo: a nitrate plan is rejected for an unresolved PDE-5 precondition, then passes in round 2 after revision."""
    cid, view = run_case(pipeline)
    f = view['final']
    reviews = f['safety']['reviews']
    assert len(reviews) == 2 and f['safety']['approved'] is True
    assert not reviews[0]['approved']
    assert any('PDE-5' in r for r in reviews[0]['rejection_reasons'])
    assert any('PDE-5' in p for p in f['safety']['preconditions'])


def test_events_persisted_in_sqlite(pipeline, store):
    cid, view = run_case(pipeline)
    events = store.events_for(cid)
    # report stats are produced before the "report delivered" event, so the ledger has at most 1 more
    assert len(events) - view['final']['stats']['events'] <= 1
    assert view['final']['stats']['events'] >= 40
    types = {e['type'] for e in events}
    assert {'case_created', 'handoff', 'agent_done', 'case_final'} <= types
