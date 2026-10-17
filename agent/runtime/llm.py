# -*- coding: utf-8 -*-
"""OpenAI 兼容 LLM 客户端（零第三方依赖）+ FakeLLM（仅自动化测试）。"""
import json
import os
import re
import urllib.request


DEFAULT_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
DEFAULT_MODEL = 'qwen3.5-flash'


def load_config(root):
    """读取 config.yaml 中的简单 key: value 配置（不引入 PyYAML）。"""
    cfg = {'base_url': DEFAULT_BASE_URL, 'model': DEFAULT_MODEL,
           'api_key_env': 'DASHSCOPE_API_KEY', 'api_key': '', 'temperature': 0.3, 'timeout': 60}
    path = os.path.join(root, 'config.yaml')
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            line = line.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            k, v = line.split(':', 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in cfg and v != '':
                cfg[k] = v
    return cfg


class LLMClient:
    """qwen3.5-flash（阿里云 DashScope OpenAI 兼容接口），可配置替换任意兼容基座。"""

    def __init__(self, cfg):
        self.base_url = str(cfg.get('base_url', DEFAULT_BASE_URL)).rstrip('/')
        self.model = cfg.get('model', DEFAULT_MODEL)
        self.api_key = cfg.get('api_key') or os.environ.get(cfg.get('api_key_env', 'DASHSCOPE_API_KEY'), '')
        self.temperature = float(cfg.get('temperature', 0.3))
        self.timeout = int(cfg.get('timeout', 60))

    def chat(self, system, user):
        if not self.api_key:
            raise RuntimeError('模型未配置：请设置 DASHSCOPE_API_KEY 环境变量或 config.yaml 的 api_key')
        body = json.dumps({
            'model': self.model,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'temperature': self.temperature,
        }).encode('utf-8')
        req = urllib.request.Request(
            f'{self.base_url}/chat/completions', data=body, method='POST',
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = data['choices'][0]['message']['content']
        usage = data.get('usage', {}) or {}
        return text, {'prompt_tokens': usage.get('prompt_tokens', 0),
                      'completion_tokens': usage.get('completion_tokens', 0)}


class FakeLLM:
    """确定性脚本化响应，仅用于自动化测试与 --fake 开发模式；正式演示不自动回退。"""

    def __init__(self, script=None):
        self.script = script or {}
        self.calls = []
        import threading
        self._lock = threading.Lock()

    def chat(self, system, user):
        with self._lock:
            header = system.split('\n', 1)[0]
            for key, responses in self.script.items():
                if key in header or key in user[:30]:
                    idx = sum(1 for c in self.calls if c[0] == key)
                    self.calls.append((key, system[:40], user[:60]))
                    text = responses[idx] if idx < len(responses) else responses[-1]
                    return text, {'prompt_tokens': 100, 'completion_tokens': 50}
            self.calls.append(('default', system[:40], user[:60]))
            return '{}', {'prompt_tokens': 1, 'completion_tokens': 1}


def extract_json(text):
    """从模型输出中提取第一个平衡的 JSON 对象；失败抛 ValueError（由角色层重试）。"""
    if not text:
        raise ValueError('空输出')
    text = re.sub(r'```(json)?', '', text)
    start = text.find('{')
    if start < 0:
        raise ValueError('输出中不含 JSON 对象')
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError('JSON 未闭合')
