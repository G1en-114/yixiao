# -*- coding: utf-8 -*-
"""角色基类：角色化 System Prompt + 检索注入 + 结构化 JSON 输出校验（不合规自动重试）。"""
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
            return None  # usage 由 call_llm 直接上报
        return None

    def call_llm(self, case_id, system, user):
        text, usage = self.llm.chat(system, user)
        if self.orchestrator:
            self.orchestrator.stat(case_id, usage)
        return text

    def ask_json(self, case_id, knowledge, user, risk='low'):
        """角色提示词 + 检索注入 + 结构化 JSON 输出；不合规自动重试一次。"""
        system = self.prompt
        if knowledge:
            system += '\n\n## 知识库检索结果（唯一取数口径）\n' + knowledge
        system += ('\n\n## 输出硬约束\n只输出一个 JSON 对象，不要输出任何解释文字、'
                   f'不要使用 markdown 代码围栏；必须包含字段：{", ".join(self.required_keys)}。')
        text = self.call_llm(case_id, system, user)
        try:
            data = extract_json(text)
            missing = [k for k in self.required_keys if k not in data]
            if missing:
                raise ValueError(f'缺少字段 {missing}')
        except (ValueError, json.JSONDecodeError) as exc:
            self._emit(case_id, 'validate_retry', f'{self.name} 输出不合规，自动重试: {exc}')
            text = self.call_llm(
                case_id, system,
                user + f'\n\n注意：上一次输出不合规（{exc}）。请严格只输出符合字段要求的 JSON 对象。')
            data = extract_json(text)
            missing = [k for k in self.required_keys if k not in data]
            if missing:
                raise ValueError(f'{self.name} 重试后仍缺少字段 {missing}')
        return data

    def _emit(self, case_id, etype, summary):
        if self.orchestrator:
            self.orchestrator.bus.emit(case_id, self.name, etype, summary, {})

    def handoff(self, case_id, to_agent, task, result, evidence=None):
        if self.orchestrator:
            from agent.core.messages import AgentMessage
            msg = AgentMessage(self.name, to_agent, case_id, task)
            self.orchestrator.handoff(msg, result, None, evidence)
