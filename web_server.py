# -*- coding: utf-8 -*-
"""医晓 Hospital Agent Web 临床指挥台（零第三方依赖，Python 标准库实现）。

路由：
    GET  /health                     原比赛健康检查入口（保持不变）
    POST /test                       原比赛单病例入口（保持不变，同步执行）
    GET  /                           登录页（服务端会话）
    GET  /demo                       Web 临床指挥台
    POST /login / POST /logout       登录/登出（HttpOnly + SameSite=Lax 会话）
    GET  /api/me /api/cases          会话与病例列表
    POST /api/cases                  创建病例（触发分诊+问诊）
    GET  /api/cases/<id>             病例实时视图
    POST /api/cases/<id>/answers     提交问诊回答
    POST /api/cases/<id>/exams       提交检查结果（系统不伪造检查数据）
    GET  /api/cases/<id>/events      SSE 事件流（Last-Event-ID 断线恢复）
"""
import json
import os
import secrets
import sys
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from agent.core.events import EventBus, Store            # noqa: E402
from agent.core.orchestrator import Orchestrator         # noqa: E402
from agent.runtime.llm import LLMClient, load_config     # noqa: E402
from agent.runtime.pipeline import Pipeline              # noqa: E402
from agent.runtime.retriever import KnowledgeBase        # noqa: E402

STATIC_DIR = os.path.join(ROOT, 'web', 'static')
DATA_DIR = os.path.join(ROOT, 'data', 'demo')
SKILLS_DIR = os.path.join(ROOT, 'data', 'skills')

DEMO_ACCOUNT = {'demo': 'yixiao2026'}    # 固定演示账号（不支持注册与找回密码）
SESSIONS = {}                            # token -> user
SESSION_LOCK = threading.Lock()

_store = Store(os.path.join(DATA_DIR, 'hospital_demo.db'))
_bus = EventBus(_store, os.path.join(DATA_DIR, 'events'))
_kb = KnowledgeBase(SKILLS_DIR)
_cfg = load_config(ROOT)


def _llm():
    # 环境变量 HOSPITAL_FAKE_LLM=1 仅用于开发自测；正式演示必须使用真实模型
    if os.environ.get('HOSPITAL_FAKE_LLM') == '1':
        from agent.runtime.fake_script import build_script
        from agent.runtime.llm import FakeLLM
        return FakeLLM(build_script())
    return LLMClient(_cfg)


_pipeline = Pipeline(Orchestrator(_bus, _store), _bus, _store, _kb, _llm())


class Handler(BaseHTTPRequestHandler):
    server_version = 'HospitalAgent/1.0'

    # ---- 基础工具 ----
    def log_message(self, fmt, *args):
        sys.stderr.write('[http] %s\n' % (fmt % args))

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except json.JSONDecodeError:
            return {}

    def _session_user(self):
        raw = self.headers.get('Cookie') or ''
        try:
            c = cookies.SimpleCookie(raw)
            token = c['session'].value
        except (KeyError, cookies.CookieError):
            return None
        with SESSION_LOCK:
            return SESSIONS.get(token)

    # ---- 路由 ----
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            return self._send(200, {'status': 'ok'})
        if path.startswith('/static/'):
            return self._static(path)
        if path == '/':
            return self._page('index.html')
        if path == '/demo':
            if not self._session_user():
                return self._redirect('/')
            return self._page('index.html')
        if path == '/api/me':
            user = self._session_user()
            if not user:
                return self._send(401, {'error': '未登录'})
            return self._send(200, {'user': user, 'knowledge': _kb.stats(),
                                    'model': _cfg.get('model', '')})
        if path == '/api/cases':
            if not self._session_user():
                return self._send(401, {'error': '未登录'})
            return self._send(200, {'cases': _store.list_cases()})
        if path.startswith('/api/cases/'):
            case_id = path.split('/')[3]
            if not self._session_user():
                return self._send(401, {'error': '未登录'})
            if path.endswith('/events'):
                return self._sse(case_id)
            view = _pipeline.view(case_id)
            if view is None:
                return self._send(404, {'error': '病例不存在'})
            return self._send(200, view)
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/test':              # 原比赛单病例入口
            body = self._body()
            try:
                from my_doctor_agent import MyDoctorAgent
                agent = MyDoctorAgent(fake=os.environ.get('HOSPITAL_FAKE_LLM') == '1')
                return self._send(200, agent.test(body))
            except Exception as exc:     # 诚实边界：如实返回错误，不伪造成功
                return self._send(500, {'error': str(exc)})
        if path == '/login':
            body = self._body()
            user, pwd = body.get('username'), body.get('password')
            if DEMO_ACCOUNT.get(user) != pwd:
                return self._send(401, {'error': '演示账号或密码不正确'})
            token = secrets.token_urlsafe(24)
            with SESSION_LOCK:
                SESSIONS[token] = user
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Set-Cookie',
                             f'session={token}; Path=/; HttpOnly; SameSite=Lax')
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')
            return
        if path == '/logout':
            raw = self.headers.get('Cookie') or ''
            try:
                token = cookies.SimpleCookie(raw)['session'].value
                with SESSION_LOCK:
                    SESSIONS.pop(token, None)
            except (KeyError, cookies.CookieError):
                pass
            return self._send(200, {'ok': True})
        if path == '/api/cases':
            if not self._session_user():
                return self._send(401, {'error': '未登录'})
            intake = self._body()
            if not intake.get('chief_complaint'):
                return self._send(422, {'error': '主诉不能为空'})
            intake.setdefault('symptoms', [])
            case_id = _pipeline.create_case(intake)
            return self._send(200, {'case_id': case_id})
        parts = path.split('/')
        if len(parts) == 5 and parts[1] == 'api' and parts[2] == 'cases':
            if not self._session_user():
                return self._send(401, {'error': '未登录'})
            case_id, action = parts[3], parts[4]
            body = self._body()
            if action == 'answers':
                ok = _pipeline.submit_answers(case_id, body.get('answers', {}))
                return self._send(200 if ok else 409, {'ok': ok})
            if action == 'exams':
                ok = _pipeline.submit_exam_results(case_id, body.get('results', {}))
                return self._send(200 if ok else 409, {'ok': ok})
        return self._send(404, {'error': 'not found'})

    # ---- SSE ----
    def _sse(self, case_id):
        last_id = int(self.headers.get('Last-Event-ID') or
                      urlparse(self.path).query.split('last=')[-1] or -1)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        try:
            backlog = _bus.replay(case_id, last_id)
            for ev in backlog:
                self._sse_event(ev)
            q = _bus.subscribe(case_id)
            try:
                while True:
                    try:
                        ev = q.get(timeout=15)
                        self._sse_event(ev)
                    except Exception:
                        self.wfile.write(b': ping\n\n')
                        self.wfile.flush()
            finally:
                _bus.unsubscribe(case_id, q)
        except (ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def _sse_event(self, ev):
        data = json.dumps(ev, ensure_ascii=False)
        self.wfile.write(f'id: {ev["seq"]}\nevent: agent\ndata: {data}\n\n'.encode('utf-8'))
        self.wfile.flush()

    # ---- 静态资源 ----
    def _page(self, name):
        path = os.path.join(STATIC_DIR, name)
        if not os.path.exists(path):
            return self._send(404, {'error': 'missing page'})
        body = open(path, 'rb').read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        rel = path[len('/static/'):]
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.exists(full):
            return self._send(404, {'error': 'not found'})
        ctype = {'.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
                 '.png': 'image/png', '.mp4': 'video/mp4'}.get(os.path.splitext(full)[1], 'application/octet-stream')
        body = open(full, 'rb').read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, to):
        self.send_response(302)
        self.send_header('Location', to)
        self.send_header('Content-Length', '0')
        self.end_headers()


def make_server(port=7860):
    return ThreadingHTTPServer(('0.0.0.0', port), Handler)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7860
    httpd = make_server(port)
    print(f'医晓 Hospital Agent · 多智能体临床决策平台')
    print(f'知识库：{_kb.stats()}')
    print(f'Web 临床指挥台：http://127.0.0.1:{port}/demo （演示账号 demo / yixiao2026）')
    print(f'比赛入口保持不变：GET /health · POST /test')
    httpd.serve_forever()


if __name__ == '__main__':
    main()
