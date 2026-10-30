# Medical Safety Rules knowledge base

Purpose: the rule base for the platform's Safety Agent. It constrains diagnoses, exams and treatment advice in this AI + medical-education demo.

## General principles
- Output supports medical education, clinical-reasoning training and decision-support demos. It never replaces a doctor's diagnosis, prescription or emergency care.
- Final diagnoses must come from the standard disease catalog; never invent disease names.
- Exams must come from the exam catalog; never recommend anything outside it.
- Exams marked avoid in a Skill must not be recommended.
- Never repeat an exam or action that is already done.
- When information is insufficient, label it "insufficient evidence" and give conservative advice.
- When red flags appear, advise the emergency department / in-person care first instead of continuing online Q&A.

## Diagnostic safety
- Each candidate disease needs supporting and opposing evidence.
- Keep at most 1-3 final diagnoses, each with a confidence level.
- Never present a low-confidence candidate as a definite diagnosis.
- With no standard-name match, fall back to "Refer for specialist evaluation".

## Exam safety
- Essential exams first; any additional exam must state its trigger.
- Avoid high-risk, high-cost or invasive exams without an indication.
- Flag risks for pregnancy, children, renal impairment and contrast allergy.
- Missing exams may not block the teaching flow, but the final report must state their impact.

## Treatment safety
- No high-risk drug or procedure may be output without Safety Agent review.
- Reject when the allergy history conflicts with the drug advice.
- Reject when hepatic/renal risk conflicts with the drug advice.
- Flag individual risk for pregnancy, children, older adults and multimorbidity.
- Acute chest pain, stroke, severe breathlessness, shock or altered consciousness: advise the emergency department first.

## Safety Agent output
- `approved`: pass or not.
- `risk_level`: low / medium / high / emergency.
- `rejection_reasons`: list of reasons.
- `required_revision`: the node to return to and the required change.
- `patient_facing_warning`: safety message for the user.
