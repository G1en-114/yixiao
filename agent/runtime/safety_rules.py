# -*- coding: utf-8 -*-
"""Deterministic safety rules (rule engine), double-checked together with the SafetyAgent LLM review.

Rule source: the safety-rules knowledge base (allergy / contraindication / emergency red flags /
over-testing / interaction preconditions). These checks do not depend on the model, so the demo is
reproducible: the rejection always fires when the condition is met.
"""
import re

RED_FLAGS = ['chest pain with sweating', 'shortness of breath', 'altered consciousness', 'shock', 'stroke',
             'severe allergic reaction']

# drug-class keywords -> precondition that must be ruled out
DRUG_PRECONDITIONS = [
    {   # nitrates x PDE-5 inhibitors: the signature rejection of the original demo
        'trigger_any': ['nitroglycerin', 'glyceryl trinitrate', 'nitrate', 'isosorbide'],
        'condition_field': 'pde5_exclusion',
        'reason': 'The plan includes a nitrate, but use of a PDE-5 inhibitor (sildenafil / vardenafil / tadalafil) '
                  'has not been ruled out. The combination can cause severe hypotension and is contraindicated.',
        'revision': 'Add a PDE-5 inhibitor exclusion to the plan: explicitly ask whether sildenafil, vardenafil or '
                    'tadalafil was taken recently (especially within 24-48 h). Until ruled out, nitrates may only be '
                    'listed as a conditional option with the precondition stated.',
        'satisfied_if_contains': 'pde-5 exclusion recorded',
    },
]

ALLERGY_RULES = [
    {'allergy_any': ['penicillin'],
     'drug_any': ['penicillin', 'amoxicillin', 'ampicillin', 'piperacillin', 'benzathine'],
     'reason': 'The allergy history records a penicillin allergy, and the plan contains a penicillin-class drug.'},
    {'allergy_any': ['cephalosporin', 'cef', 'ceph'],
     'drug_any': ['cephalosporin', 'cef', 'ceph'],
     'reason': 'The allergy history records a cephalosporin allergy, and the plan contains a cephalosporin.'},
    {'allergy_any': ['sulfa', 'sulfonamide'],
     'drug_any': ['sulfa', 'sulfonamide', 'co-trimoxazole', 'trimethoprim-sulfamethoxazole', 'sulfamethoxazole'],
     'reason': 'The allergy history records a sulfonamide allergy, and the plan contains a sulfonamide.'},
]


def _has(text, words):
    t = (text or '').lower()
    return any(re.search(r'\b' + re.escape(w), t) for w in words)


# a clause like "withhold nitrates" or "nitrates are contraindicated" is not an order for a nitrate
_NEGATION = re.compile(r"\b(withh[eo]ld|hold off|do not|don't|avoid|contraindicat\w*|stop|discontinu\w*|no nitrates?|"
                       r"not (?:be )?(?:give|given|administer\w*|use|used|start\w*|prescrib\w*))\b")


def _orders(text, words):
    """True when some clause mentions one of `words` without negating it."""
    for clause in re.split(r'[.;\n]+', (text or '').lower()):
        if _has(clause, words) and not _NEGATION.search(clause):
            return True
    return False


def check_treatment(allergies, medications_history, treatment_text, pde5_exclusion):
    """Returns [(rule_id, reason, revision_required)]; an empty list means pass."""
    violations = []
    treatment_text = treatment_text or ''
    history_text = f'{medications_history or ""} {pde5_exclusion or ""}'.lower()

    for rule in ALLERGY_RULES:
        if _has(allergies, rule['allergy_any']) and _orders(treatment_text, rule['drug_any']):
            violations.append(('allergy_conflict', rule['reason'],
                               'Replace it with an alternative that does not conflict with the allergy history, and state why.'))

    for i, rule in enumerate(DRUG_PRECONDITIONS):
        if _orders(treatment_text, rule['trigger_any']):
            if rule['satisfied_if_contains'] not in history_text:
                violations.append((f'precondition_{i}', rule['reason'], rule['revision']))

    return violations


def check_exams(exam_plan, kb, avoid_lists=None):
    """Exam-plan compliance: in catalog, not on an avoid list, not duplicated. Returns a list of violations."""
    violations = []
    seen = set()
    avoid_all = set()
    for av in (avoid_lists or []):
        avoid_all.update(av)
    for exam in exam_plan:
        name = exam if isinstance(exam, str) else exam.get('exam', '')
        if not kb.is_valid_exam(name):
            violations.append(('exam_not_in_catalog', f'Exam "{name}" is not in the 837-item standard exam catalog',
                               'Exams outside the catalog may not be submitted'))
        if name in avoid_all:
            violations.append(('avoid_exam', f'Exam "{name}" is on a Skill\'s avoid list', 'Avoid-list exams may not be recommended'))
        if name in seen:
            violations.append(('duplicate_exam', f'Exam "{name}" was submitted twice', 'Completed actions may not be repeated'))
        seen.add(name)
    return violations


def check_red_flag_advice(triage, final_report_text):
    """Red flags must come with in-person emergency advice."""
    reds = triage.get('red_flags') or []
    urgency = triage.get('urgency', '')
    if reds or urgency in ('high', 'emergency'):
        if 'emergency' not in (final_report_text or '').lower():
            return [('red_flag_er_missing', 'The case has red flags / high urgency, but the conclusion does not advise the emergency department',
                     'The conclusion must advise going to the emergency department immediately')]
    return []
