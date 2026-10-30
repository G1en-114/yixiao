# -*- coding: utf-8 -*-
"""Core protocol and orchestration: CaseState write permissions / patch history / message protocol / retry / events and storage."""
import pytest

from agent.core.messages import AgentMessage, AgentResult, HandoffEvent
from agent.core.state import CaseState


def test_casestate_permission_enforced():
    st = CaseState({'chief_complaint': 'chest pain'})
    with pytest.raises(PermissionError):
        st.apply('triage', {'differential': {}})          # triage may not write the differential
    st.apply('triage', {'triage': {'urgency': 'high'}})   # permitted fields merge normally
    assert st.get('triage')['urgency'] == 'high'


def test_casestate_patch_history_append_only():
    st = CaseState({'chief_complaint': 'chest pain'})
    st.apply('triage', {'triage': {'urgency': 'high'}})
    st.apply('interview', {'interview_rounds': [{'round': 1}]})
    assert len(st.patches) == 2
    assert st.get('interview_rounds')[0]['round'] == 1


def test_message_protocol_schema():
    m = AgentMessage('triage', 'interview', 'c1', 'triage complete').to_dict()
    r = AgentResult('triage', 'ok', {'a': 1}, 'high', ['e']).to_dict()
    h = HandoffEvent('triage', 'interview', 'task', 'ok', 'high', ['skill'], 'passed').to_dict()
    assert m['from'] == 'triage' and m['to'] == 'interview'
    assert r['status'] == 'ok' and r['risk'] == 'high'
    assert h['validation'] == 'passed' and h['evidence_used'] == ['skill']


def test_orchestrator_retry_on_failure(store, bus):
    from agent.core.orchestrator import Orchestrator

    class Flaky:
        name = 'flaky'
        calls = 0

        def run(self, case_id, state):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise RuntimeError('first attempt fails')
            from agent.core.messages import AgentResult
            return AgentResult('flaky', 'ok', {})

    orch = Orchestrator(bus, store)
    orch.register(Flaky())
    result = orch.run('case_x', 'flaky', None)
    assert result.status == 'ok'
    summaries = [e['summary'] for e in store.events_for('case_x')]
    assert any('retrying' in s for s in summaries)


def test_event_bus_replay_and_subscribe(store, bus):
    bus.emit('c1', 'triage', 'agent_start', 'start', {})
    bus.emit('c1', 'triage', 'agent_done', 'done', {})
    assert [e['seq'] for e in bus.replay('c1')] == [0, 1]
    got = []
    q = bus.subscribe('c1')
    bus.emit('c1', 'interview', 'agent_start', 'second', {})
    got.append(q.get(timeout=2))
    bus.unsubscribe('c1', q)
    assert got[0]['summary'] == 'second'


def test_store_case_lifecycle(store, bus, kb):
    import json
    store.create_case('c9', {'chief_complaint': 'chest pain'})
    store.finish_case('c9', 'final', {'diagnosis': 'CAD'})
    case = store.get_case('c9')
    assert case['status'] == 'final'
    assert json.loads(json.dumps(case['final']))['diagnosis'] == 'CAD'
    assert len(store.list_cases()) == 1
