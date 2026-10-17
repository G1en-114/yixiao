# -*- coding: utf-8 -*-
"""Web 服务：/health 比赛入口 / 登录会话 / 首页可达 / /test 单病例入口。"""
import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.request

import pytest


@pytest.fixture(scope='module')
def server():
    import web_server
    httpd = web_server.make_server(0)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    time.sleep(0.3)
    yield f'http://127.0.0.1:{port}'
    httpd.shutdown()


def test_health_entry_unchanged(server):
    with urllib.request.urlopen(server + '/health') as r:
        assert json.loads(r.read()) == {'status': 'ok'}


def test_login_and_session(server):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    bad = json.dumps({'username': 'demo', 'password': 'x'}).encode()
    try:
        opener.open(urllib.request.Request(server + '/login', data=bad,
                                           headers={'Content-Type': 'application/json'}))
        assert False, '错误密码不应登录成功'
    except urllib.error.HTTPError as e:
        assert e.code == 401
    good = json.dumps({'username': 'demo', 'password': 'yixiao2026'}).encode()
    resp = opener.open(urllib.request.Request(server + '/login', data=good,
                                              headers={'Content-Type': 'application/json'}))
    assert resp.status == 200
    with opener.open(server + '/api/me') as r:
        me = json.loads(r.read())
    assert me['user'] == 'demo'
    assert me['knowledge']['skills'] == 584


def test_index_page_served(server):
    with urllib.request.urlopen(server + '/') as r:
        body = r.read().decode('utf-8')
    assert '多智能体临床决策平台' in body


def test_test_entry_sync_run(server, monkeypatch):
    monkeypatch.setenv('HOSPITAL_FAKE_LLM', '1')   # 测试环境：不真实调用大模型
    body = json.dumps({'chief_complaint': '胸口疼并伴有呼吸困难，持续半小时', 'age': 56,
                       'sex': '男', 'duration': '半小时', 'symptoms': ['胸痛', '呼吸困难'],
                       'past_history': '高血压'}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(server + '/test', data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        result = json.loads(r.read())
    assert result['final'] and result['final']['safety']['approved'] is True
