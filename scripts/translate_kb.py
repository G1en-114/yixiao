# translate_kb.py — translate the YiXiao knowledge base (19 depts / 584 disease Skills / 837 exams) to English.
# Usage: python translate_kb.py <src skills dir> <out skills dir>
# Batches are cached in cache/ so the run can resume; set DEEPSEEK_API_KEY first. Then run install_kb.py.
import json, os, sys, glob, hashlib, time
from concurrent.futures import ThreadPoolExecutor
from deepseek_client import chat

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True); os.makedirs('cache', exist_ok=True)
MODEL = os.environ.get('TR_MODEL', 'deepseek-flash')

DEPTS = {
    '儿科': 'Pediatrics', '免疫科': 'Immunology & Rheumatology', '内分泌科': 'Endocrinology', '口腔科': 'Stomatology',
    '呼吸内科': 'Respiratory Medicine', '妇产科': 'Obstetrics & Gynecology', '心内科': 'Cardiology', '感染科': 'Infectious Diseases',
    '普外科': 'General Surgery', '泌尿外科': 'Urology', '消化内科': 'Gastroenterology', '皮肤科': 'Dermatology',
    '眼科': 'Ophthalmology', '神经内科': 'Neurology', '耳鼻咽喉科': 'Otolaryngology (ENT)', '肾内科': 'Nephrology',
    '肿瘤科': 'Oncology', '血液科': 'Hematology', '骨科': 'Orthopedics',
}
SYS = ('You are a senior medical translator (Chinese → English) for a clinical-education knowledge base. '
       'Use standard English medical terminology (as in UpToDate / Harrison\'s / BNF / ICD-10 naming), US spelling, '
       'generic drug names (INN), and keep numbers, units and abbreviations exactly. Never add, drop or soften content. '
       'Return only valid JSON in the exact structure requested.')

usage_tot = {'prompt_tokens': 0, 'completion_tokens': 0}
def call(tag, user, check):
    path = f'cache/{tag}.json'
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    last = None
    for attempt in range(4):
        try:
            text, usage = chat(SYS, user, model=MODEL)
            for k in usage_tot: usage_tot[k] += usage.get(k, 0)
            data = json.loads(text)
            check(data)
            json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            return data
        except Exception as e:
            last = e; time.sleep(2 + attempt * 3)
    raise RuntimeError(f'{tag}: {last}')

def chunks(xs, n): return [xs[i:i + n] for i in range(0, len(xs), n)]

# ---------- 1. disease names ----------
diseases = []
for line in open(os.path.join(SRC, 'all_diseases.txt'), encoding='utf-8'):
    if line.strip():
        n, _, d = line.strip().partition('\t'); diseases.append((n, d))
names = sorted({n for n, _ in diseases})
def name_batch(i, b):
    def chk(d):
        m = d['map']; miss = [x for x in b if x not in m or not m[x].strip()]
        if miss: raise ValueError(f'missing {miss[:3]}')
    return call(f'dis_{i}', 'Translate each Chinese disease name into its standard English disease name '
                '(concise, title case not required, no Chinese). Keep parenthetical qualifiers in English parentheses. '
                'Return {"map": {"<chinese>": "<english>", ...}} covering every item.\n' + json.dumps(b, ensure_ascii=False), chk)['map']
with ThreadPoolExecutor(8) as ex:
    dmap = {}
    for m in ex.map(lambda a: name_batch(*a), enumerate(chunks(names, 80))): dmap.update(m)
# disambiguate duplicates
seen = {}
for zh in names:
    en = dmap[zh].strip(); key = en.lower()
    if key in seen: en = f'{en} ({zh})'  # flagged, resolved below
    seen[key] = zh; dmap[zh] = en
dups = [v for v in dmap.values() if '(' in v and any('\u4e00' <= c <= '\u9fff' for c in v)]
print('disease names', len(dmap), 'duplicates', len(dups), dups[:5])

# ---------- 2. exams ----------
exams = json.load(open(os.path.join(SRC, 'examinations.json'), encoding='utf-8'))['examinations']
def exam_batch(i, b):
    def chk(d):
        if len(d['items']) != len(b): raise ValueError('count')
    return call(f'exam_{i}', 'Translate this list of medical examinations. For each item return name (standard English test name, '
                'keep common abbreviations such as ECG, CT, MRI, hs-cTn in the name), category, description. Same order, same count. '
                'Return {"items": [{"name": ..., "category": ..., "description": ...}, ...]}.\n' + json.dumps(b, ensure_ascii=False), chk)['items']
with ThreadPoolExecutor(8) as ex:
    ex_en = [it for part in ex.map(lambda a: exam_batch(*a), enumerate(chunks(exams, 50))) for it in part]
seen = set()
for zh, en in zip(exams, ex_en):
    n = en['name'].strip()
    if n.lower() in seen: n = f"{n} [{en['category']}]"
    seen.add(n.lower()); en['name'] = n
json.dump({'examinations': ex_en}, open(os.path.join(OUT, 'examinations.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({e['name']: x['name'] for e, x in zip(exams, ex_en)}, open('exam_map.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('exams', len(ex_en))

# ---------- 3. skills ----------
def skill_batch(tag, skills):
    def chk(d):
        if len(d['skills']) != len(skills): raise ValueError('count')
        for a, b in zip(d['skills'], skills):
            for k in ('first_questions', 'followup_questions', 'stop_conditions'):
                if len(a['interview_guide'][k]) != len(b['interview_guide'][k]): raise ValueError('shape ' + k)
            for k in ('essential', 'if_suspected', 'avoid'):
                if len(a['exam_strategy'][k]) != len(b['exam_strategy'][k]): raise ValueError('shape ' + k)
    slim = [{k: v for k, v in s.items() if k not in ('disease', 'department')} for s in skills]
    return call(tag, 'Translate every string value of these clinical Skill objects into English. Keep the JSON keys, structure, '
                'list lengths and order exactly the same. Interview questions should read naturally, addressed to the patient. '
                'Return {"skills": [...]} with the same number of objects.\n' + json.dumps(slim, ensure_ascii=False), chk)['skills']
jobs = []
for f in sorted(glob.glob(os.path.join(SRC, 'skills_*.json'))):
    data = json.load(open(f, encoding='utf-8'))
    zh_dept = data['department']
    for i, b in enumerate(chunks(data['skills'], 4)):
        jobs.append((zh_dept, i, b))
def run_job(j):
    zh_dept, i, b = j
    tag = 'sk_' + hashlib.md5(f'{zh_dept}{i}'.encode()).hexdigest()[:10]
    out = skill_batch(tag, b)
    for o, s in zip(out, b):
        o['disease'] = dmap[s['disease']]; o['department'] = DEPTS[zh_dept]
    return zh_dept, i, out
results = {}
with ThreadPoolExecutor(10) as ex:
    for k, (zh_dept, i, out) in enumerate(ex.map(run_job, jobs)):
        results.setdefault(zh_dept, {})[i] = out
        if k % 20 == 0: print('skills batch', k, '/', len(jobs), usage_tot, flush=True)
for zh_dept, parts in results.items():
    en = DEPTS[zh_dept]
    skills = [s for i in sorted(parts) for s in parts[i]]
    fn = 'skills_' + en.split(' ')[0].replace('&', '').lower() + '.json'
    json.dump({'department': en, 'skills': skills}, open(os.path.join(OUT, fn), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'all_diseases.txt'), 'w', encoding='utf-8') as f:
    for n, d in diseases: f.write(f'{dmap[n]}\t{DEPTS.get(d, d)}\n')
json.dump(dmap, open('disease_map.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('done', usage_tot)
