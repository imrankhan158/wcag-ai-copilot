from __future__ import annotations

import json
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.prompts import ANALYZE_PROMPT, EVALUATE_PROMPT, SUGGEST_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.retrieval.retriever import retrieve

load_dotenv()

# Select LLM Provider dynamically
api_key = (
    os.getenv("LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("NVIDIA_API_KEY")
)
base_url = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("OPENAI_BASE_URL")
)

if not base_url and os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    base_url = "https://integrate.api.nvidia.com/v1"
    default_model = "meta/llama-3.3-70b-instruct"
else:
    default_model = "gpt-4o"

model_name = os.getenv("LLM_MODEL", default_model)

llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    temperature=0,
    streaming=True,
)


def analyze_node(state: AgentState) -> dict:
    """Analyze the user's input and retrieve relevant WCAG criteria."""
    # Retrieve top-k criteria via hybrid search
    criteria = retrieve(state["user_input"], top_k=8)

    # Ask LLM to confirm which areas to focus on
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=ANALYZE_PROMPT.format(user_input=state["user_input"]))
    ])

    return {
        "retrieved_criteria": criteria,
        "messages": [response],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate input against retrieved criteria — find violations."""
    criteria_context = "\n\n".join([
        f"[{c.get('criterion_id') or c.get('technique_id') or 'n/a'}] {c['title']} (Level {c.get('level') or 'n/a'})\n{c['text']}"
        for c in state["retrieved_criteria"]
    ])

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

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=SUGGEST_PROMPT.format(
            violations_raw=violations_raw,
            user_input=state["user_input"],
        ))
    ])

    # Parse JSON from response
    try:
        raw = response.content
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        violations = parsed.get("violations", [])
        summary = parsed.get("summary", "")
        score = parsed.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})
    except json.JSONDecodeError:
        violations = []
        summary = response.content
        score = {"A": 0, "AA": 0, "AAA": 0, "total": 0}

    return {
        "messages": [response],
        "violations": violations,
        "summary": summary,
        "score": score,
    }
