# 医晓 Hospital Agent · 多智能体临床决策平台

AI+超级智能体赛道 · 高校组（第八届 AI 智能体开发应用赛）参赛作品的可运行实现。
八个独立临床智能体（分诊 / 问诊 / 鉴别 / 检查 / 双专科会诊 / 主治 / 安全 / 审计）由
Orchestrator 统一编排，围绕中心病例状态（CaseState）协作：**输入一条主诉，
端到端交付一份结构化、可追溯、可复盘的诊疗报告。**

> 本工程为按佐证材料口径重建的可运行版本：零第三方依赖（纯 Python 标准库），
> 知识资产沿用参赛材料包（19 科室 / 584 条疾病 Skill / 837 项检查目录 / 安全规则库）。

## 快速开始

```bash
# 1. 配置模型（qwen3.5-flash，阿里云 DashScope OpenAI 兼容接口，可替换任意兼容基座）
#    Windows:  set DASHSCOPE_API_KEY=sk-xxxx     Linux/Mac: export DASHSCOPE_API_KEY=sk-xxxx

# 2. 起服务（零依赖，无需 pip install）
python web_server.py            # 或 Windows 直接双击 启动演示.bat

# 3. 打开临床指挥台
#    http://127.0.0.1:7860/demo     演示账号 demo / yixiao2026
```

演示路线：登录（动态背景）→ 自由输入主诉（如"胸口疼并伴有呼吸困难，持续半小时"）
→ 三轮信息差追问 → 录入检查结果（系统不伪造数据）→ 双专科并行会诊 →
**Safety Gate 驳回（硝酸酯 × PDE-5 前置条件）→ 主治修订 → 二轮通过** → 审计回放时间线 → 诊疗报告。

## 比赛入口（保持不变）

```bash
curl http://127.0.0.1:7860/health            # {"status": "ok"}
curl -X POST http://127.0.0.1:7860/test -H "Content-Type: application/json" \
     -d '{"chief_complaint":"胸口疼并伴有呼吸困难，持续半小时","age":56,"sex":"男"}'

python my_doctor_agent.py train              # 知识库装配校验（584/837/19）
python my_doctor_agent.py test --complaint "胸口疼并伴有呼吸困难，持续半小时" --age 56
python basic_agent.py      test              # 原比赛基础入口，接口不变
```

`MyDoctorAgent / BasicAgent` 暴露单一 SDK 入口，内部由 Orchestrator 调度八个角色实例——
与佐证材料描述的结构一致（`docs_architecture.md` 含完整架构图）。

## 目录结构

```
agent/core/      CaseState（写权限隔离）、AgentMessage/AgentResult/HandoffEvent、
                 Store（SQLite WAL，每线程独立连接）、EventBus（JSONL 事件 + SSE 广播）、Orchestrator
agent/roles/     八个角色 Agent；SpecialistAgent 按科室动态加载；prompts/ 八套角色提示词
agent/runtime/   LLM 客户端（OpenAI 兼容，urllib 实现）、知识检索器（RAG Top-K 注入）、
                 确定性安全规则引擎、临床管线（可暂停/可恢复状态机）、FakeLLM 剧本（仅测试）
web/static/      临床指挥台（深色指挥中心风格，原生 JS + SSE，无框架）
data/skills/     19 科室 Skill JSON + all_diseases.txt（584）+ examinations.json（837）
tests/           30 项自动化测试（FakeLLM，不真实调用大模型）
```

## 工程机制（对应佐证材料口径）

- **写权限隔离**：各智能体只返回结构化补丁，Orchestrator 按角色权限合并中心状态；
- **追加式交接**：AgentMessage / AgentResult / HandoffEvent，每次交接记录来源、目标、
  任务、风险、Skill 证据与校验结果，全量写入 SQLite + JSONL，SSE 逐步回放；
- **双重安全校验**：确定性规则引擎（过敏冲突、硝酸酯×PDE-5 前置条件、avoid/目录外/重复检查、
  红旗征象必须建议急诊）+ SafetyAgent 大模型审查；驳回即阻断，主治最多修订 2 次，
  两轮未过则保守回退并如实标注；
- **诚实边界**：检查结果由用户录入；FakeLLM 只用于自动化测试（`--fake` / `HOSPITAL_FAKE_LLM=1`），
  正式演示不自动回退假结果；模型未配置或请求失败时界面如实显示错误。

## 测试与部署

```bash
python -m pytest tests -q      # 30 passed；需要 pytest（唯一开发依赖）
docker build -t yixiao . && docker run -p 7860:7860 -e DASHSCOPE_API_KEY=sk-xxx yixiao
```

## 声明

系统输出仅用于教学演示与临床决策辅助研究，不替代真实医疗诊断、处方或急救；
演示病例均为脱敏沙盒数据，不采集、不存储任何真实患者信息。
