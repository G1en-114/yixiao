# -*- coding: utf-8 -*-
"""事件总线：追加式 JSONL 事件日志 + SQLite 持久化 + SSE 订阅广播。"""
import json
import os
import queue
import sqlite3
import threading
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id TEXT PRIMARY KEY, created_at REAL, intake_json TEXT,
  status TEXT, final_json TEXT
);
CREATE TABLE IF NOT EXISTS events(
  case_id TEXT, seq INTEGER, ts REAL, agent TEXT, type TEXT,
  summary TEXT, payload_json TEXT, PRIMARY KEY(case_id, seq)
);
CREATE TABLE IF NOT EXISTS messages(
  case_id TEXT, seq INTEGER, round INTEGER, role TEXT, content TEXT, created_at REAL,
  PRIMARY KEY(case_id, seq)
);
"""


class Store:
    """每线程独立连接（WAL 模式），避免多线程共享连接。"""

    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _conn(self):
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=15)
            conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn = conn
        return conn

    # ---- cases ----
    def create_case(self, case_id, intake):
        with self._lock:
            self._conn().execute(
                'INSERT INTO cases(id, created_at, intake_json, status) VALUES(?,?,?,?)',
                (case_id, time.time(), json.dumps(intake, ensure_ascii=False), 'running'))
            self._conn().commit()

    def finish_case(self, case_id, status, final):
        with self._lock:
            self._conn().execute(
                'UPDATE cases SET status=?, final_json=? WHERE id=?',
                (status, json.dumps(final, ensure_ascii=False), case_id))
            self._conn().commit()

    def list_cases(self):
        rows = self._conn().execute(
            'SELECT id, created_at, intake_json, status FROM cases ORDER BY created_at DESC').fetchall()
        return [{'id': r[0], 'created_at': r[1],
                 'chief_complaint': (json.loads(r[2]).get('chief_complaint', '') if r[2] else ''),
                 'status': r[3]} for r in rows]

    def get_case(self, case_id):
        row = self._conn().execute(
            'SELECT id, created_at, intake_json, status, final_json FROM cases WHERE id=?', (case_id,)).fetchone()
        if not row:
            return None
        return {'id': row[0], 'created_at': row[1], 'intake': json.loads(row[2] or '{}'),
                'status': row[3], 'final': json.loads(row[4]) if row[4] else None}

    # ---- events ----
    def add_event(self, case_id, seq, agent, etype, summary, payload):
        with self._lock:
            self._conn().execute(
                'INSERT INTO events(case_id, seq, ts, agent, type, summary, payload_json) VALUES(?,?,?,?,?,?,?)',
                (case_id, seq, time.time(), agent, etype, summary, json.dumps(payload, ensure_ascii=False)))
            self._conn().commit()

    def events_for(self, case_id, after_seq=-1):
        rows = self._conn().execute(
            'SELECT seq, ts, agent, type, summary, payload_json FROM events '
            'WHERE case_id=? AND seq>? ORDER BY seq', (case_id, after_seq)).fetchall()
        return [{'seq': r[0], 'ts': r[1], 'agent': r[2], 'type': r[3],
                 'summary': r[4], 'payload': json.loads(r[5] or '{}')} for r in rows]

    # ---- interview messages ----
    def add_message(self, case_id, round_no, role, content):
        with self._lock:
            seq = self._conn().execute(
                'SELECT COALESCE(MAX(seq),0)+1 FROM messages WHERE case_id=?', (case_id,)).fetchone()[0]
            self._conn().execute(
                'INSERT INTO messages(case_id, seq, round, role, content, created_at) VALUES(?,?,?,?,?,?)',
                (case_id, seq, round_no, role, content, time.time()))
            self._conn().commit()


class EventBus:
    """追加式事件日志：内存广播 + SQLite 持久化 + 每病例 JSONL 落盘。"""

    def __init__(self, store, jsonl_dir):
        self.store = store
        self.jsonl_dir = jsonl_dir
        os.makedirs(jsonl_dir, exist_ok=True)
        self._subs = {}                  # case_id -> list[queue.Queue]
        self._seqs = {}                  # case_id -> last seq
        self._lock = threading.Lock()

    def emit(self, case_id, agent, etype, summary, payload=None):
        with self._lock:
            seq = self._seqs.get(case_id, -1) + 1
            self._seqs[case_id] = seq
        event = {'seq': seq, 'ts': time.time(), 'agent': agent, 'type': etype,
                 'summary': summary, 'payload': payload or {}}
        self.store.add_event(case_id, seq, agent, etype, summary, event['payload'])
        with open(os.path.join(self.jsonl_dir, f'{case_id}.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
        for q in list(self._subs.get(case_id, [])):
            q.put(event)
        return event

    def replay(self, case_id, after_seq=-1):
        with self._lock:
            last = self._seqs.get(case_id)
        if last is None:                 # 进程重启后从 SQLite 恢复
            events = self.store.events_for(case_id)
            with self._lock:
                self._seqs[case_id] = events[-1]['seq'] if events else -1
            return [e for e in events if e['seq'] > after_seq]
        return self.store.events_for(case_id, after_seq)

    def subscribe(self, case_id):
        q = queue.Queue()
        with self._lock:
            self._subs.setdefault(case_id, []).append(q)
        return q

    def unsubscribe(self, case_id, q):
        with self._lock:
            subs = self._subs.get(case_id, [])
            if q in subs:
                subs.remove(q)
