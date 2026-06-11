from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.nodes import analyze_node, evaluate_node, suggest_node
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("analyze", analyze_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("suggest", suggest_node)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "evaluate")
    graph.add_edge("evaluate", "suggest")
    graph.add_edge("suggest", END)

    return graph.compile()


advisor_graph = build_graph()
