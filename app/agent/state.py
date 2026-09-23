from __future__ import annotations

import time
from typing import Any
from pydantic import BaseModel, Field

from app.models.response import Citation, RAGResponse


class AgentStep(BaseModel):
    step_number: int
    thought: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: Any = None
    observation: str = ""
    duration_ms: float = 0.0
    status: str = "success"  # "success", "error", "budget_exceeded"
    error_message: str | None = None


class AgentTrace(BaseModel):
    question: str
    mode: str = "agent"  # "agent" or "fixed_workflow"
    steps: list[AgentStep] = Field(default_factory=list)
    final_response: RAGResponse | None = None
    total_steps: int = 0
    total_tool_calls: int = 0
    total_llm_calls: int = 0
    total_latency_seconds: float = 0.0
    estimated_prompt_tokens: int = 0
    estimated_completion_tokens: int = 0
    stopped_safely: bool = True
    stop_reason: str = "completed"  # "completed", "max_steps", "max_time", "stuck_loop", "error"
    created_at: float = Field(default_factory=time.time)


class AgentMemory(BaseModel):
    short_term_observations: list[str] = Field(default_factory=list)
    queried_terms: list[str] = Field(default_factory=list)
    inspected_sections: list[str] = Field(default_factory=list)
    accumulated_context: list[dict[str, Any]] = Field(default_factory=list)
    citations_pool: list[Citation] = Field(default_factory=list)
