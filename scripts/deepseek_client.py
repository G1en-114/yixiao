"""Minimal DeepSeek (OpenAI-compatible) chat client used by translate_kb.py. Reads DEEPSEEK_API_KEY from the environment."""
import json, os, re, urllib.request
KEY = os.environ.get('DEEPSEEK_API_KEY', ''); BASE = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
def models():
    r = urllib.request.Request(BASE + '/models', headers={'Authorization': 'Bearer ' + KEY})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())
def chat(system, user, model='deepseek-chat', temperature=0.2, json_mode=True, timeout=300):
    body = {'model': model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], 'temperature': temperature}
    if json_mode: body['response_format'] = {'type': 'json_object'}
    r = urllib.request.Request(BASE + '/chat/completions', data=json.dumps(body).encode(), method='POST',
                               headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY})
    d = json.loads(urllib.request.urlopen(r, timeout=timeout).read())
    return d['choices'][0]['message']['content'], d.get('usage', {})
if __name__ == '__main__':
    print([m['id'] for m in models()['data']])
