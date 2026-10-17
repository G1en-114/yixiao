# -*- coding: utf-8 -*-
"""FakeLLM 胸痛病例剧本：驱动全流程（含 Safety 硝酸酯/PDE-5 驳回 → 主治修订 → 二轮通过）。

仅用于自动化测试与 --fake 开发模式。
"""

TRIAGE = {
    "urgency": "high",
    "candidate_departments": ["心内科", "呼吸内科", "消化内科", "感染科"],
    "red_flags": [],
    "triage_reasoning": "中老年男性，压榨样胸痛伴呼吸困难、持续不缓解，合并高血压史，优先排查急性冠脉综合征。",
    "next_step": "进入问诊；同时提示患者如症状加重立即线下急诊",
}

INTERVIEW_R1 = {
    "questions": [
        {"id": "r1q1", "question": "胸痛是压榨样、针刺样还是闷胀样？具体位置在哪里？", "why": "判断疼痛性质与部位"},
        {"id": "r1q2", "question": "疼痛有没有向左肩、下颌或后背部放射？", "why": "放射痛高度提示心肌缺血"},
        {"id": "r1q3", "question": "发作时有没有出冷汗、恶心或濒死感？", "why": "伴随症状评估危险度"}],
    "missing_information": ["疼痛诱因", "既往检查"],
    "stop_interview": False,
}
INTERVIEW_R2 = {
    "questions": [
        {"id": "r2q1", "question": "胸痛在活动、劳累后加重吗？休息后能缓解吗？", "why": "劳力型心绞痛特征"},
        {"id": "r2q2", "question": "高血压平时吃什么药、控制得怎么样？", "why": "评估基础病控制情况"}],
    "missing_information": ["危险因素（吸烟/家族史）"],
    "stop_interview": False,
}
INTERVIEW_R3 = {
    "questions": [
        {"id": "r3q1", "question": "有吸烟史或冠心病家族史吗？", "why": "危险因素评估"}],
    "missing_information": [],
    "stop_interview": True,
}

DIFFERENTIAL = {
    "differential_diagnoses": [
        {"disease": "冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）", "department": "心内科",
         "confidence": "high",
         "supporting_evidence": ["压榨样胸痛伴呼吸困难、持续半小时", "高血压病史", "中老年男性"],
         "against_evidence": []},
        {"disease": "急性主动脉综合征", "department": "心内科",
         "confidence": "low",
         "supporting_evidence": ["胸痛伴呼吸困难"],
         "against_evidence": ["无撕裂样疼痛向背部放射的典型描述"]}],
    "knowledge_used": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "next_step": "建议进入检查规划",
}

EXAMINATION = {
    "recommended_exams": [
        {"exam": "心电图（ECG）", "priority": "essential", "reason": "排查 ST-T 改变与心律失常"},
        {"exam": "心肌酶谱", "priority": "essential", "reason": "评估心肌损伤"}],
    "avoid_exams": [],
    "missing_results_warning": "若无法提供检查结果，危险分层将受限",
}

SPECIALIST_A = {
    "department": "心内科", "primary_opinion": "高度怀疑急性冠脉综合征，建议按 ACS 流程处置",
    "likely_diseases": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "key_evidence": ["压榨样胸痛持续不缓解", "高血压病史"],
    "uncertainties": ["心肌酶谱结果待评估"],
    "recommendations": ["抗血小板", "强化他汀", "评估血运重建指征"],
}
SPECIALIST_B = {
    "department": "呼吸内科", "primary_opinion": "同时排查肺源性胸痛，目前证据更支持心源性",
    "likely_diseases": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "key_evidence": ["呼吸困难与胸痛伴发"],
    "uncertainties": ["无血气与影像资料"],
    "recommendations": ["必要时胸部影像评估"],
}

ATTENDING_INITIAL = {
    "consensus": ["两专科均优先考虑心源性胸痛（ACS 可能）"],
    "conflicts": ["是否需要同步排查肺栓塞证据不足"],
    "final_assessment": "冠状动脉粥样硬化性心脏病可能性大，按 ACS 处理",
    "diagnosis_candidates": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "treatment_plan": ["抗血小板：阿司匹林 100mg/d", "硝酸甘油舌下含服缓解胸痛", "强化他汀调脂稳斑"],
    "evidence_level": "sufficient",
}
ATTENDING_REVISED = {
    "consensus": ["两专科均优先考虑心源性胸痛（ACS 可能）"],
    "conflicts": [],
    "final_assessment": "冠状动脉粥样硬化性心脏病可能性大；硝酸酯使用前需排除 PDE-5 抑制剂使用史",
    "diagnosis_candidates": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "treatment_plan": ["抗血小板：阿司匹林 100mg/d",
                       "硝酸酯类：排除 PDE-5 抑制剂使用史后方可使用，未排除前以抗血小板方案为主",
                       "强化他汀调脂稳斑"],
    "evidence_level": "sufficient",
}

SAFETY_PASS = {
    "approved": True, "risk_level": "low", "rejection_reasons": [],
    "required_revision": "",
    "patient_facing_warning": "如胸痛加重或大汗淋漓，立即拨打 120 就近急诊。",
}

AUDIT = {
    "audit_summary": "高危胸痛病例完成八 Agent 全流程：3 轮问诊、双专科并行会诊、一次安全驳回与修订、二轮审查通过。",
    "agent_timeline": ["TriageAgent 完成分诊并识别红旗征象", "InterviewAgent 3 轮信息差追问",
                       "DifferentialAgent 对齐标准名录", "ExaminationAgent 目录内检查规划",
                       "Specialist A/B 并行会诊", "AttendingAgent 汇总并修订",
                       "SafetyAgent 驳回一次后通过", "AuditAgent 生成本复盘"],
    "knowledge_hits": ["冠状动脉粥样硬化性心脏病（冠状动脉疾病，CAD）"],
    "safety_decision": "驳回后修订通过",
    "limitations": ["检查结果由用户录入，系统不伪造", "教学演示，不等同于临床验证"],
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
