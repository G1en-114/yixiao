# -*- coding: utf-8 -*-
"""YiXiao Hospital Agent web clinical console (zero third-party dependencies, Python standard library).

Routes:
    GET  /health                     original competition health check (unchanged)
    POST /test                       original competition single-case entry (unchanged, synchronous)
    GET  /                           sign-in page (server-side session)
    GET  /demo                       web clinical console
    POST /login / POST /logout       sign in / out (HttpOnly + SameSite=Lax session)
    GET  /api/me /api/cases          session and case list
    POST /api/cases                  create a case (starts triage + interview)
    GET  /api/cases/<id>             live case view
    POST /api/cases/<id>/answers     submit interview answers
    POST /api/cases/<id>/exams       submit exam results (the system never invents exam data)
    GET  /api/cases/<id>/events      SSE event stream (Last-Event-ID resume)
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

DEMO_ACCOUNT = {'demo': 'yixiao2026'}    # fixed demo account (no sign-up or password reset)
SESSIONS = {}                            # token -> user
SESSION_LOCK = threading.Lock()

_store = Store(os.path.join(DATA_DIR, 'hospital_demo.db'))
_bus = EventBus(_store, os.path.join(DATA_DIR, 'events'))
_kb = KnowledgeBase(SKILLS_DIR)
_cfg = load_config(ROOT)


def _llm():
    # HOSPITAL_FAKE_LLM=1 is for development self-tests only; the real demo must use a real model
    if os.environ.get('HOSPITAL_FAKE_LLM') == '1':
        from agent.runtime.fake_script import build_script
        from agent.runtime.llm import FakeLLM
        return FakeLLM(build_script())
    return LLMClient(_cfg)


_pipeline = Pipeline(Orchestrator(_bus, _store), _bus, _store, _kb, _llm())


class Handler(BaseHTTPRequestHandler):
    server_version = 'HospitalAgent/1.0'

    # ---- helpers ----
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

    # ---- routes ----
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
                return self._send(401, {'error': 'Not signed in'})
            return self._send(200, {'user': user, 'knowledge': _kb.stats(),
                                    'model': _cfg.get('model', '')})
        if path == '/api/cases':
            if not self._session_user():
                return self._send(401, {'error': 'Not signed in'})
            return self._send(200, {'cases': _store.list_cases()})
        if path.startswith('/api/cases/'):
            case_id = path.split('/')[3]
            if not self._session_user():
                return self._send(401, {'error': 'Not signed in'})
            if path.endswith('/events'):
                return self._sse(case_id)
            view = _pipeline.view(case_id)
            if view is None:
                return self._send(404, {'error': 'Case not found'})
            return self._send(200, view)
        return self._send(404, {'error': 'not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/test':              # original single-case entry (reuses the in-process Store to avoid multiple writers)
            body = self._body()
            try:
                from my_doctor_agent import MyDoctorAgent
                agent = MyDoctorAgent(fake=os.environ.get('HOSPITAL_FAKE_LLM') == '1',
                                      store=_store, bus=_bus)
                return self._send(200, agent.test(body))
            except Exception as exc:     # honest boundary: return the error as-is, never fake success
                return self._send(500, {'error': str(exc)})
        if path == '/login':
            body = self._body()
            user, pwd = body.get('username'), body.get('password')
            if DEMO_ACCOUNT.get(user) != pwd:
                return self._send(401, {'error': 'Incorrect demo username or password'})
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
                return self._send(401, {'error': 'Not signed in'})
            intake = self._body()
            if not intake.get('chief_complaint'):
                return self._send(422, {'error': 'Chief complaint is required'})
            intake.setdefault('symptoms', [])
            case_id = _pipeline.create_case(intake)
            return self._send(200, {'case_id': case_id})
        parts = path.split('/')
        if len(parts) == 5 and parts[1] == 'api' and parts[2] == 'cases':
            if not self._session_user():
                return self._send(401, {'error': 'Not signed in'})
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

    # ---- static files ----
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
    print('YiXiao Hospital Agent · Multi-agent clinical decision platform')
    print(f'Knowledge base: {_kb.stats()}')
    print(f'Clinical console: http://127.0.0.1:{port}/demo  (demo account demo / yixiao2026)')
    print('Competition entries unchanged: GET /health · POST /test')
    httpd.serve_forever()


if __name__ == '__main__':
    main()
