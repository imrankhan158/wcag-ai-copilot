from __future__ import annotations

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # User's original input (code snippet or description)
    user_input: str

    # Retrieved WCAG criteria from Qdrant
    retrieved_criteria: list[dict]

    # LLM messages (accumulated across nodes)
    messages: Annotated[list, add_messages]

    # Final structured output
    violations: list[dict]  # list of dicts matching the violation format
    summary: str  # overall summary assessment
    score: dict  # counts of A/AA/AAA violations and total count
