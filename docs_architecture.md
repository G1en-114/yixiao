# YiXiao Hospital Agent: Real Multi-Agent Architecture

## Runtime implementation

The competition SDK still exposes a single entry point through `MyDoctorAgent`, but inside that entry point the `Orchestrator` schedules eight independent role instances. Disease Skills are specialized knowledge modules used by the Agents and are not counted as Agents.

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

Each handoff records source, target, task, status, risk level, Skill evidence, and validation results. Agents only return structured patches, which the Orchestrator merges into the central `CaseState` according to write permissions.

## 1. Overall Architecture Overview

```mermaid
flowchart TB
    subgraph ARENA["Arena Environment"]
        P["Patient Agent"]
        S["Competition Service"]
    end

    subgraph AGENT["Doctor Agent"]
        direction TB
        ST["Structured State"]
        T["Triage Doctor"]
        H["Heuristic Supplement"]
        G["Information Gap Analysis"]
        A["Multi-turn Consultation"]
        D["Deduplication"]
        EC["Category Selection"]
        EI["Item Selection"]
        SE["Overtreatment Suppression"]
        SP1["Specialist 1"]
        SP2["Specialist 2"]
        AT["Attending Doctor"]
        SF["Safety Review"]
        EV["Evaluation"]
        RF["Reflection Generation"]
        ME["Memory Storage"]
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
    SF --> OUT["Final Result"]
    OUT --> EV
    EV --> RF
    RF --> ME
    ME -.-> ST
```

## 2. Main Data Flow Loop

```mermaid
flowchart TD
    START["Patient"] --> INIT["Initial Interview"]
    INIT --> TRI["Triage"]
    TRI --> GAP{"Need more information?"}
    GAP -->|"Yes"| ASK["Follow-up Question"]
    ASK --> ANS["Patient Answer"]
    ANS --> UPD["Update State"]
    UPD --> GAP
    GAP -->|"No"| EX["Examination Phase"]
    EX --> EXC["Select Examination Category"]
    EXC --> EXI["Select Examination Item"]
    EXI --> ORD["order_examination"]
    ORD --> RES["Examination Results"]
    RES --> SP1["Specialist 1"]
    RES --> SP2["Specialist 2"]
    SP1 --> AT["Attending Doctor"]
    SP2 --> AT
    AT --> SF["Safety Review"]
    SF --> FIN["Submit Final Diagnosis"]
```

## 3. Paper Correspondence

```mermaid
flowchart LR
    subgraph PAPER["MMedAgent-RL"]
        PT["Triage Doctor"]
        PS["Specialists"]
        PA["Attending"]
    end

    subgraph OURS["Our Architecture"]
        OT["Triage Doctor"]
        OS1["Specialist 1"]
        OS2["Specialist 2"]
        OA["Attending Doctor"]
        OSF["Safety Review"]
    end

    PT --> OT
    PS --> OS1
    PS --> OS2
    PA --> OA
    OA --> OSF
```

## 4. Token Optimization

```mermaid
flowchart TD
    A["Turn Limit"] --> G["Token Reduction"]
    B["Deduplication"] --> G
    C["Information Gap Driven"] --> G
    D["Limited Disease List"] --> G
    E["JSON Output"] --> G
    F["Memory Reuse"] --> G
```

## 5. Complete Flowchart

```mermaid
flowchart TB
    PID["patient_id"] --> Q1["Open-ended Interview"]
    MEM["memory"] --> T1["Triage"]
    Q1 --> T1
    T1 --> H1["Heuristic Supplement"]
    H1 --> C1["Candidate Departments"]
    C1 --> G1["Information Gap Analysis"]
    MEM --> G1
    
    G1 --> G2{"Need follow-up?"}
    G2 -- "Yes" --> G3["Targeted Interview"]
    G3 --> G4["Deduplication Check"]
    G4 --> G5["Extract Symptoms"]
    G5 --> G6["Update Differential"]
    G6 --> G1
    
    G2 -- "No" --> E1["Select Examination Category"]
    E1 --> E2["Select Examination Item"]
    E2 --> E3["Order Examination"]
    E3 --> E4["Save Results"]
    E4 --> E1
    
    E4 --> P1["Specialist 1"]
    E4 --> P2["Specialist 2"]
    P1 --> P3["Attending Decision"]
    P2 --> P3
    P3 --> P4["Safety Review"]
    P4 --> P5["Submit Final Diagnosis"]
    
    P5 --> R1["Get Evaluation"]
    R1 --> R2["Generate Reflection"]
    R2 --> R3["Write to Memory"]
```

## 6. Role Overview

| Role | Prompt | Responsibility |
|------|--------|------|
| Triage Doctor | TRIAGE_PROMPT | Determine department |
| Information Gap Analysis | INFO_GAP_PROMPT | Decide follow-up questions |
| Specialist 1 | SPECIALIST | General assessment |
| Specialist 2 | SPECIALIST | Differential diagnosis |
| Attending Doctor | ATTENDING | Comprehensive decision |
| Safety Review | SAFETY_REVIEW | Check contraindications |

## 7. Comparison

```mermaid
flowchart LR
    subgraph BASE["Baseline"]
        B1["Single LLM Loop"]
        B2["Linear Flow"]
        B3["Simple State"]
    end

    subgraph ENH["Enhanced Version"]
        E1["Multi-Agent"]
        E2["Multi-perspective Validation"]
        E3["Structured State"]
        E4["Safety Review"]
    end

    BASE --> ENH
```
