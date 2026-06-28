from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CorrectionSuggestionRecord(BaseModel):
    violation_id: str
    suggestion_source: str
    original_value: Optional[Any] = None
    suggested_value: Optional[Any] = None
    correction_method: str
    confidence_score: float
    explanation: str
    feature_importance: Dict[str, Any] = Field(default_factory=dict)
    model_version: Optional[str] = None


class SuggestionsPayload(BaseModel):
    suggestions: List[CorrectionSuggestionRecord] = Field(default_factory=list)
