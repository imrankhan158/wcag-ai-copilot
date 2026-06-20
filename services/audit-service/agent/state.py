from __future__ import annotations
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    user_input: str
    retrieved_criteria: list[dict]
    messages: Annotated[list, add_messages]
    violations: list[dict]
    summary: str
    score: dict
