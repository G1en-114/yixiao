# -*- coding: utf-8 -*-
"""OpenAI-compatible LLM client (zero third-party dependencies) + FakeLLM (automated tests only)."""
import json
import os
import re
import urllib.request


DEFAULT_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
DEFAULT_MODEL = 'qwen3.5-flash'


def load_config(root):
    """Read simple key: value pairs from config.yaml (no PyYAML); HOSPITAL_<KEY> environment variables override them."""
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
    for k in cfg:                        # environment overrides, e.g. HOSPITAL_MODEL / HOSPITAL_BASE_URL
        v = os.environ.get('HOSPITAL_' + k.upper())
        if v:
            cfg[k] = v
    return cfg


class LLMClient:
    """qwen3.5-flash (Alibaba Cloud DashScope, OpenAI-compatible); any compatible base model can be configured."""

    def __init__(self, cfg):
        self.base_url = str(cfg.get('base_url', DEFAULT_BASE_URL)).rstrip('/')
        self.model = cfg.get('model', DEFAULT_MODEL)
        self.api_key = cfg.get('api_key') or os.environ.get(cfg.get('api_key_env', 'DASHSCOPE_API_KEY'), '')
        self.temperature = float(cfg.get('temperature', 0.3))
        self.timeout = int(cfg.get('timeout', 60))

    def chat(self, system, user):
        if not self.api_key:
            raise RuntimeError('Model not configured: set the DASHSCOPE_API_KEY environment variable or api_key in config.yaml')
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
    """Deterministic scripted responses for automated tests and --fake dev mode only; the real demo never falls back to it."""

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
    """Extract the first balanced JSON object from model output; raise ValueError on failure (the role layer retries)."""
    if not text:
        raise ValueError('empty output')
    text = re.sub(r'```(json)?', '', text)
    start = text.find('{')
    if start < 0:
        raise ValueError('no JSON object in output')
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError('unterminated JSON')
