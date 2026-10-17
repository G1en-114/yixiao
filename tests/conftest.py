# -*- coding: utf-8 -*-
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.core.events import EventBus, Store           # noqa: E402
from agent.core.orchestrator import Orchestrator        # noqa: E402
from agent.runtime.fake_script import build_script      # noqa: E402
from agent.runtime.llm import FakeLLM                   # noqa: E402
from agent.runtime.pipeline import Pipeline             # noqa: E402
from agent.runtime.retriever import KnowledgeBase       # noqa: E402

SKILLS_DIR = os.path.join(ROOT, 'data', 'skills')
CHEST_PAIN = {
    'chief_complaint': '胸口疼并伴有呼吸困难，持续半小时',
    'age': 56, 'sex': '男', 'duration': '半小时',
    'symptoms': ['胸痛', '呼吸困难'], 'past_history': '高血压',
    'allergies': '', 'medications': '',
}


@pytest.fixture(scope='session')
def kb():
    return KnowledgeBase(SKILLS_DIR)


@pytest.fixture()
def store(tmp_path):
    return Store(str(tmp_path / 'hospital_demo.db'))


@pytest.fixture()
def bus(store, tmp_path):
    return EventBus(store, str(tmp_path / 'events'))


@pytest.fixture()
def pipeline(store, bus, kb):
    orch = Orchestrator(bus, store)
    return Pipeline(orch, bus, store, kb, FakeLLM(build_script()))


def run_case(pipeline, intake=None, timeout=30):
    """跑一个自动应答病例直到 final（或 error），返回 (case_id, final_view)。"""
    cid = pipeline.create_case(dict(intake or CHEST_PAIN), auto=True)
    deadline = time.time() + timeout
    view = {}
    while time.time() < deadline:
        view = pipeline.view(cid)
        if view.get('stage') == 'final' or view.get('error'):
            break
        time.sleep(0.2)
    assert not view.get('error'), f'管线报错: {view.get("error")}'
    assert view.get('stage') == 'final', f'管线未完成: {view.get("stage")}'
    return cid, view
