# -*- coding: utf-8 -*-
"""FakeLLM chest-pain script: drives the full flow (including the Safety nitrate / PDE-5 rejection -> attending revision -> round-2 pass).

For automated tests and --fake development mode only.
"""

CAD = 'Coronary atherosclerotic heart disease (coronary artery disease, CAD)'

TRIAGE = {
    "urgency": "high",
    "candidate_departments": ["Cardiology", "Respiratory Medicine", "Gastroenterology", "Infectious Diseases"],
    "red_flags": [],
    "triage_reasoning": "Middle-aged man with crushing chest pain and breathlessness that is not settling, plus hypertension: "
                        "acute coronary syndrome must be ruled out first.",
    "next_step": "Proceed to the interview; tell the patient to go to the emergency department if symptoms worsen",
}

INTERVIEW_R1 = {
    "questions": [
        {"id": "r1q1", "question": "Is the chest pain crushing, stabbing or a dull pressure? Where exactly is it?", "why": "Character and site of the pain"},
        {"id": "r1q2", "question": "Does the pain spread to your left shoulder, jaw or back?", "why": "Radiation strongly suggests myocardial ischemia"},
        {"id": "r1q3", "question": "Have you had cold sweats, nausea or a sense of impending doom?", "why": "Associated symptoms grade the risk"}],
    "missing_information": ["trigger", "previous tests"],
    "stop_interview": False,
}
INTERVIEW_R2 = {
    "questions": [
        {"id": "r2q1", "question": "Does the pain get worse with exertion and ease with rest?", "why": "Features of exertional angina"},
        {"id": "r2q2", "question": "Which blood-pressure medicine do you take, and how well controlled is it?", "why": "Control of the underlying disease"}],
    "missing_information": ["risk factors (smoking / family history)"],
    "stop_interview": False,
}
INTERVIEW_R3 = {
    "questions": [
        {"id": "r3q1", "question": "Do you smoke, or does heart disease run in your family?", "why": "Risk-factor assessment"}],
    "missing_information": [],
    "stop_interview": True,
}

DIFFERENTIAL = {
    "differential_diagnoses": [
        {"disease": CAD, "department": "Cardiology", "confidence": "high",
         "supporting_evidence": ["Crushing chest pain with breathlessness for 30 minutes", "History of hypertension", "Middle-aged man"],
         "against_evidence": []},
        {"disease": "Acute aortic syndrome", "department": "Cardiology", "confidence": "low",
         "supporting_evidence": ["Chest pain with breathlessness"],
         "against_evidence": ["No typical tearing pain radiating to the back"]}],
    "knowledge_used": [CAD],
    "next_step": "Proceed to exam planning",
}

EXAMINATION = {
    "recommended_exams": [
        {"exam": "Electrocardiography (ECG)", "priority": "essential", "reason": "Look for ST-T changes and arrhythmia"},
        {"exam": "Cardiac enzyme panel", "priority": "essential", "reason": "Assess myocardial injury"}],
    "avoid_exams": [],
    "missing_results_warning": "Without exam results, risk stratification is limited",
}

SPECIALIST_A = {
    "department": "Cardiology", "primary_opinion": "High suspicion of acute coronary syndrome; manage on the ACS pathway",
    "likely_diseases": [CAD],
    "key_evidence": ["Crushing chest pain that does not settle", "History of hypertension"],
    "uncertainties": ["Cardiac enzyme results pending"],
    "recommendations": ["Antiplatelet therapy", "High-intensity statin", "Assess for revascularisation"],
}
SPECIALIST_B = {
    "department": "Respiratory Medicine", "primary_opinion": "Pulmonary causes considered; current evidence favours a cardiac cause",
    "likely_diseases": [CAD],
    "key_evidence": ["Breathlessness together with chest pain"],
    "uncertainties": ["No blood gas or imaging yet"],
    "recommendations": ["Chest imaging if needed"],
}

ATTENDING_INITIAL = {
    "consensus": ["Both specialists favour cardiac chest pain (possible ACS)"],
    "conflicts": ["Evidence is insufficient on whether pulmonary embolism must be excluded in parallel"],
    "final_assessment": "Coronary artery disease is most likely; manage as ACS",
    "diagnosis_candidates": [CAD],
    "treatment_plan": ["Antiplatelet: aspirin 100 mg daily", "Sublingual nitroglycerin to relieve chest pain",
                       "High-intensity statin for plaque stabilisation"],
    "evidence_level": "sufficient",
}
ATTENDING_REVISED = {
    "consensus": ["Both specialists favour cardiac chest pain (possible ACS)"],
    "conflicts": [],
    "final_assessment": "Coronary artery disease is most likely; rule out PDE-5 inhibitor use before any nitrate",
    "diagnosis_candidates": [CAD],
    "treatment_plan": ["Antiplatelet: aspirin 100 mg daily",
                       "Nitrates only after PDE-5 inhibitor use is ruled out; until then rely on the antiplatelet regimen",
                       "High-intensity statin for plaque stabilisation"],
    "evidence_level": "sufficient",
}

SAFETY_PASS = {
    "approved": True, "risk_level": "low", "rejection_reasons": [],
    "required_revision": "",
    "patient_facing_warning": "If the chest pain gets worse or you are drenched in sweat, call emergency services now.",
}

AUDIT = {
    "audit_summary": "High-risk chest-pain case completed the full 8-agent flow: 3 interview rounds, a parallel dual-specialist "
                     "consult, one safety rejection and revision, and a round-2 approval.",
    "agent_timeline": ["TriageAgent triaged and flagged red flags", "InterviewAgent asked 3 gap-driven rounds",
                       "DifferentialAgent aligned to the standard catalog", "ExaminationAgent planned in-catalog exams",
                       "Specialists A/B consulted in parallel", "AttendingAgent summarised and revised",
                       "SafetyAgent rejected once, then approved", "AuditAgent produced this review"],
    "knowledge_hits": [CAD],
    "safety_decision": "approved after revision",
    "limitations": ["Exam results are entered by the user, never invented", "Teaching demo, not clinical validation"],
}


def build_script():
    return {
        'TriageAgent': [json_str(TRIAGE)],
        'InterviewAgent': [json_str(INTERVIEW_R1), json_str(INTERVIEW_R2), json_str(INTERVIEW_R3)],
        'DifferentialAgent': [json_str(DIFFERENTIAL)],
        'ExaminationAgent': [json_str(EXAMINATION)],
        'SpecialistAgent': [json_str(SPECIALIST_A), json_str(SPECIALIST_B)],
        'AttendingAgent': [json_str(ATTENDING_INITIAL), json_str(ATTENDING_REVISED)],
        'SafetyAgent': [json_str(SAFETY_PASS), json_str(SAFETY_PASS)],
        'AuditAgent': [json_str(AUDIT)],
    }


def json_str(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)
