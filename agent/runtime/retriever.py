# -*- coding: utf-8 -*-
"""Knowledge assets: 19-department Skill retriever + 837-item exam catalog + standard disease catalog."""
import difflib
import json
import os
import re

_STOP = set('''a an and are as at be been but by for from has have he her his i in is it its me my of on or our she
that the their them they this to was we were what when which who will with you your not no any all can may
patient patients year years old male female history about after before since day days hour hours week weeks
minute minutes ago also more most than then there these those such very'''.split())


def _stem(w):
    for suf in ('ies', 'es', 's', 'ing', 'ed'):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)] + ('y' if suf == 'ies' else '')
    return w


def _tokens(text):
    words = re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', (text or '').lower())
    return {_stem(w) for w in words if len(w) > 2 and w not in _STOP}


# words that say what kind of test it is, not which test it is
_GENERIC = set('''test testing assay examination exam study panel marker level monitoring scan imaging analysis
measurement screening evaluation check profile'''.split())
# clinical shorthand in Skill exam lines -> words used in catalog exam names
_SYNONYMS = {'troponin': 'cardiac enzyme', 'ck-mb': 'cardiac enzyme', 'hs-ctni': 'cardiac enzyme', 'hs-ctnt': 'cardiac enzyme',
             'injury': 'enzyme', 'ecg': 'electrocardiography', 'cxr': 'chest x-ray', 'cbc': 'complete blood count'}


def _expand(tokens):
    out = set(tokens)
    for t in tokens:
        if t in _SYNONYMS:
            out |= _tokens(_SYNONYMS[t])
    return out


def _norm(name):
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


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

        self._disease_lc = {_norm(n): n for n in self.disease_names}
        self._exam_lc = {_norm(n): n for n in self.exams_by_name}
        self._index = []
        for s in self.all_skills:
            grams = _tokens(s['disease']) | _tokens(s['presentation'])
            self._index.append((s, grams))
        self._exam_index = [(n, _tokens(n), _tokens(it.get('description', '')))
                            for n, it in self.exams_by_name.items()]

    def stats(self):
        return {'departments': len(self.departments), 'skills': len(self.all_skills),
                'diseases': len(self.diseases), 'exams': len(self.exams_by_name)}

    # ---- catalog alignment ----
    def is_standard_disease(self, name):
        return name in self.disease_names

    def is_valid_exam(self, name):
        return name in self.exams_by_name

    def canonical_disease(self, name, cutoff=0.82):
        """Map a model-written disease name to the catalog's exact name (case-insensitive, then close match)."""
        key = _norm(name)
        if not key:
            return None
        if key in self._disease_lc:
            return self._disease_lc[key]
        base = re.split(r'\s*[(\[]', key)[0]
        for lc, n in self._disease_lc.items():
            if base and (lc == base or re.split(r'\s*[(\[]', lc)[0] == base):
                return n
        hit = difflib.get_close_matches(key, list(self._disease_lc), n=1, cutoff=cutoff)
        return self._disease_lc[hit[0]] if hit else None

    def canonical_exam(self, name, cutoff=0.86):
        key = _norm(name)
        if not key:
            return None
        if key in self._exam_lc:
            return self._exam_lc[key]
        hit = difflib.get_close_matches(key, list(self._exam_lc), n=1, cutoff=cutoff)
        return self._exam_lc[hit[0]] if hit else None

    def match_exam_line(self, line, top=2):
        """Best catalog exams for one free-text exam line of a Skill (name overlap weighs more than description)."""
        q = _expand(_tokens(line))
        scored = []
        for n, name_t, desc_t in self._exam_index:
            core = name_t - _GENERIC
            hit = len(q & core)
            if not hit:
                continue
            s = 2 * hit / len(core) + 0.25 * len((q - _GENERIC) & desc_t)
            if s >= 0.6:
                scored.append((s, n))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:top]]

    def exam_covers(self, have, want):
        """True when catalog exam `have` is `want` or a more specific form of it (e.g. TTE covers Echocardiography)."""
        if have == want:
            return True
        a = _tokens(have) - _GENERIC
        b = _tokens(want) - _GENERIC
        return bool(b) and b <= a

    def related_exams(self, skills, top_k=40):
        """Catalog exams that match the candidate Skills' exam strategy, essential lines first (offered to the model by exact name)."""
        out = []
        for key in ('essential', 'if_suspected'):
            for s in skills:
                for line in s['exam_strategy'][key]:
                    for n in self.match_exam_line(line):
                        if n not in out:
                            out.append(n)
        return out[:top_k]

    # ---- retrieval ----
    def retrieve(self, query, candidate_departments=None, top_k=5):
        """Top-K candidate disease Skills for a complaint / case state (retrieval-augmented injection)."""
        qg = _tokens(query)
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
        name = self.canonical_disease(disease) or disease
        for s in self.all_skills:
            if s['disease'] == name:
                return s
        return None

    @staticmethod
    def format_skills(skills):
        """Format candidate Skills for the System Prompt knowledge block."""
        blocks = []
        for i, s in enumerate(skills, 1):
            guide = s['interview_guide']
            exam = s['exam_strategy']
            treat = s['treatment']
            blocks.append(
                f"[Skill {i}] {s['disease']} ({s['department']})\n"
                f"Typical presentation: {s['presentation']}\n"
                f"First questions: {'; '.join(guide['first_questions'][:3])}\n"
                f"Follow-up questions: {'; '.join(guide['followup_questions'][:4])}\n"
                f"Stop when: {'; '.join(guide['stop_conditions'][:2])}\n"
                f"Essential exams: {'; '.join(exam['essential'][:4])}\n"
                f"If suspected: {'; '.join(exam['if_suspected'][:3])}\n"
                f"Avoid: {'; '.join(exam['avoid'][:3])}\n"
                f"First-line management: {'; '.join(treat['first_line'][:3])}\n"
                f"Safety warnings: {'; '.join(treat['safety_warnings'][:2])}")
        return '\n'.join(blocks)
