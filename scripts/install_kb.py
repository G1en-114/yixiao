# install_kb.py <translated dir> — normalise the translated knowledge base and install it into the app copy (replacing the Chinese data).
import json, os, re, glob, shutil
import sys
SRC = sys.argv[1]                       # output dir of translate_kb.py
DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'skills')
SMALL = {'of', 'and', 'for', 'with', 'in', 'on', 'the', 'to', 'a', 'an', 'by', 'or', 'via', 'at', 'from', 'vs'}

def title(name):
    out = []
    for i, w in enumerate(name.split(' ')):
        core = w.lstrip('([')
        lead = w[:len(w) - len(core)]
        if not core:
            out.append(w); continue
        if any(c.isupper() for c in core[1:]) or any(c.isdigit() for c in core):
            out.append(w)                                  # acronyms / mixed case: ECG, hs-cTn, HbA1c, 24-hour
        elif i > 0 and core.lower() in SMALL:
            out.append(lead + core.lower())
        else:
            out.append(lead + (core[0].upper() if core[0].isascii() else core[0]) + core[1:])
    return ' '.join(out)

ex = json.load(open(os.path.join(SRC, 'examinations.json'), encoding='utf-8'))
OVERRIDE = {'Báez Sign': 'Femoral Head Compression Test'}   # unverifiable eponym -> descriptive name
for it in ex['examinations']:
    it['name'] = OVERRIDE.get(it['name'].strip(), it['name'])
seen = {}
for it in ex['examinations']:
    it['name'] = title(it['name'].strip())
    it['category'] = title(it['category'].strip())
    k = it['name'].lower()
    if k in seen:
        it['name'] = f"{it['name']} ({it['category']})"
    seen[it['name'].lower()] = 1
assert len({i['name'] for i in ex['examinations']}) == 837, 'duplicate exam names'

for f in glob.glob(os.path.join(DST, '*')):
    os.remove(f)
json.dump(ex, open(os.path.join(DST, 'examinations.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for f in glob.glob(os.path.join(SRC, 'skills_*.json')) + [os.path.join(SRC, 'all_diseases.txt')]:
    shutil.copy(f, DST)

# sanity: no Chinese left anywhere in the installed data
bad = 0
for f in glob.glob(os.path.join(DST, '*')):
    t = open(f, encoding='utf-8').read()
    n = len(re.findall(r'[\u4e00-\u9fff]', t))
    if n: print('CJK chars left in', os.path.basename(f), n); bad += n
print('installed', len(os.listdir(DST)), 'files; CJK left:', bad)
