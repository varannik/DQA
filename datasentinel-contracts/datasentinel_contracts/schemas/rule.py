from typing import Any, Dict

from pydantic import BaseModel, Field


class DQARuleConfig(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    severity: str = "medium"
    is_hard_gate: bool = False
    weight: float = 0.125
    parameters: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
