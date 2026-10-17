# Hospital Agent 真实多 Agent 架构

## Runtime implementation

比赛 SDK 仍通过 `MyDoctorAgent` 暴露单一入口，但入口内部由 `Orchestrator` 调度八个独立角色实例。疾病 Skill 是 Agent 使用的专业知识模块，不计作 Agent。

```text
BasicAgent / MyDoctorAgent
            |
            v
      Orchestrator
   /       |        \
 triage  interview  differential
                         |
                    examination
                         |
             specialist(dept A/B) [parallel]
                         |
                     attending
                         |
                      safety --reject/retry--> attending
                         |
                       audit
                         |
                    SDK submission
```

每次交接记录来源、目标、任务、状态、风险等级、Skill 证据和校验结果。Agent 只返回结构化 patch，由 Orchestrator 按写权限合并到中心 `CaseState`。


## 1. 总体架构总览

```mermaid
flowchart TB
    subgraph ARENA["Arena 环境"]
        P["智能体患者"]
        S["比赛服务"]
    end

    subgraph AGENT["医生智能体"]
        direction TB
        ST["结构化状态"]
        T["分诊医生"]
        H["启发式补充"]
        G["信息差分析"]
        A["多轮问诊"]
        D["去重"]
        EC["类别选择"]
        EI["项目选择"]
        SE["过度医疗抑制"]
        SP1["专科医生1"]
        SP2["专科医生2"]
        AT["主治医生"]
        SF["安全审查"]
        EV["评估"]
        RF["反思生成"]
        ME["记忆存储"]
    end

    P <--> S
    S --> AGENT
    T --> H
    H --> ST
    ST --> G
    G --> A
    A --> D
    D --> ST
    ST --> EC
    EC --> EI
    EI --> SE
    SE --> ST
    ST --> SP1
    ST --> SP2
    SP1 --> AT
    SP2 --> AT
    AT --> SF
    SF --> OUT["最终结果"]
    OUT --> EV
    EV --> RF
    RF --> ME
    ME -.-> ST
```

## 2. 数据流主循环

```mermaid
flowchart TD
    START["Patient"] --> INIT["初始问诊"]
    INIT --> TRI["分诊"]
    TRI --> GAP{"需要更多信息?"}
    GAP -->|"是"| ASK["追问"]
    ASK --> ANS["患者回答"]
    ANS --> UPD["更新状态"]
    UPD --> GAP
    GAP -->|"否"| EX["检查阶段"]
    EX --> EXC["选检查类别"]
    EXC --> EXI["选检查项目"]
    EXI --> ORD["order_examination"]
    ORD --> RES["检查结果"]
    RES --> SP1["专科1"]
    RES --> SP2["专科2"]
    SP1 --> AT["主治医生"]
    SP2 --> AT
    AT --> SF["安全审查"]
    SF --> FIN["提交终诊"]
```

## 3. 论文对应关系

```mermaid
flowchart LR
    subgraph PAPER["MMedAgent-RL"]
        PT["Triage Doctor"]
        PS["Specialists"]
        PA["Attending"]
    end

    subgraph OURS["本架构"]
        OT["分诊医生"]
        OS1["专科1"]
        OS2["专科2"]
        OA["主治医生"]
        OSF["安全审查"]
    end

    PT --> OT
    PS --> OS1
    PS --> OS2
    PA --> OA
    OA --> OSF
```

## 4. Token 优化

```mermaid
flowchart TD
    A["轮数上限"] --> G["Token 降低"]
    B["去重"] --> G
    C["信息差驱动"] --> G
    D["有限疾病列表"] --> G
    E["JSON 输出"] --> G
    F["记忆复用"] --> G
```

## 5. 完整流程图

```mermaid
flowchart TB
    PID["patient_id"] --> Q1["开放式问诊"]
    MEM["memory"] --> T1["分诊"]
    Q1 --> T1
    T1 --> H1["启发式补充"]
    H1 --> C1["候选科室"]
    C1 --> G1["信息差分析"]
    MEM --> G1
    
    G1 --> G2{"还需追问?"}
    G2 -- "是" --> G3["针对性问诊"]
    G3 --> G4["去重检查"]
    G4 --> G5["提取症状"]
    G5 --> G6["更新鉴别"]
    G6 --> G1
    
    G2 -- "否" --> E1["选检查类别"]
    E1 --> E2["选检查项目"]
    E2 --> E3["调用检查"]
    E3 --> E4["保存结果"]
    E4 --> E1
    
    E4 --> P1["专科1"]
    E4 --> P2["专科2"]
    P1 --> P3["主治决策"]
    P2 --> P3
    P3 --> P4["安全审查"]
    P4 --> P5["提交终诊"]
    
    P5 --> R1["获取评估"]
    R1 --> R2["生成反思"]
    R2 --> R3["写入记忆"]
```

## 6. 角色一览

| 角色 | Prompt | 职责 |
|------|--------|------|
| 分诊医生 | TRIAGE_PROMPT | 判断科室 |
| 信息差分析 | INFO_GAP_PROMPT | 决定追问 |
| 专科医生1 | SPECIALIST | 全科评估 |
| 专科医生2 | SPECIALIST | 鉴别诊断 |
| 主治医生 | ATTENDING | 综合决策 |
| 安全审查 | SAFETY_REVIEW | 检查禁忌 |

## 7. 对比

```mermaid
flowchart LR
    subgraph BASE["Baseline"]
        B1["单LLM循环"]
        B2["线性流程"]
        B3["简单状态"]
    end

    subgraph ENH["增强版"]
        E1["多智能体"]
        E2["多视角验证"]
        E3["结构化状态"]
        E4["安全审查"]
    end

    BASE --> ENH
```
