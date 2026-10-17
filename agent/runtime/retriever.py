# -*- coding: utf-8 -*-
"""知识资产：19 科室 Skill 检索器 + 837 项检查目录 + 标准疾病名录。"""
import json
import os
import re


def _bigrams(text):
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]+', '', text or '')
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


class KnowledgeBase:
    def __init__(self, skills_dir):
        self.skills_dir = skills_dir
        self.departments = {}
        self.all_skills = []
        self.diseases = []               # [(name, dept)]
        self.disease_names = set()
        self.exams_by_name = {}
        self.exam_categories = {}
        self._load()

    def _load(self):
        for fn in sorted(os.listdir(self.skills_dir)):
            path = os.path.join(self.skills_dir, fn)
            if fn.startswith('skills_') and fn.endswith('.json'):
                data = json.load(open(path, encoding='utf-8'))
                dept = data['department']
                self.departments[dept] = data['skills']
                for s in data['skills']:
                    s['department'] = dept
                    self.all_skills.append(s)
            elif fn == 'all_diseases.txt':
                for line in open(path, encoding='utf-8'):
                    line = line.strip()
                    if line:
                        name, _, dept = line.partition('\t')
                        self.diseases.append((name, dept or ''))
                        self.disease_names.add(name)
            elif fn == 'examinations.json':
                data = json.load(open(path, encoding='utf-8'))
                for it in data['examinations']:
                    self.exams_by_name[it['name']] = it
                    self.exam_categories.setdefault(it['category'], []).append(it['name'])

        self._index = []
        for s in self.all_skills:
            grams = _bigrams(s['disease']) | _bigrams(s['presentation'][:120])
            self._index.append((s, grams))

    def stats(self):
        return {'departments': len(self.departments), 'skills': len(self.all_skills),
                'diseases': len(self.diseases), 'exams': len(self.exams_by_name)}

    def is_standard_disease(self, name):
        return name in self.disease_names

    def is_valid_exam(self, name):
        return name in self.exams_by_name

    def retrieve(self, query, candidate_departments=None, top_k=5):
        """按主诉/病例状态检索 Top-K 候选疾病 Skill（检索增强注入）。"""
        qg = _bigrams(query)
        scored = []
        for s, grams in self._index:
            score = len(qg & grams) / (len(qg) or 1)
            if candidate_departments and s['department'] in candidate_departments:
                score += 0.08
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def find_skill(self, disease):
        for s in self.all_skills:
            if s['disease'] == disease:
                return s
        return None

    @staticmethod
    def format_skills(skills):
        """把候选 Skill 格式化注入 System Prompt 知识区块。"""
        blocks = []
        for i, s in enumerate(skills, 1):
            guide = s['interview_guide']
            exam = s['exam_strategy']
            treat = s['treatment']
            blocks.append(
                f"[Skill {i}] {s['disease']}（{s['department']}）\n"
                f"典型表现：{s['presentation']}\n"
                f"首问：{'；'.join(guide['first_questions'][:3])}\n"
                f"追问：{'；'.join(guide['followup_questions'][:4])}\n"
                f"停止条件：{'；'.join(guide['stop_conditions'][:2])}\n"
                f"必要检查：{'；'.join(exam['essential'][:4])}\n"
                f"鉴别检查：{'；'.join(exam['if_suspected'][:3])}\n"
                f"避免检查：{'；'.join(exam['avoid'][:3])}\n"
                f"一线方案：{'；'.join(treat['first_line'][:3])}\n"
                f"安全警示：{'；'.join(treat['safety_warnings'][:2])}")
        return '\n'.join(blocks)
