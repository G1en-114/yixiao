# -*- coding: utf-8 -*-
"""Build runtime data (data/skills/) from the original Chinese knowledge_base CSV/JSON in the materials pack.

The shipped English data/skills/ was produced from that build by scripts/translate_kb.py.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(ROOT), 'work', 'AIC_platform_pack', 'knowledge_base')
OUT = os.path.join(ROOT, 'data', 'skills')

SPLITTERS = '\uff1b;\n'   # full-width and ASCII semicolons


def split_list(text):
    if not text:
        return []
    parts = [p.strip() for p in text.replace('\r', '').split('\uff1b')]
    out = []
    for p in parts:
        for q in p.split(';'):
            q = q.strip().strip('\n')
            if q:
                out.append(q)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    by_dept = {}
    with open(os.path.join(SRC, 'hospital_agent_skills_flat.csv'), encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            skill = {
                'disease': row['disease'].strip(),
                'department': row['department'].strip(),
                'presentation': row['presentation'].strip(),
                'interview_guide': {
                    'first_questions': split_list(row['first_questions']),
                    'followup_questions': split_list(row['followup_questions']),
                    'stop_conditions': split_list(row['stop_conditions']),
                },
                'exam_strategy': {
                    'essential': split_list(row['essential_exams']),
                    'if_suspected': split_list(row['if_suspected_exams']),
                    'avoid': split_list(row['avoid_exams']),
                },
                'treatment': {
                    'first_line': split_list(row['first_line_treatment']),
                    'safety_warnings': split_list(row['safety_warnings']),
                    'personalization': split_list(row['personalization']),
                },
            }
            by_dept.setdefault(skill['department'], []).append(skill)

    total = 0
    for dept, skills in sorted(by_dept.items()):
        path = os.path.join(OUT, f'skills_{dept}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'department': dept, 'skills': skills}, f, ensure_ascii=False, indent=1)
        total += len(skills)
        print(f'{dept}: {len(skills)} skills')

    with open(os.path.join(SRC, 'departments.json'), encoding='utf-8') as f:
        departments = json.load(f)['departments']

    catalog = json.load(open(os.path.join(SRC, 'diseases_catalog.json'), encoding='utf-8'))['diseases']
    with open(os.path.join(OUT, 'all_diseases.txt'), 'w', encoding='utf-8') as f:
        for dept in departments:
            for name in catalog.get(dept, []):
                f.write(f'{name}\t{dept}\n')

    exams_raw = json.load(open(os.path.join(SRC, 'examinations_catalog.json'), encoding='utf-8'))['examinations']
    exams = []
    for category, items in exams_raw.items():
        for it in items:
            exams.append({'name': it['name'], 'category': category, 'description': it.get('description', '')})
    with open(os.path.join(OUT, 'examinations.json'), 'w', encoding='utf-8') as f:
        json.dump({'examinations': exams}, f, ensure_ascii=False, indent=1)

    print(f'departments={len(by_dept)} skills={total} diseases={sum(len(v) for v in catalog.values())} exams={len(exams)}')


if __name__ == '__main__':
    main()
