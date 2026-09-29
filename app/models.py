from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChoiceView(BaseModel):
    choice: str
    label: str
    confidence: float
    probabilities: dict[str, float]


class ScoreView(BaseModel):
    score: float
    label: str
    confidence: float


class Judgment(BaseModel):
    engine: Literal["jev", "heuristic"]
    model: str | None = None
    latency_ms: float
    category: ChoiceView
    urgency: ScoreView
    tone: ChoiceView
    change_target: ChoiceView
    handoff_probability: float
    missing_info_probability: float
    note: str | None = None


class RouteDecision(BaseModel):
    route: Literal["handoff", "ask", "answer", "clarify"]
    reason: str


class GenerationInfo(BaseModel):
    engine: Literal["template", "llm"]
    specialist: str
    specialist_label: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    route: Literal["handoff", "ask", "answer", "clarify"]
    route_label: str
    reason: str
    judgment: Judgment
    generation: GenerationInfo
