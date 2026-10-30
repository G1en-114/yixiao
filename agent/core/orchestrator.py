# -*- coding: utf-8 -*-
"""Orchestrator: schedules the eight role instances; handles state merges, handoffs and failure retries."""
import threading


class Orchestrator:
    def __init__(self, bus, store):
        self.bus = bus
        self.store = store
        self.roles = {}
        self.stats = {}                  # case_id -> {model_calls, prompt_tokens, completion_tokens}
        self._lock = threading.Lock()

    def register(self, role):
        self.roles[role.name] = role
        role.orchestrator = self
        return role

    def stat(self, case_id, usage):
        if not usage:
            return
        with self._lock:
            s = self.stats.setdefault(case_id, {'model_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0})
            s['model_calls'] += 1
            s['prompt_tokens'] += usage.get('prompt_tokens', 0)
            s['completion_tokens'] += usage.get('completion_tokens', 0)

    def stats_for(self, case_id):
        with self._lock:
            return dict(self.stats.get(case_id, {'model_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}))

    def handoff(self, msg, result, state, evidence=None):
        """Record one structured handoff (append-only, history is never overwritten)."""
        self.bus.emit(msg.case_id, msg.from_agent, 'handoff',
                      f'{msg.from_agent} -> {msg.to_agent}: {msg.task}',
                      {'handoff': {
                          'from_agent': msg.from_agent, 'to_agent': msg.to_agent,
                          'task': msg.task, 'state_summary': result.status,
                          'risk_level': result.risk, 'evidence_used': evidence or result.evidence,
                          'validation': 'passed' if result.status == 'ok' else result.status}})

    def run(self, case_id, role_name, state, **kwargs):
        role = self.roles[role_name]
        self.bus.emit(case_id, role_name, 'agent_start', f'{role_name} started', {})
        try:
            result = role.run(case_id, state, **kwargs)
        except Exception as exc:         # retry once on failure; a second failure is reported as-is
            self.bus.emit(case_id, role_name, 'agent_retry', f'{role_name} failed, retrying once: {exc}', {})
            result = role.run(case_id, state, **kwargs)
        self.bus.emit(case_id, role_name, 'agent_done',
                      f'{role_name} done ({result.status})', {'result': result.to_dict()})
        return result
