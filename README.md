# YiXiao Hospital Agent · Multi-Agent Clinical Decision Platform

A runnable implementation of the submission for the AI + Super Agent track · University group (8th AI Agent Development Application Competition).
Eight independent clinical agents (triage / consultation / differential diagnosis / examination / dual-specialty consultation / attending / safety / audit) are orchestrated by
Orchestrator, collaborating around the central case state (CaseState): **input a chief complaint,
end-to-end deliver a structured, traceable, reviewable diagnosis and treatment report.**

> This project is a runnable version rebuilt according to the supporting materials: zero third-party dependencies (pure Python standard library),
> knowledge assets continue to use the competition material package (19 departments / 584 disease skills / 837 examination catalog / safety rule base).

## Quick Start

```bash
# 1. Configure the model (qwen3.5-flash, Alibaba Cloud DashScope OpenAI-compatible endpoint; any compatible base model can be substituted)
#    Windows:  set DASHSCOPE_API_KEY=sk-xxxx     Linux/Mac: export DASHSCOPE_API_KEY=sk-xxxx

# 2. Start the service (zero dependencies, no pip install needed)
python web_server.py            # or double-click StartDemo.bat on Windows

# 3. Open the clinical command center
#    http://127.0.0.1:7860/demo     demo account demo / yixiao2026
```

Demo route: login (dynamic background) → freely enter a chief complaint (e.g. "Chest pain with shortness of breath for 30 minutes")
→ three rounds of information-gap follow-up → enter examination results (the system does not fabricate data) → parallel dual-specialty consultation →
**Safety Gate rejection (nitrate × PDE-5 precondition) → attending revision → second-pass approval** → audit replay timeline → diagnosis and treatment report.

## Competition Entry (unchanged)

```bash
curl http://127.0.0.1:7860/health            # {"status": "ok"}
curl -X POST http://127.0.0.1:7860/test -H "Content-Type: application/json" \
     -d '{"chief_complaint":"Chest pain with shortness of breath for 30 minutes","age":56,"sex":"Male"}'

python my_doctor_agent.py train              # Knowledge base assembly validation (584/837/19)
python my_doctor_agent.py test --complaint "Chest pain with shortness of breath for 30 minutes" --age 56
python basic_agent.py      test              # Original competition base entry, interface unchanged
```

`MyDoctorAgent / BasicAgent` exposes a single SDK entry, internally scheduled by Orchestrator across eight role instances—
consistent with the structure described in the supporting materials (`docs_architecture.md` contains the complete architecture diagram).

## Directory Structure

```
agent/core/      CaseState (write-permission isolation), AgentMessage/AgentResult/HandoffEvent,
                 Store (SQLite WAL, per-thread independent connections), EventBus (JSONL events + SSE broadcast), Orchestrator
agent/roles/     eight role agents; SpecialistAgent dynamically loaded by department; prompts/ eight role prompt sets
agent/runtime/   LLM client (OpenAI-compatible, urllib implementation), knowledge retriever (RAG Top-K injection),
                 deterministic safety rule engine, clinical pipeline (pausable/resumable state machine), FakeLLM script (testing only)
web/static/      clinical command center (dark command-center style, native JS + SSE, no framework)
data/skills/     19 department Skill JSON + all_diseases.txt (584) + examinations.json (837)
tests/           30 automated tests (FakeLLM, no real large model calls)
```

## Engineering Mechanisms (corresponding to the supporting material descriptions)

- **Write-permission isolation**: each agent returns only structured patches; Orchestrator merges the central state according to role permissions;
- **Append-only handoff**: AgentMessage / AgentResult / HandoffEvent; each handoff records source, target,
  task, risk, Skill evidence and validation results, fully written to SQLite + JSONL, with SSE step-by-step replay;
- **Dual safety validation**: deterministic rule engine (allergy conflicts, nitrate × PDE-5 precondition, avoid/off-catalog/duplicate examinations,
  red-flag signs must recommend emergency) + SafetyAgent large-model review; rejection blocks immediately, the attending may revise at most 2 times,
  after two failed rounds a conservative fallback is applied and truthfully annotated;
- **Honesty boundary**: examination results are entered by the user; FakeLLM is only used for automated testing (`--fake` / `HOSPITAL_FAKE_LLM=1`),
  formal demos do not automatically fall back to fake results; when the model is not configured or a request fails, the UI truthfully displays the error.

## Testing and Deployment

```bash
python -m pytest tests -q      # 30 passed; requires pytest (the only development dependency)
docker build -t yixiao . && docker run -p 7860:7860 -e DASHSCOPE_API_KEY=sk-xxx yixiao
```

## Disclaimer

System output is used only for teaching demonstrations and clinical decision-support research, and does not replace real medical diagnosis, prescription, or emergency care;
demonstration cases are de-identified sandbox data, and no real patient information is collected or stored.
