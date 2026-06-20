from __future__ import annotations
import json
from langchain_core.messages import HumanMessage, SystemMessage
from agent.prompts import ANALYZE_PROMPT, EVALUATE_PROMPT, SUGGEST_PROMPT, SYSTEM_PROMPT
from agent.state import AgentState
from retrieval.retriever import retrieve
from llm.provider import get_llm


def analyze_node(state: AgentState) -> dict:
    """Analyze the user's input and retrieve relevant WCAG criteria."""
    criteria = retrieve(state["user_input"], top_k=8)
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=ANALYZE_PROMPT.format(user_input=state["user_input"]))
    ])
    return {"retrieved_criteria": criteria, "messages": [response]}


def evaluate_node(state: AgentState) -> dict:
    """Evaluate input against retrieved criteria — find violations."""
    criteria_context = "\n\n".join([
        f"[{c.get('criterion_id') or c.get('technique_id') or 'n/a'}] {c['title']} (Level {c.get('level') or 'n/a'})\n{c['text']}"
        for c in state["retrieved_criteria"]
    ])
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"],
        HumanMessage(content=EVALUATE_PROMPT.format(
            criteria_context=criteria_context,
            user_input=state["user_input"],
        ))
    ])
    return {"messages": [response]}


def suggest_node(state: AgentState) -> dict:
    """Generate structured violations + fix suggestions."""
    violations_raw = state["messages"][-1].content
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=SUGGEST_PROMPT.format(
            violations_raw=violations_raw,
            user_input=state["user_input"],
        ))
    ])
    try:
        raw = response.content
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        violations = parsed.get("violations", [])
        summary = parsed.get("summary", "")
        score = parsed.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})
    except json.JSONDecodeError:
        violations = []
        summary = response.content
        score = {"A": 0, "AA": 0, "AAA": 0, "total": 0}
    return {"messages": [response], "violations": violations, "summary": summary, "score": score}
