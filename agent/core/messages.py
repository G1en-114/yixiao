# -*- coding: utf-8 -*-
"""Agent collaboration protocol: AgentMessage / AgentResult / HandoffEvent."""
from dataclasses import dataclass, field


@dataclass
class AgentMessage:
    from_agent: str
    to_agent: str
    case_id: str
    task: str
    risk_level: str = 'low'

    def to_dict(self):
        return {'from': self.from_agent, 'to': self.to_agent, 'case_id': self.case_id,
                'task': self.task, 'risk_level': self.risk_level}


@dataclass
class AgentResult:
    agent: str
    status: str = 'ok'                 # ok | rejected | error
    payload: dict = field(default_factory=dict)
    risk: str = 'low'
    evidence: list = field(default_factory=list)   # Skills / knowledge evidence used

    def to_dict(self):
        return {'agent': self.agent, 'status': self.status, 'payload': self.payload,
                'risk': self.risk, 'evidence': self.evidence}


@dataclass
class HandoffEvent:
    from_agent: str
    to_agent: str
    task: str
    state_summary: str
    risk_level: str = 'low'
    evidence_used: list = field(default_factory=list)
    validation: str = 'passed'

    def to_dict(self):
        return {'from_agent': self.from_agent, 'to_agent': self.to_agent, 'task': self.task,
                'state_summary': self.state_summary, 'risk_level': self.risk_level,
                'evidence_used': self.evidence_used, 'validation': self.validation}
