# -*- coding: utf-8 -*-
"""Role base class: role System Prompt + retrieval injection + structured JSON output validation (auto-retry on non-compliance)."""
import json
import os

from agent.runtime.llm import extract_json

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts')


class RoleAgent:
    name = 'base'
    prompt_file = ''
    required_keys = ()

    def __init__(self, llm, kb):
        self.llm = llm
        self.kb = kb
        self.orchestrator = None
        path = os.path.join(PROMPT_DIR, self.prompt_file)
        self.prompt = open(path, encoding='utf-8').read() if os.path.exists(path) else ''

    def _usage(self):
        cid = getattr(self, '_case_id', None)
        if cid and self.orchestrator:
            return None  # usage is reported directly by call_llm
        return None

    def call_llm(self, case_id, system, user):
        text, usage = self.llm.chat(system, user)
        if self.orchestrator:
            self.orchestrator.stat(case_id, usage)
        return text

    def ask_json(self, case_id, knowledge, user, risk='low'):
        """Role prompt + retrieval injection + structured JSON output; one automatic retry when non-compliant."""
        system = self.prompt
        if knowledge:
            system += '\n\n## Knowledge-base retrieval (the only source of truth)\n' + knowledge
        system += ('\n\n## Hard output constraints\nOutput exactly one JSON object, written in English, with no '
                   f'explanation and no markdown code fences. It must contain the fields: {", ".join(self.required_keys)}.')
        text = self.call_llm(case_id, system, user)
        try:
            data = extract_json(text)
            missing = [k for k in self.required_keys if k not in data]
            if missing:
                raise ValueError(f'missing fields {missing}')
        except (ValueError, json.JSONDecodeError) as exc:
            self._emit(case_id, 'validate_retry', f'{self.name} output non-compliant, retrying: {exc}')
            text = self.call_llm(
                case_id, system,
                user + f'\n\nNote: the previous output was non-compliant ({exc}). Output only a JSON object with the required fields.')
            data = extract_json(text)
            missing = [k for k in self.required_keys if k not in data]
            if missing:
                raise ValueError(f'{self.name} still missing fields after retry: {missing}')
        return data

    def _emit(self, case_id, etype, summary):
        if self.orchestrator:
            self.orchestrator.bus.emit(case_id, self.name, etype, summary, {})

    def handoff(self, case_id, to_agent, task, result, evidence=None):
        if self.orchestrator:
            from agent.core.messages import AgentMessage
            msg = AgentMessage(self.name, to_agent, case_id, task)
            self.orchestrator.handoff(msg, result, None, evidence)
