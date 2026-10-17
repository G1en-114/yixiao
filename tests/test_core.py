# -*- coding: utf-8 -*-
"""核心协议与编排：CaseState 写权限 / 补丁历史 / 消息协议 / 编排重试 / 事件与存储。"""
import pytest

from agent.core.messages import AgentMessage, AgentResult, HandoffEvent
from agent.core.state import CaseState


def test_casestate_permission_enforced():
    st = CaseState({'chief_complaint': '胸痛'})
    with pytest.raises(PermissionError):
        st.apply('triage', {'differential': {}})          # 分诊无权写鉴别
    st.apply('triage', {'triage': {'urgency': 'high'}})   # 有权字段正常合并
    assert st.get('triage')['urgency'] == 'high'


def test_casestate_patch_history_append_only():
    st = CaseState({'chief_complaint': '胸痛'})
    st.apply('triage', {'triage': {'urgency': 'high'}})
    st.apply('interview', {'interview_rounds': [{'round': 1}]})
    assert len(st.patches) == 2
    assert st.get('interview_rounds')[0]['round'] == 1


def test_message_protocol_schema():
    m = AgentMessage('triage', 'interview', 'c1', '分诊完成').to_dict()
    r = AgentResult('triage', 'ok', {'a': 1}, 'high', ['e']).to_dict()
    h = HandoffEvent('triage', 'interview', '任务', 'ok', 'high', ['skill'], 'passed').to_dict()
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
                raise RuntimeError('首次失败')
            from agent.core.messages import AgentResult
            return AgentResult('flaky', 'ok', {})

    orch = Orchestrator(bus, store)
    orch.register(Flaky())
    result = orch.run('case_x', 'flaky', None)
    assert result.status == 'ok'
    summaries = [e['summary'] for e in store.events_for('case_x')]
    assert any('重试' in s for s in summaries)


def test_event_bus_replay_and_subscribe(store, bus):
    bus.emit('c1', 'triage', 'agent_start', '开始', {})
    bus.emit('c1', 'triage', 'agent_done', '完成', {})
    assert [e['seq'] for e in bus.replay('c1')] == [0, 1]
    got = []
    q = bus.subscribe('c1')
    bus.emit('c1', 'interview', 'agent_start', '第2个', {})
    got.append(q.get(timeout=2))
    bus.unsubscribe('c1', q)
    assert got[0]['summary'] == '第2个'


def test_store_case_lifecycle(store, bus, kb):
    import json
    store.create_case('c9', {'chief_complaint': '胸痛'})
    store.finish_case('c9', 'final', {'diagnosis': 'CAD'})
    case = store.get_case('c9')
    assert case['status'] == 'final'
    assert json.loads(json.dumps(case['final']))['diagnosis'] == 'CAD'
    assert len(store.list_cases()) == 1
